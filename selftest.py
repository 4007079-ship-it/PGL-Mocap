"""Самопроверка без окна: библиотеки, модель, трекинг на пустом кадре, OSC, NDI.

Запуск из исходников:  python selftest.py
Из exe:                 "PGL Mocap.exe" --selftest   (результат в pgl_mocap_selftest.txt рядом с exe)
"""
import sys
import time
import traceback


def run(out=print):
    ok = True

    def step(name, fn):
        nonlocal ok
        t = time.perf_counter()
        try:
            res = fn()
            out(f"[OK]   {name} ({time.perf_counter() - t:.2f}s) {res or ''}")
        except Exception as e:
            ok = False
            out(f"[FAIL] {name}: {type(e).__name__}: {e}")
            out(traceback.format_exc())

    def libs():
        import cv2
        import mediapipe as mp
        import numpy  # noqa
        import pythonosc  # noqa
        from mediapipe.tasks.python import vision  # noqa
        return f"mediapipe {mp.__version__}, opencv {cv2.__version__}"

    def model():
        from pglmocap.paths import available_models
        m = available_models()
        if not m:
            raise RuntimeError("модели не найдены (папка models)")
        return ", ".join(m)

    def track():
        import numpy as np
        from pglmocap.paths import available_models
        from pglmocap.tracker import PoseTracker
        m = available_models()
        if not m:
            return "пропущено — нет модели"
        tr = PoseTracker(m[0], 1, 0.5, False)
        img = np.zeros((480, 640, 3), np.uint8)
        t = time.perf_counter()
        for _ in range(5):
            poses = tr.process(img, 640)
        dt = (time.perf_counter() - t) / 5
        tr.close()
        return f"поз: {len(poses)}, {dt * 1000:.0f} мс/кадр"

    def osc():
        from pythonosc.udp_client import SimpleUDPClient
        SimpleUDPClient("127.0.0.1", 7000).send_message("/pglmocap/selftest", 1.0)
        return "отправлено на 127.0.0.1:7000"

    def ndi():
        from pglmocap.sources import list_ndi_sources
        return f"источников: {len(list_ndi_sources(1.5))}"

    def cams():
        from pglmocap.sources import list_cameras
        return "; ".join(f"{i}: {n}" for i, n in list_cameras())

    step("Библиотеки", libs)
    step("Модели", model)
    step("Трекинг", track)
    step("OSC", osc)
    step("NDI", ndi)
    step("Камеры", cams)
    out("ИТОГ: " + ("всё в порядке" if ok else "есть ошибки"))
    return ok


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
