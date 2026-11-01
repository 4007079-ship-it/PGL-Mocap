"""Рабочий цикл: источник -> трекинг -> сглаживание -> OSC / Live Link + кадр превью."""
import threading
import time
import traceback

import cv2
import numpy as np

from .extras import HAND_SKELETON, ExtrasTracker, Face, Hand
from .filters import OneEuro, params_from_strength
from .livelink_output import LiveLinkOutput
from .osc_output import OscOutput
from .sources import make_source
from .tracker import IDX, MIRROR_PERM, SKELETON, Pose, PoseTracker

ROT = {90: cv2.ROTATE_90_CLOCKWISE, 180: cv2.ROTATE_180, 270: cv2.ROTATE_90_COUNTERCLOCKWISE}
SLOT_COLORS = [(53, 230, 163), (255, 170, 40), (60, 140, 255), (220, 80, 220)]


class _Slot:
    def __init__(self):
        self.f_norm = OneEuro()
        self.f_world = OneEuro()
        self.f_vis = OneEuro()
        self.f_hand = {"l": OneEuro(), "r": OneEuro()}
        self.f_face = OneEuro()
        self.face_names = None
        self.hands = None
        self.face = None
        self.pose = None
        self.last_seen = 0.0

    def center(self):
        if self.pose is None:
            return None
        n = self.pose.norm
        return (n[IDX["left_hip"], :2] + n[IDX["right_hip"], :2]) / 2


