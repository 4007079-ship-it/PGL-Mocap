"""Окно приложения PGL Mocap (tkinter)."""
import threading
import tkinter as tk
import urllib.request
from tkinter import filedialog, messagebox, ttk

import cv2
from PIL import Image, ImageTk

from . import APP_NAME, __version__
from .engine import Engine
from .paths import MODEL_FILES, MODEL_URLS, available_models, resource_dir, settings_dir
from .settings import load_settings, save_settings
from .sources import list_cameras, list_ndi_sources, ndi_available

BG = "#16181d"
PANEL = "#1f2229"
FG = "#e6e8ec"
MUTED = "#8b93a1"
ACCENT = "#3fb68b"
DANGER = "#e5534b"

RESTART_KEYS = {
    "source_type", "camera_index", "camera_backend", "camera_resolution", "camera_fps",
    "camera_mjpg", "ndi_source", "file_path", "file_loop", "model", "num_poses",
    "min_confidence", "use_gpu",
}

SOURCE_TYPES = [("camera", "Камера / карта захвата"), ("ndi", "NDI"), ("file", "Видеофайл")]
COORD_MODES = [("screen", "Кадр (позиция в кадре, высота кадра = 1)"),
               ("world", "Мир (метры, скелет относительно бёдер)")]
UP_AXES = [("y", "Y вверх"), ("z", "Z вверх")]
JOINT_SETS = [("all", "Все 33 точки"), ("core", "Основные 13 точек")]
LL_POINT_SETS = [("all", "Все 33 точки + центры"), ("core", "Основные 13 точек + центры")]
BACKENDS = [("dshow", "DirectShow"), ("msmf", "Media Foundation"), ("any", "Авто")]


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.s = load_settings()
        self.engine = Engine(self.s)
        self.vars = {}
        self._cams = []
        self._photo = None
        self._dirty_restart = False

        root.title(f"{APP_NAME} {__version__}")
        root.configure(bg=BG)
        root.minsize(1100, 640)
        try:
            ico = resource_dir() / "assets" / "pgl_mocap.ico"
            if ico.exists():
                root.iconbitmap(default=str(ico))
        except Exception:
            pass
        self._style()
        self._build()
        self._refresh_cameras()
        self._refresh_models()
        self._on_source_type()
        root.protocol("WM_DELETE_WINDOW", self._on_close)
        root.after(33, self._tick)

    # ------------------------------------------------------------------ стиль
    def _style(self):
        st = ttk.Style(self.root)
        st.theme_use("clam")
        st.configure(".", background=PANEL, foreground=FG, fieldbackground="#2a2e37",
                     bordercolor="#333844", lightcolor=PANEL, darkcolor=PANEL, font=("Segoe UI", 10))
        st.configure("TFrame", background=PANEL)
        st.configure("Root.TFrame", background=BG)
        st.configure("TLabel", background=PANEL, foreground=FG)
        st.configure("Muted.TLabel", background=PANEL, foreground=MUTED, font=("Segoe UI", 9))
        st.configure("Title.TLabel", background=BG, foreground=FG, font=("Segoe UI Semibold", 16))
        st.configure("Status.TLabel", background=BG, foreground=MUTED, font=("Segoe UI", 10))
        st.configure("TNotebook", background=BG, borderwidth=0)
        st.configure("TNotebook.Tab", background="#252931", foreground=MUTED, padding=(14, 6))
        st.map("TNotebook.Tab", background=[("selected", PANEL)], foreground=[("selected", FG)])
        st.configure("TCheckbutton", background=PANEL, foreground=FG)
        st.map("TCheckbutton", background=[("active", PANEL)])
        st.configure("TButton", background="#2d323c", foreground=FG, padding=(10, 5))
        st.map("TButton", background=[("active", "#383e4a")])
        st.configure("Start.TButton", background=ACCENT, foreground="#0d1411",
                     font=("Segoe UI Semibold", 12), padding=(10, 10))
        st.map("Start.TButton", background=[("active", "#4fcf9f")])
        st.configure("Stop.TButton", background=DANGER, foreground="#ffffff",
                     font=("Segoe UI Semibold", 12), padding=(10, 10))
        st.map("Stop.TButton", background=[("active", "#f06b63")])
        st.configure("TCombobox", arrowcolor=FG, foreground=FG)
        st.map("TCombobox",
               fieldbackground=[("readonly", "#2a2e37"), ("!readonly", "#2a2e37")],
               foreground=[("readonly", FG), ("!readonly", FG)],
               selectbackground=[("readonly", "#2a2e37"), ("!readonly", "#3a4050")],
               selectforeground=[("readonly", FG), ("!readonly", FG)],
               background=[("active", "#383e4a"), ("!active", "#2d323c")])
        st.configure("TEntry", foreground=FG, insertcolor=FG)
        st.configure("TSpinbox", foreground=FG, arrowcolor=FG, insertcolor=FG)
        self.root.option_add("*TCombobox*Listbox.background", "#2a2e37")
        self.root.option_add("*TCombobox*Listbox.foreground", FG)
        self.root.option_add("*TCombobox*Listbox.selectBackground", ACCENT)
        self.root.option_add("*TCombobox*Listbox.selectForeground", "#0d1411")
        st.configure("Horizontal.TScale", background=ACCENT, troughcolor="#2a2e37",
                     bordercolor="#333844", lightcolor=ACCENT, darkcolor=ACCENT)
        st.map("Horizontal.TScale", background=[("active", "#4fcf9f")])

    # ------------------------------------------------------------------ разметка
    def _build(self):
        outer = ttk.Frame(self.root, style="Root.TFrame", padding=12)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(1, weight=1)

        head = ttk.Frame(outer, style="Root.TFrame")
        head.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        ttk.Label(head, text=APP_NAME, style="Title.TLabel").pack(side="left")
        self.status_lbl = ttk.Label(head, text="Остановлено", style="Status.TLabel")
        self.status_lbl.pack(side="right")

        # превью
        prev = tk.Frame(outer, bg="#0c0d10", highlightthickness=1, highlightbackground="#2a2e37")
        prev.grid(row=1, column=0, sticky="nsew", padx=(0, 12))
        self.preview = tk.Label(prev, bg="#0c0d10", fg=MUTED, text="Нажмите «Старт»",
                                font=("Segoe UI", 12))
        self.preview.pack(fill="both", expand=True)

        # правая колонка
        right = ttk.Frame(outer, style="Root.TFrame", width=400)
        right.grid(row=1, column=1, sticky="ns")
        nb = ttk.Notebook(right)
        nb.pack(fill="both", expand=True)
        nb.add(self._tab_source(nb), text="Источник")
        nb.add(self._tab_tracking(nb), text="Трекинг")
        nb.add(self._tab_osc(nb), text="OSC / Aximmetry")
        nb.add(self._tab_unreal(nb), text="Unreal Live Link")

        self.hint_lbl = ttk.Label(right, text="", style="Status.TLabel", wraplength=380)
        self.hint_lbl.pack(fill="x", pady=(8, 0))
        self.start_btn = ttk.Button(right, text="▶  Старт", style="Start.TButton", command=self._toggle)
        self.start_btn.pack(fill="x", pady=(8, 0))

    def _grid_row(self, parent, row, label, widget, hint=None):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=4, padx=(0, 10))
        widget.grid(row=row, column=1, sticky="ew", pady=4)
        if hint:
            ttk.Label(parent, text=hint, style="Muted.TLabel", wraplength=340).grid(
                row=row + 1, column=0, columnspan=2, sticky="w")

    def _frame(self, parent):
        f = ttk.Frame(parent, padding=14)
        f.columnconfigure(1, weight=1)
        return f

    # --- переменные, связанные с настройками
    def _var(self, key, kind="str"):
        cls = {"str": tk.StringVar, "int": tk.IntVar, "float": tk.DoubleVar, "bool": tk.BooleanVar}[kind]
        v = cls(value=self.s[key])
        self.vars[key] = v

        def on_change(*_):
            try:
                val = v.get()
            except (tk.TclError, ValueError):
                return
            if self.s.get(key) != val:
                self.s[key] = val
                if key in RESTART_KEYS and self.engine.running:
                    self._dirty_restart = True
        v.trace_add("write", on_change)
        return v

    def _choice(self, parent, key, options, width=None, command=None):
        """Комбобокс с отображаемыми подписями и внутренними значениями."""
        labels = [lbl for _, lbl in options]
        values = [val for val, _ in options]
        cb = ttk.Combobox(parent, values=labels, state="readonly", width=width or 28)
        cur = self.s[key]
        cb.current(values.index(cur) if cur in values else 0)

        def on_sel(_e=None):
            val = values[cb.current()]
            if self.s.get(key) != val:
                self.s[key] = val
                if key in RESTART_KEYS and self.engine.running:
                    self._dirty_restart = True
            if command:
                command()
        cb.bind("<<ComboboxSelected>>", on_sel)
        return cb

    # --- вкладка «Источник»
    def _tab_source(self, nb):
        f = self._frame(nb)
        r = 0
        self.src_cb = self._choice(f, "source_type", SOURCE_TYPES, command=self._on_source_type)
        self._grid_row(f, r, "Тип", self.src_cb); r += 1

        # камера
        self.cam_box = ttk.Frame(f)
        self.cam_box.columnconfigure(1, weight=1)
        cr = 0
        row = ttk.Frame(self.cam_box)
        row.columnconfigure(0, weight=1)
        self.cam_cb = ttk.Combobox(row, state="readonly", width=26)
        self.cam_cb.grid(row=0, column=0, sticky="ew")
        self.cam_cb.bind("<<ComboboxSelected>>", self._on_cam_selected)
        ttk.Button(row, text="↻", width=3, command=self._refresh_cameras).grid(row=0, column=1, padx=(6, 0))
        self._grid_row(self.cam_box, cr, "Устройство", row); cr += 1
        res = ttk.Combobox(self.cam_box, textvariable=self._var("camera_resolution"),
                           values=["auto", "640x480", "1280x720", "1920x1080", "3840x2160"])
        self._grid_row(self.cam_box, cr, "Разрешение", res); cr += 1
        fps = ttk.Combobox(self.cam_box, textvariable=self._var("camera_fps", "int"),
                           values=[25, 30, 50, 60], width=8)
        self._grid_row(self.cam_box, cr, "FPS", fps); cr += 1
        self._grid_row(self.cam_box, cr, "Бэкенд", self._choice(self.cam_box, "camera_backend", BACKENDS)); cr += 1
        ttk.Checkbutton(self.cam_box, text="MJPG (быстрее для USB-вебок)",
                        variable=self._var("camera_mjpg", "bool")).grid(row=cr, column=0, columnspan=2,
                                                                       sticky="w", pady=4); cr += 1
        ttk.Label(self.cam_box, style="Muted.TLabel", wraplength=340,
                  text="Карты захвата (Elgato, Magewell, AVerMedia, Blackmagic) видны здесь как обычные "
                       "устройства. Если карта не открывается — попробуйте другой бэкенд, выключите MJPG "
                       "и выставьте разрешение, которое реально приходит на вход.").grid(
            row=cr, column=0, columnspan=2, sticky="w", pady=(6, 0))

        # NDI
        self.ndi_box = ttk.Frame(f)
        self.ndi_box.columnconfigure(1, weight=1)
        row = ttk.Frame(self.ndi_box)
        row.columnconfigure(0, weight=1)
        self.ndi_cb = ttk.Combobox(row, textvariable=self._var("ndi_source"), width=26)
        self.ndi_cb.grid(row=0, column=0, sticky="ew")
        ttk.Button(row, text="↻", width=3, command=self._refresh_ndi).grid(row=0, column=1, padx=(6, 0))
        self._grid_row(self.ndi_box, 0, "Источник", row)
        self.ndi_info = ttk.Label(self.ndi_box, style="Muted.TLabel", wraplength=340,
                                  text="Нажмите ↻, чтобы найти NDI-источники в сети.")
        self.ndi_info.grid(row=1, column=0, columnspan=2, sticky="w", pady=(6, 0))

        # файл
        self.file_box = ttk.Frame(f)
        self.file_box.columnconfigure(1, weight=1)
        row = ttk.Frame(self.file_box)
        row.columnconfigure(0, weight=1)
        ttk.Entry(row, textvariable=self._var("file_path")).grid(row=0, column=0, sticky="ew")
        ttk.Button(row, text="…", width=3, command=self._browse_file).grid(row=0, column=1, padx=(6, 0))
        self._grid_row(self.file_box, 0, "Файл", row)
        ttk.Checkbutton(self.file_box, text="Зациклить", variable=self._var("file_loop", "bool")).grid(
            row=1, column=0, columnspan=2, sticky="w", pady=4)

        for b in (self.cam_box, self.ndi_box, self.file_box):
            b.grid(row=r, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        r += 1

        ttk.Separator(f).grid(row=r, column=0, columnspan=2, sticky="ew", pady=12); r += 1
        rot = ttk.Combobox(f, textvariable=self._var("rotation", "int"), values=[0, 90, 180, 270],
                           state="readonly", width=8)
        self._grid_row(f, r, "Поворот кадра", rot); r += 1
        ttk.Checkbutton(f, text="Зеркалить (как в селфи)", variable=self._var("mirror", "bool")).grid(
            row=r, column=0, columnspan=2, sticky="w", pady=4); r += 1
        self.src_info = ttk.Label(f, text="", style="Muted.TLabel")
        self.src_info.grid(row=r, column=0, columnspan=2, sticky="w", pady=(10, 0))
        return f

    # --- вкладка «Трекинг»
    def _tab_tracking(self, nb):
        f = self._frame(nb)
        r = 0
        row = ttk.Frame(f)
        row.columnconfigure(0, weight=1)
        self.model_cb = ttk.Combobox(row, state="readonly", width=20)
        self.model_cb.grid(row=0, column=0, sticky="ew")
        self.model_cb.bind("<<ComboboxSelected>>", self._on_model_selected)
        ttk.Button(row, text="Скачать", command=self._download_models).grid(row=0, column=1, padx=(6, 0))
        self._grid_row(f, r, "Модель", row,
                       "lite — самая быстрая, full — баланс, heavy — точнее, но тяжелее."); r += 2
        sp = ttk.Spinbox(f, from_=1, to=4, textvariable=self._var("num_poses", "int"), width=6)
        self._grid_row(f, r, "Людей в кадре (макс.)", sp); r += 1
        pw = ttk.Combobox(f, textvariable=self._var("proc_width", "int"),
                          values=[320, 480, 640, 960, 1280], width=8)
        self._grid_row(f, r, "Ширина анализа, px", pw,
                       "Кадр уменьшается до этой ширины перед трекингом. Меньше — быстрее."); r += 2
        self._slider(f, r, "Порог уверенности", "min_confidence", 0.1, 0.95); r += 1
        self._slider(f, r, "Сглаживание", "smoothing", 0.0, 1.0); r += 1
        self._slider(f, r, "Удержание при потере, с", "hold_seconds", 0.0, 2.0); r += 1
        ttk.Checkbutton(f, text="Пробовать GPU (если не выйдет — CPU)",
                        variable=self._var("use_gpu", "bool")).grid(row=r, column=0, columnspan=2,
                                                                    sticky="w", pady=6); r += 1
        return f

    def _slider(self, f, r, label, key, lo, hi):
        v = self._var(key, "float")
        row = ttk.Frame(f)
        row.columnconfigure(0, weight=1)
        sc = ttk.Scale(row, from_=lo, to=hi, variable=v, orient="horizontal")
        sc.grid(row=0, column=0, sticky="ew")
        val = ttk.Label(row, width=5, anchor="e")
        val.grid(row=0, column=1, padx=(6, 0))

        def upd(*_):
            try:
                val.config(text=f"{v.get():.2f}")
            except tk.TclError:
                pass
        v.trace_add("write", upd)
        upd()
        self._grid_row(f, r, label, row)

    # --- вкладка «OSC»
    def _tab_osc(self, nb):
        f = self._frame(nb)
        r = 0
        ttk.Checkbutton(f, text="Отправлять OSC", variable=self._var("osc_enabled", "bool")).grid(
            row=r, column=0, columnspan=2, sticky="w", pady=4); r += 1
        self._grid_row(f, r, "IP Aximmetry", ttk.Entry(f, textvariable=self._var("osc_ip"))); r += 1
        self._grid_row(f, r, "Порт", ttk.Entry(f, textvariable=self._var("osc_port", "int"), width=8)); r += 1
        self._grid_row(f, r, "Префикс адреса", ttk.Entry(f, textvariable=self._var("osc_prefix"))); r += 1
        self._grid_row(f, r, "Координаты", self._choice(f, "coord_mode", COORD_MODES)); r += 1
        self._grid_row(f, r, "Ось вверх", self._choice(f, "up_axis", UP_AXES)); r += 1
        self._grid_row(f, r, "Точки", self._choice(f, "joint_set", JOINT_SETS)); r += 1
        self._grid_row(f, r, "Масштаб", ttk.Entry(f, textvariable=self._var("scale", "float"), width=8)); r += 1
        off = ttk.Frame(f)
        for i, k in enumerate(("offset_x", "offset_y", "offset_z")):
            ttk.Entry(off, textvariable=self._var(k, "float"), width=7).grid(row=0, column=i, padx=(0, 4))
        self._grid_row(f, r, "Смещение X Y Z", off); r += 1
        for key, text in (("flip_x", "Инвертировать X"),
                          ("send_visibility", "Отправлять видимость точек (…/vis)"),
                          ("send_all_vector", "Все точки одним сообщением (…/all)")):
            ttk.Checkbutton(f, text=text, variable=self._var(key, "bool")).grid(
                row=r, column=0, columnspan=2, sticky="w", pady=3); r += 1
        ttk.Separator(f).grid(row=r, column=0, columnspan=2, sticky="ew", pady=10); r += 1
        help_txt = ("В Aximmetry: Edit → Manage Devices → OSC → Server, порт как здесь.\n"
                    "В графе: модуль OSC Vector, адрес например\n"
                    "  /pglmocap/p1/hip_center\n  /pglmocap/p1/right_wrist\n"
                    "Флаг наличия человека: OSC Scalar /pglmocap/p1/detected")
        ttk.Label(f, text=help_txt, style="Muted.TLabel", justify="left").grid(
            row=r, column=0, columnspan=2, sticky="w")
        return f

    # --- вкладка «Unreal Live Link»
    def _tab_unreal(self, nb):
        f = self._frame(nb)
        r = 0
        ttk.Checkbutton(f, text="Отправлять в Unreal Live Link", variable=self._var("ll_enabled", "bool")).grid(
            row=r, column=0, columnspan=2, sticky="w", pady=4); r += 1
        self._grid_row(f, r, "IP компьютера с Unreal", ttk.Entry(f, textvariable=self._var("ll_ip"))); r += 1
        self._grid_row(f, r, "Порт", ttk.Entry(f, textvariable=self._var("ll_port", "int"), width=8)); r += 1
        self._grid_row(f, r, "Префикс субъектов", ttk.Entry(f, textvariable=self._var("ll_prefix"))); r += 1
        self._grid_row(f, r, "Точки", self._choice(f, "ll_points", LL_POINT_SETS)); r += 1
        self._grid_row(f, r, "Перемещение, см", ttk.Entry(f, textvariable=self._var("ll_root_motion", "float"),
                                                          width=8),
                       "На сколько сантиметров сдвигается человек в Unreal, если в кадре он прошёл "
                       "расстояние, равное высоте кадра. 0 — всегда в центре."); r += 2
        ttk.Separator(f).grid(row=r, column=0, columnspan=2, sticky="ew", pady=10); r += 1
        help_txt = ("В Unreal 5.6: включите плагин PGL Mocap Live Link,\n"
                    "Window → Virtual Production → Live Link →\n"
                    "+ Source → PGL Mocap → порт как здесь → Add.\n\n"
                    "Появятся субъекты:\n"
                    "  PGL_P1            — скелет (Animation)\n"
                    "  PGL_P1_right_wrist — точка (Transform)\n"
                    "  PGL_P1_hip_center  — центр человека\n"
                    "Координаты: см, X вперёд, Y вправо, Z вверх, пол = 0.")
        ttk.Label(f, text=help_txt, style="Muted.TLabel", justify="left").grid(
            row=r, column=0, columnspan=2, sticky="w")
        return f

    # ------------------------------------------------------------------ действия
    def _on_source_type(self):
        t = self.s["source_type"]
        self.cam_box.grid_remove(); self.ndi_box.grid_remove(); self.file_box.grid_remove()
        {"camera": self.cam_box, "ndi": self.ndi_box, "file": self.file_box}[t].grid()
        if t == "ndi" and not self.ndi_cb["values"]:
            self._refresh_ndi()

    def _refresh_cameras(self):
        def work():
            try:
                cams = list_cameras()
            except Exception:
                cams = [(0, "Камера 0")]
            self.root.after(0, lambda: self._set_cams(cams))
        threading.Thread(target=work, daemon=True).start()

    def _set_cams(self, cams):
        self._cams = cams
        self.cam_cb["values"] = [f"{i}: {n}" for i, n in cams]
        idx = next((k for k, (i, _) in enumerate(cams) if i == self.s["camera_index"]), 0)
        if cams:
            self.cam_cb.current(idx)
            self.s["camera_index"] = cams[idx][0]

    def _on_cam_selected(self, _e=None):
        k = self.cam_cb.current()
        if 0 <= k < len(self._cams):
            new = self._cams[k][0]
            if new != self.s["camera_index"]:
                self.s["camera_index"] = new
                if self.engine.running:
                    self._dirty_restart = True

    def _refresh_ndi(self):
        ok, err = ndi_available()
        if not ok:
            self.ndi_info.config(text=f"NDI недоступен: {err}")
            return
        self.ndi_info.config(text="Поиск NDI-источников…")

        def work():
            try:
                names = list_ndi_sources(2.5)
                msg = f"Найдено источников: {len(names)}" if names else \
                    "Источники не найдены. Проверьте сеть и что источник запущен."
            except Exception as e:
                names, msg = [], f"Ошибка поиска NDI: {e}"
            self.root.after(0, lambda: self._set_ndi(names, msg))
        threading.Thread(target=work, daemon=True).start()

    def _set_ndi(self, names, msg):
        self.ndi_cb["values"] = names
        self.ndi_info.config(text=msg)
        if names and self.s["ndi_source"] not in names:
            self.vars["ndi_source"].set(names[0])

    def _browse_file(self):
        p = filedialog.askopenfilename(filetypes=[("Видео", "*.mp4 *.mov *.avi *.mkv *.webm"),
                                                  ("Все файлы", "*.*")])
        if p:
            self.vars["file_path"].set(p)

    def _refresh_models(self):
        avail = available_models()
        self._models = avail
        self.model_cb["values"] = avail or ["(нет моделей)"]
        if avail:
            if self.s["model"] not in avail:
                self.s["model"] = "full" if "full" in avail else avail[0]
            self.model_cb.current(avail.index(self.s["model"]))
        else:
            self.model_cb.current(0)

    def _on_model_selected(self, _e=None):
        k = self.model_cb.current()
        if self._models and 0 <= k < len(self._models):
            self.s["model"] = self._models[k]
            if self.engine.running:
                self._dirty_restart = True

    def _download_models(self):
        dest = settings_dir() / "models"
        dest.mkdir(parents=True, exist_ok=True)
        self.hint_lbl.config(text="Скачивание моделей…")

        def work():
            errs = []
            for k, name in MODEL_FILES.items():
                if (dest / name).exists():
                    continue
                try:
                    urllib.request.urlretrieve(MODEL_URLS[k], dest / (name + ".part"))
                    (dest / (name + ".part")).replace(dest / name)
                except Exception as e:
                    errs.append(f"{k}: {e}")
            msg = "Модели скачаны." if not errs else "Ошибки: " + "; ".join(errs)
            self.root.after(0, lambda: (self.hint_lbl.config(text=msg), self._refresh_models()))
        threading.Thread(target=work, daemon=True).start()

    def _toggle(self):
        if self.engine.running:
            self.engine.stop()
        else:
            if not available_models():
                messagebox.showwarning(APP_NAME, "Нет файлов моделей. Нажмите «Скачать» на вкладке «Трекинг» "
                                                 "или положите .task-файлы в папку models рядом с программой.")
                return
            save_settings(self.s)
            self._dirty_restart = False
            self.engine.start()

    def _tick(self):
        e = self.engine
        running = e.running
        self.start_btn.config(text="■  Стоп" if running else "▶  Старт",
                              style="Stop.TButton" if running else "Start.TButton")
        if running:
            st = f"{e.status}  ·  {e.fps:4.1f} к/с  ·  людей: {e.persons}  ·  OSC: {e.msg_rate:.0f} сообщ./с"
            if self.s.get("ll_enabled"):
                st += f"  ·  Live Link: {e.ll_rate:.0f} к/с"
        else:
            st = e.status
        self.status_lbl.config(text=st, foreground=DANGER if e.error else MUTED)
        self.src_info.config(text=f"Вход: {e.source_info}" if e.source_info and running else "")
        if e.error and not running:
            self.hint_lbl.config(text=f"Ошибка: {e.error}", foreground=DANGER)
        elif self._dirty_restart:
            self.hint_lbl.config(text="Изменения источника/модели вступят в силу после Стоп → Старт.",
                                 foreground=MUTED)
        elif running and e.out_error:
            self.hint_lbl.config(text=f"Ошибка отправки — {e.out_error}", foreground=DANGER)
        elif running:
            self.hint_lbl.config(text="", foreground=MUTED)

        img = e.get_preview()
        if img is not None:
            lw, lh = self.preview.winfo_width(), self.preview.winfo_height()
            h, w = img.shape[:2]
            sc = min(lw / w, lh / h) if lw > 10 and lh > 10 else 1.0
            if abs(sc - 1.0) > 0.02:
                img = cv2.resize(img, (max(1, int(w * sc)), max(1, int(h * sc))), interpolation=cv2.INTER_AREA)
            rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            self._photo = ImageTk.PhotoImage(Image.fromarray(rgb))
            self.preview.config(image=self._photo, text="")
        elif not running and self._photo is not None:
            self._photo = None
            self.preview.config(image="", text="Нажмите «Старт»")
        self.root.after(33, self._tick)

    def _on_close(self):
        save_settings(self.s)
        self.engine.stop()
        self.root.destroy()


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()
