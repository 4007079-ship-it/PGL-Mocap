"""Пути к ресурсам и настройкам (работает и из исходников, и из собранного exe)."""
import os
import sys
from pathlib import Path

from . import APP_NAME


def resource_dir() -> Path:
    """Папка с ресурсами: внутри exe (PyInstaller) или корень проекта."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent.parent


def exe_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


MODEL_FILES = {
    "lite": "pose_landmarker_lite.task",
    "full": "pose_landmarker_full.task",
    "heavy": "pose_landmarker_heavy.task",
}

MODEL_URLS = {
    k: f"https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_{k}/float16/latest/{v}"
    for k, v in MODEL_FILES.items()
}


def model_search_dirs():
    return [exe_dir() / "models", resource_dir() / "models", settings_dir() / "models"]


def find_model(kind: str):
    name = MODEL_FILES[kind]
    for d in model_search_dirs():
        p = d / name
        if p.is_file():
            return p
    return None


def available_models():
    return [k for k in MODEL_FILES if find_model(k) is not None]


def settings_dir() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home() / ".config")
    d = Path(base) / APP_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def settings_file() -> Path:
    return settings_dir() / "settings.json"
