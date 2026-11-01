"""Пальцы и мимика в выводе OSC и Live Link (без моделей — на синтетических данных).

Запуск: python tests/test_extras_output.py
"""
import json
import socket
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pglmocap.extras import HAND_POINTS, Face, Hand  # noqa: E402
from pglmocap.livelink_output import LiveLinkOutput, compute_points  # noqa: E402
from pglmocap.osc_output import OscOutput  # noqa: E402
from pglmocap.settings import DEFAULTS  # noqa: E402
from pglmocap.tracker import IDX  # noqa: E402
from test_livelink import make_pose  # noqa: E402


def pose_with_extras():
    p = make_pose()
    wr = IDX["right_wrist"]
    rel = np.zeros((21, 3))
    rel[:, 0] = -np.linspace(0, 0.18, 21)        # пальцы тянутся дальше от тела (к правой руке, -x MediaPipe)
    rel[:, 1] = -np.linspace(0, 0.02, 21)
    norm = np.tile(p.norm[wr], (21, 1)) + np.c_[rel[:, 0] * 0.5, rel[:, 1] * 0.5, np.zeros(21)]
    p.hands = {"l": None, "r": Hand(norm, p.world[wr] + rel)}
    p.face = Face({"eyeBlinkLeft": 0.9, "eyeBlinkRight": 0.1, "jawOpen": 0.4, "mouthSmileLeft": 0.7}, (10.0, -5.0, 2.0))
    return p


def listen():
    rx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    rx.bind(("127.0.0.1", 0))
    rx.settimeout(1)
    return rx, rx.getsockname()[1]


def drain(rx):
    out = []
    try:
        while True:
            out.append(rx.recvfrom(65535)[0])
    except socket.timeout:
        return out


def test_osc_hands_face():
    from pythonosc.osc_message import OscMessage
    rx, port = listen()
    s = dict(DEFAULTS, osc_port=port, track_hands=True, track_face=True)
    OscOutput().send_frame([pose_with_extras()], 16 / 9, s, 1)
    msgs = {m.address: m.params for m in (OscMessage(d) for d in drain(rx))}
    assert msgs["/pglmocap/p1/hand_r/detected"] == [1.0]
    assert msgs["/pglmocap/p1/hand_l/detected"] == [0.0]
    for name in HAND_POINTS:
        assert len(msgs[f"/pglmocap/p1/hand_r/{name}"]) == 3, name
    assert "/pglmocap/p1/hand_l/wrist" not in msgs
    assert msgs["/pglmocap/p1/face/detected"] == [1.0]
    assert abs(msgs["/pglmocap/p1/face/jawOpen"][0] - 0.4) < 1e-6
    assert len(msgs["/pglmocap/p1/face/head"]) == 3
    # запястье руки совпадает с запястьем тела (экранные координаты)
    assert np.allclose(msgs["/pglmocap/p1/hand_r/wrist"], msgs["/pglmocap/p1/right_wrist"], atol=1e-5)


def test_osc_off_by_default():
    from pythonosc.osc_message import OscMessage
    rx, port = listen()
    OscOutput().send_frame([pose_with_extras()], 16 / 9, dict(DEFAULTS, osc_port=port), 1)
    addrs = {OscMessage(d).address for d in drain(rx)}
    assert not any("/hand_" in a or "/face/" in a for a in addrs)


def test_livelink_hands_face():
    rx, port = listen()
    p = pose_with_extras()
    s = {"ll_enabled": True, "ll_ip": "127.0.0.1", "ll_port": port, "ll_prefix": "PGL", "ll_points": "all",
         "ll_root_motion": 0.0}
    LiveLinkOutput().send_frame([p], 16 / 9, s)
    pkt = json.loads(drain(rx)[-1])
    person = pkt["persons"][0]
    pts = person["points"]
    assert len([k for k in pts if k.startswith("hand_r_")]) == 21
    assert not any(k.startswith("hand_l_") for k in pts)
    # запястье руки в Unreal = запястье тела (тот же пол, те же оси)
    assert np.allclose(pts["hand_r_wrist"], pts["right_wrist"], atol=1e-2)
    # пальцы правой руки — дальше вправо (+Y), чем запястье
    assert pts["hand_r_index_tip"][1] > pts["hand_r_wrist"][1]
    c = person["curves"]
    assert c["EyeBlinkLeft"] == 0.9 and c["JawOpen"] == 0.4
    assert c["HeadYawDeg"] == 10.0 and c["HeadPitchDeg"] == -5.0
    assert len(json.dumps(pkt)) < 16000


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("OK", name)
