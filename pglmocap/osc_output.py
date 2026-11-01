"""Перевод позы в координаты сцены и отправка по OSC.

Адреса (префикс по умолчанию /pglmocap, N — номер человека с 1):
  /pglmocap/count                    кол-во людей в кадре          (float)
  /pglmocap/pN/detected              1 — человек есть, 0 — потерян (float)
  /pglmocap/pN/<сустав>              x y z                         (3 float) -> OSC Vector в Aximmetry
  /pglmocap/pN/<сустав>/vis          видимость 0..1 (если включено)
  /pglmocap/pN/hip_center            середина между бёдрами
  /pglmocap/pN/shoulder_center       середина между плечами
  /pglmocap/pN/screen_pos            центр бёдер в координатах кадра (всегда, в любом режиме)
  /pglmocap/pN/all                   все точки одним сообщением (если включено)

Пальцы (если включены), сторона l / r — левая / правая рука самого человека:
  /pglmocap/pN/hand_l/detected       1 / 0
  /pglmocap/pN/hand_l/<точка>        x y z  (wrist, thumb_tip, index_tip, ... — 21 точка)
Мимика (если включена):
  /pglmocap/pN/face/detected         1 / 0
  /pglmocap/pN/face/<коэффициент>    0..1   (eyeBlinkLeft, jawOpen, mouthSmileLeft, ... — 51 шт., ARKit)
  /pglmocap/pN/face/head             рыскание тангаж крен, градусы
"""
import numpy as np
from pythonosc.udp_client import SimpleUDPClient

from .extras import HAND_POINTS, SIDES
from .tracker import CORE_JOINTS, IDX, LANDMARK_NAMES


def _screen_coords(norm: np.ndarray, aspect: float) -> np.ndarray:
    """Кадр -> координаты, где высота кадра = 1, центр кадра = 0, Y вверх, Z к камере."""
    out = np.empty_like(norm)
    out[:, 0] = (norm[:, 0] - 0.5) * aspect
    out[:, 1] = 0.5 - norm[:, 1]
    out[:, 2] = -norm[:, 2] * aspect
    return out


def _world_coords(world: np.ndarray) -> np.ndarray:
    """MediaPipe world (Y вниз) -> метры, Y вверх, Z к камере."""
    out = world.copy()
    out[:, 1] = -world[:, 1]
    out[:, 2] = -world[:, 2]
    return out


def transform(pts: np.ndarray, s: dict) -> np.ndarray:
    p = pts * float(s["scale"])
    if s["flip_x"]:
        p[:, 0] = -p[:, 0]
    if s["up_axis"] == "z":
        # Z вверх: X вправо, Y вглубь сцены (от камеры), Z вверх
        p = np.stack([p[:, 0], -p[:, 2], p[:, 1]], axis=1)
    p = p + np.array([s["offset_x"], s["offset_y"], s["offset_z"]], dtype=np.float64)
    return p


class OscOutput:
    def __init__(self):
        self._client = None
        self._addr = None
        self.sent = 0

    def _ensure(self, ip, port):
        if self._addr != (ip, port):
            self._client = SimpleUDPClient(ip, int(port))
            self._addr = (ip, port)

    def send_frame(self, poses, aspect: float, s: dict, max_slots: int):
        """poses: список Pose или None на позицию (None = не найден)."""
        if not s.get("osc_enabled", True):
            return 0
        self._ensure(s["osc_ip"], s["osc_port"])
        c = self._client
        pre = s["osc_prefix"].rstrip("/") or ""
        names = LANDMARK_NAMES if s["joint_set"] == "all" else CORE_JOINTS
        n = 0
        c.send_message(f"{pre}/count", float(sum(1 for p in poses if p is not None)))
        n += 1
        for slot in range(max_slots):
            base = f"{pre}/p{slot + 1}"
            pose = poses[slot] if slot < len(poses) else None
            if pose is None:
                c.send_message(f"{base}/detected", 0.0)
                n += 1
                continue
            c.send_message(f"{base}/detected", 1.0)
            screen = _screen_coords(pose.norm, aspect)
            raw = screen if s["coord_mode"] == "screen" else _world_coords(pose.world)
            pts = transform(raw, s)
            for name in names:
                i = IDX[name]
                c.send_message(f"{base}/{name}", [float(v) for v in pts[i]])
                n += 1
                if s["send_visibility"]:
                    c.send_message(f"{base}/{name}/vis", float(pose.vis[i]))
                    n += 1
            hip = (pts[IDX["left_hip"]] + pts[IDX["right_hip"]]) / 2
            sh = (pts[IDX["left_shoulder"]] + pts[IDX["right_shoulder"]]) / 2
            c.send_message(f"{base}/hip_center", [float(v) for v in hip])
            c.send_message(f"{base}/shoulder_center", [float(v) for v in sh])
            scr = transform(screen, s)
            sp = (scr[IDX["left_hip"]] + scr[IDX["right_hip"]]) / 2
            c.send_message(f"{base}/screen_pos", [float(v) for v in sp])
            n += 3
            if s.get("track_hands"):
                for side in SIDES:
                    hand = (pose.hands or {}).get(side)
                    hb = f"{base}/hand_{side}"
                    c.send_message(f"{hb}/detected", 1.0 if hand is not None else 0.0)
                    n += 1
                    if hand is None:
                        continue
                    hraw = _screen_coords(hand.norm, aspect) if s["coord_mode"] == "screen" else _world_coords(hand.world)
                    hp = transform(hraw, s)
                    for k, name in enumerate(HAND_POINTS):
                        c.send_message(f"{hb}/{name}", [float(v) for v in hp[k]])
                    n += len(HAND_POINTS)
            if s.get("track_face"):
                face = pose.face
                c.send_message(f"{base}/face/detected", 1.0 if face is not None else 0.0)
                n += 1
                if face is not None:
                    for name, val in face.shapes.items():
                        c.send_message(f"{base}/face/{name}", float(val))
                    n += len(face.shapes)
                    if face.head is not None:
                        c.send_message(f"{base}/face/head", [float(v) for v in face.head])
                        n += 1
            if s["send_all_vector"]:
                c.send_message(f"{base}/all", [float(v) for v in pts[[IDX[x] for x in names]].ravel()])
                n += 1
        self.sent += n
        return n
