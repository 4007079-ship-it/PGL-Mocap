"""Проверка вывода Live Link: оси, пол, и что из локальных трансформов костей
(как их соберёт Unreal) восстанавливаются исходные позиции суставов.

Запуск: python -m pytest tests  или  python tests/test_livelink.py
"""
import json
import socket
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pglmocap.livelink_output import (BONE_NAMES, BONE_PARENTS, LiveLinkOutput,  # noqa: E402
                                      compute_bones, compute_points)
from pglmocap.tracker import IDX, LANDMARK_NAMES, Pose  # noqa: E402

# Суставы, в которых начинается каждая кость (для проверки прямой кинематики)
BONE_JOINT = {
    "upperarm_l": "left_shoulder", "lowerarm_l": "left_elbow", "hand_l": "left_wrist",
    "upperarm_r": "right_shoulder", "lowerarm_r": "right_elbow", "hand_r": "right_wrist",
    "thigh_l": "left_hip", "calf_l": "left_knee", "foot_l": "left_ankle",
    "thigh_r": "right_hip", "calf_r": "right_knee", "foot_r": "right_ankle",
}


def quat_rotate(q, v):
    """Поворот вектора кватернионом (x, y, z, w) — та же формула, что FQuat::RotateVector."""
    x, y, z, w = q
    u = np.array([x, y, z])
    t = 2.0 * np.cross(u, v)
    return v + w * t + np.cross(u, t)


def quat_mul(a, b):
    """a * b (сначала b, потом a) для (x, y, z, w)."""
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return np.array([
        aw * bx + ax * bw + ay * bz - az * by,
        aw * by - ax * bz + ay * bw + az * bx,
        aw * bz + ax * by - ay * bx + az * bw,
        aw * bw - ax * bx - ay * by - az * bz,
    ])


def fk(bones):
    """Компонентные позиции и повороты из локальных трансформов (как в Unreal)."""
    pos, rot = [None] * len(bones), [None] * len(bones)
    for i, b in enumerate(bones):
        t, q = np.array(b[:3]), np.array(b[3:])
        p = BONE_PARENTS[i]
        if p < 0:
            pos[i], rot[i] = t, q
        else:
            pos[i] = pos[p] + quat_rotate(rot[p], t)
            rot[i] = quat_mul(rot[p], q)
    return pos, rot


def make_pose(seed=0, arm_raise=0.0):
    """Человек стоит лицом к камере; координаты в системе MediaPipe world (м, y вниз, z от камеры).
    Правая рука человека — в левой части кадра (x < 0)."""
    rng = np.random.default_rng(seed)
    w = {}
    w["left_hip"], w["right_hip"] = [0.10, 0, 0], [-0.10, 0, 0]
    w["left_shoulder"], w["right_shoulder"] = [0.18, -0.50, 0.02], [-0.18, -0.50, 0.02]
    w["left_elbow"], w["right_elbow"] = [0.22, -0.25, 0.0], [-0.40, -0.55 - arm_raise, -0.05]
    w["left_wrist"], w["right_wrist"] = [0.24, -0.02, -0.08], [-0.62, -0.62 - arm_raise, -0.10]
    w["left_index"], w["right_index"] = [0.25, 0.06, -0.10], [-0.70, -0.66 - arm_raise, -0.12]
    w["left_pinky"], w["right_pinky"] = [0.22, 0.06, -0.08], [-0.70, -0.62 - arm_raise, -0.10]
    w["left_thumb"], w["right_thumb"] = [0.26, 0.03, -0.12], [-0.66, -0.68 - arm_raise, -0.14]
    w["left_knee"], w["right_knee"] = [0.11, 0.42, -0.05], [-0.11, 0.42, -0.03]
    w["left_ankle"], w["right_ankle"] = [0.11, 0.85, 0.02], [-0.11, 0.85, 0.02]
    w["left_heel"], w["right_heel"] = [0.11, 0.90, 0.06], [-0.11, 0.90, 0.06]
    w["left_foot_index"], w["right_foot_index"] = [0.13, 0.92, -0.12], [-0.13, 0.92, -0.12]
    w["nose"] = [0, -0.66, -0.10]
    w["left_ear"], w["right_ear"] = [0.07, -0.66, 0.0], [-0.07, -0.66, 0.0]
    for n, v in [("left_eye", [0.03, -0.68, -0.08]), ("right_eye", [-0.03, -0.68, -0.08]),
                 ("mouth_left", [0.02, -0.62, -0.09]), ("mouth_right", [-0.02, -0.62, -0.09])]:
        w[n] = v
    world = np.zeros((33, 3))
    for i, n in enumerate(LANDMARK_NAMES):
        world[i] = w.get(n, w.get(n.replace("_inner", "").replace("_outer", ""), [0, -0.66, -0.08]))
    world += rng.normal(0, 0.003, world.shape)
    norm = np.zeros((33, 3))
    norm[:, 0] = 0.5 + world[:, 0] * 0.5
    norm[:, 1] = 0.5 + world[:, 1] * 0.5
    return Pose(norm, world, np.ones(33))


