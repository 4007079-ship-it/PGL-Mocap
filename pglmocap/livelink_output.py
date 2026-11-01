"""Вывод в Unreal Engine Live Link (через плагин PGLMocapLiveLink).

Каждый кадр уходит одним UDP-пакетом JSON. Координаты — сразу в системе Unreal:
сантиметры, X — вперёд (к камере, куда смотрит человек), Y — вправо (правая рука человека), Z — вверх.
Пол (самая низкая точка стоп) — Z = 0.

Пакет:
{
  "v": 1,
  "prefix": "PGL",
  "persons": [
    {
      "id": 1,
      "root":   [x, y, z],                       положение человека на площадке (перемещение по кадру)
      "points": {"nose": [x, y, z], ...},        точки относительно root
      "names":  ["root", "pelvis", ...],         кости скелета
      "parents":[-1, 0, ...],
      "bones":  [[tx,ty,tz, qx,qy,qz,qw], ...]   локальные трансформы костей (относительно родителя)
    }
  ],
  "lost": [2]                                    номера людей, которые пропали из кадра
}

Соглашение для костей: ось X кости направлена вдоль кости к следующему суставу,
ось Z — ось сгиба (для рук/ног) или «вправо» (для корпуса, шеи, головы, стоп).
В «нулевой» позе (все повороты единичные) все кости смотрят вдоль +X.
"""
import json
import socket

import numpy as np

from .tracker import CORE_JOINTS, IDX, LANDMARK_NAMES

# ------------------------------------------------------------------ скелет
BONES = [
    # имя,          родитель,     сустав-начало,   сустав-конец (куда смотрит X)
    ("root",        -1),
    ("pelvis",       0),
    ("spine_01",     1),
    ("neck_01",      2),
    ("head",         3),
    ("upperarm_l",   2),
    ("lowerarm_l",   5),
    ("hand_l",       6),
    ("upperarm_r",   2),
    ("lowerarm_r",   8),
    ("hand_r",       9),
    ("thigh_l",      1),
    ("calf_l",      11),
    ("foot_l",      12),
    ("thigh_r",      1),
    ("calf_r",      14),
    ("foot_r",      15),
]
BONE_NAMES = [b[0] for b in BONES]
BONE_PARENTS = [b[1] for b in BONES]

# точки, по которым считается «пол»
FLOOR_POINTS = [IDX[n] for n in ("left_ankle", "right_ankle", "left_heel", "right_heel",
                                 "left_foot_index", "right_foot_index")]


def _norm(v):
    n = np.linalg.norm(v)
    return v / n if n > 1e-9 else None


def _basis(x_dir, z_hint, fallback_hint):
    """Ортонормированный базис (столбцы X, Y, Z) с X вдоль x_dir и Z как можно ближе к z_hint."""
    x = _norm(x_dir)
    if x is None:
        return np.eye(3)
    for hint in (z_hint, fallback_hint, np.array([0.0, 0.0, 1.0]), np.array([0.0, 1.0, 0.0])):
        if hint is None:
            continue
        z = hint - np.dot(hint, x) * x
        z = _norm(z)
        if z is not None:
            break
    y = np.cross(z, x)
    return np.stack([x, y, z], axis=1)


