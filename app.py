import json
import shutil
import uuid
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, Request, HTTPException, Body
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from core.config import AnalysisConfig
from core.loader import save_upload, load_dataset, dataset_path
from core.profiler import profile_dataset, correlation_matrix
from core.merger import merge_datasets as merge_fn
from core.pipeline import run_analysis
from core.reporter import export_excel
from db import db

BASE = Path(__file__).parent
RUNS = BASE / "runs"
RUNS.mkdir(exist_ok=True)
(BASE / "static").mkdir(exist_ok=True)

app = FastAPI(title="ESG Analysis Tool")
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")
templates = Jinja2Templates(directory=BASE / "templates")


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


@app.get("/api/datasets/{dataset_id}/preview")
async def api_preview(dataset_id: str, n: int = 50):
    df = load_dataset(dataset_id)
    return {
        "columns": list(df.columns),
        "rows": df.head(n).fillna("").astype(str).values.tolist(),
        "n_total": len(df),
    }


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
    dataset_ids = payload.get("dataset_ids", [])
    on = payload.get("on", [])
    how = payload.get("how", "inner")
    if not dataset_ids or not on:
        raise HTTPException(400, "Missing dataset_ids or on")
    try:
        info = merge_fn(dataset_ids, on, how)
    except Exception as e:
        raise HTTPException(400, str(e))
    db.add_dataset(info, source="merge")
    return info


# ── API: Runs ────────────────────────────────────────────────────────────────

@app.post("/api/runs")
async def api_create_run(cfg: AnalysisConfig):
    try:
        result = run_analysis(cfg)
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


@app.get("/api/runs/{run_id}/export")
async def api_export(run_id: str):
    result_path = RUNS / run_id / "result.json"
    if not result_path.exists():
        raise HTTPException(404)
    with open(result_path) as f:
        result = json.load(f)
    out = RUNS / run_id / f"report_{run_id}.xlsx"
    export_excel(result, out)
    return FileResponse(out, filename=out.name)


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
