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


def _build_panel(name: str, models: List[tuple], var_order: List[str],
                 cfg: Dict[str, Any], stat: str,
                 aliases: Optional[Dict[str, str]]) -> Dict[str, Any]:
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
    stat_rows.append({"label": "Within R²",
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

    stat_label = {"tstat": "t-statistics", "se": "Standard errors",
                  "pvalue": "p-values"}.get(stat, "t-statistics")
    note = (f"{stat_label} in parentheses. "
            f"*** p<0.01, ** p<0.05, * p<0.10. {_se_note(cfg)}")

    return {
        "kind": "publication",
        "title": f"Table. {cfg['target']}",
        "subtitle": "Panel regression estimates",
        "panels": panels,
        "note": note,
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

    stat_label = {"tstat": "t-statistics", "se": "Standard errors",
                  "pvalue": "p-values"}.get(stat, "t-statistics")
    note = (f"{stat_label} in parentheses. "
            f"*** p<0.01, ** p<0.05, * p<0.10. {_se_note(cfg)}")
    return {
        "kind": "comparison",
        "title": f"Table. {cfg['target']} — model comparison",
        "subtitle": "",
        "panels": [panel],
        "note": note,
        "stat": stat,
    }


def build_spec(run_data: Dict[str, Any], layout: str = "publication",
               stat: str = "tstat", aliases: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    if layout == "comparison":
        return build_comparison(run_data, stat, aliases)
    return build_publication(run_data, stat, aliases)
