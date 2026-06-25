import base64
import json
import os
import shutil
import uuid
from pathlib import Path

import pandas as pd

from fastapi import FastAPI, UploadFile, File, Request, HTTPException, Body
from fastapi.responses import HTMLResponse, FileResponse, Response
from starlette.concurrency import run_in_threadpool
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from paths import RUNS as DATA_RUNS

from core.config import AnalysisConfig
from core.loader import save_upload, load_dataset, dataset_path
from core.profiler import (
    profile_dataset, correlation_matrix, correlation_table, compute_vif,
    column_distribution, panel_balance, within_between_variance,
    bivariate, group_stats,
    quintile_portfolio, treated_control_trend, firm_trajectories,
    lead_lag_correlation, outlier_scores,
    density_ridgeplot, first_differences, bubble_chart, pivot_heatmap,
)
from core.merger import merge_datasets as merge_fn, merge_two as merge_two_fn
from core.pipeline import run_analysis
from core.reporter import export_excel
from core.tables import build_spec, build_correlation, build_vif
from core.exporters import (
    render_html, render_docx, render_xlsx,
    render_correlation_docx, render_correlation_html,
    render_vif_docx, render_vif_html,
)
from db import db

BASE = Path(__file__).parent
RUNS = DATA_RUNS
(BASE / "static").mkdir(exist_ok=True)

app = FastAPI(title="ESG Analysis Tool")
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")
templates = Jinja2Templates(directory=BASE / "templates")


# ── Auth (HTTP Basic, env-gated) ─────────────────────────────────────────────
APP_USER = os.environ.get("APP_USER", "admin")
APP_PASSWORD = os.environ.get("APP_PASSWORD", "")


@app.middleware("http")
async def basic_auth(request: Request, call_next):
    # No password set → run open (local dev mode)
    if not APP_PASSWORD:
        return await call_next(request)
    # Allow health checks and static assets without auth
    if request.url.path in ("/healthz",) or request.url.path.startswith("/static"):
        return await call_next(request)
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Basic "):
        try:
            decoded = base64.b64decode(auth[6:]).decode()
            user, _, pwd = decoded.partition(":")
            if user == APP_USER and pwd == APP_PASSWORD:
                return await call_next(request)
        except Exception:
            pass
    return Response(
        status_code=401,
        headers={"WWW-Authenticate": 'Basic realm="ESG Lab"'},
    )


@app.get("/healthz")
async def healthz():
    return {"ok": True}


# ── Pages ────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def page_index(request: Request):
    return templates.TemplateResponse("index.html", {
        "request": request,
        "datasets": db.list_datasets(),
        "runs": db.list_runs()[:5],
        "active": "datasets",
    })


@app.get("/datasets/{dataset_id}", response_class=HTMLResponse)
async def page_dataset(request: Request, dataset_id: str):
    ds = db.get_dataset(dataset_id)
    if not ds:
        raise HTTPException(404)
    return templates.TemplateResponse("dataset.html", {
        "request": request, "dataset": ds, "active": "datasets",
    })


@app.get("/merge", response_class=HTMLResponse)
async def page_merge(request: Request):
    return templates.TemplateResponse("merge.html", {
        "request": request, "datasets": db.list_datasets(), "active": "merge",
    })


@app.get("/train", response_class=HTMLResponse)
async def page_train(request: Request, dataset_id: str = None):
    selected = db.get_dataset(dataset_id) if dataset_id else None
    return templates.TemplateResponse("train.html", {
        "request": request,
        "datasets": db.list_datasets(),
        "selected": selected,
        "active": "train",
    })


@app.get("/runs", response_class=HTMLResponse)
async def page_runs(request: Request):
    return templates.TemplateResponse("runs.html", {
        "request": request, "runs": db.list_runs(), "active": "runs",
    })


@app.get("/runs/{run_id}", response_class=HTMLResponse)
async def page_run(request: Request, run_id: str):
    meta = db.get_run(run_id)
    if not meta:
        raise HTTPException(404)
    result_path = RUNS / run_id / "result.json"
    if not result_path.exists():
        raise HTTPException(404, "Result file missing")
    with open(result_path) as f:
        result = json.load(f)
    return templates.TemplateResponse("run.html", {
        "request": request, "meta": meta, "result": result, "active": "runs",
    })


# ── API: Datasets ────────────────────────────────────────────────────────────

