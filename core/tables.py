"""Build layout-agnostic table specs from a run's result dict.

A *table spec* is a plain-data structure (dicts/lists) describing an academic
regression table. Renderers (xlsx/docx/html) consume the spec — they never
touch the raw result dict. This keeps formatting concerns out of the layout
logic and lets a new output format be added as a single renderer.
"""
import re
from typing import Dict, Any, List, Optional

_LAG_RE = re.compile(r"_L\d+$")

# Variables that should never be shown as coefficient rows in a publication
# table (they are reported as "Yes/No" fixed-effect indicator rows instead).
_HIDDEN_PREFIXES = ("IND_",)


def _strip_lag(name: str) -> str:
    return _LAG_RE.sub("", name)


def _lag_of(name: str):
    m = _LAG_RE.search(name)
    return int(m.group(0)[2:]) if m else None


def _disp(name: str, aliases: Optional[Dict[str, str]]) -> str:
    base = _strip_lag(name)
    if aliases and base in aliases:
        return aliases[base]
    return base


def _se_note(cfg: Dict[str, Any]) -> str:
    return ("Standard errors clustered by firm."
            if cfg.get("cluster_entity") else "Heteroskedasticity-robust standard errors.")


def _models(run_data: Dict[str, Any]) -> List[tuple]:
    """(name, data) for models that fitted successfully, in insertion order."""
    return [(m, d) for m, d in run_data["results"].items() if "error" not in d]


def _is_subsample(model_name: str) -> bool:
    return "(>0)" in model_name or model_name.endswith("> 0")


def _cell(coef_data: Dict[str, Any], stat: str) -> Dict[str, Any]:
    val = {"tstat": coef_data["tstat"], "se": coef_data["se"],
           "pvalue": coef_data["pvalue"]}.get(stat, coef_data["tstat"])
    return {
        "coef": coef_data["coef"],
        "stat": val,
        "stars": coef_data["sig"],
        "p": coef_data["pvalue"],
    }


def _ordered_vars(models: List[tuple]) -> List[str]:
    """Key (model-specific) variables first, then shared controls, IND_* dropped."""
    key_vars: List[str] = []
    for _, d in models:
        for v in d.get("extra_vars", []):
            if v not in key_vars:
                key_vars.append(v)
    controls: List[str] = []
    for _, d in models:
        for c in d["coefs"]:
            v = c["var"]
            if v in key_vars or v.startswith(_HIDDEN_PREFIXES):
                continue
            if v not in controls:
                controls.append(v)
    return key_vars + controls


def _fe_rows(cfg: Dict[str, Any], ncols: int) -> List[Dict[str, Any]]:
    industry = bool(cfg.get("industry_effects") and not cfg.get("entity_effects"))
    rows = []
    rows.append({"label": "Firm FE", "values": ["Yes" if cfg.get("entity_effects") else "No"] * ncols})
    rows.append({"label": "Year FE", "values": ["Yes" if cfg.get("time_effects") else "No"] * ncols})
    rows.append({"label": "Industry FE", "values": ["Yes" if industry else "No"] * ncols})
    return rows


def _note(cfg: Dict[str, Any], stat: str) -> str:
    stat_label = {"tstat": "t-statistics", "se": "Standard errors",
                  "pvalue": "p-values"}.get(stat, "t-statistics")
    return (f"{stat_label} in parentheses. "
            f"*** p<0.01, ** p<0.05, * p<0.10. {_se_note(cfg)}")


def _build_panel(name: str, models: List[tuple], var_order: List[str],
                 cfg: Dict[str, Any], stat: str,
                 aliases: Optional[Dict[str, str]],
                 rsq_label: str = "Within R²") -> Dict[str, Any]:
    columns = [{"idx": f"({i+1})", "model": m, "label": d.get("label", "")}
               for i, (m, d) in enumerate(models)]

    # coef lookup: var -> column index -> cell
    coef_rows = []
    for v in var_order:
        cells = []
        present = False
        for _, d in models:
            cd = next((c for c in d["coefs"] if c["var"] == v), None)
            if cd:
                cells.append(_cell(cd, stat))
                present = True
            else:
                cells.append(None)
        if present:
            coef_rows.append({"label": _disp(v, aliases),
                              "lag": _lag_of(v), "cells": cells})

    ncols = len(models)
    stat_rows = _fe_rows(cfg, ncols)
    stat_rows.append({"label": "Observations",
                      "values": [f"{d['n_obs']:,}" for _, d in models]})
    stat_rows.append({"label": rsq_label,
                      "values": [f"{d['rsq_within']:.3f}" for _, d in models]})

    return {"name": name, "columns": columns, "rows": coef_rows, "stat_rows": stat_rows}