class Engine:
    def __init__(self, settings: dict):
        self.s = settings              # общий словарь, GUI может менять «живые» параметры
        self._thread = None
        self._stop = threading.Event()
        self._preview_lock = threading.Lock()
        self._preview = None
        self.status = "Остановлено"
        self.error = None
        self.fps = 0.0
        self.persons = 0
        self.msg_rate = 0.0
        self.ll_rate = 0.0
        self.out_error = None
        self.source_info = ""

    @property
    def running(self):
        return self._thread is not None and self._thread.is_alive()

    def start(self):
        if self.running:
            return
        self._stop.clear()
        self.error = None
        self._thread = threading.Thread(target=self._run, name="engine", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)
        self._thread = None

    def get_preview(self):
        with self._preview_lock:
            p, self._preview = self._preview, None
            return p

    # ------------------------------------------------------------------ цикл
    def _run(self):
        src = tracker = extras = None
        try:
            self.status = "Загрузка модели…"
            s = self.s
            max_slots = int(s["num_poses"])
            tracker = PoseTracker(s["model"], max_slots, s["min_confidence"], s["use_gpu"])
            if s.get("track_hands") or s.get("track_face"):
                extras = ExtrasTracker(bool(s.get("track_hands")), bool(s.get("track_face")), s["use_gpu"])
            self.status = "Подключение к источнику…"
            src = make_source(s)
            src.start()
            osc = OscOutput()
            livelink = LiveLinkOutput()
            ll_before = 0
            slots = [_Slot() for _ in range(max_slots)]
            seq = 0
            t_fps = time.perf_counter()
            frames = 0
            sent_before = 0
            got_first = False
            while not self._stop.is_set():
                frame, seq = src.wait_frame(seq, 0.5)
                if src.error:
                    raise RuntimeError(src.error)
                if frame is None:
                    if not got_first:
                        self.status = "Ожидание кадров от источника…"
                    continue
                got_first = True
                s = self.s
                rot = int(s["rotation"])
                if rot in ROT:
                    frame = cv2.rotate(frame, ROT[rot])
                if s["mirror"]:
                    frame = cv2.flip(frame, 1)
                h, w = frame.shape[:2]
                aspect = w / h

                poses = tracker.process(frame, int(s["proc_width"]))
                if s["mirror"]:
                    # после отражения левое/правое у MediaPipe меняются местами — возвращаем анатомию
                    poses = [Pose(p.norm[MIRROR_PERM], p.world[MIRROR_PERM], p.vis[MIRROR_PERM])
                             for p in poses]
                now = time.perf_counter()
                out = self._assign(slots, poses, now, s)
                if extras is not None:
                    self._extras(extras, slots, out, frame, now, s)
                try:
                    osc.send_frame(out, aspect, s, max_slots)
                except OSError as e:
                    self.out_error = f"OSC: {e}"
                try:
                    livelink.send_frame(out, aspect, s)
                except OSError as e:
                    self.out_error = f"Live Link: {e}"

                self._make_preview(frame, out)
                frames += 1
                if now - t_fps >= 1.0:
                    dt = now - t_fps
                    self.fps = frames / dt
                    self.msg_rate = (osc.sent - sent_before) / dt
                    sent_before = osc.sent
                    self.ll_rate = (livelink.sent - ll_before) / dt
                    ll_before = livelink.sent
                    frames = 0
                    t_fps = now
                    self.persons = sum(1 for p in out if p is not None)
                    self.source_info = src.info
                    self.status = "Работает"
        except Exception as e:
            self.error = f"{e}"
            self.status = "Ошибка"
            traceback.print_exc()
        finally:
            if src:
                src.stop()
            if tracker:
                tracker.close()
            if extras:
                extras.close()
            if self.status != "Ошибка":
                self.status = "Остановлено"
            self.fps = 0.0

    def _assign(self, slots, poses, now, s):
        """Сопоставить найденные позы слотам (стабильная нумерация людей) и сгладить."""
        mc, beta = params_from_strength(float(s["smoothing"]))
        hold = float(s["hold_seconds"])
        free = list(range(len(slots)))
        pairs = []
        centers = [((p.norm[IDX["left_hip"], :2] + p.norm[IDX["right_hip"], :2]) / 2) for p in poses]
        # жадно: ближайшие пары «поза — слот»
        cand = []
        for pi, c in enumerate(centers):
            for si in free:
                sc = slots[si].center()
                d = 0.5 if sc is None else float(np.linalg.norm(c - sc))
                cand.append((d, pi, si))
        cand.sort()
        used_p, used_s = set(), set()
        for d, pi, si in cand:
            if pi in used_p or si in used_s:
                continue
            used_p.add(pi)
            used_s.add(si)
            pairs.append((pi, si))

        out = []
        assigned = {si: pi for pi, si in pairs}
        for si, slot in enumerate(slots):
            for f in (slot.f_norm, slot.f_world, slot.f_vis):
                f.min_cutoff, f.beta = mc, beta
            if si in assigned:
                p = poses[assigned[si]]
                if slot.pose is None:
                    slot.f_norm.reset(); slot.f_world.reset(); slot.f_vis.reset()
                if s["smoothing"] > 0.001:
                    p = Pose(slot.f_norm(p.norm, now), slot.f_world(p.world, now), slot.f_vis(p.vis, now))
                slot.pose = p
                slot.last_seen = now
                out.append(p)
            elif slot.pose is not None and now - slot.last_seen <= hold:
                out.append(slot.pose)         # кратковременная потеря — держим последнюю позу
            else:
                slot.pose = None
                out.append(None)
        return out

    def _extras(self, extras, slots, out, frame, now, s):
        """Пальцы и мимика для каждого человека + сглаживание (своими фильтрами слота)."""
        mc, beta = params_from_strength(float(s["smoothing"]))
        smooth = float(s["smoothing"]) > 0.001
        for slot, pose in zip(slots, out):
            if pose is None:
                slot.hands = slot.face = None
                continue
            fresh = slot.last_seen == now     # поза найдена в этом кадре, а не удержана
            if fresh:
                if extras.hands_on:
                    found = extras.hands_for(frame, pose)
                    hands = {}
                    for side, hand in found.items():
                        f = slot.f_hand[side]
                        f.min_cutoff, f.beta = mc, beta
                        if hand is None:
                            f.reset()
                            hands[side] = None
                            continue
                        if smooth:
                            v = f(np.concatenate([hand.norm.ravel(), hand.world.ravel()]), now)
                            hand = Hand(v[:63].reshape(21, 3), v[63:].reshape(21, 3))
                        hands[side] = hand
                    slot.hands = hands
                if extras.face_on:
                    face = extras.face_for(frame, pose, mirror=bool(s["mirror"]))
                    if face is None:
                        slot.f_face.reset()
                    elif smooth:
                        names = sorted(face.shapes)
                        if names != slot.face_names:
                            slot.f_face.reset()
                            slot.face_names = names
                        vals = [face.shapes[n] for n in names] + list(face.head or (0.0, 0.0, 0.0))
                        # мимика быстрая — сглаживаем мягче, чем тело
                        slot.f_face.min_cutoff, slot.f_face.beta = mc * 2, beta * 2
                        v = slot.f_face(np.array(vals), now)
                        shapes = {n: float(np.clip(v[i], 0, 1)) for i, n in enumerate(names)}
                        head = tuple(float(x) for x in v[len(names):]) if face.head else None
                        face = Face(shapes, head)
                    slot.face = face
            pose.hands = slot.hands
            pose.face = slot.face

    def _make_preview(self, frame, poses):
        h, w = frame.shape[:2]
        scale = min(960 / w, 540 / h, 1.0)
        img = cv2.resize(frame, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA) \
            if scale < 1.0 else frame.copy()
        ph, pw = img.shape[:2]
        for si, p in enumerate(poses):
            if p is None:
                continue
            col = SLOT_COLORS[si % len(SLOT_COLORS)]
            pts = np.stack([p.norm[:, 0] * pw, p.norm[:, 1] * ph], axis=1).astype(int)
            for a, b in SKELETON:
                if p.vis[a] > 0.3 and p.vis[b] > 0.3:
                    cv2.line(img, tuple(pts[a]), tuple(pts[b]), col, 2, cv2.LINE_AA)
            for i, (x, y) in enumerate(pts):
                if p.vis[i] > 0.3:
                    cv2.circle(img, (int(x), int(y)), 3, (255, 255, 255), -1, cv2.LINE_AA)
            for hand in (p.hands or {}).values():
                if hand is None:
                    continue
                hp = np.stack([hand.norm[:, 0] * pw, hand.norm[:, 1] * ph], axis=1).astype(int)
                for a, b in HAND_SKELETON:
                    cv2.line(img, tuple(hp[a]), tuple(hp[b]), col, 1, cv2.LINE_AA)
                for x, y in hp:
                    cv2.circle(img, (int(x), int(y)), 2, (255, 255, 255), -1, cv2.LINE_AA)
            if p.face is not None:
                sh = p.face.shapes
                txt = "blink L%.1f R%.1f  jaw %.1f  smile %.1f" % (
                    sh.get("eyeBlinkLeft", 0), sh.get("eyeBlinkRight", 0), sh.get("jawOpen", 0),
                    (sh.get("mouthSmileLeft", 0) + sh.get("mouthSmileRight", 0)) / 2)
                nx, ny = pts[IDX["nose"]]
                cv2.putText(img, txt, (int(nx) - 120, max(14, int(ny) - 40)), cv2.FONT_HERSHEY_SIMPLEX,
                            0.45, col, 1, cv2.LINE_AA)
            hx, hy = ((pts[IDX["left_hip"]] + pts[IDX["right_hip"]]) / 2).astype(int)
            cv2.putText(img, f"P{si + 1}", (int(hx) + 6, int(hy)), cv2.FONT_HERSHEY_SIMPLEX,
                        0.7, col, 2, cv2.LINE_AA)
        with self._preview_lock:
            self._preview = img
