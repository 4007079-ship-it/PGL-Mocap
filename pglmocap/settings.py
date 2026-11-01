"""Настройки приложения: значения по умолчанию, загрузка и сохранение в JSON."""
import json

from .paths import settings_file

DEFAULTS = {
    # Источник
    "source_type": "camera",        # camera | ndi | file
    "camera_index": 0,
    "camera_backend": "dshow",      # dshow | msmf | any
    "camera_resolution": "1280x720",  # "auto" или "ШxВ"
    "camera_fps": 30,
    "camera_mjpg": True,
    "ndi_source": "",
    "file_path": "",
    "file_loop": True,
    # Обработка
    "model": "full",                # lite | full | heavy
    "num_poses": 1,
    "mirror": False,
    "rotation": 0,                  # 0 | 90 | 180 | 270
    "proc_width": 640,
    "min_confidence": 0.5,
    "smoothing": 0.5,               # 0 = без сглаживания, 1 = максимум
    "hold_seconds": 0.3,
    "use_gpu": False,
    # OSC
    "osc_ip": "127.0.0.1",
    "osc_port": 7000,
    "osc_prefix": "/pglmocap",
    "coord_mode": "screen",         # screen | world
    "up_axis": "y",                 # y | z
    "scale": 1.0,
    "flip_x": False,
    "offset_x": 0.0,
    "offset_y": 0.0,
    "offset_z": 0.0,
    "joint_set": "all",             # all | core
    "send_visibility": False,
    "send_all_vector": False,
    "osc_enabled": True,
}


def load_settings() -> dict:
    s = dict(DEFAULTS)
    try:
        with open(settings_file(), "r", encoding="utf-8") as f:
            data = json.load(f)
        for k, v in data.items():
            if k in s:
                s[k] = v
    except Exception:
        pass
    return s


def save_settings(s: dict) -> None:
    try:
        with open(settings_file(), "w", encoding="utf-8") as f:
            json.dump(s, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
