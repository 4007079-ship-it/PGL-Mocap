"""Пальцы рук и мимика лица (MediaPipe Hand Landmarker и Face Landmarker).

Работают поверх уже найденной позы: для каждой руки и лица вырезается область из
полноразмерного кадра (по запястью и голове из позы), и модель запускается на этой вырезке.
Так пальцы и лицо находятся даже на общем плане, где они занимают мало пикселей,
и левая/правая рука всегда сопоставлены с конкретным человеком.
"""
import math

import cv2
import numpy as np

from .paths import find_extra_model
from .tracker import IDX

HAND_POINTS = [
    "wrist", "thumb_cmc", "thumb_mcp", "thumb_ip", "thumb_tip",
    "index_mcp", "index_pip", "index_dip", "index_tip",
    "middle_mcp", "middle_pip", "middle_dip", "middle_tip",
    "ring_mcp", "ring_pip", "ring_dip", "ring_tip",
    "pinky_mcp", "pinky_pip", "pinky_dip", "pinky_tip",
]
HAND_SKELETON = [
    (0, 1), (1, 2), (2, 3), (3, 4), (0, 5), (5, 6), (6, 7), (7, 8),
    (5, 9), (9, 10), (10, 11), (11, 12), (9, 13), (13, 14), (14, 15), (15, 16),
    (13, 17), (0, 17), (17, 18), (18, 19), (19, 20),
]
SIDES = ("l", "r")
# точки позы, по которым ищется кисть: (запястье, локоть, указательный, мизинец)
_HAND_POSE = {
    "l": ("left_wrist", "left_elbow", "left_index", "left_pinky"),
    "r": ("right_wrist", "right_elbow", "right_index", "right_pinky"),
}
PROC_SIZE = 256   # до какого размера масштабируется вырезка перед моделью


class Hand:
    __slots__ = ("norm", "world")

    def __init__(self, norm, world):
        self.norm = norm      # (21, 3): x, y — доли полного кадра; z — глубина относительно запястья
        self.world = world    # (21, 3): метры в системе MediaPipe world позы (запястье совмещено с запястьем позы)


class Face:
    __slots__ = ("shapes", "head")

    def __init__(self, shapes, head):
        self.shapes = shapes  # dict: имя ARKit-коэффициента (eyeBlinkLeft, jawOpen, ...) -> 0..1
        self.head = head      # (yaw, pitch, roll) в градусах или None


def _crop_box(cx, cy, size, w, h):
    half = size / 2
    x0, y0 = int(round(cx - half)), int(round(cy - half))
    x1, y1 = int(round(cx + half)), int(round(cy + half))
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(w, x1), min(h, y1)
    if x1 - x0 < 16 or y1 - y0 < 16:
        return None
    return x0, y0, x1, y1


def _to_mp_image(bgr_crop):
    import mediapipe as mp
    side = max(bgr_crop.shape[:2])
    scale = PROC_SIZE / side
    if abs(scale - 1) > 0.05:
        interp = cv2.INTER_LINEAR if scale > 1 else cv2.INTER_AREA
        bgr_crop = cv2.resize(bgr_crop, (max(1, int(bgr_crop.shape[1] * scale)),
                                         max(1, int(bgr_crop.shape[0] * scale))), interpolation=interp)
    rgb = cv2.cvtColor(bgr_crop, cv2.COLOR_BGR2RGB)
    return mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(rgb))


def _euler_from_matrix(m):
    """Повороты головы (рыскание, тангаж, крен) в градусах из матрицы 4x4 MediaPipe."""
    r = np.asarray(m, dtype=np.float64)[:3, :3]
    sy = math.hypot(r[0, 0], r[1, 0])
    if sy > 1e-6:
        pitch = math.atan2(r[2, 1], r[2, 2])
        yaw = math.atan2(-r[2, 0], sy)
        roll = math.atan2(r[1, 0], r[0, 0])
    else:
        pitch = math.atan2(-r[1, 2], r[1, 1])
        yaw = math.atan2(-r[2, 0], sy)
        roll = 0.0
    return math.degrees(yaw), math.degrees(pitch), math.degrees(roll)


