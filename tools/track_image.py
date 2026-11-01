"""Проверка трекинга на одной картинке: python tools/track_image.py photo.jpg [lite|full|heavy]

Печатает, сколько людей найдено, и координаты нескольких точек.
Возвращает код 0, если найден хотя бы один человек.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cv2  # noqa: E402

from pglmocap.tracker import IDX, PoseTracker  # noqa: E402

path = sys.argv[1]
model = sys.argv[2] if len(sys.argv) > 2 else "full"
img = cv2.imread(path)
if img is None:
    sys.exit(f"Не удалось открыть {path}")
tr = PoseTracker(model, 2, 0.5, False)
poses = []
for _ in range(3):  # VIDEO-режим: первые кадры — детекция, дальше трекинг
    poses = tr.process(img, 640)
tr.close()
print(f"Картинка {img.shape[1]}x{img.shape[0]}, модель {model}: людей найдено {len(poses)}")
for i, p in enumerate(poses, 1):
    for name in ("nose", "left_shoulder", "right_wrist", "left_hip", "right_ankle"):
        x, y, _ = p.norm[IDX[name]]
        print(f"  P{i} {name:<14} x={x:.3f} y={y:.3f} vis={p.vis[IDX[name]]:.2f}")
sys.exit(0 if poses else 1)