def test_axes_and_floor():
    root, pts = compute_points(make_pose(), 16 / 9, 0.0)
    assert np.allclose(root, 0)
    # пол
    assert abs(min(pts[IDX[n], 2] for n in ("left_heel", "right_heel", "left_foot_index", "right_foot_index"))) < 1e-6
    # голова выше бёдер, Z вверх
    assert pts[IDX["nose"], 2] > pts[IDX["left_hip"], 2] + 50
    # правая рука человека — +Y, левая — -Y
    assert pts[IDX["right_shoulder"], 1] > 0 > pts[IDX["left_shoulder"], 1]
    # нос впереди ушей (смотрит вперёд, +X)
    assert pts[IDX["nose"], 0] > pts[IDX["left_ear"], 0]
    # носки впереди пяток
    assert pts[IDX["left_foot_index"], 0] > pts[IDX["left_heel"], 0]


def test_root_motion():
    pose = make_pose()
    pose.norm[:, 0] += 0.2      # человек сместился вправо по кадру = к своей левой руке
    root, _ = compute_points(pose, 16 / 9, 200.0)
    assert root[1] < 0 and abs(root[1] + 0.2 * 16 / 9 * 200) < 2.0  # шум позы ~0.3 см


def test_fk_reconstructs_joints():
    for seed, raise_ in [(0, 0.0), (1, 0.3), (2, -0.2)]:
        _, pts = compute_points(make_pose(seed, raise_), 16 / 9, 0.0)
        bones, comp = compute_bones(pts)
        pos, rot = fk(bones)
        for name, joint in BONE_JOINT.items():
            i = BONE_NAMES.index(name)
            assert np.allclose(pos[i], pts[IDX[joint]], atol=1e-3), (name, pos[i], pts[IDX[joint]])
        # ось X кости смотрит на следующий сустав
        for bone, child in (("upperarm_r", "right_elbow"), ("calf_l", "left_ankle"), ("thigh_r", "right_knee")):
            i = BONE_NAMES.index(bone)
            x_axis = quat_rotate(rot[i], np.array([1.0, 0, 0]))
            d = pts[IDX[child]] - pos[i]
            assert np.dot(x_axis, d / np.linalg.norm(d)) > 0.999, bone
        for b in bones:
            assert abs(np.linalg.norm(b[3:]) - 1) < 1e-4


def test_packet_over_udp():
    rx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    rx.bind(("127.0.0.1", 0))
    rx.settimeout(2)
    port = rx.getsockname()[1]
    out = LiveLinkOutput()
    s = {"ll_enabled": True, "ll_ip": "127.0.0.1", "ll_port": port, "ll_prefix": "PGL",
         "ll_points": "all", "ll_root_motion": 0.0}
    out.send_frame([make_pose(), None], 16 / 9, s)
    data, _ = rx.recvfrom(65535)
    pkt = json.loads(data)
    assert pkt["v"] == 1 and pkt["prefix"] == "PGL" and len(pkt["persons"]) == 1
    p = pkt["persons"][0]
    assert p["id"] == 1 and len(p["points"]) == 35 and len(p["bones"]) == len(BONE_NAMES)
    assert len(data) < 8000, len(data)
    out.send_frame([None, None], 16 / 9, s)
    pkt = json.loads(rx.recvfrom(65535)[0])
    assert pkt["persons"] == [] and pkt["lost"] == [1]


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("OK", name)
