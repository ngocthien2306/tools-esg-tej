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