def mat_to_quat(m):
    """Матрица поворота 3x3 (v' = M v) -> кватернион (x, y, z, w)."""
    t = np.trace(m)
    if t > 0:
        s = np.sqrt(t + 1.0) * 2
        w = 0.25 * s
        x = (m[2, 1] - m[1, 2]) / s
        y = (m[0, 2] - m[2, 0]) / s
        z = (m[1, 0] - m[0, 1]) / s
    elif m[0, 0] > m[1, 1] and m[0, 0] > m[2, 2]:
        s = np.sqrt(1.0 + m[0, 0] - m[1, 1] - m[2, 2]) * 2
        w = (m[2, 1] - m[1, 2]) / s
        x = 0.25 * s
        y = (m[0, 1] + m[1, 0]) / s
        z = (m[0, 2] + m[2, 0]) / s
    elif m[1, 1] > m[2, 2]:
        s = np.sqrt(1.0 + m[1, 1] - m[0, 0] - m[2, 2]) * 2
        w = (m[0, 2] - m[2, 0]) / s
        x = (m[0, 1] + m[1, 0]) / s
        y = 0.25 * s
        z = (m[1, 2] + m[2, 1]) / s
    else:
        s = np.sqrt(1.0 + m[2, 2] - m[0, 0] - m[1, 1]) * 2
        w = (m[1, 0] - m[0, 1]) / s
        x = (m[0, 2] + m[2, 0]) / s
        y = (m[1, 2] + m[2, 1]) / s
        z = 0.25 * s
    q = np.array([x, y, z, w])
    q /= np.linalg.norm(q)
    if q[3] < 0:
        q = -q
    return q


def mediapipe_world_to_ue(world: np.ndarray) -> np.ndarray:
    """MediaPipe world (метры; x вправо по кадру, y вниз, z от камеры) -> Unreal (см; X вперёд, Y вправо, Z вверх).

    Человек стоит лицом к камере, поэтому «вперёд» для него — к камере (-z),
    а его правая рука находится в левой части кадра (-x).
    """
    out = np.empty_like(world)
    out[:, 0] = -world[:, 2]
    out[:, 1] = -world[:, 0]
    out[:, 2] = -world[:, 1]
    return out * 100.0


def compute_points(pose, aspect: float, root_motion: float):
    """-> (root[3], points[33,3]) в сантиметрах Unreal, точки относительно root, пол на Z=0."""
    pts = mediapipe_world_to_ue(pose.world)
    floor = pts[FLOOR_POINTS, 2].min()
    pts[:, 2] -= floor
    root = np.zeros(3)
    if root_motion:
        n = pose.norm
        hip_x = (n[IDX["left_hip"], 0] + n[IDX["right_hip"], 0]) / 2
        root[1] = -(hip_x - 0.5) * aspect * root_motion   # правая часть кадра — левая сторона человека
    return root, pts


