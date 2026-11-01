"""Трекинг позы через MediaPipe Pose Landmarker (33 точки на человека)."""
import time

import cv2
import numpy as np

from .paths import MODEL_FILES, find_model

LANDMARK_NAMES = [
    "nose", "left_eye_inner", "left_eye", "left_eye_outer",
    "right_eye_inner", "right_eye", "right_eye_outer",
    "left_ear", "right_ear", "mouth_left", "mouth_right",
    "left_shoulder", "right_shoulder", "left_elbow", "right_elbow",
    "left_wrist", "right_wrist", "left_pinky", "right_pinky",
    "left_index", "right_index", "left_thumb", "right_thumb",
    "left_hip", "right_hip", "left_knee", "right_knee",
    "left_ankle", "right_ankle", "left_heel", "right_heel",
    "left_foot_index", "right_foot_index",
]
IDX = {n: i for i, n in enumerate(LANDMARK_NAMES)}

CORE_JOINTS = [
    "nose", "left_shoulder", "right_shoulder", "left_elbow", "right_elbow",
    "left_wrist", "right_wrist", "left_hip", "right_hip",
    "left_knee", "right_knee", "left_ankle", "right_ankle",
]

# Перестановка индексов левое <-> правое (нужна при зеркалировании кадра)
MIRROR_PERM = np.array([
    IDX[n.replace("left_", "#").replace("right_", "left_").replace("#", "right_")]
    for n in LANDMARK_NAMES
])

SKELETON = [
    (11, 12), (11, 13), (13, 15), (12, 14), (14, 16),
    (11, 23), (12, 24), (23, 24), (23, 25), (25, 27), (24, 26), (26, 28),
    (27, 29), (29, 31), (27, 31), (28, 30), (30, 32), (28, 32),
    (15, 17), (15, 19), (15, 21), (16, 18), (16, 20), (16, 22),
    (0, 2), (0, 5), (2, 7), (5, 8), (9, 10),
]


class Pose:
    """Одна поза: нормализованные (по кадру) и мировые (метры) координаты."""
    __slots__ = ("norm", "world", "vis")

    def __init__(self, norm, world, vis):
        self.norm = norm      # (33, 3): x, y в 0..1 по кадру, z — относительная глубина
        self.world = world    # (33, 3): метры, центр между бёдрами
        self.vis = vis        # (33,)  : видимость 0..1


class PoseTracker:
    def __init__(self, model="full", num_poses=1, min_confidence=0.5, use_gpu=False):
        from mediapipe.tasks.python import BaseOptions, vision

        path = find_model(model)
        if path is None:
            raise FileNotFoundError(
                f"Не найдена модель {MODEL_FILES[model]}. Положите её в папку models рядом с программой.")
        delegate = BaseOptions.Delegate.GPU if use_gpu else BaseOptions.Delegate.CPU
        # Читаем модель в память: так путь с кириллицей/пробелами не мешает загрузке
        model_bytes = path.read_bytes()
        opts = vision.PoseLandmarkerOptions(
            base_options=BaseOptions(model_asset_buffer=model_bytes, delegate=delegate),
            running_mode=vision.RunningMode.VIDEO,
            num_poses=int(num_poses),
            min_pose_detection_confidence=float(min_confidence),
            min_pose_presence_confidence=float(min_confidence),
            min_tracking_confidence=float(min_confidence),
            output_segmentation_masks=False,
        )
        try:
            self._lm = vision.PoseLandmarker.create_from_options(opts)
        except Exception:
            if not use_gpu:
                raise
            opts.base_options = BaseOptions(model_asset_buffer=model_bytes,
                                            delegate=BaseOptions.Delegate.CPU)
            self._lm = vision.PoseLandmarker.create_from_options(opts)
        self._t0 = time.perf_counter()
        self._last_ts = -1

    def process(self, bgr: np.ndarray, proc_width: int = 640):
        import mediapipe as mp

        h, w = bgr.shape[:2]
        if proc_width and w > proc_width:
            nh = int(round(h * proc_width / w))
            small = cv2.resize(bgr, (proc_width, nh), interpolation=cv2.INTER_AREA)
        else:
            small = bgr
        rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
        image = mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(rgb))
        ts = int((time.perf_counter() - self._t0) * 1000)
        if ts <= self._last_ts:
            ts = self._last_ts + 1
        self._last_ts = ts
        res = self._lm.detect_for_video(image, ts)

        poses = []
        for i, lms in enumerate(res.pose_landmarks or []):
            norm = np.array([[p.x, p.y, p.z] for p in lms], dtype=np.float64)
            vis = np.array([(p.visibility if p.visibility is not None else 1.0) for p in lms],
                           dtype=np.float64)
            if res.pose_world_landmarks and i < len(res.pose_world_landmarks):
                world = np.array([[p.x, p.y, p.z] for p in res.pose_world_landmarks[i]],
                                 dtype=np.float64)
            else:
                world = np.zeros_like(norm)
            poses.append(Pose(norm, world, vis))
        return poses

    def close(self):
        try:
            self._lm.close()
        except Exception:
            pass