@app.post("/api/datasets/upload")
async def api_upload(file: UploadFile = File(...)):
    content = await file.read()
    try:
        info = save_upload(content, file.filename)
    except ValueError as e:
        raise HTTPException(400, str(e))
    db.add_dataset(info)
    return {
        "id": info["id"],
        "filename": info["filename"],
        "n_rows": info["n_rows"],
        "n_cols": info["n_cols"],
    }


@app.get("/api/datasets/{dataset_id}/profile")
async def api_profile(dataset_id: str, entity_col: str = "COID", time_col: str = "Year"):
    df = load_dataset(dataset_id)
    return profile_dataset(df, entity_col=entity_col, time_col=time_col)


@app.get("/api/datasets/{dataset_id}/correlation")
async def api_correlation(dataset_id: str, cols: str = ""):
    df = load_dataset(dataset_id)
    col_list = [c for c in cols.split(",") if c] if cols else None
    return correlation_matrix(df, col_list)


@app.get("/api/datasets/{dataset_id}/correlation/export")
async def api_correlation_export(dataset_id: str, format: str = "docx", cols: str = "",
                                 pos: str = "#dc2626", neg: str = "#2563eb"):
    """Academic correlation table (lower-triangular, heat-shaded by value).
    format: docx | html ; pos/neg = +/- correlation colours from the chart theme."""
    fmt = format.lower()
    if fmt not in ("docx", "html"):
        raise HTTPException(400, f"Unsupported format '{format}'")
    df = load_dataset(dataset_id)
    col_list = [c for c in cols.split(",") if c] if cols else None
    data = await run_in_threadpool(correlation_table, df, col_list)
    if not data["vars"]:
        raise HTTPException(400, "No numeric columns selected")

    aliases = {}
    try:
        ds = db.get_dataset(dataset_id)
        if ds:
            aliases = ds.get("aliases") or {}
    except Exception:
        aliases = {}

    spec = build_correlation(data, aliases, pos=pos, neg=neg)
    if fmt == "html":
        return Response(content=render_correlation_html(spec),
                        media_type="text/html; charset=utf-8")
    out = RUNS / f"correlation_{dataset_id}.docx"
    render_correlation_docx(spec, out)
    return FileResponse(out, filename="correlation_matrix.docx",
                        media_type=_EXPORT_MEDIA["docx"])


@app.get("/api/datasets/{dataset_id}/vif/export")
async def api_vif_export(dataset_id: str, format: str = "docx", cols: str = ""):
    """Variance Inflation Factor table. format: docx | html"""
    fmt = format.lower()
    if fmt not in ("docx", "html"):
        raise HTTPException(400, f"Unsupported format '{format}'")
    df = load_dataset(dataset_id)
    col_list = [c for c in cols.split(",") if c] if cols else None
    data = await run_in_threadpool(compute_vif, df, col_list)
    if not data["rows"]:
        raise HTTPException(400, "No numeric columns selected")

    aliases = {}
    try:
        ds = db.get_dataset(dataset_id)
        if ds:
            aliases = ds.get("aliases") or {}
    except Exception:
        aliases = {}

    spec = build_vif(data, aliases)
    if fmt == "html":
        return Response(content=render_vif_html(spec),
                        media_type="text/html; charset=utf-8")
    out = RUNS / f"vif_{dataset_id}.docx"
    render_vif_docx(spec, out)
    return FileResponse(out, filename="vif_test.docx",
                        media_type=_EXPORT_MEDIA["docx"])


@app.get("/api/datasets/{dataset_id}/preview")
async def api_preview(dataset_id: str, n: int = 50):
    df = load_dataset(dataset_id)
    return {
        "columns": list(df.columns),
        "rows": df.head(n).fillna("").astype(str).values.tolist(),
        "n_total": len(df),
    }


@app.get("/api/datasets/{dataset_id}/distribution")
async def api_distribution(dataset_id: str, col: str, bins: int = 30):
    df = load_dataset(dataset_id)
    return column_distribution(df, col, bins)


@app.get("/api/datasets/{dataset_id}/panel")
async def api_panel(dataset_id: str, entity: str = "COID", time: str = "Year"):
    df = load_dataset(dataset_id)
    return panel_balance(df, entity, time)


@app.get("/api/datasets/{dataset_id}/variance")
async def api_variance(dataset_id: str, entity: str = "COID", cols: str = ""):
    df = load_dataset(dataset_id)
    col_list = [c for c in cols.split(",") if c] if cols else None
    if col_list is None:
        col_list = [c for c in df.columns
                    if c != entity and pd.api.types.is_numeric_dtype(df[c])]
    return within_between_variance(df, entity, col_list)


