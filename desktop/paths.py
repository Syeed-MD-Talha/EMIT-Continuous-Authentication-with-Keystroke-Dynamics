import os
from pathlib import Path

APP_NAME = "EMITDesktop"


def data_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    if base:
        path = Path(base) / APP_NAME
    else:
        path = Path.home() / f".{APP_NAME.lower()}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def db_path() -> Path:
    return data_dir() / "emit.db"


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]
