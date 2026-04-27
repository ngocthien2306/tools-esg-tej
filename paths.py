"""Centralized data paths. Override with env var DATA_DIR for deploy."""
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
DATA_DIR = Path(os.environ.get("DATA_DIR", PROJECT_ROOT)).resolve()

UPLOADS = DATA_DIR / "uploads"
RUNS = DATA_DIR / "runs"
DB_PATH = DATA_DIR / "tool.db"

UPLOADS.mkdir(parents=True, exist_ok=True)
RUNS.mkdir(parents=True, exist_ok=True)
