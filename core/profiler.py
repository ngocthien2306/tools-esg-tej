import numpy as np
import pandas as pd
from typing import Dict, Any, List, Optional


def profile_dataset(df: pd.DataFrame, entity_col: Optional[str] = None,
                    time_col: Optional[str] = None) -> Dict[str, Any]:
    rows, cols = df.shape

    cols_meta = []
    for c in df.columns:
        s = df[c]
        meta = {
            "name": c,
            "dtype": str(s.dtype),
            "n_missing": int(s.isna().sum()),
            "pct_missing": round(float(s.isna().mean() * 100), 2),
            "n_unique": int(s.nunique(dropna=True)),
            "is_numeric": bool(pd.api.types.is_numeric_dtype(s)),
        }
        if meta["is_numeric"]:
            clean = s.dropna()
            if pd.api.types.is_bool_dtype(clean):
                clean = clean.astype(float)
            if len(clean):
                meta.update({
                    "mean": float(clean.mean()),
                    "std": float(clean.std()),
                    "min": float(clean.min()),
                    "p25": float(clean.quantile(0.25)),
                    "median": float(clean.median()),
                    "p75": float(clean.quantile(0.75)),
                    "max": float(clean.max()),
                })
        cols_meta.append(meta)

    panel_info = None
    if entity_col and time_col and entity_col in df.columns and time_col in df.columns:
        n_entities = int(df[entity_col].nunique())
        n_periods = int(df[time_col].nunique())
        balanced = (n_entities * n_periods) == len(df)
        try:
            time_min = int(df[time_col].min())
            time_max = int(df[time_col].max())
        except (TypeError, ValueError):
            time_min = str(df[time_col].min())
            time_max = str(df[time_col].max())
        panel_info = {
            "entity_col": entity_col,
            "time_col": time_col,
            "n_entities": n_entities,
            "n_periods": n_periods,
            "balanced": balanced,
            "time_min": time_min,
            "time_max": time_max,
        }

    time_series: Dict[str, Any] = {}
    if time_col and time_col in df.columns:
        numeric_cols = [c for c in df.columns
                        if pd.api.types.is_numeric_dtype(df[c]) and c != time_col]
        if numeric_cols:
            try:
                ts = df.groupby(time_col)[numeric_cols].mean()
                idx = ts.index
                if pd.api.types.is_numeric_dtype(idx):
                    time_axis = [int(x) if float(x).is_integer() else float(x)
                                 for x in idx]
                else:
                    time_axis = [str(x) for x in idx]
                time_series = {
                    "time": time_axis,
                    "series": {c: [None if pd.isna(v) else round(float(v), 4)
                                   for v in ts[c]] for c in numeric_cols},
                }
            except Exception:
                pass

    return {
        "n_rows": rows,
        "n_cols": cols,
        "columns": cols_meta,
        "panel": panel_info,
        "time_series": time_series,
    }


def column_distribution(df: pd.DataFrame, col: str, bins: int = 30) -> Dict[str, Any]:
    """Histogram + boxplot stats + zero/missing/sign counts for a single column."""
    if col not in df.columns:
        return {"error": f"Column '{col}' not found"}
    s = df[col]
    n_total = len(s)
    n_missing = int(s.isna().sum())
    if not pd.api.types.is_numeric_dtype(s):
        vc = s.value_counts(dropna=False).head(20)
        return {
            "type": "categorical",
            "name": col,
            "n_total": n_total,
            "n_missing": n_missing,
            "value_counts": [{"value": str(k), "count": int(v)} for k, v in vc.items()],
        }
    clean = s.dropna().astype(float)
    if len(clean) == 0:
        return {"type": "numeric", "name": col, "n_total": n_total,
                "n_missing": n_missing, "all_missing": True}
    n_zero = int((clean == 0).sum())
    n_neg = int((clean < 0).sum())
    n_pos = int((clean > 0).sum())
    hist, edges = np.histogram(clean, bins=bins)
    try:
        skew = float(clean.skew())
        kurt = float(clean.kurt())
    except Exception:
        skew = kurt = 0.0
    return {
        "type": "numeric",
        "name": col,
        "n_total": n_total,
        "n_missing": n_missing,
        "n_zero": n_zero,
        "n_neg": n_neg,
        "n_pos": n_pos,
        "stats": {
            "mean": float(clean.mean()),
            "std": float(clean.std()),
            "min": float(clean.min()),
            "p01": float(clean.quantile(0.01)),
            "p25": float(clean.quantile(0.25)),
            "median": float(clean.median()),
            "p75": float(clean.quantile(0.75)),
            "p99": float(clean.quantile(0.99)),
            "max": float(clean.max()),
            "skew": skew,
            "kurt": kurt,
        },
        "histogram": {
            "counts": [int(c) for c in hist],
            "edges": [float(e) for e in edges],
        },
    }


