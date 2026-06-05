import numpy as np
import pandas as pd
from scipy.stats.mstats import winsorize
from typing import Dict, Any
from .config import AnalysisConfig, ModelSpec
from .runner import fit_panel
from .loader import load_dataset


def _sig(p: float) -> str:
    return "***" if p < 0.01 else ("**" if p < 0.05 else ("*" if p < 0.10 else ""))


def _make_lag(df: pd.DataFrame, col: str, lag: int, entity_col: str) -> str:
    if lag == 0:
        return col
    new_c = f"{col}_L{lag}"
    df[new_c] = df.groupby(entity_col)[col].shift(lag)
    return new_c


def run_analysis(cfg: AnalysisConfig) -> Dict[str, Any]:
    df = load_dataset(cfg.dataset_id)

    # Drop duplicate column labels (keep first). A duplicated label makes df[col]
    # return a DataFrame instead of a Series, which breaks lag/winsorize/fit.
    if df.columns.duplicated().any():
        df = df.loc[:, ~df.columns.duplicated()].copy()

    # Year filter
    if cfg.year_min is not None and cfg.time_col in df.columns:
        df = df[df[cfg.time_col] >= cfg.year_min].copy()
    if cfg.year_max is not None and cfg.time_col in df.columns:
        df = df[df[cfg.time_col] <= cfg.year_max].copy()

    # Log transform
    for col in cfg.log_transform_cols:
        if col in df.columns:
            new_col = f"ln_{col}"
            df[new_col] = np.log(df[col].abs().replace(0, np.nan))

    # Winsorize
    if cfg.winsorize_limits and cfg.winsorize_cols:
        lo, hi = cfg.winsorize_limits[0], cfg.winsorize_limits[1]
        for col in cfg.winsorize_cols:
            if col in df.columns and pd.api.types.is_numeric_dtype(df[col]):
                df[col] = winsorize(df[col].astype(float), limits=[lo, hi])

    # DID variables — firm-level treatment fixed by pre-period average
    did_info = None
    did_warning = None
    if (cfg.did_enabled and cfg.did_treat_col
            and cfg.did_treat_col in df.columns
            and cfg.time_col in df.columns):
        pre = df[df[cfg.time_col] < cfg.did_post_year]
        if pre.empty:
            did_warning = (
                "DID skipped: no pre-period rows "
                f"(time_col < {cfg.did_post_year}). Lower the Post year."
            )
        else:
            firm_pre = pre.groupby(cfg.entity_col)[cfg.did_treat_col].mean()
            firm_pre = firm_pre.dropna()
            if cfg.did_cutoff_method == "median_pre":
                cutoff = float(firm_pre.median()) if not firm_pre.empty else float("nan")
            else:
                cutoff = float(cfg.did_cutoff_value or 0)

            if pd.isna(cutoff) or firm_pre.empty:
                did_warning = "DID skipped: insufficient pre-period data to compute cutoff."
            else:
                n_firms_total = int(df[cfg.entity_col].nunique())
                high_map = (firm_pre > cutoff).astype(int)
                df["High_Treat"] = df[cfg.entity_col].map(high_map)
                df = df.dropna(subset=["High_Treat"]).copy()
                df["High_Treat"] = df["High_Treat"].astype(int)
                df["Post"] = (df[cfg.time_col] >= cfg.did_post_year).astype(int)
                df["DID"] = df["High_Treat"] * df["Post"]
                did_info = {
                    "treat_col": cfg.did_treat_col,
                    "cutoff": cutoff,
                    "post_year": cfg.did_post_year,
                    "assignment": "firm-level pre-period mean",
                    "n_firms_high": int(high_map.sum()),
                    "n_firms_low": int((1 - high_map).sum()),
                    "n_firms_dropped": n_firms_total - int(len(firm_pre)),
                    "n_high": int(df["High_Treat"].sum()),
                    "n_post": int(df["Post"].sum()),
                    "n_did": int(df["DID"].sum()),
                }

    # Sort & lag
    df = df.sort_values([cfg.entity_col, cfg.time_col])

    # A revenue (key) variable must not double as a base control, otherwise it
    # enters every model as a regressor and shows up in all columns instead of
    # only in its own model.
    rev_set = set(cfg.revenue_vars)
    base_lag_cols = [_make_lag(df, c, cfg.base_lag, cfg.entity_col)
                     for c in cfg.base_features
                     if c in df.columns and c not in rev_set]
    rev_lag_cols = {c: _make_lag(df, c, cfg.rev_lag, cfg.entity_col)
                    for c in cfg.revenue_vars if c in df.columns}

    # Industry dummies (skip if entity_effects also on — collinear)
    ind_cols = []
    if (cfg.industry_effects and not cfg.entity_effects
            and cfg.industry_col and cfg.industry_col in df.columns):
        ind_d = pd.get_dummies(df[cfg.industry_col], prefix="IND", drop_first=True)
        df = pd.concat([df, ind_d.astype(float)], axis=1)
        ind_cols = list(ind_d.columns)

    # Set panel index
    panel = df.set_index([cfg.entity_col, cfg.time_col])

    if base_lag_cols:
        panel_lag = panel.dropna(subset=base_lag_cols).copy()
    else:
        panel_lag = panel.copy()

    n_full = len(panel)
    n_lag = len(panel_lag)
    n_firms = int(panel_lag.index.get_level_values(0).nunique()) if n_lag else 0

    # Auto-generate models if user didn't specify
    if not cfg.models:
        cfg.models = [ModelSpec(name="Model 1", extra_vars=[], label="Base controls")]
        mode = cfg.sample_filter_mode
        for rv in cfg.revenue_vars:
            if rv not in rev_lag_cols:
                continue
            if mode in ("none", "compare_both"):
                cfg.models.append(ModelSpec(
                    name=f"+ {rv}",
                    extra_vars=[rv],
                    label="full sample",
                ))
            if mode in ("positive", "compare_both"):
                cfg.models.append(ModelSpec(
                    name=f"+ {rv} (>0)",
                    extra_vars=[rv],
                    filter_col=rv,
                    filter_op=">",
                    filter_value=0.0,
                    label=f"{rv} > 0",
                ))
        if did_info:
            cfg.models.append(ModelSpec(
                name="Model DID",
                extra_vars=["High_Treat", "Post", "DID"],
                label="DID",
            ))

    results: Dict[str, Any] = {}
    summary_rows = []

    for model in cfg.models:
        # Map raw revenue vars to lag versions
        extra = []
        for v in model.extra_vars:
            if v in rev_lag_cols:
                extra.append(rev_lag_cols[v])
            elif v in panel_lag.columns:
                extra.append(v)

        sub = panel_lag.copy()
        if extra:
            sub = sub.dropna(subset=extra)

        if model.filter_col and model.filter_col in sub.columns:
            op, val = model.filter_op, model.filter_value
            if op == ">":
                sub = sub[sub[model.filter_col] > val]
            elif op == ">=":
                sub = sub[sub[model.filter_col] >= val]
            elif op == "<":
                sub = sub[sub[model.filter_col] < val]
            elif op == "<=":
                sub = sub[sub[model.filter_col] <= val]
            elif op == "==":
                sub = sub[sub[model.filter_col] == val]

        if len(sub) < 10:
            results[model.name] = {"error": f"Too few observations ({len(sub)})"}
            continue

        valid_ind = [c for c in ind_cols if c in sub.columns and sub[c].nunique() > 1]
        # De-duplicate while preserving order: a key variable that is also a base
        # feature would otherwise appear twice and make sub[xcols] a 2-D selection,
        # which PanelOLS rejects with "'DataFrame' object has no attribute 'dtype'".
        seen = set()
        xcols = [c for c in (base_lag_cols + extra + valid_ind)
                 if c != cfg.target and not (c in seen or seen.add(c))]

        if not xcols:
            results[model.name] = {"error": "No regressors"}
            continue

        if cfg.target not in sub.columns:
            results[model.name] = {"error": f"Target '{cfg.target}' not in dataset"}
            continue

        try:
            res = fit_panel(
                sub[cfg.target].astype(float),
                sub[xcols].astype(float),
                entity_effects=cfg.entity_effects,
                time_effects=cfg.time_effects,
                cluster_entity=cfg.cluster_entity,
            )
        except Exception as e:
            results[model.name] = {"error": f"{type(e).__name__}: {e}"}
            continue

        ci = res.conf_int()
        coefs = []
        for v in res.params.index:
            if v.startswith("IND_"):
                continue
            p = float(res.pvalues[v])
            coefs.append({
                "var": v,
                "coef": float(res.params[v]),
                "se": float(res.std_errors[v]),
                "tstat": float(res.tstats[v]),
                "pvalue": p,
                "ci_low": float(ci.loc[v].iloc[0]),
                "ci_high": float(ci.loc[v].iloc[1]),
                "sig": _sig(p),
            })

        results[model.name] = {
            "label": model.label,
            "n_obs": int(res.nobs),
            "n_entities": int(res.entity_info.total),
            "rsq_within": float(res.rsquared),
            "rsq_between": float(res.rsquared_between),
            "rsq_overall": float(res.rsquared_overall),
            "coefs": coefs,
            "extra_vars": extra,
            "x_cols": xcols,
        }

        key_var = extra[0] if extra else (base_lag_cols[0] if base_lag_cols else None)
        key_p = ""
        key_sig = ""
        if key_var and key_var in res.params.index:
            kp = float(res.pvalues[key_var])
            key_p = round(kp, 4)
            key_sig = _sig(kp) or "n.s."

        summary_rows.append({
            "model": model.name,
            "label": model.label,
            "key_var": key_var,
            "key_p": key_p,
            "key_sig": key_sig,
            "n_obs": int(res.nobs),
            "rsq_within": round(float(res.rsquared), 4),
            "rsq_overall": round(float(res.rsquared_overall), 4),
        })

    return {
        "config": cfg.model_dump(),
        "panel": {
            "n_full": int(n_full),
            "n_lag": int(n_lag),
            "n_firms": n_firms,
            "n_dropped": int(n_full - n_lag),
        },
        "did": did_info,
        "did_warning": did_warning,
        "summary": summary_rows,
        "results": results,
    }