def compute_bones(pts: np.ndarray):
    """Локальные трансформы костей: список [tx,ty,tz,qx,qy,qz,qw]; плюс компонентные (для проверки)."""
    P = lambda n: pts[IDX[n]]  # noqa: E731
    hip_c = (P("left_hip") + P("right_hip")) / 2
    sh_c = (P("left_shoulder") + P("right_shoulder")) / 2
    ear_c = (P("left_ear") + P("right_ear")) / 2
    right_hips = P("right_hip") - P("left_hip")
    right_sh = P("right_shoulder") - P("left_shoulder")
    up = sh_c - hip_c
    # «вперёд» корпуса. В координатах UE (X вперёд, Y вправо, Z вверх) cross(Y, Z) = X.
    fwd = _norm(np.cross(right_hips, up))
    if fwd is None:
        fwd = np.array([1.0, 0.0, 0.0])

    def limb(a, b, c, fallback):
        """Базис для сегмента a->b, ось сгиба — нормаль плоскости (a, b, c)."""
        n = np.cross(b - a, c - b)
        return _basis(b - a, n if np.linalg.norm(n) > 1e-3 else None, fallback)

    hand_mid_l = (P("left_index") + P("left_pinky")) / 2
    hand_mid_r = (P("right_index") + P("right_pinky")) / 2

    # (позиция сустава, компонентный поворот) для каждой кости
    comp = [None] * len(BONES)
    comp[0] = (np.zeros(3), np.eye(3))
    comp[1] = (hip_c, _basis(up, right_hips, right_sh))
    comp[2] = (hip_c, _basis(up, right_sh, right_hips))
    comp[3] = (sh_c, _basis(ear_c - sh_c, right_sh, right_hips))
    head_up = ear_c - sh_c
    comp[4] = (ear_c, _basis(head_up, P("right_ear") - P("left_ear"), right_sh))
    comp[5] = (P("left_shoulder"), limb(P("left_shoulder"), P("left_elbow"), P("left_wrist"), fwd))
    comp[6] = (P("left_elbow"), _basis(P("left_wrist") - P("left_elbow"), comp[5][1][:, 2], fwd))
    comp[7] = (P("left_wrist"), _basis(hand_mid_l - P("left_wrist"), P("left_index") - P("left_pinky"), fwd))
    comp[8] = (P("right_shoulder"), limb(P("right_shoulder"), P("right_elbow"), P("right_wrist"), fwd))
    comp[9] = (P("right_elbow"), _basis(P("right_wrist") - P("right_elbow"), comp[8][1][:, 2], fwd))
    comp[10] = (P("right_wrist"), _basis(hand_mid_r - P("right_wrist"), P("right_index") - P("right_pinky"), fwd))
    comp[11] = (P("left_hip"), limb(P("left_hip"), P("left_knee"), P("left_ankle"), right_hips))
    comp[12] = (P("left_knee"), _basis(P("left_ankle") - P("left_knee"), comp[11][1][:, 2], right_hips))
    comp[13] = (P("left_ankle"), _basis(P("left_foot_index") - P("left_ankle"), right_hips, None))
    comp[14] = (P("right_hip"), limb(P("right_hip"), P("right_knee"), P("right_ankle"), right_hips))
    comp[15] = (P("right_knee"), _basis(P("right_ankle") - P("right_knee"), comp[14][1][:, 2], right_hips))
    comp[16] = (P("right_ankle"), _basis(P("right_foot_index") - P("right_ankle"), right_hips, None))

    local = []
    for i, (pos, rot) in enumerate(comp):
        p = BONE_PARENTS[i]
        if p < 0:
            t, r = pos, rot
        else:
            ppos, prot = comp[p]
            t = prot.T @ (pos - ppos)
            r = prot.T @ rot
        q = mat_to_quat(r)
        local.append([*map(float, t), *map(float, q)])
    return local, comp


class LiveLinkOutput:
    def __init__(self):
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._seen = set()
        self.sent = 0

    def send_frame(self, poses, aspect: float, s: dict):
        if not s.get("ll_enabled"):
            return 0
        names = LANDMARK_NAMES if s.get("ll_points", "all") == "all" else CORE_JOINTS
        persons, now = [], set()
        for slot, pose in enumerate(poses):
            if pose is None:
                continue
            pid = slot + 1
            now.add(pid)
            root, pts = compute_points(pose, aspect, float(s.get("ll_root_motion", 0.0)))
            hip_c = (pts[IDX["left_hip"]] + pts[IDX["right_hip"]]) / 2
            sh_c = (pts[IDX["left_shoulder"]] + pts[IDX["right_shoulder"]]) / 2
            points = {n: [round(float(v), 3) for v in pts[IDX[n]]] for n in names}
            points["hip_center"] = [round(float(v), 3) for v in hip_c]
            points["shoulder_center"] = [round(float(v), 3) for v in sh_c]
            bones, _ = compute_bones(pts)
            bones[0][:3] = [float(v) for v in root]        # root несёт перемещение по площадке
            persons.append({
                "id": pid,
                "root": [round(float(v), 3) for v in root],
                "points": points,
                "names": BONE_NAMES,
                "parents": BONE_PARENTS,
                "bones": [[round(v, 5) for v in b] for b in bones],
            })
        lost = sorted(self._seen - now)
        self._seen = now
        packet = {"v": 1, "prefix": s.get("ll_prefix", "PGL") or "PGL", "persons": persons, "lost": lost}
        data = json.dumps(packet, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self._sock.sendto(data, (s.get("ll_ip", "127.0.0.1"), int(s.get("ll_port", 54321))))
        self.sent += 1
        return 1