def panel_balance(df: pd.DataFrame, entity_col: str, time_col: str) -> Dict[str, Any]:
    """Years-per-firm distribution + entries/exits + active count per year."""
    if entity_col not in df.columns or time_col not in df.columns:
        return {"error": "Missing entity or time column"}

    years_per_firm = df.groupby(entity_col)[time_col].nunique()
    yp_dist = years_per_firm.value_counts().sort_index()

    first_year = df.groupby(entity_col)[time_col].min()
    last_year = df.groupby(entity_col)[time_col].max()

    all_years = sorted(int(y) for y in df[time_col].dropna().unique())
    if not all_years:
        return {"error": "No time values found"}
    panel_end = all_years[-1]

    active_per_year = df.groupby(time_col)[entity_col].nunique()
    entries = first_year.value_counts().sort_index()
    exits = last_year[last_year < panel_end].value_counts().sort_index()

    n_full = int((years_per_firm == len(all_years)).sum())

    return {
        "n_firms": int(years_per_firm.shape[0]),
        "n_years": len(all_years),
        "year_min": all_years[0],
        "year_max": all_years[-1],
        "balanced": bool(n_full == years_per_firm.shape[0]),
        "complete_firms": n_full,
        "median_years_per_firm": int(years_per_firm.median()),
        "years_per_firm": {
            "x": [int(k) for k in yp_dist.index],
            "y": [int(v) for v in yp_dist.values],
        },
        "active_per_year": {
            "x": [int(y) for y in active_per_year.index],
            "y": [int(v) for v in active_per_year.values],
        },
        "entries_per_year": {
            "x": [int(y) for y in entries.index],
            "y": [int(v) for v in entries.values],
        },
        "exits_per_year": {
            "x": [int(y) for y in exits.index],
            "y": [int(v) for v in exits.values],
        },
    }


def within_between_variance(df: pd.DataFrame, entity_col: str,
                            cols: List[str]) -> List[Dict[str, Any]]:
    """Variance decomposition: how much of total variance is across-firm vs within-firm-over-time."""
    out = []
    if entity_col not in df.columns:
        return out
    for c in cols:
        if c not in df.columns or not pd.api.types.is_numeric_dtype(df[c]):
            continue
        sub = df[[entity_col, c]].dropna()
        if len(sub) < 10:
            continue
        total_var = float(sub[c].var())
        if total_var <= 0:
            continue
        between_var = float(sub.groupby(entity_col)[c].mean().var())
        if pd.isna(between_var):
            between_var = 0.0
        within_var = max(0.0, total_var - between_var)
        out.append({
            "col": c,
            "total_var": round(total_var, 4),
            "within_var": round(within_var, 4),
            "between_var": round(between_var, 4),
            "within_pct": round(within_var / total_var * 100, 2),
            "between_pct": round(between_var / total_var * 100, 2),
        })
    return out


def bivariate(df: pd.DataFrame, x_col: str, y_col: str,
              sample: int = 2000) -> Dict[str, Any]:
    """Scatter sample + linear fit + correlation for any pair of numeric variables."""
    if x_col not in df.columns or y_col not in df.columns:
        return {"error": "Column not found"}
    if not pd.api.types.is_numeric_dtype(df[x_col]) or not pd.api.types.is_numeric_dtype(df[y_col]):
        return {"error": "Both columns must be numeric"}
    sub = df[[x_col, y_col]].dropna()
    n_total = len(sub)
    if n_total > sample:
        sub = sub.sample(sample, random_state=42)
    xv = sub[x_col].astype(float).values
    yv = sub[y_col].astype(float).values
    out = {
        "x_col": x_col,
        "y_col": y_col,
        "x": [float(v) for v in xv],
        "y": [float(v) for v in yv],
        "n_shown": int(len(sub)),
        "n_total": n_total,
    }
    if len(sub) >= 5:
        try:
            slope, intercept = np.polyfit(xv, yv, 1)
            corr = float(np.corrcoef(xv, yv)[0, 1])
            out["fit"] = {
                "slope": float(slope),
                "intercept": float(intercept),
                "corr": corr,
                "x_min": float(xv.min()),
                "x_max": float(xv.max()),
            }
        except Exception:
            pass
    return out