def build_publication(run_data: Dict[str, Any], stat: str = "tstat",
                      aliases: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """Academic regression table: models as columns, coef over (stat), panels."""
    cfg = run_data["config"]
    models = _models(run_data)
    var_order = _ordered_vars(models)

    full = [(m, d) for m, d in models if not _is_subsample(m)]
    sub = [(m, d) for m, d in models if _is_subsample(m)]

    panels = []
    if full and sub:
        panels.append(_build_panel("Panel A. Full Sample", full, var_order, cfg, stat, aliases))
        panels.append(_build_panel("Panel B. Non-Zero Revenue Share Subsample", sub, var_order, cfg, stat, aliases))
    else:
        only = full or sub or models
        panels.append(_build_panel("", only, var_order, cfg, stat, aliases))

    return {
        "kind": "publication",
        "title": f"Table. {cfg['target']}",
        "subtitle": "Panel regression estimates",
        "panels": panels,
        "note": _note(cfg, stat),
        "stat": stat,
    }


def build_journal(run_data: Dict[str, Any], stat: str = "tstat",
                  aliases: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """Journal-style table: like publication, plus a 'Dependent variable'
    grouped header spanning the model columns, and 'R-squared' label."""
    cfg = run_data["config"]
    models = _models(run_data)
    var_order = _ordered_vars(models)
    full = [(m, d) for m, d in models if not _is_subsample(m)]
    sub = [(m, d) for m, d in models if _is_subsample(m)]

    dep = aliases.get(cfg["target"], cfg["target"]) if aliases else cfg["target"]

    def mk(name, ms):
        p = _build_panel(name, ms, var_order, cfg, stat, aliases, rsq_label="R-squared")
        p["group_header"] = {"label": "Dependent variable", "value": dep}
        return p

    panels = []
    if full and sub:
        panels.append(mk("Panel A. Full Sample", full))
        panels.append(mk("Panel B. Non-Zero Revenue Share Subsample", sub))
    else:
        panels.append(mk("", full or sub or models))

    return {
        "kind": "journal",
        "title": f"Table. {cfg['target']}",
        "subtitle": "",
        "panels": panels,
        "note": _note(cfg, stat),
        "stat": stat,
    }


def build_comparison(run_data: Dict[str, Any], stat: str = "tstat",
                     aliases: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """Wide matrix: one row per variable, coef + (stat) per model column.

    Reuses the publication panel structure but forces a single panel with
    every model as a column.
    """
    cfg = run_data["config"]
    models = _models(run_data)
    var_order = _ordered_vars(models)
    panel = _build_panel("", models, var_order, cfg, stat, aliases)
    return {
        "kind": "comparison",
        "title": f"Table. {cfg['target']} — model comparison",
        "subtitle": "",
        "panels": [panel],
        "note": _note(cfg, stat),
        "stat": stat,
    }


def build_correlation(corr_data: Dict[str, Any],
                      aliases: Optional[Dict[str, str]] = None,
                      pos: str = "#dc2626", neg: str = "#2563eb") -> Dict[str, Any]:
    """Academic lower-triangular correlation table, heat-shaded by correlation
    value (pos colour for +, neg colour for −) and bold where significant."""
    vars_raw = corr_data["vars"]
    names = [(aliases.get(v, v) if aliases else v) for v in vars_raw]
    k = len(vars_raw)
    r = corr_data["r"]
    p = corr_data["p"]
    n_obs = corr_data.get("n_obs", 0)

    rows = []
    for i in range(k):
        cells = []
        for j in range(k):
            if j > i:
                cells.append(None)                       # upper triangle blank
            elif j == i:
                cells.append({"r": 1.0, "bold": False})
            else:
                rv = r[i][j]
                if rv is None:
                    cells.append(None)
                else:
                    pv = p[i][j]
                    cells.append({"r": rv, "bold": pv is not None and pv <= 0.05})
        rows.append(cells)

    note = (f"This table reports pairwise correlations among the variables used in "
            f"the analysis. The sample consists of {n_obs:,} firm-year observations. "
            f"Cell colour intensity is proportional to the correlation magnitude; "
            f"bold coefficients are significant at the 5% level (two-tailed).")
    return {
        "kind": "correlation",
        "title": "Correlation Matrix",
        "note": note,
        "n_vars": k,
        "rows": rows,
        "var_list": list(enumerate(names, 1)),
        "pos": (pos or "#dc2626"),
        "neg": (neg or "#2563eb"),
    }


def build_vif(vif_data: Dict[str, Any],
              aliases: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """VIF diagnostic table: Variable | VIF | √VIF | Tolerance, + Mean VIF."""
    import math
    rows = []
    for r in vif_data["rows"]:
        name = aliases.get(r["var"], r["var"]) if aliases else r["var"]
        rows.append({
            "name": name,
            "vif": ("∞" if not math.isfinite(r["vif"]) else f"{r['vif']:.2f}"),
            "sqrt_vif": ("∞" if not math.isfinite(r["sqrt_vif"]) else f"{r['sqrt_vif']:.2f}"),
            "tol": f"{r['tolerance']:.3f}",
        })
    return {
        "kind": "vif",
        "title": "Variance Inflation Factor (VIF) Test",
        "subtitle": "Table A1. Variance Inflation Factor (VIF) Results",
        "rows": rows,
        "mean_vif": f"{vif_data['mean_vif']:.2f}",
        "n": vif_data.get("n", 0),
    }


def build_spec(run_data: Dict[str, Any], layout: str = "publication",
               stat: str = "tstat", aliases: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    if layout == "comparison":
        return build_comparison(run_data, stat, aliases)
    if layout == "journal":
        return build_journal(run_data, stat, aliases)
    return build_publication(run_data, stat, aliases)
