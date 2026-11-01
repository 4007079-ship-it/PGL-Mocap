"""Источники видео: камера / карта захвата (OpenCV), NDI (cyndilib), видеофайл.

Каждый источник читает кадры в своём потоке и хранит только последний кадр,
чтобы трекинг всегда работал по свежему изображению без накопления задержки.
"""
import sys
import threading
import time

import cv2
import numpy as np

IS_WIN = sys.platform.startswith("win")


# ---------------------------------------------------------------- перечисление устройств

def list_cameras(max_probe: int = 8):
    """Список (индекс, название) камер и карт захвата."""
    if IS_WIN:
        try:
            from pygrabber.dshow_graph import FilterGraph
            names = FilterGraph().get_input_devices()
            return list(enumerate(names))
        except Exception:
            pass
    found = []
    try:  # не засорять лог предупреждениями OpenCV при переборе индексов
        cv2.utils.logging.setLogLevel(cv2.utils.logging.LOG_LEVEL_SILENT)
    except Exception:
        pass
    for i in range(max_probe):
        cap = cv2.VideoCapture(i)
        ok = cap.isOpened()
        cap.release()
        if ok:
            found.append((i, f"Камера {i}"))
    try:
        cv2.utils.logging.setLogLevel(cv2.utils.logging.LOG_LEVEL_WARNING)
    except Exception:
        pass
    if not found:
        found = [(0, "Камера 0")]
    return found


def ndi_available():
    try:
        import cyndilib  # noqa: F401
        return True, ""
    except Exception as e:  # библиотека или NDI runtime недоступны
        return False, str(e)


def list_ndi_sources(timeout: float = 2.0):
    from cyndilib.finder import Finder
    finder = Finder()
    finder.open()
    try:
        finder.wait_for_sources(timeout)
        time.sleep(0.2)
        finder.update_sources()
        return sorted(finder.get_source_names())
    finally:
        finder.close()


# ---------------------------------------------------------------- базовый класс

class FrameSource:
    """Поток, который держит последний кадр (BGR, uint8)."""

    name = "source"

    def __init__(self):
        self._lock = threading.Condition()
        self._frame = None
        self._seq = 0
        self._stop = threading.Event()
        self._thread = None
        self.error = None
        self.info = ""

    def start(self):
        self._thread = threading.Thread(target=self._run_safe, name=self.name, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)

    def _publish(self, frame):
        with self._lock:
            self._frame = frame
            self._seq += 1
            self._lock.notify_all()

    def wait_frame(self, last_seq: int, timeout: float = 0.5):
        """Вернуть (кадр, номер) новее last_seq или (None, last_seq) по таймауту."""
        with self._lock:
            if self._seq == last_seq:
                self._lock.wait(timeout)
            if self._seq == last_seq or self._frame is None:
                return None, last_seq
            return self._frame, self._seq

    def _run_safe(self):
        try:
            self._run()
        except Exception as e:
            self.error = f"{type(e).__name__}: {e}"
            with self._lock:
                self._lock.notify_all()

    def _run(self):
        raise NotImplementedError


# ---------------------------------------------------------------- камера / карта захвата

class CameraSource(FrameSource):
    name = "camera"

    def __init__(self, index=0, backend="dshow", resolution="1280x720", fps=30, mjpg=True):
        super().__init__()
        self.index = int(index)
        self.backend = backend
        self.resolution = resolution
        self.fps = fps
        self.mjpg = mjpg

    def _api(self):
        if not IS_WIN:
            return cv2.CAP_ANY
        return {"dshow": cv2.CAP_DSHOW, "msmf": cv2.CAP_MSMF}.get(self.backend, cv2.CAP_ANY)

    def _run(self):
        cap = cv2.VideoCapture(self.index, self._api())
        if not cap.isOpened():
            raise RuntimeError(f"Не удалось открыть устройство #{self.index}. "
                               "Проверьте, не занято ли оно другой программой, или смените бэкенд.")
        try:
            if self.mjpg:
                cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
            if self.resolution and self.resolution != "auto":
                w, h = (int(v) for v in self.resolution.lower().split("x"))
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, w)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)
            if self.fps:
                cap.set(cv2.CAP_PROP_FPS, float(self.fps))
            try:
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            except Exception:
                pass
            w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            self.info = f"{w}x{h} @ {cap.get(cv2.CAP_PROP_FPS):.0f}"
            fails = 0
            while not self._stop.is_set():
                ok, frame = cap.read()
                if not ok or frame is None:
                    fails += 1
                    if fails > 100:
                        raise RuntimeError("Устройство перестало отдавать кадры.")
                    time.sleep(0.01)
                    continue
                fails = 0
                self._publish(frame)
        finally:
            cap.release()