class ExtrasTracker:
    def __init__(self, hands: bool, face: bool, use_gpu=False):
        from mediapipe.tasks.python import BaseOptions, vision
        self.hands_on = hands
        self.face_on = face
        self._hand = self._face = None
        delegate = BaseOptions.Delegate.GPU if use_gpu else BaseOptions.Delegate.CPU

        def base(path):
            return BaseOptions(model_asset_buffer=path.read_bytes(), delegate=delegate)

        if hands:
            p = find_extra_model("hand")
            if p is None:
                raise FileNotFoundError("Не найдена модель hand_landmarker.task (папка models).")
            self._hand = vision.HandLandmarker.create_from_options(vision.HandLandmarkerOptions(
                base_options=base(p), running_mode=vision.RunningMode.IMAGE, num_hands=1,
                min_hand_detection_confidence=0.3, min_hand_presence_confidence=0.3))
        if face:
            p = find_extra_model("face")
            if p is None:
                raise FileNotFoundError("Не найдена модель face_landmarker.task (папка models).")
            self._face = vision.FaceLandmarker.create_from_options(vision.FaceLandmarkerOptions(
                base_options=base(p), running_mode=vision.RunningMode.IMAGE, num_faces=1,
                min_face_detection_confidence=0.3, min_face_presence_confidence=0.3,
                output_face_blendshapes=True, output_facial_transformation_matrixes=True))

    # ------------------------------------------------------------------ руки
    def hands_for(self, frame, pose):
        """-> {"l": Hand|None, "r": Hand|None}"""
        out = {"l": None, "r": None}
        if self._hand is None:
            return out
        h, w = frame.shape[:2]
        for side in SIDES:
            wr, el, ix, pk = (IDX[n] for n in _HAND_POSE[side])
            if pose.vis[wr] < 0.3:
                continue
            P = lambda i: np.array([pose.norm[i, 0] * w, pose.norm[i, 1] * h])  # noqa: E731
            wrist, elbow = P(wr), P(el)
            tip = (P(ix) + P(pk)) / 2
            forearm = np.linalg.norm(wrist - elbow)
            center = wrist + (tip - wrist) * 0.6
            size = max(forearm * 1.3, np.linalg.norm(tip - wrist) * 4.0, 48)
            box = _crop_box(center[0], center[1], size, w, h)
            if box is None:
                continue
            x0, y0, x1, y1 = box
            res = self._hand.detect(_to_mp_image(frame[y0:y1, x0:x1]))
            if not res.hand_landmarks:
                continue
            lms = res.hand_landmarks[0]
            cw, ch = x1 - x0, y1 - y0
            norm = np.array([[(x0 + p.x * cw) / w, (y0 + p.y * ch) / h, p.z] for p in lms], dtype=np.float64)
            # кисть должна оказаться у своего запястья — иначе это чужая/ложная рука
            if np.hypot((norm[0, 0] - pose.norm[wr, 0]) * w, (norm[0, 1] - pose.norm[wr, 1]) * h) > size * 0.5:
                continue
            hw = np.array([[p.x, p.y, p.z] for p in res.hand_world_landmarks[0]], dtype=np.float64)
            world = pose.world[wr] + (hw - hw[0])        # запястье руки = запястье позы
            norm[:, 2] = norm[:, 2] + pose.norm[wr, 2]   # глубина относительно запястья позы
            out[side] = Hand(norm, world)
        return out

    # ------------------------------------------------------------------ лицо
    def face_for(self, frame, pose, mirror=False):
        if self._face is None:
            return None
        h, w = frame.shape[:2]
        nose, le, re = IDX["nose"], IDX["left_ear"], IDX["right_ear"]
        if pose.vis[nose] < 0.3:
            return None
        P = lambda i: np.array([pose.norm[i, 0] * w, pose.norm[i, 1] * h])  # noqa: E731
        ear_d = np.linalg.norm(P(le) - P(re))
        sh_d = np.linalg.norm(P(IDX["left_shoulder"]) - P(IDX["right_shoulder"]))
        size = max(ear_d * 2.6, sh_d * 0.9, 48)
        c = P(nose)
        box = _crop_box(c[0], c[1], size, w, h)
        if box is None:
            return None
        x0, y0, x1, y1 = box
        res = self._face.detect(_to_mp_image(frame[y0:y1, x0:x1]))
        if not res.face_blendshapes:
            return None
        shapes = {}
        for cat in res.face_blendshapes[0]:
            name = cat.category_name or ""
            if not name or name.startswith("_"):
                continue
            if mirror:   # кадр отражён — левая/правая сторона лица меняются местами
                name = name.replace("Left", "#").replace("Right", "Left").replace("#", "Right")
            shapes[name] = float(cat.score)
        head = None
        if res.facial_transformation_matrixes:
            yaw, pitch, roll = _euler_from_matrix(res.facial_transformation_matrixes[0])
            head = (-yaw, pitch, -roll) if mirror else (yaw, pitch, roll)
        return Face(shapes, head)

    def close(self):
        for t in (self._hand, self._face):
            if t is not None:
                try:
                    t.close()
                except Exception:
                    pass
