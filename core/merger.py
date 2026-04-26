import uuid
from typing import List
from .loader import load_dataset, UPLOADS


def merge_datasets(dataset_ids: List[str], on: List[str], how: str = "inner") -> dict:
    if len(dataset_ids) < 2:
        raise ValueError("Need at least 2 datasets to merge")
    if not on:
        raise ValueError("Need at least one key column")

    dfs = [load_dataset(did) for did in dataset_ids]
    result = dfs[0]
    for i, df in enumerate(dfs[1:], 1):
        result = result.merge(df, on=on, how=how, suffixes=("", f"_{i}"))

    new_id = uuid.uuid4().hex[:12]
    out_path = UPLOADS / f"{new_id}.xlsx"
    result.to_excel(out_path, index=False)

    return {
        "id": new_id,
        "filename": f"merged_{new_id[:6]}.xlsx",
        "path": str(out_path),
        "n_rows": len(result),
        "n_cols": len(result.columns),
        "columns": list(result.columns),
    }