@app.get("/api/datasets/{dataset_id}/scatter")
async def api_scatter(dataset_id: str, x: str, y: str, sample: int = 2000):
    df = load_dataset(dataset_id)
    return bivariate(df, x, y, sample)


@app.get("/api/datasets/{dataset_id}/group")
async def api_group(dataset_id: str, group: str, value: str, top_n: int = 30):
    df = load_dataset(dataset_id)
    return group_stats(df, group, value, top_n)


# ── Tier 2 analyses ──────────────────────────────────────────────────────────

@app.get("/api/datasets/{dataset_id}/quintile")
async def api_quintile(dataset_id: str, x: str, y: str,
                       time: str = "Year", n_quintiles: int = 5):
    df = load_dataset(dataset_id)
    return quintile_portfolio(df, x, y, time, n_quintiles)


@app.get("/api/datasets/{dataset_id}/treated_control")
async def api_treated_control(dataset_id: str, treat: str, value: str,
                              time: str = "Year",
                              cutoff_method: str = "median_pre",
                              cutoff_value: float = None,
                              post_year: int = 2021):
    df = load_dataset(dataset_id)
    return treated_control_trend(df, treat, value, time,
                                 cutoff_method, cutoff_value, post_year)


@app.get("/api/datasets/{dataset_id}/trajectories")
async def api_trajectories(dataset_id: str, value: str,
                           entity: str = "COID", time: str = "Year",
                           n: int = 15):
    df = load_dataset(dataset_id)
    return firm_trajectories(df, entity, time, value, n_sample=n)


@app.get("/api/datasets/{dataset_id}/leadlag")
async def api_leadlag(dataset_id: str, x: str, y: str,
                      entity: str = "COID", time: str = "Year",
                      max_lag: int = 3):
    df = load_dataset(dataset_id)
    return lead_lag_correlation(df, x, y, entity, time, max_lag)


@app.get("/api/datasets/{dataset_id}/outliers")
async def api_outliers(dataset_id: str, cols: str = "",
                       entity: str = "COID", time: str = "Year",
                       threshold: float = 3.0, top_n: int = 50):
    df = load_dataset(dataset_id)
    col_list = [c for c in cols.split(",") if c] if cols else None
    if col_list is None:
        col_list = [c for c in df.columns
                    if c not in (entity, time)
                    and pd.api.types.is_numeric_dtype(df[c])]
    return outlier_scores(df, col_list, entity, time, threshold, top_n)


# ── Tier 3 ───────────────────────────────────────────────────────────────────

@app.get("/api/datasets/{dataset_id}/ridgeplot")
async def api_ridgeplot(dataset_id: str, value: str, group: str, n_bins: int = 50):
    df = load_dataset(dataset_id)
    return density_ridgeplot(df, value, group, n_bins)


@app.get("/api/datasets/{dataset_id}/first_diff")
async def api_first_diff(dataset_id: str, x: str, y: str,
                         entity: str = "COID", time: str = "Year",
                         sample: int = 2000):
    df = load_dataset(dataset_id)
    return first_differences(df, x, y, entity, time, sample)


@app.get("/api/datasets/{dataset_id}/bubble")
async def api_bubble(dataset_id: str, x: str, y: str, size: str,
                     color: str = "", sample: int = 500):
    df = load_dataset(dataset_id)
    return bubble_chart(df, x, y, size, color or None, sample)


@app.get("/api/datasets/{dataset_id}/pivot")
async def api_pivot(dataset_id: str, row: str, col: str, value: str,
                    agg: str = "mean"):
    df = load_dataset(dataset_id)
    return pivot_heatmap(df, row, col, value, agg)


# ── Aliases (column renames) ─────────────────────────────────────────────────

@app.get("/api/datasets/{dataset_id}/aliases")
async def api_get_aliases(dataset_id: str):
    return {"aliases": db.get_dataset(dataset_id)["aliases"] if db.get_dataset(dataset_id) else {}}


@app.patch("/api/datasets/{dataset_id}/aliases")
async def api_set_aliases(dataset_id: str, payload: dict = Body(...)):
    aliases = payload.get("aliases", {})
    if not isinstance(aliases, dict):
        raise HTTPException(400, "aliases must be a dict")
    db.update_aliases(dataset_id, aliases)
    return {"ok": True}


