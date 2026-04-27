from pathlib import Path
import uuid
import pandas as pd

from paths import UPLOADS  # re-exported below for callers


def save_upload(file_bytes: bytes, original_name: str) -> dict:
    ext = Path(original_name).suffix.lower()
    if ext not in (".xlsx", ".xls", ".csv"):
        raise ValueError(f"Unsupported file type: {ext}")
    dataset_id = uuid.uuid4().hex[:12]
    target = UPLOADS / f"{dataset_id}{ext}"
    target.write_bytes(file_bytes)
    df = load_dataframe(target)
    return {
        "id": dataset_id,
        "filename": original_name,
        "path": str(target),
        "n_rows": len(df),
        "n_cols": len(df.columns),
        "columns": list(df.columns),
    }


def load_dataframe(path) -> pd.DataFrame:
    p = Path(path)
    if p.suffix.lower() == ".csv":
        return pd.read_csv(p)
    return pd.read_excel(p)


def dataset_path(dataset_id: str) -> Path:
    for ext in (".xlsx", ".xls", ".csv"):
        p = UPLOADS / f"{dataset_id}{ext}"
        if p.exists():
            return p
    raise FileNotFoundError(f"Dataset {dataset_id} not found")


def load_dataset(dataset_id: str) -> pd.DataFrame:
    return load_dataframe(dataset_path(dataset_id))
