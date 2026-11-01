"""Проверка трекинга на одной картинке:
    python tools/track_image.py photo.jpg [lite|full|heavy] [--hands] [--face] [--require-face] [--require-hands]

Печатает, сколько людей найдено, координаты нескольких точек, а с флагами — пальцы и мимику.
Возвращает 0, если найден хотя бы один человек (и лицо/руки, если они обязательны).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cv2  # noqa: E402

from pglmocap.tracker import IDX, PoseTracker  # noqa: E402

args = [a for a in sys.argv[1:] if not a.startswith("--")]
flags = {a for a in sys.argv[1:] if a.startswith("--")}
path = args[0]
model = args[1] if len(args) > 1 else "full"
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

ok = bool(poses)
if poses and ({"--hands", "--face"} & flags):
    from pglmocap.extras import ExtrasTracker
    ex = ExtrasTracker("--hands" in flags, "--face" in flags)
    p = poses[0]
    if "--hands" in flags:
        hands = ex.hands_for(img, p)
        for side, hand in hands.items():
            if hand is None:
                print(f"  P1 рука {side}: не найдена")
            else:
                tip = hand.norm[8]
                print(f"  P1 рука {side}: 21 точка, кончик указательного x={tip[0]:.3f} y={tip[1]:.3f}")
        if "--require-hands" in flags and not any(hands.values()):
            ok = False
    if "--face" in flags:
        face = ex.face_for(img, p)
        if face is None:
            print("  P1 лицо: не найдено")
            if "--require-face" in flags:
                ok = False
        else:
            sh = face.shapes
            top = sorted(sh.items(), key=lambda kv: -kv[1])[:5]
            print(f"  P1 лицо: коэффициентов мимики {len(sh)}; самые сильные: "
                  + ", ".join(f"{k}={v:.2f}" for k, v in top))
            if face.head:
                print("  P1 голова: рыскание %.1f° тангаж %.1f° крен %.1f°" % face.head)
            if "--require-face" in flags and len(sh) < 50:
                ok = False
    ex.close()
sys.exit(0 if ok else 1)