def group_stats(df: pd.DataFrame, group_col: str, value_col: str,
                top_n: int = 30) -> Dict[str, Any]:
    """Mean ± std + N for value_col grouped by group_col, sorted by mean desc."""
    if group_col not in df.columns or value_col not in df.columns:
        return {"error": "Column not found"}
    if not pd.api.types.is_numeric_dtype(df[value_col]):
        return {"error": f"{value_col} is not numeric"}
    g = (df[[group_col, value_col]].dropna()
         .groupby(group_col)[value_col]
         .agg(['mean', 'std', 'count', 'median', 'min', 'max']))
    g = g[g['count'] >= 3].sort_values('mean', ascending=False).head(top_n)
    return {
        "group_col": group_col,
        "value_col": value_col,
        "groups": [str(k) for k in g.index],
        "mean": [float(v) for v in g['mean']],
        "std": [0.0 if pd.isna(v) else float(v) for v in g['std']],
        "median": [float(v) for v in g['median']],
        "min": [float(v) for v in g['min']],
        "max": [float(v) for v in g['max']],
        "count": [int(v) for v in g['count']],
    }


def quintile_portfolio(df: pd.DataFrame, x_col: str, y_col: str,
                       time_col: str, n_quintiles: int = 5) -> Dict[str, Any]:
    """Bin observations by quintile of x_col, plot mean y_col per quintile over time."""
    if not all(c in df.columns for c in [x_col, y_col, time_col]):
        return {"error": "Column not found"}
    sub = df[[x_col, y_col, time_col]].dropna()
    if len(sub) < n_quintiles * 5:
        return {"error": "Not enough data"}
    try:
        sub = sub.copy()
        sub["_q"] = pd.qcut(sub[x_col], q=n_quintiles, labels=False, duplicates="drop")
    except Exception as e:
        return {"error": f"Could not bin: {e}"}
    if sub["_q"].isna().all():
        return {"error": "Could not produce quintile bins"}
    agg = (sub.groupby([time_col, "_q"])[y_col].mean().unstack("_q").sort_index())
    qs = sorted([int(q) for q in agg.columns])
    n_q = len(qs)
    return {
        "x_col": x_col,
        "y_col": y_col,
        "time_col": time_col,
        "time": [int(t) for t in agg.index],
        "quintiles": [
            {
                "label": (f"Q{q+1}"
                          + (" (lowest)" if q == qs[0] else
                             " (highest)" if q == qs[-1] else "")),
                "values": [None if pd.isna(v) else round(float(v), 4)
                           for v in agg[q]],
            }
            for q in qs
        ],
        "n_quintiles_actual": n_q,
    }