@app.delete("/api/datasets/{dataset_id}")
async def api_delete_dataset(dataset_id: str):
    try:
        p = dataset_path(dataset_id)
        p.unlink(missing_ok=True)
    except FileNotFoundError:
        pass
    db.delete_dataset(dataset_id)
    return {"ok": True}


@app.post("/api/datasets/merge")
async def api_merge(payload: dict = Body(...)):
    """Two-dataset merge with per-side keys + keep-columns + strategy."""
    left_id = payload.get("left_id")
    right_id = payload.get("right_id")
    left_keys = payload.get("left_keys", [])
    right_keys = payload.get("right_keys", [])
    left_keep = payload.get("left_keep")  # null/None means keep all
    right_keep = payload.get("right_keep")
    how = payload.get("how", "inner")
    if not left_id or not right_id or not left_keys or not right_keys:
        raise HTTPException(400, "Missing left_id/right_id/left_keys/right_keys")
    try:
        info = merge_two_fn(left_id, right_id, left_keys, right_keys,
                            left_keep=left_keep, right_keep=right_keep, how=how)
    except Exception as e:
        raise HTTPException(400, str(e))
    db.add_dataset(info, source="merge")
    return info


# ── API: Runs ────────────────────────────────────────────────────────────────

@app.post("/api/runs")
async def api_create_run(cfg: AnalysisConfig):
    # run_analysis is CPU-bound (pandas + PanelOLS fits). Run it in a threadpool
    # so it never blocks the event loop — otherwise the server freezes for the
    # whole computation and reverse proxies/tunnels (pinggy, ngrok) hang.
    try:
        result = await run_in_threadpool(run_analysis, cfg)
    except Exception as e:
        raise HTTPException(400, f"{type(e).__name__}: {e}")

    run_id = uuid.uuid4().hex[:12]
    run_dir = RUNS / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    with open(run_dir / "result.json", "w") as f:
        json.dump(result, f, default=str)

    db.add_run(run_id, cfg.dataset_id, cfg.target,
               result["config"], result["summary"], cfg.note)
    return {"run_id": run_id, "summary": result["summary"]}


_EXPORT_MEDIA = {
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "html": "text/html; charset=utf-8",
}


@app.get("/api/runs/{run_id}/export")
async def api_export(run_id: str, format: str = "xlsx",
                     layout: str = "publication", stat: str = "tstat"):
    """Export a run's tables.

    format: xlsx | docx | html
    layout: publication | comparison | raw   (raw = full data workbook, xlsx only)
    stat:   tstat | se | pvalue              (value shown in parentheses)
    """
    result_path = RUNS / run_id / "result.json"
    if not result_path.exists():
        raise HTTPException(404)
    with open(result_path) as f:
        result = json.load(f)

    fmt = format.lower()
    if fmt not in _EXPORT_MEDIA:
        raise HTTPException(400, f"Unsupported format '{format}'")

    # Raw multi-sheet workbook keeps the legacy detailed exporter (xlsx only).
    if layout == "raw":
        out = RUNS / run_id / f"report_{run_id}.xlsx"
        export_excel(result, out)
        return FileResponse(out, filename=f"{result['config']['target']}_raw.xlsx",
                            media_type=_EXPORT_MEDIA["xlsx"])

    # Pretty variable labels from the dataset's saved aliases, if any.
    aliases = {}
    try:
        ds = db.get_dataset(result["config"]["dataset_id"])
        if ds:
            aliases = ds.get("aliases") or {}
    except Exception:
        aliases = {}

    spec = build_spec(result, layout=layout, stat=stat, aliases=aliases)
    target = result["config"]["target"]
    safe = "".join(c if c.isalnum() or c in " -_" else "_" for c in target).strip() or "table"
    fname = f"{safe}_{layout}.{fmt}"

    if fmt == "html":
        return Response(content=render_html(spec), media_type=_EXPORT_MEDIA["html"],
                        headers={"Content-Disposition": f'inline; filename="{fname}"'})

    out = RUNS / run_id / fname
    if fmt == "xlsx":
        render_xlsx(spec, out)
    else:
        render_docx(spec, out)
    return FileResponse(out, filename=fname, media_type=_EXPORT_MEDIA[fmt])


@app.delete("/api/runs/{run_id}")
async def api_delete_run(run_id: str):
    run_dir = RUNS / run_id
    if run_dir.exists():
        shutil.rmtree(run_dir)
    db.delete_run(run_id)
    return {"ok": True}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="127.0.0.1", port=8765, reload=True)