# ---------------------------------------------------------------- NDI

class NDISource(FrameSource):
    name = "ndi"

    def __init__(self, source_name: str):
        super().__init__()
        self.source_name = source_name

    def _run(self):
        from cyndilib.finder import Finder
        from cyndilib.receiver import Receiver
        from cyndilib.video_frame import VideoFrameSync
        from cyndilib.wrapper.ndi_recv import RecvBandwidth, RecvColorFormat

        finder = Finder()
        finder.open()
        receiver = None
        try:
            src = None
            t0 = time.time()
            while src is None and not self._stop.is_set():
                finder.wait_for_sources(1.0)
                finder.update_sources()
                if self.source_name in finder.get_source_names():
                    src = finder.get_source(self.source_name)
                elif time.time() - t0 > 10:
                    raise RuntimeError(f"NDI-источник «{self.source_name}» не найден в сети.")
            if src is None:
                return
            receiver = Receiver(
                color_format=RecvColorFormat.BGRX_BGRA,
                bandwidth=RecvBandwidth.highest,
                recv_name="PGL Mocap",
            )
            vf = VideoFrameSync()
            receiver.frame_sync.set_video_frame(vf)
            receiver.set_source(src)
            last_ts = None
            while not self._stop.is_set():
                if not receiver.is_connected():
                    time.sleep(0.05)
                    continue
                receiver.frame_sync.capture_video()
                xres, yres = vf.xres, vf.yres
                if not xres or not yres:
                    time.sleep(0.01)
                    continue
                ts = vf.get_timestamp_posix()
                if ts == last_ts:
                    time.sleep(0.004)
                    continue
                last_ts = ts
                stride = vf.get_line_stride() or xres * 4
                arr = vf.get_array()
                if arr.size < stride * yres:
                    continue
                img = arr[: stride * yres].reshape(yres, stride // 4, 4)[:, :xres, :3]
                self.info = f"{xres}x{yres} @ {float(vf.get_frame_rate() or 0):.2f}"
                self._publish(np.ascontiguousarray(img))
        finally:
            if receiver is not None:
                try:
                    receiver.disconnect()
                except Exception:
                    pass
            finder.close()


# ---------------------------------------------------------------- видеофайл

class FileSource(FrameSource):
    name = "file"

    def __init__(self, path: str, loop=True):
        super().__init__()
        self.path = path
        self.loop = loop

    def _run(self):
        cap = cv2.VideoCapture(self.path)
        if not cap.isOpened():
            raise RuntimeError(f"Не удалось открыть файл: {self.path}")
        try:
            fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
            if fps <= 1 or fps > 240:
                fps = 30.0
            period = 1.0 / fps
            self.info = f"{int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))}x{int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))} @ {fps:.2f}"
            nxt = time.perf_counter()
            while not self._stop.is_set():
                ok, frame = cap.read()
                if not ok:
                    if self.loop:
                        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                        continue
                    break
                self._publish(frame)
                nxt += period
                delay = nxt - time.perf_counter()
                if delay > 0:
                    time.sleep(delay)
                else:
                    nxt = time.perf_counter()
        finally:
            cap.release()


def make_source(s: dict) -> FrameSource:
    t = s["source_type"]
    if t == "camera":
        return CameraSource(s["camera_index"], s["camera_backend"], s["camera_resolution"],
                            s["camera_fps"], s["camera_mjpg"])
    if t == "ndi":
        if not s["ndi_source"]:
            raise ValueError("Не выбран NDI-источник.")
        return NDISource(s["ndi_source"])
    if t == "file":
        if not s["file_path"]:
            raise ValueError("Не выбран видеофайл.")
        return FileSource(s["file_path"], s["file_loop"])
    raise ValueError(f"Неизвестный тип источника: {t}")