def treated_control_trend(df: pd.DataFrame, treat_col: str, value_col: str,
                          time_col: str, cutoff_method: str = "median_pre",
                          cutoff_value: Optional[float] = None,
                          post_year: Optional[int] = None) -> Dict[str, Any]:
    """DID-style trend: split firms by cutoff on treat_col, plot value_col mean over time per group."""
    if not all(c in df.columns for c in [treat_col, value_col, time_col]):
        return {"error": "Column not found"}
    sub = df[[treat_col, value_col, time_col]].dropna().copy()
    if len(sub) == 0:
        return {"error": "No data after dropping NaN"}

    if cutoff_method == "median_pre" and post_year is not None:
        pre = sub[sub[time_col] < post_year]
        if len(pre) == 0:
            return {"error": "No pre-policy observations"}
        cutoff = float(pre[treat_col].median())
    elif cutoff_value is not None:
        cutoff = float(cutoff_value)
    else:
        cutoff = float(sub[treat_col].median())

    sub["_high"] = (sub[treat_col] > cutoff).astype(int)
    high = (sub[sub["_high"] == 1].groupby(time_col)[value_col]
            .agg(["mean", "count"]).sort_index())
    low = (sub[sub["_high"] == 0].groupby(time_col)[value_col]
           .agg(["mean", "count"]).sort_index())

    all_t = sorted(set(high.index) | set(low.index))
    return {
        "treat_col": treat_col,
        "value_col": value_col,
        "time_col": time_col,
        "cutoff": cutoff,
        "post_year": post_year,
        "time": [int(t) for t in all_t],
        "high_mean": [None if t not in high.index or pd.isna(high.loc[t, "mean"])
                      else round(float(high.loc[t, "mean"]), 4) for t in all_t],
        "low_mean": [None if t not in low.index or pd.isna(low.loc[t, "mean"])
                     else round(float(low.loc[t, "mean"]), 4) for t in all_t],
        "high_count": [int(high.loc[t, "count"]) if t in high.index else 0
                       for t in all_t],
        "low_count": [int(low.loc[t, "count"]) if t in low.index else 0
                      for t in all_t],
    }


def firm_trajectories(df: pd.DataFrame, entity_col: str, time_col: str,
                      value_col: str, n_sample: int = 15,
                      seed: int = 42) -> Dict[str, Any]:
    """Plot value_col over time for N randomly sampled entities + overall mean."""
    if not all(c in df.columns for c in [entity_col, time_col, value_col]):
        return {"error": "Column not found"}
    sub = df[[entity_col, time_col, value_col]].dropna()
    if len(sub) == 0:
        return {"error": "No data"}
    counts = sub.groupby(entity_col)[time_col].count()
    valid = counts[counts >= 3].index
    if len(valid) == 0:
        return {"error": "No entities with ≥ 3 observations"}
    sample_size = min(n_sample, len(valid))
    sampled = pd.Series(list(valid)).sample(sample_size, random_state=seed).tolist()
    trajectories = []
    for ent in sampled:
        d = sub[sub[entity_col] == ent].sort_values(time_col)
        trajectories.append({
            "entity": str(ent),
            "x": [int(t) for t in d[time_col]],
            "y": [round(float(v), 4) for v in d[value_col]],
        })
    mean = sub.groupby(time_col)[value_col].mean().sort_index()
    return {
        "entity_col": entity_col,
        "time_col": time_col,
        "value_col": value_col,
        "trajectories": trajectories,
        "mean": {
            "x": [int(t) for t in mean.index],
            "y": [round(float(v), 4) for v in mean.values],
        },
        "n_sampled": sample_size,
        "n_eligible": int(len(valid)),
    }


def lead_lag_correlation(df: pd.DataFrame, x_col: str, y_col: str,
                         entity_col: str, time_col: str,
                         max_lag: int = 3) -> Dict[str, Any]:
    """corr(X(t-k), Y(t)) for k in [-max_lag, max_lag]. Negative k = X leads."""
    if not all(c in df.columns for c in [x_col, y_col, entity_col, time_col]):
        return {"error": "Column not found"}
    sub = (df[[entity_col, time_col, x_col, y_col]].dropna()
           .sort_values([entity_col, time_col]).copy())
    if len(sub) < 10:
        return {"error": "Not enough data"}

    results = []
    for k in range(-max_lag, max_lag + 1):
        x_shifted = sub.groupby(entity_col)[x_col].shift(k)
        mask = x_shifted.notna() & sub[y_col].notna()
        n = int(mask.sum())
        if n < 10:
            results.append({"lag": k, "corr": None, "n": n})
            continue
        try:
            corr = float(np.corrcoef(x_shifted[mask], sub[y_col][mask])[0, 1])
        except Exception:
            corr = None
        results.append({"lag": k, "corr": corr, "n": n})

    return {
        "x_col": x_col,
        "y_col": y_col,
        "lags": [r["lag"] for r in results],
        "correlations": [r["corr"] for r in results],
        "n": [r["n"] for r in results],
        "max_lag": max_lag,
    }


