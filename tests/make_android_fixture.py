"""Эталонные данные для теста Android-версии: позы + то, что из них делает компьютерная версия.

python tests/make_android_fixture.py  -> android/app/src/test/resources/fixture.json
"""
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from test_livelink import make_pose  # noqa: E402
from pglmocap.livelink_output import compute_bones, compute_points  # noqa: E402
from pglmocap.osc_output import _screen_coords, _world_coords, transform  # noqa: E402
from pglmocap.settings import DEFAULTS  # noqa: E402

cases = []
for seed, raise_ in [(0, 0.0), (1, 0.3), (2, -0.2), (3, 0.6)]:
    pose = make_pose(seed, raise_)
    aspect = 16 / 9
    root, pts = compute_points(pose, aspect, 200.0)
    bones, _ = compute_bones(pts)
    s_world_z = dict(DEFAULTS, coord_mode="world", up_axis="z", scale=2.0, flip_x=True, offset_x=1.0, offset_y=-2.0, offset_z=0.5)
    cases.append({
        "norm": pose.norm.tolist(), "world": pose.world.tolist(), "vis": pose.vis.tolist(), "aspect": aspect,
        "ll_root": root.tolist(), "ll_points": pts.tolist(), "ll_bones": bones,
        "osc_screen": transform(_screen_coords(pose.norm, aspect), DEFAULTS).tolist(),
        "osc_world_z": transform(_world_coords(pose.world), s_world_z).tolist(),
    })
out = ROOT / "android/app/src/test/resources/fixture.json"
out.write_text(json.dumps({"cases": cases}))
print("written", out, len(cases))
