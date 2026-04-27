import uuid
from typing import List, Optional
from .loader import load_dataset, UPLOADS


def merge_two(left_id: str, right_id: str,
              left_keys: List[str], right_keys: List[str],
              left_keep: Optional[List[str]] = None,
              right_keep: Optional[List[str]] = None,
              how: str = "inner",
              left_suffix: str = "",
              right_suffix: str = "_right") -> dict:
    """Merge two datasets using per-side key columns and selectable keep-columns."""
    if not left_keys or not right_keys:
        raise ValueError("Both left_keys and right_keys are required")
    if len(left_keys) != len(right_keys):
        raise ValueError("Number of left and right keys must match")

    left = load_dataset(left_id)
    right = load_dataset(right_id)

    for k in left_keys:
        if k not in left.columns:
            raise ValueError(f"Left key '{k}' not in left dataset")
    for k in right_keys:
        if k not in right.columns:
            raise ValueError(f"Right key '{k}' not in right dataset")

    # Filter to selected keep-columns + keys
    if left_keep is not None:
        left_cols = list(dict.fromkeys(left_keys + list(left_keep)))
        left_cols = [c for c in left_cols if c in left.columns]
        left = left[left_cols]
    if right_keep is not None:
        right_cols = list(dict.fromkeys(right_keys + list(right_keep)))
        right_cols = [c for c in right_cols if c in right.columns]
        right = right[right_cols]

    result = left.merge(
        right,
        left_on=left_keys, right_on=right_keys,
        how=how, suffixes=(left_suffix, right_suffix),
    )

    # Drop right key columns when their names differ from left (avoid duplicates)
    for lk, rk in zip(left_keys, right_keys):
        if lk != rk and rk in result.columns:
            result = result.drop(columns=[rk])

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


# Legacy single-key-name multi-dataset merge (kept for backward compat)
def merge_datasets(dataset_ids: List[str], on: List[str],
                   how: str = "inner") -> dict:
    if len(dataset_ids) < 2:
        raise ValueError("Need at least 2 datasets to merge")
    if not on:
        raise ValueError("Need at least one key column")

    dfs = [load_dataset(d) for d in dataset_ids]
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