def outlier_scores(df: pd.DataFrame, cols: List[str],
                   entity_col: Optional[str] = None,
                   time_col: Optional[str] = None,
                   threshold: float = 3.0,
                   top_n: int = 50) -> Dict[str, Any]:
    """Flag rows where any column has |z-score| > threshold. Returns top extremes."""
    valid_cols = [c for c in cols
                  if c in df.columns and pd.api.types.is_numeric_dtype(df[c])]
    if not valid_cols:
        return {"error": "No valid numeric columns"}

    z_df = pd.DataFrame(index=df.index)
    for c in valid_cols:
        s = df[c]
        mean, std = s.mean(), s.std()
        z_df[c] = (s - mean) / std if std and std > 0 else 0.0

    abs_z = z_df.abs()
    max_z = abs_z.max(axis=1)
    extreme_col = abs_z.idxmax(axis=1)

    flagged = max_z > threshold
    n_flagged = int(flagged.sum())

    extreme = df.loc[flagged].copy()
    extreme["_max_z"] = max_z[flagged]
    extreme["_extreme_col"] = extreme_col[flagged]
    extreme = extreme.sort_values("_max_z", ascending=False).head(top_n)

    rows = []
    for _, r in extreme.iterrows():
        c = str(r["_extreme_col"])
        row = {
            "max_z": round(float(r["_max_z"]), 2),
            "extreme_col": c,
            "value": (round(float(r[c]), 4)
                      if c in df.columns and pd.notna(r[c]) else None),
        }
        if entity_col and entity_col in df.columns:
            row["entity"] = str(r[entity_col])
        if time_col and time_col in df.columns and pd.notna(r[time_col]):
            try:
                row["time"] = int(r[time_col])
            except (ValueError, TypeError):
                row["time"] = str(r[time_col])
        rows.append(row)

    return {
        "threshold": threshold,
        "n_flagged": n_flagged,
        "n_total": len(df),
        "pct_flagged": round(n_flagged / len(df) * 100, 2) if len(df) else 0,
        "rows": rows,
        "cols_used": valid_cols,
    }


def density_ridgeplot(df: pd.DataFrame, value_col: str, group_col: str,
                      n_bins: int = 50) -> Dict[str, Any]:
    """Per-group histogram density on a shared x-grid for ridgeplot rendering."""
    if value_col not in df.columns or group_col not in df.columns:
        return {"error": "Column not found"}
    if not pd.api.types.is_numeric_dtype(df[value_col]):
        return {"error": f"{value_col} must be numeric"}
    sub = df[[value_col, group_col]].dropna()
    if len(sub) < 10:
        return {"error": "Not enough data"}

    vmin = float(sub[value_col].min())
    vmax = float(sub[value_col].max())
    if vmin == vmax:
        return {"error": "Variable has no spread"}
    edges = np.linspace(vmin, vmax, n_bins + 1)
    centers = (edges[:-1] + edges[1:]) / 2

    raw_groups = sub[group_col].unique()
    try:
        groups = sorted(raw_groups)
    except TypeError:
        groups = sorted(raw_groups, key=str)

    densities = []
    for g in groups:
        gdata = sub[sub[group_col] == g][value_col]
        if len(gdata) < 5:
            continue
        hist, _ = np.histogram(gdata, bins=edges, density=True)
        densities.append({
            "group": str(g),
            "density": [float(h) for h in hist],
            "n": int(len(gdata)),
            "mean": round(float(gdata.mean()), 4),
            "median": round(float(gdata.median()), 4),
        })

    return {
        "value_col": value_col,
        "group_col": group_col,
        "centers": [float(c) for c in centers],
        "densities": densities,
    }


def first_differences(df: pd.DataFrame, x_col: str, y_col: str,
                      entity_col: str, time_col: str,
                      sample: int = 2000) -> Dict[str, Any]:
    """Within-firm Δ scatter: corr between year-over-year changes in x and y."""
    if not all(c in df.columns for c in [x_col, y_col, entity_col, time_col]):
        return {"error": "Column not found"}
    sub = (df[[entity_col, time_col, x_col, y_col]].dropna()
           .sort_values([entity_col, time_col]).copy())
    sub["dx"] = sub.groupby(entity_col)[x_col].diff()
    sub["dy"] = sub.groupby(entity_col)[y_col].diff()
    sub = sub.dropna(subset=["dx", "dy"])
    n_total = len(sub)
    if n_total < 5:
        return {"error": "Not enough first-differences (need entities with ≥ 2 years)"}
    if n_total > sample:
        sub = sub.sample(sample, random_state=42)
    xv = sub["dx"].astype(float).values
    yv = sub["dy"].astype(float).values
    out = {
        "x_col": f"Δ {x_col}",
        "y_col": f"Δ {y_col}",
        "x": [float(v) for v in xv],
        "y": [float(v) for v in yv],
        "n_shown": int(len(sub)),
        "n_total": int(n_total),
    }
    if len(sub) >= 5:
        try:
            slope, intercept = np.polyfit(xv, yv, 1)
            corr = float(np.corrcoef(xv, yv)[0, 1])
            out["fit"] = {
                "slope": float(slope), "intercept": float(intercept),
                "corr": corr,
                "x_min": float(xv.min()), "x_max": float(xv.max()),
            }
        except Exception:
            pass
    return out


def bubble_chart(df: pd.DataFrame, x_col: str, y_col: str, size_col: str,
                 color_col: Optional[str] = None,
                 sample: int = 500) -> Dict[str, Any]:
    """4-dim scatter: x, y, size, color (optional categorical)."""
    needed = [x_col, y_col, size_col]
    if color_col:
        needed.append(color_col)
    for c in needed:
        if c not in df.columns:
            return {"error": f"Column '{c}' not found"}
    for c in [x_col, y_col, size_col]:
        if not pd.api.types.is_numeric_dtype(df[c]):
            return {"error": f"Column '{c}' must be numeric"}
    sub = df[needed].dropna()
    if len(sub) == 0:
        return {"error": "No data after dropping NaN"}
    if len(sub) > sample:
        sub = sub.sample(sample, random_state=42)
    out = {
        "x_col": x_col, "y_col": y_col, "size_col": size_col,
        "x": [float(v) for v in sub[x_col]],
        "y": [float(v) for v in sub[y_col]],
        "size": [float(v) for v in sub[size_col]],
        "n": int(len(sub)),
    }
    if color_col:
        out["color_col"] = color_col
        out["color"] = [str(v) for v in sub[color_col]]
    return out


def pivot_heatmap(df: pd.DataFrame, row_col: str, col_col: str, value_col: str,
                  agg: str = "mean") -> Dict[str, Any]:
    """2D pivot: row × col, cell = aggregated value."""
    if not all(c in df.columns for c in [row_col, col_col, value_col]):
        return {"error": "Column not found"}
    if not pd.api.types.is_numeric_dtype(df[value_col]):
        return {"error": f"{value_col} must be numeric"}
    if agg not in ("mean", "median", "sum", "count", "std", "min", "max"):
        agg = "mean"
    sub = df[[row_col, col_col, value_col]].dropna(subset=[row_col, col_col])
    if len(sub) == 0:
        return {"error": "No data after dropping NaN keys"}
    try:
        pivot = sub.pivot_table(index=row_col, columns=col_col,
                                values=value_col, aggfunc=agg)
    except Exception as e:
        return {"error": f"Pivot failed: {e}"}
    try:
        pivot = pivot.sort_index()
    except TypeError:
        pivot.index = pivot.index.astype(str)
        pivot = pivot.sort_index()
    try:
        pivot = pivot.sort_index(axis=1)
    except TypeError:
        pivot.columns = pivot.columns.astype(str)
        pivot = pivot.sort_index(axis=1)
    return {
        "row_col": row_col,
        "col_col": col_col,
        "value_col": value_col,
        "agg": agg,
        "rows": [str(r) for r in pivot.index],
        "cols": [str(c) for c in pivot.columns],
        "values": [[None if pd.isna(v) else round(float(v), 3)
                    for v in row] for row in pivot.values],
    }


def correlation_matrix(df: pd.DataFrame,
                       cols: Optional[List[str]] = None) -> Dict[str, Any]:
    if cols is None:
        cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    sub = df[cols].dropna()
    if len(sub) < 2:
        return {"cols": cols, "matrix": []}
    corr = sub.corr().round(3)
    return {
        "cols": list(corr.columns),
        "matrix": corr.values.tolist(),
    }
