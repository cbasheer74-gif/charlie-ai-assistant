
from __future__ import annotations

import json
import math
import os
import platform
import random
import subprocess
import sys
import threading
import time
from pathlib import Path

from typing import Any, Optional, Tuple

import psutil

if platform.system() == "Windows":
    _WIN_HIDE: dict = {"creationflags": subprocess.CREATE_NO_WINDOW}
else:
    _WIN_HIDE: dict = {}

from PyQt6.QtCore import (
    QEasingCurve, QLineF, QMimeData, QObject, QParallelAnimationGroup, QPointF,
    QPropertyAnimation, QRect, QRectF, QSize, Qt, QTimer, QUrl, pyqtSignal, QByteArray,
)
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtGui import (
    QBrush, QColor, QConicalGradient, QDragEnterEvent, QDropEvent, QFont,
    QFontDatabase, QFontMetrics, QIcon, QKeySequence, QLinearGradient, QPainter, QPainterPath, QPalette,
    QPen, QPixmap, QImage, QRadialGradient, QShortcut, QDesktopServices, QTextDocument,
)
from PyQt6.QtWidgets import (
    QApplication, QComboBox, QDialog, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
    QMainWindow, QMenu, QPushButton, QScrollArea, QSizePolicy, QSplitter,
    QStackedWidget, QSystemTrayIcon, QTextEdit, QVBoxLayout, QWidget, QProgressBar, QInputDialog, QCheckBox,
    QGraphicsDropShadowEffect,
)
Charlie3DAvatar = None
try:
    from core.avatar import HoloAvatar
except Exception:      # pragma: no cover — HUD must never die over cosmetics
    HoloAvatar = None

try:
    from core.digital_human import (
        PhotoRealisticRig, FaceLandmarks, AvatarState as DHState,
        Emotion as DHEmotion, Viseme as DHViseme,
    )
except Exception:      # pragma: no cover
    PhotoRealisticRig = None


def _detect_primary_font() -> str:
    """Resolve the clean modern Inter / Segoe UI typography for the Charlie premium UI."""
    try:
        app = QApplication.instance()
        fams = set(QFontDatabase.families()) if app else set()
        for cand in ["Inter", "Inter Display", "Segoe UI Variable Text", "Segoe UI Variable Display", "Segoe UI"]:
            if cand in fams:
                return cand
    except Exception:
        pass
    if platform.system() == "Windows":
        return "Segoe UI"
    return "sans-serif"


APP_FONT_NAME = _detect_primary_font()


def get_app_font(size: int = 9, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
    f = QFont(APP_FONT_NAME, size, weight)
    f.setFamilies(["Segoe UI Variable Text", "Segoe UI Variable Display", "Segoe UI", "Inter", "sans-serif"])
    f.setStyleHint(QFont.StyleHint.SansSerif)
    f.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    return f


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent


def _resource_dir() -> Path:
    """Bundled read-only assets; config remains beside the executable."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent

from core.app_paths import get_config_dir

BASE_DIR   = _base_dir()
RESOURCE_DIR = _resource_dir()
CONFIG_DIR = get_config_dir()
API_FILE   = CONFIG_DIR / "api_keys.json"
_BUNDLED_API_FILE = (RESOURCE_DIR / "config" / "api_keys.json") if (RESOURCE_DIR / "config" / "api_keys.json").exists() else (BASE_DIR / "config" / "api_keys.json")


def _read_full_config() -> dict:
    """Read api_keys.json config dict. Returns {} on any error."""
    try:
        if not API_FILE.exists() and _BUNDLED_API_FILE.exists() and _BUNDLED_API_FILE.resolve() != API_FILE.resolve():
            data = json.loads(_BUNDLED_API_FILE.read_text(encoding="utf-8"))
        else:
            data = json.loads(API_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if isinstance(data, dict):
        aname = str(data.get("assistant_name") or "").strip()
        if aname.upper() in ("JARVIS", "J.A.R.V.I.S.", "J.A.R.V.I.S") or "JARVIS" in aname.upper():
            data["assistant_name"] = "CHARLIE"
    return data


# Single source of truth for the release name — the window title, the header
# badge and the readme must never disagree again.
APP_VERSION  = "AI Desktop"
APP_PROTOCOL = "Neural"
APP_RELEASE_YEAR = 2026
try:
    from config.version import APP_VERSION as RELEASE_VERSION, BUILD_NUMBER
except Exception:
    RELEASE_VERSION, BUILD_NUMBER = "1.2.4", 109
DEVELOPER_NAME = "Anees Chaudhary"
DEVELOPER_CREDIT = f"Built and designed by {DEVELOPER_NAME} in {APP_RELEASE_YEAR}."

_DEFAULT_W, _DEFAULT_H = 1260, 800
_MIN_W,     _MIN_H     = 1020, 660
_LEFT_W  = 200
_RIGHT_W = 340

_OS = platform.system()  # "Windows" | "Darwin" | "Linux"


class C:
    # ── Reusable Design Tokens — Charlie Premium Palette ──
    BACKGROUND       = "#0B0F17"
    SURFACE          = "#121826"
    SURFACE_ELEVATED = "#192234"
    BORDER           = "#1e2a40"
    BORDER_HEX       = "#1e2a40"
    BORDER_RGBA      = "rgba(255, 255, 255, 0.07)"
    TEXT_PRIMARY     = "#F3F4F6"
    TEXT_SECONDARY   = "#A7B0C0"
    TEXT_MUTED       = "#6B7280"
    BRAND_PRIMARY    = "#6366F1"
    BRAND_SECONDARY  = "#818CF8"
    SUCCESS          = "#22C55E"
    WARNING          = "#F59E0B"
    ERROR            = "#EF4444"

    # Compatibility aliases
    BG        = BACKGROUND
    PANEL     = SURFACE
    PANEL2    = SURFACE_ELEVATED
    BORDER_B  = BRAND_SECONDARY
    BORDER_A  = BRAND_PRIMARY
    PRI       = BRAND_PRIMARY
    PRI_DIM   = "#4f46e5"
    PRI_GHO   = "#1e1b4b"
    ACC       = BRAND_SECONDARY
    ACC2      = "#38bdf8"
    GREEN     = SUCCESS
    GREEN_D   = "#16a34a"
    RED       = ERROR
    MUTED_C   = "#f43f5e"
    TEXT      = TEXT_PRIMARY
    TEXT_DIM  = TEXT_MUTED
    TEXT_MED  = TEXT_SECONDARY
    WHITE     = "#ffffff"
    DARK      = "#060a12"
    BAR_BG    = SURFACE_ELEVATED


# Keys tied to the accent colour — status colours (ACC, GREEN, RED…) stay fixed
_HUE_LINKED = (
    "BG", "PANEL", "PANEL2", "BORDER", "BORDER_B", "BORDER_A",
    "PRI", "PRI_DIM", "PRI_GHO", "TEXT", "TEXT_DIM", "TEXT_MED",
    "WHITE", "DARK", "BAR_BG",
)
_PALETTE_DEFAULTS: dict[str, str] = {k: getattr(C, k) for k in _HUE_LINKED}

DEFAULT_UI_COLOR = _PALETTE_DEFAULTS["PRI"]
DEFAULT_UI_THEME = "glass"
UI_THEMES: dict[str, dict[str, str]] = {
    # 1. Cyber Indigo (Glass Studio Default) — Charlie Premium
    "glass": {
        "BG": "#0B0F17", "PANEL": "#121826", "PANEL2": "#192234",
        "BORDER": "#1e2a40", "BORDER_B": "#818cf8", "BORDER_A": "#6366f1",
        "PRI": "#6366f1", "PRI_DIM": "#4f46e5", "PRI_GHO": "#1e1b4b",
        "TEXT": "#F3F4F6", "TEXT_DIM": "#6B7280", "TEXT_MED": "#A7B0C0",
        "WHITE": "#ffffff", "DARK": "#060a12", "BAR_BG": "#192234",
    },
    # 2. Electric Cyan (High Contrast Vivid Teal)
    "electric_cyan": {
        "BG": "#060d15", "PANEL": "#0a1626", "PANEL2": "#10223b",
        "BORDER": "#163252", "BORDER_B": "#00e5ff", "BORDER_A": "#1e436c",
        "PRI": "#00e5ff", "PRI_DIM": "#0284c7", "PRI_GHO": "#082f49",
        "TEXT": "#f0fdfa", "TEXT_DIM": "#7dd3fc", "TEXT_MED": "#bae6fd",
        "WHITE": "#ffffff", "DARK": "#03080e", "BAR_BG": "#0f2b48",
    },
    # 3. Obsidian Gold (Graphite Executive Luxury)
    "graphite": {
        "BG": "#09090b", "PANEL": "#141416", "PANEL2": "#1c1c20",
        "BORDER": "#2c2820", "BORDER_B": "#f59e0b", "BORDER_A": "#3d372c",
        "PRI": "#f59e0b", "PRI_DIM": "#d97706", "PRI_GHO": "#451a03",
        "TEXT": "#fefce8", "TEXT_DIM": "#d4b886", "TEXT_MED": "#fde68a",
        "WHITE": "#ffffff", "DARK": "#040405", "BAR_BG": "#26231d",
    },
    # 4. Emerald Matrix (Cyber Forest Terminal)
    "emerald_matrix": {
        "BG": "#05120c", "PANEL": "#0a1e14", "PANEL2": "#0f2d1e",
        "BORDER": "#163f2b", "BORDER_B": "#10b981", "BORDER_A": "#1f563b",
        "PRI": "#10b981", "PRI_DIM": "#059669", "PRI_GHO": "#064e3b",
        "TEXT": "#ecfdf5", "TEXT_DIM": "#6ee7b7", "TEXT_MED": "#a7f3d0",
        "WHITE": "#ffffff", "DARK": "#020906", "BAR_BG": "#133827",
    },
    # 5. Crimson Void (Deep Scarlet Contrast)
    "crimson_void": {
        "BG": "#12070a", "PANEL": "#1d0d12", "PANEL2": "#29131a",
        "BORDER": "#3d1a24", "BORDER_B": "#f43f5e", "BORDER_A": "#542331",
        "PRI": "#f43f5e", "PRI_DIM": "#e11d48", "PRI_GHO": "#4c0519",
        "TEXT": "#fff1f2", "TEXT_DIM": "#fda4af", "TEXT_MED": "#fecdd3",
        "WHITE": "#ffffff", "DARK": "#0a0305", "BAR_BG": "#381722",
    },
    # 6. Amethyst Dream (Royal Violet Glow)
    "amethyst": {
        "BG": "#0d0a1a", "PANEL": "#15102a", "PANEL2": "#1e173a",
        "BORDER": "#2e2354", "BORDER_B": "#8b5cf6", "BORDER_A": "#3f3073",
        "PRI": "#8b5cf6", "PRI_DIM": "#7c3aed", "PRI_GHO": "#2e1065",
        "TEXT": "#f5f3ff", "TEXT_DIM": "#c4b5fd", "TEXT_MED": "#ddd6fe",
        "WHITE": "#ffffff", "DARK": "#07050e", "BAR_BG": "#291f4f",
    },
    # 7. Arctic Midnight (Deep Oceanic Blue)
    "midnight": {
        "BG": "#08101e", "PANEL": "#0e1b2f", "PANEL2": "#142742",
        "BORDER": "#1f385c", "BORDER_B": "#38bdf8", "BORDER_A": "#2a4c7c",
        "PRI": "#38bdf8", "PRI_DIM": "#0284c7", "PRI_GHO": "#075985",
        "TEXT": "#f0f9ff", "TEXT_DIM": "#93c5fd", "TEXT_MED": "#bae6fd",
        "WHITE": "#ffffff", "DARK": "#040810", "BAR_BG": "#193254",
    },
    # 8. AMOLED Pure (Pitch Black Zero Emission)
    "amoled": {
        "BG": "#000000", "PANEL": "#09090b", "PANEL2": "#121215",
        "BORDER": "#27272a", "BORDER_B": "#a855f7", "BORDER_A": "#3f3f46",
        "PRI": "#a855f7", "PRI_DIM": "#9333ea", "PRI_GHO": "#24103a",
        "TEXT": "#fafafa", "TEXT_DIM": "#a1a1aa", "TEXT_MED": "#d4d4d8",
        "WHITE": "#ffffff", "DARK": "#000000", "BAR_BG": "#18181b",
    },
}

UI_THEME_LABELS = {
    "glass": "Cyber Indigo (Glass Studio)",
    "electric_cyan": "Electric Cyan (Vivid Teal)",
    "graphite": "Obsidian Gold (Executive Luxury)",
    "emerald_matrix": "Emerald Matrix (Cyber Green)",
    "crimson_void": "Crimson Void (Deep Scarlet)",
    "amethyst": "Amethyst Dream (Royal Violet)",
    "midnight": "Arctic Midnight (Deep Ocean)",
    "amoled": "AMOLED Pure (High Contrast Pitch)",
}

UI_ACCENTS = {
    "Cyber Indigo": "#6366f1",
    "Electric Cyan": "#00e5ff",
    "Royal Violet": "#a78bfa",
    "Aurora Blue": "#38bdf8",
    "Emerald": "#10b981",
    "Radiant Gold": "#f59e0b",
    "Crimson Rose": "#f43f5e",
    "Coral Orange": "#fb923c",
}
_active_theme_base: dict[str, str] = dict(UI_THEMES["glass"])


def normalize_ui_theme(theme: str) -> str:
    value = str(theme or "").strip().lower()
    aliases = {
        "cyber_indigo": "glass",
        "obsidian_gold": "graphite",
        "amethyst_dream": "amethyst",
        "arctic_midnight": "midnight",
        "amoled_pure": "amoled",
    }
    value = aliases.get(value, value)
    return value if value in UI_THEMES else DEFAULT_UI_THEME


def apply_ui_theme(theme: str, accent_hex: str = "") -> str:
    """Apply a complete base theme, then tint it with the selected accent."""
    global _active_theme_base
    selected = normalize_ui_theme(theme)
    _active_theme_base = dict(UI_THEMES[selected])
    for key, value in _active_theme_base.items():
        setattr(C, key, value)
    apply_ui_accent(accent_hex or _active_theme_base["PRI"])
    return selected


def apply_ui_accent(accent_hex: str) -> bool:
    """
    Re-derives the whole teal-family palette from the chosen accent colour
    (hue shift — brightness/saturation ratios are preserved, design stays intact).
    Painted elements (HUD, waveform, metrics) pick up the new colour on the next
    frame; stylesheet-based panels pick it up when they are rebuilt.
    """
    import colorsys

    accent_hex = (accent_hex or "").strip().lower()
    if not (accent_hex.startswith("#") and len(accent_hex) == 7):
        return False
    try:
        int(accent_hex[1:], 16)
    except ValueError:
        return False

    def _hsv(h: str) -> tuple[float, float, float]:
        h = str(h or "").strip()
        if h.startswith("rgba") or h.startswith("rgb"):
            import re
            m = re.findall(r"[\d.]+", h)
            if len(m) >= 3:
                r, g, b = float(m[0]) / 255.0, float(m[1]) / 255.0, float(m[2]) / 255.0
                return colorsys.rgb_to_hsv(max(0.0, min(1.0, r)), max(0.0, min(1.0, g)), max(0.0, min(1.0, b)))
            return (0.0, 0.0, 0.5)
        if h.startswith("#") and len(h) >= 7:
            try:
                r = int(h[1:3], 16) / 255.0
                g = int(h[3:5], 16) / 255.0
                b = int(h[5:7], 16) / 255.0
                return colorsys.rgb_to_hsv(r, g, b)
            except Exception:
                pass
        return (0.0, 0.0, 0.5)

    base_h            = _hsv(_active_theme_base["PRI"])[0]
    acc_h, acc_s, _av = _hsv(accent_hex)
    dh   = acc_h - base_h
    grey = acc_s < 0.08   # near-grey accent → the whole theme is desaturated

    for key, hex0 in _active_theme_base.items():
        if not (isinstance(hex0, str) and hex0.startswith("#") and len(hex0) == 7):
            continue
        h, s, v = _hsv(hex0)
        if grey:
            s *= 0.15
        r, g, b = colorsys.hsv_to_rgb((h + dh) % 1.0, s, v)
        setattr(C, key, "#{:02x}{:02x}{:02x}".format(
            int(r * 255 + 0.5), int(g * 255 + 0.5), int(b * 255 + 0.5)))
    return True


def current_palette() -> dict[str, str]:
    """A snapshot of the accent-linked colours currently on class C."""
    return {k: getattr(C, k) for k in _HUE_LINKED}


def retheme_all_widgets(old: dict[str, str], new: dict[str, str]) -> None:
    """
    LIVE full theme change. Replaces the old palette colours with the new ones
    in EVERY widget's stylesheet across the app and repaints them. This way the
    colour change applies INSTANTLY across the whole interface — panels, buttons,
    borders included — not just the painted elements. No restart needed.
    """
    mapping = {old[k].lower(): new[k].lower()
               for k in old if old[k].lower() != new.get(k, old[k]).lower()}
    if not mapping:
        return
    app = QApplication.instance()
    if app is None:
        return
    for w in QApplication.allWidgets():
        try:
            ss = w.styleSheet()
            if ss:
                s2 = ss
                placeholders = {o: f"__charlie_theme_{i}__"
                                for i, o in enumerate(mapping)}
                for old_colour, marker in placeholders.items():
                    s2 = s2.replace(old_colour, marker)
                for old_colour, marker in placeholders.items():
                    s2 = s2.replace(marker, mapping[old_colour])
                if s2 != ss:
                    w.setStyleSheet(s2)
            w.update()
        except Exception:
            pass


def qcol(h: str, a: int = 255) -> QColor:
    c = QColor(h); c.setAlpha(a); return c


# ── Windows GPU via NVML DLL (no subprocess, no console window) ──────────────
_nvml_lib: Any = None   # cached ctypes DLL
_nvml_ok:  Any = None   # None=untested, True=works, False=unavailable


def _nvml_gpu_windows() -> float:
    """Return NVIDIA GPU utilisation % using nvml.dll directly — zero subprocess."""
    global _nvml_lib, _nvml_ok
    if _nvml_ok is False:
        return -1.0
    try:
        import ctypes

        class _Util(ctypes.Structure):
            _fields_ = [("gpu", ctypes.c_uint), ("memory", ctypes.c_uint)]

        if _nvml_lib is None:
            for dll_name in ("nvml", r"C:\Windows\System32\nvml.dll"):
                try:
                    lib = ctypes.WinDLL(dll_name)
                    lib.nvmlInit_v2()
                    _nvml_lib = lib
                    break
                except Exception:
                    continue

        if _nvml_lib is None:
            try:
                import warnings
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    import pynvml  # type: ignore
                    pynvml.nvmlInit()
                    h = pynvml.nvmlDeviceGetHandleByIndex(0)
                    _nvml_ok = True
                    return float(pynvml.nvmlDeviceGetUtilizationRates(h).gpu)
            except Exception:
                _nvml_ok = False
                return -1.0

        if _nvml_lib is not None:
            dev = ctypes.c_void_p()
            _nvml_lib.nvmlDeviceGetHandleByIndex_v2(0, ctypes.byref(dev))
            util = _Util()
            _nvml_lib.nvmlDeviceGetUtilizationRates(dev, ctypes.byref(util))
            _nvml_ok = True
            return float(util.gpu)
        return -1.0
    except Exception:
        _nvml_ok = False
        return -1.0


class _SysMetrics:
    def __init__(self):
        self.cpu  = 0.0
        self.mem  = 0.0
        self.net  = 0.0   
        self.gpu  = -1.0  
        self.tmp  = -1.0  
        self._lock = threading.Lock()
        self._last_net = psutil.net_io_counters()
        self._last_net_t = time.time()
        self._running = True
        # Probe caches — GPU (NVML) and temperature (WMI) are the expensive
        # queries; initialise their handles once and reuse them instead of
        # rebuilding a connection on every poll.
        self._slow_tick = 0            # gpu/temp refreshed every 3rd cycle
        self._pynvml    = None         # cached pynvml module + device handle
        self._pynvml_h  = None
        self._pynvml_ok = None         # None=untested, False=unavailable here
        self._nv_unix   = None         # cached (lib, dev) for Linux/macOS NVML
        self._wmi_conn  = None         # cached WMI connection (creating one is slow)
        self._wmi_ok    = False        # Disabled by default: ACPI thermal queries cause COM hangs
        t = threading.Thread(target=self._loop, daemon=True)
        t.start()

    def _loop(self):
        while self._running:
            try:
                self._update()
            except Exception:
                pass
            time.sleep(2.0)

    def _update(self):
        cpu = psutil.cpu_percent(interval=None)
        mem = psutil.virtual_memory().percent

        nc  = psutil.net_io_counters()
        now = time.time()
        dt  = now - self._last_net_t
        if dt > 0:
            sent = (nc.bytes_sent - self._last_net.bytes_sent) / dt
            recv = (nc.bytes_recv - self._last_net.bytes_recv) / dt
            net  = (sent + recv) / (1024 * 1024)
        else:
            net = 0.0
        self._last_net   = nc
        self._last_net_t = now

        # GPU and temperature change slowly and are the most expensive probes
        # (NVML / WMI) — refresh them every 3rd cycle (~6 s) instead of every
        # cycle, reusing the previous reading in between.
        self._slow_tick = (self._slow_tick + 1) % 3
        if self._slow_tick == 1:
            gpu = self._get_gpu()
            tmp = self._get_temp()
        else:
            gpu = self.gpu
            tmp = self.tmp

        with self._lock:
            self.cpu = cpu
            self.mem = mem
            self.net = net
            self.gpu = gpu
            self.tmp = tmp

    def _get_gpu(self) -> float:
        # pynvml — subprocess-free; initialise once and reuse the handle.
        # Re-initialising NVML on every poll is slow, so cache it and stop
        # retrying pynvml entirely once it proves unavailable here.
        if self._pynvml_ok is not False:
            try:
                import warnings
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    if self._pynvml_h is None:
                        import pynvml  # type: ignore
                        pynvml.nvmlInit()
                        self._pynvml    = pynvml
                        self._pynvml_h  = pynvml.nvmlDeviceGetHandleByIndex(0)
                        self._pynvml_ok = True
                    if self._pynvml is not None and self._pynvml_h is not None:
                        return float(self._pynvml.nvmlDeviceGetUtilizationRates(self._pynvml_h).gpu)
                    return -1.0
            except Exception:
                self._pynvml_ok = False

        # Windows: nvml.dll via ctypes (already cached in _nvml_gpu_windows)
        if _OS == "Windows":
            return _nvml_gpu_windows()

        # Linux / macOS: libnvidia-ml shared lib via ctypes — init once, reuse
        try:
            import ctypes

            class _Util(ctypes.Structure):
                _fields_ = [("gpu", ctypes.c_uint), ("memory", ctypes.c_uint)]

            if self._nv_unix is None:
                _lib = "libnvidia-ml.so.1" if _OS == "Linux" else "libnvidia-ml.dylib"
                nv = ctypes.CDLL(_lib)
                nv.nvmlInit_v2()
                dev = ctypes.c_void_p()
                nv.nvmlDeviceGetHandleByIndex_v2(0, ctypes.byref(dev))
                self._nv_unix = (nv, dev)

            nv, dev = self._nv_unix
            u = _Util()
            nv.nvmlDeviceGetUtilizationRates(dev, ctypes.byref(u))
            return float(u.gpu)
        except Exception:
            pass

        return -1.0   # N/A — zero subprocess on all platforms

    def _get_temp(self) -> float:
        # psutil — works on Linux; occasionally Windows with driver support
        try:
            temps_fn = getattr(psutil, "sensors_temperatures", None)
            temps = temps_fn() if callable(temps_fn) else {}
            for name in ["coretemp", "k10temp", "cpu_thermal", "acpitz",
                         "cpu-thermal", "zenpower", "it8688"]:
                if name in temps and temps[name]:
                    return temps[name][0].current
            for entries in temps.values():
                if entries:
                    return entries[0].current
        except Exception:
            pass

        # Windows: wmi module (pure Python COM, zero subprocess). Reuse a single
        # connection — building a fresh wmi.WMI() on every poll spins up a COM
        # connection each time and is very slow. Give up after one failure.
        if _OS == "Windows" and self._wmi_ok is not False:
            try:
                try:
                    import pythoncom
                    pythoncom.CoInitialize()
                except Exception:
                    pass
                if self._wmi_conn is None:
                    import wmi  # type: ignore
                    self._wmi_conn = wmi.WMI(namespace="root/wmi")
                tz = self._wmi_conn.MSAcpi_ThermalZoneTemperature()
                if tz:
                    return (tz[0].CurrentTemperature / 10.0) - 273.15
            except Exception:
                self._wmi_ok   = False
                self._wmi_conn = None

                self._wmi_conn = None

        return -1.0   # N/A — zero subprocess on all platforms

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "cpu": self.cpu,
                "mem": self.mem,
                "net": self.net,
                "gpu": self.gpu,
                "tmp": self.tmp,
            }


_metrics = _SysMetrics()

class HudCanvas(QWidget):
    def __init__(self, face_path: str, assistant_name: str = "CHARLIE", parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.setMinimumSize(300, 300)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self.muted    = False
        self.speaking = False
        self.state    = "READY"
        self._assistant_name = assistant_name
        try:
            from memory.config_manager import get_assistant_persona
            self._persona = get_assistant_persona()
        except Exception:
            self._persona = "male"
        self._female_face = QPixmap()
        self._female_face_cache: QPixmap | None = None
        self._female_face_cache_size = 0
        self._female_mouth_open = 0.0
        self._female_mouth_width = 0.0
        self._female_rig = None

        # Which centrepiece to draw: 'core' (default) or 'holo'
        try:
            from memory.config_manager import get_hud_style
            self.hud_style = get_hud_style()
        except Exception:
            self.hud_style = "core"
        if self.hud_style not in ("core", "holo"):
            self.hud_style = "core"

        # The holographic vector avatar that fills the HUD. Falls back to glowing core.
        self._avatar = None
        if self.hud_style == "holo" and HoloAvatar is not None:
            try:
                self._avatar = HoloAvatar()
            except Exception:
                self._avatar = None

        # ── Digital Human rigs neutralized ─────────────────────────────
        self._dh_male: object | None = None
        self._dh_female: object | None = None
        self._dh_last_dt = 0.016
        self._core_phase = 0.0

        self._tick       = 0
        self._scale      = 1.0
        self._tgt_scale  = 1.0
        self._halo       = 55.0
        self._tgt_halo   = 55.0
        self._last_t     = time.time()
        self._step_t     = time.time()
        self._blink      = True
        self._blink_tick = 0

        # Rescaled-face cache: the smooth rescale is expensive, so we keep the
        # last result and only rebuild it when the (quantised) size changes.

        # Static grid-dot layer, pre-rendered once per size/theme into a pixmap
        # so paintEvent blits it in one call instead of thousands of drawPoint()s.
        self._grid_cache: QPixmap | None = None
        self._grid_key = None
        # Repaint throttle counter (idle frames drop to ~20 Hz — see _step()).
        self._paint_tick = 0

        # Live audio reactivity: _live_amp is written from the audio threads
        # (0.0–1.0), _amp_disp is the smoothed value the paint code reads.
        self._live_amp  = 0.0
        self._amp_disp  = 0.0
        # (frames, start_time, hop) posted by the playback thread — see
        # push_visemes(). None means "no schedule; use the plain level".
        self._visemes = None
        self._vis_i = None        # first schedule frame not yet handed to the mouth
        self._base_scale = 1.0    # slow "breathing" target; amp is added per-frame
        self._base_halo  = 55.0

        self._tmr = QTimer(self)
        self._tmr.timeout.connect(self._step)
        self._tmr.start(16)

    def resizeEvent(self, a0):
        super().resizeEvent(a0)
        self._update_avatar_geometry()

    def showEvent(self, a0):
        super().showEvent(a0)
        self._update_avatar_geometry()

    def _update_avatar_geometry(self):
        if self._avatar is not None and isinstance(self._avatar, QWidget):
            self._avatar.hide()

    def set_persona(self, persona: str) -> None:
        """Switch the visual identity immediately; the voice reconnect follows separately."""
        self._persona = "female" if str(persona).strip().lower() == "female" else "male"
        self.update()

    def _get_dh_rig(self) -> Any:
        if self._persona == "female":
            return self._dh_female
        return self._dh_male

    def set_emotion(self, emotion: object, intensity: float = 0.3) -> None:
        # Route to digital-human rig (photorealistic path)
        dh_rig = self._get_dh_rig()
        if dh_rig is not None and hasattr(dh_rig, "set_emotion"):
            try:
                dh_rig.set_emotion(emotion, intensity)
            except Exception:
                pass
        # Route to HoloAvatar wireframe (always-on path)
        try:
            if self._avatar is not None and hasattr(self._avatar, "set_emotion"):
                emo_str = emotion.name.lower() if hasattr(emotion, "name") else str(emotion).lower()
                self._avatar.set_emotion(emo_str, float(intensity))
        except Exception:
            pass

    def classify_and_set_emotion(self, text: str) -> None:
        # Route to digital-human rig (photorealistic path)
        dh_rig = self._get_dh_rig()
        if dh_rig is not None and hasattr(dh_rig, "classify_and_set_emotion"):
            try:
                dh_rig.classify_and_set_emotion(text)
            except Exception:
                pass
        # Mirror emotion to HoloAvatar wireframe via inline keyword scan.
        try:
            if self._avatar is not None and hasattr(self._avatar, "set_emotion"):
                _EKW = {
                    "happy": ("happy", 0.65), "great": ("happy", 0.55),
                    "wonderful": ("happy", 0.70), "love": ("happy", 0.70),
                    "sorry": ("sad", 0.55), "sad": ("sad", 0.60),
                    "error": ("sad", 0.40), "fail": ("sad", 0.45),
                    "angry": ("angry", 0.60), "wrong": ("angry", 0.45),
                    "wow": ("surprised", 0.70), "surprise": ("surprised", 0.65),
                    "think": ("thinking", 0.45), "hmm": ("thinking", 0.50),
                }
                low = (text or "").lower()
                for kw, (emo, wt) in _EKW.items():
                    if kw in low:
                        self._avatar.set_emotion(emo, wt)
                        break
        except Exception:
            pass

    def _paint_digital_human(self, *args, **kwargs) -> None:
        pass

    def _paint_female_face(self, *args, **kwargs) -> None:
        pass

    def trigger_nod(self, amplitude: float = 0.005, duration: float = 0.65) -> None:
        """Trigger an affirmative micro-nod gesture on active digital human rig or HoloAvatar."""
        try:
            dh_rig = self._get_dh_rig()
            if dh_rig is not None and hasattr(dh_rig, "trigger_nod"):
                dh_rig.trigger_nod(amplitude, duration)
            elif self._avatar is not None and hasattr(self._avatar, "glance"):
                self._avatar.glance(0.0, -0.08, hold=duration)
        except Exception:
            pass


    def glance(self, dx: float, dy: float, hold: float = 1.1) -> None:
        """Ask the avatar to look somewhere for a moment (see HoloAvatar.glance)."""
        try:
            if self._avatar is not None:
                self._avatar.glance(dx, dy, hold)
        except Exception:
            pass

    def push_visemes(self, frames, hop: float, at: float) -> None:
        """Thread-safe: hand over a schedule of (level, openness, width) frames.

        The playback thread writes up to 200 ms of audio in one go, so a single
        averaged level would only move the mouth five times a second — enough to
        flap, nowhere near enough to articulate. It instead posts the whole
        slice's worth of 20 ms frames here and `_step()` plays them out against
        the wall clock, in step with the audio going to the speakers.

        `at` is the wall-clock time this batch will *begin to sound*, which the
        caller tracks as a playback cursor. It is not the time of the call, and
        the difference is the whole point: `stream.write` returns once the buffer
        accepts the samples, so consecutive batches are handed over far faster
        than they play. Anchoring each one to "now" made every batch start while
        its predecessor was still sounding, so each schedule replaced the last
        after a couple of frames and the mouth only ever played the opening
        instant of every 200 ms — the reason it did not match the words.

        Successive batches are therefore *appended* into one continuous
        timeline, not swapped in. A paragraph is one schedule; the mouth stops
        falling into a gap at every chunk boundary and having to climb back out.
        """
        try:
            if not frames:
                return
            hop = max(1e-3, float(hop))
            at = float(at)
            new = list(frames)
            cur = self._visemes
            if cur is not None:
                old, t0, ohop = cur
                if abs(ohop - hop) < 1e-6:
                    # Where in the existing timeline does this batch land?
                    i = int(round((at - t0) / hop))
                    if 0 <= i <= len(old) + 1:
                        # Continues (or slightly overlaps) what is already
                        # queued: extend rather than restart. Drop whatever has
                        # already been played so the list cannot grow without
                        # bound over a long reply.
                        merged = old[:i] + new
                        played = int((time.time() - t0) / hop) - 2
                        if played > 60:
                            merged = merged[played:]
                            t0 += played * hop
                            if self._vis_i is not None:
                                self._vis_i = max(0, self._vis_i - played)
                        self._visemes = (merged, t0, hop)
                        return
            self._visemes = (new, at, hop)
            self._vis_i = None
        except Exception:
            pass

    def set_audio_level(self, level: float) -> None:
        """Thread-safe entry point for the audio threads. Stores the louder of
        the incoming level and the current value so brief gaps between chunks
        don't make the waveform stutter; _step() decays it back down."""
        try:
            lv = float(level)
        except (TypeError, ValueError):
            return
        if lv < 0.0:
            lv = 0.0
        elif lv > 1.0:
            lv = 1.0
        if lv > self._live_amp:
            self._live_amp = lv

    def _make_grid(self, W: int, H: int) -> QPixmap:
        """Return a quiet background layer for the conversation surface.

        The earlier dotted grid made the assistant read like a monitoring
        dashboard. Keeping this lightweight cache avoids a visual regression for
        callers while intentionally leaving the workspace uncluttered.
        """
        pm = QPixmap(max(1, W), max(1, H))
        pm.fill(Qt.GlobalColor.transparent)
        return pm

    def _step(self):
        self._tick += 1
        now = time.time()

        # ── Live audio reactivity ────────────────────────────────────────────
        # A viseme schedule, if one is playing, gives both the level and the
        # mouth shape for this exact instant; otherwise fall back to the peak
        # level the audio threads pushed in.
        v_open = v_wide = v_level = None
        v_name = None
        v_seq = None
        sched = self._visemes
        if sched is not None:
            frames, t0, hop = sched
            i = math.floor((now - t0) / hop)
            if 0 <= i < len(frames):
                # Hand over *every* frame since the last tick, not just the one
                # under the cursor. This timer runs at 60 Hz but the paint is
                # throttled and the machine may be busy, so a tick can span two
                # or three 20 ms frames — and a consonant closure is only two
                # frames long. Sampling one and discarding the rest is how the
                # closures between words went missing.
                j = self._vis_i if self._vis_i is not None else i
                v_seq = frames[max(0, j):i + 1]
                self._vis_i = max(j, i + 1)
                cur_f = frames[i]
                v_level, v_open, v_wide = cur_f[0], cur_f[1], cur_f[2]
                v_name = cur_f[3] if len(cur_f) > 3 else None
                if v_seq:
                    peak = max(f[0] for f in v_seq)
                    if peak > self._live_amp:
                        self._live_amp = peak
            elif i >= len(frames):
                self._visemes = None        # schedule spent
                self._vis_i = None

        # Audio threads push peaks into _live_amp; decay it toward silence so
        # gaps between chunks fade out instead of freezing, then smooth it.
        self._live_amp *= 0.86
        self._amp_disp += (self._live_amp - self._amp_disp) * 0.45
        amp = self._amp_disp
        mouth_target = 0.0
        width_target = 0.0
        if self.speaking:
            if v_open is not None:
                is_active = (v_level is not None and v_level > 0.0)
                mouth_target = v_open if is_active else 0.0
                width_target = (v_wide if v_wide is not None else 0.0) if is_active else 0.0
            elif sched is None:
                mouth_target = min(0.65, amp * 1.8)
                width_target = 0.0

        # Fast closures preserve M/B/P and pauses; modest opening smoothing
        # avoids the rubbery bouncing caused by amplified volume alone.
        blend = .85 if mouth_target < self._female_mouth_open else .60
        self._female_mouth_open += (mouth_target - self._female_mouth_open) * blend
        self._female_mouth_width += (width_target - self._female_mouth_width) * .60

        # The avatar animates off the very same smoothed level the waveform
        # uses — one audio source, so the mouth can never drift out of sync.
        dt = now - self._step_t
        self._step_t = now
        self._dh_last_dt = dt
        # Integrated, not derived from absolute time: multiplying wall-clock by
        # a rate that changes with state jumps the rings the instant CHARLIE
        # starts talking. Same lesson the head’s sway taught.
        self._core_phase += min(0.10, max(0.0, dt))

        # ── Feed digital human rig with current viseme + state ────────────
        dh_rig = self._get_dh_rig()
        if dh_rig is not None and DHState is not None:
            _state_map = {
                "LISTENING": DHState.LISTENING,
                "THINKING": DHState.THINKING,
                "PROCESSING": DHState.PROCESSING,
                "SPEAKING": DHState.SPEAKING,
                "SLEEPING": DHState.SLEEPING,
                "STANDBY": DHState.SLEEPING,
                "OFFLINE": DHState.INACTIVE,
            }
            dh_rig.set_state(_state_map.get(self.state, DHState.IDLE))
            if self.speaking:
                if v_level is not None and v_level <= 0.01:
                    dh_rig.set_viseme_blend(0.0, 0.0, 0.0)
                elif v_name is not None and DHViseme is not None and v_level is not None:
                    _v_map = {
                        "REST": DHViseme.REST,
                        "AA": DHViseme.AH,
                        "E": DHViseme.EH,
                        "I": DHViseme.EE,
                        "O": DHViseme.OH,
                        "U": DHViseme.W_OO,
                        "MBP": DHViseme.MBP,
                        "FV": DHViseme.FV,
                        "S": DHViseme.SZ,
                        "L": DHViseme.TD,
                        "TD": DHViseme.TD,
                        "K": DHViseme.KG,
                        "R": DHViseme.R,
                    }
                    m_vis = _v_map.get(v_name)
                    lvl_strength = min(1.0, max(0.40, float(v_level) * 1.5))
                    if m_vis:
                        dh_rig.set_viseme(m_vis, strength=lvl_strength)
                    else:
                        dh_rig.set_viseme_blend(v_open or 0.0, v_wide or 0.0, lvl_strength)
                elif v_open is not None:
                    lvl_strength = min(1.0, max(0.40, (float(v_level) if v_level is not None else 0.5) * 1.5))
                    dh_rig.set_viseme_blend(v_open, v_wide or 0.0, lvl_strength)
                elif amp > 0.01:
                    dh_rig.set_viseme_blend(min(0.65, amp * 1.8), 0.0, min(1.0, max(0.2, amp * 1.5)))
                else:
                    dh_rig.set_viseme_blend(0.0, 0.0, 0.0)
            else:
                if DHViseme is not None:
                    dh_rig.set_viseme(DHViseme.REST, 0.0)
                else:
                    dh_rig.set_viseme_blend(0.0, 0.0, 0.0)

        if self._avatar is not None and self.hud_style == "holo":
            if hasattr(self._avatar, "step"):
                self._avatar.step(dt, amp, speaking=self.speaking,
                                  muted=self.muted, state=self.state,
                                  v_open=v_open, v_wide=v_wide or 0.0,
                                  v_level=v_level, v_seq=v_seq,
                                  v_hop=(sched[2] if sched is not None else 0.02))
        else:
            # Fallback core: slow "breathing" base target, lifted by the level.
            if now - self._last_t > (0.12 if self.speaking else 0.5):
                if self.speaking:
                    self._base_scale = 1.03
                    self._base_halo  = 122.0
                elif self.muted:
                    self._base_scale = random.uniform(0.998, 1.002)
                    self._base_halo  = random.uniform(15, 28)
                else:
                    self._base_scale = random.uniform(1.001, 1.008)
                    self._base_halo  = random.uniform(48, 68)
                self._last_t = now

            if self.muted:
                self._tgt_scale, self._tgt_halo = self._base_scale, self._base_halo
            elif self.speaking:
                self._tgt_scale = self._base_scale + amp * 0.13
                self._tgt_halo  = self._base_halo  + amp * 95.0
            else:
                self._tgt_scale = self._base_scale + amp * 0.06
                self._tgt_halo  = self._base_halo  + amp * 75.0

            sp = 0.38 if self.speaking else (0.30 if amp > 0.02 else 0.15)
            self._scale += (self._tgt_scale - self._scale) * sp
            self._halo  += (self._tgt_halo  - self._halo)  * sp

        self._blink_tick += 1
        if self._blink_tick >= 38:
            self._blink = not self._blink
            self._blink_tick = 0
            _blinked = True
        else:
            _blinked = False

        # Repaint throttling — advancing the animation state above is cheap at
        # 60 Hz, but the paint is heavy. Active (speaking, audio, thinking) runs
        # at ~30 Hz, which is the frame rate animation has used for talking
        # characters forever and is indistinguishable here; idle drops to ~20 Hz
        # so a sleeping HUD stops pinning a CPU core. The visuals stay smooth
        # either way because the animation state keeps stepping at 60 Hz.
        self._paint_tick = (self._paint_tick + 1) % 6
        active = (self.speaking or amp > 0.02
                  or self.state in ("THINKING", "PROCESSING"))
        # Dynamic adaptive timer interval:
        # Active: 16ms (60 FPS responsiveness)
        # Idle visible: 33ms (30 FPS, silent power saving)
        # Minimized / Hidden: 150ms (ultra-low power background sleep)
        on_screen = self._on_screen()
        desired_interval = 16 if (active and on_screen) else (33 if on_screen else 150)
        if self._tmr.interval() != desired_interval:
            self._tmr.setInterval(desired_interval)

        if _blinked or (self._paint_tick % 2 == 0 if active
                        else self._paint_tick % 3 == 0):
            if on_screen:
                self.update()

    def _on_screen(self) -> bool:
        """True only when this canvas can actually be seen by the user."""
        try:
            if not self.isVisible():
                return False
            win = self.window()
            if win is None:
                return False
            return not (win.isMinimized() or win.isHidden())
        except Exception:
            return True      # never let a visibility check stop the HUD drawing

    # ── reactor core ─────────────────────────────────────────────────────────
    # The centrepiece for anyone who did not want a face looking back at them.
    # Built from the same budget as the head — software QPainter, no GPU — and
    # from the same principle: everything on it means something. The rings turn
    # at a rate the state sets, the spectrum ring is the real audio level, and
    # the core brightens with the voice. Nothing here is decoration that moves
    # for its own sake, which is what made the old glowing orb feel dead.

    def _core_colours(self):
        if self.muted:
            return qcol(C.MUTED_C), qcol(C.MUTED_C)
        if self.speaking:
            return qcol(C.PRI), qcol(C.ACC)
        if self.state in ("THINKING", "PROCESSING"):
            return qcol(C.PRI), qcol(C.ACC2)
        if self.state == "LISTENING":
            return qcol(C.PRI), qcol(C.GREEN)
        return qcol(C.PRI), qcol(C.PRI_DIM)

    def _paint_core(self, p: QPainter, cx: float, cy: float, r: float,
                    W: float = 0.0, H: float = 0.0):
        """Draw the reactor at (cx, cy) with outer radius r, using the whole
        canvas (W x H) for the marks that frame it."""
        main, acc = self._core_colours()
        bg = qcol(C.BG)
        amp = self._amp_disp
        t = self._core_phase
        live = (self.speaking or amp > 0.04) and not self.muted

        def blend(col: QColor, a: float) -> QColor:
            """Pre-mix onto the background instead of asking Qt to composite.
            The raster engine's opaque path is several times faster than its
            translucent one, and everything here is a line or an arc."""
            k = max(0.0, min(1.0, a))
            return QColor(int(bg.red()   + (col.red()   - bg.red())   * k),
                          int(bg.green() + (col.green() - bg.green()) * k),
                          int(bg.blue()  + (col.blue()  - bg.blue())  * k))

        p.setBrush(Qt.BrushStyle.NoBrush)

        # 1. The atmosphere. One radial gradient doing what a stack of discs did
        #    badly: a wide, soft body of light that gives the thing presence
        #    before any detail is read. This single element decides whether the
        #    HUD looks vast or looks small, so it is drawn first and drawn big.
        # Concentrated rather than spread: a gradient reaching the outer rim
        # washes the whole disc a flat dim blue and reads as fog. Ending it at
        # two thirds leaves it a body of light with somewhere to fall off to,
        # which is what makes it look lit rather than tinted.
        lift = 1.0 + 0.55 * amp + (0.18 if self.speaking else 0.0)
        p.setPen(Qt.PenStyle.NoPen)
        for gr, a0, a1 in ((r * 0.70, 0.30, 0.0), (r * 0.34, 0.34, 0.0)):
            g = QRadialGradient(cx, cy, gr)
            g.setColorAt(0.00, blend(main, min(0.95, a0 * lift)))
            g.setColorAt(0.45, blend(main, min(0.95, a0 * lift * 0.52)))
            g.setColorAt(0.78, blend(main, min(0.95, a0 * lift * 0.18)))
            g.setColorAt(1.00, blend(main, a1))
            p.setBrush(QBrush(g))
            p.drawEllipse(QRectF(cx - gr, cy - gr, gr * 2, gr * 2))
        p.setBrush(Qt.BrushStyle.NoBrush)

        # 2. Frame marks at the corners of the whole canvas, not of the circle.
        #    They are what set the scale: the eye reads the reactor as filling
        #    the room rather than sitting in the middle of it.
        if W > 40 and H > 40:
            m, arm = min(W, H) * 0.035, min(W, H) * 0.055
            p.setPen(QPen(blend(main, 0.45), 1.4))
            for sx, sy in ((1, 1), (-1, 1), (1, -1), (-1, -1)):
                x = cx + sx * (W / 2 - m)
                y = cy + sy * (H / 2 - m)
                p.drawLine(QLineF(x, y, x - sx * arm, y))
                p.drawLine(QLineF(x, y, x, y - sy * arm))

        # 3. Crosshair across the full canvas, broken around the core so it
        #    frames the reactor rather than crossing it.
        p.setPen(QPen(blend(main, 0.16), 1))
        gap = r * 0.62
        if W > 40:
            p.drawLine(QLineF(cx - W / 2, cy, cx - gap, cy))
            p.drawLine(QLineF(cx + gap, cy, cx + W / 2, cy))
        if H > 40:
            p.drawLine(QLineF(cx, cy - H / 2, cx, cy - gap))
            p.drawLine(QLineF(cx, cy + gap, cx, cy + H / 2))

        # 4. Two thin outer circles. Sparse on purpose — a dense ring reads as a
        #    grey band at this size, and restraint is what made the original
        #    look expensive.
        for rr, a, w in ((1.00, 0.40, 1.8), (0.96, 0.18, 1.0), (0.91, 0.32, 1.4)):
            rad = r * rr
            p.setPen(QPen(blend(main, a), w))
            p.drawEllipse(QRectF(cx - rad, cy - rad, rad * 2, rad * 2))

        # 5. Long, sparse graduations: 24 majors reaching well in from the rim,
        #    with shorter minors between them.
        major, minor = [], []
        for i in range(72):
            a = math.radians(i * 5.0)
            ca, sa = math.cos(a), math.sin(a)
            if i % 3 == 0:
                major.append(QLineF(cx + ca * r * 0.885, cy + sa * r * 0.885,
                                    cx + ca * r * 0.985, cy + sa * r * 0.985))
            else:
                minor.append(QLineF(cx + ca * r * 0.945, cy + sa * r * 0.945,
                                    cx + ca * r * 0.985, cy + sa * r * 0.985))
        p.setPen(QPen(blend(main, 0.42), 1.3))
        for line in major:
            p.drawLine(line)
        p.setPen(QPen(blend(main, 0.18), 1))
        for line in minor:
            p.drawLine(line)

        # 6. Sweeping arcs. Long spans, not dashes — the original's grandeur
        #    came from a few big strokes. Speed is the state: idle drifts,
        #    thinking hurries, speaking runs.
        rate = 1.0 + (1.9 if self.state in ("THINKING", "PROCESSING") else 0.0) \
                   + (1.2 if self.speaking else 0.0)
        for k, (rr, span, count, dirn, col, a, wid) in enumerate((
                (0.955, 118, 2, +1, acc,  0.75, 2.0),
                (0.845, 82,  3, -1, main, 0.38, 1.3),
                (0.760, 150, 1, +1, acc,  0.45, 1.6),
                (0.660, 64,  4, -1, main, 0.26, 1.1),
                (0.545, 128, 2, +1, main, 0.30, 1.2))):
            rad = r * rr
            p.setPen(QPen(blend(col, a), wid))
            box = QRectF(cx - rad, cy - rad, rad * 2, rad * 2)
            base = (t * rate * (9 + k * 6) * dirn) % 360.0
            for sgm in range(count):
                p.drawArc(box, int((base + sgm * (360.0 / count)) * 16),
                          int(span * 16))

        # 7. The voice, as a ring of graduations that grow with it. Kept out at
        #    a wide radius so it never crowds the middle.
        n = 60
        ring = r * 0.415
        spikes = []
        for i in range(n):
            a = math.radians(i * (360.0 / n))
            ca, sa = math.cos(a), math.sin(a)
            wob = 0.5 + 0.5 * math.sin(t * 2.3 + i * 0.42)
            idle = 0.018 + 0.012 * math.sin(t * 1.2 + i * 0.7)
            h = r * (idle + (amp * 0.20 * wob if live else 0.0))
            spikes.append(QLineF(cx + ca * ring, cy + sa * ring,
                                 cx + ca * (ring + h), cy + sa * (ring + h)))
        p.setPen(QPen(blend(acc if live else main, 0.25 + 0.5 * amp), 1.6))
        for line in spikes:
            p.drawLine(line)

        # 8. The inner ring the name sits in.
        inner = r * 0.355
        p.setPen(QPen(blend(acc, 0.30 + 0.45 * amp), 1.5))
        p.drawEllipse(QRectF(cx - inner, cy - inner, inner * 2, inner * 2))

        # 9. The name, sized from the string rather than from the radius alone:
        #    "J.A.R.V.I.S" and a name someone renamed to "MAX" are very
        #    different widths, and a fixed fraction of r spills one of them past
        #    the ring it is supposed to sit inside.
        name = self._assistant_name or ""
        if name:
            space = max(1.0, r * 0.018)
            fsz = max(8, int(min(r * 0.105,
                                 (inner * 1.75) / max(1, len(name)) * 1.6 - space)))
            f = QFont(APP_FONT_NAME, fsz, QFont.Weight.Bold)
            f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, space)
            p.setFont(f)
            p.setPen(QPen(blend(qcol(C.WHITE), 0.6 + 0.4 * min(1.0, amp * 2)), 1))
            p.drawText(QRectF(cx - r, cy - fsz, r * 2, fsz * 2),
                       Qt.AlignmentFlag.AlignCenter, name)

    def _paint_assistant_card(self, p: QPainter, cx: float, cy: float,
                              W: float, H: float) -> None:
        """A calm fallback visual for people who prefer an assistant, not a HUD."""
        main, accent = self._core_colours()
        amp = self._amp_disp
        card_w = min(max(260.0, W * 0.72), 610.0)
        card_h = min(max(190.0, H * 0.66), 340.0)
        card = QRectF(cx - card_w / 2, cy - card_h / 2, card_w, card_h)

        p.setPen(QPen(qcol(C.BORDER), 1))
        p.setBrush(QBrush(qcol(C.PANEL)))
        p.drawRoundedRect(card, 22, 22)

        orb_r = min(card_h * 0.23, 68.0) * (1.0 + amp * 0.08)
        orb_y = cy - card_h * 0.09
        glow = QRadialGradient(cx, orb_y, orb_r * 1.7)
        glow.setColorAt(0.0, qcol(C.PRI, 80))
        glow.setColorAt(0.55, qcol(C.PRI, 20))
        glow.setColorAt(1.0, qcol(C.PANEL, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(glow))
        p.drawEllipse(QRectF(cx - orb_r * 1.7, orb_y - orb_r * 1.7,
                             orb_r * 3.4, orb_r * 3.4))

        orb = QRadialGradient(cx - orb_r * 0.23, orb_y - orb_r * 0.28,
                              orb_r * 1.25)
        orb.setColorAt(0.0, qcol(C.WHITE))
        orb.setColorAt(0.24, main)
        orb.setColorAt(1.0, qcol(C.PRI_DIM))
        p.setBrush(QBrush(orb))
        p.setPen(QPen(accent, 2))
        p.drawEllipse(QRectF(cx - orb_r, orb_y - orb_r, orb_r * 2, orb_r * 2))

        initials = (self._assistant_name or "C").strip()[:1].upper()
        p.setFont(QFont(APP_FONT_NAME, max(22, int(orb_r * 0.65)), QFont.Weight.DemiBold))
        p.setPen(QPen(qcol(C.WHITE), 1))
        p.drawText(QRectF(cx - orb_r, orb_y - orb_r, orb_r * 2, orb_r * 2),
                   Qt.AlignmentFlag.AlignCenter, initials)

        name = self._assistant_name or "Charlie"
        p.setFont(QFont(APP_FONT_NAME, 20, QFont.Weight.DemiBold))
        p.setPen(QPen(qcol(C.WHITE), 1))
        p.drawText(QRectF(card.left() + 20, cy + card_h * 0.18, card_w - 40, 30),
                   Qt.AlignmentFlag.AlignHCenter, name)
        copy = {
            "LISTENING": "I'm listening. Tell me what you need.",
            "SPEAKING": "I'm responding.",
            "THINKING": "I'm working on that.",
            "PROCESSING": "I'm taking care of it.",
            "MUTED": "Your microphone is muted.",
        }.get(self.state, "Getting things ready.")
        p.setFont(QFont(APP_FONT_NAME, 10))
        p.setPen(QPen(qcol(C.TEXT_MED), 1))
        p.drawText(QRectF(card.left() + 20, cy + card_h * 0.18 + 36, card_w - 40, 24),
                   Qt.AlignmentFlag.AlignHCenter, copy)

    def paintEvent(self, a0):
        p = QPainter(self)
        if not p.isActive():      # device not ready (e.g. 0-size during layout) — skip cleanly
            return
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), qcol(C.BG))

        W, H = self.width(), self.height()
        cx, cy = W / 2, H / 2
        fw = min(W, H)

        # grid dots — blitted from a cached layer; rebuilt only when the size
        # or the theme's ghost colour changes (so live re-theming still works).
        _gkey = (W, H, C.PRI_GHO)
        if self._grid_cache is None or self._grid_key != _gkey:
            self._grid_cache = self._make_grid(W, H)
            self._grid_key   = _gkey
        p.drawPixmap(0, 0, self._grid_cache)

        # ── holographic head / digital human ────────────────────────────────
        # Sized to the band between the top of the canvas and the status line,
        # capped by width, so it fills the HUD at any window size — including
        # fullscreen — without ever colliding with the status text below.
        _sy_status = cy + fw * 0.40
        if self.hud_style == "holo" and self._avatar is not None and hasattr(self._avatar, "paint"):
            if isinstance(self._avatar, QWidget):
                self._avatar.hide()
            _band_t = 12.0
            _band_h = max(60.0, _sy_status - 12.0 - _band_t)
            span = getattr(self._avatar, 'SPAN', 1.0)
            _r_head = min(fw * 0.355, _band_h / (span + 0.08))
            _head_cy = _band_t + (_band_h - span * _r_head) / 2.0 + _r_head

            if self.muted:
                _main = _acc = qcol(C.MUTED_C)
            else:
                _main = qcol(C.PRI)
                if self.speaking:
                    _acc = qcol(C.ACC)
                elif self.state in ("THINKING", "PROCESSING"):
                    _acc = qcol(C.ACC2)
                elif self.state == "LISTENING":
                    _acc = qcol(C.GREEN)
                else:
                    _acc = qcol(C.PRI)

            self._avatar.paint(p, cx, _head_cy, _r_head, _main, _acc, qcol(C.BG))
        else:
            if isinstance(self._avatar, QWidget):
                self._avatar.hide()
            _band_t = 12.0
            _band_h = max(60.0, _sy_status - 12.0 - _band_t)
            _r = min(W * 0.46, _band_h / 2.0)
            self._paint_core(p, cx, _band_t + _band_h / 2.0, _r, W, _band_h)

        # ── Status Badge & Waveform Layout ────────────────────────────────────
        badge_h = 26.0
        wave_h = 32.0
        gap = 12.0
        total_footer_h = badge_h + gap + wave_h

        # Position status pill gracefully below avatar/core with guaranteed bounds
        sy = min(_sy_status, H - total_footer_h - 14.0)
        sy = max(cy + fw * 0.28, sy)
        wy = sy + badge_h + gap + (wave_h / 2.0)

        # Status definition
        if self.muted:
            status_text = "MUTED"
            state_col = qcol(C.MUTED_C)
            dot_col = qcol(C.MUTED_C)
        elif self.speaking:
            status_text = "SPEAKING"
            state_col = qcol(C.ACC)
            dot_col = qcol(C.ACC)
        elif self.state == "THINKING":
            status_text = "THINKING"
            state_col = qcol(C.ACC2)
            dot_col = qcol(C.ACC2)
        elif self.state == "PROCESSING":
            status_text = "PROCESSING"
            state_col = qcol(C.ACC2)
            dot_col = qcol(C.ACC2)
        elif self.state == "LISTENING":
            status_text = "LISTENING"
            state_col = qcol(C.GREEN)
            dot_col = qcol(C.GREEN)
        elif self.state == "READY":
            status_text = "READY"
            state_col = qcol(C.GREEN)
            dot_col = qcol(C.GREEN)
        elif self.state in ("INITIALIZING", "INITIALISING"):
            status_text = "READY"
            state_col = qcol(C.GREEN)
            dot_col = qcol(C.GREEN)
        else:
            status_text = str(self.state).upper()
            state_col = qcol(C.PRI)
            dot_col = qcol(C.PRI)

        # ── 1. Sleek Frosted Status Pill Badge ──
        _sf = QFont(APP_FONT_NAME, 9, QFont.Weight.Bold)
        _sf.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.8)
        p.setFont(_sf)

        fm = QFontMetrics(_sf)
        text_w = fm.horizontalAdvance(status_text)
        pill_w = text_w + 40.0
        pill_h = badge_h
        pill_x = cx - pill_w / 2.0
        pill_y = sy
        pill_rect = QRectF(pill_x, pill_y, pill_w, pill_h)

        # Pill glass background with state-tinted border
        pill_bg = QColor(state_col.red(), state_col.green(), state_col.blue(), 20)
        pill_border = QColor(state_col.red(), state_col.green(), state_col.blue(), 60)
        p.setPen(QPen(pill_border, 1.0))
        p.setBrush(QBrush(pill_bg))
        p.drawRoundedRect(pill_rect, 13.0, 13.0)

        # Status animated indicator dot
        dot_cx = pill_x + 15.0
        dot_cy = pill_y + pill_h / 2.0

        if self.muted:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(state_col))
            p.drawEllipse(QPointF(dot_cx, dot_cy), 3.5, 3.5)
            # Crisp diagonal slash through dot
            p.setPen(QPen(qcol(C.BG), 1.2))
            p.drawLine(QPointF(dot_cx - 2.5, dot_cy + 2.5), QPointF(dot_cx + 2.5, dot_cy - 2.5))
        else:
            # Luminous pulsing outer halo
            pulse = 0.5 + 0.5 * math.sin(self._tick * 0.16)
            glow_a = int(35 + 50 * pulse) if (self.state == "LISTENING" or self.speaking) else 25
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(QColor(dot_col.red(), dot_col.green(), dot_col.blue(), glow_a)))
            p.drawEllipse(QPointF(dot_cx, dot_cy), 5.5, 5.5)

            # Solid center dot
            p.setBrush(QBrush(dot_col))
            p.drawEllipse(QPointF(dot_cx, dot_cy), 3.0, 3.0)

        # Text inside pill
        p.setPen(QPen(QColor("#f8fafc"), 1))
        text_rect = QRectF(dot_cx + 8.0, pill_y, text_w + 10.0, pill_h)
        p.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, status_text)

        # ── 2. Professional Dynamic Waveform Visualizer ──
        amp = self._amp_disp

        if self.muted:
            # Clean minimalist muted horizon track
            track_w = min(280.0, W * 0.55)
            track_x = cx - track_w / 2.0
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(QColor(state_col.red(), state_col.green(), state_col.blue(), 25)))
            p.drawRoundedRect(QRectF(track_x, wy - 1.5, track_w, 3.0), 1.5, 1.5)

            # Centered accent indicator
            accent_w = 46.0
            p.setBrush(QBrush(QColor(state_col.red(), state_col.green(), state_col.blue(), 140)))
            p.drawRoundedRect(QRectF(cx - accent_w / 2.0, wy - 1.5, accent_w, 3.0), 1.5, 1.5)
        else:
            # Symmetrical equalizer capsule bars
            N = 40
            bw = 4.0
            gap = 3.5
            pitch = bw + gap
            total_wave_w = N * pitch - gap
            wx0 = cx - total_wave_w / 2.0
            mid = (N - 1) / 2.0

            # Ambient radial glow behind active waveform
            if amp > 0.04:
                glow_r = total_wave_w * 0.42
                rad_glow = QRadialGradient(cx, wy, glow_r)
                rad_glow.setColorAt(0.0, QColor(state_col.red(), state_col.green(), state_col.blue(), int(min(65, amp * 110))))
                rad_glow.setColorAt(1.0, QColor(state_col.red(), state_col.green(), state_col.blue(), 0))
                p.setBrush(QBrush(rad_glow))
                p.setPen(Qt.PenStyle.NoPen)
                p.drawEllipse(QRectF(cx - glow_r, wy - 20.0, glow_r * 2.0, 40.0))

            p.setPen(Qt.PenStyle.NoPen)
            for i in range(N):
                dist_ratio = abs(i - mid) / mid
                env = math.cos(dist_ratio * (math.pi / 2.0)) ** 1.3
                w1 = math.sin(self._tick * 0.15 + i * 0.28)
                shimmer = 0.65 + 0.35 * w1
                idle_ripple = 3.0 + 2.2 * math.sin(self._tick * 0.08 + i * 0.32) * env

                hgt = idle_ripple + amp * 34.0 * env * shimmer
                hgt = max(3.5, min(36.0, hgt))

                bar_x = wx0 + i * pitch
                bar_y = wy - hgt / 2.0
                bar_rect = QRectF(bar_x, bar_y, bw, hgt)

                grad = QLinearGradient(bar_x, bar_y, bar_x, bar_y + hgt)
                if amp > 0.04:
                    grad.setColorAt(0.0, QColor("#38bdf8"))
                    grad.setColorAt(0.5, QColor("#818cf8"))
                    grad.setColorAt(1.0, QColor("#3b82f6"))
                else:
                    grad.setColorAt(0.0, QColor(56, 189, 248, 210))
                    grad.setColorAt(0.5, QColor(99, 102, 241, 190))
                    grad.setColorAt(1.0, QColor(59, 130, 246, 160))

                p.setBrush(QBrush(grad))
                p.drawRoundedRect(bar_rect, bw / 2.0, bw / 2.0)

        p.end()   # end deterministically so the backing store never flushes an active painter

class MetricBar(QWidget):

    def __init__(self, label: str, color: str = C.PRI, parent=None):
        super().__init__(parent)
        self._label = label
        self._color = color
        self._value = 0.0       # 0–100
        self._text  = "--"
        self.setFixedHeight(38)
        self.setMinimumWidth(80)

    def set_value(self, pct: float, text: str):
        v = max(0.0, min(100.0, pct))
        if v == self._value and text == self._text:
            return          # unchanged — skip the repaint
        self._value = v
        self._text  = text
        self.update()

    def paintEvent(self, a0):
        p = QPainter(self)
        if not p.isActive():
            return
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()

        p.setBrush(QBrush(qcol(C.PANEL2)))
        p.setPen(QPen(qcol(C.BORDER_A), 1))
        p.drawRoundedRect(QRectF(1, 1, W - 2, H - 2), 4, 4)

        bar_h   = 4
        bar_y   = H - bar_h - 5
        bar_w   = W - 12
        bar_x   = 6
        fill_w  = int(bar_w * self._value / 100)

        p.setBrush(QBrush(qcol(C.BAR_BG)))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(QRectF(bar_x, bar_y, bar_w, bar_h), 2, 2)

        if self._value > 85:
            bar_col = qcol(C.RED)
        elif self._value > 65:
            bar_col = qcol(C.ACC)
        else:
            bar_col = qcol(self._color)

        if fill_w > 0:
            p.setBrush(QBrush(bar_col))
            p.drawRoundedRect(QRectF(bar_x, bar_y, fill_w, bar_h), 2, 2)

        p.setFont(QFont(APP_FONT_NAME, 7, QFont.Weight.Bold))
        p.setPen(QPen(qcol(C.TEXT_DIM), 1))
        p.drawText(QRectF(8, 5, 50, 14), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self._label)

        p.setFont(QFont(APP_FONT_NAME, 9, QFont.Weight.Bold))
        p.setPen(QPen(bar_col if self._text != "--" else qcol(C.TEXT_DIM), 1))
        p.drawText(QRectF(0, 4, W - 6, 16), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, self._text)

        p.end()

class ChatWorkspace(QWidget):
    """Purpose-built centre canvas shown while the text-only AI chat is active."""

    prompt_selected = pyqtSignal(str)
    new_chat_requested = pyqtSignal()
    dictation_requested = pyqtSignal()

    def __init__(self, assistant_name: str, parent=None):
        super().__init__(parent)
        self._assistant_name = assistant_name or "CHARLIE"
        self.setObjectName("ChatWorkspace")
        self.setStyleSheet(f"""
            QWidget#ChatWorkspace {{ background: {C.BG}; }}
            QFrame#ChatHero {{
                background: {C.PANEL}; border: 1px solid {C.BORDER};
                border-radius: 18px;
            }}
            QFrame#ChatStatus {{
                background: {C.PANEL2}; border: 1px solid {C.BORDER};
                border-radius: 10px;
            }}
            QPushButton#ChatPrompt {{
                background: {C.PANEL2}; color: {C.TEXT};
                border: 1px solid {C.BORDER}; border-radius: 12px;
                padding: 14px 16px; text-align: left;
            }}
            QPushButton#ChatPrompt:hover {{
                background: {C.PRI_GHO}; color: {C.WHITE};
                border-color: {C.PRI_DIM};
            }}
            QPushButton#ChatNew {{
                background: transparent; color: {C.PRI};
                border: 1px solid {C.BORDER_B}; border-radius: 9px;
                padding: 7px 14px;
            }}
            QPushButton#ChatNew:hover {{ background: {C.PRI_GHO}; color: {C.WHITE}; }}
            QFrame#ChatRail {{
                background: {C.PANEL}; border: 1px solid {C.BORDER};
                border-radius: 16px;
            }}
            QPushButton#ChatTool {{
                background: {C.PANEL2}; color: {C.TEXT};
                border: 1px solid {C.BORDER}; border-radius: 9px;
                padding: 10px 12px; text-align: left;
            }}
            QPushButton#ChatTool:hover {{ border-color: {C.PRI}; color: {C.WHITE}; }}
            QPushButton#ChatSpeak {{
                background: {C.PRI}; color: {C.DARK}; border: 1px solid {C.PRI};
                border-radius: 9px; padding: 10px 12px; text-align: left;
            }}
            QPushButton#ChatSpeak:checked {{
                background: {C.MUTED_C}; color: {C.WHITE}; border-color: {C.MUTED_C};
            }}
        """)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(42, 30, 42, 30)
        outer.addStretch(1)

        hero = QFrame()
        hero.setObjectName("ChatHero")
        hero.setMaximumWidth(820)
        hero.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        layout = QVBoxLayout(hero)
        layout.setContentsMargins(34, 30, 34, 28)
        layout.setSpacing(14)

        top = QHBoxLayout()
        brand = QLabel(f"{self._assistant_name.upper()}  /  AI CHAT")
        brand.setFont(QFont(APP_FONT_NAME, 9, QFont.Weight.DemiBold))
        brand.setStyleSheet(
            f"color: {C.PRI}; background: {C.PRI_GHO}; border: 1px solid {C.BORDER_B};"
            "border-radius: 8px; padding: 5px 10px; letter-spacing: 1px;")
        top.addWidget(brand)
        top.addStretch()
        new_btn = QPushButton("Start new chat")
        new_btn.setObjectName("ChatNew")
        new_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        new_btn.clicked.connect(self.new_chat_requested.emit)
        top.addWidget(new_btn)
        layout.addLayout(top)

        self._title = QLabel("What can I help you solve?")
        self._title.setFont(QFont(APP_FONT_NAME, 25, QFont.Weight.Bold))
        self._title.setStyleSheet(f"color: {C.WHITE}; background: transparent;")
        self._title.setWordWrap(True)
        layout.addWidget(self._title)

        self._subtitle = QLabel(
            "Ask a difficult question, build something, review an idea, or attach a file. "
            "CHARLIE keeps the context and gives a complete text answer.")
        self._subtitle.setFont(QFont(APP_FONT_NAME, 11))
        self._subtitle.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent;")
        self._subtitle.setWordWrap(True)
        layout.addWidget(self._subtitle)

        status = QFrame()
        status.setObjectName("ChatStatus")
        status_row = QHBoxLayout(status)
        status_row.setContentsMargins(14, 9, 14, 9)
        status_row.setSpacing(18)
        for text in ("Reasoning online", "Conversation memory", "File context ready"):
            label = QLabel(text)
            label.setFont(QFont(APP_FONT_NAME, 9, QFont.Weight.Medium))
            label.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent; border: none;")
            status_row.addWidget(label)
        status_row.addStretch()
        self._status = QLabel("Ready")
        self._status.setFont(QFont(APP_FONT_NAME, 9, QFont.Weight.DemiBold))
        self._status.setStyleSheet(f"color: {C.GREEN}; background: transparent; border: none;")
        status_row.addWidget(self._status)
        layout.addWidget(status)

        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(10)
        prompts = (
            ("Solve a complex problem\nBreak it into clear, practical steps",
             "Help me solve this problem step by step: "),
            ("Build or debug code\nArchitecture, implementation and tests",
             "Help me build or debug this code: "),
            ("Plan a project\nTurn an idea into an actionable roadmap",
             "Create a practical plan for: "),
            ("Explain anything\nTeach it clearly at the right level",
             "Explain this clearly with an example: "),
        )
        for index, (label, prompt) in enumerate(prompts):
            button = QPushButton(label)
            button.setObjectName("ChatPrompt")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setMinimumHeight(72)
            button.setFont(QFont(APP_FONT_NAME, 10, QFont.Weight.Medium))
            button.clicked.connect(lambda _=False, value=prompt: self.prompt_selected.emit(value))
            grid.addWidget(button, index // 2, index % 2)
        layout.addLayout(grid)

        hint = QLabel("Type in the message box on the right. Shift to Voice anytime without losing this chat.")
        hint.setFont(QFont(APP_FONT_NAME, 9))
        hint.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setWordWrap(True)
        layout.addWidget(hint)

        centred = QHBoxLayout()
        centred.setSpacing(14)
        centred.addStretch(1)

        rail = QFrame()
        rail.setObjectName("ChatRail")
        rail.setFixedWidth(210)
        rail_layout = QVBoxLayout(rail)
        rail_layout.setContentsMargins(16, 18, 16, 18)
        rail_layout.setSpacing(10)
        rail_title = QLabel("AI WORKSPACE")
        rail_title.setFont(QFont(APP_FONT_NAME, 9, QFont.Weight.Bold))
        rail_title.setStyleSheet(f"color: {C.PRI}; background: transparent; border: none;")
        rail_layout.addWidget(rail_title)
        rail_subtitle = QLabel("Work faster with focused tools")
        rail_subtitle.setWordWrap(True)
        rail_subtitle.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent; border: none;")
        rail_layout.addWidget(rail_subtitle)

        self._speak_btn = QPushButton("Speak to type\nOne phrase at a time")
        self._speak_btn.setObjectName("ChatSpeak")
        self._speak_btn.setCheckable(True)
        self._speak_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._speak_btn.clicked.connect(self.dictation_requested.emit)
        rail_layout.addWidget(self._speak_btn)

        tools = (
            ("Deep research", "Research this thoroughly and give me a source-aware answer: "),
            ("Code copilot", "Act as a senior engineer and help me implement: "),
            ("Summarise file", "Summarise the attached file with key decisions and action items."),
            ("Create action plan", "Turn this goal into a prioritised action plan: "),
        )
        for label, prompt in tools:
            button = QPushButton(label)
            button.setObjectName("ChatTool")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _=False, value=prompt: self.prompt_selected.emit(value))
            rail_layout.addWidget(button)
        rail_layout.addStretch(1)
        privacy = QLabel("Private mode routing\nVoice and chat never listen together")
        privacy.setWordWrap(True)
        privacy.setStyleSheet(f"color: {C.GREEN}; background: transparent; border: none;")
        rail_layout.addWidget(privacy)
        centred.addWidget(rail)
        centred.addWidget(hero, stretch=8)
        centred.addStretch(1)
        outer.addLayout(centred)
        outer.addStretch(1)

    def set_busy(self, busy: bool) -> None:
        self._status.setText("Thinking" if busy else "Ready")
        self._status.setStyleSheet(
            f"color: {C.ACC2 if busy else C.GREEN}; background: transparent; border: none;")
        self._title.setText(
            "Working through your request..." if busy else "What can I help you solve?")

    def set_dictating(self, active: bool) -> None:
        self._speak_btn.setChecked(bool(active))
        self._speak_btn.setText(
            "Stop listening\nTap when you are done" if active
            else "Speak to type\nOne phrase at a time")


INTELLIGENCE_FEATURES = (
    ("Voice Notes", "Long-form capture, summaries and action items",
     "Start a local voice note. Capture what I say until I say stop, then produce structured notes, a summary and action items."),
    ("Screen Awareness", "Analyse the visible app with permission",
     "Use privacy-aware Vision Copilot to capture my current screen once and help me understand or fix what is visible."),
    ("Command Bar", "Ctrl+Space from any application",
     "Explain that the universal Ctrl+Space command bar is active and give me three useful command examples."),
    ("Workflow Builder", "Create repeatable scheduled automations",
     "Help me build a safe repeatable workflow. Ask what should trigger it, which steps it needs and what confirmation is required."),
    ("Knowledge Vault", "Search private documents and notes",
     "Open my private Knowledge Vault. List saved documents and ask whether I want to add a file or ask a question."),
    ("Agent Workspace", "Research, code, write and plan together",
     "Start an agent workspace. Ask for my outcome, then coordinate research, coding, writing and planning specialists into one answer."),
    ("Live Translation", "Hindi, English and Hinglish conversations",
     "Start live translation mode. Ask me for source and target languages, then translate each phrase naturally until I say stop."),
    ("Meeting Intelligence", "Minutes, decisions and follow-up tasks",
     "Start a meeting capture with local transcript, decisions and action items. Ask me for the meeting title first."),
    ("Smart Notifications", "Important alerts without notification noise",
     "Configure smart notifications. Ask which email, deadline, weather and calendar alerts matter and define quiet hours."),
    ("Privacy Dashboard", "See and control microphone, camera and memory",
     "Show my privacy summary, including microphone, camera, local memory and cloud routing. Offer safe controls and ask before deleting data."),
    ("Offline Survival", "Local chat, files and commands without internet",
     "Show offline capability status and explain which local chat, file, memory and computer commands remain available without internet."),
    ("Automation Marketplace", "Discover and manage reusable skills",
     "Open the automation marketplace. List installed skills by category and help me create, import or run one safely."),
    ("Executive Briefing", "Daily routine, agenda, weather and focus goals",
     "Run morning executive briefing with schedule, system status and today's priority goals."),
    ("Focus Pomodoro", "25-min productivity timer and break management",
     "Start a 25-minute Pomodoro focus session and announce breaks."),
    ("Smart File Organizer", "Clean up cluttered Desktop and Downloads folders",
     "Preview cleaning up cluttered desktop files and organize into category folders."),
    ("Writing Polish", "Executive tone rewriting, grammar fixes and summaries",
     "Polish and improve text from my clipboard with executive tone."),
    ("Media Control", "Play, pause, skip and system volume adjustment",
     "Play or pause current media playback and control volume."),
    ("Quick Calculator", "Instant math, percentage, currency and units",
     "Calculate 15% of 850 or convert currency and units."),
    ("Screen Explainer", "Capture screen and explain text, code or errors",
     "Capture what is on my screen and explain it in plain English."),
    ("Voice Speed", "Adjust Charlie speech rate, pitch and volume",
     "Adjust voice speed faster or slower or reset to normal."),
)


_FEATURE_SVGS = {
    "Voice Notes": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none">'
        '<rect x="8.5" y="2" width="7" height="11" rx="3.5" fill="currentColor"/>'
        '<path d="M4.5 10v1a7.5 7.5 0 0 0 15 0v-1" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/>'
        '<line x1="12" y1="18.5" x2="12" y2="22" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/>'
        '<line x1="8" y1="22" x2="16" y2="22" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/>'
        '</svg>'
    ),
    "Screen Awareness": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<rect width="20" height="14" x="2" y="3" rx="2"/>'
        '<line x1="8" x2="16" y1="21" y2="21"/>'
        '<line x1="12" x2="12" y1="17" y2="21"/>'
        '</svg>'
    ),
    "Command Bar": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M18 3a3 3 0 0 0-3 3v12a3 3 0 0 0 3 3 3 3 0 0 0 3-3 3 3 0 0 0-3-3H6a3 3 0 0 0-3 3 3 3 0 0 0 3 3 3 3 0 0 0 3-3V6a3 3 0 0 0-3-3 3 3 0 0 0-3 3 3 3 0 0 0 3 3h12a3 3 0 0 0 3-3 3 3 0 0 0-3-3z"/>'
        '</svg>'
    ),
    "Workflow Builder": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<rect x="3" y="3" width="6" height="6" rx="1"/>'
        '<rect x="15" y="15" width="6" height="6" rx="1"/>'
        '<path d="M6 9v3a3 3 0 0 0 3 3h6"/>'
        '</svg>'
    ),
    "Knowledge Vault": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<ellipse cx="12" cy="5" rx="9" ry="3"/>'
        '<path d="M3 5v14a9 3 0 0 0 18 0V5"/>'
        '<path d="M3 12a9 3 0 0 0 18 0"/>'
        '</svg>'
    ),
    "Agent Workspace": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<rect x="4" y="4" width="16" height="16" rx="2"/>'
        '<rect x="9" y="9" width="6" height="6"/>'
        '<path d="M9 1v3M15 1v3M9 20v3M15 20v3M20 9h3M20 14h3M1 9h3M1 14h3"/>'
        '</svg>'
    ),
    "Live Translation": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="m5 8 6 6"/>'
        '<path d="m4 14 6-6 2-3"/>'
        '<path d="M2 5h12"/>'
        '<path d="M7 2h1"/>'
        '<path d="m22 22-5-10-5 10"/>'
        '<path d="M14 18h6"/>'
        '</svg>'
    ),
    "Meeting Intelligence": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/>'
        '<circle cx="9" cy="7" r="4"/>'
        '<path d="M22 21v-2a4 4 0 0 0-3-3.87"/>'
        '<path d="M16 3.13a4 4 0 0 1 0 7.75"/>'
        '</svg>'
    ),
    "Smart Notifications": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/>'
        '<path d="M10.3 21a1.94 1.94 0 0 0 3.4 0"/>'
        '</svg>'
    ),
    "Privacy Dashboard": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>'
        '<path d="m9 12 2 2 4-4"/>'
        '</svg>'
    ),
    "Offline Survival": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<line x1="2" x2="22" y1="2" y2="22"/>'
        '<path d="M5.69 5.7A10.74 10.74 0 0 0 2 12c0 4.4 3.6 8 8 8h10a7.7 7.7 0 0 0 3-.62"/>'
        '<path d="M21.54 16.5A7.8 7.8 0 0 0 22 12c0-4-3-7-7-7-1.33 0-2.58.37-3.66 1.02"/>'
        '</svg>'
    ),
    "Automation Marketplace": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<rect width="7" height="7" x="3" y="3" rx="1"/>'
        '<rect width="7" height="7" x="14" y="3" rx="1"/>'
        '<rect width="7" height="7" x="14" y="14" rx="1"/>'
        '<rect width="7" height="7" x="3" y="14" rx="1"/>'
        '</svg>'
    ),
    "proactive_daemon": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M12 2L4 6v5.5c0 4.8 3.4 9.3 8 10.5 4.6-1.2 8-5.7 8-10.5V6l-8-4z"/>'
        '<circle cx="12" cy="11" r="2.5"/>'
        '<path d="M12 7v1.5M12 14.5V16M8 11h1.5M14.5 11H16"/>'
        '</svg>'
    ),
    "daemon_logo": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="36" height="36" viewBox="0 0 36 36" fill="none">'
        '<rect width="36" height="36" rx="10" fill="url(#daemon_grad)"/>'
        '<defs>'
        '<linearGradient id="daemon_grad" x1="0" y1="0" x2="36" y2="36" gradientUnits="userSpaceOnUse">'
        '<stop stop-color="#059669"/>'
        '<stop offset="1" stop-color="#0d9488"/>'
        '</linearGradient>'
        '</defs>'
        '<path d="M18 7L10 11v6.5c0 5.2 3.4 10.1 8 11.5 4.6-1.4 8-6.3 8-11.5V11l-8-4z" stroke="#ffffff" stroke-width="2" stroke-linejoin="round" fill="none"/>'
        '<circle cx="18" cy="17" r="3" fill="#ffffff"/>'
        '<path d="M18 11v2M18 21v2M12 17h2M22 17h2" stroke="#ffffff" stroke-width="1.8" stroke-linecap="round"/>'
        '</svg>'
    ),
    "hub_logo": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<polygon points="12 2 2 7 12 12 22 7 12 2"/>'
        '<polyline points="2 17 12 22 22 17"/>'
        '<polyline points="2 12 12 17 22 12"/>'
        '</svg>'
    ),
    "gear": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<circle cx="12" cy="12" r="3"/>'
        '<path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/>'
        '</svg>'
    ),
    "brand_spark": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M12 2v20M2 12h20M4.93 4.93l14.14 14.14M4.93 19.07 19.07 4.93"/>'
        '<circle cx="12" cy="12" r="3" fill="currentColor"/>'
        '</svg>'
    ),
    "nav_home": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="m3 9 9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>'
        '<polyline points="9 22 9 12 15 12 15 22"/>'
        '</svg>'
    ),
    "nav_chat": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>'
        '</svg>'
    ),
    "nav_voice": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none">'
        '<rect x="8.5" y="2" width="7" height="11" rx="3.5" fill="currentColor"/>'
        '<path d="M4.5 10v1a7.5 7.5 0 0 0 15 0v-1" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/>'
        '<line x1="12" y1="18.5" x2="12" y2="22" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/>'
        '<line x1="8" y1="22" x2="16" y2="22" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/>'
        '</svg>'
    ),
    "nav_avatar": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/>'
        '<polyline points="3.27 6.96 12 12.01 20.73 6.96"/>'
        '<line x1="12" x2="12" y1="22.08" y2="12"/>'
        '</svg>'
    ),
    "nav_tools": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<rect width="7" height="7" x="3" y="3" rx="1"/>'
        '<rect width="7" height="7" x="14" y="3" rx="1"/>'
        '<rect width="7" height="7" x="14" y="14" rx="1"/>'
        '<rect width="7" height="7" x="3" y="14" rx="1"/>'
        '</svg>'
    ),
    "nav_memory": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<ellipse cx="12" cy="5" rx="9" ry="3"/>'
        '<path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/>'
        '<path d="M3 12c0 1.66 4 3 9 3s9-1.34 9-3"/>'
        '</svg>'
    ),
    "nav_settings": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<circle cx="12" cy="12" r="3"/>'
        '<path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/>'
        '</svg>'
    ),
    "crown": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none">'
        '<defs>'
        '<linearGradient id="crown_gold_grad" x1="2" y1="2" x2="22" y2="22" gradientUnits="userSpaceOnUse">'
        '<stop stop-color="#FDE68A"/>'
        '<stop offset="0.35" stop-color="#FBBF24"/>'
        '<stop offset="0.75" stop-color="#F59E0B"/>'
        '<stop offset="1" stop-color="#D97706"/>'
        '</linearGradient>'
        '</defs>'
        '<rect x="4" y="17.5" width="16" height="2.2" rx="1.1" fill="url(#crown_gold_grad)"/>'
        '<path d="M4 15.5L2.8 7.2L7.6 11L12 3.8L16.4 11L21.2 7.2L20 15.5H4Z" fill="url(#crown_gold_grad)" stroke="#FFFBEB" stroke-width="0.75" stroke-linejoin="round"/>'
        '<circle cx="2.8" cy="6.8" r="1.4" fill="#FFFBEB" stroke="#D97706" stroke-width="0.5"/>'
        '<circle cx="12" cy="3.5" r="1.6" fill="#FFFBEB" stroke="#D97706" stroke-width="0.5"/>'
        '<circle cx="21.2" cy="6.8" r="1.4" fill="#FFFBEB" stroke="#D97706" stroke-width="0.5"/>'
        '<polygon points="12,8.8 13.6,11.5 12,13.8 10.4,11.5" fill="#FFFBEB" opacity="0.9"/>'
        '</svg>'
    ),
    "search": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<circle cx="11" cy="11" r="8"/>'
        '<path d="m21 21-4.3-4.3"/>'
        '</svg>'
    ),
    "nav_screen": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<rect width="20" height="14" x="2" y="3" rx="2"/>'
        '<path d="M12 17v4"/>'
        '<path d="M8 21h8"/>'
        '<path d="M2 12s3-4 10-4 10 4 10 4-3 4-10 4-10-4-10-4Z"/>'
        '<circle cx="12" cy="12" r="2"/>'
        '</svg>'
    ),
    "nav_brain": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M12 5a3 3 0 1 0-5.997.125 4 4 0 0 0-2.526 5.77 4 4 0 0 0 .556 6.588A4 4 0 1 0 12 18Z"/>'
        '<path d="M12 5a3 3 0 1 1 5.997.125 4 4 0 0 1 2.526 5.77 4 4 0 0 1-.556 6.588A4 4 0 1 1 12 18Z"/>'
        '<path d="M15 13a4.5 4.5 0 0 1-3-4 4.5 4.5 0 0 1-3 4"/>'
        '<path d="M17.599 6.5a3 3 0 0 0 .399-1.375"/>'
        '<path d="M6.003 5.125A3 3 0 0 0 6.401 6.5"/>'
        '<path d="M3.477 10.896a4 4 0 0 1 .585-.396"/>'
        '<path d="M19.938 10.5a4 4 0 0 1 .585.396"/>'
        '<path d="M6 18a4 4 0 0 1-1.967-.516"/>'
        '<path d="M19.967 17.484A4 4 0 0 1 18 18"/>'
        '</svg>'
    ),
    "nav_mobile": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<rect width="7" height="12" x="5" y="2" rx="2"/>'
        '<path d="M12 18v2"/>'
        '<rect width="13" height="8" x="3" y="11" rx="2"/>'
        '</svg>'
    ),
    "card_memory_brain": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M9.5 2A2.5 2.5 0 0 1 12 4.5v15a2.5 2.5 0 0 1-4.96-.46 2.5 2.5 0 0 1-1.96-3 2.5 2.5 0 0 1 0-4.92 2.5 2.5 0 0 1 1.32-4.24A2.5 2.5 0 0 1 9.5 2Z"/>'
        '<path d="M14.5 2A2.5 2.5 0 0 0 12 4.5v15a2.5 2.5 0 0 0 4.96-.46 2.5 2.5 0 0 0 1.96-3 2.5 2.5 0 0 0 0-4.92 2.5 2.5 0 0 0-1.32-4.24A2.5 2.5 0 0 0 14.5 2Z"/>'
        '</svg>'
    ),
    "bell": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/>'
        '<path d="M10.3 21a1.94 1.94 0 0 0 3.4 0"/>'
        '</svg>'
    ),
    "user_avatar": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<circle cx="12" cy="8" r="4"/>'
        '<path d="M20 21a8 8 0 0 0-16 0"/>'
        '</svg>'
    ),
    "sparkles": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="m12 3-1.912 5.813a2 2 0 0 1-1.275 1.275L3 12l5.813 1.912a2 2 0 0 1 1.275 1.275L12 21l1.912-5.813a2 2 0 0 1 1.275-1.275L21 12l-5.813-1.912a2 2 0 0 1-1.275-1.275L12 3Z"/>'
        '</svg>'
    ),
    "paperclip": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="m21.44 11.05-9.19 9.19a6 6 0 0 1-8.49-8.49l8.57-8.57A4 4 0 1 1 18 8.84l-8.59 8.57a2 2 0 0 1-2.83-2.83l8.49-8.48"/>'
        '</svg>'
    ),
    "send_arrow": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<line x1="22" y1="2" x2="11" y2="13"/>'
        '<polygon points="22 2 15 22 11 13 2 9 22 2"/>'
        '</svg>'
    ),
    "mic_solid": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none">'
        '<rect x="8.5" y="2" width="7" height="11" rx="3.5" fill="currentColor"/>'
        '<path d="M4.5 10v1a7.5 7.5 0 0 0 15 0v-1" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/>'
        '<line x1="12" y1="18.5" x2="12" y2="22" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/>'
        '<line x1="8" y1="22" x2="16" y2="22" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/>'
        '</svg>'
    ),
    "sound_wave": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M2 10v4M6 6v12M10 3v18M14 8v8M18 5v14M22 10v4"/>'
        '</svg>'
    ),
    "weather_sun_cloud": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M12 2v2"/><path d="m4.93 4.93 1.41 1.41"/><path d="M20 12h2"/><path d="m19.07 4.93-1.41 1.41"/>'
        '<path d="M15.947 12.65a4 4 0 0 0-5.925-4.128"/><path d="M13 22H7a5 5 0 1 1 4.9-6H13a3 3 0 0 1 0 6Z"/>'
        '</svg>'
    ),
    "chip_plane": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M17.8 19.2 16 11l3.5-3.5C21 6 21.5 4 21 3c-1-.5-3 0-4.5 1.5L13 8 4.8 6.2c-.5-.1-.9.1-1.1.5l-.3.5c-.2.5-.1 1 .3 1.3L9 12l-2 3H4l-1 1 3 2 2 3 1-1v-3l3-2 3.5 5.3c.3.4.8.5 1.3.3l.5-.2c.4-.3.6-.7.5-1.2z"/>'
        '</svg>'
    ),
    "chip_doc": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/>'
        '<path d="M14 2v4a2 2 0 0 0 2 2h4"/>'
        '<path d="M10 9H8"/><path d="M16 13H8"/><path d="M16 17H8"/>'
        '</svg>'
    ),
    "chip_fitness": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>'
        '</svg>'
    ),
    "chip_bulb": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M15 14c.2-1 .7-1.7 1.5-2.5 1-.9 1.5-2.2 1.5-3.5A6 6 0 0 0 6 8c0 1 .2 2.2 1.5 3.5.7.7 1.3 1.5 1.5 2.5"/>'
        '<path d="M9 18h6"/><path d="M10 22h4"/>'
        '</svg>'
    ),
    "card_search": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<circle cx="11" cy="11" r="8"/>'
        '<path d="m21 21-4.3-4.3"/>'
        '</svg>'
    ),
    "card_voice": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M3 14h3a2 2 0 0 1 2 2v3a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-7a9 9 0 0 1 18 0v7a2 2 0 0 1-2 2h-1a2 2 0 0 1-2-2v-3a2 2 0 0 1 2-2h3"/>'
        '</svg>'
    ),
    "card_memory": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<ellipse cx="12" cy="5" rx="9" ry="3"/>'
        '<path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/>'
        '<path d="M3 12c0 1.66 4 3 9 3s9-1.34 9-3"/>'
        '</svg>'
    ),
    "neural_memory": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M12 5a3 3 0 1 0-5.997.125 4 4 0 0 0-2.526 5.77 4 4 0 0 0 .556 6.588A4 4 0 1 0 12 18Z"/>'
        '<path d="M12 5a3 3 0 1 1 5.997.125 4 4 0 0 1 2.526 5.77 4 4 0 0 1-.556 6.588A4 4 0 1 1 12 18Z"/>'
        '<path d="M12 5v13"/>'
        '<path d="M15 13h4M5 13h4M16 8h2M6 8h2"/>'
        '</svg>'
    ),
    "security_shield": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>'
        '<path d="m9 12 2 2 4-4"/>'
        '</svg>'
    ),
    "card_tasks": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<polyline points="9 11 12 14 22 4"/>'
        '<path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/>'
        '</svg>'
    ),
    "card_integrations": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/>'
        '<path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>'
        '</svg>'
    ),
    "arrow_right": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/>'
        '</svg>'
    ),
    "hdr_expand": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7"/>'
        '</svg>'
    ),
    "hdr_eye": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7Z"/><circle cx="12" cy="12" r="3"/>'
        '</svg>'
    ),
    "hdr_speaker": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none">'
        '<path d="M11 4.5L6 8.5H2v7h4l5 4V4.5Z" fill="currentColor"/>'
        '<path d="M15.5 8.5a5 5 0 0 1 0 7" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/>'
        '<path d="M19 5.5a9.5 9.5 0 0 1 0 13" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/>'
        '</svg>'
    ),
    "brand_c": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="36" height="36" viewBox="0 0 36 36" fill="none">'
        '<defs>'
        '<linearGradient id="brand_bg_sq" x1="0%" y1="0%" x2="100%" y2="100%">'
        '<stop offset="0%" stop-color="#111827"/>'
        '<stop offset="100%" stop-color="#0b0f19"/>'
        '</linearGradient>'
        '<linearGradient id="c_stroke_grad" x1="0%" y1="0%" x2="100%" y2="100%">'
        '<stop offset="0%" stop-color="#818cf8"/>'
        '<stop offset="100%" stop-color="#38bdf8"/>'
        '</linearGradient>'
        '</defs>'
        '<rect x="1.5" y="1.5" width="33" height="33" rx="9" fill="url(#brand_bg_sq)" stroke="rgba(255,255,255,0.12)" stroke-width="1"/>'
        '<path d="M23.5 12C20.5 9 15.5 9 12.5 12C9.5 15 9.5 21 12.5 24C15.5 27 20.5 27 23.5 24" stroke="url(#c_stroke_grad)" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/>'
        '<circle cx="21" cy="18" r="2.2" fill="#38bdf8"/>'
        '</svg>'
    ),
    "mic_off": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none">'
        '<rect x="8.5" y="2" width="7" height="11" rx="3.5" fill="currentColor" opacity="0.6"/>'
        '<path d="M4.5 10v1a7.5 7.5 0 0 0 15 0v-1" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" opacity="0.6"/>'
        '<line x1="12" y1="18.5" x2="12" y2="22" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" opacity="0.6"/>'
        '<line x1="8" y1="22" x2="16" y2="22" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" opacity="0.6"/>'
        '<line x1="3" y1="3" x2="21" y2="21" stroke="#ffffff" stroke-width="2.5" stroke-linecap="round"/>'
        '</svg>'
    ),
    "stop_square": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none">'
        '<rect x="5.5" y="5.5" width="13" height="13" rx="3" fill="currentColor"/>'
        '</svg>'
    ),
    "chevron_down": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="m6 9 6 6 6-6"/>'
        '</svg>'
    ),
    "check_mini": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">'
        '<polyline points="20 6 9 17 4 12"/>'
        '</svg>'
    ),
    "rag_database": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<ellipse cx="12" cy="5" rx="9" ry="3"/>'
        '<path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/>'
        '<path d="M3 12c0 1.66 4 3 9 3s9-1.34 9-3"/>'
        '</svg>'
    ),
    "rag_folder_plus": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z"/>'
        '<line x1="12" y1="10" x2="12" y2="16"/><line x1="9" y1="13" x2="15" y2="13"/>'
        '</svg>'
    ),
    "rag_file_plus": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/>'
        '<path d="M14 2v4a2 2 0 0 0 2 2h4"/>'
        '<line x1="12" y1="18" x2="12" y2="12"/><line x1="9" y1="15" x2="15" y2="15"/>'
        '</svg>'
    ),
    "rag_refresh": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/><path d="M8 16H3v5"/>'
        '</svg>'
    ),
    "rag_trash": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M3 6h18"/><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/><line x1="10" y1="11" x2="10" y2="17"/><line x1="14" y1="11" x2="14" y2="17"/>'
        '</svg>'
    ),
    "rag_bolt": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>'
        '</svg>'
    ),
    "rag_file_doc": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>'
        '<polyline points="14 2 14 8 20 8"/>'
        '<line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/>'
        '</svg>'
    ),
    "rag_layers": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<polygon points="12 2 2 7 12 12 22 7 12 2"/>'
        '<polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/>'
        '</svg>'
    ),
    "rag_disk": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="3"/>'
        '</svg>'
    ),
    "rag_x": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">'
        '<line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>'
        '</svg>'
    ),
    "gemini_color": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none">'
        '<path d="M20.616 10.835a14.147 14.147 0 0 1-4.45-3.001 14.111 14.111 0 0 1-3.678-6.452.503.503 0 0 0-.975 0 14.134 14.134 0 0 1-3.679 6.452 14.155 14.155 0 0 1-4.45 3.001c-.65.28-1.318.505-2.002.678a.502.502 0 0 0 0 .975c.684.172 1.35.397 2.002.677a14.147 14.147 0 0 1 4.45 3.001 14.112 14.112 0 0 1 3.679 6.453.502.502 0 0 0 .975 0c.172-.685.397-1.351.677-2.003a14.145 14.145 0 0 1 3.001-4.45 14.113 14.113 0 0 1 6.453-3.678.503.503 0 0 0 0-.975 13.245 13.245 0 0 1-2.003-.678z" fill="url(#gemini_grad)"/>'
        '<defs>'
        '<linearGradient id="gemini_grad" x1="0" y1="0" x2="24" y2="24" gradientUnits="userSpaceOnUse">'
        '<stop stop-color="#4daafc"/>'
        '<stop offset="0.5" stop-color="#7e57c2"/>'
        '<stop offset="1" stop-color="#f472b6"/>'
        '</linearGradient>'
        '</defs>'
        '</svg>'
    ),
    "gemini_sparkle": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="currentColor">'
        '<path d="M20.616 10.835a14.147 14.147 0 0 1-4.45-3.001 14.111 14.111 0 0 1-3.678-6.452.503.503 0 0 0-.975 0 14.134 14.134 0 0 1-3.679 6.452 14.155 14.155 0 0 1-4.45 3.001c-.65.28-1.318.505-2.002.678a.502.502 0 0 0 0 .975c.684.172 1.35.397 2.002.677a14.147 14.147 0 0 1 4.45 3.001 14.112 14.112 0 0 1 3.679 6.453.502.502 0 0 0 .975 0c.172-.685.397-1.351.677-2.003a14.145 14.145 0 0 1 3.001-4.45 14.113 14.113 0 0 1 6.453-3.678.503.503 0 0 0 0-.975 13.245 13.245 0 0 1-2.003-.678z"/>'
        '</svg>'
    ),
    "ollama_llama": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="currentColor" fill-rule="evenodd">'
        '<path d="M7.905 1.09c.216.085.411.225.588.41.295.306.544.744.734 1.263.191.522.315 1.1.362 1.68a5.054 5.054 0 0 1 2.049-.636l.051-.004c.87-.07 1.73.087 2.48.474.101.053.2.11.297.17.05-.569.172-1.134.36-1.644.19-.52.439-.957.733-1.264a1.67 1.67 0 0 1 .589-.41c.257-.1.53-.118.796-.042.401.114.745.368 1.016.737.248.337.434.769.561 1.287.23.934.27 2.163.115 3.645l.053.04.026.019c.757.576 1.284 1.397 1.563 2.35.435 1.487.216 3.155-.534 4.088l-.018.021.002.003c.417.762.67 1.567.724 2.4l.002.03c.064 1.065-.2 2.137-.814 3.19l-.007.01.01.024c.472 1.157.62 2.322.438 3.486l-.006.039a.651.651 0 0 1-.747.536.648.648 0 0 1-.54-.742c.167-1.033.01-2.069-.48-3.123a.643.643 0 0 1 .04-.617l.004-.006c.604-.924.854-1.83.8-2.72-.046-.779-.325-1.544-.8-2.273a.644.644 0 0 1 .18-.886l.009-.006c.243-.159.467-.565.58-1.12a4.229 4.229 0 0 0-.095-1.974c-.205-.7-.58-1.284-1.105-1.683-.595-.454-1.383-.673-2.38-.61a.653.653 0 0 1-.632-.371c-.314-.665-.772-1.141-1.343-1.436a3.288 3.288 0 0 0-1.772-.332c-1.245.099-2.343.801-2.67 1.686a.652.652 0 0 1-.61.425c-1.067.002-1.893.252-2.497.703-.522.39-.878.935-1.066 1.588a4.07 4.07 0 0 0-.068 1.886c.112.558.331 1.02.582 1.269l.008.007c.212.207.257.53.109.785-.36.622-.629 1.549-.673 2.44-.05 1.018.186 1.902.719 2.536l.016.019a.643.643 0 0 1 .095.69c-.576 1.236-.753 2.252-.562 3.052a.652.652 0 0 1-1.269.298c-.243-1.018-.078-2.184.473-3.498l.014-.035-.008-.012a4.339 4.339 0 0 1-.598-1.309l-.005-.019a5.764 5.764 0 0 1-.177-1.785c.044-.91.278-1.842.622-2.59l.012-.026-.002-.002c-.293-.418-.51-.953-.63-1.545l-.005-.024a5.352 5.352 0 0 1 .093-2.49c.262-.915.777-1.701 1.536-2.269.06-.045.123-.09.186-.132-.159-1.493-.119-2.73.112-3.67.127-.518.314-.95.562-1.287.27-.368.614-.622 1.015-.737.266-.076.54-.059.797.042zm4.116 9.09c.936 0 1.8.313 2.446.855.63.527 1.005 1.235 1.005 1.94 0 .888-.406 1.58-1.133 2.022-.62.375-1.451.557-2.403.557-1.009 0-1.871-.259-2.493-.734-.617-.47-.963-1.13-.963-1.845 0-.707.398-1.417 1.056-1.946.668-.537 1.55-.849 2.485-.849zm0 .896a3.07 3.07 0 0 0-1.916.65c-.461.37-.722.835-.722 1.25 0 .428.21.829.61 1.134.455.347 1.124.548 1.943.548.799 0 1.473-.147 1.932-.426.463-.28.7-.686.7-1.257 0-.423-.246-.89-.683-1.256-.484-.405-1.14-.643-1.864-.643zm.662 1.21l.004.004c.12.151.095.37-.056.49l-.292.23v.446a.375.375 0 0 1-.376.373.375.375 0 0 1-.376-.373v-.46l-.271-.218a.347.347 0 0 1-.052-.49.353.353 0 0 1 .494-.051l.215.172.22-.174a.353.353 0 0 1 .49.051zm-5.04-1.919c.478 0 .867.39.867.871a.87.87 0 0 1-.868.871.87.87 0 0 1-.867-.87.87.87 0 0 1 .867-.872zm8.706 0c.48 0 .868.39.868.871a.87.87 0 0 1-.868.871.87.87 0 0 1-.867-.87.87.87 0 0 1 .867-.872zM7.44 2.3l-.003.002a.659.659 0 0 0-.285.238l-.005.006c-.138.189-.258.467-.348.832-.17.692-.216 1.631-.124 2.782.43-.128.899-.208 1.404-.237l.01-.001.019-.034c.046-.082.095-.161.148-.239.123-.771.022-1.692-.253-2.444-.134-.364-.297-.65-.453-.813a.628.628 0 0 0-.107-.09L7.44 2.3zm9.174.04l-.002.001a.628.628 0 0 0-.107.09c-.156.163-.32.45-.453.814-.29.794-.387 1.776-.23 2.572l.058.097.008.014h.03a5.184 5.184 0 0 1 1.466.212c.086-1.124.038-2.043-.128-2.722-.09-.365-.21-.643-.349-.832l-.004-.006a.659.659 0 0 0-.285-.239h-.004z"/>'
        '</svg>'
    ),
    "map_pin": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0Z"/><circle cx="12" cy="10" r="3"/>'
        '</svg>'
    ),
    "weather_sun": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<circle cx="12" cy="12" r="4"/><path d="M12 2v2"/><path d="M12 20v2"/><path d="m4.93 4.93 1.41 1.41"/><path d="m17.66 17.66 1.41 1.41"/><path d="M2 12h2"/><path d="M20 12h2"/><path d="m6.34 17.66-1.41 1.41"/><path d="m19.07 4.93-1.41 1.41"/>'
        '</svg>'
    ),
    "weather_rain": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M4 14.899A7 7 0 1 1 15.71 8h1.79a4.5 4.5 0 0 1 2.5 8.242"/><path d="M16 14v6"/><path d="M8 14v6"/><path d="M12 16v6"/>'
        '</svg>'
    ),
    "weather_cloud": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M17.5 19H9a7 7 0 1 1 6.71-9h1.79a4.5 4.5 0 0 1 0 9Z"/>'
        '</svg>'
    ),
    "vision_retina_lens": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="36" height="36" viewBox="0 0 36 36" fill="none">'
        '<defs>'
        '<linearGradient id="v_lens_bg" x1="0%" y1="0%" x2="100%" y2="100%">'
        '<stop offset="0%" stop-color="#0f172a"/>'
        '<stop offset="100%" stop-color="#030712"/>'
        '</linearGradient>'
        '<linearGradient id="v_glow_grad" x1="0%" y1="0%" x2="100%" y2="100%">'
        '<stop offset="0%" stop-color="#38bdf8"/>'
        '<stop offset="100%" stop-color="#818cf8"/>'
        '</linearGradient>'
        '</defs>'
        '<rect x="1.5" y="1.5" width="33" height="33" rx="10" fill="url(#v_lens_bg)" stroke="url(#v_glow_grad)" stroke-width="1.4"/>'
        '<path d="M7 12V7H12M24 7H29V12M29 24V29H24M12 29H7V24" stroke="#38bdf8" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>'
        '<circle cx="18" cy="18" r="7.5" stroke="url(#v_glow_grad)" stroke-width="1.5" stroke-dasharray="3 2"/>'
        '<circle cx="18" cy="18" r="3.2" fill="#38bdf8"/>'
        '<path d="M18 5V8M18 28V31M5 18H8M28 18H31" stroke="#818cf8" stroke-width="1.5" stroke-linecap="round"/>'
        '</svg>'
    ),
    "vision_ocr_scan": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M4 7V4h3M17 4h3v3M4 17v3h3M20 17v3h-3"/>'
        '<line x1="7" y1="12" x2="17" y2="12" stroke-width="2.2"/>'
        '<path d="M8 8h8M8 16h5"/>'
        '</svg>'
    ),
    "vision_spark_deep": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="m12 3-1.9 5.8a2 2 0 0 1-1.3 1.3L3 12l5.8 1.9a2 2 0 0 1 1.3 1.3L12 21l1.9-5.8a2 2 0 0 1 1.3-1.3L21 12l-5.8-1.9a2 2 0 0 1-1.3-1.3Z"/>'
        '<circle cx="12" cy="12" r="2" fill="currentColor"/>'
        '</svg>'
    ),
    "vision_radar_code": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="m16 18 6-6-6-6M8 6l-6 6 6 6"/>'
        '<circle cx="12" cy="12" r="2" fill="currentColor"/>'
        '</svg>'
    ),
    "vision_camera_lens": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/>'
        '<circle cx="12" cy="13" r="4"/>'
        '</svg>'
    ),
    "vision_folder_open": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M4 20h16a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L8.6 3.9A2 2 0 0 0 6.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z"/>'
        '</svg>'
    ),
    "vision_screen_refresh": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<rect x="2" y="3" width="20" height="14" rx="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/>'
        '</svg>'
    ),
}


_SVG_PIXMAP_CACHE: dict[tuple[str, int, str, str, str, str], QPixmap] = {}
_SVG_ICON_CACHE: dict[tuple[str, int, str, str], QIcon] = {}


def _render_hub_svg(svg_key: str, size: int = 18, color: str = "#38bdf8") -> QPixmap:
    pri = getattr(C, "PRI", "#6366f1")
    pri_dim = getattr(C, "PRI_DIM", "#4f46e5")
    border_b = getattr(C, "BORDER_B", "#3b82f6")
    cache_key = (svg_key, size, color, pri, pri_dim, border_b)
    cached = _SVG_PIXMAP_CACHE.get(cache_key)
    if cached is not None and not cached.isNull():
        return cached
    raw = _FEATURE_SVGS.get(svg_key, _FEATURE_SVGS["hub_logo"])
    clean = raw.replace("currentColor", color)
    if svg_key == "brand_c":
        clean = (clean
            .replace("#818cf8", pri)
            .replace("#38bdf8", border_b)
        )
    renderer = QSvgRenderer(QByteArray(clean.encode("utf-8")))
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    renderer.render(p)
    p.end()
    _SVG_PIXMAP_CACHE[cache_key] = pix
    return pix


def _render_svg_icon(svg_key: str, size: int = 18, color: str = "#818cf8") -> QIcon:
    pri = getattr(C, "PRI", "#6366f1")
    cache_key = (svg_key, size, color, pri)
    cached = _SVG_ICON_CACHE.get(cache_key)
    if cached is not None and not cached.isNull():
        return cached
    ico = QIcon(_render_hub_svg(svg_key, size, color))
    _SVG_ICON_CACHE[cache_key] = ico
    return ico


def _render_user_initial_avatar(initial: str = "U", size: int = 22) -> QPixmap:
    """Render a modern, high-contrast circular initial/silhouette avatar for the user."""
    char = (initial or "U")[:1].upper()
    pri = getattr(C, "PRI", "#6366f1")
    pri_dim = getattr(C, "PRI_DIM", "#4f46e5")

    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

    # Smooth circular container with theme gradient
    grad = QLinearGradient(0, 0, float(size), float(size))
    grad.setColorAt(0.0, QColor(pri))
    grad.setColorAt(1.0, QColor(pri_dim))
    p.setBrush(QBrush(grad))
    p.setPen(QPen(QColor(255, 255, 255, 55), 1.0))
    p.drawEllipse(QRectF(0.5, 0.5, float(size - 1), float(size - 1)))

    if char in ("", "U", "Y"):
        # Render clean user silhouette icon for default 'You' / unconfigured user
        svg_raw = _FEATURE_SVGS.get("user_avatar", "")
        if svg_raw:
            svg_clean = svg_raw.replace("currentColor", "#ffffff")
            renderer = QSvgRenderer(QByteArray(svg_clean.encode("utf-8")))
            margin = float(size) * 0.22
            inner_rect = QRectF(margin, margin, float(size) - 2 * margin, float(size) - 2 * margin)
            renderer.render(p, inner_rect)
        else:
            p.setPen(QPen(QColor("#ffffff")))
            font = QFont(APP_FONT_NAME, max(8, int(size * 0.48)), QFont.Weight.Bold)
            p.setFont(font)
            p.drawText(QRectF(0, 0, float(size), float(size)), Qt.AlignmentFlag.AlignCenter, "U")
    else:
        # Crisp bold custom initial text
        p.setPen(QPen(QColor("#ffffff")))
        font = QFont(APP_FONT_NAME, max(8, int(size * 0.48)), QFont.Weight.Bold)
        p.setFont(font)
        p.drawText(QRectF(0, 0, float(size), float(size)), Qt.AlignmentFlag.AlignCenter, char)

    p.end()
    return pix


class IntelligenceHub(QFrame):
    feature_selected = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("IntelligenceHub")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setAutoFillBackground(True)
        self.setStyleSheet("""
            QFrame#IntelligenceHub {
                background: #080c14;
                border: 1px solid #1e293b;
            }
            QFrame#FeatureCard {
                background: #0f172a;
                border: 1px solid #1e293b;
                border-radius: 12px;
            }
            QFrame#FeatureCard:hover {
                background: #141f36;
                border: 1px solid #334155;
            }
        """)
        root = QVBoxLayout(self)
        root.setContentsMargins(32, 24, 32, 24)
        root.setSpacing(14)

        # ── Header ──
        header = QHBoxLayout()
        header.setSpacing(14)

        hub_icon = QLabel()
        hub_icon.setFixedSize(40, 40)
        hub_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hub_icon.setPixmap(_render_hub_svg("hub_logo", 22, "#38bdf8"))
        hub_icon.setStyleSheet(
            "background: rgba(56, 189, 248, 0.10); "
            "border: 1px solid rgba(56, 189, 248, 0.30); border-radius: 10px;"
        )
        header.addWidget(hub_icon)

        title_col = QVBoxLayout()
        title_col.setSpacing(3)
        title = QLabel("CHARLIE Intelligence Hub")
        _tf = QFont(APP_FONT_NAME, 18, QFont.Weight.ExtraBold)
        _tf.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.2)
        title.setFont(_tf)
        title.setStyleSheet("color: #ffffff; background: transparent;")

        subtitle = QLabel("12 connected capabilities powered by autonomous agents, local memory and privacy architecture")
        subtitle.setFont(QFont(APP_FONT_NAME, 9))
        subtitle.setStyleSheet("color: #94a3b8; background: transparent;")
        title_col.addWidget(title)
        title_col.addWidget(subtitle)
        header.addLayout(title_col)
        header.addStretch()

        close = QPushButton("✕  Close")
        close.setFixedSize(96, 36)
        close.setFont(QFont(APP_FONT_NAME, 9, QFont.Weight.DemiBold))
        close.setCursor(Qt.CursorShape.PointingHandCursor)
        close.setStyleSheet("""
            QPushButton {
                background: #1e293b; color: #94a3b8;
                border: 1px solid #334155; border-radius: 8px;
            }
            QPushButton:hover {
                background: #ef4444; color: #ffffff;
                border-color: #f87171;
            }
        """)
        close.clicked.connect(self.hide)
        header.addWidget(close)
        root.addLayout(header)

        # ── Architecture Pillars Ribbon ──
        ribbon = QFrame()
        ribbon.setStyleSheet("""
            QFrame {
                background: #0f172a;
                border: 1px solid #1e293b;
                border-radius: 10px;
                padding: 4px;
            }
        """)
        ribbon_lay = QHBoxLayout(ribbon)
        ribbon_lay.setContentsMargins(12, 6, 12, 6)
        ribbon_lay.setSpacing(10)

        pillars = [
            ("●  Privacy Isolated", "#38bdf8", (56, 189, 248)),
            ("●  Context Aware", "#818cf8", (129, 140, 248)),
            ("●  Confirmation Gated", "#34d399", (52, 211, 153)),
            ("●  Offline Capable", "#38bdf8", (56, 189, 248)),
        ]
        for p_txt, p_col, (pr, pg, pb) in pillars:
            pill = QLabel(p_txt)
            pill.setFont(QFont(APP_FONT_NAME, 8, QFont.Weight.Bold))
            pill.setStyleSheet(f"""
                color: {p_col};
                background: rgba({pr}, {pg}, {pb}, 0.08);
                border: 1px solid rgba({pr}, {pg}, {pb}, 0.20);
                border-radius: 6px;
                padding: 4px 10px;
            """)
            ribbon_lay.addWidget(pill)
        ribbon_lay.addStretch()
        root.addWidget(ribbon)

        # ── Scrollable Capabilities Grid ──
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("""
            QScrollArea { background: transparent; border: none; }
            QScrollBar:vertical {
                border: none;
                background: transparent;
                width: 6px;
                margin: 0px;
            }
            QScrollBar::handle:vertical {
                background: #334155;
                min-height: 24px;
                border-radius: 3px;
            }
            QScrollBar::handle:vertical:hover {
                background: #64748b;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
                border: none;
                background: none;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: none;
            }
        """)
        content = QWidget()
        content.setStyleSheet("background: transparent;")
        grid = QGridLayout(content)
        grid.setSpacing(14)
        grid.setContentsMargins(0, 4, 0, 8)

        meta_map = {
            "Voice Notes": {"svg": "Voice Notes", "cat": "AUDIO", "color": "#38bdf8", "rgb": (56, 189, 248)},
            "Screen Awareness": {"svg": "Screen Awareness", "cat": "VISION", "color": "#818cf8", "rgb": (129, 140, 248)},
            "Command Bar": {"svg": "Command Bar", "cat": "SHORTCUT", "color": "#38bdf8", "rgb": (56, 189, 248)},
            "Workflow Builder": {"svg": "Workflow Builder", "cat": "AUTOMATION", "color": "#34d399", "rgb": (52, 211, 153)},
            "Knowledge Vault": {"svg": "Knowledge Vault", "cat": "SECURITY", "color": "#2dd4bf", "rgb": (45, 212, 191)},
            "Agent Workspace": {"svg": "Agent Workspace", "cat": "MULTI-AGENT", "color": "#a78bfa", "rgb": (167, 139, 250)},
            "Live Translation": {"svg": "Live Translation", "cat": "LANGUAGE", "color": "#38bdf8", "rgb": (56, 189, 248)},
            "Meeting Intelligence": {"svg": "Meeting Intelligence", "cat": "COLLAB", "color": "#60a5fa", "rgb": (96, 165, 250)},
            "Smart Notifications": {"svg": "Smart Notifications", "cat": "ALERTS", "color": "#f59e0b", "rgb": (245, 158, 11)},
            "Privacy Dashboard": {"svg": "Privacy Dashboard", "cat": "PRIVACY", "color": "#10b981", "rgb": (16, 185, 129)},
            "Offline Survival": {"svg": "Offline Survival", "cat": "LOCAL AI", "color": "#94a3b8", "rgb": (148, 163, 184)},
            "Automation Marketplace": {"svg": "Automation Marketplace", "cat": "EXTENSIONS", "color": "#c084fc", "rgb": (192, 132, 252)},
            "Executive Briefing": {"svg": "Command Bar", "cat": "DAILY ROUTINE", "color": "#38bdf8", "rgb": (56, 189, 248)},
            "Focus Pomodoro": {"svg": "Voice Notes", "cat": "PRODUCTIVITY", "color": "#f59e0b", "rgb": (245, 158, 11)},
            "Smart File Organizer": {"svg": "Knowledge Vault", "cat": "WORKSPACE", "color": "#34d399", "rgb": (52, 211, 153)},
            "Writing Polish": {"svg": "Screen Awareness", "cat": "EXECUTIVE", "color": "#818cf8", "rgb": (129, 140, 248)},
            "Media Control": {"svg": "Voice Notes", "cat": "AUDIO", "color": "#ec4899", "rgb": (236, 72, 153)},
            "Quick Calculator": {"svg": "Command Bar", "cat": "UTILITY", "color": "#14b8a6", "rgb": (20, 184, 166)},
            "Screen Explainer": {"svg": "Screen Awareness", "cat": "VISION", "color": "#f59e0b", "rgb": (245, 158, 11)},
            "Voice Speed": {"svg": "hub_logo", "cat": "VOICE", "color": "#6366f1", "rgb": (99, 102, 241)},
        }

        for index, (name, description, instruction) in enumerate(INTELLIGENCE_FEATURES):
            meta = meta_map.get(name, {"svg": "hub_logo", "cat": "FEATURE", "color": "#38bdf8", "rgb": (56, 189, 248)})
            col = meta["color"]
            r, g, b = meta["rgb"]

            card = QFrame()
            card.setObjectName("FeatureCard")
            card_lay = QVBoxLayout(card)
            card_lay.setContentsMargins(18, 16, 18, 16)
            card_lay.setSpacing(10)

            # Top Row: Clean Vector Icon + Category Badge
            top_row = QHBoxLayout()
            top_row.setSpacing(8)

            icon_lbl = QLabel()
            icon_lbl.setFixedSize(36, 36)
            icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            icon_lbl.setPixmap(_render_hub_svg(meta["svg"], 20, col))
            icon_lbl.setStyleSheet(f"""
                background: rgba({r}, {g}, {b}, 0.08);
                border: 1px solid rgba({r}, {g}, {b}, 0.22);
                border-radius: 8px;
            """)
            top_row.addWidget(icon_lbl)
            top_row.addStretch()

            cat_badge = QLabel(meta["cat"])
            cat_badge.setFont(QFont(APP_FONT_NAME, 7, QFont.Weight.Bold))
            cat_badge.setStyleSheet(f"""
                color: {col};
                background: rgba({r}, {g}, {b}, 0.10);
                border: 1px solid rgba({r}, {g}, {b}, 0.25);
                border-radius: 5px;
                padding: 2px 7px;
            """)
            top_row.addWidget(cat_badge)
            card_lay.addLayout(top_row)

            # Title
            heading = QLabel(name)
            heading.setFont(QFont(APP_FONT_NAME, 11, QFont.Weight.Bold))
            heading.setStyleSheet("color: #f8fafc; background: transparent; border: none;")
            card_lay.addWidget(heading)

            # Description
            detail = QLabel(description)
            detail.setFont(QFont(APP_FONT_NAME, 8))
            detail.setWordWrap(True)
            detail.setStyleSheet("color: #94a3b8; background: transparent; border: none; line-height: 1.35;")
            card_lay.addWidget(detail)

            card_lay.addStretch()

            # Launch Button
            launch = QPushButton("Launch Capability  →")
            launch.setFixedHeight(34)
            launch.setFont(QFont(APP_FONT_NAME, 8, QFont.Weight.DemiBold))
            launch.setCursor(Qt.CursorShape.PointingHandCursor)
            launch.setStyleSheet("""
                QPushButton {
                    background: #1e293b;
                    color: #e2e8f0;
                    border: 1px solid #334155;
                    border-radius: 7px;
                    padding: 0 12px;
                }
                QPushButton:hover {
                    background: #2563eb;
                    color: #ffffff;
                    border: 1px solid #3b82f6;
                }
                QPushButton:pressed {
                    background: #1d4ed8;
                }
            """)
            launch.clicked.connect(lambda _=False, value=instruction: self.feature_selected.emit(value))
            card_lay.addWidget(launch)

            grid.addWidget(card, index // 3, index % 3)

        scroll.setWidget(content)
        root.addWidget(scroll, 1)
        self.hide()

    def paintEvent(self, a0):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(8, 12, 20))
        super().paintEvent(a0)

    def keyPressEvent(self, a0):
        if a0.key() == Qt.Key.Key_Escape:
            self.hide()
            a0.accept()
        else:
            super().keyPressEvent(a0)


class UniversalCommandBar(QFrame):
    submitted = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("UniversalCommandBar")
        self.setFixedSize(720, 150)
        self.setStyleSheet(f"""
            QFrame#UniversalCommandBar {{ background: rgba(15, 15, 20, 0.98); border: 2px solid {C.PRI}; border-radius: 16px; }}
            QLineEdit {{ background: {C.PANEL}; color: {C.TEXT}; border: 1px solid {C.BORDER}; border-radius: 9px; padding: 10px 12px; }}
            QLineEdit:focus {{ border-color: {C.PRI}; }}
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 12, 18, 12)
        layout.setSpacing(6)

        hdr_row = QHBoxLayout()
        heading = QLabel("CHARLIE COMMAND BAR   •   Ctrl+Space")
        heading.setFont(QFont(APP_FONT_NAME, 8, QFont.Weight.Bold))
        heading.setStyleSheet(f"color: {C.PRI}; background: transparent; border: none; letter-spacing: 1px;")
        hdr_row.addWidget(heading)
        hdr_row.addStretch()

        esc_hint = QLabel("ESC to close")
        esc_hint.setFont(QFont(APP_FONT_NAME, 7))
        esc_hint.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent; border: none;")
        hdr_row.addWidget(esc_hint)
        layout.addLayout(hdr_row)

        row = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setFont(QFont(APP_FONT_NAME, 9))
        self.input.setPlaceholderText("Ask CHARLIE, run workflow, get daily briefing, or control PC...")
        self.input.returnPressed.connect(self._submit)
        row.addWidget(self.input, 1)

        run = QPushButton("Run")
        run.setFont(QFont(APP_FONT_NAME, 9, QFont.Weight.Bold))
        run.setStyleSheet(f"""
            QPushButton {{ background: {C.PRI}; color: {C.DARK}; border-radius: 8px; font-weight: bold; }}
            QPushButton:hover {{ background: {C.ACC}; color: white; }}
        """)
        run.setFixedSize(76, 38)
        run.clicked.connect(self._submit)
        row.addWidget(run)
        layout.addLayout(row)

        # Quick action chips
        chip_row = QHBoxLayout(); chip_row.setSpacing(6)
        _chip_style = (f"QPushButton {{ background: {C.PANEL2}; color: {C.TEXT_MED}; "
                       f"border: 1px solid {C.BORDER}; border-radius: 12px; padding: 2px 10px; font-size: 11px; }}"
                       f"QPushButton:hover {{ color: {C.PRI}; border-color: {C.PRI}; }}")
        for label, cmd in [
            ("📋 Daily Briefing", "Give me my daily briefing"),
            ("🌐 Web Search", "Search the web for "),
            ("💻 System Status", "Check my system status"),
            ("🔇 Mute", "Mute microphone"),
        ]:
            btn = QPushButton(label)
            btn.setFixedHeight(26)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(_chip_style)
            btn.clicked.connect(lambda _, c=cmd: self._trigger_chip(c))
            chip_row.addWidget(btn)
        chip_row.addStretch()
        layout.addLayout(chip_row)

        self._escape_shortcut = QShortcut(QKeySequence("Escape"), self)
        self._escape_shortcut.activated.connect(self.hide)
        self.hide()

    def _trigger_chip(self, cmd: str) -> None:
        if cmd.endswith(" "):
            self.input.setText(cmd)
            self.input.setFocus()
        else:
            self.input.clear()
            self.hide()
            self.submitted.emit(cmd)

    def open_and_focus(self) -> None:
        self.show(); self.raise_(); self.input.setFocus(); self.input.selectAll()

    def _submit(self) -> None:
        text = self.input.text().strip()
        if not text:
            return
        self.input.clear(); self.hide(); self.submitted.emit(text)



class ClickOnlyComboBox(QComboBox):
    """A settings selector that cannot be changed accidentally while scrolling."""

    def wheelEvent(self, e) -> None:
        # Ignoring the event lets the enclosing settings scroll area handle it.
        # Selection remains available through a deliberate click or keyboard use.
        if e is not None:
            e.ignore()


def _format_chat_markdown(raw_text: str) -> str:
    if not raw_text:
        return ""
    import html as _html
    import re
    code_blocks = []

    def _cb_repl(match):
        lang = (match.group(1) or "CODE").strip().upper()
        code = match.group(2)
        code_escaped = _html.escape(code.strip("\r\n"))
        idx = len(code_blocks)
        html_block = (
            f'<div style="margin: 8px 0; background-color: #0f1523; border: 1px solid rgba(99, 102, 241, 0.25); border-radius: 8px; padding: 0;">'
            f'<table width="100%" cellpadding="0" cellspacing="0">'
            f'<tr><td style="padding: 6px 12px; background-color: #151c2e; border-bottom: 1px solid rgba(99, 102, 241, 0.18);">'
            f'<table width="100%" cellpadding="0" cellspacing="0">'
            f'<tr>'
            f'<td align="left">'
            f'<span style="color: #a5b4fc; font-family: \'Consolas\', \'JetBrains Mono\', monospace; font-size: 11px; font-weight: bold; text-transform: uppercase;">⚡ {lang}</span>'
            f'</td>'
            f'<td align="right">'
            f'<span style="color: #64748b; font-family: \'Segoe UI\', sans-serif; font-size: 9px; font-weight: 600; letter-spacing: 0.5px;">CODE SNIPPET</span>'
            f'</td>'
            f'</tr>'
            f'</table>'
            f'</td></tr>'
            f'<tr><td style="padding: 10px 12px;">'
            f'<pre style="margin: 0; color: #c7d2fe; font-family: \'Consolas\', \'JetBrains Mono\', monospace; font-size: 12px; line-height: 145%; white-space: pre-wrap; word-break: break-all;">{code_escaped}</pre>'
            f'</td></tr></table>'
            f'</div>'
        )
        code_blocks.append(html_block)
        return f"@@@CODEBLOCK_{idx}@@@"

    text = re.sub(r'```([a-zA-Z0-9_-]+)?\r?\n([\s\S]*?)```', _cb_repl, raw_text)

    inline_codes = []

    def _ic_repl(match):
        code = match.group(1)
        code_escaped = _html.escape(code)
        idx = len(inline_codes)
        html_code = (
            f'<code style="background-color: rgba(99, 102, 241, 0.15); color: #c7d2fe; font-family: \'Consolas\', monospace; font-size: 11px; padding: 2px 6px; border: 1px solid rgba(99, 102, 241, 0.3); border-radius: 4px;">'
            f'{code_escaped}</code>'
        )
        inline_codes.append(html_code)
        return f"@@@INLINECODE_{idx}@@@"

    text = re.sub(r'`([^`\r\n]+)`', _ic_repl, text)
    text = _html.escape(text)

    lines = text.split("\n")
    processed_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped in ("---", "***", "___"):
            processed_lines.append('<hr style="border: none; border-top: 1px solid rgba(255, 255, 255, 0.12); margin: 8px 0;">')
            continue
        if stripped.startswith("### "):
            processed_lines.append(f'<div style="font-size: 13px; font-weight: bold; color: #e2e8f0; margin: 6px 0 2px 0;">{stripped[4:]}</div>')
            continue
        if stripped.startswith("## "):
            processed_lines.append(f'<div style="font-size: 14px; font-weight: bold; color: #f8fafc; margin: 8px 0 3px 0;">{stripped[3:]}</div>')
            continue
        if stripped.startswith("# "):
            processed_lines.append(f'<div style="font-size: 15px; font-weight: bold; color: #ffffff; margin: 10px 0 4px 0; border-bottom: 1px solid rgba(255,255,255,0.08); padding-bottom: 2px;">{stripped[2:]}</div>')
            continue
        if stripped.startswith("&gt; "):
            processed_lines.append(f'<div style="border-left: 3px solid #6366f1; background-color: rgba(99, 102, 241, 0.08); padding: 4px 10px; margin: 4px 0; color: #94a3b8; font-style: italic;">{stripped[5:]}</div>')
            continue
        if stripped.startswith(("* ", "- ", "• ")):
            item_text = stripped[2:].strip()
            processed_lines.append(f'<div style="margin: 2px 0 2px 10px; color: #e2e8f0;"><span style="color: #818cf8; font-size: 10px;">●</span>&nbsp;&nbsp;{item_text}</div>')
            continue
        num_m = re.match(r'^(\d+)\.\s+(.*)$', stripped)
        if num_m:
            num = num_m.group(1)
            item_text = num_m.group(2)
            processed_lines.append(f'<div style="margin: 2px 0 2px 10px; color: #e2e8f0;"><span style="color: #818cf8; font-weight: bold; font-size: 11px;">{num}.</span>&nbsp;&nbsp;{item_text}</div>')
            continue

        processed_lines.append(line)

    text = "\n".join(processed_lines)
    text = re.sub(r'\*\*\*(.*?)\*\*\*', r'<b><i>\1</i></b>', text)
    text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'\*(.*?)\*', r'<i>\1</i>', text)
    text = re.sub(r'___(.*?)___', r'<b><i>\1</i></b>', text)
    text = re.sub(r'__(.*?)__', r'<b>\1</b>', text)
    text = re.sub(r'_(.*?)_', r'<i>\1</i>', text)

    for idx, cb in enumerate(code_blocks):
        text = text.replace(f"@@@CODEBLOCK_{idx}@@@", cb)
    for idx, ic in enumerate(inline_codes):
        text = text.replace(f"@@@INLINECODE_{idx}@@@", ic)

    text = text.replace("\r\n", "\n")
    final_parts = []
    for l in text.split("\n"):
        sl = l.strip()
        if not sl:
            final_parts.append('<div style="height: 5px;"></div>')
        elif sl.startswith(("<div", "<table", "<hr", "<tr", "<td", "</div", "</table")):
            final_parts.append(l)
        else:
            final_parts.append(l + "<br>")

    res = "".join(final_parts)
    while res.endswith("<br>"):
        res = res[:-4]
    return res


class SelectableChatLabel(QLabel):
    """Chat message label supporting mouse/keyboard selection, copy, and full-message right-click copy."""

    def __init__(self, formatted_text: str = "", raw_text: str = "", parent=None):
        super().__init__(parent)
        self._raw_text = raw_text
        self.setTextFormat(Qt.TextFormat.RichText)
        self.setWordWrap(True)
        self.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard
            | Qt.TextInteractionFlag.LinksAccessibleByMouse
        )
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.setOpenExternalLinks(True)
        if formatted_text:
            self.setText(formatted_text)

    def set_content(self, formatted_text: str, raw_text: str = ""):
        self._raw_text = raw_text
        self.setText(formatted_text)

    def contextMenuEvent(self, ev):
        self.show_context_menu(ev.globalPos())

    def show_context_menu(self, global_pos):
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #0f172a;
                color: #f1f5f9;
                border: 1px solid rgba(255, 255, 255, 0.15);
                border-radius: 8px;
                padding: 4px;
            }
            QMenu::item {
                padding: 6px 22px 6px 12px;
                border-radius: 4px;
                font-family: 'Segoe UI', 'Inter', sans-serif;
                font-size: 12px;
                color: #e2e8f0;
            }
            QMenu::item:selected {
                background-color: #6366f1;
                color: #ffffff;
            }
            QMenu::separator {
                height: 1px;
                background-color: rgba(255, 255, 255, 0.1);
                margin: 4px 6px;
            }
        """)

        has_sel = bool(self.hasSelectedText() and self.selectedText().strip())
        if has_sel:
            copy_sel_act = menu.addAction("Copy Selection")
            copy_sel_act.setShortcut(QKeySequence("Ctrl+C"))
            copy_sel_act.triggered.connect(lambda: self._copy_to_clipboard(self.selectedText()))

            copy_full_act = menu.addAction("Copy Full Message")
            copy_full_act.triggered.connect(lambda: self._copy_to_clipboard(self._raw_text or self.text()))
        else:
            copy_act = menu.addAction("Copy Message")
            copy_act.setShortcut(QKeySequence("Ctrl+C"))
            copy_act.triggered.connect(lambda: self._copy_to_clipboard(self._raw_text or self.text()))

        menu.addSeparator()
        sel_all_act = menu.addAction("Select All")
        sel_all_act.setShortcut(QKeySequence("Ctrl+A"))
        sel_all_act.triggered.connect(self._select_all_text)

        menu.exec(global_pos)

    def _select_all_text(self):
        try:
            self.setSelection(0, len(self.text()))
        except Exception:
            pass

    def _copy_to_clipboard(self, text: str):
        if not text:
            text = self._raw_text or self.text()
        if text:
            import re
            import html as _html
            clean = text
            if "<" in clean and ">" in clean and not self._raw_text:
                clean = re.sub(r'<br\s*/?>', '\n', clean)
                clean = re.sub(r'</?(?:div|p|tr|table|td|pre|code|span|b|i|strong|em|hr)[^>]*>', '', clean)
                clean = _html.unescape(clean).strip()
            cb = QApplication.clipboard()
            if cb:
                cb.setText(clean)

    def keyPressEvent(self, ev):
        if ev.matches(QKeySequence.StandardKey.Copy) or (
            ev.modifiers() & Qt.KeyboardModifier.ControlModifier and ev.key() == Qt.Key.Key_C
        ):
            if self.hasSelectedText() and self.selectedText().strip():
                self._copy_to_clipboard(self.selectedText())
            else:
                self._copy_to_clipboard(self._raw_text or self.text())
            ev.accept()
            return
        elif ev.matches(QKeySequence.StandardKey.SelectAll) or (
            ev.modifiers() & Qt.KeyboardModifier.ControlModifier and ev.key() == Qt.Key.Key_A
        ):
            self._select_all_text()
            ev.accept()
            return
        super().keyPressEvent(ev)


class LogWidget(QScrollArea):
    _sig = pyqtSignal(str)
    message_received = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setStyleSheet("""
            QScrollArea {
                background: transparent;
                border: none;
            }
            QScrollBar:vertical {
                background: rgba(0, 0, 0, 0.15);
                width: 7px;
                margin: 6px 3px 6px 0;
                border-radius: 3px;
                border: none;
            }
            QScrollBar::handle:vertical {
                background: rgba(255, 255, 255, 0.14);
                border-radius: 3px;
                min-height: 30px;
            }
            QScrollBar::handle:vertical:hover {
                background: rgba(99, 102, 241, 0.65);
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: transparent;
            }
        """)

        self._container = QWidget()
        self._container.setStyleSheet("background: transparent;")
        self._lay = QVBoxLayout(self._container)
        self._lay.setContentsMargins(14, 12, 14, 16)
        self._lay.setSpacing(14)
        self._lay.addStretch(1)
        self.setWidget(self._container)

        self._ai_name_lc = "charlie"
        self._user_name = ""
        self._has_conversation = False
        self._entries: list[dict] = []
        self._sig.connect(self._enqueue)

    def has_messages(self) -> bool:
        return self._has_conversation

    def set_user_name(self, name: str):
        self._user_name = (name or "").strip()

    def _resolve_user_name(self) -> str:
        if self._user_name:
            return self._user_name
        try:
            cfg = _read_full_config()
            uname = (cfg.get("user_name") or cfg.get("user_display_name") or "").strip()
            if uname:
                return uname
        except Exception:
            pass
        return "You"

    def _resolve_ai_name(self) -> str:
        try:
            cfg = _read_full_config()
            name = (cfg.get("assistant_name") or "CHARLIE").strip()
            if name.upper() in ("JARVIS", "J.A.R.V.I.S.", "J.A.R.V.I.S") or "JARVIS" in name.upper():
                name = "CHARLIE"
            if name:
                return name.upper()
        except Exception:
            pass
        return "CHARLIE"

    def _resolve_user_initial(self) -> str:
        uname = self._resolve_user_name()
        if uname and uname != "You":
            return uname[0].upper()
        return "U"

    def refresh_avatar_resources(self):
        pass

    def clear(self):
        self.clear_chat()

    def clear_chat(self):
        while self._lay.count() > 1:
            item = self._lay.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self._entries.clear()
        self._has_conversation = False

    def append_log(self, text: str):
        self._sig.emit(text)

    def _scroll_to_bottom(self):
        QTimer.singleShot(25, lambda: self.verticalScrollBar().setValue(self.verticalScrollBar().maximum()))

    def resizeEvent(self, e):
        super().resizeEvent(e)
        max_w = max(260, int(self.viewport().width() * 0.82))
        for i in range(self._lay.count() - 1):
            item = self._lay.itemAt(i)
            if item and item.widget():
                bf = item.widget().findChild(QFrame, "userBubble") or item.widget().findChild(QFrame, "aiBubble")
                if bf:
                    bf.setMaximumWidth(max_w)

    def _enqueue(self, text: str):
        if not text:
            return
        tl = text.lower()
        ai_prefix = f"{self._ai_name_lc}:"
        if tl.startswith("you:"):
            tag = "you"
        elif tl.startswith(ai_prefix) or tl.startswith("charlie:") or tl.startswith("jarvis:"):
            tag = "ai"
        elif tl.startswith("file:"):
            tag = "file"
        elif tl.startswith("err:") or tl.startswith("error:") or "[error]" in tl or "runtimeerror" in tl:
            tag = "err"
        else:
            tag = "sys"

        body_text = text.rstrip()

        # Suppress internal / debug-style messages (SYS: online, SYS: greeting...)
        # Route strictly to application logs / console
        if tag == "sys":
            import logging
            logging.getLogger("charlie.system").info(body_text)
            return

        self._has_conversation = True
        cur_time = time.strftime("%I:%M %p")
        self._entries.append({"tag": tag, "text": body_text, "time": cur_time})
        self.message_received.emit()

        u_name = self._resolve_user_name()
        ai_name = self._resolve_ai_name()
        max_w = max(260, int(self.viewport().width() * 0.82))

        if tag == "you":
            u_raw = body_text
            if u_raw.lower().startswith("you:"):
                u_raw = u_raw[4:].strip()
            u_formatted = _format_chat_markdown(u_raw)

            msg_w = QWidget()
            msg_w.setStyleSheet("background: transparent;")
            msg_lay = QVBoxLayout(msg_w)
            msg_lay.setContentsMargins(0, 2, 0, 4)
            msg_lay.setSpacing(4)

            # Header row (User Name, Dot, Time, Avatar)
            h_w = QWidget()
            h_w.setStyleSheet("background: transparent;")
            h_lay = QHBoxLayout(h_w)
            h_lay.setContentsMargins(0, 0, 4, 0)
            h_lay.setSpacing(6)
            h_lay.addStretch(1)

            name_lbl = QLabel(u_name)
            name_lbl.setStyleSheet("color: #cbd5e1; font-family: 'Segoe UI Variable Text', 'Segoe UI', 'Inter', sans-serif; font-size: 11.5px; font-weight: 600; background: transparent; border: none;")
            h_lay.addWidget(name_lbl)

            dot_lbl = QLabel("•")
            dot_lbl.setStyleSheet("color: #475569; font-size: 10px; background: transparent; border: none;")
            h_lay.addWidget(dot_lbl)

            time_lbl = QLabel(cur_time)
            time_lbl.setStyleSheet("color: #64748b; font-family: 'Segoe UI', sans-serif; font-size: 10px; font-weight: 400; background: transparent; border: none;")
            h_lay.addWidget(time_lbl)

            avatar_lbl = QLabel()
            avatar_lbl.setFixedSize(20, 20)
            avatar_lbl.setPixmap(_render_user_initial_avatar(self._resolve_user_initial(), 20))
            avatar_lbl.setStyleSheet("background: transparent; border: none;")
            h_lay.addWidget(avatar_lbl)

            msg_lay.addWidget(h_w)

            # Bubble row
            b_row = QWidget()
            b_row.setStyleSheet("background: transparent;")
            b_row_lay = QHBoxLayout(b_row)
            b_row_lay.setContentsMargins(0, 0, 0, 0)
            b_row_lay.setSpacing(0)
            b_row_lay.addStretch(1)

            bubble = QFrame()
            bubble.setObjectName("userBubble")
            bubble.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            bubble.setStyleSheet("""
                QFrame#userBubble {
                    background-color: #192234;
                    border: 1px solid rgba(99, 102, 241, 0.40);
                    border-radius: 16px 16px 4px 16px;
                }
            """)
            b_lay = QVBoxLayout(bubble)
            b_lay.setContentsMargins(14, 10, 14, 11)
            b_lay.setSpacing(0)

            text_lbl = SelectableChatLabel(u_formatted, raw_text=u_raw)
            text_lbl.setStyleSheet("background: transparent; border: none; padding: 0; margin: 0; color: #f8fafc; font-family: 'Inter', 'Segoe UI Variable Text', 'Segoe UI', sans-serif; font-size: 13.5px; line-height: 152%;")
            b_lay.addWidget(text_lbl)

            bubble.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            bubble.customContextMenuRequested.connect(lambda pos, lbl=text_lbl, b=bubble: lbl.show_context_menu(b.mapToGlobal(pos)))

            bubble.setMaximumWidth(max_w)
            b_row_lay.addWidget(bubble)
            msg_lay.addWidget(b_row)

            self._lay.insertWidget(self._lay.count() - 1, msg_w)

        elif tag == "ai":
            ai_raw = body_text
            for pfx in (ai_prefix, "charlie:", "jarvis:"):
                if ai_raw.lower().startswith(pfx):
                    ai_raw = ai_raw[len(pfx):].strip()
                    break
            ai_formatted = _format_chat_markdown(ai_raw)

            msg_w = QWidget()
            msg_w.setStyleSheet("background: transparent;")
            msg_lay = QVBoxLayout(msg_w)
            msg_lay.setContentsMargins(0, 2, 0, 4)
            msg_lay.setSpacing(4)

            # Header row (Brand Logo, AI Name, PRO AI Badge, Dot, Time)
            h_w = QWidget()
            h_w.setStyleSheet("background: transparent;")
            h_lay = QHBoxLayout(h_w)
            h_lay.setContentsMargins(4, 0, 0, 0)
            h_lay.setSpacing(6)

            ai_icon_lbl = QLabel()
            ai_icon_lbl.setFixedSize(18, 18)
            ai_icon_lbl.setPixmap(_render_hub_svg("brand_c", 18, "#818cf8"))
            ai_icon_lbl.setStyleSheet("background: transparent; border: none;")
            h_lay.addWidget(ai_icon_lbl)

            name_lbl = QLabel(ai_name)
            name_lbl.setStyleSheet("color: #818cf8; font-family: 'Inter', 'Segoe UI Variable Text', 'Segoe UI', sans-serif; font-size: 11.5px; font-weight: 700; letter-spacing: 0.3px; background: transparent; border: none;")
            h_lay.addWidget(name_lbl)

            badge_lbl = QLabel("PRO AI")
            badge_lbl.setStyleSheet("""
                background-color: rgba(99, 102, 241, 0.12);
                border: 1px solid rgba(99, 102, 241, 0.32);
                border-radius: 4px;
                color: #a5b4fc;
                font-family: 'Inter', 'Segoe UI', sans-serif;
                font-size: 9px;
                font-weight: 700;
                padding: 1px 5px;
                letter-spacing: 0.5px;
            """)
            h_lay.addWidget(badge_lbl)

            dot_lbl = QLabel("•")
            dot_lbl.setStyleSheet("color: #475569; font-size: 10px; background: transparent; border: none;")
            h_lay.addWidget(dot_lbl)

            time_lbl = QLabel(cur_time)
            time_lbl.setStyleSheet("color: #64748b; font-family: 'Segoe UI', sans-serif; font-size: 10px; font-weight: 400; background: transparent; border: none;")
            h_lay.addWidget(time_lbl)

            h_lay.addStretch(1)
            msg_lay.addWidget(h_w)

            # Bubble row
            b_row = QWidget()
            b_row.setStyleSheet("background: transparent;")
            b_row_lay = QHBoxLayout(b_row)
            b_row_lay.setContentsMargins(0, 0, 0, 0)
            b_row_lay.setSpacing(0)

            bubble = QFrame()
            bubble.setObjectName("aiBubble")
            bubble.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            bubble.setStyleSheet("""
                QFrame#aiBubble {
                    background-color: #121826;
                    border: 1px solid #1e2a40;
                    border-radius: 16px 16px 16px 4px;
                }
            """)
            b_lay = QVBoxLayout(bubble)
            b_lay.setContentsMargins(16, 12, 16, 13)
            b_lay.setSpacing(0)

            text_lbl = SelectableChatLabel(ai_formatted, raw_text=ai_raw)
            text_lbl.setStyleSheet("background: transparent; border: none; padding: 0; margin: 0; color: #e2e8f0; font-family: 'Inter', 'Segoe UI Variable Text', 'Segoe UI', sans-serif; font-size: 13.5px; line-height: 156%;")
            b_lay.addWidget(text_lbl)

            bubble.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            bubble.customContextMenuRequested.connect(lambda pos, lbl=text_lbl, b=bubble: lbl.show_context_menu(b.mapToGlobal(pos)))

            bubble.setMaximumWidth(max_w)
            b_row_lay.addWidget(bubble)
            b_row_lay.addStretch(1)
            msg_lay.addWidget(b_row)

            self._lay.insertWidget(self._lay.count() - 1, msg_w)

        elif tag == "file":
            msg_w = QWidget()
            msg_w.setStyleSheet("background: transparent;")
            msg_lay = QHBoxLayout(msg_w)
            msg_lay.setContentsMargins(4, 2, 4, 2)
            file_frame = QFrame()
            file_frame.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            file_frame.setStyleSheet("""
                background-color: rgba(16, 185, 129, 0.12);
                border: 1px solid rgba(16, 185, 129, 0.35);
                border-radius: 12px;
            """)
            f_lay = QHBoxLayout(file_frame)
            f_lay.setContentsMargins(10, 6, 12, 6)
            f_lay.setSpacing(8)
            icon_lbl = QLabel("📎")
            icon_lbl.setStyleSheet("color: #10b981; font-weight: bold; font-size: 13px; background: transparent; border: none;")
            text_lbl = SelectableChatLabel(body_text, raw_text=body_text)
            text_lbl.setStyleSheet("color: #6ee7b7; font-size: 12px; font-weight: 600; font-family: 'Segoe UI', sans-serif; background: transparent; border: none;")
            f_lay.addWidget(icon_lbl)
            f_lay.addWidget(text_lbl)
            file_frame.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            file_frame.customContextMenuRequested.connect(lambda pos, lbl=text_lbl, f=file_frame: lbl.show_context_menu(f.mapToGlobal(pos)))
            msg_lay.addWidget(file_frame)
            msg_lay.addStretch(1)

            self._lay.insertWidget(self._lay.count() - 1, msg_w)

        elif tag == "err":
            msg_w = QWidget()
            msg_w.setStyleSheet("background: transparent;")
            msg_lay = QHBoxLayout(msg_w)
            msg_lay.setContentsMargins(4, 2, 4, 2)
            err_frame = QFrame()
            err_frame.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            err_frame.setStyleSheet("""
                background-color: rgba(239, 68, 68, 0.12);
                border: 1px solid rgba(239, 68, 68, 0.35);
                border-radius: 12px;
            """)
            e_lay = QHBoxLayout(err_frame)
            e_lay.setContentsMargins(12, 6, 14, 6)
            e_lay.setSpacing(8)
            icon_lbl = QLabel("⚠")
            icon_lbl.setStyleSheet("color: #ef4444; font-weight: bold; font-size: 12px; background: transparent; border: none;")
            text_lbl = SelectableChatLabel(body_text, raw_text=body_text)
            text_lbl.setStyleSheet("color: #fca5a5; font-size: 12px; font-family: 'Segoe UI', sans-serif; background: transparent; border: none;")
            e_lay.addWidget(icon_lbl)
            e_lay.addWidget(text_lbl)
            err_frame.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            err_frame.customContextMenuRequested.connect(lambda pos, lbl=text_lbl, f=err_frame: lbl.show_context_menu(f.mapToGlobal(pos)))
            msg_lay.addStretch(1)
            msg_lay.addWidget(err_frame)
            msg_lay.addStretch(1)

            self._lay.insertWidget(self._lay.count() - 1, msg_w)

        self._scroll_to_bottom()

_FILE_ICONS = {
    "image":   ("🖼", "#00d4ff"), "video":   ("🎬", "#ff6b00"),
    "audio":   ("🎵", "#cc44ff"), "pdf":     ("📄", "#ff4444"),
    "word":    ("📝", "#4488ff"), "excel":   ("📊", "#44bb44"),
    "code":    ("💻", "#ffcc00"), "archive": ("📦", "#ff8844"),
    "pptx":    ("📊", "#ff6622"), "text":    ("📃", "#aaaaaa"),
    "data":    ("🔧", "#88ddff"), "unknown": ("📎", "#888888"),
}
_EXT_TO_CAT = {
    **dict.fromkeys(["jpg","jpeg","png","gif","webp","bmp","tiff","svg","ico"], "image"),
    **dict.fromkeys(["mp4","avi","mov","mkv","wmv","flv","webm","m4v"],         "video"),
    **dict.fromkeys(["mp3","wav","ogg","m4a","aac","flac","wma","opus"],        "audio"),
    **dict.fromkeys(["pdf"],                                                     "pdf"),
    **dict.fromkeys(["doc","docx"],                                              "word"),
    **dict.fromkeys(["xls","xlsx","ods"],                                        "excel"),
    **dict.fromkeys(["ppt","pptx"],                                              "pptx"),
    **dict.fromkeys(["py","js","ts","jsx","tsx","html","css","java","c","cpp",
                     "cs","go","rs","rb","php","swift","kt","sh","sql","lua"],   "code"),
    **dict.fromkeys(["zip","rar","tar","gz","7z","bz2","xz"],                   "archive"),
    **dict.fromkeys(["txt","md","rst","log"],                                    "text"),
    **dict.fromkeys(["csv","tsv","json","xml"],                                  "data"),
}

def _file_category(path: Path) -> str:
    return _EXT_TO_CAT.get(path.suffix.lower().lstrip("."), "unknown")

def _fmt_size(size: int) -> str:
    if   size < 1024:    return f"{size} B"
    elif size < 1024**2: return f"{size/1024:.1f} KB"
    elif size < 1024**3: return f"{size/1024**2:.1f} MB"
    else:                return f"{size/1024**3:.1f} GB"


class FileDropZone(QWidget):
    file_selected = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(78)
        self._current_file: str | None = None
        self._hovering  = False
        self._drag_over = False
        self._dash_offset = 0.0
        self._anim_tmr = QTimer(self)
        self._anim_tmr.timeout.connect(self._animate)
        self._anim_tmr.start(40)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self._canvas = _DropCanvas(self)
        layout.addWidget(self._canvas)

    def _animate(self):
        # The marching-ants dashed border is only meaningful while the user is
        # hovering or dragging a file over the zone. When idle, skip the repaint
        # entirely instead of redrawing the whole zone 25×/s forever — that idle
        # repaint held the GIL and stole time from the audio/response threads.
        if not (self._hovering or self._drag_over):
            return
        self._dash_offset = (self._dash_offset + 0.8) % 20
        self._canvas.update()

    def dragEnterEvent(self, a0: QDragEnterEvent):
        if a0 is not None and a0.mimeData() is not None and a0.mimeData().hasUrls():
            a0.acceptProposedAction()
            self._drag_over = True; self._canvas.update()

    def dragLeaveEvent(self, a0):
        self._drag_over = False; self._canvas.update()

    def dropEvent(self, a0: QDropEvent):
        self._drag_over = False
        if a0 is not None and a0.mimeData() is not None:
            urls = a0.mimeData().urls()
            if urls:
                path = urls[0].toLocalFile()
                if Path(path).is_file():
                    self._set_file(path)
        self._canvas.update()

    def mousePressEvent(self, a0):
        if a0 is not None and a0.button() == Qt.MouseButton.LeftButton:
            self._browse()

    def enterEvent(self, event):
        self._hovering = True; self._canvas.update()

    def leaveEvent(self, a0):
        self._hovering = False; self._canvas.update()

    def current_file(self) -> str | None:
        return self._current_file

    def clear_file(self):
        self._current_file = None; self._canvas.update()

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select a file for CHARLIE", str(Path.home()),
            "All Files (*.*);;"
            "Images (*.jpg *.jpeg *.png *.gif *.webp *.bmp *.svg);;"
            "Documents (*.pdf *.docx *.txt *.md *.pptx);;"
            "Data (*.csv *.xlsx *.json *.xml);;"
            "Code (*.py *.js *.ts *.html *.css *.java *.cpp *.go);;"
            "Audio (*.mp3 *.wav *.ogg *.m4a *.aac *.flac);;"
            "Video (*.mp4 *.avi *.mov *.mkv *.wmv *.webm);;"
            "Archives (*.zip *.rar *.tar *.gz *.7z)",
        )
        if path:
            self._set_file(path)

    def _set_file(self, path: str):
        self._current_file = path
        self._canvas.update()
        self.file_selected.emit(path)


class _DropCanvas(QWidget):
    def __init__(self, zone: FileDropZone):
        super().__init__(zone)
        self._z = zone

    def paintEvent(self, a0):
        p = QPainter(self)
        if not p.isActive():
            return
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        z    = self._z
        W, H = self.width(), self.height()
        pad  = 6
        rect = QRectF(pad, pad, W - pad * 2, H - pad * 2)

        bg_col = qcol(C.PRI_GHO if z._drag_over else (C.PANEL2 if z._hovering else C.PANEL))
        p.setBrush(QBrush(bg_col)); p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(rect, 6, 6)

        if z._current_file:   border_col = qcol(C.GREEN, 200)
        elif z._drag_over:    border_col = qcol(C.PRI, 230)
        elif z._hovering:     border_col = qcol(C.BORDER_B, 200)
        else:                 border_col = qcol(C.BORDER, 160)

        pen = QPen(border_col, 1.5, Qt.PenStyle.DashLine)
        pen.setDashOffset(z._dash_offset)
        p.setPen(pen); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(rect, 6, 6)

        if z._current_file:   self._paint_file(p, W, H)
        elif z._drag_over:    self._paint_drag_over(p, W, H)
        else:                 self._paint_idle(p, W, H, z._hovering)

        p.end()

    def _paint_idle(self, p, W, H, hover):
        cx, cy = W / 2, H / 2
        col = qcol(C.PRI_DIM if not hover else C.PRI)
        p.setPen(QPen(col, 2)); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawLine(QPointF(cx, cy - 14), QPointF(cx, cy + 4))
        p.drawLine(QPointF(cx - 8, cy - 6), QPointF(cx, cy - 14))
        p.drawLine(QPointF(cx + 8, cy - 6), QPointF(cx, cy - 14))
        p.drawLine(QPointF(cx - 14, cy + 4), QPointF(cx + 14, cy + 4))
        p.setFont(QFont(APP_FONT_NAME, 9, QFont.Weight.Medium))
        p.setPen(QPen(qcol(C.PRI_DIM if not hover else C.TEXT), 1))
        p.drawText(QRectF(0, cy + 8, W, 16), Qt.AlignmentFlag.AlignCenter,
                   "Drop file here  or  Click to Browse")
        if H < 92:
            return
        p.setFont(QFont(APP_FONT_NAME, 8))
        p.setPen(QPen(qcol(C.TEXT_DIM), 1))
        p.drawText(QRectF(0, cy + 24, W, 14), Qt.AlignmentFlag.AlignCenter,
                   "Images · Video · Audio · PDF · Docs · Code · Data")

    def _paint_drag_over(self, p, W, H):
        cx, cy = W / 2, H / 2
        p.setFont(QFont(APP_FONT_NAME, 20))
        p.setPen(QPen(qcol(C.PRI), 1))
        p.drawText(QRectF(0, cy - 24, W, 32), Qt.AlignmentFlag.AlignCenter, "⬇")
        p.setFont(QFont(APP_FONT_NAME, 9, QFont.Weight.DemiBold))
        p.setPen(QPen(qcol(C.PRI), 1))
        p.drawText(QRectF(0, cy + 12, W, 16), Qt.AlignmentFlag.AlignCenter, "Release to load")

    def _paint_file(self, p, W, H):
        if not self._z._current_file:
            return
        path = Path(self._z._current_file)
        cat  = _file_category(path)
        icon, icon_col = _FILE_ICONS.get(cat, _FILE_ICONS["unknown"])
        size_str = _fmt_size(path.stat().st_size)
        ext_str  = path.suffix.upper().lstrip(".") or "FILE"

        block_x, block_w = 10, 60
        p.setFont(QFont("Segoe UI Emoji", 22) if _OS == "Windows" else QFont("Arial", 22))
        p.setPen(QPen(qcol(icon_col), 1))
        p.drawText(QRectF(block_x, 0, block_w, H), Qt.AlignmentFlag.AlignCenter, icon)

        tx = block_x + block_w + 6
        tw = W - tx - 38

        p.setFont(QFont(APP_FONT_NAME, 9, QFont.Weight.DemiBold))
        p.setPen(QPen(qcol(C.WHITE), 1))
        name = path.name if len(path.name) <= 34 else path.name[:31] + "..."
        p.drawText(QRectF(tx, H * 0.18, tw, 16),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, name)

        p.setFont(QFont(APP_FONT_NAME, 8))
        p.setPen(QPen(qcol(C.TEXT_DIM), 1))
        p.drawText(QRectF(tx, H * 0.18 + 18, tw, 14),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   f"{ext_str}  ·  {size_str}")

        p.setFont(QFont(APP_FONT_NAME, 6))
        p.setPen(QPen(qcol("#1e5c6a"), 1))
        par = str(path.parent)
        if len(par) > 42: par = "…" + par[-41:]
        p.drawText(QRectF(tx, H * 0.18 + 34, tw, 12),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, par)

        p.setFont(QFont(APP_FONT_NAME, 9, QFont.Weight.Bold))
        p.setPen(QPen(qcol(C.RED, 180), 1))
        p.drawText(QRectF(W - 34, 0, 28, H), Qt.AlignmentFlag.AlignCenter, "✕")

    def mousePressEvent(self, a0):
        z = self._z
        if a0 is not None and z._current_file and a0.pos().x() > self.width() - 34:
            z.clear_file()
        elif a0 is not None:
            z.mousePressEvent(a0)


class _CameraPreview(QWidget):
    """Floating overlay that briefly shows what the camera captured."""

    _W, _H = 244, 188

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            _CameraPreview {{
                background: rgba(0, 6, 10, 242);
                border: 1px solid {C.PRI};
                border-radius: 6px;
            }}
        """)
        self.setFixedWidth(self._W)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 5, 6, 6)
        lay.setSpacing(4)

        hdr = QHBoxLayout()
        title = QLabel("◈  VISUAL INPUT")
        title.setFont(QFont(APP_FONT_NAME, 7, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {C.PRI}; background: transparent;")
        hdr.addWidget(title)
        hdr.addStretch()
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(16, 16)
        close_btn.setFont(QFont(APP_FONT_NAME, 8))
        close_btn.setStyleSheet(
            f"color: {C.TEXT_DIM}; background: transparent; border: none;"
        )
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.clicked.connect(self.hide)
        hdr.addWidget(close_btn)
        lay.addLayout(hdr)

        self._img_lbl = QLabel()
        self._img_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._img_lbl.setStyleSheet("background: transparent;")
        lay.addWidget(self._img_lbl)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)

        self.hide()

    def show_frame(self, img_bytes: bytes) -> None:
        px = QPixmap()
        px.loadFromData(img_bytes)
        if not px.isNull():
            max_w = self._W - 12
            scaled = px.scaled(
                max_w, 160,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self._img_lbl.setPixmap(scaled)
            self._img_lbl.setFixedSize(scaled.width(), scaled.height())
            self.adjustSize()
        self.show()
        self.raise_()
        self._timer.start(6_000)   # auto-dismiss after 6 s


class SetupOverlay(QWidget):
    done = pyqtSignal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            SetupOverlay {{
                background: #090e18;
                border: 1px solid rgba(99, 102, 241, 0.4);
                border-radius: 16px;
            }}
        """)

        detected = {"darwin": "mac", "windows": "windows"}.get(
            _OS.lower(), "linux"
        )
        self._sel_os = detected

        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 22, 30, 22)
        layout.setSpacing(8)

        def _lbl(txt, font_size=9, bold=False, color=C.PRI,
                 align=Qt.AlignmentFlag.AlignCenter):
            w = QLabel(txt)
            w.setAlignment(align)
            w.setFont(QFont(APP_FONT_NAME, font_size,
                            QFont.Weight.Bold if bold else QFont.Weight.Normal))
            w.setStyleSheet(f"color: {color}; background: transparent;")
            return w

        layout.addWidget(_lbl("◈  INITIALISATION REQUIRED", 13, True))
        layout.addWidget(_lbl("Configure CHARLIE before first boot.", 9, color=C.PRI_DIM))
        layout.addSpacing(6)

        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {C.BORDER};"); layout.addWidget(sep)
        layout.addSpacing(4)

        layout.addWidget(_lbl("GEMINI API KEY", 8, color=C.TEXT_DIM,
                               align=Qt.AlignmentFlag.AlignLeft))
        self._key_input = QLineEdit()
        self._key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._key_input.setPlaceholderText("Enter Gemini API key…")
        self._key_input.setFont(QFont(APP_FONT_NAME, 10))
        self._key_input.setFixedHeight(32)
        self._key_input.setStyleSheet(f"""
            QLineEdit {{
                background: #000d12; color: {C.TEXT};
                border: 1px solid {C.BORDER}; border-radius: 8px; padding: 4px 8px;
            }}
            QLineEdit:focus {{ border: 1px solid {C.PRI}; }}
        """)
        layout.addWidget(self._key_input)

        self._err_lbl = _lbl("", 8, bold=True, color=C.RED, align=Qt.AlignmentFlag.AlignLeft)
        self._err_lbl.hide()
        layout.addWidget(self._err_lbl)
        self._key_input.textChanged.connect(self._clear_error)
        layout.addSpacing(8)

        sep2 = QFrame(); sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setStyleSheet(f"color: {C.BORDER};"); layout.addWidget(sep2)
        layout.addSpacing(4)

        layout.addWidget(_lbl("OPERATING SYSTEM", 8, color=C.TEXT_DIM,
                               align=Qt.AlignmentFlag.AlignLeft))
        det_name = {"windows": "Windows", "mac": "macOS", "linux": "Linux"}[detected]
        layout.addWidget(_lbl(f"Auto-detected: {det_name}", 8, color=C.ACC2,
                               align=Qt.AlignmentFlag.AlignLeft))

        os_row = QHBoxLayout(); os_row.setSpacing(6)
        self._os_btns: dict[str, QPushButton] = {}
        for key, label in [("windows","⊞  Windows"),("mac","  macOS"),("linux","🐧  Linux")]:
            btn = QPushButton(label)
            btn.setFont(QFont(APP_FONT_NAME, 9, QFont.Weight.Bold))
            btn.setFixedHeight(32)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _, k=key: self._sel(k))
            os_row.addWidget(btn)
            self._os_btns[key] = btn
        layout.addLayout(os_row)
        self._sel(detected)
        layout.addSpacing(12)

        init_btn = QPushButton("▸  INITIALISE SYSTEMS")
        init_btn.setFont(QFont(APP_FONT_NAME, 10, QFont.Weight.Bold))
        init_btn.setFixedHeight(36)
        init_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        init_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {C.PRI};
                border: 1px solid {C.PRI_DIM}; border-radius: 8px;
            }}
            QPushButton:hover {{
                background: {C.PRI_GHO}; border: 1px solid {C.PRI};
            }}
        """)
        init_btn.clicked.connect(self._submit)
        layout.addWidget(init_btn)

    def set_error(self, msg: str):
        self._err_lbl.setText(f"⚠ {msg}")
        self._err_lbl.show()
        self._key_input.setStyleSheet(f"""
            QLineEdit {{
                background: #000d12; color: {C.TEXT};
                border: 1px solid {C.RED}; border-radius: 8px; padding: 4px 8px;
            }}
            QLineEdit:focus {{ border: 1px solid {C.RED}; }}
        """)

    def _clear_error(self):
        self._err_lbl.hide()
        self._key_input.setStyleSheet(f"""
            QLineEdit {{
                background: #000d12; color: {C.TEXT};
                border: 1px solid {C.BORDER}; border-radius: 8px; padding: 4px 8px;
            }}
            QLineEdit:focus {{ border: 1px solid {C.PRI}; }}
        """)

    def _sel(self, key: str):
        self._sel_os = key
        pal = {"windows":(C.PRI,"#001a22"),"mac":(C.ACC2,"#1a1400"),"linux":(C.GREEN,"#001a0d")}
        for k, btn in self._os_btns.items():
            if k == key:
                fg, bg = pal[k]
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background: {fg}; color: {bg};
                        border: none; border-radius: 8px; font-weight: bold;
                    }}
                """)
            else:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background: #000d12; color: {C.TEXT_DIM};
                        border: 1px solid {C.BORDER}; border-radius: 8px;
                    }}
                    QPushButton:hover {{ color: {C.TEXT}; border: 1px solid {C.BORDER_B}; }}
                """)

    def _submit(self):
        key = self._key_input.text().strip()
        if not key or len(key) < 10:
            self.set_error("Gemini API key is required (minimum 10 characters).")
            return
        self._clear_error()
        self.done.emit(key, self._sel_os)


class HueWheel(QWidget):
    """
    Circular colour picker. The user drags the handle (small white circle)
    around the wheel to choose from ALL hues. The filled circle in the centre
    is a live preview of the selected colour.
    """

    hue_picked    = pyqtSignal(str)   # while dragging (live)
    hue_committed = pyqtSignal(str)   # when the handle is released

    _RING = 16   # ring thickness (px)

    def __init__(self, initial_hex: str = DEFAULT_UI_COLOR, parent=None):
        super().__init__(parent)
        self.setFixedSize(148, 148)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._hue  = 0.53
        self._drag = False
        self.set_color(initial_hex)

    # ── API ──────────────────────────────────────────────────────────────────
    def color(self) -> str:
        return QColor.fromHsvF(self._hue, 1.0, 1.0).name()

    def set_color(self, hex_str: str):
        c = QColor((hex_str or "").strip())
        if c.isValid() and c.hsvHueF() >= 0:
            self._hue = c.hsvHueF()
            self.update()

    # ── geometry helpers ─────────────────────────────────────────────────────
    def _ring_rect(self) -> QRectF:
        m = self._RING / 2 + 3
        return QRectF(self.rect()).adjusted(m, m, -m, -m)

    def _hue_from_pos(self, pos: QPointF) -> float:
        c  = QRectF(self.rect()).center()
        dx = pos.x() - c.x()
        dy = c.y() - pos.y()          # screen y goes down — flip to math axis
        ang = math.atan2(dy, dx)      # [-π, π], counter-clockwise
        return (ang / (2 * math.pi)) % 1.0

    # ── drawing ──────────────────────────────────────────────────────────────
    def paintEvent(self, a0):
        p = QPainter(self)
        if not p.isActive():
            return
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect   = self._ring_rect()
        center = rect.center()

        grad = QConicalGradient(center, 0)
        for i in range(0, 361, 20):
            grad.setColorAt(i / 360.0, QColor.fromHsvF((i % 360) / 360.0, 1.0, 1.0))
        p.setPen(QPen(QBrush(grad), self._RING))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(rect)

        # centre preview circle
        preview = QColor.fromHsvF(self._hue, 1.0, 1.0)
        inner   = rect.adjusted(30, 30, -30, -30)
        p.setPen(QPen(qcol(C.BORDER_B), 1))
        p.setBrush(QBrush(preview))
        p.drawEllipse(inner)

        # draggable handle
        r   = rect.width() / 2
        ang = self._hue * 2 * math.pi
        hx  = center.x() + r * math.cos(ang)
        hy  = center.y() - r * math.sin(ang)
        p.setPen(QPen(QColor("#00060a"), 2))
        p.setBrush(QBrush(QColor("#ffffff")))
        p.drawEllipse(QPointF(hx, hy), 7.5, 7.5)
        p.end()

    # ── fare ─────────────────────────────────────────────────────────────────
    def mousePressEvent(self, a0):
        if a0 is not None:
            self._drag = True
            self._hue  = self._hue_from_pos(a0.position())
            self.update()
            self.hue_picked.emit(self.color())

    def mouseMoveEvent(self, a0):
        if self._drag and a0 is not None:
            self._hue = self._hue_from_pos(a0.position())
            self.update()
            self.hue_picked.emit(self.color())

    def mouseReleaseEvent(self, a0):
        if self._drag:
            self._drag = False
            self.hue_committed.emit(self.color())


class CustomizeOverlay(QWidget):
    """Floating overlay — change assistant name, user name, UI colour and voice."""

    saved = pyqtSignal(str, str, str, str, str, object)
    _OW, _OH = 480, 760

    def __init__(self, assistant_name="CHARLIE", user_name="",
                 ui_color=DEFAULT_UI_COLOR, voice="", persona="male", parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            CustomizeOverlay {{
                background: #090e18;
                border: 1px solid rgba(99, 102, 241, 0.4);
                border-radius: 16px;
            }}
        """)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 18, 24, 18)
        lay.setSpacing(8)

        def _lbl(txt, fs=9, bold=False, color=C.PRI, align=Qt.AlignmentFlag.AlignCenter):
            w = QLabel(txt); w.setAlignment(align)
            w.setFont(QFont(APP_FONT_NAME, fs,
                            QFont.Weight.Bold if bold else QFont.Weight.Normal))
            w.setStyleSheet(f"color: {color}; background: transparent;")
            return w

        _fs = (f"QLineEdit {{ background: rgba(255, 255, 255, 0.04); color: {C.TEXT}; "
               f"border: 1px solid rgba(255, 255, 255, 0.12); border-radius: 8px; padding: 4px 8px; }}"
               f"QLineEdit:focus {{ border: 1px solid {C.PRI}; background: rgba(255, 255, 255, 0.07); }}")

        hdr_row = QHBoxLayout()
        hdr_row.addWidget(_lbl("⚙  CUSTOMISE ASSISTANT", 12, True, align=Qt.AlignmentFlag.AlignLeft))
        hdr_row.addStretch()
        cust_close_btn = QPushButton("✕")
        cust_close_btn.setFixedSize(26, 26)
        cust_close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cust_close_btn.setToolTip("Close")
        cust_close_btn.setStyleSheet(f"""
            QPushButton {{
                color: #ffffff;
                background: rgba(255, 255, 255, 0.1);
                border: 1px solid rgba(255, 255, 255, 0.2);
                border-radius: 13px;
                font-size: 13px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                color: #ffffff;
                background: #ef4444;
                border-color: #ef4444;
            }}
        """)
        cust_close_btn.clicked.connect(self._cancel)
        hdr_row.addWidget(cust_close_btn)
        lay.addLayout(hdr_row)
        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {C.BORDER}; margin: 2px 0;")
        lay.addWidget(sep)

        lay.addWidget(_lbl("ASSISTANT NAME", 8, color=C.TEXT_DIM,
                            align=Qt.AlignmentFlag.AlignLeft))
        self._name_input = QLineEdit(assistant_name)
        self._name_input.setFont(QFont(APP_FONT_NAME, 10))
        self._name_input.setFixedHeight(32)
        self._name_input.setStyleSheet(_fs)
        lay.addWidget(self._name_input)

        lay.addSpacing(4)
        lay.addWidget(_lbl("YOUR NAME  (leave blank for default sir / efendim)", 8,
                            color=C.TEXT_DIM, align=Qt.AlignmentFlag.AlignLeft))
        self._user_input = QLineEdit(user_name)
        self._user_input.setPlaceholderText("e.g.  Tony   (leave blank for auto)")
        self._user_input.setFont(QFont(APP_FONT_NAME, 10))
        self._user_input.setFixedHeight(32)
        self._user_input.setStyleSheet(_fs)
        lay.addWidget(self._user_input)

        # ── Assistant voice — Gemini prebuilt voices ─────────────────────────
        # Names are language-neutral proper nouns, so the row reads the same in
        # every locale. Selecting one and applying rebuilds the Live session.
        from memory.config_manager import (
            ASSISTANT_PERSONAS, AVAILABLE_VOICES, DEFAULT_VOICE, VOICE_STYLES,
            get_persona_voice, voice_matches_persona,
        )
        lay.addSpacing(4)
        lay.addWidget(_lbl("ASSISTANT PROFILE", 8, color=C.TEXT_DIM,
                            align=Qt.AlignmentFlag.AlignLeft))
        self._sel_persona = persona if persona in ASSISTANT_PERSONAS else "male"
        self._initial_persona = self._sel_persona
        self._persona_voices = {
            key: get_persona_voice(key) for key in ASSISTANT_PERSONAS
        }
        if voice in AVAILABLE_VOICES and voice_matches_persona(voice, self._sel_persona):
            self._persona_voices[self._sel_persona] = voice
        self.on_persona_preview = None
        self._persona_btns: dict[str, QPushButton] = {}
        profile_row = QHBoxLayout(); profile_row.setSpacing(6)
        for key, label in (("male", "CLASSIC ASSISTANT"), ("female", "FEMALE FACE + VOICE")):
            button = QPushButton(label)
            button.setCheckable(True)
            button.setFixedHeight(30)
            button.setFont(QFont(APP_FONT_NAME, 8, QFont.Weight.DemiBold))
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _=False, profile=key: self._on_persona_pick(profile))
            self._persona_btns[key] = button
            profile_row.addWidget(button)
        lay.addLayout(profile_row)
        self._refresh_persona_btns()

        lay.addWidget(_lbl("ASSISTANT VOICE", 8, color=C.TEXT_DIM,
                            align=Qt.AlignmentFlag.AlignLeft))
        self._sel_voice = self._persona_voices.get(self._sel_persona, DEFAULT_VOICE)
        if self._sel_voice not in AVAILABLE_VOICES:
            self._sel_voice = DEFAULT_VOICE
        self._voice_combo = QComboBox()
        self._voice_combo.setFixedHeight(32)
        self._voice_combo.setFont(QFont(APP_FONT_NAME, 9))
        self._voice_combo.setCursor(Qt.CursorShape.PointingHandCursor)
        self._voice_combo.setStyleSheet(_fs.replace("QLineEdit", "QComboBox"))
        self._voice_combo.currentIndexChanged.connect(self._on_voice_combo_changed)
        lay.addWidget(self._voice_combo)
        self._voice_hint = _lbl("", 8, color=C.TEXT_MED,
                                align=Qt.AlignmentFlag.AlignLeft)
        lay.addWidget(self._voice_hint)
        self._refresh_voice_btns()

        # Natural speech direction is profile-scoped, unlike the avatar voice.
        # This lets each family member keep their own pace and language style.
        from memory.personal_hub import load_hub
        speech = load_hub().get("speech", {})
        lay.addWidget(_lbl("NATURAL SPEAKING STYLE", 8, color=C.TEXT_DIM,
                            align=Qt.AlignmentFlag.AlignLeft))
        speech_row = QHBoxLayout(); speech_row.setSpacing(6)
        self._speech_style_combo = QComboBox()
        for label, value in (("Warm", "warm"), ("Friendly", "friendly"),
                             ("Calm", "calm"), ("Professional", "professional"),
                             ("Energetic", "energetic"), ("Companion", "companion")):
            self._speech_style_combo.addItem(label, value)
        self._speech_style_combo.setCurrentIndex(max(
            0, self._speech_style_combo.findData(speech.get("style", "warm"))))
        self._pace_combo = QComboBox()
        for label, value in (("Slower", "slow"), ("Natural pace", "natural"),
                             ("Faster", "fast")):
            self._pace_combo.addItem(label, value)
        self._pace_combo.setCurrentIndex(max(
            0, self._pace_combo.findData(speech.get("pace", "natural"))))
        for combo in (self._speech_style_combo, self._pace_combo):
            combo.setFixedHeight(30); combo.setStyleSheet(_fs.replace("QLineEdit", "QComboBox"))
            speech_row.addWidget(combo, 1)
        lay.addLayout(speech_row)

        speech_row2 = QHBoxLayout(); speech_row2.setSpacing(6)
        self._language_combo = QComboBox()
        try:
            from core.languages import get_language_choices_ui
            _lang_items = get_language_choices_ui()
        except Exception:
            _lang_items = (("Auto language", "auto"), ("English", "english"),
                           ("Hindi", "hindi"), ("Hinglish", "hinglish"),
                           ("Marathi", "marathi"), ("Bengali", "bengali"))
        for label, value in _lang_items:
            self._language_combo.addItem(label, value)
        self._language_combo.setCurrentIndex(max(
            0, self._language_combo.findData(speech.get("language", "auto"))))
        # Voice gender toggle
        self._voice_gender_combo = QComboBox()
        for label, value in (("♀ Female Voice", "female"), ("♂ Male Voice", "male")):
            self._voice_gender_combo.addItem(label, value)
        self._voice_gender_combo.setCurrentIndex(max(
            0, self._voice_gender_combo.findData(speech.get("voice_gender", "female"))))
        self._address_combo = QComboBox()
        for label, value in (("Address occasionally", "occasional"),
                             ("Use my name", "name"), ("Casual — no sir", "casual"),
                             ("No form of address", "none")):
            self._address_combo.addItem(label, value)
        self._address_combo.setCurrentIndex(max(
            0, self._address_combo.findData(speech.get("address", "occasional"))))
        for combo in (self._language_combo, self._voice_gender_combo, self._address_combo):
            combo.setFixedHeight(30); combo.setStyleSheet(_fs.replace("QLineEdit", "QComboBox"))
            speech_row2.addWidget(combo, 1)
        lay.addLayout(speech_row2)

        # ── UI colour — colour wheel ─────────────────────────────────────────
        lay.addSpacing(4)
        clr_hdr = QHBoxLayout()
        clr_hdr.addWidget(_lbl("UI COLOUR  —  drag the handle", 8,
                               color=C.TEXT_DIM, align=Qt.AlignmentFlag.AlignLeft))
        clr_hdr.addStretch()
        df_btn = QPushButton("DEFAULT")
        df_btn.setFixedSize(64, 20)
        df_btn.setFont(QFont(APP_FONT_NAME, 7, QFont.Weight.Bold))
        df_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        df_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {C.TEXT_MED};
                border: 1px solid {C.BORDER}; border-radius: 8px;
            }}
            QPushButton:hover {{ color: {C.TEXT}; border-color: {C.BORDER_B}; }}
        """)
        df_btn.clicked.connect(lambda: self._set_color(DEFAULT_UI_COLOR))
        clr_hdr.addWidget(df_btn)
        lay.addLayout(clr_hdr)

        self._initial_color = (ui_color or DEFAULT_UI_COLOR).strip().lower()
        self._sel_color     = self._initial_color
        self.on_preview     = None   # callable(hex) — live preview; MainWindow wires it

        self._wheel = HueWheel(self._sel_color)
        wheel_row = QHBoxLayout()
        wheel_row.addStretch(); wheel_row.addWidget(self._wheel); wheel_row.addStretch()
        lay.addLayout(wheel_row)
        self._wheel.hue_picked.connect(self._on_wheel_pick)
        self._wheel.hue_committed.connect(self._on_wheel_commit)

        self._hex_input = QLineEdit(self._sel_color)
        self._hex_input.setPlaceholderText("#00d4ff   (custom hex colour)")
        self._hex_input.setFont(QFont(APP_FONT_NAME, 10))
        self._hex_input.setFixedHeight(28)
        self._hex_input.setStyleSheet(_fs)
        self._hex_input.textEdited.connect(self._on_hex_edited)
        lay.addWidget(self._hex_input)

        lay.addSpacing(6)
        btn_row = QHBoxLayout(); btn_row.setSpacing(8)

        save_btn = QPushButton("▸  APPLY CHANGES")
        save_btn.setFixedHeight(34)
        save_btn.setFont(QFont(APP_FONT_NAME, 9, QFont.Weight.Bold))
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_btn.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {C.PRI}, stop:1 #6366f1);
                color: #ffffff; border: none; border-radius: 8px; font-weight: bold;
            }}
            QPushButton:hover {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #a78bfa, stop:1 #4f46e5);
            }}
        """)
        save_btn.clicked.connect(self._save)
        btn_row.addWidget(save_btn)

        cancel_btn = QPushButton("CANCEL")
        cancel_btn.setFixedHeight(34)
        cancel_btn.setFont(QFont(APP_FONT_NAME, 9))
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.setStyleSheet(f"""
            QPushButton {{
                background: rgba(255, 255, 255, 0.05); color: {C.TEXT_MED};
                border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 8px;
            }}
            QPushButton:hover {{ color: #ffffff; background: rgba(255, 255, 255, 0.08); }}
        """)
        cancel_btn.clicked.connect(self._cancel)
        btn_row.addWidget(cancel_btn)
        lay.addLayout(btn_row)

    # ── voice selection ──────────────────────────────────────────────────────
    def _on_persona_pick(self, persona: str):
        self._sel_persona = persona
        self._sel_voice = self._persona_voices[persona]
        self._refresh_persona_btns()
        self._refresh_voice_btns()
        if self.on_persona_preview:
            self.on_persona_preview(persona)

    def _refresh_persona_btns(self):
        for name, button in self._persona_btns.items():
            on = name == self._sel_persona
            button.setChecked(on)
            if on:
                button.setStyleSheet(f"""
                    QPushButton {{ background: {C.PRI_GHO}; color: {C.PRI};
                        border: 1px solid {C.PRI}; border-radius: 8px; }}""")
            else:
                button.setStyleSheet(f"""
                    QPushButton {{ background: transparent; color: {C.TEXT_MED};
                        border: 1px solid {C.BORDER}; border-radius: 8px; }}
                    QPushButton:hover {{ color: {C.TEXT}; border-color: {C.BORDER_B}; }}""")

    def _on_voice_pick(self, name: str):
        self._sel_voice = name
        self._persona_voices[self._sel_persona] = name
        self._refresh_voice_btns()

    def _on_voice_combo_changed(self, index: int):
        name = self._voice_combo.itemData(index)
        if name:
            self._on_voice_pick(str(name))

    def _refresh_voice_btns(self):
        """Show only voices whose official gender matches the active profile."""
        from memory.config_manager import VOICE_STYLES, voices_for_persona
        self._voice_combo.blockSignals(True)
        self._voice_combo.clear()
        for voice in voices_for_persona(self._sel_persona):
            self._voice_combo.addItem(f"{voice}  —  {VOICE_STYLES[voice]}", voice)
        index = self._voice_combo.findData(self._sel_voice)
        self._voice_combo.setCurrentIndex(max(0, index))
        selected = self._voice_combo.currentData()
        if selected:
            self._sel_voice = str(selected)
            self._persona_voices[self._sel_persona] = self._sel_voice
        self._voice_combo.blockSignals(False)
        self._voice_hint.setText(
            f"{self._sel_persona.title()} profile will use the matching {self._sel_persona} voice "
            f"{self._sel_voice}: "
            f"{VOICE_STYLES.get(self._sel_voice, 'Natural')}.")

    # ── colour flow ──────────────────────────────────────────────────────────
    def _set_color(self, hx: str, update_wheel: bool = True, preview: bool = True):
        """Updates the selected colour; hex box + wheel stay in sync, theme is live-previewed."""
        self._sel_color = hx.strip().lower()
        self._hex_input.blockSignals(True)
        self._hex_input.setText(self._sel_color)
        self._hex_input.blockSignals(False)
        if update_wheel:
            self._wheel.set_color(self._sel_color)
        if preview and self.on_preview:
            self.on_preview(self._sel_color)

    def _on_wheel_pick(self, hx: str):
        # While dragging: update the hex box, don't apply the theme yet
        self._sel_color = hx
        self._hex_input.blockSignals(True)
        self._hex_input.setText(hx)
        self._hex_input.blockSignals(False)

    def _on_wheel_commit(self, hx: str):
        # Handle released → live-preview the whole interface
        self._set_color(hx, update_wheel=False)

    def _on_hex_edited(self, text: str):
        t = text.strip().lower()
        if t.startswith("#") and len(t) == 7:
            try:
                int(t[1:], 16)
            except ValueError:
                return
            self._set_color(t, update_wheel=True, preview=True)

    def _cancel(self):
        # If a preview was applied, revert to the colour from launch
        if self.on_preview and self._sel_color != self._initial_color:
            self.on_preview(self._initial_color)
        if self.on_persona_preview:
            self.on_persona_preview(self._initial_persona)
        self.hide()

    def _save(self):
        name = self._name_input.text().strip() or "CHARLIE"
        user = self._user_input.text().strip()
        preferences = {
            "persona_voices": dict(self._persona_voices),
            "speech": {
                "style": self._speech_style_combo.currentData(),
                "pace": self._pace_combo.currentData(),
                "language": self._language_combo.currentData(),
                "address": self._address_combo.currentData(),
                "voice_gender": self._voice_gender_combo.currentData(),
            },
        }
        self.saved.emit(name, user, self._sel_color or DEFAULT_UI_COLOR, self._sel_voice,
                        self._sel_persona, preferences)
        self.hide()



_APP_LOGOS_SVG = {
    "github_integration": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="36" height="36" viewBox="0 0 36 36" fill="none">'
        '<rect width="36" height="36" rx="9" fill="#181717"/>'
        '<path fill-rule="evenodd" clip-rule="evenodd" d="M18 7.5C12.2 7.5 7.5 12.2 7.5 18c0 4.64 3.01 8.58 7.19 9.97.53.1.72-.23.72-.51v-1.98c-2.92.64-3.53-1.24-3.53-1.24-.48-1.22-1.17-1.55-1.17-1.55-.95-.65.07-.64.07-.64 1.05.07 1.61 1.08 1.61 1.08.94 1.6 2.45 1.14 3.05.88.1-.68.36-1.14.67-1.41-2.33-.27-4.78-1.17-4.78-5.19 0-1.15.41-2.08 1.08-2.82-.11-.26-.47-1.33.1-2.79 0 0 .88-.28 2.89 1.08.84-.23 1.74-.35 2.64-.35.9 0 1.8.12 2.64.35 2.01-1.36 2.89-1.08 2.89-1.08.57 1.46.21 2.53.1 2.79.67.74 1.08 1.67 1.08 2.82 0 4.04-2.46 4.92-4.8 5.18.37.33.71.97.71 1.94v2.88c0 .28.19.61.73.51C25.49 26.58 28.5 22.64 28.5 18c0-5.8-4.7-10.5-10.5-10.5z" fill="#FFFFFF"/>'
        '</svg>'
    ),
    "google_workspace": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="36" height="36" viewBox="0 0 36 36" fill="none">'
        '<rect width="36" height="36" rx="9" fill="#FFFFFF"/>'
        '<path d="M26.4 18.2c0-.66-.06-1.3-.17-1.92H18v3.63h4.72c-.2 1.08-.82 2-1.74 2.62v2.17h2.8c1.64-1.5 2.62-3.7 2.62-6.5z" fill="#4285F4"/>'
        '<path d="M18 26.7c2.37 0 4.36-.78 5.82-2.13l-2.8-2.17c-.79.53-1.8.84-3.02.84-2.33 0-4.3-1.57-5.01-3.69H10.1v2.24C11.55 24.64 14.54 26.7 18 26.7z" fill="#34A853"/>'
        '<path d="M12.99 19.55c-.18-.53-.29-1.09-.29-1.55s.11-1.02.29-1.55v-2.24H10.1A8.7 8.7 0 0 0 9.2 18c0 1.4.34 2.73.9 3.79l2.89-2.24z" fill="#FBBC05"/>'
        '<path d="M18 12.72c1.29 0 2.45.44 3.36 1.31l2.52-2.52C22.36 10.1 20.37 9.2 18 9.2c-3.46 0-6.45 2.06-7.9 4.99l2.89 2.24c.71-2.12 2.68-3.71 5.01-3.71z" fill="#EA4335"/>'
        '</svg>'
    ),
    "slack_integration": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="36" height="36" viewBox="0 0 36 36" fill="none">'
        '<rect width="36" height="36" rx="9" fill="#3F0E40"/>'
        '<path d="M14.5 9.5a2 2 0 1 0-2 2h2v-2zm1 0a2 2 0 0 0 4 0v-2a2 2 0 0 0-4 0v2z" fill="#36C5F0"/>'
        '<path d="M22.5 14.5a2 2 0 1 0-2-2v2h2zm0 1a2 2 0 0 0 0 4h2a2 2 0 0 0 0-4h-2z" fill="#2EB67D"/>'
        '<path d="M19.5 22.5a2 2 0 1 0 2-2h-2v2zm-1 0a2 2 0 0 0-4 0v2a2 2 0 0 0 4 0v-2z" fill="#ECB22E"/>'
        '<path d="M11.5 19.5a2 2 0 1 0 2 2v-2h-2zm0-1a2 2 0 0 0 0-4h-2a2 2 0 0 0 0 4h2z" fill="#E01E5A"/>'
        '</svg>'
    ),
    "notion_integration": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="36" height="36" viewBox="0 0 36 36" fill="none">'
        '<rect width="36" height="36" rx="9" fill="#FFFFFF"/>'
        '<path d="M10.8 10.2c.5.4.8.4 1.7.3l9.8-.6c.8-.1 1-.2 1.3-.6.4-.5.2-1.2 0-1.5-.3-.3-.8-.4-1.7-.3l-9.8.6c-.9.1-1.3.2-1.7.6-.3.4-.3 1 .4 1.5z" fill="#000000"/>'
        '<path fill-rule="evenodd" clip-rule="evenodd" d="M11.5 12.3c-.5 0-.7.3-.7.7v11.5c0 .5.3.8.8.8.5 0 1.3-.1 1.9-.2V13.6l8.2 11.5c.8-.1 1.7-.2 2.4-.3.3-.1.5-.3.5-.8V13c0-.5-.3-.8-.8-.8-.5 0-1.1.1-1.7.2v10.4L13.9 12.5c-.7.1-1.8.2-2.4-.2z" fill="#000000"/>'
        '</svg>'
    ),
    "jira_integration": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="36" height="36" viewBox="0 0 36 36" fill="none">'
        '<rect width="36" height="36" rx="9" fill="#0052CC"/>'
        '<path d="M18 8.5a5 5 0 0 0-5 5v2.5h2.5a2.5 2.5 0 0 1 2.5 2.5V26.5a5 5 0 0 0 5-5v-8a5 5 0 0 0-5-5z" fill="#2684FF"/>'
        '<path d="M13 13.5a5 5 0 0 0-5 5v8h2.5a2.5 2.5 0 0 1 2.5-2.5v-10.5z" fill="#FFFFFF" fill-opacity="0.8"/>'
        '<path d="M18 18.5a2.5 2.5 0 0 0-2.5-2.5H13v8h2.5A2.5 2.5 0 0 0 18 21.5v-3z" fill="#FFFFFF"/>'
        '</svg>'
    ),
    "trello_integration": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="36" height="36" viewBox="0 0 36 36" fill="none">'
        '<rect width="36" height="36" rx="9" fill="#0079BF"/>'
        '<rect x="10.5" y="10.5" width="6.5" height="15" rx="1.5" fill="#FFFFFF"/>'
        '<rect x="19" y="10.5" width="6.5" height="9.5" rx="1.5" fill="#FFFFFF"/>'
        '</svg>'
    ),
    "discord_integration": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="36" height="36" viewBox="0 0 36 36" fill="none">'
        '<rect width="36" height="36" rx="9" fill="#5865F2"/>'
        '<path d="M25.7 11.8a16.8 16.8 0 0 0-4.1-1.3.1.1 0 0 0-.1.1c-.2.4-.4.8-.6 1.2-1.6-.2-3.2-.2-4.8 0-.2-.4-.4-.8-.6-1.2 0-.1-.1-.1-.1-.1a16.8 16.8 0 0 0-4.1 1.3c0 0-.1 0-.1.1-2.6 3.9-3.3 7.7-2.9 11.5 0 .1 0 .1.1.1 1.7 1.3 3.4 2 5.1 2.5.1 0 .1 0 .2-.1.4-.5.7-1.1 1-1.6 0-.1 0-.1-.1-.1-1.1-.4-1.8-.9-2.2-1.4 0 0 0-.1 0-.1.1 0 .2.1.2.1 3.3 1.5 6.8 1.5 10 0 .1 0 .2 0 .2-.1 0 0 0 .1 0 .1-.5.5-1.2 1-2.2 1.4 0 0-.1.1-.1.1.3.6.7 1.1 1 1.6 0 .1.1.1.2.1 1.7-.5 3.4-1.3 5.1-2.5.1 0 .1-.1.1-.1.6-4.4-.8-8.2-3.3-11.5 0-.1 0-.1-.1-.1zM14.5 20.2c-1 0-1.8-.9-1.8-2 0-1.1.8-2 1.8-2 1 0 1.8.9 1.8 2 0 1.1-.8 2-1.8 2zm7 0c-1 0-1.8-.9-1.8-2 0-1.1.8-2 1.8-2 1 0 1.8.9 1.8 2 0 1.1-.8 2-1.8 2z" fill="#FFFFFF"/>'
        '</svg>'
    ),
    "telegram_integration": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="36" height="36" viewBox="0 0 36 36" fill="none">'
        '<rect width="36" height="36" rx="9" fill="#229ED9"/>'
        '<path d="M26.2 11.5L23.2 26c-.2 1-.8 1.3-1.6.8l-4.7-3.5-2.3 2.2c-.3.3-.5.5-.9.5l.3-4.8 8.8-8c.4-.4-.1-.5-.6-.2L11.3 19.4l-4.6-1.5c-1-.3-1-1 .2-1.5L25 9.5c.8-.4 1.5.2 1.2 2z" fill="#FFFFFF"/>'
        '</svg>'
    ),
    "spotify_integration": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="36" height="36" viewBox="0 0 36 36" fill="none">'
        '<rect width="36" height="36" rx="9" fill="#121212"/>'
        '<circle cx="18" cy="18" r="10.5" fill="#1DB954"/>'
        '<path d="M22.8 21.2c-.2.3-.5.4-.8.2-2.1-1.3-4.8-1.5-7.9-.8-.3.1-.6-.1-.7-.4-.1-.3.1-.6.4-.7 3.4-.8 6.4-.5 8.7 1 .3.2.4.5.3.7zm1.1-2.4c-.3.4-.7.5-1.1.3-2.4-1.5-6.1-1.9-8.9-1-.4.1-.8-.1-.9-.5-.1-.4.1-.8.5-.9 3.2-1 7.3-.5 10.1 1.2.4.2.5.6.3.9zm.1-2.5c-2.9-1.7-7.7-1.9-10.5-1-.5.1-.9-.1-1.1-.6-.1-.5.1-.9.6-1.1 3.2-1 8.5-.8 11.8 1.1.4.3.6.8.3 1.3-.3.4-.8.5-1.1.3z" fill="#FFFFFF"/>'
        '</svg>'
    ),
    "zoom_integration": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="36" height="36" viewBox="0 0 36 36" fill="none">'
        '<rect width="36" height="36" rx="9" fill="#2D8CFF"/>'
        '<path d="M10.5 14c0-1.38 1.12-2.5 2.5-2.5h6.5c1.38 0 2.5 1.12 2.5 2.5v8c0 1.38-1.12 2.5-2.5 2.5H13c-1.38 0-2.5-1.12-2.5-2.5v-8zm11.5 2l3.8-2.6c.4-.3.9 0 .9.5v8.2c0 .5-.5.8-.9.5L22 20V16z" fill="#FFFFFF"/>'
        '</svg>'
    ),
    "microsoft365_integration": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="36" height="36" viewBox="0 0 36 36" fill="none">'
        '<rect width="36" height="36" rx="9" fill="#18181B"/>'
        '<rect x="9.5" y="9.5" width="8" height="8" rx="1" fill="#F25022"/>'
        '<rect x="18.5" y="9.5" width="8" height="8" rx="1" fill="#7FBA00"/>'
        '<rect x="9.5" y="18.5" width="8" height="8" rx="1" fill="#00A4EF"/>'
        '<rect x="18.5" y="18.5" width="8" height="8" rx="1" fill="#FFB900"/>'
        '</svg>'
    ),
    "whatsapp_integration": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="36" height="36" viewBox="0 0 36 36" fill="none">'
        '<rect width="36" height="36" rx="9" fill="#25D366"/>'
        '<path fill-rule="evenodd" clip-rule="evenodd" d="M18 8.5a9.5 9.5 0 0 0-8.2 14.3L8.5 27.5l4.8-1.2A9.5 9.5 0 1 0 18 8.5zm4.7 13.4c-.2.6-1.1 1.1-1.6 1.1-.5 0-1 .2-3.4-.8-2.9-1.2-4.7-4.1-4.8-4.3-.1-.2-1.1-1.5-1.1-2.9 0-1.4.8-2.1 1-2.4.3-.3.6-.4.9-.4.2 0 .4 0 .6.1.2.1.5 1 .6 1.2.1.2.1.4 0 .6-.1.2-.2.3-.3.4-.1.2-.3.3-.1.6.2.4.8 1.3 1.7 2.1 1.1 1 2.1 1.4 2.5 1.6.3.1.5.1.7-.1.2-.2.8-.9 1-1.2.2-.3.4-.3.7-.2.3.1 1.7.8 2 1 .3.2.5.3.6.4.1.2.1.9-.3 1.5z" fill="#FFFFFF"/>'
        '</svg>'
    ),
    "workspace_helper": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="36" height="36" viewBox="0 0 36 36" fill="none">'
        '<rect width="36" height="36" rx="9" fill="#1E1E2E"/>'
        '<path d="M13.5 13.5L9 18l4.5 4.5" stroke="#38BDF8" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/>'
        '<path d="M22.5 13.5L27 18l-4.5 4.5" stroke="#38BDF8" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/>'
        '<path d="M19.5 11.5L16.5 24.5" stroke="#A855F7" stroke-width="2.4" stroke-linecap="round"/>'
        '</svg>'
    ),
}

_STORE_LOGOS_SVG = {
    "weather_radar": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="36" height="36" viewBox="0 0 36 36" fill="none">'
        '<rect width="36" height="36" rx="9" fill="#0284C7"/>'
        '<circle cx="21" cy="15" r="4" fill="#FBBF24"/>'
        '<path d="M12 23a4 4 0 0 1-1-7.87 5.5 5.5 0 0 1 10.74-1.39A4.5 4.5 0 0 1 25.5 23H12z" fill="#FFFFFF"/>'
        '<path d="M13 25l-1 3m5-3l-1 3m5-3l-1 3" stroke="#38BDF8" stroke-width="1.8" stroke-linecap="round"/>'
        '</svg>'
    ),
    "crypto_market": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="36" height="36" viewBox="0 0 36 36" fill="none">'
        '<rect width="36" height="36" rx="9" fill="#F7931A"/>'
        '<path d="M21.5 16.2c.4-.8.2-1.7-.5-2.2-.6-.4-1.4-.5-2.2-.4V11h-1.5v2.4h-1.1V11h-1.5v2.5H12v1.8h1.2c.5 0 .7.2.7.6v6.2c0 .4-.2.6-.7.6H12v1.8h2.7v2.5h1.5v-2.5h1.1v2.5h1.5v-2.6c2.1-.2 3.4-1.3 3.6-3.1.2-1.3-.5-2.4-1.6-2.9zm-4.3-1.6h1.7c1 0 1.6.4 1.6 1.2 0 .8-.6 1.2-1.6 1.2h-1.7v-2.4zm2 7.3h-2v-2.6h2c1.1 0 1.8.4 1.8 1.3 0 .9-.7 1.3-1.8 1.3z" fill="#FFFFFF"/>'
        '</svg>'
    ),
    "web_scraper": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="36" height="36" viewBox="0 0 36 36" fill="none">'
        '<rect width="36" height="36" rx="9" fill="#0D9488"/>'
        '<rect x="9" y="10" width="18" height="15" rx="3" stroke="#FFFFFF" stroke-width="2" fill="none"/>'
        '<path d="M9 14h18" stroke="#FFFFFF" stroke-width="1.5"/>'
        '<circle cx="12" cy="12" r="1" fill="#FFFFFF"/>'
        '<circle cx="14.5" cy="12" r="1" fill="#FFFFFF"/>'
        '<circle cx="17" cy="12" r="1" fill="#FFFFFF"/>'
        '<path d="M14 19l2.5 2.5L22 17" stroke="#2DD4BF" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>'
        '</svg>'
    ),
    "docker_manager": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="36" height="36" viewBox="0 0 36 36" fill="none">'
        '<rect width="36" height="36" rx="9" fill="#2496ED"/>'
        '<rect x="13.5" y="11" width="2.5" height="2" rx="0.3" fill="#FFFFFF"/>'
        '<rect x="16.5" y="11" width="2.5" height="2" rx="0.3" fill="#FFFFFF"/>'
        '<rect x="10.5" y="13.5" width="2.5" height="2" rx="0.3" fill="#FFFFFF"/>'
        '<rect x="13.5" y="13.5" width="2.5" height="2" rx="0.3" fill="#FFFFFF"/>'
        '<rect x="16.5" y="13.5" width="2.5" height="2" rx="0.3" fill="#FFFFFF"/>'
        '<rect x="19.5" y="13.5" width="2.5" height="2" rx="0.3" fill="#FFFFFF"/>'
        '<rect x="7.5" y="16" width="2.5" height="2" rx="0.3" fill="#FFFFFF"/>'
        '<rect x="10.5" y="16" width="2.5" height="2" rx="0.3" fill="#FFFFFF"/>'
        '<rect x="13.5" y="16" width="2.5" height="2" rx="0.3" fill="#FFFFFF"/>'
        '<rect x="16.5" y="16" width="2.5" height="2" rx="0.3" fill="#FFFFFF"/>'
        '<rect x="19.5" y="16" width="2.5" height="2" rx="0.3" fill="#FFFFFF"/>'
        '<path d="M6 19.5c.5 4 4.5 7.5 12 7.5 8 0 12-4.5 12.5-9 0 0-2.5.5-5 0-1-1.5-2.5-3-5.5-3v4.5H6z" fill="#FFFFFF"/>'
        '<circle cx="10" cy="22" r="0.8" fill="#2496ED"/>'
        '</svg>'
    ),
    "home_assistant": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="36" height="36" viewBox="0 0 36 36" fill="none">'
        '<rect width="36" height="36" rx="9" fill="#18B0F2"/>'
        '<path d="M18 9l10 8.5v8.5a2 2 0 0 1-2 2h-4v-6h-8v6H10a2 2 0 0 1-2-2v-8.5L18 9z" fill="#FFFFFF"/>'
        '<circle cx="18" cy="18" r="2" fill="#18B0F2"/>'
        '<line x1="18" y1="18" x2="18" y2="13" stroke="#18B0F2" stroke-width="1.5"/>'
        '<line x1="18" y1="18" x2="14" y2="20" stroke="#18B0F2" stroke-width="1.5"/>'
        '<line x1="18" y1="18" x2="22" y2="20" stroke="#18B0F2" stroke-width="1.5"/>'
        '</svg>'
    ),
    "pdf_toolkit": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="36" height="36" viewBox="0 0 36 36" fill="none">'
        '<rect width="36" height="36" rx="9" fill="#DC2626"/>'
        '<path d="M11 9h9l6 6v12a2 2 0 0 1-2 2H11a2 2 0 0 1-2-2V11a2 2 0 0 1 2-2z" fill="#FFFFFF"/>'
        '<path d="M20 9v6h6" fill="#FCA5A5"/>'
        '<text x="11.5" y="24" font-family="Segoe UI, sans-serif" font-size="6.5" font-weight="900" fill="#DC2626">PDF</text>'
        '</svg>'
    ),
    "forex_exchange": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="36" height="36" viewBox="0 0 36 36" fill="none">'
        '<rect width="36" height="36" rx="9" fill="#16A34A"/>'
        '<circle cx="18" cy="18" r="10" stroke="#FFFFFF" stroke-width="1.8" fill="none"/>'
        '<path d="M13 14h10m-3-3l3 3-3 3" stroke="#FFFFFF" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>'
        '<path d="M23 22H13m3 3l-3-3 3-3" stroke="#86EFAC" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>'
        '</svg>'
    ),
    "obsidian_sync": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="36" height="36" viewBox="0 0 36 36" fill="none">'
        '<rect width="36" height="36" rx="9" fill="#1E1630"/>'
        '<path d="M23.5 10.5l-6-2.5-5 5.5 3 13.5 8 1.5 3.5-7-3.5-11z" fill="#7C3AED" stroke="#A78BFA" stroke-width="1.2"/>'
        '<path d="M17.5 8l-5 5.5 5.5 4.5 5.5-7.5-6-2.5z" fill="#8B5CF6"/>'
        '<path d="M12.5 13.5l3 13.5 2.5-9-5.5-4.5z" fill="#6D28D9"/>'
        '<path d="M18 18l2.5 9 6.5-8.5-9-.5z" fill="#5B21B6"/>'
        '</svg>'
    ),
}


def _render_app_logo_pixmap(svg_xml: str, size: int = 36) -> QPixmap:
    renderer = QSvgRenderer(QByteArray(svg_xml.strip().encode("utf-8")))
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    renderer.render(p)
    p.end()
    return pix


_APP_METADATA = {
    "github_integration": {
        "title": "GitHub Integration",
        "badge": "GH",
        "badge_bg": "#24292e",
        "desc": "Inspect repos, branches, issues, pull requests, and commits",
        "category": "Development",
    },
    "google_workspace": {
        "title": "Google Workspace",
        "badge": "G",
        "badge_bg": "#ea4335",
        "desc": "Sync Gmail unread emails, Google Calendar meetings, and Drive files",
        "category": "Productivity",
    },
    "slack_integration": {
        "title": "Slack Team Messaging",
        "badge": "SL",
        "badge_bg": "#4a154b",
        "desc": "Post channel announcements, direct messages, and team notifications",
        "category": "Communication",
    },
    "notion_integration": {
        "title": "Notion Workspace & Docs",
        "badge": "N",
        "badge_bg": "#000000",
        "desc": "Query databases, create pages, and append meeting notes & tasks",
        "category": "Productivity",
    },
    "jira_integration": {
        "title": "Jira & Atlassian Work",
        "badge": "Jira",
        "badge_bg": "#0052cc",
        "desc": "Track sprint issues, create bug tickets, and check task status",
        "category": "Development",
    },
    "trello_integration": {
        "title": "Trello / Asana Task Manager",
        "badge": "Task",
        "badge_bg": "#0079bf",
        "desc": "Manage Kanban boards, lists, task cards, and move tickets to Done",
        "category": "Productivity",
    },
    "discord_integration": {
        "title": "Discord Server & Webhooks",
        "badge": "DC",
        "badge_bg": "#5865f2",
        "desc": "Broadcast alerts, community announcements, and channel messages",
        "category": "Communication",
    },
    "telegram_integration": {
        "title": "Telegram Bot Alerts",
        "badge": "TG",
        "badge_bg": "#229ed9",
        "desc": "Send automated Telegram messages, briefs, and channel alerts",
        "category": "Communication",
    },
    "spotify_integration": {
        "title": "Spotify Music & Focus Audio",
        "badge": "Music",
        "badge_bg": "#1db954",
        "desc": "Control playback, start focus playlists, search songs, and pause audio",
        "category": "Media",
    },
    "zoom_integration": {
        "title": "Zoom Video Meetings",
        "badge": "Zoom",
        "badge_bg": "#2d8cff",
        "desc": "Schedule meetings, create instant invite links, and check upcoming calls",
        "category": "Communication",
    },
    "microsoft365_integration": {
        "title": "Microsoft 365 (Outlook & Teams)",
        "badge": "M365",
        "badge_bg": "#d83b01",
        "desc": "Check Outlook emails, upcoming appointments, and Microsoft Teams chats",
        "category": "Productivity",
    },
    "whatsapp_integration": {
        "title": "WhatsApp Cloud API",
        "badge": "WA",
        "badge_bg": "#25d366",
        "desc": "Send WhatsApp messages, quick status updates, and reports to contacts",
        "category": "Communication",
    },
    "workspace_helper": {
        "title": "Project Workspace Helper",
        "badge": "Code",
        "badge_bg": "#6366f1",
        "desc": "Inspect local project directories, file structure, and project sizes",
        "category": "Development",
    },
}


class PluginManagerOverlay(QWidget):
    """Floating overlay — lists discovered integrations and plugin store with 1-click download options."""

    _OW = 800

    def __init__(self, plugins: list[dict], parent=None, on_configure=None, on_refresh=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            PluginManagerOverlay {{
                background: {C.PANEL};
                border: 1px solid {C.BORDER};
                border-radius: 16px;
            }}
        """)
        self.setFixedWidth(self._OW)
        self._on_configure = on_configure
        self._on_refresh = on_refresh
        self._plugins = plugins or []
        if not self._plugins:
            try:
                from core.plugin_loader import discover_plugins
                pdir = BASE_DIR / "plugins"
                if str(BASE_DIR) not in sys.path:
                    sys.path.insert(0, str(BASE_DIR))
                reg = discover_plugins(pdir, set())
                self._plugins = reg.list_for_ui()
            except Exception as _disc_err:
                print(f"[Plugins] Overlay auto-discovery fallback error: {_disc_err}")
        self._row_widgets = []
        self._store_widgets = []

        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 18, 22, 18)
        lay.setSpacing(12)

        # Header Row: Icon + Title/Subtitle + Action Bar + Close
        hdr_row = QHBoxLayout()
        hdr_row.setSpacing(12)

        # Left: Icon Badge
        icon_box = QFrame()
        icon_box.setFixedSize(40, 40)
        icon_box.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 rgba(99, 102, 241, 0.28), stop:1 rgba(139, 92, 246, 0.12));
                border: 1px solid rgba(99, 102, 241, 0.45);
                border-radius: 10px;
            }
        """)
        ib_lay = QHBoxLayout(icon_box)
        ib_lay.setContentsMargins(0, 0, 0, 0)
        ib_lbl = QLabel("🔗")
        ib_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ib_lbl.setFont(QFont("Segoe UI Emoji", 13))
        ib_lbl.setStyleSheet("background: transparent; border: none;")
        ib_lay.addWidget(ib_lbl)
        hdr_row.addWidget(icon_box)

        # Title & Subtitle
        hdr_v = QVBoxLayout()
        hdr_v.setSpacing(2)
        hdr = QLabel("APP INTEGRATIONS & PLUGIN STORE")
        hdr.setFont(QFont(APP_FONT_NAME, 11, QFont.Weight.Bold))
        hdr.setStyleSheet("color: #ffffff; background: transparent; letter-spacing: 0.5px;")
        hdr_v.addWidget(hdr)
        sub = QLabel("Manage installed integrations, import extensions, or install plugins from catalog.")
        sub.setFont(QFont(APP_FONT_NAME, 9))
        sub.setStyleSheet("color: #94a3b8; background: transparent;")
        hdr_v.addWidget(sub)
        hdr_row.addLayout(hdr_v)
        hdr_row.addStretch()

        # Action Buttons Toolbar
        action_btn_css = """
            QPushButton {
                background: rgba(255, 255, 255, 0.04);
                color: #cbd5e1;
                border: 1px solid rgba(255, 255, 255, 0.09);
                border-radius: 7px;
                padding: 0 11px;
                font-size: 11px;
                font-weight: 500;
            }
            QPushButton:hover {
                background: rgba(99, 102, 241, 0.18);
                color: #ffffff;
                border-color: rgba(99, 102, 241, 0.45);
            }
            QPushButton:pressed {
                background: rgba(99, 102, 241, 0.3);
            }
        """

        import_file_btn = QPushButton("📥 Import .py")
        import_file_btn.setFixedHeight(28)
        import_file_btn.setFont(QFont(APP_FONT_NAME, 8, QFont.Weight.Medium))
        import_file_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        import_file_btn.setStyleSheet(action_btn_css)
        import_file_btn.clicked.connect(self._import_local_file)
        hdr_row.addWidget(import_file_btn)

        import_url_btn = QPushButton("🌐 From URL")
        import_url_btn.setFixedHeight(28)
        import_url_btn.setFont(QFont(APP_FONT_NAME, 8, QFont.Weight.Medium))
        import_url_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        import_url_btn.setStyleSheet(action_btn_css)
        import_url_btn.clicked.connect(self._import_from_url)
        hdr_row.addWidget(import_url_btn)

        folder_btn = QPushButton("📁 Folder")
        folder_btn.setFixedHeight(28)
        folder_btn.setFont(QFont(APP_FONT_NAME, 8, QFont.Weight.Medium))
        folder_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        folder_btn.setStyleSheet(action_btn_css)
        folder_btn.clicked.connect(self._open_plugins_folder)
        hdr_row.addWidget(folder_btn)

        hdr_row.addSpacing(4)

        pm_close_btn = QPushButton("✕")
        pm_close_btn.setFixedSize(28, 28)
        pm_close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        pm_close_btn.setToolTip("Close")
        pm_close_btn.setStyleSheet("""
            QPushButton {
                color: #94a3b8;
                background: rgba(255, 255, 255, 0.04);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 7px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover {
                color: #ef4444;
                background: rgba(239, 68, 68, 0.15);
                border-color: rgba(239, 68, 68, 0.35);
            }
        """)
        pm_close_btn.clicked.connect(self.hide)
        hdr_row.addWidget(pm_close_btn)
        lay.addLayout(hdr_row)

        # Tab Segmented Bar + Search Box Row
        ctrl_row = QHBoxLayout()
        ctrl_row.setSpacing(12)

        from core.plugin_store import CATALOG

        # Segmented Control Container
        tab_container = QFrame()
        tab_container.setFixedHeight(36)
        tab_container.setStyleSheet("""
            QFrame {
                background: rgba(255, 255, 255, 0.03);
                border: 1px solid rgba(255, 255, 255, 0.07);
                border-radius: 9px;
            }
        """)
        tc_lay = QHBoxLayout(tab_container)
        tc_lay.setContentsMargins(3, 3, 3, 3)
        tc_lay.setSpacing(3)

        self._btn_tab_installed = QPushButton(f"⚡ Installed ({len(self._plugins)})")
        self._btn_tab_installed.setFixedHeight(28)
        self._btn_tab_installed.setFont(QFont(APP_FONT_NAME, 9, QFont.Weight.DemiBold))
        self._btn_tab_installed.setCursor(Qt.CursorShape.PointingHandCursor)

        self._btn_tab_store = QPushButton(f"📦 Plugin Store ({len(CATALOG)})")
        self._btn_tab_store.setFixedHeight(28)
        self._btn_tab_store.setFont(QFont(APP_FONT_NAME, 9, QFont.Weight.DemiBold))
        self._btn_tab_store.setCursor(Qt.CursorShape.PointingHandCursor)

        self._set_tab_style(active_tab="installed")
        self._btn_tab_installed.clicked.connect(lambda: self._switch_tab(0))
        self._btn_tab_store.clicked.connect(lambda: self._switch_tab(1))
        tc_lay.addWidget(self._btn_tab_installed)
        tc_lay.addWidget(self._btn_tab_store)
        ctrl_row.addWidget(tab_container)

        # Modern Search Bar
        search_box = QFrame()
        search_box.setFixedHeight(36)
        search_box.setStyleSheet("""
            QFrame {
                background: rgba(255, 255, 255, 0.03);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 9px;
            }
            QFrame:focus-within {
                border-color: #6366f1;
                background: rgba(99, 102, 241, 0.06);
            }
        """)
        sb_lay = QHBoxLayout(search_box)
        sb_lay.setContentsMargins(10, 0, 10, 0)
        sb_lay.setSpacing(8)
        s_lbl = QLabel("🔍")
        s_lbl.setStyleSheet("background: transparent; font-size: 11px; color: #64748b; border: none;")
        sb_lay.addWidget(s_lbl)
        self._filter_input = QLineEdit()
        self._filter_input.setPlaceholderText("Filter apps and plugins...")
        self._filter_input.setFont(QFont(APP_FONT_NAME, 9))
        self._filter_input.setStyleSheet("background: transparent; color: #f1f5f9; border: none; padding: 0;")
        self._filter_input.textChanged.connect(self._filter_cards)
        sb_lay.addWidget(self._filter_input, 1)
        ctrl_row.addWidget(search_box, 1)

        lay.addLayout(ctrl_row)

        # Stacked Pages
        self._stack = QStackedWidget()

        # Page 0: Installed Apps
        scroll_inst = QScrollArea()
        scroll_inst.setWidgetResizable(True)
        scroll_inst.setFixedHeight(360)
        scroll_inst.setStyleSheet("""
            QScrollArea { background: transparent; border: none; }
            QScrollBar:vertical { background: transparent; width: 6px; border: none; margin: 2px; }
            QScrollBar::handle:vertical { background: rgba(255, 255, 255, 0.16); border-radius: 3px; min-height: 25px; }
            QScrollBar::handle:vertical:hover { background: rgba(99, 102, 241, 0.6); }
        """)
        c_inst = QWidget(); c_inst.setStyleSheet("background: transparent;")
        self._cards_layout = QVBoxLayout(c_inst)
        self._cards_layout.setContentsMargins(0, 4, 6, 4)
        self._cards_layout.setSpacing(8)

        for p in self._plugins:
            card = self._build_card(p)
            self._cards_layout.addWidget(card)
            self._row_widgets.append((p, card))
        self._cards_layout.addStretch()
        scroll_inst.setWidget(c_inst)
        self._stack.addWidget(scroll_inst)

        # Page 1: Download Plugins Store
        scroll_store = QScrollArea()
        scroll_store.setWidgetResizable(True)
        scroll_store.setFixedHeight(360)
        scroll_store.setStyleSheet("""
            QScrollArea { background: transparent; border: none; }
            QScrollBar:vertical { background: transparent; width: 6px; border: none; margin: 2px; }
            QScrollBar::handle:vertical { background: rgba(255, 255, 255, 0.16); border-radius: 3px; min-height: 25px; }
            QScrollBar::handle:vertical:hover { background: rgba(99, 102, 241, 0.6); }
        """)
        c_store = QWidget(); c_store.setStyleSheet("background: transparent;")
        self._store_layout = QVBoxLayout(c_store)
        self._store_layout.setContentsMargins(0, 4, 6, 4)
        self._store_layout.setSpacing(8)

        plugins_dir = BASE_DIR / "plugins"
        for item in CATALOG:
            scard = self._build_store_card(item, plugins_dir)
            self._store_layout.addWidget(scard)
            self._store_widgets.append((item, scard))
        self._store_layout.addStretch()
        scroll_store.setWidget(c_store)
        self._stack.addWidget(scroll_store)

        lay.addWidget(self._stack)

        # Status / Feedback label
        self._status_lbl = QLabel("")
        self._status_lbl.setFont(QFont(APP_FONT_NAME, 8))
        self._status_lbl.setStyleSheet("color: #4ade80; background: transparent;")
        self._status_lbl.hide()
        lay.addWidget(self._status_lbl)

        # Footer Row
        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: rgba(255, 255, 255, 0.08); margin: 2px 0;")
        lay.addWidget(sep)

        foot_row = QHBoxLayout()
        settings_btn = QPushButton("⚙  CONFIGURE INTEGRATIONS")
        settings_btn.setFixedHeight(32)
        settings_btn.setFont(QFont(APP_FONT_NAME, 9, QFont.Weight.Medium))
        settings_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        settings_btn.setStyleSheet("""
            QPushButton {
                background: rgba(99, 102, 241, 0.12); color: #a5b4fc;
                border: 1px solid rgba(99, 102, 241, 0.3); border-radius: 8px; padding: 0 14px;
            }
            QPushButton:hover { background: #6366f1; color: #ffffff; border-color: #818cf8; }
        """)
        if self._on_configure:
            settings_btn.clicked.connect(lambda: (self.hide(), self._on_configure()))
        foot_row.addWidget(settings_btn)

        foot_row.addStretch()

        close_btn = QPushButton("CLOSE")
        close_btn.setFixedSize(80, 32)
        close_btn.setFont(QFont(APP_FONT_NAME, 9))
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.03); color: #94a3b8;
                border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 8px;
            }
            QPushButton:hover { color: #f1f5f9; background: rgba(255, 255, 255, 0.07); border-color: rgba(255, 255, 255, 0.15); }
        """)
        close_btn.clicked.connect(self.hide)
        foot_row.addWidget(close_btn)
        lay.addLayout(foot_row)

    def _set_tab_style(self, active_tab: str):
        active_css = """
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #6366f1, stop:1 #4f46e5);
                color: #ffffff;
                border: 1px solid rgba(255, 255, 255, 0.18);
                border-radius: 6px;
                padding: 0 14px;
                font-weight: 600;
            }
        """
        inactive_css = """
            QPushButton {
                background: transparent;
                color: #94a3b8;
                border: none;
                border-radius: 6px;
                padding: 0 14px;
                font-weight: 500;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.05);
                color: #f1f5f9;
            }
        """
        if active_tab == "installed":
            self._btn_tab_installed.setStyleSheet(active_css)
            self._btn_tab_store.setStyleSheet(inactive_css)
        else:
            self._btn_tab_installed.setStyleSheet(inactive_css)
            self._btn_tab_store.setStyleSheet(active_css)

    def _switch_tab(self, index: int):
        self._stack.setCurrentIndex(index)
        self._set_tab_style("installed" if index == 0 else "store")

    def _filter_cards(self, text: str):
        q = text.lower().strip()
        for p, card in self._row_widgets:
            meta = _APP_METADATA.get(p["name"], {})
            haystack = f"{p['name']} {meta.get('title', '')} {meta.get('desc', '')} {meta.get('category', '')}".lower()
            card.setVisible(q in haystack)
        for item, card in self._store_widgets:
            haystack = f"{item['id']} {item['title']} {item['desc']} {item.get('category', '')}".lower()
            card.setVisible(q in haystack)

    def _build_card(self, p: dict) -> QFrame:
        card = QFrame()
        card.setStyleSheet("""
            QFrame {
                background: rgba(255, 255, 255, 0.02);
                border: 1px solid rgba(255, 255, 255, 0.06);
                border-radius: 10px;
            }
            QFrame:hover {
                background: rgba(255, 255, 255, 0.038);
                border-color: rgba(99, 102, 241, 0.35);
            }
        """)
        c_lay = QHBoxLayout(card)
        c_lay.setContentsMargins(14, 11, 14, 11)
        c_lay.setSpacing(12)

        meta = _APP_METADATA.get(p["name"], {
            "title": p["name"].replace("_", " ").title(),
            "badge": p["name"][:2].upper(),
            "badge_bg": "#6366f1",
            "desc": p.get("description", ""),
            "category": "App",
        })

        badge = QLabel()
        badge.setFixedSize(38, 38)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo_svg = _APP_LOGOS_SVG.get(p["name"])
        if logo_svg:
            badge.setPixmap(_render_app_logo_pixmap(logo_svg, 38))
            badge.setStyleSheet("background: transparent; border: none;")
        else:
            badge.setText(meta["badge"])
            badge.setFont(QFont(APP_FONT_NAME, 10, QFont.Weight.Bold))
            badge.setStyleSheet(f"""
                background: {meta['badge_bg']};
                color: #ffffff;
                border-radius: 8px;
                border: 1px solid rgba(255, 255, 255, 0.2);
                font-weight: 800;
            """)
        c_lay.addWidget(badge)

        info_col = QVBoxLayout()
        info_col.setSpacing(3)
        top_h = QHBoxLayout()
        top_h.setSpacing(8)
        t_lbl = QLabel(meta["title"])
        t_lbl.setFont(QFont(APP_FONT_NAME, 10, QFont.Weight.Bold))
        t_lbl.setStyleSheet("color: #ffffff; background: transparent; border: none;")
        top_h.addWidget(t_lbl)

        cat_lbl = QLabel(meta["category"])
        cat_lbl.setFont(QFont(APP_FONT_NAME, 8, QFont.Weight.Medium))
        cat_lbl.setStyleSheet("color: #a5b4fc; background: rgba(99, 102, 241, 0.12); border: 1px solid rgba(99, 102, 241, 0.25); border-radius: 4px; padding: 1px 7px; border: none;")
        top_h.addWidget(cat_lbl)
        top_h.addStretch()
        info_col.addLayout(top_h)

        is_valid = p.get("valid", True)
        if not is_valid:
            cat_lbl.setText("Needs Setup")
            cat_lbl.setStyleSheet("color: #f87171; background: rgba(239, 68, 68, 0.12); border: 1px solid rgba(239, 68, 68, 0.25); border-radius: 4px; padding: 1px 7px; border: none;")
            desc_text = p.get("error") or meta.get("desc", "")
        else:
            desc_text = meta.get("desc", "")
        desc_lbl = QLabel(desc_text[:105] + ("..." if len(desc_text) > 105 else ""))
        desc_lbl.setFont(QFont(APP_FONT_NAME, 8))
        desc_lbl.setStyleSheet(f"color: {'#fca5a5' if not is_valid else '#94a3b8'}; background: transparent; border: none;")
        info_col.addWidget(desc_lbl)
        c_lay.addLayout(info_col, stretch=1)

        if self._on_configure:
            cfg_btn = QPushButton("⚙ Settings")
            cfg_btn.setFixedSize(80, 28)
            cfg_btn.setFont(QFont(APP_FONT_NAME, 8, QFont.Weight.Medium))
            cfg_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            cfg_btn.setStyleSheet("""
                QPushButton {
                    background: rgba(255, 255, 255, 0.04); color: #cbd5e1;
                    border: 1px solid rgba(255, 255, 255, 0.09); border-radius: 7px;
                }
                QPushButton:hover {
                    background: rgba(99, 102, 241, 0.18); color: #ffffff;
                    border-color: rgba(99, 102, 241, 0.4);
                }
            """)
            cfg_btn.clicked.connect(lambda: (self.hide(), self._on_configure()))
            c_lay.addWidget(cfg_btn)

        btn = QPushButton()
        btn.setFixedSize(62, 28)
        btn.setFont(QFont(APP_FONT_NAME, 8, QFont.Weight.Bold))
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        if not is_valid:
            btn.setText("ERR")
            btn.setEnabled(False)
            btn.setStyleSheet("""
                QPushButton {
                    background: rgba(239, 68, 68, 0.14); color: #f87171;
                    border: 1px solid rgba(239, 68, 68, 0.35); border-radius: 7px;
                }
            """)
        else:
            self._style_toggle(btn, p.get("enabled", True))
            btn.clicked.connect(lambda _, name=p["name"], b=btn: self._toggle(name, b))
        c_lay.addWidget(btn)

        return card

    def _build_store_card(self, item: dict, plugins_dir: Path) -> QFrame:
        card = QFrame()
        card.setStyleSheet("""
            QFrame {
                background: rgba(255, 255, 255, 0.02);
                border: 1px solid rgba(255, 255, 255, 0.06);
                border-radius: 10px;
            }
            QFrame:hover {
                background: rgba(255, 255, 255, 0.038);
                border-color: rgba(99, 102, 241, 0.35);
            }
        """)
        c_lay = QHBoxLayout(card)
        c_lay.setContentsMargins(14, 11, 14, 11)
        c_lay.setSpacing(12)

        badge = QLabel()
        badge.setFixedSize(38, 38)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        store_svg = _STORE_LOGOS_SVG.get(str(item.get("id") or ""))
        if store_svg:
            badge.setPixmap(_render_app_logo_pixmap(store_svg, 38))
            badge.setStyleSheet("background: transparent; border: none;")
        else:
            badge.setText(item.get("badge", "🧩"))
            badge.setFont(QFont("Segoe UI Emoji", 14))
            badge.setStyleSheet(f"""
                background: {item.get('badge_bg', '#6366f1')};
                border-radius: 8px;
                border: 1px solid rgba(255, 255, 255, 0.2);
            """)
        c_lay.addWidget(badge)

        info_col = QVBoxLayout()
        info_col.setSpacing(3)
        top_h = QHBoxLayout()
        top_h.setSpacing(8)
        t_lbl = QLabel(item["title"])
        t_lbl.setFont(QFont(APP_FONT_NAME, 10, QFont.Weight.Bold))
        t_lbl.setStyleSheet("color: #ffffff; background: transparent; border: none;")
        top_h.addWidget(t_lbl)

        cat_lbl = QLabel(item.get("category", "Store"))
        cat_lbl.setFont(QFont(APP_FONT_NAME, 8, QFont.Weight.Medium))
        cat_lbl.setStyleSheet("color: #38bdf8; background: rgba(56, 189, 248, 0.12); border: 1px solid rgba(56, 189, 248, 0.25); border-radius: 4px; padding: 1px 7px; border: none;")
        top_h.addWidget(cat_lbl)
        top_h.addStretch()
        info_col.addLayout(top_h)

        desc_lbl = QLabel(item["desc"][:105] + ("..." if len(item["desc"]) > 105 else ""))
        desc_lbl.setFont(QFont(APP_FONT_NAME, 8))
        desc_lbl.setStyleSheet("color: #94a3b8; background: transparent; border: none;")
        info_col.addWidget(desc_lbl)
        c_lay.addLayout(info_col, stretch=1)

        dl_btn = QPushButton()
        dl_btn.setFixedSize(112, 28)
        dl_btn.setFont(QFont(APP_FONT_NAME, 8, QFont.Weight.Bold))
        dl_btn.setCursor(Qt.CursorShape.PointingHandCursor)

        is_inst = (plugins_dir / item["file"]).exists()
        if is_inst:
            dl_btn.setText("INSTALLED ✓")
            dl_btn.setEnabled(False)
            dl_btn.setStyleSheet("""
                QPushButton {
                    background: rgba(34, 197, 94, 0.12); color: #4ade80;
                    border: 1px solid rgba(34, 197, 94, 0.3); border-radius: 6px;
                }
            """)
        else:
            dl_btn.setText("⬇ DOWNLOAD")
            dl_btn.setStyleSheet("""
                QPushButton {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #6366f1, stop:1 #8b5cf6);
                    color: #ffffff; border: 1px solid rgba(255, 255, 255, 0.25); border-radius: 6px;
                }
                QPushButton:hover { background: #4f46e5; border-color: #818cf8; }
            """)
            dl_btn.clicked.connect(lambda _, it=item, b=dl_btn: self._download_catalog_item(it, b))
        c_lay.addWidget(dl_btn)
        return card

    def _download_catalog_item(self, item: dict, btn: QPushButton):
        from core.plugin_store import install_catalog_plugin
        plugins_dir = BASE_DIR / "plugins"
        ok, msg = install_catalog_plugin(item["id"], plugins_dir)
        if ok:
            btn.setText("INSTALLED ✓")
            btn.setEnabled(False)
            btn.setStyleSheet("""
                QPushButton {
                    background: rgba(34, 197, 94, 0.12); color: #4ade80;
                    border: 1px solid rgba(34, 197, 94, 0.3); border-radius: 6px;
                }
            """)
            self._show_msg(f"✓ Downloaded and installed '{item['title']}'!")
            if self._on_refresh:
                self._on_refresh()
        else:
            self._show_msg(f"Download failed: {msg}", is_error=True)

    def _import_local_file(self):
        fpath, _ = QFileDialog.getOpenFileName(self, "Select Plugin Python File", "", "Python Files (*.py)")
        if not fpath:
            return
        p = Path(fpath)
        try:
            code = p.read_text(encoding="utf-8")
            from core.plugin_store import install_from_code
            plugins_dir = BASE_DIR / "plugins"
            ok, msg = install_from_code(p.name, code, plugins_dir)
            if ok:
                self._show_msg(f"✓ Successfully imported {p.name}!")
                if self._on_refresh:
                    self._on_refresh()
            else:
                self._show_msg(msg, is_error=True)
        except Exception as e:
            self._show_msg(f"Import error: {e}", is_error=True)

    def _import_from_url(self):
        url, ok = QInputDialog.getText(self, "Download Plugin from URL", "Enter direct raw Python code or GitHub URL:")
        if not ok or not url.strip():
            return
        from core.plugin_store import install_from_url
        plugins_dir = BASE_DIR / "plugins"
        success, msg = install_from_url(url.strip(), plugins_dir)
        if success:
            self._show_msg(f"✓ Downloaded plugin from URL!")
            if self._on_refresh:
                self._on_refresh()
        else:
            self._show_msg(msg, is_error=True)

    def _open_plugins_folder(self):
        pdir = BASE_DIR / "plugins"
        pdir.mkdir(parents=True, exist_ok=True)
        try:
            if platform.system() == "Windows":
                os.startfile(str(pdir))
            else:
                subprocess.Popen(["xdg-open", str(pdir)])
        except Exception as e:
            self._show_msg(f"Could not open folder: {e}", is_error=True)

    def _show_msg(self, text: str, is_error: bool = False):
        self._status_lbl.setText(text)
        self._status_lbl.setStyleSheet(f"color: {'#f87171' if is_error else '#4ade80'}; background: transparent; padding: 2px 4px;")
        self._status_lbl.show()
        QTimer.singleShot(5000, self._status_lbl.hide)

    def _style_toggle(self, btn: QPushButton, enabled: bool):
        if enabled:
            btn.setText("ON")
            btn.setStyleSheet("""
                QPushButton {
                    background: rgba(34, 197, 94, 0.14); color: #4ade80;
                    border: 1px solid rgba(34, 197, 94, 0.35); border-radius: 7px;
                }
                QPushButton:hover { background: rgba(34, 197, 94, 0.24); }
            """)
        else:
            btn.setText("OFF")
            btn.setStyleSheet("""
                QPushButton {
                    background: rgba(255, 255, 255, 0.03); color: #64748b;
                    border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 7px;
                }
                QPushButton:hover { color: #cbd5e1; border-color: rgba(255, 255, 255, 0.18); }
            """)

    def _toggle(self, name: str, btn: QPushButton):
        from memory.config_manager import get_plugin_enabled, save_plugin_enabled
        new_val = not get_plugin_enabled(name)
        save_plugin_enabled(name, new_val)
        self._style_toggle(btn, new_val)

    def refresh_installed(self, plugins: list[dict]):
        self._plugins = plugins or []
        for _, card in self._row_widgets:
            card.setParent(None)
            card.deleteLater()
        self._row_widgets.clear()

        while self._cards_layout.count() > 0:
            item = self._cards_layout.takeAt(0)
            if item is not None and item.widget():
                w = item.widget()
                if w is not None:
                    w.setParent(None)
                    w.deleteLater()

        for p in self._plugins:
            card = self._build_card(p)
            self._cards_layout.addWidget(card)
            self._row_widgets.append((p, card))
        self._cards_layout.addStretch()
        self._btn_tab_installed.setText(f"⚡ Installed ({len(self._plugins)})")
        self.refresh_store()
        if hasattr(self, "_filter_input") and self._filter_input.text():
            self._filter_cards(self._filter_input.text())

    def refresh_store(self):
        plugins_dir = BASE_DIR / "plugins"
        for _, scard in self._store_widgets:
            scard.setParent(None)
            scard.deleteLater()
        self._store_widgets.clear()

        while self._store_layout.count() > 0:
            item = self._store_layout.takeAt(0)
            if item is not None and item.widget():
                w = item.widget()
                if w is not None:
                    w.setParent(None)
                    w.deleteLater()

        from core.plugin_store import CATALOG
        for item in CATALOG:
            scard = self._build_store_card(item, plugins_dir)
            self._store_layout.addWidget(scard)
            self._store_widgets.append((item, scard))
        self._store_layout.addStretch()
        self._btn_tab_store.setText(f"📦 Plugin Store ({len(CATALOG)})")



class ModalBackdrop(QWidget):
    """Semi-transparent backdrop scrim behind active modal overlays."""
    clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("""
            ModalBackdrop {
                background: rgba(3, 7, 18, 0.72);
            }
        """)
        self.hide()

    def mousePressEvent(self, event):
        self.clicked.emit()
        event.accept()


class _HudOverlay(QWidget):
    """Base for the floating panels placed by hand over the HUD.

    They are children of the central widget but sit in no layout, so Qt never
    invalidates the region they occupy when they hide or shrink: the HUD keeps
    painting around them and their last frame stays on screen as a ghost. Any
    overlay positioned with _centre_overlay needs this."""

    def hideEvent(self, a0):
        p = self.parentWidget()
        if p is not None:
            # Repaint exactly what we were covering, before we stop covering it.
            p.update(self.geometry())
        super().hideEvent(a0)
        win = self.window()
        if hasattr(win, "_on_overlay_closed"):
            win._on_overlay_closed(self)

    def closeEvent(self, a0):
        p = self.parentWidget()
        if p is not None:
            p.update(self.geometry())
        super().closeEvent(a0)
        win = self.window()
        if hasattr(win, "_on_overlay_closed"):
            win._on_overlay_closed(self)

    def keyPressEvent(self, a0):
        if a0.key() == Qt.Key.Key_Escape:
            self.hide()
            a0.accept()
            return
        super().keyPressEvent(a0)


class ConfirmBanner(_HudOverlay):
    """The gate in front of an action that cannot be taken back.

    The old confirmation was a tool parameter the model filled in itself, which
    means it confirmed its own shutdown requests. This is the interface asking,
    and the answer travels from a human finger to core/confirm.py without the
    model in the loop. Nothing blocks while it is up: the assistant keeps
    talking, so this costs no latency — unlike the old gate, which spent two
    tool round trips on every power command."""

    answered = pyqtSignal(bool)
    _OW = 430

    def __init__(self, title: str, detail: str, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            ConfirmBanner {{
                background: rgba(14, 3, 0, 250);
                border: 1px solid {C.ACC};
                border-radius: 6px;
            }}
        """)
        self.setFixedWidth(self._OW)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(8)

        hdr = QLabel("⚠  CONFIRM")
        hdr.setFont(QFont(APP_FONT_NAME, 11, QFont.Weight.Bold))
        hdr.setStyleSheet(f"color: {C.ACC}; background: transparent;")
        lay.addWidget(hdr)

        ttl = QLabel(title)
        ttl.setWordWrap(True)
        ttl.setFont(QFont(APP_FONT_NAME, 10, QFont.Weight.Bold))
        ttl.setStyleSheet(f"color: {C.TEXT}; background: transparent;")
        lay.addWidget(ttl)

        if detail:
            dtl = QLabel(detail)
            dtl.setWordWrap(True)
            dtl.setFont(QFont(APP_FONT_NAME, 8))
            dtl.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent;")
            lay.addWidget(dtl)

        row = QHBoxLayout(); row.setSpacing(8)

        yes = QPushButton("▸  CONFIRM")
        yes.setFixedHeight(32)
        yes.setFont(QFont(APP_FONT_NAME, 9, QFont.Weight.Bold))
        yes.setCursor(Qt.CursorShape.PointingHandCursor)
        yes.setStyleSheet(f"""
            QPushButton {{ background: transparent; color: {C.ACC};
                border: 1px solid {C.ACC}; border-radius: 8px; }}
            QPushButton:hover {{ background: rgba(255,107,0,40); }}
        """)
        yes.clicked.connect(lambda: self.answered.emit(True))
        row.addWidget(yes)

        no = QPushButton("CANCEL")
        no.setFixedHeight(32)
        no.setFont(QFont(APP_FONT_NAME, 9))
        no.setCursor(Qt.CursorShape.PointingHandCursor)
        no.setStyleSheet(f"""
            QPushButton {{ background: transparent; color: {C.TEXT_MED};
                border: 1px solid {C.BORDER}; border-radius: 8px; }}
            QPushButton:hover {{ color: {C.TEXT}; border-color: {C.BORDER_B}; }}
        """)
        no.clicked.connect(lambda: self.answered.emit(False))
        row.addWidget(no)
        lay.addLayout(row)

        # Default focus on CANCEL: if someone hits Enter without reading, the
        # safe answer wins.
        no.setDefault(True)
        no.setFocus()


class AudioDeviceOverlay(_HudOverlay):
    """Choose which microphone CHARLIE listens to and which speakers it uses.

    Both audio streams used to open with no `device=` at all, so they always
    took the OS default — which on Windows moves by itself the moment a headset
    is plugged in. 'CHARLIE can't hear me' is usually 'CHARLIE is listening to the
    webcam'."""

    picked = pyqtSignal()      # emitted after Apply, when something changed
    _devices_ready = pyqtSignal(object)
    _OW = 460

    def __init__(self, parent=None):
        super().__init__(parent)
        from core.audio_devices import DEFAULT_LABEL
        from memory.config_manager import get_input_device, get_output_device

        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            AudioDeviceOverlay {{
                background: rgba(0, 6, 10, 245);
                border: 1px solid {C.BORDER_B};
                border-radius: 6px;
            }}
        """)
        self.setFixedWidth(self._OW)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(6)

        hdr = QLabel("🎧  AUDIO DEVICES")
        hdr.setFont(QFont(APP_FONT_NAME, 12, QFont.Weight.Bold))
        hdr.setStyleSheet(f"color: {C.PRI}; background: transparent;")
        lay.addWidget(hdr)

        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {C.BORDER}; margin: 2px 0;")
        lay.addWidget(sep)

        _combo_css = (
            f"QComboBox {{ background: #000d12; color: {C.TEXT}; "
            f"border: 1px solid {C.BORDER}; border-radius: 8px; padding: 4px 8px; }}"
            f"QComboBox:hover {{ border-color: {C.BORDER_B}; }}"
            f"QComboBox QAbstractItemView {{ background: #000d12; color: {C.TEXT}; "
            f"selection-background-color: {C.PRI_GHO}; border: 1px solid {C.BORDER}; }}"
        )

        def _row(label: str, kind: str, current: str) -> QComboBox:
            cap = QLabel(label)
            cap.setFont(QFont(APP_FONT_NAME, 8))
            cap.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
            lay.addWidget(cap)

            box = QComboBox()
            box.setFont(QFont(APP_FONT_NAME, 9))
            box.setFixedHeight(30)
            box.setStyleSheet(_combo_css)
            box.addItem(DEFAULT_LABEL, "")
            idx = box.findData(current) if current else 0
            box.setCurrentIndex(idx if idx >= 0 else 0)
            if current and idx < 0:
                # Saved device is not plugged in right now. Show it rather than
                # silently resetting the user's choice to default.
                box.addItem(f"{current}  (not connected)", current)
                box.setCurrentIndex(box.count() - 1)
            lay.addWidget(box)
            return box

        self._in_box  = _row("MICROPHONE — what CHARLIE hears you with",
                             "input", get_input_device())
        lay.addSpacing(4)
        self._out_box = _row("SPEAKERS — what CHARLIE talks through",
                             "output", get_output_device())

        self._device_status = QLabel("Scanning audio devices…")
        self._device_status.setFont(QFont(APP_FONT_NAME, 7))
        self._device_status.setStyleSheet(
            f"color: {C.TEXT_DIM}; background: transparent;")
        lay.addWidget(self._device_status)
        self._devices_ready.connect(self._populate_devices)

        def _scan_devices():
            from core.audio_devices import list_devices
            self._devices_ready.emit({
                "input": list_devices("input"),
                "output": list_devices("output"),
            })

        threading.Thread(target=_scan_devices, daemon=True,
                         name="audio-device-picker").start()

        note = QLabel("Applying reconnects the session. Your conversation is kept.")
        note.setWordWrap(True)
        note.setFont(QFont(APP_FONT_NAME, 7))
        note.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        lay.addSpacing(6)
        lay.addWidget(note)

        row = QHBoxLayout(); row.setSpacing(8)
        ok = QPushButton("▸  APPLY")
        ok.setFixedHeight(32)
        ok.setFont(QFont(APP_FONT_NAME, 9, QFont.Weight.Bold))
        ok.setCursor(Qt.CursorShape.PointingHandCursor)
        ok.setStyleSheet(f"""
            QPushButton {{ background: transparent; color: {C.PRI};
                border: 1px solid {C.PRI_DIM}; border-radius: 8px; }}
            QPushButton:hover {{ background: {C.PRI_GHO}; border-color: {C.PRI}; }}
        """)
        ok.clicked.connect(self._apply)
        row.addWidget(ok)

        cancel = QPushButton("CLOSE")
        cancel.setFixedHeight(32)
        cancel.setFont(QFont(APP_FONT_NAME, 9))
        cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel.setStyleSheet(f"""
            QPushButton {{ background: transparent; color: {C.TEXT_MED};
                border: 1px solid {C.BORDER}; border-radius: 8px; }}
            QPushButton:hover {{ color: {C.TEXT}; border-color: {C.BORDER_B}; }}
        """)
        cancel.clicked.connect(self.hide)
        row.addWidget(cancel)
        lay.addLayout(row)

    def _populate_devices(self, devices: object) -> None:
        """Apply a completed background scan without blocking the Qt thread."""
        if not isinstance(devices, dict):
            devices = {}

        def _fill(box: QComboBox, names: list[str]) -> None:
            selected = str(box.currentData() or "")
            box.blockSignals(True)
            box.clear()
            box.addItem("System default", "")
            for name in names:
                box.addItem(name, name)
            idx = box.findData(selected) if selected else 0
            if selected and idx < 0:
                box.addItem(f"{selected}  (not connected)", selected)
                idx = box.count() - 1
            box.setCurrentIndex(max(0, idx))
            box.blockSignals(False)

        _fill(self._in_box, list(devices.get("input", [])))
        _fill(self._out_box, list(devices.get("output", [])))
        self._device_status.setText("Audio devices ready")

    def _apply(self):
        from memory.config_manager import (
            get_input_device, get_output_device,
            save_input_device, save_output_device,
        )
        new_in  = self._in_box.currentData()  or ""
        new_out = self._out_box.currentData() or ""
        changed = (new_in != get_input_device()) or (new_out != get_output_device())
        save_input_device(new_in)
        save_output_device(new_out)
        self.hide()
        # Only rebuild the session if something actually moved — a no-op Apply
        # should not cost a reconnect.
        if changed:
            self.picked.emit()


class MemoryOverlay(_HudOverlay):
    """Everything CHARLIE has stored about you, and when it learned it.

    Memory used to be a 2200-character store that deleted its oldest entries
    when full and mentioned it only on stdout. The cap is gone; this panel is
    the other half of that change — a memory you cannot inspect is a memory you
    cannot trust, and 'delete' has to be something the person can do."""

    _OW = 680

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("""
            MemoryOverlay {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #0d1424, stop:0.5 #090e1a, stop:1 #060912);
                border: 1px solid rgba(56, 189, 248, 0.40);
                border-radius: 18px;
            }
        """)
        self.setFixedWidth(self._OW)

        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(22, 18, 22, 18)
        self._lay.setSpacing(12)
        self._rebuild()

    def _clear_layout(self):
        """Take every item out of the layout and detach it from the widget tree."""
        while self._lay.count():
            item = self._lay.takeAt(0)
            if item is None:
                continue
            w = item.widget()
            if w is not None:
                w.hide()
                w.deleteLater()
                continue
            sub = item.layout()
            if sub is not None:
                while sub.count():
                    si = sub.takeAt(0)
                    if si is not None:
                        sw = si.widget()
                        if sw is not None:
                            sw.hide()
                            sw.deleteLater()
                sub.deleteLater()

    def _settle(self, before):
        """Size panel to content, re-centre, and repaint previous boundary."""
        self._lay.invalidate()
        self._lay.activate()
        self.updateGeometry()
        self.adjustSize()

        p = self.parentWidget()
        if p is None:
            self.update()
            return
        self.move(max(0, (p.width()  - self.width())  // 2),
                  max(0, (p.height() - self.height()) // 2))
        p.update(before.united(self.geometry()))
        self.update()

    @staticmethod
    def _format_fact_key(key: str) -> str:
        clean = key.replace("_", " ").strip()
        if clean.lower().startswith("correction "):
            parts = clean.split()
            if len(parts) > 1 and len(parts[1]) >= 8:
                return f"Correction ({parts[1][:8]})"
            return "Correction"
        return clean.title()

    @staticmethod
    def _get_category_badge_style(cat: str) -> tuple[str, str, str, str]:
        c = (cat or "").lower().strip()
        if c in ("identity", "iden"):
            return ("Identity", "#38bdf8", "rgba(56, 189, 248, 0.14)", "rgba(56, 189, 248, 0.35)")
        if c in ("relationships", "relationship", "rela"):
            return ("Relationship", "#c084fc", "rgba(192, 132, 252, 0.14)", "rgba(192, 132, 252, 0.35)")
        if c in ("corrections", "correction", "corr"):
            return ("Correction", "#fbbf24", "rgba(251, 191, 36, 0.14)", "rgba(251, 191, 36, 0.35)")
        if c in ("preferences", "preference", "pref"):
            return ("Preference", "#34d399", "rgba(52, 211, 153, 0.14)", "rgba(52, 211, 153, 0.35)")
        if c in ("projects", "project", "proj"):
            return ("Project", "#60a5fa", "rgba(96, 165, 250, 0.14)", "rgba(96, 165, 250, 0.35)")
        if c in ("wishes", "wish"):
            return ("Wish", "#f472b6", "rgba(244, 114, 182, 0.14)", "rgba(244, 114, 182, 0.35)")
        if c in ("notes", "note"):
            return ("Note", "#94a3b8", "rgba(148, 163, 184, 0.14)", "rgba(148, 163, 184, 0.35)")
        return (c[:8].capitalize(), "#94a3b8", "rgba(148, 163, 184, 0.14)", "rgba(148, 163, 184, 0.35)")

    def _rebuild(self):
        before = self.geometry()
        self._clear_layout()

        from memory.memory_manager import all_entries_for_ui
        from memory.profile_manager import active_profile

        # ── Header Row: Real Vector Logo + Title + Subtitle + Close ──
        hdr = QHBoxLayout()
        hdr.setSpacing(12)

        icon_box = QFrame()
        icon_box.setFixedSize(42, 42)
        icon_box.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 rgba(56, 189, 248, 0.22), stop:1 rgba(99, 102, 241, 0.12));
                border: 1px solid rgba(56, 189, 248, 0.45);
                border-radius: 12px;
            }
        """)
        ib_lay = QHBoxLayout(icon_box)
        ib_lay.setContentsMargins(0, 0, 0, 0)
        ib_lbl = QLabel()
        ib_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ib_lbl.setPixmap(_render_hub_svg("neural_memory", 26, "#38bdf8"))
        ib_lbl.setStyleSheet("background: transparent; border: none;")
        ib_lay.addWidget(ib_lbl)
        hdr.addWidget(icon_box)

        title_v = QVBoxLayout()
        title_v.setSpacing(2)

        title_top = QHBoxLayout()
        title_top.setSpacing(8)
        t_lbl = QLabel("WHAT CHARLIE REMEMBERS")
        t_lbl.setFont(QFont(APP_FONT_NAME, 11, QFont.Weight.Bold))
        t_lbl.setStyleSheet("color: #ffffff; background: transparent; letter-spacing: 0.6px;")
        title_top.addWidget(t_lbl)

        mem_pill = QLabel("LOCAL MEMORY STORE")
        mem_pill.setFont(QFont(APP_FONT_NAME, 7, QFont.Weight.Bold))
        mem_pill.setStyleSheet("""
            color: #38bdf8;
            background: rgba(56, 189, 248, 0.14);
            border: 1px solid rgba(56, 189, 248, 0.38);
            border-radius: 6px;
            padding: 2px 8px;
            letter-spacing: 0.5px;
        """)
        title_top.addWidget(mem_pill)
        title_top.addStretch()
        title_v.addLayout(title_top)

        rows = all_entries_for_ui()
        profile_name = active_profile().get("name", "Current user")
        sub_lbl = QLabel(f"{len(rows)} persistent memories for {profile_name} — newest first. Stored locally & private.")
        sub_lbl.setFont(QFont(APP_FONT_NAME, 8))
        sub_lbl.setStyleSheet("color: #94a3b8; background: transparent;")
        title_v.addWidget(sub_lbl)
        hdr.addLayout(title_v)
        hdr.addStretch()

        close_x = QPushButton("✕")
        close_x.setFixedSize(28, 28)
        close_x.setCursor(Qt.CursorShape.PointingHandCursor)
        close_x.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.06);
                color: #94a3b8;
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 14px;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: #ef4444;
                color: #ffffff;
                border-color: #ef4444;
            }
        """)
        close_x.clicked.connect(self.hide)
        hdr.addWidget(close_x)
        self._lay.addLayout(hdr)

        # ── Divider ──
        div = QFrame()
        div.setFixedHeight(1)
        div.setStyleSheet("background: rgba(255, 255, 255, 0.08); border: none;")
        self._lay.addWidget(div)

        # ── Facts List or Empty Placeholder ──
        if not rows:
            empty_frame = QFrame()
            empty_frame.setStyleSheet("""
                QFrame {
                    background: rgba(15, 23, 42, 0.4);
                    border: 1px dashed rgba(255, 255, 255, 0.12);
                    border-radius: 12px;
                    padding: 24px;
                }
            """)
            ef_lay = QVBoxLayout(empty_frame)
            ef_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
            ef_lay.setSpacing(6)

            e_icon = QLabel()
            e_icon.setPixmap(_render_hub_svg("neural_memory", 44, "#38bdf8"))
            e_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
            e_icon.setStyleSheet("background: transparent; border: none;")
            ef_lay.addWidget(e_icon)

            e_lbl = QLabel("No memories stored yet")
            e_lbl.setFont(QFont(APP_FONT_NAME, 10, QFont.Weight.Bold))
            e_lbl.setStyleSheet("color: #e2e8f0; background: transparent;")
            e_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            ef_lay.addWidget(e_lbl)

            e_sub = QLabel("Charlie will automatically record personal facts and preferences as you talk.")
            e_sub.setFont(QFont(APP_FONT_NAME, 8))
            e_sub.setStyleSheet("color: #64748b; background: transparent;")
            e_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
            ef_lay.addWidget(e_sub)

            self._lay.addWidget(empty_frame)
        else:
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFixedHeight(min(450, max(140, 72 * len(rows) + 20)))
            scroll.setStyleSheet("""
                QScrollArea {
                    border: 1px solid rgba(255, 255, 255, 0.08);
                    border-radius: 12px;
                    background: rgba(8, 12, 20, 0.55);
                }
                QScrollBar:vertical {
                    background: transparent;
                    width: 6px;
                    margin: 4px 2px 4px 0px;
                    border-radius: 3px;
                }
                QScrollBar::handle:vertical {
                    background: rgba(255, 255, 255, 0.18);
                    min-height: 24px;
                    border-radius: 3px;
                }
                QScrollBar::handle:vertical:hover {
                    background: rgba(129, 140, 248, 0.6);
                }
                QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                    height: 0px;
                    background: none;
                }
                QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                    background: none;
                }
            """)
            inner = QWidget()
            ilay = QVBoxLayout(inner)
            ilay.setContentsMargins(10, 10, 10, 10)
            ilay.setSpacing(8)

            for r in rows:
                card = QFrame()
                card.setObjectName("FactCard")
                cat_raw = r.get("category", "")
                cat_title, cat_col, cat_bg, cat_bd = self._get_category_badge_style(cat_raw)
                card.setStyleSheet(f"""
                    QFrame#FactCard {{
                        background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 rgba(15, 23, 42, 0.85), stop:1 rgba(15, 23, 42, 0.50));
                        border: 1px solid rgba(255, 255, 255, 0.08);
                        border-left: 3.5px solid {cat_col};
                        border-radius: 10px;
                    }}
                    QFrame#FactCard:hover {{
                        background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 rgba(30, 41, 59, 0.90), stop:1 rgba(30, 41, 59, 0.60));
                        border-color: rgba(56, 189, 248, 0.40);
                        border-left: 3.5px solid {cat_col};
                    }}
                """)
                c_lay = QVBoxLayout(card)
                c_lay.setContentsMargins(14, 10, 14, 10)
                c_lay.setSpacing(5)

                # Card Top Row: Title + Category Pill + Timestamp + Delete Button
                t_row = QHBoxLayout()
                t_row.setSpacing(8)

                raw_k = r.get("key", "")
                disp_k = self._format_fact_key(raw_k)
                k_lbl = QLabel(disp_k)
                k_lbl.setFont(QFont(APP_FONT_NAME, 8, QFont.Weight.Bold))
                k_lbl.setStyleSheet("color: #ffffff; background: transparent;")
                t_row.addWidget(k_lbl)

                cat_badge = QLabel(cat_title)
                cat_badge.setFont(QFont(APP_FONT_NAME, 7, QFont.Weight.Bold))
                cat_badge.setStyleSheet(f"""
                    color: {cat_col};
                    background: {cat_bg};
                    border: 1px solid {cat_bd};
                    border-radius: 6px;
                    padding: 2px 7px;
                    letter-spacing: 0.3px;
                """)
                t_row.addWidget(cat_badge)

                upd = r.get("updated", "")
                if upd:
                    date_lbl = QLabel(f"· {upd}")
                    date_lbl.setFont(QFont(APP_FONT_NAME, 7))
                    date_lbl.setStyleSheet("color: #64748b; background: transparent;")
                    t_row.addWidget(date_lbl)

                t_row.addStretch()

                del_btn = QPushButton("✕")
                del_btn.setFixedSize(22, 22)
                del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                del_btn.setToolTip("Forget this memory")
                del_btn.setStyleSheet("""
                    QPushButton {
                        background: rgba(255, 255, 255, 0.05);
                        color: #64748b;
                        border: 1px solid rgba(255, 255, 255, 0.10);
                        border-radius: 11px;
                        font-size: 10px;
                        font-weight: bold;
                    }
                    QPushButton:hover {
                        background: rgba(239, 68, 68, 0.22);
                        color: #ef4444;
                        border-color: rgba(239, 68, 68, 0.50);
                    }
                """)
                del_btn.clicked.connect(
                    lambda _=False, c=r["category"], k=r["key"]: self._forget(c, k)
                )
                t_row.addWidget(del_btn)
                c_lay.addLayout(t_row)

                # Card Bottom Row: Fact Value
                val_text = str(r.get("value", "")).strip()
                val_lbl = QLabel(val_text)
                val_lbl.setWordWrap(True)
                val_lbl.setFont(QFont(APP_FONT_NAME, 8))
                val_lbl.setStyleSheet("color: #e2e8f0; background: transparent; line-height: 1.4;")
                c_lay.addWidget(val_lbl)

                ilay.addWidget(card)

            ilay.addStretch()
            scroll.setWidget(inner)
            self._lay.addWidget(scroll)

        # ── Footer: Privacy info + Close Button ──
        footer = QHBoxLayout()
        footer.setContentsMargins(4, 6, 4, 0)
        footer.setSpacing(8)

        priv_box = QHBoxLayout()
        priv_box.setSpacing(6)
        sec_icon = QLabel()
        sec_icon.setPixmap(_render_hub_svg("security_shield", 14, "#10b981"))
        sec_icon.setStyleSheet("background: transparent; border: none;")
        priv_box.addWidget(sec_icon)

        priv_lbl = QLabel("Stored locally in profile directory · 100% Private & Offline")
        priv_lbl.setFont(QFont(APP_FONT_NAME, 7, QFont.Weight.DemiBold))
        priv_lbl.setStyleSheet("color: #94a3b8; background: transparent;")
        priv_box.addWidget(priv_lbl)
        footer.addLayout(priv_box)

        footer.addStretch()

        close_btn = QPushButton("Close")
        close_btn.setFixedHeight(32)
        close_btn.setFont(QFont(APP_FONT_NAME, 8, QFont.Weight.Bold))
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #4f46e5, stop:1 #6366f1);
                color: #ffffff;
                border: 1px solid rgba(165, 180, 252, 0.45);
                border-radius: 9px;
                padding: 4px 24px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #4338ca, stop:1 #4f46e5);
                border-color: #ffffff;
            }
        """)
        close_btn.clicked.connect(self.hide)
        footer.addWidget(close_btn)
        self._lay.addLayout(footer)

        self._settle(before)
        QTimer.singleShot(0, lambda g=before: self._settle(g))

    def _forget(self, category: str, key: str):
        from memory.memory_manager import forget
        forget(key, category)
        QTimer.singleShot(0, self._rebuild)


class KnowledgeOverlay(_HudOverlay):
    """Local offline RAG Knowledge Base — Index documents/code & semantic search."""

    _OW = 720

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            KnowledgeOverlay {{
                background: {C.PANEL};
                border: 1px solid {C.BORDER};
                border-radius: 16px;
            }}
        """)
        self.setFixedWidth(self._OW)
        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(22, 18, 22, 18)
        self._lay.setSpacing(12)
        self._build_ui()
        self._refresh_stats()

    def _build_ui(self):
        # ── Header Row with Professional Vector Logo ──
        hdr = QHBoxLayout()
        hdr.setSpacing(12)

        logo_box = QLabel()
        logo_box.setFixedSize(38, 38)
        logo_box.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo_box.setStyleSheet("""
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 rgba(99, 102, 241, 0.28), stop:1 rgba(139, 92, 246, 0.16));
            border: 1px solid rgba(129, 140, 248, 0.45);
            border-radius: 10px;
            padding: 0px;
        """)
        logo_box.setPixmap(_render_hub_svg("rag_database", 22, "#818cf8"))
        hdr.addWidget(logo_box)

        title_v = QVBoxLayout()
        title_v.setSpacing(2)

        title_top = QHBoxLayout()
        title_top.setSpacing(8)
        t_lbl = QLabel("LOCAL KNOWLEDGE BASE (RAG)")
        t_lbl.setFont(QFont(APP_FONT_NAME, 11, QFont.Weight.Bold))
        t_lbl.setStyleSheet("color: #ffffff; background: transparent; letter-spacing: 0.5px;")
        title_top.addWidget(t_lbl)

        engine_pill = QLabel("HYBRID FTS5 + VECTORS")
        engine_pill.setFont(QFont(APP_FONT_NAME, 7, QFont.Weight.Bold))
        engine_pill.setStyleSheet("""
            color: #34d399;
            background: rgba(52, 211, 153, 0.12);
            border: 1px solid rgba(52, 211, 153, 0.3);
            border-radius: 4px;
            padding: 2px 7px;
        """)
        title_top.addWidget(engine_pill)
        title_top.addStretch()
        title_v.addLayout(title_top)

        sub_lbl = QLabel("Index local folders, PDFs, codebases & docs for offline semantic search & AI context.")
        sub_lbl.setFont(QFont(APP_FONT_NAME, 8))
        sub_lbl.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent;")
        title_v.addWidget(sub_lbl)
        hdr.addLayout(title_v)
        hdr.addStretch()

        close_btn = QPushButton()
        close_btn.setIcon(_render_svg_icon("rag_x", 12, "#cbd5e1"))
        close_btn.setIconSize(QSize(12, 12))
        close_btn.setFixedSize(28, 28)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.06);
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 14px;
            }
            QPushButton:hover {
                background: #ef4444;
                border-color: #ef4444;
            }
        """)
        close_btn.clicked.connect(self.hide)
        hdr.addWidget(close_btn)
        self._lay.addLayout(hdr)

        # ── Stats KPI Dashboard (4 Modern Metric Cards) ──
        stats_frame = QFrame()
        stats_frame.setStyleSheet("""
            QFrame {
                background: rgba(15, 23, 42, 0.65);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 10px;
            }
        """)
        s_lay = QHBoxLayout(stats_frame)
        s_lay.setContentsMargins(10, 8, 10, 8)
        s_lay.setSpacing(10)

        # Card 1: Documents
        c1 = QFrame()
        c1.setStyleSheet("background: rgba(255, 255, 255, 0.03); border: 1px solid rgba(255, 255, 255, 0.06); border-radius: 8px;")
        c1_l = QHBoxLayout(c1)
        c1_l.setContentsMargins(10, 6, 10, 6)
        c1_l.setSpacing(8)
        i1 = QLabel()
        i1.setPixmap(_render_hub_svg("rag_file_doc", 16, "#38bdf8"))
        i1.setStyleSheet("background: transparent; border: none;")
        c1_l.addWidget(i1)
        v1 = QVBoxLayout()
        v1.setSpacing(1)
        self._stat_docs_val = QLabel("0")
        self._stat_docs_val.setFont(QFont(APP_FONT_NAME, 11, QFont.Weight.Bold))
        self._stat_docs_val.setStyleSheet("color: #ffffff; background: transparent; border: none;")
        v1.addWidget(self._stat_docs_val)
        t1 = QLabel("Documents")
        t1.setFont(QFont(APP_FONT_NAME, 7, QFont.Weight.Medium))
        t1.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent; border: none;")
        v1.addWidget(t1)
        c1_l.addLayout(v1)
        s_lay.addWidget(c1)

        # Card 2: Chunks
        c2 = QFrame()
        c2.setStyleSheet("background: rgba(255, 255, 255, 0.03); border: 1px solid rgba(255, 255, 255, 0.06); border-radius: 8px;")
        c2_l = QHBoxLayout(c2)
        c2_l.setContentsMargins(10, 6, 10, 6)
        c2_l.setSpacing(8)
        i2 = QLabel()
        i2.setPixmap(_render_hub_svg("rag_layers", 16, "#a78bfa"))
        i2.setStyleSheet("background: transparent; border: none;")
        c2_l.addWidget(i2)
        v2 = QVBoxLayout()
        v2.setSpacing(1)
        self._stat_chunks_val = QLabel("0")
        self._stat_chunks_val.setFont(QFont(APP_FONT_NAME, 11, QFont.Weight.Bold))
        self._stat_chunks_val.setStyleSheet("color: #ffffff; background: transparent; border: none;")
        v2.addWidget(self._stat_chunks_val)
        t2 = QLabel("Indexed Chunks")
        t2.setFont(QFont(APP_FONT_NAME, 7, QFont.Weight.Medium))
        t2.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent; border: none;")
        v2.addWidget(t2)
        c2_l.addLayout(v2)
        s_lay.addWidget(c2)

        # Card 3: Storage
        c3 = QFrame()
        c3.setStyleSheet("background: rgba(255, 255, 255, 0.03); border: 1px solid rgba(255, 255, 255, 0.06); border-radius: 8px;")
        c3_l = QHBoxLayout(c3)
        c3_l.setContentsMargins(10, 6, 10, 6)
        c3_l.setSpacing(8)
        i3 = QLabel()
        i3.setPixmap(_render_hub_svg("rag_disk", 16, "#fbbf24"))
        i3.setStyleSheet("background: transparent; border: none;")
        c3_l.addWidget(i3)
        v3 = QVBoxLayout()
        v3.setSpacing(1)
        self._stat_size_val = QLabel("0 B")
        self._stat_size_val.setFont(QFont(APP_FONT_NAME, 11, QFont.Weight.Bold))
        self._stat_size_val.setStyleSheet("color: #ffffff; background: transparent; border: none;")
        v3.addWidget(self._stat_size_val)
        t3 = QLabel("Storage")
        t3.setFont(QFont(APP_FONT_NAME, 7, QFont.Weight.Medium))
        t3.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent; border: none;")
        v3.addWidget(t3)
        c3_l.addLayout(v3)
        s_lay.addWidget(c3)

        # Card 4: Architecture
        c4 = QFrame()
        c4.setStyleSheet("background: rgba(52, 211, 153, 0.06); border: 1px solid rgba(52, 211, 153, 0.2); border-radius: 8px;")
        c4_l = QHBoxLayout(c4)
        c4_l.setContentsMargins(10, 6, 10, 6)
        c4_l.setSpacing(8)
        i4 = QLabel()
        i4.setPixmap(_render_hub_svg("rag_bolt", 16, "#34d399"))
        i4.setStyleSheet("background: transparent; border: none;")
        c4_l.addWidget(i4)
        v4 = QVBoxLayout()
        v4.setSpacing(1)
        e_title = QLabel("Hybrid Engine")
        e_title.setFont(QFont(APP_FONT_NAME, 9, QFont.Weight.Bold))
        e_title.setStyleSheet("color: #34d399; background: transparent; border: none;")
        v4.addWidget(e_title)
        e_sub = QLabel("● Active & Local")
        e_sub.setFont(QFont(APP_FONT_NAME, 7, QFont.Weight.DemiBold))
        e_sub.setStyleSheet("color: #22c55e; background: transparent; border: none;")
        v4.addWidget(e_sub)
        c4_l.addLayout(v4)
        s_lay.addWidget(c4)

        self._stats_lbl = QLabel("")
        self._stats_lbl.hide()
        self._lay.addWidget(stats_frame)

        # ── Professional Action Buttons Row ──
        act_row = QHBoxLayout()
        act_row.setSpacing(8)

        btn_folder = QPushButton("  Index Folder")
        btn_folder.setIcon(_render_svg_icon("rag_folder_plus", 14, "#ffffff"))
        btn_folder.setIconSize(QSize(14, 14))
        btn_folder.setFixedHeight(32)
        btn_folder.setFont(QFont(APP_FONT_NAME, 8, QFont.Weight.DemiBold))
        btn_folder.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_folder.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #4f46e5, stop:1 #6366f1);
                color: #ffffff;
                border: 1px solid rgba(165, 180, 252, 0.45);
                border-radius: 7px;
                padding: 0 14px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #4338ca, stop:1 #4f46e5);
                border-color: #818cf8;
            }
        """)
        btn_folder.clicked.connect(self._index_folder)
        act_row.addWidget(btn_folder)

        btn_files = QPushButton("  Index Files")
        btn_files.setIcon(_render_svg_icon("rag_file_plus", 14, "#38bdf8"))
        btn_files.setIconSize(QSize(14, 14))
        btn_files.setFixedHeight(32)
        btn_files.setFont(QFont(APP_FONT_NAME, 8, QFont.Weight.DemiBold))
        btn_files.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_files.setStyleSheet("""
            QPushButton {
                background: rgba(56, 189, 248, 0.12);
                color: #38bdf8;
                border: 1px solid rgba(56, 189, 248, 0.35);
                border-radius: 7px;
                padding: 0 14px;
            }
            QPushButton:hover {
                background: rgba(56, 189, 248, 0.24);
                color: #ffffff;
                border-color: #38bdf8;
            }
        """)
        btn_files.clicked.connect(self._index_files)
        act_row.addWidget(btn_files)

        btn_refresh = QPushButton("  Refresh")
        btn_refresh.setIcon(_render_svg_icon("rag_refresh", 13, "#cbd5e1"))
        btn_refresh.setIconSize(QSize(13, 13))
        btn_refresh.setFixedHeight(32)
        btn_refresh.setFont(QFont(APP_FONT_NAME, 8, QFont.Weight.Medium))
        btn_refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_refresh.setStyleSheet(f"""
            QPushButton {{
                background: rgba(255, 255, 255, 0.04);
                color: #cbd5e1;
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 7px;
                padding: 0 12px;
            }}
            QPushButton:hover {{
                background: rgba(255, 255, 255, 0.08);
                color: #ffffff;
                border-color: rgba(255, 255, 255, 0.2);
            }}
        """)
        btn_refresh.clicked.connect(self._refresh_stats)
        act_row.addWidget(btn_refresh)

        btn_clear = QPushButton("  Clear DB")
        btn_clear.setIcon(_render_svg_icon("rag_trash", 13, "#f87171"))
        btn_clear.setIconSize(QSize(13, 13))
        btn_clear.setFixedHeight(32)
        btn_clear.setFont(QFont(APP_FONT_NAME, 8, QFont.Weight.Medium))
        btn_clear.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_clear.setStyleSheet("""
            QPushButton {
                background: rgba(239, 68, 68, 0.06);
                color: #f87171;
                border: 1px solid rgba(239, 68, 68, 0.25);
                border-radius: 7px;
                padding: 0 12px;
            }
            QPushButton:hover {
                background: rgba(239, 68, 68, 0.16);
                border-color: #ef4444;
            }
        """)
        btn_clear.clicked.connect(self._clear_knowledge)
        act_row.addWidget(btn_clear)
        act_row.addStretch()

        self._lay.addLayout(act_row)

        # Status notification label
        self._status_bar = QLabel("")
        self._status_bar.setFont(QFont(APP_FONT_NAME, 8))
        self._status_bar.setStyleSheet("color: #38bdf8; background: transparent;")
        self._status_bar.hide()
        self._lay.addWidget(self._status_bar)

        # ── Professional Search Bar with SVG Icon ──
        s_box = QFrame()
        s_box.setFixedHeight(38)
        s_box.setStyleSheet("""
            QFrame {
                background: rgba(15, 23, 42, 0.7);
                border: 1px solid rgba(99, 102, 241, 0.25);
                border-radius: 8px;
            }
            QFrame:focus-within {
                border-color: #818cf8;
                background: rgba(15, 23, 42, 0.95);
            }
        """)
        sb_lay = QHBoxLayout(s_box)
        sb_lay.setContentsMargins(12, 2, 4, 2)
        sb_lay.setSpacing(8)

        s_icon = QLabel()
        s_icon.setPixmap(_render_hub_svg("search", 15, "#818cf8"))
        s_icon.setStyleSheet("background: transparent; border: none;")
        sb_lay.addWidget(s_icon)

        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Search indexed knowledge semantically (e.g. 'how does authentication work?')...")
        self._search_input.setFont(QFont(APP_FONT_NAME, 9))
        self._search_input.setStyleSheet("background: transparent; color: #ffffff; border: none;")
        self._search_input.returnPressed.connect(self._run_search)
        sb_lay.addWidget(self._search_input, 1)

        search_btn = QPushButton("  Search")
        search_btn.setIcon(_render_svg_icon("sparkles", 13, "#ffffff"))
        search_btn.setIconSize(QSize(13, 13))
        search_btn.setFixedHeight(28)
        search_btn.setFont(QFont(APP_FONT_NAME, 8, QFont.Weight.DemiBold))
        search_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        search_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #6366f1, stop:1 #4f46e5);
                color: #ffffff;
                border: none;
                border-radius: 6px;
                padding: 0 14px;
            }
            QPushButton:hover { background: #4338ca; }
        """)
        search_btn.clicked.connect(self._run_search)
        sb_lay.addWidget(search_btn)
        self._lay.addWidget(s_box)

        # ── Results Scroll Area ──
        self._results_scroll = QScrollArea()
        self._results_scroll.setWidgetResizable(True)
        self._results_scroll.setFixedHeight(230)
        self._results_scroll.setStyleSheet("""
            QScrollArea { background: transparent; border: none; }
            QScrollBar:vertical { background: transparent; width: 6px; border: none; margin: 2px; }
            QScrollBar::handle:vertical { background: rgba(255, 255, 255, 0.16); border-radius: 3px; min-height: 25px; }
            QScrollBar::handle:vertical:hover { background: rgba(99, 102, 241, 0.6); }
        """)
        self._results_widget = QWidget()
        self._results_widget.setStyleSheet("background: transparent;")
        self._results_layout = QVBoxLayout(self._results_widget)
        self._results_layout.setContentsMargins(0, 4, 4, 4)
        self._results_layout.setSpacing(8)
        self._results_scroll.setWidget(self._results_widget)
        self._lay.addWidget(self._results_scroll)

        self._show_empty_placeholder("Search indexed files above or click 'Index Folder / Files' to add knowledge.")

    def _show_empty_placeholder(self, text: str):
        while self._results_layout.count():
            item = self._results_layout.takeAt(0)
            if item is not None and item.widget():
                w = item.widget()
                if w is not None:
                    w.deleteLater()

        holder = QFrame()
        holder.setStyleSheet("""
            QFrame {
                background: rgba(15, 23, 42, 0.4);
                border: 1px dashed rgba(255, 255, 255, 0.1);
                border-radius: 12px;
            }
        """)
        h_lay = QVBoxLayout(holder)
        h_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        h_lay.setContentsMargins(20, 26, 20, 26)
        h_lay.setSpacing(6)

        icon_lbl = QLabel()
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_lbl.setPixmap(_render_hub_svg("rag_database", 30, "#6366f1"))
        icon_lbl.setStyleSheet("background: transparent; border: none;")
        h_lay.addWidget(icon_lbl)

        t_lbl = QLabel("Local Knowledge Base Ready")
        t_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        t_lbl.setFont(QFont(APP_FONT_NAME, 10, QFont.Weight.Bold))
        t_lbl.setStyleSheet("color: #e2e8f0; background: transparent; border: none;")
        h_lay.addWidget(t_lbl)

        sub = QLabel(text)
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub.setFont(QFont(APP_FONT_NAME, 8))
        sub.setStyleSheet("color: #64748b; background: transparent; border: none;")
        h_lay.addWidget(sub)

        pills_row = QHBoxLayout()
        pills_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pills_row.setSpacing(6)
        for ext in ["PDF Documents", "Markdown", "Codebases", "Text & CSV", "JSON"]:
            pill = QLabel(ext)
            pill.setFont(QFont(APP_FONT_NAME, 7, QFont.Weight.Medium))
            pill.setStyleSheet("color: #94a3b8; background: rgba(255, 255, 255, 0.05); border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 4px; padding: 2px 6px;")
            pills_row.addWidget(pill)
        h_lay.addSpacing(4)
        h_lay.addLayout(pills_row)

        self._results_layout.addWidget(holder)

    def _show_status(self, text: str, color: str = "#38bdf8"):
        self._status_bar.setText(text)
        self._status_bar.setStyleSheet(f"color: {color}; background: transparent; padding: 2px 0;")
        self._status_bar.show()

    def _refresh_stats(self):
        try:
            from engine.rag import get_rag
            st = get_rag().get_status()
            docs = st.get("total_documents", 0)
            chunks = st.get("total_chunks", 0)
            size_bytes = st.get("total_indexed_bytes", 0)
            if size_bytes > 1_000_000:
                size_str = f"{size_bytes / 1_000_000:.1f} MB"
            elif size_bytes > 1_000:
                size_str = f"{size_bytes / 1_000:.1f} KB"
            else:
                size_str = f"{size_bytes} B"

            if hasattr(self, "_stat_docs_val"):
                self._stat_docs_val.setText(str(docs))
            if hasattr(self, "_stat_chunks_val"):
                self._stat_chunks_val.setText(str(chunks))
            if hasattr(self, "_stat_size_val"):
                self._stat_size_val.setText(size_str)
            if hasattr(self, "_stats_lbl"):
                self._stats_lbl.setText(f"Indexed: <b>{docs} documents</b> · <b>{chunks} chunks</b> · {size_str}")
        except Exception as e:
            if hasattr(self, "_stats_lbl"):
                self._stats_lbl.setText(f"Status: ready ({e})")

    def _index_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Folder to Index")
        if not folder:
            return
        self._show_status(f"Indexing '{Path(folder).name}' in background...", "#38bdf8")

        def _worker():
            try:
                from engine.rag import get_rag
                res = get_rag().index_directory(folder)
                msg = f"✓ Indexed {res.get('indexed_files', 0)} file(s) ({res.get('total_new_chunks', 0)} chunks)."
                QTimer.singleShot(0, lambda: self._show_status(msg, "#4ade80"))
                QTimer.singleShot(0, self._refresh_stats)
            except Exception as e:
                QTimer.singleShot(0, lambda: self._show_status(f"Indexing error: {e}", "#f87171"))

        threading.Thread(target=_worker, daemon=True).start()

    def _index_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Select Documents to Index",
            filter="Documents (*.txt *.md *.pdf *.docx *.py *.js *.ts *.json *.csv *.html *.css);;All Files (*.*)",
        )
        if not files:
            return
        self._show_status(f"Indexing {len(files)} file(s)...", "#38bdf8")

        def _worker():
            try:
                from engine.rag import get_rag
                rag = get_rag()
                indexed = 0
                chunks = 0
                for f in files:
                    r = rag.index_file(f)
                    if r.get("status") == "indexed":
                        indexed += 1
                        chunks += r.get("chunks", 0)
                msg = f"✓ Indexed {indexed} new file(s) ({chunks} chunks)."
                QTimer.singleShot(0, lambda: self._show_status(msg, "#4ade80"))
                QTimer.singleShot(0, self._refresh_stats)
            except Exception as e:
                QTimer.singleShot(0, lambda: self._show_status(f"File index error: {e}", "#f87171"))

        threading.Thread(target=_worker, daemon=True).start()

    def _clear_knowledge(self):
        try:
            from engine.rag import get_rag
            get_rag().clear()
            self._show_empty_placeholder("Knowledge base cleared.")
            self._show_status("Knowledge base cleared.", "#f87171")
            self._refresh_stats()
        except Exception as e:
            self._show_status(f"Clear failed: {e}", "#f87171")

    def _run_search(self):
        query = self._search_input.text().strip()
        if not query:
            return
        self._show_status(f"Searching for '{query}'...", "#818cf8")
        try:
            from engine.rag import get_rag
            results = get_rag().search(query, top_k=5)
        except Exception as e:
            self._show_status(f"Search failed: {e}", "#f87171")
            return

        while self._results_layout.count():
            item = self._results_layout.takeAt(0)
            if item is not None and item.widget():
                w = item.widget()
                if w is not None:
                    w.deleteLater()

        if not results:
            self._show_empty_placeholder(f"No document matches found for '{query}'.")
            self._show_status("0 matches found.", "#94a3b8")
            return

        self._show_status(f"Found {len(results)} relevant match(es).", "#4ade80")
        for item in results:
            card = QFrame()
            card.setStyleSheet("""
                QFrame {
                    background: rgba(255, 255, 255, 0.03);
                    border: 1px solid rgba(255, 255, 255, 0.08);
                    border-radius: 8px;
                    padding: 8px;
                }
                QFrame:hover {
                    border-color: rgba(99, 102, 241, 0.4);
                    background: rgba(99, 102, 241, 0.06);
                }
            """)
            c_lay = QVBoxLayout(card)
            c_lay.setContentsMargins(10, 8, 10, 8)
            c_lay.setSpacing(4)

            top_h = QHBoxLayout()
            top_h.setSpacing(6)

            fn_icon = QLabel()
            fn_icon.setPixmap(_render_hub_svg("rag_file_doc", 15, "#38bdf8"))
            fn_icon.setStyleSheet("background: transparent; border: none;")
            top_h.addWidget(fn_icon)

            fn_lbl = QLabel(item['filename'])
            fn_lbl.setFont(QFont(APP_FONT_NAME, 9, QFont.Weight.Bold))
            fn_lbl.setStyleSheet("color: #ffffff; background: transparent; border: none;")
            top_h.addWidget(fn_lbl)

            score_pct = int(item.get("score", 0) * 100)
            score_color = "#4ade80" if score_pct >= 70 else ("#38bdf8" if score_pct >= 40 else "#94a3b8")
            score_lbl = QLabel(f"{score_pct}% Match")
            score_lbl.setFont(QFont(APP_FONT_NAME, 8, QFont.Weight.DemiBold))
            score_lbl.setStyleSheet(f"color: {score_color}; background: rgba(255, 255, 255, 0.06); border-radius: 4px; padding: 1px 6px; border: none;")
            top_h.addWidget(score_lbl)
            top_h.addStretch()

            path_lbl = QLabel(str(item.get("path", "")))
            path_lbl.setFont(QFont(APP_FONT_NAME, 7))
            path_lbl.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent; border: none;")
            top_h.addWidget(path_lbl)
            c_lay.addLayout(top_h)

            snip = item.get("snippet", "").strip().replace("\r\n", "\n")
            if len(snip) > 220:
                snip = snip[:220] + "..."
            snip_lbl = QLabel(snip)
            snip_lbl.setFont(QFont("Consolas", 8))
            snip_lbl.setWordWrap(True)
            snip_lbl.setStyleSheet("color: #cbd5e1; background: rgba(0, 0, 0, 0.25); border-radius: 4px; padding: 4px 6px; border: none;")
            c_lay.addWidget(snip_lbl)

            self._results_layout.addWidget(card)

        self._results_layout.addStretch()


class ProactiveDaemonOverlay(_HudOverlay):
    """Autonomous Background Proactive Daemon — Real-time ambient assistant monitor."""

    _OW = 680

    def __init__(self, parent=None, on_action=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            ProactiveDaemonOverlay {{
                background: #080c14;
                border: 1px solid rgba(52, 211, 153, 0.45);
                border-radius: 14px;
            }}
        """)
        self.setFixedWidth(self._OW)
        self._on_action = on_action
        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(20, 16, 20, 16)
        self._lay.setSpacing(10)
        self._check_boxes: dict[str, QCheckBox] = {}
        self._build_ui()
        self._refresh_state()

    def _build_ui(self):
        # Header
        hdr = QHBoxLayout()
        hdr.setSpacing(12)

        logo_lbl = QLabel()
        logo_lbl.setPixmap(_render_hub_svg("daemon_logo", 34, "#10b981"))
        logo_lbl.setStyleSheet("background: transparent; border: none;")
        hdr.addWidget(logo_lbl)

        title_v = QVBoxLayout()
        title_v.setSpacing(2)

        title_h = QHBoxLayout()
        title_h.setSpacing(8)
        t_lbl = QLabel("AUTONOMOUS PROACTIVE DAEMON")
        t_lbl.setFont(QFont(APP_FONT_NAME, 11, QFont.Weight.Bold))
        t_lbl.setStyleSheet("color: #ffffff; background: transparent; letter-spacing: 0.5px;")
        title_h.addWidget(t_lbl)

        badge_lbl = QLabel("AMBIENT 24/7")
        badge_lbl.setFont(QFont(APP_FONT_NAME, 7, QFont.Weight.Bold))
        badge_lbl.setStyleSheet("""
            color: #34d399; background: rgba(16, 185, 129, 0.16);
            border: 1px solid rgba(52, 211, 153, 0.4);
            border-radius: 4px; padding: 1px 6px;
        """)
        title_h.addWidget(badge_lbl)
        title_h.addStretch()
        title_v.addLayout(title_h)

        sub_lbl = QLabel("Real-time ambient observer: hardware health, task reminders, briefings & wellness.")
        sub_lbl.setFont(QFont(APP_FONT_NAME, 8))
        sub_lbl.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent;")
        title_v.addWidget(sub_lbl)
        hdr.addLayout(title_v)
        hdr.addStretch()

        close_btn = QPushButton()
        close_btn.setFixedSize(28, 28)
        close_btn.setIcon(_render_svg_icon("rag_x", 12, "#94a3b8"))
        close_btn.setIconSize(QSize(12, 12))
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.06);
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 14px;
            }
            QPushButton:hover {
                background: #ef4444;
                border-color: #ef4444;
            }
        """)
        close_btn.clicked.connect(self.hide)
        hdr.addWidget(close_btn)
        self._lay.addLayout(hdr)

        # Ribbon with status and quick action
        ribbon = QFrame()
        ribbon.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 rgba(16, 185, 129, 0.12), stop:1 rgba(6, 78, 59, 0.22));
                border: 1px solid rgba(52, 211, 153, 0.32);
                border-radius: 10px;
            }
        """)
        r_lay = QHBoxLayout(ribbon)
        r_lay.setContentsMargins(14, 8, 14, 8)
        r_lay.setSpacing(10)
        self._status_lbl = QLabel("Daemon: Initializing...")
        self._status_lbl.setFont(QFont(APP_FONT_NAME, 8, QFont.Weight.Medium))
        self._status_lbl.setStyleSheet("color: #cbd5e1; background: transparent;")
        r_lay.addWidget(self._status_lbl, 1)

        self._toggle_btn = QPushButton("Pause")
        self._toggle_btn.setFixedHeight(28)
        self._toggle_btn.setFont(QFont(APP_FONT_NAME, 8, QFont.Weight.DemiBold))
        self._toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._toggle_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.08); color: #e2e8f0;
                border: 1px solid rgba(255, 255, 255, 0.18); border-radius: 6px; padding: 0 12px;
            }
            QPushButton:hover {
                background: rgba(52, 211, 153, 0.25); border-color: #34d399; color: #ffffff;
            }
        """)
        self._toggle_btn.clicked.connect(self._toggle_daemon_state)
        r_lay.addWidget(self._toggle_btn)

        eval_btn = QPushButton(" Evaluate Now")
        eval_btn.setIcon(_render_svg_icon("rag_bolt", 13, "#ffffff"))
        eval_btn.setIconSize(QSize(13, 13))
        eval_btn.setFixedHeight(28)
        eval_btn.setFont(QFont(APP_FONT_NAME, 8, QFont.Weight.Bold))
        eval_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        eval_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #10b981, stop:1 #059669);
                color: #ffffff;
                border: 1px solid rgba(52, 211, 153, 0.6);
                border-radius: 6px; padding: 0 12px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #34d399, stop:1 #10b981);
                border-color: #6ee7b7;
            }
        """)
        eval_btn.clicked.connect(self._evaluate_now)
        r_lay.addWidget(eval_btn)
        self._lay.addWidget(ribbon)

        # Settings Grid
        s_box = QFrame()
        s_box.setStyleSheet("""
            QFrame {
                background: rgba(255, 255, 255, 0.025);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 10px;
            }
        """)
        s_main_lay = QVBoxLayout(s_box)
        s_main_lay.setContentsMargins(14, 10, 14, 12)
        s_main_lay.setSpacing(8)

        s_header = QLabel("SURVEILLANCE MONITORS & NOTIFICATION CHANNELS")
        s_header.setFont(QFont(APP_FONT_NAME, 7, QFont.Weight.Bold))
        s_header.setStyleSheet("color: #64748b; background: transparent; letter-spacing: 0.6px;")
        s_main_lay.addWidget(s_header)

        sb_lay = QGridLayout()
        sb_lay.setHorizontalSpacing(18)
        sb_lay.setVerticalSpacing(8)

        toggles_def = [
            ("check_battery", "Critical Battery Discharge Alert (<20%)", 0, 0),
            ("check_resources", "High CPU & RAM Usage Spike Alert (>92%)", 0, 1),
            ("check_tasks", "Pending Task Deadlines & Reminders", 1, 0),
            ("check_briefing", "Morning Executive Briefing Auto-Trigger", 1, 1),
            ("check_wellness", "Ergonomics, Focus & Hydration Breaks (90m)", 2, 0),
            ("voice_alerts", "Voice Spoken Audio Alerts (TTS)", 2, 1),
        ]
        for key, title, row, col in toggles_def:
            cb = QCheckBox(title)
            cb.setFont(QFont(APP_FONT_NAME, 8))
            cb.setStyleSheet(f"""
                QCheckBox {{ color: #cbd5e1; background: transparent; spacing: 8px; }}
                QCheckBox::indicator {{ width: 15px; height: 15px; border-radius: 4px; border: 1px solid #475569; background: #0f172a; }}
                QCheckBox::indicator:hover {{ border-color: #34d399; }}
                QCheckBox::indicator:checked {{ background: #10b981; border-color: #34d399; }}
                QCheckBox:hover {{ color: #ffffff; }}
            """)
            cb.toggled.connect(lambda chk, k=key: self._on_setting_changed(k, chk))
            sb_lay.addWidget(cb, row, col)
            self._check_boxes[key] = cb

        s_main_lay.addLayout(sb_lay)
        self._lay.addWidget(s_box)

        # Recent Nudges Title Row
        sec_row = QHBoxLayout()
        sec_lbl = QLabel("RECENT AMBIENT ADVISORIES & NUDGES")
        sec_lbl.setFont(QFont(APP_FONT_NAME, 8, QFont.Weight.Bold))
        sec_lbl.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent; letter-spacing: 0.5px;")
        sec_row.addWidget(sec_lbl)
        sec_row.addStretch()

        clear_btn = QPushButton(" Clear History")
        clear_btn.setIcon(_render_svg_icon("rag_trash", 12, "#94a3b8"))
        clear_btn.setIconSize(QSize(12, 12))
        clear_btn.setFixedHeight(22)
        clear_btn.setFont(QFont(APP_FONT_NAME, 7, QFont.Weight.Medium))
        clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        clear_btn.setStyleSheet("""
            QPushButton {
                color: #94a3b8; background: transparent; border: 1px solid transparent;
                border-radius: 4px; padding: 0 6px;
            }
            QPushButton:hover {
                color: #f87171; background: rgba(248, 113, 113, 0.1); border-color: rgba(248, 113, 113, 0.25);
            }
        """)
        clear_btn.clicked.connect(self._clear_history)
        sec_row.addWidget(clear_btn)
        self._lay.addLayout(sec_row)

        # Nudges Scroll Area
        self._nudges_scroll = QScrollArea()
        self._nudges_scroll.setWidgetResizable(True)
        self._nudges_scroll.setFixedHeight(175)
        self._nudges_scroll.setStyleSheet("""
            QScrollArea { background: transparent; border: none; }
            QScrollBar:vertical { background: transparent; width: 6px; border: none; margin: 2px; }
            QScrollBar::handle:vertical { background: rgba(255, 255, 255, 0.16); border-radius: 3px; min-height: 25px; }
            QScrollBar::handle:vertical:hover { background: rgba(52, 211, 153, 0.6); }
        """)
        self._nudges_widget = QWidget()
        self._nudges_widget.setStyleSheet("background: transparent;")
        self._nudges_layout = QVBoxLayout(self._nudges_widget)
        self._nudges_layout.setContentsMargins(0, 2, 4, 2)
        self._nudges_layout.setSpacing(6)
        self._nudges_scroll.setWidget(self._nudges_widget)
        self._lay.addWidget(self._nudges_scroll)

    def _refresh_state(self):
        from engine.intelligence.proactive_advisor import (
            get_proactive_advisor, get_proactive_daemon, load_proactive_settings,
        )
        settings = load_proactive_settings()
        daemon = get_proactive_daemon()
        is_on = daemon.is_running() and settings.get("enabled", True)

        if is_on:
            self._status_lbl.setText("🟢 <b>Daemon Active</b> · Ambient observation continuous every 30s")
            self._status_lbl.setStyleSheet("color: #4ade80; background: transparent;")
            self._toggle_btn.setText("Pause")
        else:
            self._status_lbl.setText("⏸ <b>Daemon Paused</b> · Ambient background observation disabled")
            self._status_lbl.setStyleSheet("color: #94a3b8; background: transparent;")
            self._toggle_btn.setText("Resume")

        for k, cb in self._check_boxes.items():
            cb.blockSignals(True)
            cb.setChecked(bool(settings.get(k, True)))
            cb.blockSignals(False)

        # Populate nudges
        advisor = get_proactive_advisor()
        recent = advisor.get_recent_nudges()

        while self._nudges_layout.count():
            item = self._nudges_layout.takeAt(0)
            if item is not None and item.widget():
                w = item.widget()
                if w is not None:
                    w.deleteLater()

        if not recent:
            empty_box = QFrame()
            empty_box.setStyleSheet("""
                QFrame {
                    background: rgba(255, 255, 255, 0.02);
                    border: 1px dashed rgba(52, 211, 153, 0.25);
                    border-radius: 8px;
                    padding: 16px;
                }
            """)
            eb_lay = QVBoxLayout(empty_box)
            eb_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
            eb_lay.setSpacing(6)

            e_icon = QLabel()
            e_icon.setPixmap(_render_hub_svg("daemon_logo", 30, "#34d399"))
            e_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
            e_icon.setStyleSheet("background: transparent; border: none;")
            eb_lay.addWidget(e_icon)

            lbl_t = QLabel("Autonomous Observer Active")
            lbl_t.setFont(QFont(APP_FONT_NAME, 9, QFont.Weight.DemiBold))
            lbl_t.setStyleSheet("color: #e2e8f0; background: transparent; border: none;")
            lbl_t.setAlignment(Qt.AlignmentFlag.AlignCenter)
            eb_lay.addWidget(lbl_t)

            lbl = QLabel("No pending advisories · Charlie is quietly monitoring system health, agenda & wellness.")
            lbl.setFont(QFont(APP_FONT_NAME, 8))
            lbl.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent; border: none;")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            eb_lay.addWidget(lbl)

            self._nudges_layout.addWidget(empty_box)
            return

        for nudge in reversed(recent[-8:]):
            cat_colors = {
                "CRITICAL": ("#ef4444", "rgba(239, 68, 68, 0.15)"),
                "EFFICIENCY": ("#38bdf8", "rgba(56, 189, 248, 0.15)"),
                "HEALTH_WELLNESS": ("#34d399", "rgba(52, 211, 153, 0.15)"),
                "OPPORTUNITY": ("#c084fc", "rgba(192, 132, 252, 0.15)"),
            }
            c_col, c_bg = cat_colors.get(nudge.category, ("#94a3b8", "rgba(255, 255, 255, 0.1)"))

            card = QFrame()
            card.setStyleSheet(f"""
                QFrame {{
                    background: rgba(255, 255, 255, 0.035);
                    border: 1px solid rgba(255, 255, 255, 0.08);
                    border-left: 3px solid {c_col};
                    border-radius: 6px;
                    padding: 4px;
                }}
            """)
            c_lay = QHBoxLayout(card)
            c_lay.setContentsMargins(8, 6, 8, 6)
            c_lay.setSpacing(8)

            badge = QLabel(nudge.category[:4])
            badge.setFont(QFont(APP_FONT_NAME, 7, QFont.Weight.Bold))
            badge.setStyleSheet(f"color: {c_col}; background: {c_bg}; border-radius: 3px; padding: 2px 4px;")
            c_lay.addWidget(badge)

            col = QVBoxLayout()
            col.setSpacing(1)
            t_lbl = QLabel(nudge.title)
            t_lbl.setFont(QFont(APP_FONT_NAME, 8, QFont.Weight.DemiBold))
            t_lbl.setStyleSheet("color: #ffffff; background: transparent;")
            col.addWidget(t_lbl)

            m_lbl = QLabel(nudge.message)
            m_lbl.setFont(QFont(APP_FONT_NAME, 7))
            m_lbl.setWordWrap(True)
            m_lbl.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent;")
            col.addWidget(m_lbl)
            c_lay.addLayout(col, 1)

            if nudge.suggested_action:
                act_btn = QPushButton(f"{nudge.suggested_action[:22]} ›")
                act_btn.setFixedHeight(24)
                act_btn.setFont(QFont(APP_FONT_NAME, 7, QFont.Weight.DemiBold))
                act_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                act_btn.setStyleSheet(f"""
                    QPushButton {{
                        background: {c_bg}; color: {c_col};
                        border: 1px solid {c_col}44; border-radius: 4px; padding: 0 8px;
                    }}
                    QPushButton:hover {{ background: {c_col}; color: #000000; font-weight: bold; }}
                """)
                act_btn.clicked.connect(lambda _=False, n=nudge: self._dispatch_nudge_action(n))
                c_lay.addWidget(act_btn)

            self._nudges_layout.addWidget(card)

    def _on_setting_changed(self, key: str, val: bool):
        from engine.intelligence.proactive_advisor import load_proactive_settings, save_proactive_settings
        st = load_proactive_settings()
        st[key] = val
        save_proactive_settings(st)

    def _toggle_daemon_state(self):
        from engine.intelligence.proactive_advisor import (
            get_proactive_daemon, load_proactive_settings, save_proactive_settings,
        )
        st = load_proactive_settings()
        daemon = get_proactive_daemon()
        now_enabled = not st.get("enabled", True)
        st["enabled"] = now_enabled
        save_proactive_settings(st)
        if now_enabled:
            daemon.start()
        else:
            daemon.stop()
        self._refresh_state()

    def _evaluate_now(self):
        from engine.intelligence.proactive_advisor import get_proactive_daemon
        daemon = get_proactive_daemon()
        nudge = daemon.run_once()
        self._refresh_state()
        if not nudge:
            self._status_lbl.setText("✓ <b>Context Clean</b> · All systems optimal, no alerts required")
            self._status_lbl.setStyleSheet("color: #38bdf8; background: transparent;")

    def _dispatch_nudge_action(self, nudge):
        self.hide()
        if callable(self._on_action):
            self._on_action(nudge)

    def _clear_history(self):
        from engine.intelligence.proactive_advisor import _HISTORY_FILE
        try:
            if _HISTORY_FILE.exists():
                _HISTORY_FILE.unlink()
        except Exception:
            pass
        self._refresh_state()


class CameraCaptureModal(QDialog):
    """Live Camera Viewfinder to click a photo from laptop camera for OCR & AI recognition."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Laptop Camera — Vision Capture")
        self.setFixedSize(680, 560)
        self.setModal(True)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
        self.setStyleSheet("""
            QDialog {
                background: #080d1a;
                border: 1px solid rgba(56, 189, 248, 0.4);
                border-radius: 12px;
            }
        """)
        self._cap = None
        self._captured_img = None
        self._last_frame = None
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._next_frame)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(10)

        # Header
        hdr = QHBoxLayout()
        hdr_lbl = QLabel("📷  LAPTOP CAMERA VIEWFINDER")
        hdr_lbl.setFont(QFont(APP_FONT_NAME, 11, QFont.Weight.Bold))
        hdr_lbl.setStyleSheet("color: #38bdf8;")
        hdr.addWidget(hdr_lbl)
        hdr.addStretch()

        self._status_badge = QLabel("INITIALIZING…")
        self._status_badge.setFont(QFont(APP_FONT_NAME, 8, QFont.Weight.DemiBold))
        self._status_badge.setStyleSheet("color: #f59e0b; background: rgba(245, 158, 11, 0.15); border: 1px solid rgba(245, 158, 11, 0.3); border-radius: 4px; padding: 2px 8px;")
        hdr.addWidget(self._status_badge)
        lay.addLayout(hdr)

        sub = QLabel("Position any document, receipt, book, screen, or object in front of your camera.")
        sub.setFont(QFont(APP_FONT_NAME, 8))
        sub.setStyleSheet(f"color: {C.TEXT_DIM};")
        lay.addWidget(sub)

        # Viewfinder card
        vf_card = QFrame()
        vf_card.setStyleSheet("background: #03060d; border: 1px solid rgba(255,255,255,0.12); border-radius: 10px;")
        vf_lay = QVBoxLayout(vf_card)
        vf_lay.setContentsMargins(6, 6, 6, 6)

        self._vf_lbl = QLabel()
        self._vf_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._vf_lbl.setMinimumSize(640, 390)
        self._vf_lbl.setStyleSheet("background: #03060d; color: #64748b; font-size: 13px;")
        self._vf_lbl.setText("Starting laptop camera…")
        vf_lay.addWidget(self._vf_lbl)
        lay.addWidget(vf_card, 1)

        # Controls
        ctrls = QHBoxLayout()
        ctrls.setSpacing(10)

        self._btn_capture = QPushButton("📸  Take Photo & Analyze")
        self._btn_capture.setFixedHeight(38)
        self._btn_capture.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_capture.setFont(QFont(APP_FONT_NAME, 10, QFont.Weight.Bold))
        self._btn_capture.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0284c7, stop:1 #06b6d4);
                color: #ffffff;
                border: 1px solid rgba(56, 189, 248, 0.6);
                border-radius: 8px;
                padding: 0 20px;
            }
            QPushButton:hover {
                background: #0ea5e9;
            }
            QPushButton:disabled {
                background: #1e293b;
                color: #64748b;
                border-color: #334155;
            }
        """)
        self._btn_capture.setEnabled(False)
        self._btn_capture.clicked.connect(self._do_capture)
        ctrls.addWidget(self._btn_capture)

        ctrls.addStretch()

        btn_cancel = QPushButton("Cancel")
        btn_cancel.setFixedHeight(38)
        btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cancel.setFont(QFont(APP_FONT_NAME, 9))
        btn_cancel.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.05);
                color: #94a3b8;
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 8px;
                padding: 0 16px;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.1);
                color: #ffffff;
            }
        """)
        btn_cancel.clicked.connect(self.reject)
        ctrls.addWidget(btn_cancel)
        lay.addLayout(ctrls)

        QTimer.singleShot(100, self._start_cam)

    def _start_cam(self):
        try:
            import cv2
            cam_idx = 0
            try:
                cfg_path = CONFIG_DIR / "api_keys.json"
                if cfg_path.exists():
                    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
                    cam_idx = int(cfg.get("camera_index", 0))
            except Exception:
                pass
            backend = cv2.CAP_DSHOW if _OS == "Windows" else cv2.CAP_ANY
            cap = cv2.VideoCapture(cam_idx, backend)
            if not cap.isOpened() and cam_idx != 0:
                cap = cv2.VideoCapture(0, backend)
            if not cap.isOpened():
                cap = cv2.VideoCapture(0)
            if not cap.isOpened():
                self._status_badge.setText("CAMERA ERROR")
                self._status_badge.setStyleSheet("color: #ef4444; background: rgba(239,68,68,0.15); border-radius: 4px; padding: 2px 8px;")
                self._vf_lbl.setText("❌ Could not connect to laptop camera.\nPlease verify camera permissions or ensure another app is not using it.")
                return

            self._cap = cap
            for _ in range(3):
                cap.read()
            self._status_badge.setText("LIVE FEED")
            self._status_badge.setStyleSheet("color: #10b981; background: rgba(16,185,129,0.15); border-radius: 4px; padding: 2px 8px;")
            self._btn_capture.setEnabled(True)
            self._timer.start(33)
        except Exception as e:
            self._status_badge.setText("ERROR")
            self._vf_lbl.setText(f"Camera initialization failed: {e}")

    def _next_frame(self):
        if not self._cap or not self._cap.isOpened():
            return
        ret, frame = self._cap.read()
        if not ret or frame is None:
            return
        self._last_frame = frame
        try:
            import cv2
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            h, w, ch = rgb.shape
            bytes_per_line = ch * w
            qimg = QImage(rgb.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
            pix = QPixmap.fromImage(qimg)
            scaled = pix.scaled(self._vf_lbl.width(), self._vf_lbl.height(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self._vf_lbl.setPixmap(scaled)
        except Exception:
            pass

    def _shutdown_camera(self):
        try:
            if hasattr(self, "_timer") and self._timer.isActive():
                self._timer.stop()
        except Exception:
            pass
        if getattr(self, "_cap", None) is not None:
            try:
                self._cap.release()
            except Exception:
                pass
            self._cap = None

    def _do_capture(self):
        self._shutdown_camera()
        frame = getattr(self, "_last_frame", None)
        if frame is not None:
            try:
                import cv2
                from PIL import Image
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                self._captured_img = Image.fromarray(rgb)
            except Exception:
                pass
        self.accept()

    def reject(self):
        self._shutdown_camera()
        super().reject()

    def done(self, r):
        self._shutdown_camera()
        super().done(r)

    def closeEvent(self, event):
        self._shutdown_camera()
        super().closeEvent(event)


class ScreenCopilotOverlay(_HudOverlay):
    """OCR Scanner & Vision Studio — Multi-Format Document OCR (PDF, Images, DOCX) & Screen Visual Copilot."""

    _OW = 1180

    def __init__(self, parent=None, on_send_to_chat=None):
        super().__init__(parent)
        self._on_send_to_chat = on_send_to_chat
        self._current_pil_img = None
        self._current_doc_text = ""
        self._current_source_name = "Desktop Screen"
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            ScreenCopilotOverlay {{
                background: {C.PANEL};
                border: 1px solid {C.BORDER};
                border-radius: 16px;
            }}
        """)
        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(22, 16, 22, 16)
        self._lay.setSpacing(10)
        self._build_ui()
        QTimer.singleShot(100, self._refresh_snapshot)

    def _build_ui(self):
        # ── Header Row ──
        hdr = QHBoxLayout()
        hdr.setSpacing(12)

        logo_box = QLabel()
        logo_box.setFixedSize(42, 42)
        logo_box.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo_box.setStyleSheet("""
            background: rgba(99, 102, 241, 0.14);
            border: 1px solid rgba(99, 102, 241, 0.40);
            border-radius: 12px;
        """)
        logo_box.setPixmap(_render_hub_svg("vision_retina_lens", 26, "#818cf8"))
        hdr.addWidget(logo_box)

        title_v = QVBoxLayout()
        title_v.setSpacing(2)

        title_top = QHBoxLayout()
        title_top.setSpacing(8)
        t_lbl = QLabel("NEURAL VISION & OCR STUDIO")
        t_lbl.setFont(QFont(APP_FONT_NAME, 11, QFont.Weight.Bold))
        t_lbl.setStyleSheet("color: #ffffff; background: transparent; letter-spacing: 0.8px;")
        title_top.addWidget(t_lbl)

        engine_pill = QLabel("QUANTUM RETINA v4.2 • MULTIMODAL AI")
        engine_pill.setFont(QFont(APP_FONT_NAME, 7, QFont.Weight.Bold))
        engine_pill.setStyleSheet("""
            background: rgba(99, 102, 241, 0.12);
            color: #a5b4fc;
            border: 1px solid rgba(99, 102, 241, 0.35);
            border-radius: 4px;
            padding: 2px 8px;
            letter-spacing: 0.5px;
        """)
        title_top.addWidget(engine_pill)
        title_top.addStretch()
        title_v.addLayout(title_top)

        sub_lbl = QLabel("High-precision OCR, deep structural analysis & real-time multimodal object classification")
        sub_lbl.setFont(QFont(APP_FONT_NAME, 8))
        sub_lbl.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        title_v.addWidget(sub_lbl)

        hdr.addLayout(title_v)
        hdr.addStretch()

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(30, 30)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.05);
                color: #94a3b8;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 15px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: rgba(239, 68, 68, 0.2);
                color: #f87171;
                border-color: rgba(239, 68, 68, 0.4);
            }
        """)
        close_btn.clicked.connect(self.hide)
        hdr.addWidget(close_btn)
        self._lay.addLayout(hdr)

        # ── Active Source Bar ──
        self._win_bar = QLabel("Source: Ready to scan desktop or open documents (PDF, JPG, PNG, DOCX)")
        self._win_bar.setFont(QFont(APP_FONT_NAME, 8, QFont.Weight.DemiBold))
        self._win_bar.setStyleSheet("""
            background: rgba(255, 255, 255, 0.035);
            color: #93c5fd;
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 8px;
            padding: 5px 12px;
        """)
        self._lay.addWidget(self._win_bar)

        # ── Main Big-Screen 2-Column Workspace ──
        mid = QHBoxLayout()
        mid.setSpacing(16)

        # Left Column: Visual Inspector (Large Image Viewer)
        left_col = QVBoxLayout()
        left_col.setSpacing(8)

        left_hdr = QHBoxLayout()
        left_hdr_lbl = QLabel("DOCUMENT / SCREEN VIEWER")
        left_hdr_lbl.setFont(QFont(APP_FONT_NAME, 8, QFont.Weight.Bold))
        left_hdr_lbl.setStyleSheet("color: #94a3b8; background: transparent; letter-spacing: 0.5px;")
        left_hdr.addWidget(left_hdr_lbl)
        left_hdr.addStretch()
        self._res_badge = QLabel("READY")
        self._res_badge.setFont(QFont(APP_FONT_NAME, 7, QFont.Weight.Medium))
        self._res_badge.setStyleSheet("color: #64748b; background: rgba(255,255,255,0.04); border-radius: 4px; padding: 1px 6px;")
        left_hdr.addWidget(self._res_badge)
        left_col.addLayout(left_hdr)

        prev_card = QFrame()
        prev_card.setStyleSheet("""
            QFrame {
                background: #050811;
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 12px;
            }
        """)
        prev_lay = QVBoxLayout(prev_card)
        prev_lay.setContentsMargins(8, 8, 8, 8)

        self._preview_lbl = QLabel()
        self._preview_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview_lbl.setMinimumSize(420, 340)
        self._preview_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        prev_lay.addWidget(self._preview_lbl)
        left_col.addWidget(prev_card, 1)

        # Input source tools under viewer
        source_bar = QHBoxLayout()
        source_bar.setSpacing(8)

        def _action_btn(text: str, bg_color: str, border_color: str, hover_bg: str, svg_key: str = "", icon_color: str = "#38bdf8") -> QPushButton:
            btn = QPushButton(f"  {text}")
            btn.setFixedHeight(34)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFont(QFont(APP_FONT_NAME, 9, QFont.Weight.DemiBold))
            if svg_key:
                btn.setIcon(QIcon(_render_hub_svg(svg_key, 16, icon_color)))
                btn.setIconSize(QSize(16, 16))
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: {bg_color};
                    color: #ffffff;
                    border: 1px solid {border_color};
                    border-radius: 8px;
                    padding: 0 14px;
                    text-align: center;
                }}
                QPushButton:hover {{
                    background: {hover_bg};
                    border-color: #38bdf8;
                }}
                QPushButton:pressed {{
                    background: rgba(56, 189, 248, 0.25);
                }}
            """)
            return btn

        self._btn_refresh = _action_btn("Recapture Screen", "rgba(255, 255, 255, 0.05)", "rgba(255, 255, 255, 0.12)", "rgba(255, 255, 255, 0.15)", svg_key="vision_screen_refresh", icon_color="#94a3b8")
        self._btn_refresh.clicked.connect(self._refresh_snapshot)
        source_bar.addWidget(self._btn_refresh)

        self._btn_upload = _action_btn("Open Document / Image", "rgba(16, 185, 129, 0.18)", "rgba(16, 185, 129, 0.40)", "rgba(16, 185, 129, 0.28)", svg_key="vision_folder_open", icon_color="#34d399")
        self._btn_upload.clicked.connect(self._select_file_to_scan)
        source_bar.addWidget(self._btn_upload)

        self._btn_camera = _action_btn("Live Camera Photo", "rgba(245, 158, 11, 0.18)", "rgba(245, 158, 11, 0.40)", "rgba(245, 158, 11, 0.28)", svg_key="vision_camera_lens", icon_color="#fbbf24")
        self._btn_camera.clicked.connect(self._open_camera_capture)
        source_bar.addWidget(self._btn_camera)

        left_col.addLayout(source_bar)
        mid.addLayout(left_col, 5)

        # Right Column: Analysis Studio & Results
        right_col = QVBoxLayout()
        right_col.setSpacing(8)

        # Action pills
        acts_row = QHBoxLayout()
        acts_row.setSpacing(8)

        self._btn_ocr = _action_btn("Extract Text (AI OCR)", "rgba(99, 102, 241, 0.22)", "rgba(99, 102, 241, 0.50)", "rgba(99, 102, 241, 0.35)", svg_key="vision_ocr_scan", icon_color="#a5b4fc")
        self._btn_ocr.clicked.connect(self._run_extract_ocr)
        acts_row.addWidget(self._btn_ocr)

        self._btn_explain = _action_btn("Deep Neural Breakdown", "rgba(56, 189, 248, 0.20)", "rgba(56, 189, 248, 0.45)", "rgba(56, 189, 248, 0.32)", svg_key="vision_spark_deep", icon_color="#38bdf8")
        self._btn_explain.clicked.connect(self._run_explain_screen)
        acts_row.addWidget(self._btn_explain)

        self._btn_scan = _action_btn("Detect Code / Errors", "rgba(239, 68, 68, 0.18)", "rgba(239, 68, 68, 0.42)", "rgba(239, 68, 68, 0.30)", svg_key="vision_radar_code", icon_color="#f87171")
        self._btn_scan.clicked.connect(self._run_scan_errors)
        acts_row.addWidget(self._btn_scan)

        right_col.addLayout(acts_row)

        # Results header row
        res_hdr = QHBoxLayout()
        res_hdr_lbl = QLabel("ANALYSIS & EXTRACTED DATA")
        res_hdr_lbl.setFont(QFont(APP_FONT_NAME, 8, QFont.Weight.Bold))
        res_hdr_lbl.setStyleSheet("color: #94a3b8; background: transparent; letter-spacing: 0.5px;")
        res_hdr.addWidget(res_hdr_lbl)

        self._word_count_lbl = QLabel("0 words")
        self._word_count_lbl.setFont(QFont(APP_FONT_NAME, 7, QFont.Weight.Medium))
        self._word_count_lbl.setStyleSheet("color: #64748b; background: rgba(255,255,255,0.04); border-radius: 4px; padding: 1px 6px;")
        res_hdr.addWidget(self._word_count_lbl)
        res_hdr.addStretch()

        self._btn_save = QPushButton("💾  Save")
        self._btn_save.setFixedHeight(24)
        self._btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_save.setFont(QFont(APP_FONT_NAME, 8))
        self._btn_save.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.04);
                color: #cbd5e1;
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 5px;
                padding: 0 8px;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.1);
                color: #ffffff;
            }
        """)
        self._btn_save.clicked.connect(self._save_results)
        res_hdr.addWidget(self._btn_save)

        self._btn_copy = QPushButton("📋  Copy")
        self._btn_copy.setFixedHeight(24)
        self._btn_copy.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_copy.setFont(QFont(APP_FONT_NAME, 8))
        self._btn_copy.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.04);
                color: #cbd5e1;
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 5px;
                padding: 0 8px;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.1);
                color: #ffffff;
            }
        """)
        self._btn_copy.clicked.connect(self._copy_results)
        res_hdr.addWidget(self._btn_copy)

        right_col.addLayout(res_hdr)

        # Big Results Editor
        self._result_box = QTextEdit()
        self._result_box.setReadOnly(True)
        self._result_box.setFont(QFont("Consolas", 10))
        self._result_box.setStyleSheet("""
            QTextEdit {
                background: #050811;
                color: #f1f5f9;
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 12px;
                padding: 12px;
                line-height: 150%;
                selection-background-color: #3b82f6;
            }
        """)
        self._result_box.setPlainText("⚡ Neural Vision & OCR Studio Ready.\n\nSelect an action above ('Extract Text (AI OCR)' or 'Deep Neural Breakdown'), or capture a live camera photo to generate an executive intelligence dossier.")
        self._result_box.textChanged.connect(self._update_word_count)
        right_col.addWidget(self._result_box, 1)

        mid.addLayout(right_col, 6)
        self._lay.addLayout(mid, 1)

        # ── Footer Row ──
        ftr = QHBoxLayout()
        ftr.setSpacing(10)

        self._btn_ask = QPushButton("  Ask Charlie About This Scan")
        self._btn_ask.setIcon(QIcon(_render_hub_svg("vision_spark_deep", 16, "#ffffff")))
        self._btn_ask.setIconSize(QSize(16, 16))
        self._btn_ask.setFixedHeight(34)
        self._btn_ask.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_ask.setFont(QFont(APP_FONT_NAME, 9, QFont.Weight.DemiBold))
        self._btn_ask.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #4f46e5, stop:1 #6366f1);
                color: #ffffff;
                border: 1px solid rgba(129, 140, 248, 0.5);
                border-radius: 8px;
                padding: 0 18px;
            }
            QPushButton:hover {
                background: #4338ca;
            }
        """)
        self._btn_ask.clicked.connect(self._send_to_chat)
        ftr.addWidget(self._btn_ask)

        ftr.addStretch()

        close_ftr = QPushButton("Done")
        close_ftr.setFixedHeight(34)
        close_ftr.setCursor(Qt.CursorShape.PointingHandCursor)
        close_ftr.setFont(QFont(APP_FONT_NAME, 9))
        close_ftr.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.04);
                color: #94a3b8;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 8px;
                padding: 0 16px;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.08);
                color: #ffffff;
            }
        """)
        close_ftr.clicked.connect(self.hide)
        ftr.addWidget(close_ftr)
        self._lay.addLayout(ftr)

        self._show_placeholder_preview("Click 'Recapture Desktop' or 'Open Document / Image to Scan'")

    def _display_pixmap_preview(self, pix: QPixmap):
        if not pix or pix.isNull():
            return
        if hasattr(self, "_res_badge"):
            self._res_badge.setText(f"{pix.width()} × {pix.height()} px")
        scaled = pix.scaled(560, 400, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        self._preview_lbl.setPixmap(scaled)

    def _display_pil_preview(self, img):
        import io
        if img is None:
            return
        if hasattr(self, "_res_badge"):
            self._res_badge.setText(f"{img.width} × {img.height} px")
        img_thumb = img.copy()
        img_thumb.thumbnail((560, 400))
        buf = io.BytesIO()
        img_thumb.save(buf, format="PNG")
        pix = QPixmap()
        pix.loadFromData(buf.getvalue())
        self._preview_lbl.setPixmap(pix)

    def _show_document_badge_preview(self, filename: str, details: str, accent_color: str = "#3b82f6"):
        pix = QPixmap(560, 380)
        pix.fill(QColor("#050811"))
        p = QPainter(pix)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Border card
        p.setPen(QColor(255, 255, 255, 25))
        p.setBrush(QColor("#080d1a"))
        p.drawRoundedRect(20, 20, 520, 340, 14, 14)

        # Accent icon box
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(accent_color))
        p.drawRoundedRect(235, 65, 90, 80, 16, 16)

        # Icon text
        ext = os.path.splitext(filename)[1].upper().replace(".", "") or "DOC"
        p.setPen(QColor("#ffffff"))
        p.setFont(QFont(APP_FONT_NAME, 15, QFont.Weight.Bold))
        p.drawText(235, 65, 90, 80, Qt.AlignmentFlag.AlignCenter, ext)

        # Filename
        p.setFont(QFont(APP_FONT_NAME, 11, QFont.Weight.Bold))
        p.drawText(40, 175, 480, 30, Qt.AlignmentFlag.AlignCenter, filename)

        # Details
        p.setPen(QColor("#93c5fd"))
        p.setFont(QFont(APP_FONT_NAME, 9, QFont.Weight.DemiBold))
        p.drawText(40, 210, 480, 25, Qt.AlignmentFlag.AlignCenter, details)

        # Subtitle
        p.setPen(QColor("#64748b"))
        p.setFont(QFont(APP_FONT_NAME, 8))
        p.drawText(40, 245, 480, 25, Qt.AlignmentFlag.AlignCenter, "✓ Document content parsed & indexed • Ready for OCR/AI analysis")
        p.end()
        self._preview_lbl.setPixmap(pix)
        if hasattr(self, "_res_badge"):
            self._res_badge.setText(ext)

    def _show_placeholder_preview(self, msg: str = "Ready to scan"):
        pix = QPixmap(560, 380)
        pix.fill(QColor("#050811"))
        p = QPainter(pix)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QColor(255, 255, 255, 20))
        p.setBrush(QColor("#070c18"))
        p.drawRoundedRect(20, 20, 520, 340, 14, 14)

        p.setPen(QColor("#38bdf8"))
        p.setFont(QFont(APP_FONT_NAME, 11, QFont.Weight.Bold))
        p.drawText(40, 130, 480, 30, Qt.AlignmentFlag.AlignCenter, "DOCUMENT & VISION STUDIO")

        p.setPen(QColor("#94a3b8"))
        p.setFont(QFont(APP_FONT_NAME, 9))
        p.drawText(40, 170, 480, 30, Qt.AlignmentFlag.AlignCenter, msg)

        p.setPen(QColor("#64748b"))
        p.setFont(QFont(APP_FONT_NAME, 8))
        p.drawText(40, 210, 480, 30, Qt.AlignmentFlag.AlignCenter, "Supported formats: PDF • PNG • JPG • WEBP • TIFF • BMP • DOCX • TXT")
        p.end()
        self._preview_lbl.setPixmap(pix)

    def _update_word_count(self):
        text = self._result_box.toPlainText().strip()
        words = len(text.split()) if text else 0
        if hasattr(self, "_word_count_lbl"):
            self._word_count_lbl.setText(f"{words} words • {len(text)} chars")

    def _select_file_to_scan(self):
        from PyQt6.QtWidgets import QFileDialog
        from PIL import Image
        from pathlib import Path
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select File or Document to Scan",
            "",
            "All Supported Documents (*.pdf *.png *.jpg *.jpeg *.webp *.bmp *.tiff *.docx *.txt *.csv *.json *.md *.log);;"
            "PDF Documents (*.pdf);;"
            "Images (*.png *.jpg *.jpeg *.webp *.bmp *.tiff *.gif);;"
            "Word Documents (*.docx *.doc);;"
            "Text & Code Files (*.txt *.csv *.json *.md *.log *.py);;"
            "All Files (*.*)",
        )
        if not path:
            return

        ext = os.path.splitext(path)[1].lower()
        fname = os.path.basename(path)
        self._current_source_name = f"File: {fname}"

        try:
            # 1. Images
            if ext in (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff", ".tif", ".gif"):
                img = Image.open(path).convert("RGB")
                self._current_pil_img = img
                self._current_doc_text = ""
                self._win_bar.setText(f"📁  Loaded Image: {fname}  ({img.width}×{img.height} px)")
                self._display_pil_preview(img)
                self._result_box.setPlainText(f"✓ Loaded image '{fname}' ({img.width}×{img.height} px).\nRunning AI OCR text extraction…")
                QTimer.singleShot(100, self._run_extract_ocr)
                return

            # 2. PDF Documents
            if ext == ".pdf":
                extracted_text = ""
                page_count = 0
                preview_img = None

                # Try PyMuPDF (fitz)
                try:
                    import fitz
                    doc = fitz.open(path)
                    page_count = len(doc)
                    pages_out = []
                    for idx, page in enumerate(doc):
                        t = page.get_text()
                        if t.strip():
                            pages_out.append(f"=== Page {idx + 1} ===\n{t.strip()}")
                    extracted_text = "\n\n".join(pages_out)
                    if page_count > 0:
                        p0 = doc[0]
                        pix = p0.get_pixmap(dpi=150)
                        preview_img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                except Exception:
                    pass

                # Try pypdf
                if not extracted_text:
                    try:
                        import pypdf
                        reader = pypdf.PdfReader(path)
                        page_count = len(reader.pages)
                        pages_out = [f"=== Page {idx + 1} ===\n{p.extract_text()}" for idx, p in enumerate(reader.pages) if p.extract_text()]
                        extracted_text = "\n\n".join(pages_out)
                    except Exception:
                        pass

                # Try PyPDF2
                if not extracted_text:
                    try:
                        import PyPDF2
                        reader = PyPDF2.PdfReader(path)
                        page_count = len(reader.pages)
                        pages_out = [f"=== Page {idx + 1} ===\n{p.extract_text()}" for idx, p in enumerate(reader.pages) if p.extract_text()]
                        extracted_text = "\n\n".join(pages_out)
                    except Exception:
                        pass

                self._current_doc_text = extracted_text
                self._current_pil_img = preview_img
                self._win_bar.setText(f"📁  Loaded PDF: {fname}  ({page_count} Pages)")

                if preview_img:
                    self._display_pil_preview(preview_img)
                else:
                    self._show_document_badge_preview(fname, f"PDF Document • {page_count} Pages", "#ef4444")

                if extracted_text.strip():
                    self._result_box.setPlainText(f"✓ PDF Extracted ({page_count} pages, {len(extracted_text.split())} words):\n\n" + extracted_text)
                else:
                    self._result_box.setPlainText(f"Loaded '{fname}'. This may be an image-only scanned PDF. Click 'Extract Text (AI OCR)' to scan pages with AI Vision.")
                return

            # 3. Word Documents (.docx, .doc)
            if ext in (".docx", ".doc"):
                try:
                    import docx
                    doc = docx.Document(path)
                    extracted_text = "\n".join(p.text for p in doc.paragraphs if p.text)
                except Exception as e:
                    extracted_text = f"Could not parse docx: {e}"

                self._current_doc_text = extracted_text
                self._current_pil_img = None
                self._win_bar.setText(f"📁  Loaded Word Doc: {fname}  ({len(extracted_text.split())} words)")
                self._show_document_badge_preview(fname, f"Word Document • {len(extracted_text.split())} words", "#2563eb")
                self._result_box.setPlainText(f"✓ Word Document Extracted ({len(extracted_text.split())} words):\n\n" + extracted_text)
                return

            # 4. Text & Code files (.txt, .csv, .json, .md, .log, .py, etc.)
            try:
                extracted_text = Path(path).read_text(encoding="utf-8", errors="replace")
            except Exception as e:
                extracted_text = f"Could not read text file: {e}"

            self._current_doc_text = extracted_text
            self._current_pil_img = None
            self._win_bar.setText(f"📁  Loaded File: {fname}  ({len(extracted_text.split())} words)")
            self._show_document_badge_preview(fname, f"Text / Code File • {len(extracted_text.split())} words", "#10b981")
            self._result_box.setPlainText(extracted_text)

        except Exception as e:
            self._result_box.setPlainText(f"Failed to open document: {e}")

    def _refresh_snapshot(self):
        try:
            from PyQt6.QtGui import QGuiApplication
            from PyQt6.QtCore import QBuffer, QIODevice
            from PIL import Image
            import io
            screen = QGuiApplication.primaryScreen()
            if screen:
                pix = screen.grabWindow(0)
                if pix and not pix.isNull() and pix.width() > 100:
                    buf = QBuffer()
                    buf.open(QIODevice.OpenModeFlag.ReadWrite)
                    pix.save(buf, "PNG")
                    self._current_pil_img = Image.open(io.BytesIO(buf.data().data()))
                    self._current_doc_text = ""
                    self._current_source_name = f"Desktop Screen ({pix.width()}×{pix.height()})"
                    self._win_bar.setText(f"🖥️  Captured: {self._current_source_name}")
                    self._display_pixmap_preview(pix)
                    self._result_box.setPlainText("Desktop screen captured.\nClick 'Extract Text (AI OCR)' or 'Deep Analysis' above to analyze.")
                    return
        except Exception as e:
            print(f"[OCR] Qt screen grab note: {e}")

        try:
            from engine.vision.screen_copilot import get_screen_copilot
            copilot = get_screen_copilot()
            win = copilot.get_active_window_title()
            self._current_source_name = f"Active Window: {win}"
            img = copilot.capture_screen_pil()
            if img:
                self._current_pil_img = img
                self._current_doc_text = ""
                self._win_bar.setText(f"🖥️  Captured: {self._current_source_name}")
                self._display_pil_preview(img)
                self._result_box.setPlainText("Screen captured. Ready for OCR extraction.")
                return
        except Exception as e:
            print(f"[OCR] Copilot capture fallback error: {e}")

        self._win_bar.setText("🖥️  Screen Capture: Standby (Click 'Open Document / Image' or 'Recapture')")
        self._show_placeholder_preview("Screen capture pending.\nClick 'Recapture Desktop' or 'Open Document / Image' to begin.")

    def _run_extract_ocr(self):
        self._result_box.setPlainText("⚡ Scanning optical signatures & executing AI OCR extraction…")
        QApplication.processEvents()
        try:
            target_img = getattr(self, "_current_pil_img", None)
            if target_img is None:
                self._refresh_snapshot()
                target_img = getattr(self, "_current_pil_img", None)

            if target_img is None:
                self._result_box.setPlainText("No image or document loaded to scan. Please click 'Open Document / Image to Scan' or 'Live Camera Photo'.")
                return

            prompt = (
                "You are CHARLIE's Advanced Neural Vision & Multimodal Intelligence Engine.\n"
                "Examine the target visual capture with maximum technical rigor and professional executive depth.\n\n"
                "Format your complete response professionally using this structured template:\n\n"
                "════════════════════════════════════════════════════════════════════════════════\n"
                "◈ NEURAL VISION INTELLIGENCE DOSSIER ◈\n"
                "════════════════════════════════════════════════════════════════════════════════\n\n"
                "1. 🏷️ TARGET IDENTIFICATION & CLASSIFICATION\n"
                "   • Primary Entity       : <Exact Brand, Model Name, or Document Classification>\n"
                "   • Category & Form Factor: <Hardware Peripheral / Packaging / Consumer Electronics / Document>\n"
                "   • Optical Confidence   : High (99.2% visual signature match)\n"
                "   • Physical Attributes  : <Materials, colorway, contours, finish, condition>\n\n"
                "2. 🔍 OPTICAL CHARACTER RECOGNITION (OCR) & TELEMETRY\n"
                "   • Extracted Logotypes  : <Exact visible logos, e.g. boAt, Boult, Apple, Samsung, etc.>\n"
                "   • Visible Serials/Specs: <Model numbers, charging ratings, regulatory icons, dates>\n"
                "   • Complete Transcript  :\n"
                "     \"<Accurately transcribe all visible text, paragraphs, or tabular lines>\"\n\n"
                "3. ⚙️ TECHNICAL ARCHITECTURE & CORE USE CASES\n"
                "   • Primary Function     : <In-depth explanation of what this item is and what problem it solves>\n"
                "   • Operational Mechanics: <How it operates, wireless protocols, drivers, battery system, or workflow role>\n"
                "   • Practical Deployment : <Everyday scenarios: commuting, calls, workouts, office, study, gaming>\n\n"
                "4. 🛠️ TACTICAL OPERATING GUIDE & INSTRUCTIONS\n"
                "   • Operation Protocol   : <Step-by-step instructions: opening, pairing, charging, power states>\n"
                "   • Best Practices       : <Optimal usage advice, charging parameters, maintenance and care>\n\n"
                "5. 💡 EXECUTIVE SYNTHESIS & CHARLIE'S INSIGHTS\n"
                "   • <Crisp pro-grade analytical summary with expert recommendations>\n"
            )
            from core import gemini
            resp = gemini.call([prompt, target_img], tier=gemini.SMART, timeout_ms=30000)
            if resp and getattr(resp, "text", None):
                extracted = resp.text.strip()
            else:
                extracted = "AI Vision recognition could not return an answer. Please verify your Gemini API key in config/api_keys.json."
            self._result_box.setPlainText(extracted)
            self._current_doc_text = extracted
            if hasattr(self, "_speak_recognition_summary"):
                self._speak_recognition_summary(extracted)
        except Exception as e:
            self._result_box.setPlainText(f"OCR Extraction failed: {e}")

    def _run_explain_screen(self):
        self._result_box.setPlainText("Performing deep AI visual analysis & structured breakdown…")
        QApplication.processEvents()
        try:
            target_img = getattr(self, "_current_pil_img", None)
            if target_img is not None:
                prompt = (
                    "You are CHARLIE's Advanced Neural Vision & Deep Analytical Intelligence Engine.\n"
                    "Perform an exhaustive, high-level structured evaluation of this visual capture.\n\n"
                    "Structure your findings in the following executive format:\n\n"
                    "════════════════════════════════════════════════════════════════════════════════\n"
                    "◈ DEEP NEURAL VISUAL BREAKDOWN & COGNITIVE ANALYSIS ◈\n"
                    "════════════════════════════════════════════════════════════════════════════════\n\n"
                    "1. 🌐 EXECUTIVE OVERVIEW\n"
                    "   • Subject Matter       : <Accurate identification of object, application, screen, or document>\n"
                    "   • Context & Environment: <Hardware setup, desktop workspace, paper layout, or camera scene>\n"
                    "   • Status & State       : <Active, operational, standby, or in-use>\n\n"
                    "2. 📊 CRITICAL DATA, METRICS & KEY INFORMATION\n"
                    "   • Core Parameters      : <Highlight key dates, code snippets, monetary values, metrics, labels>\n"
                    "   • Structural Breakdown : <Logical hierarchy, UI components, clauses, or hardware elements>\n\n"
                    "3. 🧠 DEEP COGNITIVE INSIGHTS\n"
                    "   • Functional Purpose   : <Why this exists and how it fits into the user's workflow or daily routine>\n"
                    "   • Significance & Impact: <Value proposition, advantages, or technical implications>\n\n"
                    "4. ⚡ ACTIONABLE RECOMMENDATIONS & NEXT STEPS\n"
                    "   • 1. <Immediate tactical next step>\n"
                    "   • 2. <Optimization recommendation>\n"
                    "   • 3. <Maintenance, follow-up, or security advisory>\n"
                )
                from core import gemini
                resp = gemini.call([prompt, target_img], tier=gemini.SMART, timeout_ms=30000)
                if resp and getattr(resp, "text", None):
                    out_text = resp.text.strip()
                    self._result_box.setPlainText(out_text)
                    self._current_doc_text = out_text
                    if hasattr(self, "_speak_recognition_summary"):
                        self._speak_recognition_summary(out_text)
                    return

            doc_txt = getattr(self, "_current_doc_text", "").strip()
            if doc_txt:
                prompt = (
                    "Perform a comprehensive executive analysis and structured breakdown of this document content:\n"
                    "1. Document Overview: Document type, purpose, and key subjects.\n"
                    "2. Critical Information & Data: Key dates, numbers, parties, metrics, or obligations.\n"
                    "3. Key Takeaways & In-Depth Insights: Main points and significance.\n"
                    "4. Actionable Next Steps: Recommended actions or follow-ups.\n\n"
                    f"Document Content Excerpt:\n{doc_txt[:8000]}"
                )
                from core import gemini
                resp = gemini.call(prompt, tier=gemini.SMART, timeout_ms=30000)
                if resp and getattr(resp, "text", None):
                    self._result_box.setPlainText(resp.text.strip())
                    return

            self._refresh_snapshot()
            target_img = getattr(self, "_current_pil_img", None)
            if target_img is None:
                self._result_box.setPlainText("No target loaded to analyze.")
                return

            from engine.vision_ocr import describe_screen
            res = describe_screen()
            self._result_box.setPlainText(res.get("text", "No details returned."))
        except Exception as e:
            self._result_box.setPlainText(f"Visual analysis unavailable: {e}")

    def _run_scan_errors(self):
        self._result_box.setPlainText("⚡ Scanning for tracebacks, code errors, dialog warnings, and bugs…")
        QApplication.processEvents()
        try:
            doc_txt = getattr(self, "_current_doc_text", "").strip()
            if doc_txt:
                prompt = (
                    "You are CHARLIE's Advanced Autonomous Code & Structural Debugging Auditor.\n"
                    "Inspect this document content with extreme precision for syntax faults, runtime tracebacks, compiler errors, or structural defects.\n\n"
                    "════════════════════════════════════════════════════════════════════════════════\n"
                    "◈ SYSTEM DIAGNOSTIC & DEBUG RADAR ◈\n"
                    "════════════════════════════════════════════════════════════════════════════════\n\n"
                    "1. ⚠️ DEFECT IDENTIFICATION & TELEMETRY\n"
                    "   • Error Signature      : <Exact error name, exception class, or warning title>\n"
                    "   • Line & Module        : <File name, line numbers, or code block>\n"
                    "   • Severity Level       : <Critical / Warning / Advisory>\n\n"
                    "2. 🔬 ROOT CAUSE INVESTIGATION\n"
                    "   • Failure Mechanism    : <Technical explanation of why this issue triggered>\n\n"
                    "3. 🛠️ DEFINITIVE REMEDIATION & PATCH\n"
                    "   • Corrective Code/Fix  : <Exact corrected code block or step-by-step resolution>\n"
                    "   • Verification Command : <Command or test to confirm resolution>\n\n"
                    "If no errors or issues are present, state clearly: '✓ All systems nominal. No errors or defects detected.'\n\n"
                    f"Content:\n{doc_txt[:8000]}"
                )
                from core import gemini
                resp = gemini.call(prompt, tier=gemini.SMART, timeout_ms=30000)
                if resp and getattr(resp, "text", None):
                    self._result_box.setPlainText(resp.text.strip())
                    return

            target_img = getattr(self, "_current_pil_img", None)
            if target_img is not None:
                prompt = (
                    "You are CHARLIE's Advanced Autonomous Code & Structural Debugging Auditor.\n"
                    "Inspect this image with extreme precision for syntax faults, terminal errors, tracebacks, compiler failures, or UI dialog warnings.\n\n"
                    "════════════════════════════════════════════════════════════════════════════════\n"
                    "◈ SYSTEM DIAGNOSTIC & DEBUG RADAR ◈\n"
                    "════════════════════════════════════════════════════════════════════════════════\n\n"
                    "1. ⚠️ DEFECT IDENTIFICATION & TELEMETRY\n"
                    "   • Error Signature      : <Exact error name, exception class, or warning title>\n"
                    "   • Module / Context     : <Application, terminal window, or script area>\n"
                    "   • Severity Level       : <Critical / Warning / Advisory>\n\n"
                    "2. 🔬 ROOT CAUSE INVESTIGATION\n"
                    "   • Failure Mechanism    : <Technical explanation of why this issue triggered>\n\n"
                    "3. 🛠️ DEFINITIVE REMEDIATION & PATCH\n"
                    "   • Corrective Code/Fix  : <Exact corrected code block or step-by-step resolution>\n"
                    "   • Verification Command : <Command or test to confirm resolution>\n\n"
                    "If no errors or issues are present, state clearly: '✓ All systems nominal. No errors or defects detected in this scan.'"
                )
                from core import gemini
                resp = gemini.call([prompt, target_img], tier=gemini.SMART, timeout_ms=30000)
                if resp and getattr(resp, "text", None):
                    self._result_box.setPlainText(resp.text.strip())
                    return

            from engine.vision.screen_copilot import get_screen_copilot
            insight = get_screen_copilot().inspect_screen_now(force_ocr=True)
            lines = ["=== Screen Inspection Report ==="]
            lines.append(f"Window: {insight.active_window}")
            if insight.has_code_error:
                lines.append(f"\n⚠️ DETECTED ACTIVE ERRORS ({len(insight.detected_errors)}):")
                for err in insight.detected_errors:
                    lines.append(f"  • {err}")
            else:
                lines.append("\n✓ No obvious code crash or error dialog detected.")
            if insight.ocr_text_snippet:
                lines.append(f"\nVisible Text Excerpt:\n{insight.ocr_text_snippet}")
            self._result_box.setPlainText("\n".join(lines))
        except Exception as e:
            self._result_box.setPlainText(f"Error during inspection: {e}")

    def _save_results(self):
        txt = self._result_box.toPlainText().strip()
        if not txt:
            return
        from PyQt6.QtWidgets import QFileDialog
        from pathlib import Path
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Extracted OCR Text",
            "extracted_text.txt",
            "Text Files (*.txt);;Markdown Files (*.md);;All Files (*.*)",
        )
        if path:
            try:
                Path(path).write_text(txt, encoding="utf-8")
                self._btn_save.setText("✓ Saved")
                QTimer.singleShot(1500, lambda: self._btn_save.setText("💾  Save"))
            except Exception as e:
                self._result_box.append(f"\n[Save Error]: {e}")

    def _send_to_chat(self):
        txt = self._result_box.toPlainText().strip()
        source = getattr(self, "_current_source_name", "scanned target")
        if not txt or txt.startswith("Select an action") or txt.startswith("Click any action"):
            txt = f"Explain what is on my {source} right now."
        else:
            txt = f"I scanned {source}. Please analyze and help me with this:\n\n{txt}"
        self.hide()
        if callable(self._on_send_to_chat):
            self._on_send_to_chat(txt)

    def _copy_results(self):
        app = QApplication.instance()
        if app:
            cb = app.clipboard()
            if cb:
                cb.setText(self._result_box.toPlainText())
                self._btn_copy.setText("✓ Copied")
                QTimer.singleShot(1500, lambda: self._btn_copy.setText("📋  Copy"))

    def _open_camera_capture(self):
        try:
            import sys
            main_mod = sys.modules.get("main")
            if main_mod and hasattr(main_mod, "app_instance") and hasattr(main_mod.app_instance, "ui"):
                main_mod.app_instance.ui.stop_camera_stream()
        except Exception:
            pass

        modal = CameraCaptureModal(self)
        try:
            if modal.exec() == QDialog.DialogCode.Accepted and getattr(modal, "_captured_img", None):
                img = modal._captured_img
                self._current_pil_img = img
                self._current_doc_text = ""
                self._current_source_name = "Laptop Camera Photo"
                self._win_bar.setText(f"📷  Captured: Laptop Camera Photo ({img.width}×{img.height} px) — Ready for Recognition & OCR")
                self._display_pil_preview(img)
                self._result_box.setPlainText("📸 Photo captured from camera!\n\nCharlie is watching and recognizing the image…")
                QTimer.singleShot(100, self._run_camera_recognition)
        finally:
            modal._shutdown_camera()
            modal.deleteLater()

    def _run_camera_recognition(self):
        target_img = getattr(self, "_current_pil_img", None)
        if target_img is None:
            self._result_box.setPlainText("No camera photo available. Click '📷 Camera Photo' to take one.")
            return

        self._result_box.setPlainText("⚡ Optical sensor active… Charlie is analyzing telemetry, objects & OCR…")
        QApplication.processEvents()

        prompt = (
            "You are CHARLIE's Advanced Neural Vision & Multimodal Intelligence Engine.\n"
            "The user captured a real-time photo to inspect an object, product, hardware, or document.\n"
            "Deliver an executive, articulate intelligence assessment following this template:\n\n"
            "════════════════════════════════════════════════════════════════════════════════\n"
            "◈ OPTICAL RECOGNITION & TELEMETRY REPORT ◈\n"
            "════════════════════════════════════════════════════════════════════════════════\n\n"
            "1. 🏷️ TARGET IDENTIFICATION\n"
            "   • Entity Name          : <Exact Brand and Model, e.g. boAt Airdopes 141 ANC / Boult Wireless Audio>\n"
            "   • Category & Form      : <Device category, hardware type, or document nature>\n"
            "   • Visual Specifications: <Colors, finish, shape, ports, indicators, visible wear>\n\n"
            "2. 🔍 OPTICAL CHARACTER RECOGNITION (OCR)\n"
            "   • Verified Typography  : <All visible text, brand logos, model markings transcribed>\n\n"
            "3. 🎯 WHAT IS THIS & WHAT IS ITS USE\n"
            "   • Operational Utility  : <Detailed explanation of what this item is, why people use it, and its benefits>\n"
            "   • Everyday Application : <Commuting, hands-free calling, music streaming, workouts, office meetings>\n\n"
            "4. 🛠️ USAGE & INSTRUCTIONS\n"
            "   • Step-by-Step Guide   : <Clear instructions on how to use, open, pair, charge, or maintain it>\n\n"
            "5. 💡 CHARLIE'S PRO ADVICE\n"
            "   • <Smart tips, battery longevity advice, or safety notes>\n\n"
            "Ensure the tone is refined, high-tech, authoritative, and brilliantly clear."
        )

        try:
            from core import gemini
            resp = gemini.call([prompt, target_img], tier=gemini.SMART, timeout_ms=30000)
            if resp and getattr(resp, "text", None):
                full_text = resp.text.strip()
                self._result_box.setPlainText(full_text)
                self._current_doc_text = full_text
                self._speak_recognition_summary(full_text)
            else:
                self._result_box.setPlainText("AI vision could not process this camera frame. Please ensure your Gemini API key is valid in config/api_keys.json and check your internet connection.")
        except Exception as e:
            self._result_box.setPlainText(f"Camera recognition note: {e}\n\nClick 'Extract Text (AI OCR)' or 'Deep Analysis' to re-try.")

    def _speak_recognition_summary(self, full_text: str):
        try:
            lines = [ln.strip() for ln in full_text.splitlines() if ln.strip()]
            spoken = ""
            for line in lines:
                clean = line.replace("*", "").replace("#", "").strip()
                if clean.lower().startswith("1. object") or clean.lower().startswith("1. identification") or clean.lower().startswith("identification:"):
                    clean = clean.split(":", 1)[-1].strip()
                if clean and not clean.startswith("1.") and not clean.startswith("Object") and not clean.startswith("Identification"):
                    spoken = clean
                    break
            if not spoken and lines:
                spoken = lines[0].replace("*", "").replace("#", "").strip()

            if len(spoken) > 160:
                spoken = spoken[:160].rsplit(" ", 1)[0] + "."

            speech_msg = f"I see: {spoken}"

            def _worker():
                try:
                    from core.tts import create_tts_player
                    from memory.config_manager import load_api_keys
                    cfg = load_api_keys()
                    player = create_tts_player(cfg)
                    player.speak(speech_msg)
                except Exception:
                    try:
                        from core import tts
                        tts.WindowsSAPITTSEngine().speak(speech_msg)
                    except Exception:
                        pass

            threading.Thread(target=_worker, daemon=True, name="cam-speak-thread").start()
        except Exception:
            pass


class MobileBridgeOverlay(_HudOverlay):
    """Wireless LAN Mobile Companion Bridge — Connect phone browser to Charlie."""

    _OW = 640

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("""
            MobileBridgeOverlay {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #12132e, stop:0.5 #0c0e20, stop:1 #060714);
                border: 1px solid rgba(168, 85, 247, 0.45);
                border-radius: 16px;
            }
        """)
        self.setFixedWidth(self._OW)
        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(22, 18, 22, 18)
        self._lay.setSpacing(12)
        self._build_ui()
        self._start_bridge()

    def _build_ui(self):
        # Header Row
        hdr = QHBoxLayout()
        hdr.setSpacing(12)

        logo_box = QLabel()
        logo_box.setFixedSize(38, 38)
        logo_box.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo_box.setStyleSheet("""
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 rgba(168, 85, 247, 0.28), stop:1 rgba(99, 102, 241, 0.16));
            border: 1px solid rgba(168, 85, 247, 0.45);
            border-radius: 10px;
        """)
        logo_box.setPixmap(_render_hub_svg("nav_mobile", 22, "#c084fc"))
        hdr.addWidget(logo_box)

        title_v = QVBoxLayout()
        title_v.setSpacing(2)

        title_top = QHBoxLayout()
        title_top.setSpacing(8)
        t_lbl = QLabel("MOBILE COMPANION BRIDGE")
        t_lbl.setFont(QFont(APP_FONT_NAME, 11, QFont.Weight.Bold))
        t_lbl.setStyleSheet("color: #ffffff; background: transparent; letter-spacing: 0.5px;")
        title_top.addWidget(t_lbl)

        status_pill = QLabel("LAN SERVER READY")
        status_pill.setFont(QFont(APP_FONT_NAME, 7, QFont.Weight.Bold))
        status_pill.setStyleSheet("""
            background: rgba(34, 197, 94, 0.12);
            color: #4ade80;
            border: 1px solid rgba(34, 197, 94, 0.35);
            border-radius: 4px;
            padding: 1px 6px;
        """)
        title_top.addWidget(status_pill)
        title_top.addStretch()
        title_v.addLayout(title_top)

        sub_lbl = QLabel("Connect your phone browser to Charlie on your local Wi-Fi")
        sub_lbl.setFont(QFont(APP_FONT_NAME, 8))
        sub_lbl.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        title_v.addWidget(sub_lbl)

        hdr.addLayout(title_v)

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(28, 28)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.05);
                color: #94a3b8;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 14px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: rgba(239, 68, 68, 0.2);
                color: #f87171;
                border-color: rgba(239, 68, 68, 0.4);
            }
        """)
        close_btn.clicked.connect(self.hide)
        hdr.addWidget(close_btn)
        self._lay.addLayout(hdr)

        # Connection Card
        card = QFrame()
        card.setStyleSheet("""
            QFrame {
                background: rgba(255, 255, 255, 0.035);
                border: 1px solid rgba(168, 85, 247, 0.3);
                border-radius: 12px;
                padding: 8px;
            }
        """)
        c_lay = QVBoxLayout(card)
        c_lay.setContentsMargins(14, 12, 14, 12)
        c_lay.setSpacing(10)

        url_top = QHBoxLayout()
        url_lbl_tag = QLabel("PAIRING URL (PHONE BROWSER)")
        url_lbl_tag.setFont(QFont(APP_FONT_NAME, 8, QFont.Weight.Bold))
        url_lbl_tag.setStyleSheet("color: #a855f7; letter-spacing: 0.5px;")
        url_top.addWidget(url_lbl_tag)
        url_top.addStretch()

        self._port_lbl = QLabel("Port: 8765")
        self._port_lbl.setFont(QFont(APP_FONT_NAME, 8))
        self._port_lbl.setStyleSheet(f"color: {C.TEXT_DIM};")
        url_top.addWidget(self._port_lbl)
        c_lay.addLayout(url_top)

        # Big URL display
        self._url_display = QLabel("http://127.0.0.1:8765/")
        self._url_display.setFont(QFont("Consolas", 14, QFont.Weight.Bold))
        self._url_display.setStyleSheet("""
            background: #090d16;
            color: #38bdf8;
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 8px;
            padding: 10px 14px;
        """)
        self._url_display.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        c_lay.addWidget(self._url_display)

        # Buttons Row
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self._copy_btn = QPushButton("📋  Copy Pairing Link")
        self._copy_btn.setFixedHeight(34)
        self._copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._copy_btn.setFont(QFont(APP_FONT_NAME, 8, QFont.Weight.DemiBold))
        self._copy_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 rgba(168, 85, 247, 0.35), stop:1 rgba(99, 102, 241, 0.28));
                color: #ffffff;
                border: 1px solid rgba(168, 85, 247, 0.55);
                border-radius: 8px;
                padding: 0 14px;
            }
            QPushButton:hover {
                background: rgba(168, 85, 247, 0.5);
            }
        """)
        self._copy_btn.clicked.connect(self._copy_url)
        btn_row.addWidget(self._copy_btn)

        self._open_btn = QPushButton("🌐  Open in Browser")
        self._open_btn.setFixedHeight(34)
        self._open_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._open_btn.setFont(QFont(APP_FONT_NAME, 8, QFont.Weight.DemiBold))
        self._open_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.05);
                color: #e2e8f0;
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 8px;
                padding: 0 14px;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.1);
                color: #ffffff;
            }
        """)
        self._open_btn.clicked.connect(self._open_in_browser)
        btn_row.addWidget(self._open_btn)

        btn_row.addStretch()
        c_lay.addLayout(btn_row)
        self._lay.addWidget(card)

        # Instructions / Feature list
        guide_card = QFrame()
        guide_card.setStyleSheet("""
            QFrame {
                background: rgba(255, 255, 255, 0.02);
                border: 1px solid rgba(255, 255, 255, 0.06);
                border-radius: 10px;
                padding: 8px;
            }
        """)
        g_lay = QVBoxLayout(guide_card)
        g_lay.setContentsMargins(12, 10, 12, 10)
        g_lay.setSpacing(6)

        g_title = QLabel("HOW TO CONNECT FROM YOUR PHONE:")
        g_title.setFont(QFont(APP_FONT_NAME, 8, QFont.Weight.Bold))
        g_title.setStyleSheet("color: #94a3b8;")
        g_lay.addWidget(g_title)

        s1 = QLabel("1. Make sure your phone and this PC are on the same Wi-Fi network.")
        s1.setFont(QFont(APP_FONT_NAME, 8))
        s1.setStyleSheet("color: #cbd5e1;")
        g_lay.addWidget(s1)

        s2 = QLabel("2. Open Chrome, Safari, or Brave on your phone and type the URL above.")
        s2.setFont(QFont(APP_FONT_NAME, 8))
        s2.setStyleSheet("color: #cbd5e1;")
        g_lay.addWidget(s2)

        s3 = QLabel("3. Enjoy remote chat, real-time PC telemetry, and desktop screen mirror.")
        s3.setFont(QFont(APP_FONT_NAME, 8))
        s3.setStyleSheet("color: #cbd5e1;")
        g_lay.addWidget(s3)

        self._lay.addWidget(guide_card)

        # Footer
        ftr = QHBoxLayout()
        ftr.addStretch()
        done_btn = QPushButton("Done")
        done_btn.setFixedHeight(32)
        done_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        done_btn.setFont(QFont(APP_FONT_NAME, 8))
        done_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.04);
                color: #94a3b8;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 6px;
                padding: 0 16px;
            }
            QPushButton:hover {
                color: #ffffff;
                background: rgba(255, 255, 255, 0.08);
            }
        """)
        done_btn.clicked.connect(self.hide)
        ftr.addWidget(done_btn)
        self._lay.addLayout(ftr)

    def _start_bridge(self):
        try:
            from engine.bridge.mobile_companion import get_mobile_bridge
            bridge = get_mobile_bridge()
            bridge.start()
            url = bridge.get_pairing_url()
            self._url_display.setText(url)
            self._current_url = url
        except Exception as e:
            self._url_display.setText(f"Bridge error: {e}")
            self._current_url = "http://127.0.0.1:8765/"

    def _copy_url(self):
        app = QApplication.instance()
        if app:
            cb = app.clipboard()
            if cb:
                cb.setText(getattr(self, "_current_url", "http://127.0.0.1:8765/"))
                self._copy_btn.setText("✓ Link Copied!")
                QTimer.singleShot(1500, lambda: self._copy_btn.setText("📋  Copy Pairing Link"))

    def _open_in_browser(self):
        url = getattr(self, "_current_url", "http://127.0.0.1:8765/")
        QDesktopServices.openUrl(QUrl(url))


class ThemeStudioOverlay(_HudOverlay):
    """Professional UI Theme, Accent & Logo Contrast Studio."""

    theme_changed = pyqtSignal(str, str)
    custom_wheel_requested = pyqtSignal()

    _OW = 640
    _OH = 630

    def __init__(self, current_theme: str = "glass", current_color: str = "#6366f1", parent=None):
        super().__init__(parent)
        self.setObjectName("ThemeStudioOverlay")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedSize(self._OW, self._OH)

        self._active_theme = normalize_ui_theme(current_theme)
        self._active_color = str(current_color or DEFAULT_UI_COLOR).lower()
        self._theme_buttons: dict[str, QPushButton] = {}
        self._swatch_buttons: dict[str, QPushButton] = {}

        self._build_ui()

    def _build_ui(self):
        self.setStyleSheet("""
            QWidget#ThemeStudioOverlay {
                background: #090e18;
                border: 1px solid rgba(99, 102, 241, 0.45);
                border-radius: 18px;
            }
        """)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(11)

        # ── Header ──
        hdr = QHBoxLayout()
        hdr_info = QVBoxLayout()
        hdr_info.setSpacing(2)

        eyebrow = QLabel("APPEARANCE & CONTRAST STUDIO")
        eyebrow.setFont(QFont(APP_FONT_NAME, 8, QFont.Weight.Bold))
        eyebrow.setStyleSheet("color: #6366f1; background: transparent; letter-spacing: 1.2px;")
        hdr_info.addWidget(eyebrow)

        title = QLabel("UI Theme & Logo Customizer")
        title.setFont(QFont(APP_FONT_NAME, 13, QFont.Weight.ExtraBold))
        title.setStyleSheet("color: #ffffff; background: transparent;")
        hdr_info.addWidget(title)

        hdr.addLayout(hdr_info, 1)

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(28, 28)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet("""
            QPushButton {
                color: #94a3b8; background: rgba(255, 255, 255, 0.06);
                border: 1px solid rgba(255, 255, 255, 0.12); border-radius: 14px;
                font-weight: bold; font-size: 12px;
            }
            QPushButton:hover {
                color: #ffffff; background: #ef4444; border-color: #ef4444;
            }
        """)
        close_btn.clicked.connect(self.hide)
        hdr.addWidget(close_btn)
        lay.addLayout(hdr)

        # ── Live Contrast Preview Card ──
        self._preview_frame = QFrame()
        self._preview_frame.setObjectName("ThemePreviewFrame")
        pf_lay = QHBoxLayout(self._preview_frame)
        pf_lay.setContentsMargins(16, 12, 16, 12)
        pf_lay.setSpacing(14)

        # Logo badge
        self._pv_logo = QLabel()
        self._pv_logo.setFixedSize(46, 46)
        self._pv_logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._pv_logo.setStyleSheet("background: transparent; border: none;")
        pf_lay.addWidget(self._pv_logo)

        # Middle info
        pv_mid = QVBoxLayout()
        pv_mid.setSpacing(2)
        self._pv_title = QLabel("CHARLIE AI COMPANION")
        self._pv_title.setFont(QFont(APP_FONT_NAME, 10, QFont.Weight.Bold))
        pv_mid.addWidget(self._pv_title)

        pv_sub_row = QHBoxLayout()
        pv_sub_row.setSpacing(6)
        self._pv_theme_tag = QLabel("Active: Cyber Indigo")
        self._pv_theme_tag.setFont(QFont(APP_FONT_NAME, 8, QFont.Weight.Medium))
        pv_sub_row.addWidget(self._pv_theme_tag)

        self._pv_contrast_badge = QLabel("AAA High Contrast")
        self._pv_contrast_badge.setFont(QFont(APP_FONT_NAME, 7, QFont.Weight.Bold))
        self._pv_contrast_badge.setStyleSheet("""
            color: #34d399; background: rgba(16, 185, 129, 0.15);
            border: 1px solid rgba(16, 185, 129, 0.4); border-radius: 4px;
            padding: 1px 6px;
        """)
        pv_sub_row.addWidget(self._pv_contrast_badge)
        pv_sub_row.addStretch()
        pv_mid.addLayout(pv_sub_row)

        self._pv_desc = QLabel("Crisp typography, balanced dark luminosity, and vivid branding.")
        self._pv_desc.setFont(QFont(APP_FONT_NAME, 7))
        pv_mid.addWidget(self._pv_desc)
        pf_lay.addLayout(pv_mid, 1)

        # Sample UI Button
        self._pv_sample_btn = QPushButton("Active Accent")
        self._pv_sample_btn.setFixedHeight(30)
        self._pv_sample_btn.setFont(QFont(APP_FONT_NAME, 8, QFont.Weight.Bold))
        pf_lay.addWidget(self._pv_sample_btn)

        lay.addWidget(self._preview_frame)

        # ── Section 1: Themes Grid ──
        th_lbl = QLabel("CURATED HIGH-CONTRAST PALETTES")
        th_lbl.setFont(QFont(APP_FONT_NAME, 8, QFont.Weight.Bold))
        th_lbl.setStyleSheet("color: #94a3b8; letter-spacing: 0.8px; background: transparent;")
        lay.addWidget(th_lbl)

        grid_w = QWidget()
        grid_w.setStyleSheet("background: transparent;")
        grid_lay = QGridLayout(grid_w)
        grid_lay.setContentsMargins(0, 0, 0, 0)
        grid_lay.setSpacing(8)

        themes_list = [
            ("glass", "Cyber Indigo", "#080c14", "#0f172a", "#6366f1"),
            ("electric_cyan", "Electric Cyan", "#060d15", "#0a1626", "#00e5ff"),
            ("graphite", "Obsidian Gold", "#09090b", "#141416", "#f59e0b"),
            ("emerald_matrix", "Emerald Matrix", "#05120c", "#0a1e14", "#10b981"),
            ("crimson_void", "Crimson Void", "#12070a", "#1d0d12", "#f43f5e"),
            ("amethyst", "Amethyst Dream", "#0d0a1a", "#15102a", "#8b5cf6"),
            ("midnight", "Arctic Midnight", "#08101e", "#0e1b2f", "#38bdf8"),
            ("amoled", "AMOLED Pure", "#000000", "#09090b", "#a855f7"),
        ]

        for idx, (t_key, t_name, bg_c, p_c, pri_c) in enumerate(themes_list):
            row = idx // 2
            col = idx % 2
            card = self._build_theme_card(t_key, t_name, bg_c, p_c, pri_c)
            grid_lay.addWidget(card, row, col)

        lay.addWidget(grid_w)

        # ── Section 2: Accent Tuning ──
        lay.addSpacing(2)
        acc_hdr = QHBoxLayout()
        acc_lbl = QLabel("ACCENT COLOR HARMONY")
        acc_lbl.setFont(QFont(APP_FONT_NAME, 8, QFont.Weight.Bold))
        acc_lbl.setStyleSheet("color: #94a3b8; letter-spacing: 0.8px; background: transparent;")
        acc_hdr.addWidget(acc_lbl)
        acc_hdr.addStretch()

        custom_btn = QPushButton("🎨 Custom Color Wheel...")
        custom_btn.setFont(QFont(APP_FONT_NAME, 7, QFont.Weight.DemiBold))
        custom_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        custom_btn.setStyleSheet("""
            QPushButton {
                color: #a5b4fc; background: rgba(99, 102, 241, 0.12);
                border: 1px solid rgba(99, 102, 241, 0.35); border-radius: 6px;
                padding: 3px 8px;
            }
            QPushButton:hover {
                color: #ffffff; background: rgba(99, 102, 241, 0.25); border-color: #818cf8;
            }
        """)
        custom_btn.clicked.connect(self._on_custom_wheel_clicked)
        acc_hdr.addWidget(custom_btn)
        lay.addLayout(acc_hdr)

        swatch_row = QHBoxLayout()
        swatch_row.setSpacing(10)
        for name, col_hex in UI_ACCENTS.items():
            btn = QPushButton()
            btn.setFixedSize(32, 32)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setToolTip(f"{name} ({col_hex})")
            btn.clicked.connect(lambda _, c=col_hex: self._select_accent(c))
            self._swatch_buttons[col_hex.lower()] = btn
            swatch_row.addWidget(btn)
        swatch_row.addStretch()
        lay.addLayout(swatch_row)

        # ── Footer Actions ──
        lay.addSpacing(4)
        ft_row = QHBoxLayout()
        reset_btn = QPushButton("Reset to Default")
        reset_btn.setFixedHeight(32)
        reset_btn.setFont(QFont(APP_FONT_NAME, 8))
        reset_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        reset_btn.setStyleSheet("""
            QPushButton {
                color: #94a3b8; background: transparent;
                border: 1px solid rgba(255, 255, 255, 0.12); border-radius: 8px;
                padding: 0 14px;
            }
            QPushButton:hover {
                color: #ffffff; border-color: rgba(255, 255, 255, 0.3); background: rgba(255, 255, 255, 0.05);
            }
        """)
        reset_btn.clicked.connect(lambda: self._select_theme("glass", "#6366f1"))
        ft_row.addWidget(reset_btn)

        ft_row.addStretch()

        done_btn = QPushButton("Done")
        done_btn.setFixedHeight(32)
        done_btn.setFont(QFont(APP_FONT_NAME, 9, QFont.Weight.Bold))
        done_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        done_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #4f46e5, stop:1 #6366f1);
                color: #ffffff; border: 1px solid rgba(255, 255, 255, 0.2);
                border-radius: 8px; padding: 0 20px;
            }
            QPushButton:hover {
                background: #6366f1; border-color: #ffffff;
            }
        """)
        done_btn.clicked.connect(self.hide)
        ft_row.addWidget(done_btn)
        lay.addLayout(ft_row)

        self._refresh_styles()

    def _build_theme_card(self, key: str, name: str, bg_c: str, p_c: str, pri_c: str) -> QPushButton:
        btn = QPushButton()
        btn.setFixedHeight(48)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(lambda _, k=key: self._select_theme(k))

        b_lay = QHBoxLayout(btn)
        b_lay.setContentsMargins(12, 6, 12, 6)
        b_lay.setSpacing(10)

        # Swatch dots (3 dots)
        dots_w = QWidget()
        dots_w.setFixedSize(36, 18)
        dots_w.setStyleSheet("background: transparent;")
        d_lay = QHBoxLayout(dots_w)
        d_lay.setContentsMargins(0, 0, 0, 0)
        d_lay.setSpacing(3)
        for c in (bg_c, p_c, pri_c):
            dot = QLabel()
            dot.setFixedSize(9, 9)
            dot.setStyleSheet(f"background: {c}; border-radius: 4px; border: 1px solid rgba(255,255,255,0.2);")
            d_lay.addWidget(dot)
        b_lay.addWidget(dots_w)

        # Label
        t_lbl = QLabel(name)
        t_lbl.setFont(QFont(APP_FONT_NAME, 9, QFont.Weight.DemiBold))
        t_lbl.setStyleSheet("color: #f1f5f9; background: transparent;")
        b_lay.addWidget(t_lbl, 1)

        # Check badge
        chk = QLabel("✓")
        chk.setObjectName(f"chk_{key}")
        chk.setFont(QFont(APP_FONT_NAME, 9, QFont.Weight.Bold))
        chk.setStyleSheet("color: #38bdf8; background: transparent;")
        chk.setVisible(key == self._active_theme)
        b_lay.addWidget(chk)

        self._theme_buttons[key] = btn
        return btn

    def _select_theme(self, theme_key: str, accent_hex: str = ""):
        self._active_theme = normalize_ui_theme(theme_key)
        if accent_hex:
            self._active_color = accent_hex.lower()
        else:
            th_data = UI_THEMES.get(self._active_theme, {})
            self._active_color = str(th_data.get("PRI", self._active_color)).lower()

        self._refresh_styles()
        self.theme_changed.emit(self._active_theme, self._active_color)

    def _select_accent(self, color_hex: str):
        self._active_color = str(color_hex).lower()
        self._refresh_styles()
        self.theme_changed.emit(self._active_theme, self._active_color)

    def _on_custom_wheel_clicked(self):
        self.custom_wheel_requested.emit()
        self.hide()

    def _refresh_styles(self):
        pri = self._active_color
        th_data = UI_THEMES.get(self._active_theme, UI_THEMES["glass"])
        bg = th_data.get("BG", "#080c14")
        panel = th_data.get("PANEL", "#0f172a")
        panel2 = th_data.get("PANEL2", "#15203b")
        text = th_data.get("TEXT", "#ffffff")
        text_dim = th_data.get("TEXT_DIM", "#94a3b8")

        # Update preview frame
        self._preview_frame.setStyleSheet(f"""
            QFrame#ThemePreviewFrame {{
                background: {panel2};
                border: 1px solid {pri};
                border-radius: 14px;
            }}
        """)
        self._pv_logo.setPixmap(_render_hub_svg("brand_c", 44, "#ffffff"))
        self._pv_title.setStyleSheet(f"color: {text}; background: transparent; letter-spacing: 0.5px;")
        t_label_display = UI_THEME_LABELS.get(self._active_theme, self._active_theme.title())
        self._pv_theme_tag.setText(f"Active Theme: {t_label_display}")
        self._pv_theme_tag.setStyleSheet(f"color: {pri}; background: transparent;")
        self._pv_desc.setStyleSheet(f"color: {text_dim}; background: transparent;")
        self._pv_sample_btn.setStyleSheet(f"""
            QPushButton {{
                background: {pri}; color: #ffffff;
                border: 1px solid rgba(255, 255, 255, 0.3); border-radius: 8px;
                padding: 0 14px; font-weight: bold;
            }}
            QPushButton:hover {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #ffffff, stop:1 {pri});
                color: #000000;
            }}
        """)

        # Update theme cards
        for k, btn in self._theme_buttons.items():
            is_active = (k == self._active_theme)
            chk = btn.findChild(QLabel, f"chk_{k}")
            if chk:
                chk.setVisible(is_active)
            if is_active:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background: rgba(99, 102, 241, 0.16);
                        border: 1.5px solid {pri}; border-radius: 10px;
                    }}
                """)
            else:
                btn.setStyleSheet("""
                    QPushButton {
                        background: rgba(255, 255, 255, 0.035);
                        border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 10px;
                    }
                    QPushButton:hover {
                        background: rgba(255, 255, 255, 0.07);
                        border-color: rgba(255, 255, 255, 0.2);
                    }
                """)

        # Update accent swatches
        for hex_code, btn in self._swatch_buttons.items():
            is_cur = (hex_code == self._active_color)
            if is_cur:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background: {hex_code}; border-radius: 16px;
                        border: 3px solid #ffffff;
                    }}
                """)
            else:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background: {hex_code}; border-radius: 16px;
                        border: 1px solid rgba(255, 255, 255, 0.25);
                    }}
                    QPushButton:hover {{
                        border: 2px solid rgba(255, 255, 255, 0.8);
                    }}
                """)


class AppInfoOverlay(_HudOverlay):
    """Polished About and Developer information panels."""

    _OW = 560

    def __init__(self, panel: str, parent=None):
        super().__init__(parent)
        is_developer = panel == "developer"
        self.setObjectName("AppInfoOverlay")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            QWidget#AppInfoOverlay {{
                background: {C.PANEL}; border: 1px solid {C.BORDER};
                border-radius: 14px;
            }}
            QFrame#InfoCard {{
                background: {C.PANEL2}; border: 1px solid {C.BORDER};
                border-radius: 10px;
            }}
        """)
        self.setFixedWidth(self._OW)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(26, 22, 26, 22)
        lay.setSpacing(12)

        eyebrow = QLabel("CREATOR & PRODUCT" if is_developer else "PRODUCT INFORMATION")
        eyebrow.setFont(QFont(APP_FONT_NAME, 8, QFont.Weight.DemiBold))
        eyebrow.setStyleSheet(f"color: {C.PRI}; background: transparent; letter-spacing: 1px;")
        lay.addWidget(eyebrow)

        title = QLabel("Developer Details" if is_developer else "About CHARLIE")
        title.setFont(QFont(APP_FONT_NAME, 21, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {C.WHITE}; background: transparent;")
        lay.addWidget(title)

        summary = QLabel(
            DEVELOPER_CREDIT if is_developer else
            "CHARLIE is a personal desktop AI assistant for natural voice and text chat, "
            "computer tasks, files, planning, memory, learning, meetings and everyday help.")
        summary.setWordWrap(True)
        summary.setFont(QFont(APP_FONT_NAME, 10))
        summary.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent;")
        lay.addWidget(summary)

        card = QFrame()
        card.setObjectName("InfoCard")
        card_lay = QVBoxLayout(card)
        card_lay.setContentsMargins(16, 13, 16, 13)
        card_lay.setSpacing(9)
        rows = (
            (("Creator", DEVELOPER_NAME),
             ("Role", "Developer and product designer"),
             ("Product", f"CHARLIE — {APP_VERSION}"),
             ("Year", str(APP_RELEASE_YEAR)))
            if is_developer else
            (("Product", f"CHARLIE — {APP_VERSION}"),
             ("Version", f"{RELEASE_VERSION} (Build {BUILD_NUMBER})"),
             ("Edition", f"{APP_RELEASE_YEAR} Edition"),
             ("Developer", f"{DEVELOPER_NAME} — built and designed in {APP_RELEASE_YEAR}"),
             ("Privacy", "Profile and memory data stay on this device"))
        )
        for key, value in rows:
            row = QHBoxLayout()
            key_label = QLabel(key)
            key_label.setFixedWidth(92)
            key_label.setFont(QFont(APP_FONT_NAME, 9, QFont.Weight.DemiBold))
            key_label.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent; border: none;")
            value_label = QLabel(value)
            value_label.setWordWrap(True)
            value_label.setFont(QFont(APP_FONT_NAME, 9))
            value_label.setStyleSheet(f"color: {C.TEXT}; background: transparent; border: none;")
            row.addWidget(key_label)
            row.addWidget(value_label, 1)
            card_lay.addLayout(row)
        lay.addWidget(card)

        if not is_developer:
            note = QLabel(
                "Use Voice for natural conversation or AI Chat for detailed answers, coding, "
                "research and file-based work. Features depend on the active subscription plan.")
            note.setWordWrap(True)
            note.setFont(QFont(APP_FONT_NAME, 9))
            note.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
            lay.addWidget(note)

        def _open_legal_doc(filename: str, fallback_url: str):
            try:
                local_p = Path(__file__).resolve().parent / "landing_page" / filename
                if local_p.exists():
                    QDesktopServices.openUrl(QUrl.fromLocalFile(str(local_p)))
                else:
                    QDesktopServices.openUrl(QUrl(fallback_url))
            except Exception:
                pass

        legal_row = QHBoxLayout()
        legal_row.setSpacing(10)

        btn_priv = QPushButton("Privacy Policy")
        btn_priv.setFixedHeight(30)
        btn_priv.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_priv.setFont(QFont(APP_FONT_NAME, 8, QFont.Weight.Medium))
        btn_priv.setStyleSheet(f"""
            QPushButton {{ background: {C.PANEL2}; color: {C.TEXT_MED}; border: 1px solid {C.BORDER}; border-radius: 6px; padding: 2px 10px; }}
            QPushButton:hover {{ color: {C.PRI}; border-color: {C.PRI_DIM}; background: {C.PANEL}; }}
        """)
        btn_priv.clicked.connect(lambda: _open_legal_doc("privacy.html", "https://charlie.ai/privacy.html"))
        legal_row.addWidget(btn_priv)

        btn_terms = QPushButton("Terms & Conditions")
        btn_terms.setFixedHeight(30)
        btn_terms.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_terms.setFont(QFont(APP_FONT_NAME, 8, QFont.Weight.Medium))
        btn_terms.setStyleSheet(f"""
            QPushButton {{ background: {C.PANEL2}; color: {C.TEXT_MED}; border: 1px solid {C.BORDER}; border-radius: 6px; padding: 2px 10px; }}
            QPushButton:hover {{ color: {C.PRI}; border-color: {C.PRI_DIM}; background: {C.PANEL}; }}
        """)
        btn_terms.clicked.connect(lambda: _open_legal_doc("terms.html", "https://charlie.ai/terms.html"))
        legal_row.addWidget(btn_terms)

        lay.addLayout(legal_row)

        close = QPushButton("Close")
        close.setFixedHeight(36)
        close.setCursor(Qt.CursorShape.PointingHandCursor)
        close.setStyleSheet(f"""
            QPushButton {{ background: {C.PANEL2}; color: {C.TEXT};
                border: 1px solid {C.BORDER}; border-radius: 8px; }}
            QPushButton:hover {{ color: {C.WHITE}; border-color: {C.PRI_DIM}; }}
        """)
        close.clicked.connect(self.hide)
        lay.addWidget(close)


class ProfileOverlay(_HudOverlay):
    """Editable, profile-scoped account details stored locally."""

    saved = pyqtSignal(dict)
    _OW = 580
    _FIELDS = (
        ("name", "Full name", "Your name"),
        ("email", "Email / Gmail", "name@gmail.com"),
        ("phone", "Phone", "+91 ..."),
        ("date_of_birth", "Date of birth", "DD / MM / YYYY"),
        ("pronouns", "Pronouns", "Optional"),
        ("occupation", "Occupation", "What you do"),
        ("location", "City and country", "Your location"),
        ("language", "Preferred language", "English, Hindi, Hinglish..."),
        ("timezone", "Time zone", "Asia/Kolkata"),
        ("notes", "About you", "Interests or useful preferences"),
    )

    def __init__(self, parent=None):
        super().__init__(parent)
        from memory.profile_manager import active_profile
        profile = active_profile()
        self._fields: dict[str, QLineEdit] = {}
        self.setObjectName("ProfileOverlay")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            QWidget#ProfileOverlay {{
                background: {C.PANEL}; border: 1px solid {C.BORDER};
                border-radius: 14px;
            }}
            QLineEdit {{
                background: {C.BG}; color: {C.TEXT_PRIMARY}; border: 1px solid {C.BORDER};
                border-radius: 8px; padding: 7px 10px;
                font-family: 'Inter', 'Segoe UI', sans-serif;
            }}
            QLineEdit:focus {{ border-color: {C.PRI}; }}
        """)
        self.setFixedWidth(self._OW)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(26, 22, 26, 22)
        lay.setSpacing(9)
        eyebrow = QLabel("LOCAL USER PROFILE")
        eyebrow.setFont(QFont(APP_FONT_NAME, 8, QFont.Weight.DemiBold))
        eyebrow.setStyleSheet(f"color: {C.PRI}; background: transparent; letter-spacing: 1px;")
        lay.addWidget(eyebrow)
        title = QLabel("My Profile")
        title.setFont(QFont(APP_FONT_NAME, 21, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {C.WHITE}; background: transparent;")
        lay.addWidget(title)
        privacy = QLabel("Personal details are saved locally for this family profile.")
        privacy.setFont(QFont(APP_FONT_NAME, 9))
        privacy.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        lay.addWidget(privacy)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFixedHeight(390)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        form = QWidget()
        form_lay = QVBoxLayout(form)
        form_lay.setContentsMargins(0, 4, 8, 4)
        form_lay.setSpacing(7)
        for key, label, placeholder in self._FIELDS:
            caption = QLabel(label)
            caption.setFont(QFont(APP_FONT_NAME, 8, QFont.Weight.DemiBold))
            caption.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent;")
            field = QLineEdit(str(profile.get(key) or ""))
            field.setPlaceholderText(placeholder)
            field.setFixedHeight(34)
            field.setMaxLength(500 if key == "notes" else 254)
            form_lay.addWidget(caption)
            form_lay.addWidget(field)
            self._fields[key] = field
        form_lay.addStretch()
        scroll.setWidget(form)
        lay.addWidget(scroll)

        self._status = QLabel("")
        self._status.setFont(QFont(APP_FONT_NAME, 8))
        self._status.setStyleSheet(f"color: {C.RED}; background: transparent;")
        lay.addWidget(self._status)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        save = QPushButton("Save profile")
        save.setObjectName("SaveProfile")
        save.setFixedHeight(36)
        save.setCursor(Qt.CursorShape.PointingHandCursor)
        save.setStyleSheet(f"""
            QPushButton {{ background: {C.PRI}; color: #ffffff;
                border: 1px solid {C.PRI}; border-radius: 8px; font-weight: 600;
                font-family: 'Inter', 'Segoe UI', sans-serif; }}
            QPushButton:hover {{ background: #4f46e5; border-color: {C.PRI}; }}
        """)
        save.clicked.connect(self._save)
        actions.addWidget(save, 1)
        close = QPushButton("Cancel")
        close.setFixedHeight(36)
        close.setCursor(Qt.CursorShape.PointingHandCursor)
        close.setStyleSheet(f"""
            QPushButton {{ background: {C.PANEL2}; color: {C.TEXT_PRIMARY};
                border: 1px solid {C.BORDER}; border-radius: 8px; font-weight: 500;
                font-family: 'Inter', 'Segoe UI', sans-serif; }}
            QPushButton:hover {{ color: #ffffff; background: rgba(99, 102, 241, 0.15); border-color: {C.PRI}; }}
        """)
        close.clicked.connect(self.hide)
        actions.addWidget(close, 1)
        lay.addLayout(actions)

    def _save(self) -> None:
        from memory.profile_manager import update_active_profile
        try:
            record = update_active_profile(
                {key: field.text() for key, field in self._fields.items()})
        except ValueError as exc:
            self._status.setText(str(exc))
            return
        self.saved.emit(record)
        self.hide()


class ClipboardPanel(QWidget):
    """Floating panel shown when text/file is copied — smart context-aware actions."""

    action_requested = pyqtSignal(str)
    _W, _H = 370, 118

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            ClipboardPanel {{
                background: rgba(15, 15, 20, 0.96);
                border: 1px solid {C.PRI_DIM};
                border-radius: 8px;
            }}
        """)
        self.setFixedWidth(self._W)
        self._clip_text = ""
        self._context_info = {}

        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(6)

        hdr = QHBoxLayout(); hdr.setSpacing(6)
        self._title_lbl = QLabel("◈  SMART CONTEXT DETECTED")
        self._title_lbl.setFont(QFont(APP_FONT_NAME, 7, QFont.Weight.Bold))
        self._title_lbl.setStyleSheet(f"color: {C.PRI}; background: transparent; letter-spacing: 1px;")
        hdr.addWidget(self._title_lbl); hdr.addStretch()

        self._meta_lbl = QLabel("")
        self._meta_lbl.setFont(QFont(APP_FONT_NAME, 7))
        self._meta_lbl.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        hdr.addWidget(self._meta_lbl)

        x_btn = QPushButton("✕")
        x_btn.setFixedSize(16, 16)
        x_btn.setFont(QFont(APP_FONT_NAME, 8))
        x_btn.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent; border: none;")
        x_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        x_btn.clicked.connect(self.hide)
        hdr.addWidget(x_btn)
        lay.addLayout(hdr)

        self._preview = QLabel()
        self._preview.setFont(QFont(APP_FONT_NAME, 8))
        self._preview.setStyleSheet(f"""
            color: {C.TEXT}; background: {C.PANEL2};
            border: 1px solid {C.BORDER}; border-radius: 4px; padding: 4px 8px;
        """)
        self._preview.setWordWrap(False)
        self._preview.setFixedHeight(28)
        lay.addWidget(self._preview)

        self._btn_row = QHBoxLayout(); self._btn_row.setSpacing(4)
        lay.addLayout(self._btn_row)

        self._dismiss_timer = QTimer(self)
        self._dismiss_timer.setSingleShot(True)
        self._dismiss_timer.timeout.connect(self.hide)
        self.hide()

    def _clear_buttons(self):
        while self._btn_row.count():
            item = self._btn_row.takeAt(0)
            if item is not None and item.widget():
                w = item.widget()
                if w is not None:
                    w.deleteLater()

    def _trigger(self, cmd_fmt: str):
        if self._clip_text:
            text_param = self._clip_text[:1200]
            if "{text}" in cmd_fmt:
                cmd = cmd_fmt.format(text=text_param)
            else:
                cmd = cmd_fmt
            self.action_requested.emit(cmd)
        self.hide()

    def show_clipboard(self, text: str):
        self._clip_text = text
        from actions.file_processor import inspect_clipboard_item
        try:
            info = inspect_clipboard_item(text)
        except Exception:
            info = {"is_file": False, "type": "text", "actions": [("SUMMARIZE", "Summarize this: {text}")]}
        self._context_info = info

        # Header metadata
        if info.get("is_file"):
            fname = info.get("filename", "")
            ftype = str(info.get("type") or "FILE").upper()
            self._title_lbl.setText(f"◈  FILE CONTEXT: {ftype}")
            self._title_lbl.setStyleSheet(f"color: {C.ACC}; background: transparent; letter-spacing: 1px;")
            self._preview.setText(f"📄  {fname}")
            self._meta_lbl.setText("LOCAL FILE")
        else:
            ctype = str(info.get("type") or "text").upper()
            self._title_lbl.setText(f"◈  CLIPBOARD: {ctype}")
            self._title_lbl.setStyleSheet(f"color: {C.PRI}; background: transparent; letter-spacing: 1px;")
            preview = text[:55].replace('\n', ' ')
            if len(text) > 55:
                preview += "…"
            self._preview.setText(f'"{preview}"')
            self._meta_lbl.setText(f"{len(text)} chars")

        # Dynamic action buttons
        self._clear_buttons()
        _bs = (f"QPushButton {{ background: {C.PANEL2}; color: {C.TEXT_MED}; "
               f"border: 1px solid {C.BORDER}; border-radius: 4px; padding: 0 6px; }}"
               f"QPushButton:hover {{ color: {C.WHITE}; background: {C.PANEL}; border-color: {C.PRI}; }}")
        actions = info.get("actions", [])
        if isinstance(actions, list):
            for act_item in actions[:4]:
                if isinstance(act_item, (list, tuple)) and len(act_item) >= 2:
                    label, cmd = str(act_item[0]), str(act_item[1])
                    b = QPushButton(label)
                    b.setFixedHeight(24)
                    b.setFont(QFont(APP_FONT_NAME, 7, QFont.Weight.Bold))
                    b.setCursor(Qt.CursorShape.PointingHandCursor)
                    b.setStyleSheet(_bs)
                    b.clicked.connect(lambda _, c=cmd: self._trigger(c))
                    self._btn_row.addWidget(b)

        self.show(); self.raise_()
        self._dismiss_timer.start(9000)



class PluginSettingsOverlay(QWidget):
    """Floating overlay — renders per-plugin settings forms.

    Fully generic: it iterates the settings schemas a plugin declared via its
    PLUGIN_SETTINGS constant (delivered by PluginRegistry.settings_schemas) and
    builds a form for each. It knows NOTHING about any specific plugin, so the
    core stays clean and plugins remain pure drop-in — install a plugin that
    declares fields (e.g. the 3D-printer suite) and its section appears here;
    install none and this panel simply says there's nothing to configure.
    """

    _test_done = pyqtSignal(str, bool, str)   # namespace, ok, message
    _OW = 560

    def __init__(self, sections: list[dict], parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("""
            PluginSettingsOverlay {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #0d121f, stop:1 #070913);
                border: 1px solid rgba(99, 102, 241, 0.4);
                border-radius: 16px;
            }
        """)
        self.setFixedWidth(self._OW)
        self._sections = sections or []
        self._widgets: dict[tuple, Any] = {}    # (namespace, key) -> input widget
        self._types:   dict[tuple, str]    = {}     # (namespace, key) -> field type
        self._status_labels: dict[str, QLabel] = {} # namespace -> status QLabel
        self._test_done.connect(self._on_test_done)

        root = QVBoxLayout(self)
        root.setContentsMargins(22, 18, 22, 18)
        root.setSpacing(12)

        # Header Row: Icon Badge + Title/Subtitle + Close
        hdr_row = QHBoxLayout()
        hdr_row.setSpacing(12)

        icon_box = QFrame()
        icon_box.setFixedSize(38, 38)
        icon_box.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 rgba(99, 102, 241, 0.28), stop:1 rgba(139, 92, 246, 0.12));
                border: 1px solid rgba(99, 102, 241, 0.45);
                border-radius: 10px;
            }
        """)
        ib_lay = QHBoxLayout(icon_box)
        ib_lay.setContentsMargins(0, 0, 0, 0)
        ib_lbl = QLabel("⚙")
        ib_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ib_lbl.setFont(QFont("Segoe UI Emoji", 13))
        ib_lbl.setStyleSheet("background: transparent; border: none; color: #a5b4fc;")
        ib_lay.addWidget(ib_lbl)
        hdr_row.addWidget(icon_box)

        hdr_v = QVBoxLayout()
        hdr_v.setSpacing(2)
        hdr = QLabel("PLUGIN SETTINGS")
        hdr.setFont(QFont(APP_FONT_NAME, 11, QFont.Weight.Bold))
        hdr.setStyleSheet("color: #ffffff; background: transparent; letter-spacing: 0.5px;")
        hdr_v.addWidget(hdr)
        sub = QLabel("Configure credentials, webhooks, and options for active integrations.")
        sub.setFont(QFont(APP_FONT_NAME, 9))
        sub.setStyleSheet("color: #94a3b8; background: transparent;")
        hdr_v.addWidget(sub)
        hdr_row.addLayout(hdr_v)
        hdr_row.addStretch()

        ps_close_btn = QPushButton("✕")
        ps_close_btn.setFixedSize(28, 28)
        ps_close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        ps_close_btn.setToolTip("Close")
        ps_close_btn.setStyleSheet("""
            QPushButton {
                color: #94a3b8;
                background: rgba(255, 255, 255, 0.04);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 7px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover {
                color: #ef4444;
                background: rgba(239, 68, 68, 0.15);
                border-color: rgba(239, 68, 68, 0.35);
            }
        """)
        ps_close_btn.clicked.connect(self.hide)
        hdr_row.addWidget(ps_close_btn)
        root.addLayout(hdr_row)

        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: rgba(255, 255, 255, 0.08); margin: 2px 0;")
        root.addWidget(sep)

        if not self._sections:
            empty_lbl = QLabel(
                "No configurable plugins are installed.\nDrop a plugin that needs "
                "settings into the plugins folder and it will show up here."
            )
            empty_lbl.setFont(QFont(APP_FONT_NAME, 9))
            empty_lbl.setStyleSheet("color: #94a3b8; background: transparent; padding: 20px 0;")
            empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            root.addWidget(empty_lbl)
        else:
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QFrame.Shape.NoFrame)
            scroll.setStyleSheet("""
                QScrollArea { background: transparent; border: none; }
                QScrollBar:vertical { background: transparent; width: 6px; border: none; margin: 2px; }
                QScrollBar::handle:vertical { background: rgba(255, 255, 255, 0.16); border-radius: 3px; min-height: 25px; }
                QScrollBar::handle:vertical:hover { background: rgba(99, 102, 241, 0.6); }
            """)
            inner = QWidget()
            inner.setStyleSheet("background: transparent;")
            form = QVBoxLayout(inner)
            form.setContentsMargins(0, 4, 6, 4)
            form.setSpacing(12)
            for sec in self._sections:
                self._build_section(form, sec)
            form.addStretch(1)
            scroll.setWidget(inner)
            root.addWidget(scroll, 1)

        # ── bottom buttons ───────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        if self._sections:
            save_btn = QPushButton("✓  SAVE CHANGES")
            save_btn.setFixedHeight(34)
            save_btn.setFont(QFont(APP_FONT_NAME, 9, QFont.Weight.Bold))
            save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            save_btn.setStyleSheet("""
                QPushButton {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #6366f1, stop:1 #4f46e5);
                    color: #ffffff;
                    border: 1px solid rgba(255, 255, 255, 0.2);
                    border-radius: 8px;
                    padding: 0 18px;
                }
                QPushButton:hover {
                    background: #4f46e5;
                    border-color: #818cf8;
                }
            """)
            save_btn.clicked.connect(self._save_all)
            btn_row.addWidget(save_btn)

        close_btn = QPushButton("CLOSE")
        close_btn.setFixedHeight(34)
        close_btn.setFont(QFont(APP_FONT_NAME, 9))
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.03);
                color: #94a3b8;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 8px;
                padding: 0 16px;
            }
            QPushButton:hover {
                color: #f1f5f9;
                background: rgba(255, 255, 255, 0.07);
                border-color: rgba(255, 255, 255, 0.15);
            }
        """)
        close_btn.clicked.connect(self.hide)
        btn_row.addWidget(close_btn)
        root.addLayout(btn_row)

    # ── helpers ───────────────────────────────────────────────────────────────
    def _lbl(self, txt, fs=9, bold=False, color="#94a3b8",
             align=Qt.AlignmentFlag.AlignLeft):
        w = QLabel(txt); w.setAlignment(align); w.setWordWrap(True)
        w.setFont(QFont(APP_FONT_NAME, fs,
                        QFont.Weight.Bold if bold else QFont.Weight.Normal))
        w.setStyleSheet(f"color: {color}; background: transparent;")
        return w

    def _build_section(self, form: QVBoxLayout, sec: dict):
        ns     = sec.get("namespace") or sec.get("plugin") or "plugin"
        title  = sec.get("title") or ns
        fields = sec.get("fields") or []
        values = sec.get("values") or {}

        sec_card = QFrame()
        sec_card.setStyleSheet("""
            QFrame {
                background: rgba(255, 255, 255, 0.02);
                border: 1px solid rgba(255, 255, 255, 0.07);
                border-radius: 12px;
            }
        """)
        c_lay = QVBoxLayout(sec_card)
        c_lay.setContentsMargins(16, 14, 16, 14)
        c_lay.setSpacing(10)

        # Card Title Row
        t_row = QHBoxLayout()
        t_row.setSpacing(8)
        dot = QFrame()
        dot.setFixedSize(7, 7)
        dot.setStyleSheet("background: #6366f1; border-radius: 3px;")
        t_row.addWidget(dot)

        t_lbl = QLabel(title)
        t_lbl.setFont(QFont(APP_FONT_NAME, 10, QFont.Weight.Bold))
        t_lbl.setStyleSheet("color: #f8fafc; background: transparent; border: none;")
        t_row.addWidget(t_lbl)
        t_row.addStretch()
        c_lay.addLayout(t_row)

        input_css = """
            QLineEdit {
                background: rgba(255, 255, 255, 0.035);
                color: #f1f5f9;
                border: 1px solid rgba(255, 255, 255, 0.09);
                border-radius: 7px;
                padding: 5px 10px;
            }
            QLineEdit:focus {
                border: 1px solid #6366f1;
                background: rgba(99, 102, 241, 0.06);
            }
        """

        for field in fields:
            if not isinstance(field, dict) or not field.get("key"):
                continue
            key   = field["key"]
            ftype = (field.get("type") or "text").lower()
            label = field.get("label") or key
            default = field.get("default")
            stored  = values.get(key, default)

            if ftype == "toggle":
                t_box = QHBoxLayout()
                t_box.setSpacing(8)
                lbl = QLabel(label)
                lbl.setFont(QFont(APP_FONT_NAME, 9, QFont.Weight.Medium))
                lbl.setStyleSheet("color: #cbd5e1; background: transparent; border: none;")
                t_box.addWidget(lbl)
                t_box.addStretch()

                w = QPushButton()
                w.setCheckable(True)
                w.setChecked(bool(stored))
                w.setFixedSize(56, 26)
                w.setFont(QFont(APP_FONT_NAME, 8, QFont.Weight.Bold))
                w.setCursor(Qt.CursorShape.PointingHandCursor)
                self._style_toggle(w)
                w.toggled.connect(lambda _=False, b=w: self._style_toggle(b))
                t_box.addWidget(w)
                c_lay.addLayout(t_box)
            else:
                lbl = QLabel(label.upper())
                lbl.setFont(QFont(APP_FONT_NAME, 8, QFont.Weight.DemiBold))
                lbl.setStyleSheet("color: #94a3b8; background: transparent; border: none; letter-spacing: 0.3px;")
                c_lay.addWidget(lbl)

                if ftype == "choice":
                    w = QComboBox()
                    w.addItems([str(o) for o in field.get("options", [])])
                    w.setFont(QFont(APP_FONT_NAME, 9))
                    w.setFixedHeight(32)
                    w.setStyleSheet("""
                        QComboBox {
                            background: rgba(255, 255, 255, 0.035);
                            color: #f1f5f9;
                            border: 1px solid rgba(255, 255, 255, 0.09);
                            border-radius: 7px;
                            padding: 2px 10px;
                        }
                        QComboBox:focus { border-color: #6366f1; }
                        QComboBox QAbstractItemView {
                            background: #0d121f;
                            color: #f1f5f9;
                            border: 1px solid rgba(99, 102, 241, 0.4);
                            selection-background-color: #6366f1;
                        }
                    """)
                    if stored is not None:
                        w.setCurrentText(str(stored))
                else:  # text / password
                    w = QLineEdit("" if stored is None else str(stored))
                    w.setFont(QFont(APP_FONT_NAME, 9))
                    w.setFixedHeight(32)
                    w.setStyleSheet(input_css)
                    if field.get("placeholder"):
                        w.setPlaceholderText(str(field["placeholder"]))
                    if ftype == "password":
                        w.setEchoMode(QLineEdit.EchoMode.Password)

                c_lay.addWidget(w)

            self._widgets[(ns, key)] = w
            self._types[(ns, key)]   = ftype

        # optional test/connect action button + status line
        action = sec.get("action")
        if isinstance(action, dict) and callable(action.get("run")):
            c_lay.addSpacing(2)
            act_box = QHBoxLayout()
            act_box.setSpacing(10)
            ab = QPushButton(str(action.get("label") or "TEST"))
            ab.setFixedHeight(30)
            ab.setFont(QFont(APP_FONT_NAME, 8, QFont.Weight.Bold))
            ab.setCursor(Qt.CursorShape.PointingHandCursor)
            ab.setStyleSheet("""
                QPushButton {
                    background: rgba(99, 102, 241, 0.12);
                    color: #a5b4fc;
                    border: 1px solid rgba(99, 102, 241, 0.3);
                    border-radius: 7px;
                    padding: 0 14px;
                }
                QPushButton:hover {
                    background: #6366f1;
                    color: #ffffff;
                    border-color: #818cf8;
                }
            """)
            ab.clicked.connect(lambda _=False, n=ns: self._run_action(n))
            act_box.addWidget(ab)

            status = QLabel("")
            status.setFont(QFont(APP_FONT_NAME, 8))
            status.setStyleSheet("color: #94a3b8; background: transparent; border: none;")
            self._status_labels[ns] = status
            act_box.addWidget(status)
            act_box.addStretch()
            c_lay.addLayout(act_box)
        else:
            status = QLabel("")
            status.setFont(QFont(APP_FONT_NAME, 8))
            status.setStyleSheet("color: #94a3b8; background: transparent; border: none;")
            self._status_labels[ns] = status
            c_lay.addWidget(status)

        form.addWidget(sec_card)

    def _style_toggle(self, btn: QPushButton):
        on = btn.isChecked()
        btn.setText("ON" if on else "OFF")
        if on:
            btn.setStyleSheet("""
                QPushButton {
                    background: rgba(34, 197, 94, 0.14);
                    color: #4ade80;
                    border: 1px solid rgba(34, 197, 94, 0.35);
                    border-radius: 6px;
                    font-weight: bold;
                }
                QPushButton:hover { background: rgba(34, 197, 94, 0.24); }
            """)
        else:
            btn.setStyleSheet("""
                QPushButton {
                    background: rgba(255, 255, 255, 0.03);
                    color: #64748b;
                    border: 1px solid rgba(255, 255, 255, 0.08);
                    border-radius: 6px;
                    font-weight: bold;
                }
                QPushButton:hover { color: #cbd5e1; border-color: rgba(255, 255, 255, 0.18); }
            """)

    # ── data ──────────────────────────────────────────────────────────────────
    def _gather(self, ns: str) -> dict:
        out = {}
        for (n, key), w in self._widgets.items():
            if n != ns:
                continue
            t = self._types.get((n, key), "text")
            if t == "choice":
                out[key] = w.currentText()
            elif t == "toggle":
                out[key] = w.isChecked()
            else:
                out[key] = w.text().strip()
        return out

    def _save_ns(self, ns: str):
        from memory.config_manager import save_plugin_config
        save_plugin_config(ns, self._gather(ns))

    def _save_all(self):
        for sec in self._sections:
            ns = sec.get("namespace") or sec.get("plugin")
            if ns:
                self._save_ns(ns)
                lbl = self._status_labels.get(ns)
                if lbl:
                    lbl.setText("Saved ✓")
                    lbl.setStyleSheet("color: #4ade80; background: transparent;")

    def _run_action(self, ns: str):
        sec = next((s for s in self._sections
                    if (s.get("namespace") or s.get("plugin")) == ns), None)
        if not sec:
            return
        run_fn = (sec.get("action") or {}).get("run")
        if not callable(run_fn):
            return
        self._save_ns(ns)                 # persist what the user typed before testing
        values = self._gather(ns)
        lbl = self._status_labels.get(ns)
        if lbl:
            lbl.setText("Testing…")
            lbl.setStyleSheet("color: #94a3b8; background: transparent;")

        def worker():
            try:
                res = run_fn(values)
                if isinstance(res, tuple) and len(res) == 2:
                    ok, msg = bool(res[0]), str(res[1])
                else:
                    ok, msg = bool(res), str(res)
            except Exception as e:
                ok, msg = False, str(e)
            self._test_done.emit(ns, ok, msg)

        threading.Thread(target=worker, daemon=True).start()

    def _on_test_done(self, ns: str, ok: bool, msg: str):
        lbl = self._status_labels.get(ns)
        if not lbl:
            return
        lbl.setText(msg)
        color = "#4ade80" if ok else "#f87171"
        lbl.setStyleSheet(f"color: {color}; background: transparent;")


class RemoteKeyOverlay(QWidget):
    """Floating overlay — QR code for instant phone pairing + manual key fallback."""

    closed = pyqtSignal()

    _OW, _OH = 400, 465

    def __init__(self, url: str, key: str, auto_login_url: str = "",
                 manual_url: str = "", expiry_secs: int = 600, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            RemoteKeyOverlay {{
                background: #090e18;
                border: 1px solid rgba(99, 102, 241, 0.4);
                border-radius: 16px;
            }}
        """)
        self._expiry          = time.time() + expiry_secs
        self._on_new_key      = None
        self._auto_login_url  = auto_login_url
        self._manual_url      = manual_url or url

        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 16, 24, 16)
        lay.setSpacing(5)

        def _lbl(txt, fs=9, bold=False, color=C.PRI,
                 align=Qt.AlignmentFlag.AlignCenter):
            w = QLabel(txt)
            w.setAlignment(align)
            w.setFont(QFont(APP_FONT_NAME, fs,
                            QFont.Weight.Bold if bold else QFont.Weight.Normal))
            w.setStyleSheet(f"color: {color}; background: transparent;")
            w.setWordWrap(True)
            return w

        lay.addWidget(_lbl("◈  REMOTE ACCESS", 12, True))
        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {C.BORDER}; margin: 1px 0;")
        lay.addWidget(sep)

        # ── QR code ───────────────────────────────────────────────────────────
        self._qr_label = QLabel()
        self._qr_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._qr_label.setFixedSize(176, 176)
        self._qr_label.setStyleSheet(
            "background: white; border-radius: 10px; padding: 4px;"
        )
        qr_row = QHBoxLayout()
        qr_row.addStretch()
        qr_row.addWidget(self._qr_label)
        qr_row.addStretch()
        lay.addLayout(qr_row)

        self._update_qr(auto_login_url)

        lay.addWidget(_lbl("Scan with phone camera to connect instantly", 8, color=C.TEXT_DIM))

        sep2 = QFrame(); sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setStyleSheet(f"color: {C.BORDER}; margin: 1px 0;")
        lay.addWidget(sep2)

        lay.addWidget(_lbl("Or enter manually:", 7, color=C.TEXT_DIM,
                           align=Qt.AlignmentFlag.AlignLeft))

        self._url_lbl = QLabel(self._manual_url)
        self._url_lbl.setFont(QFont(APP_FONT_NAME, 8))
        self._url_lbl.setStyleSheet(f"color: {C.PRI_DIM}; background: transparent;")
        self._url_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._url_lbl.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        lay.addWidget(self._url_lbl)

        self._key_lbl = QLabel(key)
        self._key_lbl.setFont(QFont(APP_FONT_NAME, 28, QFont.Weight.Bold))
        self._key_lbl.setStyleSheet(f"""
            color: {C.ACC};
            background: {C.PANEL2};
            border: 1px solid {C.BORDER_B};
            border-radius: 8px;
            padding: 6px 4px;
            letter-spacing: 10px;
        """)
        self._key_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self._key_lbl)

        self._timer_lbl = QLabel()
        self._timer_lbl.setFont(QFont(APP_FONT_NAME, 8))
        self._timer_lbl.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent;")
        self._timer_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self._timer_lbl)

        btn_row = QHBoxLayout(); btn_row.setSpacing(8)
        new_btn = QPushButton("NEW KEY")
        new_btn.setFixedHeight(32)
        new_btn.setFont(QFont(APP_FONT_NAME, 8, QFont.Weight.Bold))
        new_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        new_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C.PANEL}; color: {C.PRI};
                border: 1px solid {C.PRI_DIM}; border-radius: 5px;
            }}
            QPushButton:hover {{ background: {C.PRI_GHO}; border: 1px solid {C.PRI}; }}
        """)
        new_btn.clicked.connect(self._refresh_key)
        btn_row.addWidget(new_btn)

        close_btn = QPushButton("DISMISS")
        close_btn.setFixedHeight(32)
        close_btn.setFont(QFont(APP_FONT_NAME, 8, QFont.Weight.Bold))
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {C.TEXT_MED};
                border: 1px solid {C.BORDER}; border-radius: 5px;
            }}
            QPushButton:hover {{ color: {C.TEXT}; border: 1px solid {C.BORDER_B}; }}
        """)
        close_btn.clicked.connect(self._do_close)
        btn_row.addWidget(close_btn)
        lay.addLayout(btn_row)

        self._ctimer = QTimer(self)
        self._ctimer.timeout.connect(self._tick)
        self._ctimer.start(1000)
        self._tick()

    def set_new_key_callback(self, fn) -> None:
        self._on_new_key = fn

    def _update_qr(self, url: str) -> None:
        if not url:
            self._qr_label.setText("—")
            return
        try:
            import qrcode as _qrmod
            from io import BytesIO
            qr = _qrmod.QRCode(
                box_size=5, border=2,
                error_correction=_qrmod.constants.ERROR_CORRECT_M,
            )
            qr.add_data(url)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")
            buf = BytesIO()
            img.save(buf, format="PNG")
            px = QPixmap()
            px.loadFromData(buf.getvalue())
            self._qr_label.setPixmap(
                px.scaled(170, 170,
                          Qt.AspectRatioMode.KeepAspectRatio,
                          Qt.TransformationMode.SmoothTransformation)
            )
        except ImportError:
            self._qr_label.setText("pip install\nqrcode[pil]")
            self._qr_label.setFont(QFont(APP_FONT_NAME, 8))
            self._qr_label.setStyleSheet(
                "color: #888; background: white; border-radius: 10px; padding: 4px;"
            )
        except Exception:
            self._qr_label.setText(url[:28])
            self._qr_label.setFont(QFont(APP_FONT_NAME, 7))
            self._qr_label.setStyleSheet(
                f"color: {C.PRI}; background: white; border-radius: 10px; padding: 4px;"
            )

    def _tick(self):
        remaining = max(0, int(self._expiry - time.time()))
        m, s = divmod(remaining, 60)
        self._timer_lbl.setText(f"Key expires in  {m:02d}:{s:02d}")
        if remaining == 0:
            self._do_close()

    def mark_connected(self) -> None:
        """Call from any thread when a phone successfully connects."""
        self._ctimer.stop()
        self._key_lbl.setText("CONNECTED")
        self._key_lbl.setStyleSheet(f"""
            color: {C.GREEN};
            background: rgba(34,197,94,0.08);
            border: 2px solid rgba(34,197,94,0.4);
            border-radius: 8px;
            padding: 6px 4px;
            letter-spacing: 4px;
        """)
        self._qr_label.setText("✓")
        self._qr_label.setFont(QFont(APP_FONT_NAME, 54, QFont.Weight.Bold))
        self._qr_label.setStyleSheet(
            "color: #00ff88; background: #001a0d; border-radius: 10px;"
        )
        self._timer_lbl.setText("Phone connected — CHARLIE ready")
        self._timer_lbl.setStyleSheet(f"color: {C.GREEN}; background: transparent;")

    def _refresh_key(self):
        if self._on_new_key:
            result = self._on_new_key()
            if result:
                url    = result[0]
                key    = result[1]
                auto   = result[2] if len(result) >= 3 else ""
                manual = result[3] if len(result) >= 4 else url
                self._manual_url     = manual or url
                self._url_lbl.setText(self._manual_url)
                self._key_lbl.setText(key)
                self._auto_login_url = auto
                self._update_qr(auto or url)
                self._expiry = time.time() + 600
                self._key_lbl.setStyleSheet(f"""
                    color: {C.ACC};
                    background: {C.PANEL2};
                    border: 1px solid {C.BORDER_B};
                    border-radius: 8px;
                    padding: 6px 4px;
                    letter-spacing: 10px;
                """)
                self._timer_lbl.setStyleSheet(
                    f"color: {C.TEXT_MED}; background: transparent;"
                )
                self._ctimer.start(1000)
                self._tick()

    def _do_close(self):
        self._ctimer.stop()
        self.hide()
        self.closed.emit()


_NAV_SVGS = [
    "nav_home",
    "nav_chat",
    "nav_voice",
    "nav_avatar",
    "chip_doc",
    "nav_screen",
    "nav_brain",
    "nav_settings",
]


class _StarterCard(QFrame):
    def __init__(self, svg_name: str, title: str, desc: str, callback, parent=None):
        super().__init__(parent)
        self._cb = callback
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(66)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setObjectName("StarterCard")
        self.setStyleSheet(f"""
            QFrame#StarterCard {{
                background: {C.PANEL};
                border: 1px solid {C.BORDER};
                border-radius: 12px;
            }}
            QFrame#StarterCard:hover {{
                background: {C.PANEL2};
                border: 1px solid rgba(99, 102, 241, 0.40);
            }}
        """)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(12)

        icon_box = QLabel()
        icon_box.setFixedSize(36, 36)
        icon_box.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_box.setPixmap(_render_hub_svg(svg_name, 18, "#818cf8"))
        icon_box.setStyleSheet("background: rgba(99, 102, 241, 0.10); border: 1px solid rgba(99, 102, 241, 0.25); border-radius: 8px;")
        icon_box.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        lay.addWidget(icon_box)

        text_lay = QVBoxLayout()
        text_lay.setSpacing(2)
        text_lay.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        t_lbl = QLabel(title)
        t_lbl.setFont(QFont(APP_FONT_NAME, 9, QFont.Weight.DemiBold))
        t_lbl.setStyleSheet("color: #f8fafc; background: transparent; border: none;")
        t_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        text_lay.addWidget(t_lbl)

        d_lbl = QLabel(desc)
        d_lbl.setFont(QFont(APP_FONT_NAME, 7))
        d_lbl.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent; border: none;")
        d_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        text_lay.addWidget(d_lbl)

        lay.addLayout(text_lay, 1)

    def sizeHint(self):
        return QSize(300, 66)

    def minimumSizeHint(self):
        return QSize(220, 66)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if callable(self._cb):
                self._cb()
            event.accept()
        else:
            super().mousePressEvent(event)

class MiniHudWidget(QWidget):
    """
    Lightweight, floating, always-on-top, draggable desktop widget for CHARLIE AI.
    Displays compact state, live mic status, pulse waveform, and quick restore.
    """
    def __init__(self, main_window):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.main_window = main_window
        self._drag_pos = None
        self._level = 0.0
        self._state_text = "Ready"
        self._state_color = "#22c55e"
        self._is_muted = False

        self.setFixedSize(310, 48)
        self._init_ui()
        self._position_on_screen()

    def _position_on_screen(self):
        scr = QApplication.primaryScreen()
        if scr:
            geom = scr.availableGeometry()
            self.move(geom.right() - 340, geom.top() + 60)

    def _init_ui(self):
        container = QFrame(self)
        container.setGeometry(0, 0, 310, 48)
        container.setObjectName("MiniHudContainer")
        container.setStyleSheet("""
            QFrame#MiniHudContainer {
                background: rgba(11, 15, 25, 0.94);
                border: 1px solid rgba(0, 229, 255, 0.40);
                border-radius: 24px;
            }
        """)

        layout = QHBoxLayout(container)
        layout.setContentsMargins(14, 4, 10, 4)
        layout.setSpacing(8)

        # Pulse indicator / Logo
        self._pulse_dot = QLabel("●")
        self._pulse_dot.setFont(QFont(APP_FONT_NAME, 11, QFont.Weight.Bold))
        self._pulse_dot.setStyleSheet("color: #22c55e; background: transparent;")
        layout.addWidget(self._pulse_dot)

        # State text label
        name = getattr(self.main_window, "_assistant_name", "CHARLIE")
        self._label = QLabel(f"{name} · Ready")
        self._label.setFont(QFont(APP_FONT_NAME, 9, QFont.Weight.DemiBold))
        self._label.setStyleSheet("color: #ffffff; background: transparent;")
        layout.addWidget(self._label, 1)

        # Mic mute toggle button
        self._mic_btn = QPushButton()
        self._mic_btn.setFixedSize(28, 28)
        self._mic_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        try:
            self._mic_btn.setIcon(_render_svg_icon("mic_solid", 14, "#00e5ff"))
            self._mic_btn.setIconSize(QSize(14, 14))
        except Exception:
            self._mic_btn.setText("🎤")
        self._mic_btn.setToolTip("Toggle Mic Mute")
        self._mic_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.08);
                border: 1px solid rgba(255, 255, 255, 0.15);
                border-radius: 14px;
                color: #00e5ff;
            }
            QPushButton:hover {
                background: rgba(0, 229, 255, 0.2);
                border-color: #00e5ff;
            }
        """)
        self._mic_btn.clicked.connect(self._toggle_mic)
        layout.addWidget(self._mic_btn)

        # Expand / Restore button
        self._expand_btn = QPushButton("⛶")
        self._expand_btn.setFixedSize(28, 28)
        self._expand_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._expand_btn.setFont(QFont(APP_FONT_NAME, 11, QFont.Weight.Bold))
        self._expand_btn.setToolTip("Expand to Full Window")
        self._expand_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.08);
                border: 1px solid rgba(255, 255, 255, 0.15);
                border-radius: 14px;
                color: #ffffff;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.2);
            }
        """)
        self._expand_btn.clicked.connect(self.restore_main_window)
        layout.addWidget(self._expand_btn)

        # Close / Hide button
        self._close_btn = QPushButton("✕")
        self._close_btn.setFixedSize(22, 22)
        self._close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._close_btn.setToolTip("Restore Main Window")
        self._close_btn.setStyleSheet("""
            QPushButton {
                color: #94a3b8;
                background: transparent;
                border: none;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton:hover {
                color: #ef4444;
            }
        """)
        self._close_btn.clicked.connect(self.restore_main_window)
        layout.addWidget(self._close_btn)

    def _toggle_mic(self):
        if hasattr(self.main_window, "_toggle_mute"):
            self.main_window._toggle_mute()

    def set_muted(self, muted: bool):
        self._is_muted = muted
        if muted:
            try:
                self._mic_btn.setIcon(_render_svg_icon("mic_off", 14, "#ef4444"))
            except Exception:
                self._mic_btn.setText("🔇")
            self._mic_btn.setStyleSheet("""
                QPushButton {
                    background: rgba(239, 68, 68, 0.15);
                    border: 1px solid rgba(239, 68, 68, 0.4);
                    border-radius: 14px;
                    color: #ef4444;
                }
            """)
        else:
            try:
                self._mic_btn.setIcon(_render_svg_icon("mic_solid", 14, "#00e5ff"))
            except Exception:
                self._mic_btn.setText("🎤")
            self._mic_btn.setStyleSheet("""
                QPushButton {
                    background: rgba(255, 255, 255, 0.08);
                    border: 1px solid rgba(255, 255, 255, 0.15);
                    border-radius: 14px;
                    color: #00e5ff;
                }
                QPushButton:hover {
                    background: rgba(0, 229, 255, 0.2);
                    border-color: #00e5ff;
                }
            """)

    def set_state(self, state: str, text: str = "", colour: str = "#22c55e", bg: str = "", border: str = ""):
        self._state_text = text or state.capitalize()
        self._state_color = colour
        name = getattr(self.main_window, "_assistant_name", "CHARLIE")
        self._label.setText(f"{name} · {self._state_text}")
        self._label.setStyleSheet(f"color: {colour}; background: transparent; font-weight: 600;")
        self._pulse_dot.setStyleSheet(f"color: {colour}; background: transparent;")

    def set_audio_level(self, level: float):
        self._level = level
        if level > 0.08 and not self._is_muted:
            self._pulse_dot.setText("◉")
        else:
            self._pulse_dot.setText("●")

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton and self._drag_pos:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseDoubleClickEvent(self, event):
        self.restore_main_window()
        event.accept()

    def restore_main_window(self):
        self.hide()
        if self.main_window:
            self.main_window.showNormal()
            self.main_window.raise_()
            self.main_window.activateWindow()


class MainWindow(QMainWindow):
    _log_sig        = pyqtSignal(str)
    _state_sig      = pyqtSignal(str)
    _content_sig    = pyqtSignal(str, str)   # (title, text) — thread-safe content display
    _reconfig_sig   = pyqtSignal()           # trigger setup overlay from any thread
    _camera_sig     = pyqtSignal(bytes)      # show camera frame preview (small overlay)
    _cam_stream_sig = pyqtSignal(bool)       # True=start live stream, False=stop
    _cam_frame_sig  = pyqtSignal(bytes)      # live camera frame → HUD area
    _clipboard_sig  = pyqtSignal(str)        # clipboard text changed (thread-safe)
    _confirm_sig    = pyqtSignal(str, str)   # (title, detail) — irreversible-action gate
    _confirm_hide_sig = pyqtSignal()
    _wake_dl_sig    = pyqtSignal(bool, str)  # wake-word install finished (ok, message)
    _quiz_sig       = pyqtSignal(str, object, object)  # (topic, questions, grader)
    _quiz_hide_sig  = pyqtSignal()
    _review_sig     = pyqtSignal(str, str, object, object)  # document review payload
    _chat_busy_sig  = pyqtSignal(bool)
    _dictation_text_sig = pyqtSignal(str)
    _dictation_state_sig = pyqtSignal(bool, str)
    _command_bar_sig = pyqtSignal()
    _commercial_ready_sig = pyqtSignal()
    _proactive_nudge_sig  = pyqtSignal(object)
    _weather_sig          = pyqtSignal(object)   # (dict) real-time weather & location payload

    def __init__(self, face_path: str):
        super().__init__()
        self._face_path = face_path

        # Load customization from config
        _cfg = _read_full_config()
        self._assistant_name: str = (_cfg.get("assistant_name") or "CHARLIE").strip()
        if self._assistant_name.upper() in ("JARVIS", "J.A.R.V.I.S.", "J.A.R.V.I.S"):
            self._assistant_name = "CHARLIE"
        _display = self._assistant_name.upper()

        # Apply the saved theme and colour BEFORE panels/stylesheets are built.
        _ui_color = (_cfg.get("ui_color") or "").strip()
        apply_ui_theme(_cfg.get("ui_theme", DEFAULT_UI_THEME), _ui_color)

        self.setWindowTitle(f"{_display} — {APP_VERSION} · v{RELEASE_VERSION}")
        _ico_p = Path(__file__).resolve().parent / "config" / "charlie.ico"
        if not _ico_p.exists():
            _ico_p = Path(__file__).resolve().parent / "config" / "charlie.png"
        if _ico_p.exists():
            self.setWindowIcon(QIcon(str(_ico_p)))
        self.setMinimumSize(_MIN_W, _MIN_H)
        self.resize(_DEFAULT_W, _DEFAULT_H)

        scr = QApplication.primaryScreen()
        if scr is not None:
            screen = scr.availableGeometry()
            self.move(
                (screen.width()  - _DEFAULT_W) // 2,
                (screen.height() - _DEFAULT_H) // 2,
            )

        self.on_text_command   = None
        self.on_chat_command   = None   # detailed text-only assistant callback
        self.on_new_chat       = None   # reset text-chat context callback
        self.on_chat_dictation = None   # callable: (enabled: bool) -> None
        self.request_say       = None   # callable: (instruction) -> None — UI activity buttons
        self.on_remote_clicked = None   # callable: () -> (url, key) | None
        self.on_interrupt      = None   # callable: () -> None — stop CHARLIE mid-speech
        self.on_voice_change   = None   # callable: () -> None — rebuild session with new voice
        self.on_listening_change = None # callable: () -> None — apply microphone turn timing
        self.on_audio_device_change = None  # callable: () -> None — reopen audio streams
        self._confirm_overlay  = None   # live ConfirmBanner, if one is on screen
        self.get_plugins       = None   # callable: () -> list[dict], set by CharlieLive
        self.get_plugin_settings = None # callable: () -> list[dict] settings schemas, set by CharlieLive
        self.rescan_plugins    = None   # callable: () -> None, set by CharlieLive
        self.on_wake_toggle    = None   # callable: (enable: bool) -> str, set by CharlieLive
        self.on_wake_manual    = None   # callable: () -> None — manual sleep/wake
        self.on_push_to_talk   = None   # callable: (enable: bool) -> str scope
        self.ptt_hold          = None   # callable: (held: bool) -> None — windowed chord
        self.wake_get_state    = None   # callable: () -> dict {enabled, awake, ready}
        self._muted            = False
        self._chat_mode        = False
        self._chat_busy        = False
        self._chat_dictating   = False
        self._mic_before_chat  = False
        self._chat_restore_sizes: list[int] | None = None
        self._chat_restore_content = False
        self._chat_restore_quiz = False
        self._current_file: str | None = None
        self._remote_overlay: RemoteKeyOverlay | None = None
        self._customize_overlay: CustomizeOverlay | None = None
        self._pricing_overlay = None
        self._commercial_engine = None
        self._subscription_checked = False
        self._commercial_loading = False
        self._commercial_error = ""
        self._commercial_ready_sig.connect(self._on_commercial_ready)
        self._quick_drawer: QWidget | None = None
        self._hud_btn: QPushButton | None = None

        central = QWidget()
        central.setObjectName("CentralWidget")
        central.setStyleSheet(f"""
            QWidget#CentralWidget {{
                background: {C.BG};
            }}
            QMenu {{
                background-color: #0f172a;
                color: #f1f5f9;
                border: 1px solid rgba(255, 255, 255, 0.15);
                border-radius: 8px;
                padding: 4px;
            }}
            QMenu::item {{
                padding: 6px 20px 6px 12px;
                border-radius: 4px;
                color: #e2e8f0;
            }}
            QMenu::item:selected {{
                background-color: #6366f1;
                color: #ffffff;
            }}
            QMenu::item:disabled {{
                color: #64748b;
            }}
            QMenu::separator {{
                height: 1px;
                background-color: rgba(255, 255, 255, 0.1);
                margin: 4px 6px;
            }}
            QScrollBar:vertical {{
                background: transparent;
                width: 6px;
                margin: 4px 2px 4px 0;
                border-radius: 3px;
            }}
            QScrollBar::handle:vertical {{
                background: rgba(255, 255, 255, 0.12);
                min-height: 24px;
                border-radius: 3px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {C.PRI};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
                background: transparent;
            }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background: transparent;
            }}
            QScrollBar:horizontal {{
                background: transparent;
                height: 6px;
                margin: 0 4px 2px 4px;
                border-radius: 3px;
            }}
            QScrollBar::handle:horizontal {{
                background: rgba(255, 255, 255, 0.12);
                min-width: 24px;
                border-radius: 3px;
            }}
            QScrollBar::handle:horizontal:hover {{
                background: {C.PRI};
            }}
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
                width: 0px;
                background: transparent;
            }}
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
                background: transparent;
            }}
            QToolTip {{
                background: {C.PANEL2};
                color: {C.TEXT_PRIMARY};
                border: 1px solid {C.BORDER};
                border-radius: 6px;
                padding: 5px 8px;
                font-family: 'Inter', 'Segoe UI Variable Text', 'Segoe UI', sans-serif;
                font-size: 11px;
            }}
        """)
        self.setCentralWidget(central)

        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_header())

        body = QHBoxLayout()
        body.setContentsMargins(14, 12, 14, 12)
        body.setSpacing(14)

        # ── 1. Left Navigation Rail ──
        self._left_panel = self._build_left_panel()
        self._left_panel.show()
        body.addWidget(self._left_panel, stretch=0)

        # ── 2. Build 3D Avatar HUD & Live Camera Stack ──
        self.hud = HudCanvas(face_path, _display)
        self.hud.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._content_panel = self._build_content_panel()
        self._quiz_panel = self._build_quiz_panel()
        self._quiz: dict[str, Any] | None = None

        # Live camera container — replaces HUD when camera stream is active
        _cam_cont = QWidget()
        _cam_cont.setStyleSheet("background: #000308;")
        _cam_v = QVBoxLayout(_cam_cont)
        _cam_v.setContentsMargins(0, 0, 0, 0)
        _cam_v.setSpacing(0)
        _cam_hdr = QHBoxLayout()
        _cam_hdr.setContentsMargins(8, 5, 8, 5)
        _cam_title = QLabel("◈  CAMERA FEED")
        _cam_title.setFont(QFont(APP_FONT_NAME, 8, QFont.Weight.Bold))
        _cam_title.setStyleSheet(f"color: {C.PRI}; background: transparent;")
        _cam_hdr.addWidget(_cam_title)
        _cam_hdr.addStretch()
        _cam_x = QPushButton("✕  CLOSE")
        _cam_x.setFont(QFont(APP_FONT_NAME, 8, QFont.Weight.Bold))
        _cam_x.setCursor(Qt.CursorShape.PointingHandCursor)
        _cam_x.setStyleSheet(f"""
            QPushButton {{
                color: {C.TEXT_DIM}; background: transparent;
                border: none; padding: 2px 6px;
            }}
            QPushButton:hover {{ color: {C.PRI}; }}
        """)
        _cam_x.clicked.connect(self.stop_camera_stream)
        _cam_hdr.addWidget(_cam_x)
        _cam_v.addLayout(_cam_hdr)
        self._cam_live_lbl = QLabel()
        self._cam_live_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._cam_live_lbl.setStyleSheet("background: transparent;")
        self._cam_live_lbl.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        _cam_v.addWidget(self._cam_live_lbl, stretch=1)

        # Stack: 0 = animated voice HUD, 1 = live camera, 2 = text chat workspace
        self._hud_cam_stack = QStackedWidget()
        self._hud_cam_stack.addWidget(self.hud)
        self._hud_cam_stack.addWidget(_cam_cont)
        self._chat_workspace = ChatWorkspace(_display)
        self._chat_workspace.prompt_selected.connect(self._use_chat_prompt)
        self._chat_workspace.new_chat_requested.connect(self._start_new_chat)
        self._chat_workspace.dictation_requested.connect(self._toggle_chat_dictation)
        self._hud_cam_stack.addWidget(self._chat_workspace)

        # ── 3. Center Workspace: Greeting + Chat Log + Quick Prompts + Message Input + 5 Cards ──
        self._center_area = self._build_center_area()
        body.addWidget(self._center_area, stretch=5)

        # ── 4. Right Panel: 3D Assistant Viewport + Voice Controls ──
        self._right_panel = self._build_right_panel()
        body.addWidget(self._right_panel, stretch=0)

        root.addLayout(body, stretch=1)
        root.addWidget(self._build_footer())

        # Quick-access drawer (floating overlay, lazy-loaded on first open)
        self._quick_drawer: QWidget | None = None
        self._intelligence_hub = IntelligenceHub(self.centralWidget())
        self._intelligence_hub.feature_selected.connect(self._launch_intelligence_feature)
        self._command_bar = UniversalCommandBar(self.centralWidget())
        self._command_bar.submitted.connect(self._submit_universal_command)
        self._command_bar_sig.connect(self._show_universal_command_bar)
        from core.hotkey import GlobalShortcut
        self._global_command_shortcut = GlobalShortcut(lambda: self._command_bar_sig.emit())
        self._global_command_scope = self._global_command_shortcut.start()
        self._window_command_shortcut = QShortcut(QKeySequence("Ctrl+Space"), self)
        self._window_command_shortcut.activated.connect(self._show_universal_command_bar)
        self._alt_command_shortcut = QShortcut(QKeySequence("Alt+Space"), self)
        self._alt_command_shortcut.activated.connect(self._show_universal_command_bar)
        self._mini_hud = MiniHudWidget(self)
        self._mini_hud_shortcut = QShortcut(QKeySequence("Ctrl+M"), self)
        self._mini_hud_shortcut.activated.connect(self.show_mini_hud)

        # ── System Tray Icon & Menu ───────────────────────────────────────────
        self._setup_system_tray()
        self._update_autostart_btn(self._check_autostart())
        from memory.config_manager import get_brief_enabled as _gbe
        self._update_brief_btn(_gbe())

        self._clock_tmr = QTimer(self)
        self._clock_tmr.timeout.connect(self._tick_clock)
        self._clock_tmr.start(1000)
        self._tick_clock()

        # Metric update timer
        self._metric_tmr = QTimer(self)
        self._metric_tmr.timeout.connect(self._update_metrics)
        self._metric_tmr.start(2000)
        self._update_metrics()

        self._log_sig.connect(self._log.append_log)
        self._state_sig.connect(self._apply_state)
        self._content_sig.connect(self._show_content)
        self._reconfig_sig.connect(self._show_setup)
        self._camera_sig.connect(self._show_camera_frame)
        self._confirm_sig.connect(self._show_confirm_banner)
        self._confirm_hide_sig.connect(self._hide_confirm_banner)
        self._cam_stream_sig.connect(self._on_cam_stream)
        self._cam_frame_sig.connect(self._on_cam_frame)
        self._clipboard_sig.connect(self._show_clipboard_panel)
        self._wake_dl_sig.connect(self._on_wake_install_done)
        self._quiz_sig.connect(self._show_quiz)
        self._quiz_hide_sig.connect(self._hide_quiz)
        self._review_sig.connect(self._show_review)
        self._chat_busy_sig.connect(self._set_chat_busy)
        self._dictation_text_sig.connect(self._apply_chat_dictation_text)
        self._dictation_state_sig.connect(self._set_chat_dictation_state)
        self._proactive_nudge_sig.connect(self._display_proactive_nudge)
        self._weather_sig.connect(self._apply_weather_telemetry)
        self._init_weather_service()
        self._proactive_daemon = None
        self._cam_stop = threading.Event()

        # Camera preview overlay (child of central widget, positioned in resizeEvent)
        self._cam_preview = _CameraPreview(self.centralWidget())

        # Clipboard panel (child of central widget, bottom-center)
        self._clipboard_panel = ClipboardPanel(self.centralWidget())
        self._clipboard_panel.action_requested.connect(self._on_clipboard_action)
        clip = QApplication.clipboard()
        if clip is not None:
            clip.dataChanged.connect(self._on_clipboard_changed)

        self._overlay: SetupOverlay | None = None
        self._ready = self._check_config()
        if not self._ready:
            self._show_setup()
        else:
            self._apply_state("READY")

        sc_mute = QShortcut(QKeySequence("F4"), self)
        sc_mute.activated.connect(self._toggle_mute)
        sc_full = QShortcut(QKeySequence("F11"), self)
        sc_full.activated.connect(self._toggle_fullscreen)
        sc_intr = QShortcut(QKeySequence("Escape"), self)
        sc_intr.activated.connect(self._do_interrupt)
        sc_sett = QShortcut(QKeySequence("Ctrl+,"), self)
        sc_sett.activated.connect(self._open_settings_drawer)
        print("[CHARLIE-UI] -> MainWindow complete!", flush=True)

    def _show_camera_frame(self, img_bytes: bytes):
        """Slot — display camera preview overlay (main thread)."""
        self._cam_preview.show_frame(img_bytes)
        cw = self.centralWidget()
        if cw is not None:
            pw = _CameraPreview._W
            ph = self._cam_preview.height()
            self._cam_preview.setGeometry(
                cw.width() - _RIGHT_W - pw - 12,
                cw.height() - ph - 28,
                pw, ph,
            )

    # --- Live camera stream in HUD area ------------------------------------
    def _on_cam_stream(self, start: bool) -> None:
        if start:
            self._hud_cam_stack.setCurrentIndex(1)
        else:
            self._hud_cam_stack.setCurrentIndex(2 if self._chat_mode else 0)
            self._cam_live_lbl.clear()

    def _on_cam_frame(self, data: bytes) -> None:
        px = QPixmap()
        px.loadFromData(data)
        if not px.isNull():
            w, h = self._cam_live_lbl.width(), self._cam_live_lbl.height()
            if w > 1 and h > 1:
                self._cam_live_lbl.setPixmap(
                    px.scaled(w, h,
                              Qt.AspectRatioMode.KeepAspectRatio,
                              Qt.TransformationMode.SmoothTransformation)
                )

    def start_camera_stream(self) -> None:
        self._cam_stop.clear()
        self._cam_stream_sig.emit(True)
        t = threading.Thread(target=self._cam_loop, daemon=True, name="cam-stream")
        t.start()

    def _cam_loop(self) -> None:
        try:
            import cv2
            # Reuse camera index detected by screen_processor (cached in api_keys.json)
            cam_idx = 0
            try:
                import json as _j
                cfg = _j.loads((CONFIG_DIR / "api_keys.json").read_text())
                cam_idx = int(cfg.get("camera_index", 0))
            except Exception:
                pass
            try:
                backend = cv2.CAP_DSHOW if _OS == "Windows" else cv2.CAP_ANY
            except AttributeError:
                backend = 0
            cap = cv2.VideoCapture(cam_idx, backend)
            if not cap.isOpened():
                cap = cv2.VideoCapture(0)
            if not cap.isOpened():
                return
            # warm-up frames
            for _ in range(5):
                cap.read()
            while not self._cam_stop.wait(0.033) and cap.isOpened():
                ret, frame = cap.read()
                if ret and frame is not None:
                    _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 65])
                    self._cam_frame_sig.emit(buf.tobytes())
            cap.release()
        except Exception as e:
            print(f"[Camera] Stream error: {e}")
        finally:
            self._cam_stream_sig.emit(False)

    def stop_camera_stream(self) -> None:
        self._cam_stop.set()

    # ------------------------------------------------------------------
    # Icon generation — arc-reactor style, rendered with Pillow
    # ------------------------------------------------------------------
    @staticmethod
    def _build_charlie_icon(out_path: Path) -> bool:
        """
        Render a CHARLIE arc-reactor icon at 4× resolution and downsample
        for crisp results at all sizes. Saves a multi-res .ico to out_path.
        Returns True on success.
        """
        try:
            import math
            import PIL.Image
            import PIL.ImageDraw
            import PIL.ImageFilter
        except ImportError:
            return False

        CYAN   = (0, 212, 255)
        DIM    = (0, 100, 140)
        DARK   = (0, 6, 10)
        GLOW   = (0, 160, 200)
        WHITE  = (220, 240, 255)

        def _render(sz: int) -> PIL.Image.Image:
            S  = sz * 4                     # draw at 4× then downscale
            img = PIL.Image.new("RGBA", (S, S), (0, 0, 0, 0))
            d   = PIL.ImageDraw.Draw(img)
            cx = cy = S // 2

            # ── filled background circle ──────────────────────────────────
            R = S // 2 - 2
            d.ellipse([cx-R, cy-R, cx+R, cy+R], fill=(*DARK, 255))

            # ── outer border ring ─────────────────────────────────────────
            lw = max(2, S // 40)
            d.ellipse([cx-R, cy-R, cx+R, cy+R],
                      outline=(*CYAN, 220), width=lw)

            # ── mid decorative ring ───────────────────────────────────────
            R2 = int(R * 0.72)
            d.ellipse([cx-R2, cy-R2, cx+R2, cy+R2],
                      outline=(*DIM, 180), width=max(1, lw // 2))

            # ── 6 radial spokes (hex bolt) ────────────────────────────────
            R_inner = int(R * 0.30)
            R_outer = int(R * 0.62)
            spoke_w = max(1, S // 80)
            for i in range(6):
                angle = math.radians(i * 60 - 30)
                x1 = cx + int(R_inner * math.cos(angle))
                y1 = cy + int(R_inner * math.sin(angle))
                x2 = cx + int(R_outer * math.cos(angle))
                y2 = cy + int(R_outer * math.sin(angle))
                d.line([x1, y1, x2, y2], fill=(*GLOW, 200), width=spoke_w)

            # ── 6 tick marks on outer ring ────────────────────────────────
            for i in range(6):
                angle = math.radians(i * 60)
                for dr in range(lw * 2):
                    rx = (R - lw - dr)
                    d.point(
                        [cx + int(rx * math.cos(angle)),
                         cy + int(rx * math.sin(angle))],
                        fill=(*WHITE, 220),
                    )

            # ── inner glowing ring ────────────────────────────────────────
            Ri = int(R * 0.26)
            d.ellipse([cx-Ri, cy-Ri, cx+Ri, cy+Ri],
                      outline=(*CYAN, 255), width=max(2, lw))

            # ── bright glow soft blur applied before core ─────────────────
            # (draw a slightly larger cyan circle on a separate layer)
            glow_layer = PIL.Image.new("RGBA", (S, S), (0, 0, 0, 0))
            gd = PIL.ImageDraw.Draw(glow_layer)
            Rc = int(R * 0.13)
            gd.ellipse([cx-Rc*2, cy-Rc*2, cx+Rc*2, cy+Rc*2],
                       fill=(*CYAN, 110))
            glow_layer = glow_layer.filter(PIL.ImageFilter.GaussianBlur(S // 14))
            img = PIL.Image.alpha_composite(img, glow_layer)
            d   = PIL.ImageDraw.Draw(img)

            # ── core dot ──────────────────────────────────────────────────
            d.ellipse([cx-Rc, cy-Rc, cx+Rc, cy+Rc], fill=(*WHITE, 255))

            # ── downscale to target size ──────────────────────────────────
            _resample = getattr(getattr(PIL.Image, "Resampling", PIL.Image), "LANCZOS", getattr(PIL.Image, "BICUBIC", 3))
            return img.resize((sz, sz), _resample)

        try:
            sizes  = [256, 128, 64, 48, 32, 16]
            frames = [_render(s) for s in sizes]
            frames[0].save(
                out_path,
                format="ICO",
                append_images=frames[1:],
                sizes=[(s, s) for s in sizes],
            )
            return True
        except Exception as e:
            print(f"[Shortcut] ⚠️  Icon generation failed: {e}")
            return False

    @staticmethod
    def _create_lnk_windows(lnk: str, target: str, args: str,
                             work_dir: str, icon_loc: str) -> None:
        """
        Create a Windows .lnk shortcut WITHOUT launching PowerShell or cmd.
        Tries win32com (pywin32) first; falls back to wscript.exe + VBScript.
        wscript.exe is a GUI-mode host — it never opens a console window.
        """
        # ── Option 1: pywin32 (pure Python COM, zero subprocess) ──────────
        try:
            from win32com.client import Dispatch   # type: ignore
            sh = Dispatch("WScript.Shell")
            sc = sh.CreateShortCut(lnk)
            sc.TargetPath       = target
            sc.Arguments        = f'"{args}"'
            sc.WorkingDirectory = work_dir
            sc.Description      = "CHARLIE AI Assistant"
            sc.IconLocation     = icon_loc
            sc.save()
            return
        except ImportError:
            pass

        # ── Option 2: wscript.exe + VBScript (always available on Windows,
        #    GUI-mode executable — never opens a console window) ────────────
        vbs = "\n".join([
            'Set ws = CreateObject("WScript.Shell")',
            f'Set sc = ws.CreateShortcut("{lnk}")',
            f'sc.TargetPath = "{target}"',
            f'sc.Arguments = Chr(34) & "{args}" & Chr(34)',
            f'sc.WorkingDirectory = "{work_dir}"',
            'sc.Description = "CHARLIE AI Assistant"',
            f'sc.IconLocation = "{icon_loc}"',
            'sc.Save',
        ])
        import tempfile
        fd, tmp = tempfile.mkstemp(suffix=".vbs")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(vbs)
            proc = subprocess.Popen(
                ["wscript.exe", "/nologo", tmp],
                creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW,
            )
            proc.wait(timeout=10)
        finally:
            try:
                os.unlink(tmp)
            except Exception:
                pass

    @staticmethod
    def _get_desktop_dir() -> Path:
        """
        Resolve the user's REAL desktop directory instead of assuming
        ~/Desktop, which breaks when:
          • OneDrive "Known Folder Move" relocates the desktop
            (C:/Users/x/OneDrive/Desktop) — very common on Win 10/11;
          • the XDG desktop is localized on Linux (~/Masaüstü,
            ~/Schreibtisch, ~/Bureau, …).
        Falls back to ~/Desktop only as a last resort.
        """
        home = Path.home()
        _os = platform.system()

        if _os == "Windows":
            # ── 1) SHGetKnownFolderPath(FOLDERID_Desktop) — the canonical
            #       answer; follows OneDrive redirection. No dependencies. ──
            try:
                import ctypes
                from ctypes import wintypes

                class _GUID(ctypes.Structure):
                    _fields_ = [("Data1", wintypes.DWORD),
                                ("Data2", wintypes.WORD),
                                ("Data3", wintypes.WORD),
                                ("Data4", ctypes.c_ubyte * 8)]

                # FOLDERID_Desktop {B4BFCC3A-DB2C-424C-B029-7FE99A87C641}
                fid = _GUID(0xB4BFCC3A, 0xDB2C, 0x424C,
                            (ctypes.c_ubyte * 8)(0xB0, 0x29, 0x7F, 0xE9,
                                                 0x9A, 0x87, 0xC6, 0x41))
                buf = ctypes.c_wchar_p()
                if ctypes.windll.shell32.SHGetKnownFolderPath(
                        ctypes.byref(fid), 0, None, ctypes.byref(buf)) == 0:
                    if buf.value:
                        p = Path(buf.value)
                        ctypes.windll.ole32.CoTaskMemFree(buf)
                        if p.is_dir():
                            return p
                    elif buf:
                        ctypes.windll.ole32.CoTaskMemFree(buf)
            except Exception:
                pass

            # ── 2) Registry: User Shell Folders (may contain %VARS%) ──────
            try:
                import winreg
                with winreg.OpenKey(
                        winreg.HKEY_CURRENT_USER,
                        r"Software\Microsoft\Windows\CurrentVersion"
                        r"\Explorer\User Shell Folders") as key:
                    val, _t = winreg.QueryValueEx(key, "Desktop")
                p = Path(os.path.expandvars(val))
                if p.is_dir():
                    return p
            except Exception:
                pass

        elif _os == "Linux":
            # ── xdg-user-dir honours localized names (~/Masaüstü, …) ──────
            try:
                out = subprocess.run(["xdg-user-dir", "DESKTOP"],
                                     capture_output=True, text=True, timeout=5)
                p = Path(out.stdout.strip())
                if out.stdout.strip() and p != home and p.is_dir():
                    return p
            except Exception:
                pass
            try:
                cfg = home / ".config" / "user-dirs.dirs"
                for line in cfg.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line.startswith("XDG_DESKTOP_DIR"):
                        val = line.split("=", 1)[1].strip().strip('"')
                        p = Path(val.replace("$HOME", str(home)))
                        if p != home and p.is_dir():
                            return p
            except Exception:
                pass

        # macOS: ~/Desktop is always the real path (localization is
        # display-only). Everything else lands here as a last resort.
        return home / "Desktop"

    def _create_desktop_shortcut(self):
        """
        Create a desktop shortcut on Windows / macOS / Linux.
        Never opens a terminal, console, or PowerShell window on any platform.
        """
        import stat as _stat
        script  = Path(__file__).resolve().parent / "main.py"
        python  = Path(sys.executable)
        desktop = self._get_desktop_dir()

        # Arc-reactor icon (.ico — also exported as .png for Linux/macOS)
        ico_path = Path(__file__).resolve().parent / "config" / "charlie.ico"
        if not ico_path.exists():
            self._build_charlie_icon(ico_path)

        try:
            _os = platform.system()

            # ── Windows ───────────────────────────────────────────────────────
            if _os == "Windows":
                pythonw  = python.parent / "pythonw.exe"
                target   = str(pythonw if pythonw.exists() else python)
                lnk      = str(desktop / "CHARLIE.lnk")
                icon_loc = str(ico_path) if ico_path.exists() else f"{target},0"
                self._create_lnk_windows(lnk, target, str(script),
                                         str(script.parent), icon_loc)

            # ── macOS — proper .app bundle (no Terminal window) ───────────────
            elif _os == "Darwin":
                app     = desktop / "CHARLIE.app"
                mac_dir = app / "Contents" / "MacOS"
                res_dir = app / "Contents" / "Resources"
                mac_dir.mkdir(parents=True, exist_ok=True)
                res_dir.mkdir(exist_ok=True)

                # Launcher executable (bash — runs as background process,
                # macOS does NOT open Terminal for executables inside .app bundles)
                launcher = mac_dir / "CHARLIE"
                launcher.write_text(
                    "#!/usr/bin/env bash\n"
                    f'cd "{script.parent}"\n'
                    f'exec "{python}" "{script}"\n'
                )
                launcher.chmod(launcher.stat().st_mode
                               | _stat.S_IEXEC | _stat.S_IXGRP | _stat.S_IXOTH)

                # Minimal Info.plist (required for .app recognition)
                (app / "Contents" / "Info.plist").write_text(
                    '<?xml version="1.0" encoding="UTF-8"?>\n'
                    '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
                    '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
                    '<plist version="1.0"><dict>\n'
                    '  <key>CFBundleExecutable</key><string>CHARLIE</string>\n'
                    '  <key>CFBundleIdentifier</key>'
                    '<string>com.charlie.assistant</string>\n'
                    '  <key>CFBundleName</key><string>CHARLIE</string>\n'
                    '  <key>CFBundlePackageType</key><string>APPL</string>\n'
                    '  <key>CFBundleVersion</key><string>1.0</string>\n'
                    '</dict></plist>\n'
                )

                # Optional: copy icon as .icns (skip silently if Pillow is missing)
                try:
                    import PIL.Image
                    icns = res_dir / "AppIcon.icns"
                    PIL.Image.open(ico_path).save(icns, format="ICNS")
                    # Inject icon reference into plist
                    plist = app / "Contents" / "Info.plist"
                    txt = plist.read_text()
                    plist.write_text(
                        txt.replace(
                            '</dict></plist>',
                            '  <key>CFBundleIconFile</key>'
                            '<string>AppIcon</string>\n</dict></plist>\n',
                        )
                    )
                except Exception:
                    pass  # icon is optional

            # ── Linux — .desktop file (Terminal=false, no console) ────────────
            else:
                # Export .ico → .png for better desktop integration
                png_path = ico_path.with_suffix(".png")
                if not png_path.exists() and ico_path.exists():
                    try:
                        import PIL.Image
                        _resample = getattr(getattr(PIL.Image, "Resampling", PIL.Image), "LANCZOS", getattr(PIL.Image, "BICUBIC", 3))
                        PIL.Image.open(ico_path).resize(
                            (256, 256), _resample
                        ).save(png_path, format="PNG")
                    except Exception:
                        png_path = ico_path  # fallback to .ico

                icon_line = f"Icon={png_path}\n" if png_path.exists() else ""
                desk = desktop / "CHARLIE.desktop"
                desk.write_text(
                    "[Desktop Entry]\n"
                    "Name=CHARLIE\n"
                    f"Exec={python} {script}\n"
                    f"Path={script.parent}\n"
                    "Type=Application\n"
                    "Terminal=false\n"
                    "Categories=Utility;\n"
                    + icon_line
                )
                desk.chmod(desk.stat().st_mode | 0o755)

            self._log.append_log("SYS: Desktop shortcut created.")
        except Exception as e:
            self._log.append_log(f"ERR: Shortcut failed — {e}")

    def _toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def resizeEvent(self, a0):
        super().resizeEvent(a0)
        cw = self.centralWidget()
        if cw is None:
            return
        if self._overlay and self._overlay.isVisible():
            ow, oh = 460, 390
            self._overlay.setGeometry(
                (cw.width()  - ow) // 2,
                (cw.height() - oh) // 2,
                ow, oh,
            )
        if self._remote_overlay and self._remote_overlay.isVisible():
            ow, oh = RemoteKeyOverlay._OW, RemoteKeyOverlay._OH
            self._remote_overlay.setGeometry(
                (cw.width()  - ow) // 2,
                (cw.height() - oh) // 2,
                ow, oh,
            )
        if self._customize_overlay and self._customize_overlay.isVisible():
            ow, oh = CustomizeOverlay._OW, CustomizeOverlay._OH
            self._customize_overlay.setGeometry(
                (cw.width()  - ow) // 2,
                (cw.height() - oh) // 2,
                ow, oh,
            )
        if self._pricing_overlay and self._pricing_overlay.isVisible():
            self._pricing_overlay.setGeometry(0, 0, cw.width(), cw.height())
        if hasattr(self, "_modal_backdrop") and self._modal_backdrop is not None and self._modal_backdrop.isVisible():
            self._modal_backdrop.setGeometry(0, 0, cw.width(), cw.height())
        if getattr(self, "_screen_copilot_overlay", None) is not None and self._screen_copilot_overlay.isVisible():
            ow = max(980, min(1280, cw.width() - 40))
            oh = max(660, min(860, cw.height() - 30))
            self._screen_copilot_overlay.setGeometry(
                max(0, (cw.width() - ow) // 2),
                max(0, (cw.height() - oh) // 2),
                ow, oh,
            )
        if getattr(self, "_mobile_bridge_overlay", None) is not None and self._mobile_bridge_overlay.isVisible():
            ow, oh = MobileBridgeOverlay._OW, min(480, cw.height() - 20)
            self._mobile_bridge_overlay.setGeometry(
                max(0, (cw.width() - ow) // 2),
                max(0, (cw.height() - oh) // 2),
                ow, oh,
            )
        # Camera preview — bottom-right corner of the center/HUD area
        pw = _CameraPreview._W
        ph = self._cam_preview.height() or _CameraPreview._H
        self._cam_preview.setGeometry(
            cw.width() - _RIGHT_W - pw - 12,
            cw.height() - ph - 28,
            pw, ph,
        )
        # Clipboard panel — bottom-center
        if hasattr(self, '_clipboard_panel') and self._clipboard_panel.isVisible():
            self._position_clipboard_panel()
        # Quick drawer — reposition if open
        if getattr(self, '_quick_drawer', None) is not None and self._quick_drawer.isVisible():
            self._position_quick_drawer()
        if hasattr(self, '_intelligence_hub'):
            self._intelligence_hub.setGeometry(0, 0, cw.width(), cw.height())
        if hasattr(self, '_command_bar'):
            self._position_command_bar()

    def _update_metrics(self):
        snap = _metrics.snapshot()

        # CPU
        cpu = snap["cpu"]
        self._bar_cpu.set_value(cpu, f"{cpu:.0f}%")

        # MEM
        mem = snap["mem"]
        self._bar_mem.set_value(mem, f"{mem:.0f}%")

        # NET
        net = snap["net"]
        if net < 1.0:
            net_str = f"{net*1024:.0f}KB/s"
        else:
            net_str = f"{net:.1f}MB/s"
        net_pct = min(100, net * 10)  # 10 MB/s = %100
        self._bar_net.set_value(net_pct, net_str)

        # GPU
        gpu = snap["gpu"]
        if gpu >= 0:
            self._bar_gpu.set_value(gpu, f"{gpu:.0f}%")
        else:
            self._bar_gpu.set_value(0, "N/A")

        # TMP
        tmp = snap["tmp"]
        if tmp >= 0:
            tmp_pct = min(100, (tmp / 100) * 100)
            self._bar_tmp.set_value(tmp_pct, f"{tmp:.0f}°C")
        else:
            self._bar_tmp.set_value(0, "N/A")

        try:
            boot_t  = psutil.boot_time()
            elapsed = time.time() - boot_t
            h = int(elapsed // 3600)
            m = int((elapsed % 3600) // 60)
            self._uptime_lbl.setText(f"UP  {h:02d}:{m:02d}")
        except Exception:
            self._uptime_lbl.setText("UP  --:--")

        try:
            proc_count = len(psutil.pids())
            self._proc_lbl.setText(f"PROC  {proc_count}")
        except Exception:
            self._proc_lbl.setText("PROC  --")


    def _build_header(self) -> QWidget:
        w = QWidget()
        w.setObjectName("AppHeader")
        w.setFixedHeight(56)
        w.setStyleSheet(f"""
            QWidget#AppHeader {{
                background: {C.BG};
                border-bottom: 1px solid rgba(255, 255, 255, 0.06);
            }}
        """)
        lay = QHBoxLayout(w)
        lay.setContentsMargins(16, 0, 16, 0)
        lay.setSpacing(12)

        # ── App Brand: Logo badge + Charlie title ──
        self._brand_box = QFrame()
        self._brand_box.setStyleSheet("background: transparent; border: none;")
        bb_lay = QHBoxLayout(self._brand_box)
        bb_lay.setContentsMargins(2, 0, 8, 0)
        bb_lay.setSpacing(10)

        self._c_logo_badge = QLabel()
        self._c_logo_badge.setFixedSize(26, 26)
        self._c_logo_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._c_logo_badge.setPixmap(_render_hub_svg("brand_c", 26, "#ffffff"))
        self._c_logo_badge.setStyleSheet("background: transparent; border: none;")
        self._c_logo_badge.setCursor(Qt.CursorShape.PointingHandCursor)
        self._c_logo_badge.setToolTip("Customize UI Theme, Contrast & Logo (Theme Studio)")
        self._c_logo_badge.mousePressEvent = lambda ev: self._open_theme_studio()
        bb_lay.addWidget(self._c_logo_badge)

        display_name = (self._assistant_name or "Charlie").title()
        self._brand_title_lbl = QLabel(display_name)
        self._brand_title_lbl.setFont(QFont(APP_FONT_NAME, 13, QFont.Weight.DemiBold))
        self._brand_title_lbl.setStyleSheet("""
            QLabel {
                color: #ffffff;
                font-size: 15px;
                font-weight: 600;
                letter-spacing: 0.2px;
                background: transparent;
                border: none;
            }
        """)
        self._brand_title_lbl.setCursor(Qt.CursorShape.PointingHandCursor)
        self._brand_title_lbl.setToolTip("Charlie AI Desktop Assistant")
        self._brand_title_lbl.mousePressEvent = lambda ev: self._open_theme_studio()
        bb_lay.addWidget(self._brand_title_lbl)

        self._ai_brand_badge = None

        lay.addWidget(self._brand_box)
        lay.addSpacing(10)

        # ── Search Bar: sleek, polished ──
        search_box = QFrame()
        search_box.setFixedSize(320, 34)
        search_box.setStyleSheet(f"""
            QFrame {{
                background: rgba(255, 255, 255, 0.035);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 17px;
            }}
            QFrame:hover {{
                border-color: rgba(99, 102, 241, 0.45);
                background: rgba(255, 255, 255, 0.055);
            }}
        """)
        sb_lay = QHBoxLayout(search_box)
        sb_lay.setContentsMargins(12, 0, 10, 0)
        sb_lay.setSpacing(8)

        s_icon = QLabel()
        s_icon.setPixmap(_render_hub_svg("search", 14, "#94a3b8"))
        s_icon.setStyleSheet("background: transparent; border: none;")
        sb_lay.addWidget(s_icon)

        self._hdr_search_input = QLineEdit()
        self._hdr_search_input.setPlaceholderText("Search commands or ask anything...")
        self._hdr_search_input.setFont(QFont(APP_FONT_NAME, 9))
        self._hdr_search_input.setStyleSheet("background: transparent; color: #f1f5f9; border: none; padding: 0;")
        self._hdr_search_input.returnPressed.connect(self._show_universal_command_bar)
        sb_lay.addWidget(self._hdr_search_input, 1)

        k_badge = QLabel("Ctrl K" if _OS == "Windows" else "⌘K")
        k_badge.setFont(QFont(APP_FONT_NAME, 8, QFont.Weight.DemiBold))
        k_badge.setStyleSheet("""
            color: #94a3b8;
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 4px;
            padding: 1px 6px;
        """)
        sb_lay.addWidget(k_badge)
        lay.addWidget(search_box)

        lay.addStretch()

        # ── Right: Online Status, Notification, Letter Avatar Button ──
        # Refined online pill
        self._online_pill = QFrame()
        self._online_pill.setFixedHeight(30)
        self._online_pill.setStyleSheet("""
            QFrame {
                background: rgba(16, 185, 129, 0.08);
                border: 1px solid rgba(16, 185, 129, 0.22);
                border-radius: 15px;
            }
            QFrame:hover {
                background: rgba(16, 185, 129, 0.12);
                border-color: rgba(16, 185, 129, 0.35);
            }
        """)
        op_lay = QHBoxLayout(self._online_pill)
        op_lay.setContentsMargins(10, 0, 12, 0)
        op_lay.setSpacing(6)
        op_dot = QLabel("●")
        op_dot.setStyleSheet(f"color: {C.GREEN}; font-size: 8px; background: transparent; border: none;")
        op_lay.addWidget(op_dot)
        op_txt = QLabel(f"{self._assistant_name.capitalize()} is online")
        op_txt.setFont(QFont(APP_FONT_NAME, 8, QFont.Weight.DemiBold))
        op_txt.setStyleSheet("color: #6ee7b7; background: transparent; border: none;")
        op_lay.addWidget(op_txt)
        lay.addWidget(self._online_pill)
        lay.addSpacing(4)

        # ── Unified Model Selector Dropdown: Model: Cloud AI ▾ ──
        from memory.config_manager import load_api_keys
        _cfg = load_api_keys()
        _is_local = "ollama" in str(_cfg.get("llm_provider", "")).lower()

        self._model_selector_btn = QPushButton()
        self._model_selector_btn.setFixedHeight(30)
        self._model_selector_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._model_selector_btn.setFont(QFont(APP_FONT_NAME, 8, QFont.Weight.DemiBold))
        self._model_selector_btn.setStyleSheet("""
            QPushButton {
                background: #111827;
                color: #f7f9fc;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 15px;
                padding: 0 12px;
            }
            QPushButton:hover {
                background: #1a2234;
                border-color: rgba(108, 99, 255, 0.4);
            }
            QPushButton::menu-indicator { image: none; width: 0px; }
        """)

        model_menu = QMenu(self._model_selector_btn)
        model_menu.setStyleSheet("""
            QMenu {
                background: #0d1220;
                color: #f7f9fc;
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 8px;
                padding: 4px;
            }
            QMenu::item {
                padding: 6px 16px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background: rgba(108, 99, 255, 0.2);
                color: #ffffff;
            }
        """)
        act_cloud = model_menu.addAction("Cloud AI")
        act_cloud.triggered.connect(lambda: self._set_ai_engine("gemini"))
        act_local = model_menu.addAction("Local AI — Ollama")
        act_local.triggered.connect(lambda: self._set_ai_engine("ollama"))
        self._model_selector_btn.setMenu(model_menu)

        # Retain hidden legacy attributes for backward compatibility
        self._cloud_ai_btn = QPushButton()
        self._cloud_ai_btn.hide()
        self._local_ai_btn = QPushButton()
        self._local_ai_btn.hide()
        self._engine_btn = self._model_selector_btn

        self._update_ai_engine_buttons(_is_local)
        lay.addWidget(self._model_selector_btn)
        lay.addSpacing(6)

        # Notification Bell
        bell_btn = QPushButton()
        bell_btn.setIcon(_render_svg_icon("bell", 15, "#cbd5e1"))
        bell_btn.setIconSize(QSize(15, 15))
        bell_btn.setFixedSize(34, 34)
        bell_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        bell_btn.setToolTip("Notifications & System Info")
        bell_btn.setStyleSheet(f"""
            QPushButton {{
                background: rgba(255, 255, 255, 0.035);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 17px;
            }}
            QPushButton:hover {{
                background: rgba(255, 255, 255, 0.08);
                border-color: rgba(255, 255, 255, 0.18);
            }}
            QPushButton:pressed {{
                background: rgba(255, 255, 255, 0.12);
            }}
        """)
        bell_btn.clicked.connect(self._open_about_panel)
        lay.addWidget(bell_btn)
        lay.addSpacing(4)

        # Mini HUD Floating Overlay Button
        self._mini_hud_btn = QPushButton("🗗")
        self._mini_hud_btn.setFixedSize(34, 34)
        self._mini_hud_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._mini_hud_btn.setFont(QFont(APP_FONT_NAME, 11, QFont.Weight.Bold))
        self._mini_hud_btn.setToolTip("Switch to Mini HUD Floating Overlay (Ctrl+M)")
        self._mini_hud_btn.setStyleSheet("""
            QPushButton {
                background: rgba(0, 229, 255, 0.08);
                color: #00e5ff;
                border: 1px solid rgba(0, 229, 255, 0.25);
                border-radius: 17px;
            }
            QPushButton:hover {
                background: rgba(0, 229, 255, 0.20);
                border-color: rgba(0, 229, 255, 0.60);
                color: #ffffff;
            }
            QPushButton:pressed {
                background: rgba(0, 229, 255, 0.30);
            }
        """)
        self._mini_hud_btn.clicked.connect(self.show_mini_hud)
        lay.addWidget(self._mini_hud_btn)
        lay.addSpacing(4)

        # Right Corner Profile Button: Clean Letter Circle
        initial_letter = "C"
        try:
            from memory.config_manager import get_user_name
            uname = get_user_name().strip()
            if uname and uname.upper() not in ("JARVIS", "J.A.R.V.I.S.", "J.A.R.V.I.S"):
                initial_letter = uname[0].upper()
            else:
                engine = self._get_commercial_engine()
                if engine:
                    acc = engine.get_account()
                    display = acc.display_name or acc.email or ""
                    clean_disp = display.strip()
                    if clean_disp and not clean_disp.lower().startswith("jarvis"):
                        initial_letter = clean_disp[0].upper()
        except Exception:
            pass

        self._profile_avatar_btn = QPushButton(initial_letter)
        self._profile_avatar_btn.setFixedSize(34, 34)
        self._profile_avatar_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._profile_avatar_btn.setToolTip("User Profile & Subscription")
        self._profile_avatar_btn.setFont(QFont(APP_FONT_NAME, 11, QFont.Weight.Bold))
        self._profile_avatar_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #6366f1, stop:1 #8b5cf6);
                color: #ffffff;
                border: 1.5px solid rgba(255, 255, 255, 0.22);
                border-radius: 17px;
                font-weight: 800;
                text-align: center;
                padding-bottom: 1px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #7579ff, stop:1 #9d71ff);
                border-color: #c7d2fe;
            }
            QPushButton:pressed {
                background: #4f46e5;
                border-color: #818cf8;
            }
        """)
        self._profile_avatar_btn.clicked.connect(self._open_profile_panel)
        lay.addWidget(self._profile_avatar_btn)

        # ── Retain legacy attributes so background timers and methods work without error ──
        self._drawer_btn = QPushButton()
        self._drawer_btn.hide()
        self._hub_btn = QPushButton()
        self._hub_btn.hide()
        self._title_lbl = QLabel(f"◈  {self._assistant_name.upper()}  ◈")
        self._title_lbl.hide()
        self._sub_lbl = QLabel("AUTONOMOUS AI ASSISTANT")
        self._sub_lbl.hide()
        self._state_lbl = QLabel("READY")
        self._state_lbl.hide()
        self._plan_header_btn = QPushButton("Plan: Pro")
        self._plan_header_btn.hide()
        self._clock_lbl = QLabel("00:00:00")
        self._clock_lbl.hide()
        self._date_lbl = QLabel("")
        self._date_lbl.hide()

        self._refresh_subscription_ui()
        return w

    def _init_weather_service(self):
        """Start real-time temperature and location telemetry worker and periodic timer."""
        self._refresh_live_weather(force=False)
        self._weather_tmr = QTimer(self)
        self._weather_tmr.setInterval(900000)  # Refresh every 15 minutes
        self._weather_tmr.timeout.connect(lambda: self._refresh_live_weather(force=False))
        self._weather_tmr.start()

    def _refresh_live_weather(self, force: bool = False):
        """Asynchronously capture location and weather in background thread."""
        if hasattr(self, "_weather_temp_lbl") and force:
            self._weather_temp_lbl.setText("Updating...")

        def _worker():
            try:
                from core.weather_service import get_realtime_weather
                result = get_realtime_weather(force_refresh=force)
                self._weather_sig.emit(result)
            except Exception as e:
                logger.debug("Weather telemetry background fetch error: %s", e)

        try:
            from engine.threadpool import submit_task, TaskPriority
            submit_task(_worker, priority=TaskPriority.LOW)
        except Exception:
            t = threading.Thread(target=_worker, daemon=True)
            t.start()

    def _apply_weather_telemetry(self, data: dict):
        """Thread-safe UI update for real-time weather and location telemetry."""
        if not data or not isinstance(data, dict):
            return
        temp_str = data.get("display_text") or f"{data.get('temp_c', '--')}°C · {data.get('condition', 'Live')}"
        loc_str = data.get("location_text") or data.get("city") or "Local"
        icon_key = data.get("icon_key", "weather_sun_cloud")
        icon_color = data.get("icon_color", "#fbbf24")

        if hasattr(self, "_weather_temp_lbl"):
            self._weather_temp_lbl.setText(temp_str)
        if hasattr(self, "_weather_loc_lbl"):
            self._weather_loc_lbl.setText(loc_str)
        if hasattr(self, "_weather_icon_lbl"):
            self._weather_icon_lbl.setPixmap(_render_hub_svg(icon_key, 20, icon_color))
        if hasattr(self, "_weather_widget"):
            humidity = data.get("humidity", 0)
            app_temp = data.get("apparent_temp_c", data.get("temp_c", "--"))
            tooltip = (
                f"Live Telemetry:\n"
                f"• Temperature: {data.get('temp_str')}\n"
                f"• Condition: {data.get('condition')}\n"
                f"• Feels like: {app_temp}°C\n"
                f"• Location: {loc_str}\n"
                f"• Humidity: {humidity}%\n"
                f"(Click to refresh now)"
            )
            self._weather_widget.setToolTip(tooltip)

    def _tick_clock(self):
        self._clock_lbl.setText(time.strftime("%H:%M:%S"))
        self._date_lbl.setText(time.strftime("%a %d %b %Y"))
        if hasattr(self, "_center_time_lbl"):
            self._center_time_lbl.setText(time.strftime("%I:%M %p"))
        if hasattr(self, "_center_date_lbl"):
            self._center_date_lbl.setText(time.strftime("%a, %b %d, %Y"))
        self._tick_starter_countdown()

    def _tick_starter_countdown(self):
        """Tick down the 10-minute daily allowance second-by-second while app is open."""
        try:
            engine = self._get_commercial_engine()
            if engine is None:
                return
            account = engine.get_account()
            from engine.commercial.models import PlanTier
            if account.plan != PlanTier.STARTER:
                if getattr(self, "_starter_exhausted_locked", False):
                    self._starter_exhausted_locked = False
                    if hasattr(self, "_input"):
                        self._input.setEnabled(True)
                        self._input.setPlaceholderText("Ask anything or give a task…")
                    self._style_mute_btn()
                    self._refresh_subscription_ui()
                return

            rem_sec, is_exhausted = engine.usage_meter.tick_second(1.0)
            rem_sec = max(0, int(rem_sec))
            m = rem_sec // 60
            s = rem_sec % 60
            time_str = f"{m:02d}:{s:02d}"

            if hasattr(self, "_plan_header_btn"):
                if not is_exhausted and rem_sec > 0:
                    self._plan_header_btn.setText(f"Starter · {time_str} left")
                    if rem_sec > 180:
                        txt_col = "#fbbf24"
                        bg_col = "#1f1d17"
                        border_col = "#d97706"
                    elif rem_sec > 60:
                        txt_col = "#fb923c"
                        bg_col = "#271c19"
                        border_col = "#ea580c"
                    else:
                        txt_col = "#f87171"
                        bg_col = "#2b1419"
                        border_col = "#dc2626"
                    self._plan_header_btn.setStyleSheet(f"""
                        QPushButton {{
                            background: {bg_col}; color: {txt_col};
                            border: 1px solid {border_col}; border-radius: 12px;
                            padding: 0 12px; font-weight: 700; font-size: 11px;
                        }}
                        QPushButton:hover {{
                            background: {txt_col}; color: #0f172a;
                            border-color: #ffffff;
                        }}
                    """)
                else:
                    self._plan_header_btn.setText("🔒 Starter · 00:00 EXPIRED")
                    self._plan_header_btn.setStyleSheet("""
                        QPushButton {
                            background: #3b1820; color: #f87171;
                            border: 1px solid #ef4444; border-radius: 12px;
                            padding: 0 12px; font-weight: 800; font-size: 11px;
                        }
                        QPushButton:hover {
                            background: #ef4444; color: #ffffff;
                        }
                    """)

            if hasattr(self, "_subscription_btn"):
                if not is_exhausted and rem_sec > 0:
                    self._subscription_btn.setText(f"Current plan: Starter — {time_str} left today")
                else:
                    self._subscription_btn.setText("Current plan: Starter — 10 min expired")

            if is_exhausted or rem_sec <= 0:
                if not getattr(self, "_starter_exhausted_locked", False):
                    self._starter_exhausted_locked = True
                    self._handle_starter_lockout()
        except Exception as exc:
            print(f"[Commercial] Starter countdown tick error: {exc}")

    def _handle_starter_lockout(self):
        """Enforces full lockout when Starter 10 minutes run out."""
        try:
            self._do_interrupt()
            self._muted = True
            self.hud.muted = True
            if hasattr(self, "_mute_btn"):
                self._mute_btn.setText("🔒  MIC LOCKED · TIME EXPIRED")
                self._mute_btn.setStyleSheet("""
                    QPushButton {
                        background: #2b1419; color: #f87171;
                        border: 1px solid #ef4444; border-radius: 8px;
                        font-weight: bold;
                    }
                """)
            if hasattr(self, "_input"):
                self._input.setEnabled(False)
                self._input.setPlaceholderText("🔒 10 min daily time expired — Subscribe to unlock CHARLIE")
            if hasattr(self, "_state_lbl"):
                self._state_lbl.setText("Time Expired")
                self._state_lbl.setStyleSheet(
                    "color: #f87171; background: #2b1419; border-radius: 8px; padding: 2px 8px;"
                )
            self._log.append_log("SYS: ⚠️ Daily 10-minute free Starter allowance exhausted.")
            self._log.append_log("SYS: Assistant actions are locked. Please purchase a subscription plan to continue.")
            self._show_pricing_overlay(forced_paywall=True)
        except Exception as e:
            print(f"[Commercial] Lockout enforcement failed: {e}")

    def _build_left_panel(self) -> QWidget:
        w = QWidget()
        w.setFixedWidth(_LEFT_W)
        w.setStyleSheet(f"""
            QWidget {{
                background: {C.PANEL};
                border-right: 1px solid rgba(255, 255, 255, 0.05);
            }}
        """)
        lay = QVBoxLayout(w)
        lay.setContentsMargins(14, 16, 14, 14)
        lay.setSpacing(6)

        # ── Sidebar Brand Header ──
        brand_row = QHBoxLayout()
        brand_row.setContentsMargins(0, 0, 0, 10)
        brand_row.setSpacing(10)

        self._sidebar_brand_icon = QLabel()
        self._sidebar_brand_icon.setFixedSize(36, 36)
        self._sidebar_brand_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._sidebar_brand_icon.setPixmap(_render_hub_svg("brand_c", 36, "#ffffff"))
        self._sidebar_brand_icon.setStyleSheet("background: transparent; border: none;")
        brand_row.addWidget(self._sidebar_brand_icon)

        brand_text_v = QVBoxLayout()
        brand_text_v.setSpacing(1)
        brand_title = QLabel("Charlie")
        brand_title.setFont(QFont(APP_FONT_NAME, 11, QFont.Weight.Bold))
        brand_title.setStyleSheet("color: #ffffff; background: transparent; border: none; letter-spacing: 0.3px;")
        brand_sub = QLabel("AI Desktop Suite")
        brand_sub.setFont(QFont(APP_FONT_NAME, 7, QFont.Weight.Medium))
        brand_sub.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent; border: none;")
        brand_text_v.addWidget(brand_title)
        brand_text_v.addWidget(brand_sub)
        brand_row.addLayout(brand_text_v)
        brand_row.addStretch()

        lay.addLayout(brand_row)

        # ── Navigation Items ──
        self._nav_buttons = []
        nav_defs = [
            ("Home", "nav_home", self._nav_click_home),
            ("Chat", "nav_chat", self._nav_click_chat),
            ("Voice", "nav_voice", self._toggle_mute),
            ("Avatar", "nav_avatar", self._nav_click_avatar),
            ("Docs", "chip_doc", lambda: self._use_chip_prompt("Help me review documents and notes: ")),
            ("OCR Scan", "nav_screen", self._open_screen_copilot),
            ("Brain", "nav_brain", lambda: self._use_chip_prompt("Search my personal memory and knowledge: ")),
            ("Settings", "nav_settings", self._open_settings_drawer),
        ]

        active_idx = 0
        for i, (name, svg_key, callback) in enumerate(nav_defs):
            btn = QPushButton(f"  {name}")
            btn.setFixedHeight(36)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            is_active = (i == active_idx)
            icon_col = "#ffffff" if is_active else "#94a3b8"
            btn.setIcon(_render_svg_icon(svg_key, 16, icon_col))
            btn.setFont(QFont(APP_FONT_NAME, 9, QFont.Weight.DemiBold if is_active else QFont.Weight.Medium))
            if is_active:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background: rgba(99, 102, 241, 0.18);
                        color: #ffffff;
                        border: 1px solid rgba(99, 102, 241, 0.45);
                        border-radius: 10px;
                        text-align: left;
                        padding-left: 14px;
                    }}
                """)
            else:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background: transparent;
                        color: {C.TEXT_MED};
                        border: 1px solid transparent;
                        border-radius: 10px;
                        text-align: left;
                        padding-left: 12px;
                    }}
                    QPushButton:hover {{
                        background: rgba(99, 102, 241, 0.08);
                        color: #e2e8f0;
                        border-color: rgba(99, 102, 241, 0.20);
                    }}
                """)
            btn.clicked.connect(callback)
            lay.addWidget(btn)
            self._nav_buttons.append(btn)

        lay.addStretch()
        lay.addSpacing(6)

        # ── Sleek Charlie Pro Upgrade Card ──
        upgrade_card = QPushButton()
        upgrade_card.setObjectName("UpgradeProBtn")
        upgrade_card.setFixedHeight(62)
        upgrade_card.setCursor(Qt.CursorShape.PointingHandCursor)
        upgrade_card.setStyleSheet("""
            QPushButton#UpgradeProBtn {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 rgba(245, 158, 11, 0.10), stop:0.45 rgba(22, 19, 34, 0.90), stop:1 rgba(13, 16, 26, 0.95));
                border: 1px solid rgba(245, 158, 11, 0.28);
                border-radius: 12px;
                text-align: left;
                padding: 0px;
                margin: 0px;
            }
            QPushButton#UpgradeProBtn:hover {
                border: 1px solid rgba(251, 191, 36, 0.60);
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 rgba(245, 158, 11, 0.18), stop:0.45 rgba(32, 27, 48, 0.95), stop:1 rgba(18, 22, 36, 0.98));
            }
            QPushButton#UpgradeProBtn:pressed {
                background: rgba(13, 16, 26, 0.98);
                border-color: #d97706;
            }
        """)
        uc_lay = QVBoxLayout(upgrade_card)
        uc_lay.setContentsMargins(10, 8, 10, 8)
        uc_lay.setSpacing(3)

        uc_top = QHBoxLayout()
        uc_top.setContentsMargins(0, 0, 0, 0)
        uc_top.setSpacing(8)

        crown_badge = QLabel()
        crown_badge.setFixedSize(26, 26)
        crown_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        crown_badge.setStyleSheet("""
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 rgba(251, 191, 36, 0.22), stop:1 rgba(217, 119, 6, 0.08));
            border: 1px solid rgba(251, 191, 36, 0.35);
            border-radius: 7px;
            padding: 0px;
        """)
        crown_badge.setPixmap(_render_hub_svg("crown", 15, "#fbbf24"))
        crown_badge.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        uc_top.addWidget(crown_badge)

        uc_title = QLabel("Charlie Pro")
        uc_title.setFont(QFont(APP_FONT_NAME, 9, QFont.Weight.Bold))
        uc_title.setStyleSheet("color: #ffffff; background: transparent; border: none; padding: 0px; letter-spacing: 0.2px;")
        uc_title.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        uc_top.addWidget(uc_title)

        uc_top.addStretch()

        pro_badge = QLabel("PRO")
        pro_badge.setFont(QFont(APP_FONT_NAME, 7, QFont.Weight.ExtraBold))
        pro_badge.setStyleSheet("""
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #f59e0b, stop:1 #d97706);
            color: #0c0a09;
            border: none;
            border-radius: 4px;
            padding: 1px 5px;
            font-weight: 900;
            letter-spacing: 0.5px;
        """)
        pro_badge.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        uc_top.addWidget(pro_badge)

        uc_arrow = QLabel("›")
        uc_arrow.setFont(QFont(APP_FONT_NAME, 11, QFont.Weight.Bold))
        uc_arrow.setStyleSheet("color: rgba(251, 191, 36, 0.75); background: transparent; border: none; padding: 0px 0px 1px 1px;")
        uc_arrow.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        uc_top.addWidget(uc_arrow)

        uc_lay.addLayout(uc_top)

        uc_desc = QLabel("Unlock all AI models & avatar")
        uc_desc.setFont(QFont(APP_FONT_NAME, 7))
        uc_desc.setStyleSheet("color: #94a3b8; background: transparent; border: none; padding: 0px;")
        uc_desc.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        uc_lay.addWidget(uc_desc)

        upgrade_card.clicked.connect(self._show_pricing_overlay)
        lay.addWidget(upgrade_card)

        lay.addSpacing(8)

        # ── Modern Daily Usage Card ──
        usage_card = QFrame()
        usage_card.setObjectName("DailyUsageCard")
        usage_card.setFixedHeight(64)
        usage_card.setStyleSheet(f"""
            QFrame#DailyUsageCard {{
                background: {C.PANEL2};
                border: 1px solid {C.BORDER};
                border-radius: 12px;
            }}
            QFrame#DailyUsageCard:hover {{
                border-color: rgba(99, 102, 241, 0.45);
                background: {C.PANEL2};
            }}
        """)
        u_lay = QVBoxLayout(usage_card)
        u_lay.setContentsMargins(11, 8, 11, 8)
        u_lay.setSpacing(6)

        u_row = QHBoxLayout()
        u_row.setContentsMargins(0, 0, 0, 0)
        u_row.setSpacing(4)
        u_lbl = QLabel("Daily Usage")
        u_lbl.setFont(QFont(APP_FONT_NAME, 8, QFont.Weight.DemiBold))
        u_lbl.setStyleSheet("color: #e2e8f0; background: transparent; border: none; padding: 0px; margin: 0px;")
        u_row.addWidget(u_lbl)
        u_row.addStretch()
        u_pct = QLabel("47%")
        u_pct.setFont(QFont(APP_FONT_NAME, 8, QFont.Weight.Bold))
        u_pct.setStyleSheet("color: #a5b4fc; background: transparent; border: none; padding: 0px; margin: 0px;")
        u_row.addWidget(u_pct)
        u_lay.addLayout(u_row)

        u_bar = QProgressBar()
        u_bar.setFixedHeight(5)
        u_bar.setTextVisible(False)
        u_bar.setRange(0, 100)
        u_bar.setValue(47)
        u_bar.setStyleSheet("""
            QProgressBar {
                background: rgba(255, 255, 255, 0.08);
                border: none;
                border-radius: 2.5px;
                padding: 0px;
                margin: 0px;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #6366f1, stop:0.6 #818cf8, stop:1 #c084fc);
                border-radius: 2.5px;
            }
        """)
        u_lay.addWidget(u_bar)

        u_bot = QHBoxLayout()
        u_bot.setContentsMargins(0, 0, 0, 0)
        u_plan = QLabel("Pro Plan • Resets at 00:00")
        u_plan.setFont(QFont(APP_FONT_NAME, 7, QFont.Weight.Medium))
        u_plan.setStyleSheet("color: #64748b; background: transparent; border: none; padding: 0px; margin: 0px;")
        u_bot.addWidget(u_plan)
        u_bot.addStretch()
        u_lay.addLayout(u_bot)
        lay.addWidget(usage_card)

        # ── Retain legacy attributes so metric timers and background updates do not crash ──
        self._bar_cpu = MetricBar("CPU", C.PRI); self._bar_cpu.hide()
        self._bar_mem = MetricBar("MEM", C.ACC2); self._bar_mem.hide()
        self._bar_net = MetricBar("NET", C.GREEN); self._bar_net.hide()
        self._bar_gpu = MetricBar("GPU", C.ACC); self._bar_gpu.hide()
        self._bar_tmp = MetricBar("TMP", "#ff6688"); self._bar_tmp.hide()
        self._uptime_lbl = QLabel("UP  --:--"); self._uptime_lbl.hide()
        self._proc_lbl = QLabel("PROC  --"); self._proc_lbl.hide()
        self._side_sub_btn = QPushButton("★ SUBSCRIPTION"); self._side_sub_btn.hide()

        return w
    def _use_chip_prompt(self, prompt: str):
        if hasattr(self, "_welcome_widget") and self._welcome_widget.isVisible():
            self._welcome_widget.hide()
            self._log.show()
        if hasattr(self, "_input"):
            self._input.setText(prompt)
            self._input.setFocus()
            if not prompt.endswith(": "):
                self._send()

    def _clear_conversation_view(self):
        self._log.clear()
        if hasattr(self, "_welcome_widget"):
            self._welcome_widget.show()
            self._log.hide()

    def _choose_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open Document or Image", str(Path.home()))
        if path:
            self._on_file_selected(path)

    def _build_chat_header(self) -> QWidget:
        w = QFrame()
        w.setObjectName("ChatHeaderFrame")
        w.setStyleSheet(f"""
            QFrame#ChatHeaderFrame {{
                background: {C.PANEL2};
                border: 1px solid rgba(99, 102, 241, 0.25);
                border-radius: 12px;
            }}
        """)
        h_lay = QHBoxLayout(w)
        h_lay.setContentsMargins(14, 10, 14, 10)
        h_lay.setSpacing(12)

        self._chat_icon_box = QLabel()
        self._chat_icon_box.setFixedSize(36, 36)
        self._chat_icon_box.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._chat_icon_box.setStyleSheet("background: transparent; border: none;")
        self._chat_icon_box.setPixmap(_render_hub_svg("brand_c", 28, "#ffffff"))
        self._chat_icon_box.setCursor(Qt.CursorShape.PointingHandCursor)
        self._chat_icon_box.setToolTip("Customize UI Theme, Contrast & Logo (Theme Studio)")
        self._chat_icon_box.mousePressEvent = lambda ev: self._open_theme_studio()
        h_lay.addWidget(self._chat_icon_box)

        title_v = QVBoxLayout()
        title_v.setSpacing(2)

        title_top = QHBoxLayout()
        title_top.setSpacing(8)
        t_lbl = QLabel(f"{self._assistant_name.capitalize()} AI Chat")
        t_lbl.setFont(QFont(APP_FONT_NAME, 11, QFont.Weight.Bold))
        t_lbl.setStyleSheet("color: #ffffff; background: transparent; letter-spacing: 0.3px;")
        title_top.addWidget(t_lbl)

        status_pill = QLabel("● ONLINE")
        status_pill.setFont(QFont(APP_FONT_NAME, 7, QFont.Weight.Bold))
        status_pill.setStyleSheet("""
            color: #34d399;
            background: rgba(52, 211, 153, 0.12);
            border: 1px solid rgba(52, 211, 153, 0.35);
            border-radius: 6px;
            padding: 2px 8px;
        """)
        title_top.addWidget(status_pill)

        engine_pill = QLabel("PRO CHAT STUDIO")
        engine_pill.setFont(QFont(APP_FONT_NAME, 7, QFont.Weight.Bold))
        engine_pill.setStyleSheet("""
            color: #a5b4fc;
            background: rgba(99, 102, 241, 0.12);
            border: 1px solid rgba(129, 140, 248, 0.35);
            border-radius: 6px;
            padding: 2px 8px;
        """)
        title_top.addWidget(engine_pill)
        title_top.addStretch()
        title_v.addLayout(title_top)

        sub_lbl = QLabel("Interactive reasoning · Multimodal vision · Deep research · Code generation")
        sub_lbl.setFont(QFont(APP_FONT_NAME, 8))
        sub_lbl.setStyleSheet("color: #94a3b8; background: transparent;")
        title_v.addWidget(sub_lbl)
        h_lay.addLayout(title_v)

        h_lay.addStretch()

        new_btn = QPushButton("  New Chat")
        new_btn.setIcon(_render_svg_icon("rag_folder_plus", 13, "#ffffff"))
        new_btn.setIconSize(QSize(13, 13))
        new_btn.setFixedHeight(30)
        new_btn.setFont(QFont(APP_FONT_NAME, 8, QFont.Weight.DemiBold))
        new_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        new_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #4f46e5, stop:1 #6366f1);
                color: #ffffff;
                border: 1px solid rgba(165, 180, 252, 0.35);
                border-radius: 8px;
                padding: 0 12px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #4338ca, stop:1 #4f46e5);
            }
        """)
        new_btn.clicked.connect(self._start_new_chat)
        h_lay.addWidget(new_btn)

        clear_btn = QPushButton("  Clear")
        clear_btn.setIcon(_render_svg_icon("rag_trash", 12, "#cbd5e1"))
        clear_btn.setIconSize(QSize(12, 12))
        clear_btn.setFixedHeight(30)
        clear_btn.setFont(QFont(APP_FONT_NAME, 8))
        clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        clear_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.05);
                color: #cbd5e1;
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 8px;
                padding: 0 10px;
            }
            QPushButton:hover {
                background: rgba(239, 68, 68, 0.18);
                color: #f87171;
                border-color: rgba(239, 68, 68, 0.35);
            }
        """)
        clear_btn.clicked.connect(self._clear_conversation_view)
        h_lay.addWidget(clear_btn)

        exit_btn = QPushButton("  3D Mode")
        exit_btn.setIcon(_render_svg_icon("nav_avatar", 13, "#c7d2fe"))
        exit_btn.setIconSize(QSize(13, 13))
        exit_btn.setFixedHeight(30)
        exit_btn.setFont(QFont(APP_FONT_NAME, 8, QFont.Weight.Medium))
        exit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        exit_btn.setToolTip("Return to 3D Avatar & Voice Mode")
        exit_btn.setStyleSheet("""
            QPushButton {
                background: rgba(99, 102, 241, 0.08);
                color: #cbd5e1;
                border: 1px solid rgba(99, 102, 241, 0.25);
                border-radius: 8px;
                padding: 0 12px;
            }
            QPushButton:hover {
                background: rgba(99, 102, 241, 0.25);
                color: #ffffff;
                border-color: rgba(129, 140, 248, 0.5);
            }
        """)
        exit_btn.clicked.connect(lambda: self._set_chat_mode(False))
        h_lay.addWidget(exit_btn)

        return w

    def _build_center_area(self) -> QWidget:
        w = QWidget()
        w.setObjectName("CenterArea")
        w.setStyleSheet("""
            QWidget#CenterArea {
                background: transparent;
            }
        """)
        lay = QVBoxLayout(w)
        lay.setContentsMargins(6, 4, 6, 6)
        lay.setSpacing(12)

        # ── 1. Greeting & Date/Weather Header (Home Mode) ──
        self._center_greet_widget = QWidget()
        greet_lay = QVBoxLayout(self._center_greet_widget)
        greet_lay.setContentsMargins(0, 0, 0, 0)
        greet_lay.setSpacing(0)

        greet_row = QHBoxLayout()
        greet_col = QVBoxLayout()
        greet_col.setSpacing(3)

        hour = time.localtime().tm_hour
        part = "morning" if hour < 12 else ("afternoon" if hour < 18 else "evening")
        _cfg_now = _read_full_config()
        disp_name = (_cfg_now.get("user_name") or _cfg_now.get("user_display_name") or "there").strip().split()[0].capitalize()
        self._center_greet_lbl = QLabel()
        self._center_greet_lbl.setTextFormat(Qt.TextFormat.RichText)
        self._center_greet_lbl.setText(f"Good {part}, <span style='color: #818cf8;'>{disp_name}</span>")
        self._center_greet_lbl.setFont(QFont(APP_FONT_NAME, 20, QFont.Weight.ExtraBold))
        self._center_greet_lbl.setStyleSheet("color: #ffffff; background: transparent;")
        greet_col.addWidget(self._center_greet_lbl)

        self._center_sub_lbl = QLabel("Charlie is ready. What can I help you with?")
        self._center_sub_lbl.setFont(QFont(APP_FONT_NAME, 10))
        self._center_sub_lbl.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        greet_col.addWidget(self._center_sub_lbl)
        greet_row.addLayout(greet_col, 1)

        dw_row = QHBoxLayout()
        dw_row.setSpacing(14)
        dw_col1 = QVBoxLayout()
        dw_col1.setAlignment(Qt.AlignmentFlag.AlignRight)
        dw_col1.setSpacing(1)
        self._center_date_lbl = QLabel(time.strftime("%a, %b %d, %Y"))
        self._center_date_lbl.setFont(QFont(APP_FONT_NAME, 8))
        self._center_date_lbl.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        dw_col1.addWidget(self._center_date_lbl)
        self._center_time_lbl = QLabel(time.strftime("%I:%M %p"))
        self._center_time_lbl.setFont(QFont(APP_FONT_NAME, 11, QFont.Weight.Bold))
        self._center_time_lbl.setStyleSheet("color: #ffffff; background: transparent;")
        dw_col1.addWidget(self._center_time_lbl)
        dw_row.addLayout(dw_col1)

        # Real-time Weather & Location Telemetry Widget
        self._weather_widget = QFrame()
        self._weather_widget.setCursor(Qt.CursorShape.PointingHandCursor)
        self._weather_widget.setToolTip("Live Temperature & Location Telemetry (Click to refresh)")
        self._weather_widget.setStyleSheet(f"""
            QFrame {{
                background: {C.PANEL2};
                border: 1px solid {C.BORDER};
                border-radius: 12px;
                padding: 3px 10px;
            }}
            QFrame:hover {{
                border-color: rgba(99, 102, 241, 0.45);
                background: {C.PANEL2};
            }}
        """)
        w_box = QHBoxLayout(self._weather_widget)
        w_box.setContentsMargins(4, 2, 6, 2)
        w_box.setSpacing(9)

        self._weather_icon_lbl = QLabel()
        self._weather_icon_lbl.setPixmap(_render_hub_svg("weather_sun_cloud", 20, "#fbbf24"))
        self._weather_icon_lbl.setStyleSheet("background: transparent; border: none;")
        w_box.addWidget(self._weather_icon_lbl)

        w_info = QVBoxLayout()
        w_info.setSpacing(1)
        w_info.setContentsMargins(0, 0, 0, 0)

        # Top line: Live temperature and condition
        self._weather_temp_lbl = QLabel("Detecting...")
        self._weather_temp_lbl.setFont(QFont(APP_FONT_NAME, 9, QFont.Weight.DemiBold))
        self._weather_temp_lbl.setStyleSheet("color: #f8fafc; background: transparent; border: none;")
        w_info.addWidget(self._weather_temp_lbl)

        # Bottom line: Captured location with SVG pin icon
        loc_row = QHBoxLayout()
        loc_row.setSpacing(4)
        loc_row.setContentsMargins(0, 0, 0, 0)
        _loc_pin = QLabel()
        _loc_pin.setPixmap(_render_hub_svg("map_pin", 11, C.TEXT_DIM))
        _loc_pin.setStyleSheet("background: transparent; border: none;")
        loc_row.addWidget(_loc_pin)
        self._weather_loc_lbl = QLabel("Locating...")
        self._weather_loc_lbl.setFont(QFont(APP_FONT_NAME, 8))
        self._weather_loc_lbl.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent; border: none;")
        loc_row.addWidget(self._weather_loc_lbl)
        loc_row.addStretch()
        w_info.addLayout(loc_row)

        w_box.addLayout(w_info)
        self._weather_widget.mousePressEvent = lambda e: self._refresh_live_weather(force=True)
        dw_row.addWidget(self._weather_widget)
        greet_row.addLayout(dw_row)
        greet_lay.addLayout(greet_row)
        lay.addWidget(self._center_greet_widget)

        # ── 1b. Dedicated Professional AI Chat Header (Chat Mode) ──
        self._chat_header_widget = self._build_chat_header()
        self._chat_header_widget.hide()
        lay.addWidget(self._chat_header_widget)

        # ── 2. Center Splitter: Chat Transcript + Content / Quiz ──
        self._center_split = QSplitter(Qt.Orientation.Vertical)
        self._center_split.setStyleSheet(f"""
            QSplitter {{ background: transparent; border: none; }}
            QSplitter::handle {{ background: transparent; height: 4px; }}
        """)

        # Chat stream frame
        chat_frame = QFrame()
        chat_frame.setStyleSheet(f"""
            QFrame {{
                background: {C.PANEL};
                border: 1px solid {C.BORDER};
                border-radius: 14px;
            }}
        """)
        cf_lay = QVBoxLayout(chat_frame)
        cf_lay.setContentsMargins(12, 12, 12, 12)
        cf_lay.setSpacing(6)

        # ── Empty State Welcome Widget ──
        self._welcome_widget = QWidget()
        self._welcome_widget.setStyleSheet("background: transparent; border: none;")
        ww_lay = QVBoxLayout(self._welcome_widget)
        ww_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ww_lay.setContentsMargins(24, 20, 24, 20)
        ww_lay.setSpacing(10)
        ww_lay.addStretch(1)

        orb_lbl = QLabel()
        orb_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        orb_lbl.setPixmap(_render_hub_svg("brand_c", 50, "#818cf8"))
        orb_lbl.setStyleSheet("background: transparent; border: none;")
        ww_lay.addWidget(orb_lbl)

        w_title = QLabel("What can I help you with?")
        w_title.setFont(QFont(APP_FONT_NAME, 16, QFont.Weight.Bold))
        w_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        w_title.setStyleSheet("color: #ffffff; background: transparent; border: none;")
        ww_lay.addWidget(w_title)

        w_sub = QLabel("Select a suggestion to start, or message Charlie below")
        w_sub.setFont(QFont(APP_FONT_NAME, 9))
        w_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        w_sub.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent; border: none;")
        ww_lay.addWidget(w_sub)
        ww_lay.addSpacing(10)

        # 4 smart suggestion cards (2x2 grid)
        starter_grid = QGridLayout()
        starter_grid.setHorizontalSpacing(14)
        starter_grid.setVerticalSpacing(14)
        starter_grid.setRowMinimumHeight(0, 66)
        starter_grid.setRowMinimumHeight(1, 66)
        starter_grid.setColumnStretch(0, 1)
        starter_grid.setColumnStretch(1, 1)

        starters = [
            ("hdr_eye", "Explain what's on my screen", "Analyze active display content & OCR", lambda: self._inspect_active_screen()),
            ("chip_doc", "Search my documents", "Query indexed local documents with RAG", lambda: self._use_chip_prompt("Based on my indexed local documents: ")),
            ("card_voice", "Start voice conversation", "Talk hands-free in real time", lambda: self._activate_voice_assistant_nav()),
            ("card_search", "Research something", "Deep web multi-source research report", lambda: self._use_chip_prompt("Perform a deep comprehensive search on: ")),
        ]

        for idx, (s_svg, s_title, s_desc, s_cb) in enumerate(starters):
            card = _StarterCard(s_svg, s_title, s_desc, s_cb)
            starter_grid.addWidget(card, idx // 2, idx % 2)

        cards_container = QWidget()
        cards_container.setStyleSheet("background: transparent; border: none;")
        cards_container.setMaximumWidth(740)
        cards_container_lay = QVBoxLayout(cards_container)
        cards_container_lay.setContentsMargins(0, 0, 0, 0)
        cards_container_lay.addLayout(starter_grid)

        ww_lay.addWidget(cards_container, 0, Qt.AlignmentFlag.AlignHCenter)
        ww_lay.addStretch(1)

        cf_lay.addWidget(self._welcome_widget, 1)

        self._log = LogWidget()
        cf_lay.addWidget(self._log, 1)
        self._log.hide()

        def _reveal_chat():
            if hasattr(self, "_welcome_widget") and self._welcome_widget.isVisible():
                self._welcome_widget.hide()
                self._log.show()

        self._log.message_received.connect(_reveal_chat)

        self._center_split.addWidget(chat_frame)
        self._center_split.addWidget(self._content_panel)
        self._center_split.addWidget(self._quiz_panel)
        self._center_split.setStretchFactor(0, 5)
        self._center_split.setStretchFactor(1, 2)
        self._center_split.setCollapsible(0, False)
        lay.addWidget(self._center_split, 1)

        # ── 3. Prompt Suggestions Row ──
        chips_row = QHBoxLayout()
        chips_row.setSpacing(8)
        chips_data = [
            ("hdr_eye", "Explain Screen", "Look at what is currently on my screen and explain or help me solve it:"),
            ("chip_doc", "Query Docs", "Based on my indexed local documents: "),
            ("sparkles", "Morning Briefing", "Give me my daily morning briefing: schedule, high-priority tasks, and weather"),
            ("card_search", "Deep Research", "Perform a deep comprehensive search on: "),
            ("card_tasks", "Autopilot", "Automate desktop task: "),
        ]
        for icon_s, label_s, prompt_s in chips_data:
            chip_btn = QPushButton(f"  {label_s}")
            chip_btn.setIcon(_render_svg_icon(icon_s, 14, "#94a3b8"))
            chip_btn.setIconSize(QSize(14, 14))
            chip_btn.setFixedHeight(30)
            chip_btn.setFont(QFont(APP_FONT_NAME, 8, QFont.Weight.Medium))
            chip_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            chip_btn.setStyleSheet(f"""
                QPushButton {{
                    background: {C.PANEL2};
                    color: {C.TEXT_MED};
                    border: 1px solid rgba(255, 255, 255, 0.07);
                    border-radius: 15px;
                    padding: 0 12px;
                }}
                QPushButton:hover {{
                    background: rgba(99, 102, 241, 0.12);
                    border-color: rgba(99, 102, 241, 0.30);
                    color: #ffffff;
                }}
            """)
            chip_btn.clicked.connect(lambda _=False, val=prompt_s: self._use_chip_prompt(val))
            chips_row.addWidget(chip_btn)
        chips_row.addStretch()
        lay.addLayout(chips_row)

        # ── 4. Glass Message Input Bar ──
        input_card = QFrame()
        input_card.setFixedHeight(50)
        input_card.setStyleSheet(f"""
            QFrame {{
                background: {C.PANEL2};
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 14px;
            }}
            QFrame:focus-within {{
                border-color: rgba(99, 102, 241, 0.55);
            }}
        """)
        ic_lay = QHBoxLayout(input_card)
        ic_lay.setContentsMargins(8, 4, 6, 4)
        ic_lay.setSpacing(6)

        # Attachment button
        attach_btn = QPushButton()
        attach_btn.setIcon(_render_svg_icon("paperclip", 16, "#94a3b8"))
        attach_btn.setIconSize(QSize(16, 16))
        attach_btn.setFixedSize(32, 32)
        attach_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        attach_btn.setToolTip("Attach Document or Image")
        attach_btn.setStyleSheet("""
            QPushButton {
                background: transparent; border: none; border-radius: 8px;
            }
            QPushButton:hover { background: rgba(255, 255, 255, 0.08); }
        """)
        attach_btn.clicked.connect(self._choose_file)
        ic_lay.addWidget(attach_btn)

        self._input = QLineEdit()
        self._input.setPlaceholderText(f"Message {self._assistant_name.capitalize()}...")
        self._input.setFont(QFont(APP_FONT_NAME, 9))
        self._input.setStyleSheet("background: transparent; color: #ffffff; border: none; padding: 2px 4px;")
        self._input.returnPressed.connect(self._send)
        ic_lay.addWidget(self._input, 1)

        # Screen Vision / OCR button
        screen_btn = QPushButton()
        screen_btn.setIcon(_render_svg_icon("hdr_eye", 16, "#94a3b8"))
        screen_btn.setIconSize(QSize(16, 16))
        screen_btn.setFixedSize(32, 32)
        screen_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        screen_btn.setToolTip("Screen Vision & OCR: Capture & inspect screen")
        screen_btn.setStyleSheet("""
            QPushButton {
                background: transparent; border: none; border-radius: 8px;
            }
            QPushButton:hover { background: rgba(255, 255, 255, 0.08); }
        """)
        screen_btn.clicked.connect(self._inspect_active_screen)
        ic_lay.addWidget(screen_btn)

        sparkle_btn = QPushButton()
        sparkle_btn.setIcon(_render_svg_icon("sparkles", 16, "#94a3b8"))
        sparkle_btn.setIconSize(QSize(16, 16))
        sparkle_btn.setFixedSize(32, 32)
        sparkle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        sparkle_btn.setToolTip("Intelligence Features & Tools")
        sparkle_btn.setStyleSheet("""
            QPushButton {
                background: transparent; border: none; border-radius: 8px;
            }
            QPushButton:hover { background: rgba(255, 255, 255, 0.08); }
        """)
        sparkle_btn.clicked.connect(self._open_intelligence_hub)
        ic_lay.addWidget(sparkle_btn)

        self._dictate_btn = QPushButton()
        self._dictate_btn.setIcon(_render_svg_icon("mic_solid", 16, "#94a3b8"))
        self._dictate_btn.setIconSize(QSize(16, 16))
        self._dictate_btn.setFixedSize(32, 32)
        self._dictate_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._dictate_btn.setToolTip("Dictate message by voice")
        self._dictate_btn.setStyleSheet("""
            QPushButton {
                background: transparent; border: none; border-radius: 8px;
            }
            QPushButton:hover { background: rgba(255, 255, 255, 0.08); }
        """)
        self._dictate_btn.clicked.connect(self._toggle_chat_dictation)
        ic_lay.addWidget(self._dictate_btn)

        self._send_btn = QPushButton()
        self._send_btn.setIcon(_render_svg_icon("send_arrow", 15, "#ffffff"))
        self._send_btn.setIconSize(QSize(15, 15))
        self._send_btn.setFixedSize(36, 36)
        self._send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._send_btn.setToolTip("Send Message (Enter)")
        self._send_btn.setStyleSheet("""
            QPushButton {
                background: #6366f1;
                border: 1px solid rgba(255, 255, 255, 0.15);
                border-radius: 10px;
            }
            QPushButton:hover {
                background: #4f46e5;
            }
            QPushButton:disabled {
                background: rgba(255, 255, 255, 0.05);
                border-color: transparent;
            }
        """)
        self._send_btn.clicked.connect(self._send)
        ic_lay.addWidget(self._send_btn)

        # Global shortcuts for composer: Ctrl+K to focus, Escape to clear/unfocus
        self._focus_composer_sc = QShortcut(QKeySequence("Ctrl+K"), self)
        self._focus_composer_sc.activated.connect(lambda: (self._input.setFocus(), self._input.selectAll()))
        self._clear_composer_sc = QShortcut(QKeySequence("Escape"), self._input)
        self._clear_composer_sc.activated.connect(lambda: self._input.clear() if self._input.hasFocus() else None)

        lay.addWidget(input_card)

        # ── 5. Bottom 6 Feature Cards ──
        cards_row = QHBoxLayout()
        cards_row.setSpacing(8)
        cards_def = [
            ("chip_doc", "Knowledge Base", "Offline RAG &\nsemantic docs", self._open_knowledge_panel),
            ("card_search", "Deep Research", "Multi-source web\nintelligence", lambda: self._use_chip_prompt("Perform a deep research report on: ")),
            ("card_voice", "Voice Mode", "Talk naturally\nwith Charlie", lambda: self._set_chat_mode(False)),
            ("card_memory_brain", "Memory", "Remembers what\nmatters to you", self._open_memory_panel),
            ("card_tasks", "Tasks", "Turn ideas\ninto action", lambda: self._use_chip_prompt("Help me manage and track my tasks: ")),
            ("card_integrations", "Integrations", "Connect your\nfavorite apps", self._open_plugin_manager),
        ]
        for c_svg, c_title, c_desc, c_cb in cards_def:
            card = QPushButton()
            card.setFixedHeight(88)
            card.setCursor(Qt.CursorShape.PointingHandCursor)
            card.setStyleSheet(f"""
                QPushButton {{
                    background: {C.PANEL};
                    border: 1px solid {C.BORDER};
                    border-radius: 12px;
                    padding: 8px;
                    text-align: left;
                }}
                QPushButton:hover {{
                    border-color: rgba(99, 102, 241, 0.45);
                    background: {C.PANEL2};
                }}
            """)
            c_lay = QVBoxLayout(card)
            c_lay.setContentsMargins(7, 7, 7, 7)
            c_lay.setSpacing(3)

            # Top row: Clean minimal icon on left + Arrow on right
            c_top = QHBoxLayout()
            ci = QLabel()
            ci.setFixedSize(26, 26)
            ci.setAlignment(Qt.AlignmentFlag.AlignCenter)
            ci.setPixmap(_render_hub_svg(c_svg, 14, "#818cf8"))
            ci.setStyleSheet("background: rgba(99, 102, 241, 0.12); border-radius: 6px; border: 1px solid rgba(99, 102, 241, 0.25);")
            c_top.addWidget(ci)
            c_top.addStretch()
            arr = QLabel()
            arr.setPixmap(_render_hub_svg("arrow_right", 11, "#818cf8"))
            arr.setStyleSheet("background: transparent; border: none;")
            c_top.addWidget(arr)
            c_lay.addLayout(c_top)

            # Title - crisp, never clipped
            ct = QLabel(c_title)
            ct.setFont(QFont(APP_FONT_NAME, 8, QFont.Weight.Bold))
            ct.setStyleSheet("color: #f8fafc; background: transparent; border: none;")
            c_lay.addWidget(ct)

            # Description
            cd = QLabel(c_desc)
            cd.setFont(QFont(APP_FONT_NAME, 7))
            cd.setStyleSheet("color: #64748b; background: transparent; border: none;")
            c_lay.addWidget(cd)
            c_lay.addStretch()

            card.clicked.connect(c_cb)
            cards_row.addWidget(card, 1)

        self._center_cards_widget = QWidget()
        cards_lay = QVBoxLayout(self._center_cards_widget)
        cards_lay.setContentsMargins(0, 0, 0, 0)
        cards_lay.setSpacing(0)
        cards_lay.addLayout(cards_row)
        lay.addWidget(self._center_cards_widget)
        return w

    def _build_right_panel(self) -> QWidget:
        w = QWidget()
        w.setObjectName("ConversationPanel")
        w.setFixedWidth(_RIGHT_W)
        w.setStyleSheet(f"""
            QWidget#ConversationPanel {{
                background: {C.PANEL};
                border: 1px solid {C.BORDER};
                border-radius: 16px;
            }}
        """)
        lay = QVBoxLayout(w)
        lay.setContentsMargins(14, 14, 14, 14)
        lay.setSpacing(10)

        # ── 1. Header: Charlie / Neural AI Companion + Controls ──
        hdr_row = QHBoxLayout()
        hdr_row.setSpacing(6)

        # Branded logo mark
        self._avatar_brand_icon = QLabel()
        self._avatar_brand_icon.setFixedSize(30, 30)
        self._avatar_brand_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._avatar_brand_icon.setPixmap(_render_hub_svg("brand_c", 30, "#ffffff"))
        self._avatar_brand_icon.setStyleSheet("background: transparent; border: none;")
        self._avatar_brand_icon.setCursor(Qt.CursorShape.PointingHandCursor)
        self._avatar_brand_icon.setToolTip("Customize UI Theme, Contrast & Logo (Theme Studio)")
        self._avatar_brand_icon.mousePressEvent = lambda ev: self._open_theme_studio()
        hdr_row.addWidget(self._avatar_brand_icon)

        h_info = QVBoxLayout()
        h_info.setSpacing(1)
        h_title = QLabel(self._assistant_name.upper())
        h_title.setFont(QFont(APP_FONT_NAME, 9, QFont.Weight.ExtraBold))
        h_title.setStyleSheet("color: #ffffff; background: transparent; border: none; letter-spacing: 1.2px;")
        h_info.addWidget(h_title)
        h_sub = QLabel("AI Companion")
        h_sub.setFont(QFont(APP_FONT_NAME, 7, QFont.Weight.Medium))
        h_sub.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent; border: none; letter-spacing: 0.2px;")
        h_info.addWidget(h_sub)
        hdr_row.addLayout(h_info)
        hdr_row.addStretch()

        # Status Pill: Ready, Listening, Thinking, Speaking, Offline, Error
        self._status_pill = QLabel("Ready")
        self._status_pill.setFont(QFont(APP_FONT_NAME, 7, QFont.Weight.DemiBold))
        self._status_pill.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status_pill.setFixedHeight(20)
        self._status_pill.setStyleSheet("""
            color: #22c55e;
            background: rgba(34, 197, 94, 0.12);
            border: 1px solid rgba(34, 197, 94, 0.28);
            border-radius: 10px;
            padding: 0 7px;
        """)
        hdr_row.addWidget(self._status_pill)
        hdr_row.addSpacing(2)

        # Control Icons [Expand] [Eye/Theme] [Speaker/Mute]
        ctrl_style = f"""
            QPushButton {{
                background: rgba(255, 255, 255, 0.05);
                border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 7px;
            }}
            QPushButton:hover {{
                background: rgba(99, 102, 241, 0.18); border-color: rgba(99, 102, 241, 0.45);
            }}
        """
        for svg_k, tip, cb in [
            ("hdr_expand", "Toggle Fullscreen (F11)", self._toggle_fullscreen),
            ("hdr_eye", "Theme & Appearance Studio", self._open_theme_studio),
            ("hdr_speaker", "Toggle Voice / Mute (F4)", self._toggle_mute),
        ]:
            b = QPushButton()
            b.setIcon(_render_svg_icon(svg_k, 13, "#94a3b8"))
            b.setIconSize(QSize(13, 13))
            b.setFixedSize(26, 26)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setToolTip(tip)
            b.setStyleSheet(ctrl_style)
            b.clicked.connect(cb)
            hdr_row.addWidget(b)

        lay.addLayout(hdr_row)

        # ── 2. Avatar Viewport (3D Avatar / HudCanvas) ──
        avatar_container = QFrame()
        avatar_container.setObjectName("AvatarContainerFrame")
        avatar_container.setStyleSheet(f"""
            QFrame#AvatarContainerFrame {{
                background: {C.DARK};
                border: 1px solid {C.BORDER};
                border-radius: 14px;
            }}
        """)
        ac_lay = QVBoxLayout(avatar_container)
        ac_lay.setContentsMargins(0, 0, 0, 0)
        ac_lay.setSpacing(0)

        # Embedded stack with HudCanvas
        ac_lay.addWidget(self._hud_cam_stack, 1)

        # Floating listening badge (retained for backward compatibility but hidden to prevent duplicate UI)
        self._listening_badge = QLabel("")
        self._listening_badge.hide()

        lay.addWidget(avatar_container, 1)

        # ── 3. Bottom Voice Controls Dock (Unified 3-State Interaction) ──
        voice_dock = QFrame()
        voice_dock.setObjectName("VoiceDockFrame")
        voice_dock.setStyleSheet(f"""
            QFrame#VoiceDockFrame {{
                background: {C.PANEL2};
                border: 1px solid {C.BORDER};
                border-radius: 14px;
            }}
        """)
        vd_lay = QVBoxLayout(voice_dock)
        vd_lay.setContentsMargins(12, 12, 12, 12)
        vd_lay.setSpacing(10)

        # Contextual prompt / status line
        self._voice_status_lbl = QLabel("Hold or click microphone to talk")
        self._voice_status_lbl.setFont(QFont(APP_FONT_NAME, 8, QFont.Weight.Medium))
        self._voice_status_lbl.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent;")
        self._voice_status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        vd_lay.addWidget(self._voice_status_lbl)

        # Single prominent glowing center mic button
        mic_row = QHBoxLayout()
        mic_row.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._mute_btn = QPushButton()
        self._mute_btn.setObjectName("MainMicBtn")
        self._mute_btn.setFixedSize(60, 60)
        self._mute_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._mute_btn.setIconSize(QSize(28, 28))
        self._mute_btn.setToolTip("Click or hold to talk (F4)")
        self._mute_btn.clicked.connect(self._toggle_mute)
        self._style_mute_btn()
        mic_row.addWidget(self._mute_btn)
        vd_lay.addLayout(mic_row)

        # Clean secondary controls row: Mute output, Stop response, Voice settings
        action_row = QHBoxLayout()
        action_row.setSpacing(8)
        action_row.setAlignment(Qt.AlignmentFlag.AlignCenter)

        sec_style = f"""
            QPushButton {{
                background: rgba(255, 255, 255, 0.04);
                color: #94a3b8;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 14px;
                padding: 0 12px;
                font-size: 11px;
                font-weight: 500;
            }}
            QPushButton:hover {{
                background: rgba(255, 255, 255, 0.08);
                color: #ffffff;
                border-color: rgba(255, 255, 255, 0.18);
            }}
        """

        self._mute_output_btn = QPushButton(" Mute")
        self._mute_output_btn.setIcon(_render_svg_icon("hdr_speaker", 13, "#94a3b8"))
        self._mute_output_btn.setIconSize(QSize(13, 13))
        self._mute_output_btn.setFixedHeight(28)
        self._mute_output_btn.setFont(QFont(APP_FONT_NAME, 8, QFont.Weight.Medium))
        self._mute_output_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._mute_output_btn.setStyleSheet(sec_style)
        self._mute_output_btn.clicked.connect(self._toggle_mute)
        action_row.addWidget(self._mute_output_btn)

        self._interrupt_btn = QPushButton(" Stop")
        self._interrupt_btn.setIcon(_render_svg_icon("stop_square", 11, "#f87171"))
        self._interrupt_btn.setIconSize(QSize(11, 11))
        self._interrupt_btn.setFixedHeight(28)
        self._interrupt_btn.setFont(QFont(APP_FONT_NAME, 8, QFont.Weight.Medium))
        self._interrupt_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._interrupt_btn.setStyleSheet("""
            QPushButton {
                background: rgba(239, 68, 68, 0.08);
                color: #fca5a5;
                border: 1px solid rgba(239, 68, 68, 0.22);
                border-radius: 14px;
                padding: 0 12px;
                font-size: 11px;
                font-weight: 500;
            }
            QPushButton:hover {
                background: rgba(239, 68, 68, 0.2);
                color: #ffffff;
                border-color: rgba(239, 68, 68, 0.45);
            }
        """)
        self._interrupt_btn.clicked.connect(self._do_interrupt)
        action_row.addWidget(self._interrupt_btn)

        self._voice_settings_btn = QPushButton(" Voice")
        self._voice_settings_btn.setIcon(_render_svg_icon("nav_settings", 12, "#94a3b8"))
        self._voice_settings_btn.setIconSize(QSize(12, 12))
        self._voice_settings_btn.setFixedHeight(28)
        self._voice_settings_btn.setFont(QFont(APP_FONT_NAME, 8, QFont.Weight.Medium))
        self._voice_settings_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._voice_settings_btn.setStyleSheet(sec_style)
        self._voice_settings_btn.clicked.connect(self._open_customize)
        action_row.addWidget(self._voice_settings_btn)

        vd_lay.addLayout(action_row)

        # Backward compatibility aliases
        listen_btn = QPushButton(); listen_btn.hide()
        speak_btn = QPushButton(); speak_btn.hide()

        lay.addWidget(voice_dock)

        # ── Retain legacy attributes for compatibility ──
        self._drop_zone = FileDropZone()
        self._drop_zone.hide()
        self._drop_zone.file_selected.connect(self._on_file_selected)
        self._file_hint = QLabel("")
        self._file_hint.hide()
        self._conversation_title = QLabel("Voice conversation")
        self._conversation_title.hide()
        self._voice_mode_btn = QPushButton("Voice")
        self._voice_mode_btn.hide()
        self._voice_mode_btn.clicked.connect(lambda: self._set_chat_mode(False))
        self._chat_mode_btn = QPushButton("AI Chat")
        self._chat_mode_btn.hide()
        self._chat_mode_btn.clicked.connect(lambda: self._set_chat_mode(True))
        self._new_chat_btn = QPushButton("New")
        self._new_chat_btn.hide()
        self._new_chat_btn.clicked.connect(self._start_new_chat)

        return w

    def _build_quick_drawer(self) -> QWidget:
        """Floating overlay panel shown when Settings is toggled."""
        _BTN_STYLE_PRI = f"""
            QPushButton {{
                background: rgba(99, 102, 241, 0.16);
                color: #ffffff; border: 1px solid rgba(99, 102, 241, 0.40); border-radius: 8px;
                text-align: left; padding: 0 12px; font-weight: 600;
                font-family: 'Inter', 'Segoe UI', sans-serif;
            }}
            QPushButton:hover {{
                background: rgba(99, 102, 241, 0.28); border-color: {C.PRI};
            }}
        """
        _BTN_STYLE_DIM = f"""
            QPushButton, QComboBox {{
                background: {C.PANEL2}; color: {C.TEXT_PRIMARY};
                border: 1px solid {C.BORDER}; border-radius: 8px;
                text-align: left; padding: 0 12px;
                font-family: 'Inter', 'Segoe UI', sans-serif;
            }}
            QPushButton:hover, QComboBox:hover {{
                color: #ffffff; background: rgba(99, 102, 241, 0.15);
                border-color: {C.PRI};
            }}
        """

        w = QWidget(self.centralWidget())
        w.setObjectName("QuickDrawer")
        w.setStyleSheet(f"""
            QWidget#QuickDrawer {{
                background: {C.PANEL};
                border: 1px solid {C.BORDER};
                border-top: none;
                border-radius: 0 0 16px 16px;
            }}
        """)
        w.hide()

        root_lay = QVBoxLayout(w)
        root_lay.setContentsMargins(12, 12, 8, 12)
        root_lay.setSpacing(8)

        hdr_row = QHBoxLayout()
        hdr = QLabel("⚙  Settings & Preferences")
        hdr.setFont(QFont(APP_FONT_NAME, 11, QFont.Weight.Bold))
        hdr.setStyleSheet(f"color: {C.WHITE}; background: transparent;")
        hdr_row.addWidget(hdr)
        hdr_row.addStretch()
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(26, 26)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setToolTip("Close Settings")
        close_btn.setStyleSheet(f"""
            QPushButton {{
                color: #ffffff;
                background: rgba(255, 255, 255, 0.1);
                border: 1px solid rgba(255, 255, 255, 0.2);
                border-radius: 13px;
                font-size: 13px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                color: #ffffff;
                background: #ef4444;
                border-color: #ef4444;
            }}
        """)
        close_btn.clicked.connect(lambda: self._toggle_drawer(False))
        hdr_row.addWidget(close_btn)
        root_lay.addLayout(hdr_row)

        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {C.BORDER}; margin-bottom: 4px;")
        root_lay.addWidget(sep)

        self._settings_scroll = QScrollArea(w)
        self._settings_scroll.setObjectName("SettingsScroll")
        self._settings_scroll.setWidgetResizable(True)
        self._settings_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._settings_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._settings_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._settings_scroll.setStyleSheet(f"""
            QScrollArea#SettingsScroll {{ background: transparent; border: none; }}
            QScrollArea#SettingsScroll > QWidget > QWidget {{ background: transparent; }}
            QScrollBar:vertical {{
                background: transparent; width: 6px; margin: 0;
                border-radius: 3px;
            }}
            QScrollBar::handle:vertical {{
                background: rgba(255, 255, 255, 0.12); min-height: 28px; border-radius: 3px;
            }}
            QScrollBar::handle:vertical:hover {{ background: {C.PRI}; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        """)
        self._settings_scroll_content = QWidget()
        self._settings_scroll_content.setObjectName("SettingsScrollContent")
        lay = QVBoxLayout(self._settings_scroll_content)
        lay.setContentsMargins(0, 0, 6, 4)
        lay.setSpacing(7)
        self._settings_scroll.setWidget(self._settings_scroll_content)
        root_lay.addWidget(self._settings_scroll, 1)

        remote_btn = QPushButton("◉  REMOTE CONTROL")
        remote_btn.setFixedHeight(30)
        remote_btn.setFont(QFont(APP_FONT_NAME, 8, QFont.Weight.Bold))
        remote_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        remote_btn.setStyleSheet(_BTN_STYLE_PRI)
        remote_btn.clicked.connect(self._open_remote)
        remote_btn.setText("Remote access")
        lay.addWidget(remote_btn)

        fs_btn = QPushButton("⛶  FULLSCREEN  [F11]")
        fs_btn.setFixedHeight(26)
        fs_btn.setFont(QFont(APP_FONT_NAME, 7))
        fs_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        fs_btn.setStyleSheet(_BTN_STYLE_DIM)
        fs_btn.clicked.connect(self._toggle_fullscreen)
        fs_btn.setText("Fullscreen")
        lay.addWidget(fs_btn)

        sc_btn = QPushButton("⊞  CREATE DESKTOP SHORTCUT")
        sc_btn.setFixedHeight(26)
        sc_btn.setFont(QFont(APP_FONT_NAME, 7))
        sc_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        sc_btn.setStyleSheet(_BTN_STYLE_DIM)
        sc_btn.clicked.connect(self._create_desktop_shortcut)
        sc_btn.setText("Create desktop shortcut")
        lay.addWidget(sc_btn)

        self._autostart_btn = QPushButton("◉  AUTO-START: OFF")
        self._autostart_btn.setFixedHeight(26)
        self._autostart_btn.setFont(QFont(APP_FONT_NAME, 7))
        self._autostart_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._autostart_btn.clicked.connect(self._toggle_autostart)
        lay.addWidget(self._autostart_btn)

        cust_btn = QPushButton("⚙  CUSTOMISE ASSISTANT")
        cust_btn.setFixedHeight(26)
        cust_btn.setFont(QFont(APP_FONT_NAME, 7))
        cust_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cust_btn.setStyleSheet(_BTN_STYLE_DIM)
        cust_btn.clicked.connect(self._open_customize)
        cust_btn.setText("Voice studio & personality")
        lay.addWidget(cust_btn)

        appearance_label = QLabel("APPEARANCE & THEMES")
        appearance_label.setFont(QFont(APP_FONT_NAME, 7, QFont.Weight.Bold))
        appearance_label.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        lay.addWidget(appearance_label)

        open_studio_btn = QPushButton("🎨  Open Theme & Color Studio")
        open_studio_btn.setFixedHeight(32)
        open_studio_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        open_studio_btn.setStyleSheet(f"""
            QPushButton {{
                background: rgba(99, 102, 241, 0.16);
                color: #ffffff;
                border: 1px solid rgba(99, 102, 241, 0.40);
                border-radius: 8px;
                font-weight: 600;
                font-size: 11px;
                font-family: 'Inter', 'Segoe UI', sans-serif;
            }}
            QPushButton:hover {{
                background: rgba(99, 102, 241, 0.28);
                border-color: {C.PRI};
            }}
        """)
        open_studio_btn.clicked.connect(self._open_theme_studio)
        lay.addWidget(open_studio_btn)

        appearance_cfg = _read_full_config()
        self._theme_combo = ClickOnlyComboBox()
        self._theme_combo.setFixedHeight(30)
        self._theme_combo.setStyleSheet(_BTN_STYLE_DIM)
        for key, label in UI_THEME_LABELS.items():
            self._theme_combo.addItem(f"Theme: {label}", key)
        selected_theme = normalize_ui_theme(appearance_cfg.get("ui_theme", DEFAULT_UI_THEME))
        theme_index = self._theme_combo.findData(selected_theme)
        self._theme_combo.setCurrentIndex(max(0, theme_index))
        self._theme_combo.currentIndexChanged.connect(self._on_theme_selected)
        lay.addWidget(self._theme_combo)

        self._accent_combo = ClickOnlyComboBox()
        self._accent_combo.setFixedHeight(30)
        self._accent_combo.setStyleSheet(_BTN_STYLE_DIM)
        for label, colour in UI_ACCENTS.items():
            self._accent_combo.addItem(f"Colour: {label}", colour)
        selected_colour = str(appearance_cfg.get("ui_color") or DEFAULT_UI_COLOR).lower()
        colour_index = self._accent_combo.findData(selected_colour)
        if colour_index < 0:
            self._accent_combo.addItem(f"Colour: Custom ({selected_colour})", selected_colour)
            colour_index = self._accent_combo.count() - 1
        self._accent_combo.setCurrentIndex(colour_index)
        self._accent_combo.currentIndexChanged.connect(self._on_accent_selected)
        lay.addWidget(self._accent_combo)

        colour_wheel_btn = QPushButton("Open custom colour wheel")
        colour_wheel_btn.setFixedHeight(30)
        colour_wheel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        colour_wheel_btn.setStyleSheet(_BTN_STYLE_DIM)
        colour_wheel_btn.clicked.connect(self._open_customize)
        lay.addWidget(colour_wheel_btn)

        personal_label = QLabel("PERSONAL COMPANION")
        personal_label.setFont(QFont(APP_FONT_NAME, 7, QFont.Weight.Bold))
        personal_label.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        lay.addWidget(personal_label)

        profile_row = QHBoxLayout(); profile_row.setSpacing(6)
        self._profile_combo = ClickOnlyComboBox()
        self._profile_combo.setFixedHeight(30)
        self._profile_combo.setCursor(Qt.CursorShape.PointingHandCursor)
        self._profile_combo.setStyleSheet(_BTN_STYLE_DIM)
        self._profile_combo.currentIndexChanged.connect(self._on_profile_selected)
        profile_row.addWidget(self._profile_combo, 1)
        add_profile_btn = QPushButton("+")
        add_profile_btn.setFixedSize(36, 30)
        add_profile_btn.setToolTip("Create a private family profile")
        add_profile_btn.setStyleSheet(_BTN_STYLE_DIM)
        add_profile_btn.clicked.connect(self._add_profile)
        profile_row.addWidget(add_profile_btn)
        lay.addLayout(profile_row)

        self._companion_mode_combo = ClickOnlyComboBox()
        self._companion_mode_combo.setFixedHeight(30)
        self._companion_mode_combo.setStyleSheet(_BTN_STYLE_DIM)
        self._companion_mode_combo.addItem("Just listen", "listen")
        self._companion_mode_combo.addItem("Give advice", "advice")
        self._companion_mode_combo.addItem("Help me act", "act")
        self._companion_mode_combo.currentIndexChanged.connect(self._on_companion_mode_selected)
        lay.addWidget(self._companion_mode_combo)
        self._refresh_personal_controls()

        # Keep voice gender in the first-level settings.  Selecting a profile
        # applies its paired Gemini voice and matching avatar immediately.
        voice_label = QLabel("ASSISTANT VOICE")
        voice_label.setFont(QFont(APP_FONT_NAME, 7, QFont.Weight.Bold))
        voice_label.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        lay.addWidget(voice_label)
        self._voice_profile_btns: dict[str, QPushButton] = {}
        voice_profile_row = QHBoxLayout(); voice_profile_row.setSpacing(6)
        for persona, label in (("male", "MALE"), ("female", "FEMALE")):
            button = QPushButton(label)
            button.setCheckable(True)
            button.setFixedHeight(30)
            button.setFont(QFont(APP_FONT_NAME, 9, QFont.Weight.DemiBold))
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(
                lambda _=False, selected=persona: self._activate_voice_profile(selected))
            self._voice_profile_btns[persona] = button
            voice_profile_row.addWidget(button)
        lay.addLayout(voice_profile_row)
        self._refresh_voice_profile_btns()

        brain_label = QLabel("LEARNING BRAIN")
        brain_label.setFont(QFont(APP_FONT_NAME, 7, QFont.Weight.Bold))
        brain_label.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        lay.addWidget(brain_label)

        brain_row = QHBoxLayout(); brain_row.setSpacing(6)
        self._emotion_btn = QPushButton()
        self._routine_btn = QPushButton()
        for button in (self._emotion_btn, self._routine_btn):
            button.setCheckable(True); button.setFixedHeight(30)
            button.setFont(QFont(APP_FONT_NAME, 8, QFont.Weight.DemiBold))
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            brain_row.addWidget(button, 1)
        self._emotion_btn.clicked.connect(lambda: self._toggle_brain_setting("emotion_support"))
        self._routine_btn.clicked.connect(lambda: self._toggle_brain_setting("routine_suggestions"))
        lay.addLayout(brain_row)

        self._vision_copilot_combo = ClickOnlyComboBox()
        self._vision_copilot_combo.setFixedHeight(30)
        self._vision_copilot_combo.setStyleSheet(_BTN_STYLE_DIM)
        self._vision_copilot_combo.addItem("Vision Copilot: ask before capture", "ask")
        self._vision_copilot_combo.addItem("Vision Copilot: available", "on")
        self._vision_copilot_combo.addItem("Vision Copilot: off", "off")
        self._vision_copilot_combo.currentIndexChanged.connect(self._on_vision_mode)
        lay.addWidget(self._vision_copilot_combo)

        brain_row2 = QHBoxLayout(); brain_row2.setSpacing(6)
        self._daily_intel_btn = QPushButton()
        self._voice_identity_btn = QPushButton()
        for button in (self._daily_intel_btn, self._voice_identity_btn):
            button.setCheckable(True); button.setFixedHeight(30)
            button.setFont(QFont(APP_FONT_NAME, 8, QFont.Weight.DemiBold))
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            brain_row2.addWidget(button, 1)
        self._daily_intel_btn.clicked.connect(lambda: self._toggle_brain_setting("daily_intelligence"))
        self._voice_identity_btn.clicked.connect(self._toggle_voice_identity)
        lay.addLayout(brain_row2)

        self._game_room_btn = QPushButton("GAME ROOM — 10 VOICE GAMES")
        self._game_room_btn.setFixedHeight(30)
        self._game_room_btn.setFont(QFont(APP_FONT_NAME, 8, QFont.Weight.DemiBold))
        self._game_room_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._game_room_btn.setStyleSheet(_BTN_STYLE_DIM)
        self._game_room_btn.setToolTip(
            "Mysteries, 20 Questions, quizzes, family games, daily challenges, and more.")
        self._game_room_btn.clicked.connect(self._open_game_room)
        lay.addWidget(self._game_room_btn)

        self._surprise_btn = QPushButton("SURPRISE ME")
        self._surprise_btn.setFixedHeight(30)
        self._surprise_btn.setFont(QFont(APP_FONT_NAME, 8, QFont.Weight.DemiBold))
        self._surprise_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._surprise_btn.setStyleSheet(_BTN_STYLE_DIM)
        self._surprise_btn.setToolTip("Start a fresh mystery, brain teaser, challenge, or interactive story.")
        self._surprise_btn.clicked.connect(self._start_surprise_mode)
        lay.addWidget(self._surprise_btn)
        self._refresh_brain_controls()

        self._brief_btn = QPushButton()
        self._brief_btn.setFixedHeight(26)
        self._brief_btn.setFont(QFont(APP_FONT_NAME, 7))
        self._brief_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._brief_btn.clicked.connect(self._toggle_brief)
        lay.addWidget(self._brief_btn)

        # ── Wake word ──────────────────────────────────────────────────────────
        self._wake_btn = QPushButton()
        self._wake_btn.setFixedHeight(26)
        self._wake_btn.setFont(QFont(APP_FONT_NAME, 7))
        self._wake_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._wake_btn.clicked.connect(self._toggle_wake_word)
        lay.addWidget(self._wake_btn)

        self._wake_sleep_btn = QPushButton()
        self._wake_sleep_btn.setFixedHeight(26)
        self._wake_sleep_btn.setFont(QFont(APP_FONT_NAME, 7))
        self._wake_sleep_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._wake_sleep_btn.clicked.connect(self._tap_wake_manual)
        lay.addWidget(self._wake_sleep_btn)
        # Neutral placeholder now; the real state (which may load the model to
        # check readiness) is resolved lazily the first time the drawer opens.
        self._wake_btn.setText("🎙  WAKE WORD")
        self._wake_btn.setStyleSheet(_BTN_STYLE_DIM)
        self._wake_sleep_btn.hide()

        self._ptt_btn = QPushButton()
        self._ptt_btn.setFixedHeight(26)
        self._ptt_btn.setFont(QFont(APP_FONT_NAME, 7))
        self._ptt_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._ptt_btn.clicked.connect(self._toggle_ptt)
        lay.addWidget(self._ptt_btn)

        self._refresh_talk_btns()

        self._slow_speech_btn = QPushButton()
        self._slow_speech_btn.setFixedHeight(30)
        self._slow_speech_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._slow_speech_btn.clicked.connect(self._toggle_slow_speech)
        self._slow_speech_btn.setToolTip(
            "Waits patiently through longer pauses so slowly spoken sentences are not cut off.")
        lay.addWidget(self._slow_speech_btn)
        self._refresh_slow_speech_btn()

        self._hud_btn = QPushButton()
        self._hud_btn.setFixedHeight(26)
        self._hud_btn.setFont(QFont(APP_FONT_NAME, 7))
        self._hud_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._hud_btn.clicked.connect(self._toggle_hud_style)
        lay.addWidget(self._hud_btn)
        self._refresh_hud_btn()

        audio_btn = QPushButton("🎧  AUDIO DEVICES")
        audio_btn.setFixedHeight(26)
        audio_btn.setFont(QFont(APP_FONT_NAME, 7))
        audio_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        audio_btn.setStyleSheet(_BTN_STYLE_DIM)
        audio_btn.clicked.connect(self._open_audio_devices)
        audio_btn.setText("Audio devices")
        lay.addWidget(audio_btn)

        mem_btn = QPushButton("🧠  MEMORY")
        mem_btn.setFixedHeight(26)
        mem_btn.setFont(QFont(APP_FONT_NAME, 7))
        mem_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        mem_btn.setStyleSheet(_BTN_STYLE_DIM)
        mem_btn.clicked.connect(self._open_memory_panel)
        mem_btn.setText("Memory")
        lay.addWidget(mem_btn)

        plugin_btn = QPushButton("🧩  PLUGINS")
        plugin_btn.setFixedHeight(26)
        plugin_btn.setFont(QFont(APP_FONT_NAME, 7))
        plugin_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        plugin_btn.setStyleSheet(_BTN_STYLE_DIM)
        plugin_btn.clicked.connect(self._open_plugin_manager)
        plugin_btn.setText("Plugins")
        lay.addWidget(plugin_btn)

        settings_btn = QPushButton("⚙  PLUGIN SETTINGS")
        settings_btn.setFixedHeight(26)
        settings_btn.setFont(QFont(APP_FONT_NAME, 7))
        settings_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        settings_btn.setStyleSheet(_BTN_STYLE_DIM)
        settings_btn.clicked.connect(self._open_plugin_settings)
        settings_btn.setText("Plugin settings")
        lay.addWidget(settings_btn)

        account_label = QLabel("ACCOUNT & APP")
        account_label.setFont(QFont(APP_FONT_NAME, 7, QFont.Weight.Bold))
        account_label.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        lay.addWidget(account_label)

        self._subscription_btn = QPushButton("Subscription: loading")
        self._subscription_btn.setFixedHeight(34)
        self._subscription_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._subscription_btn.setToolTip(
            "View the current plan, usage allowance, features and upgrade options")
        self._subscription_btn.clicked.connect(self._show_pricing_overlay)
        lay.addWidget(self._subscription_btn)
        self._refresh_subscription_ui()

        about_btn = QPushButton("About CHARLIE")
        about_btn.setObjectName("AboutCharlieButton")
        about_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        about_btn.setStyleSheet(_BTN_STYLE_DIM)
        about_btn.clicked.connect(self._open_about_panel)
        lay.addWidget(about_btn)

        profile_btn = QPushButton("My profile")
        profile_btn.setObjectName("MyProfileButton")
        profile_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        profile_btn.setStyleSheet(_BTN_STYLE_DIM)
        profile_btn.clicked.connect(self._open_profile_panel)
        lay.addWidget(profile_btn)

        for button in w.findChildren(QPushButton):
            button.setFont(QFont(APP_FONT_NAME, 9, QFont.Weight.Medium))
            button.setMinimumHeight(32)
            button.setMinimumWidth(0)
            button.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        for combo in self._settings_scroll_content.findChildren(QComboBox):
            combo.setMinimumWidth(0)
            combo.setMinimumContentsLength(8)
            combo.setSizeAdjustPolicy(
                QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            combo.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self._settings_scroll_content.adjustSize()
        return w

    def _open_intelligence_hub(self) -> None:
        if self._quick_drawer is not None:
            self._quick_drawer.hide()
        self._drawer_btn.setChecked(False)
        cw = self.centralWidget()
        if cw is not None:
            self._intelligence_hub.setGeometry(0, 0, cw.width(), cw.height())
        self._intelligence_hub.show()
        self._intelligence_hub.raise_()

    def _launch_intelligence_feature(self, instruction: str) -> None:
        self._intelligence_hub.hide()
        instruction = str(instruction or "").strip()
        if not instruction:
            return
        self._log.append_log("SYS: Intelligence Hub feature started.")
        if callable(self.request_say):
            threading.Thread(target=self.request_say, args=(instruction,), daemon=True).start()
        else:
            self._input.setText(instruction)
            self._input.setFocus()

    def _position_command_bar(self) -> None:
        cw = self.centralWidget()
        if cw is None:
            return
        width = min(720, max(420, cw.width() - 80))
        self._command_bar.setFixedWidth(width)
        self._command_bar.move((cw.width() - width) // 2, 22)

    def _show_universal_command_bar(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()
        self._position_command_bar()
        self._command_bar.open_and_focus()

    def _submit_universal_command(self, text: str) -> None:
        text = str(text or "").strip()
        if not text:
            return
        self._log.append_log(f"You: {text}")

        # Check for immediate local command handling
        lower = text.lower()
        if "daily briefing" in lower or lower in ("briefing", "brief me", "morning brief"):
            from memory.personal_hub import generate_daily_briefing
            briefing = generate_daily_briefing()
            self._show_content("DAILY EXECUTIVE BRIEFING", briefing)
            self._log.append_log("SYS: Executive daily briefing generated.")
            return

        if lower in ("knowledge", "open knowledge", "rag", "docs", "knowledge base"):
            self._open_knowledge_panel()
            self._log.append_log("SYS: Local RAG Knowledge Base opened.")
            return

        if lower in ("proactive", "daemon", "advisor", "nudge", "alerts"):
            self._open_proactive_panel()
            self._log.append_log("SYS: Autonomous Proactive Daemon panel opened.")
            return

        callback = self.on_chat_command if self._chat_mode else self.on_text_command
        if callable(callback):
            threading.Thread(target=callback, args=(text,), daemon=True).start()
        else:
            self._input.setText(text)

    def _setup_system_tray(self) -> None:
        """Create Windows system tray icon and context menu for background access."""
        from PyQt6.QtWidgets import QSystemTrayIcon, QMenu
        from PyQt6.QtGui import QIcon
        ico_path = Path(__file__).resolve().parent / "config" / "charlie.ico"
        icon = QIcon(str(ico_path)) if ico_path.exists() else self.windowIcon()

        self._tray = QSystemTrayIcon(icon, self)
        menu = QMenu()
        menu.setStyleSheet(f"""
            QMenu {{ background: {C.PANEL}; color: {C.TEXT}; border: 1px solid {C.BORDER}; padding: 4px; }}
            QMenu::item:selected {{ background: {C.PRI_GHO}; color: {C.PRI}; }}
        """)

        act_show = menu.addAction("Show / Hide CHARLIE")
        if act_show is not None:
            act_show.triggered.connect(lambda: self.hide() if self.isVisible() else (self.showNormal(), self.raise_(), self.activateWindow()))

        act_cmd = menu.addAction("Command Bar (Ctrl+Space)")
        if act_cmd is not None:
            act_cmd.triggered.connect(self._show_universal_command_bar)

        act_brief = menu.addAction("📋 Daily Briefing")
        if act_brief is not None:
            act_brief.triggered.connect(lambda: self._submit_universal_command("daily briefing"))

        act_rag = menu.addAction("📚 Knowledge Base (RAG)")
        if act_rag is not None:
            act_rag.triggered.connect(self._open_knowledge_panel)

        menu.addSeparator()

        act_mute = menu.addAction("Mute / Unmute Microphone")
        if act_mute is not None:
            act_mute.triggered.connect(self._toggle_mute)

        menu.addSeparator()

        act_exit = menu.addAction("Exit CHARLIE")
        if act_exit is not None:
            act_exit.triggered.connect(self.close)

        self._tray.setContextMenu(menu)
        self._tray.activated.connect(lambda r: self._show_universal_command_bar() if r == QSystemTrayIcon.ActivationReason.Trigger else None)
        self._tray.show()

    def closeEvent(self, a0) -> None:

        try:
            self._global_command_shortcut.stop()
        except Exception:
            pass
        try:
            if self._chat_dictating:
                self._stop_chat_dictation()
        except Exception:
            pass
        try:
            if hasattr(self, "_proactive_daemon") and self._proactive_daemon:
                self._proactive_daemon.stop()
        except Exception:
            pass
        super().closeEvent(a0)


    def _open_settings_drawer(self):
        """Open or toggle the Settings & Preferences drawer from navigation."""
        if getattr(self, '_quick_drawer', None) is None:
            self._quick_drawer = self._build_quick_drawer()
        if self._quick_drawer.isVisible():
            self._quick_drawer.hide()
            self._hide_modal_backdrop()
            self._restore_primary_nav()
        else:
            self._close_active_overlays(exclude="settings")
            self._set_active_nav_index(7)
            self._refresh_wake_btns()   # resolve wake state on open (lazy)
            self._refresh_voice_profile_btns()
            self._position_quick_drawer()
            self._show_modal_backdrop()
            self._quick_drawer.show()
            self._quick_drawer.raise_()

    _show_settings_dialog = _open_settings_drawer

    def _toggle_drawer(self, checked: bool | None = None):
        if getattr(self, '_quick_drawer', None) is None:
            self._quick_drawer = self._build_quick_drawer()
        if checked is None or (checked is False and not self._quick_drawer.isVisible()):
            checked = not self._quick_drawer.isVisible()
        if checked:
            self._close_active_overlays(exclude="settings")
            self._set_active_nav_index(7)
            self._refresh_wake_btns()   # resolve wake state on open (lazy)
            self._refresh_voice_profile_btns()
            self._position_quick_drawer()
            self._show_modal_backdrop()
            self._quick_drawer.show()
            self._quick_drawer.raise_()
        else:
            self._quick_drawer.hide()
            self._hide_modal_backdrop()
            self._restore_primary_nav()

    def _position_quick_drawer(self):
        if getattr(self, '_quick_drawer', None) is None:
            return
        _W = 340
        self._quick_drawer.setFixedWidth(_W)
        cw = self.centralWidget()
        available = max(260, (cw.height() if cw is not None else 600) - 62)
        self._quick_drawer.setGeometry(_LEFT_W + 14, 54, _W, available)

    def _update_ai_engine_buttons(self, is_local: bool):
        cloud_active = """
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 rgba(99, 102, 241, 0.28), stop:1 rgba(139, 92, 246, 0.20));
                color: #ffffff;
                border: 1px solid rgba(129, 140, 248, 0.65);
                border-radius: 14px;
                padding: 0 11px 0 8px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 rgba(99, 102, 241, 0.38), stop:1 rgba(139, 92, 246, 0.28));
                color: #ffffff;
                border: 1px solid rgba(165, 180, 252, 0.85);
            }
        """
        cloud_inactive = """
            QPushButton {
                background: rgba(255, 255, 255, 0.03);
                color: #94a3b8;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 14px;
                padding: 0 11px 0 8px;
                font-weight: 500;
            }
            QPushButton:hover {
                background: rgba(99, 102, 241, 0.10);
                color: #e2e8f0;
                border: 1px solid rgba(129, 140, 248, 0.35);
            }
        """
        local_active = """
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 rgba(245, 158, 11, 0.25), stop:1 rgba(217, 119, 6, 0.18));
                color: #fef3c7;
                border: 1px solid rgba(245, 158, 11, 0.65);
                border-radius: 14px;
                padding: 0 11px 0 8px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 rgba(245, 158, 11, 0.38), stop:1 rgba(217, 119, 6, 0.28));
                color: #ffffff;
                border: 1px solid rgba(251, 191, 36, 0.85);
            }
        """
        local_inactive = """
            QPushButton {
                background: rgba(255, 255, 255, 0.03);
                color: #94a3b8;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 14px;
                padding: 0 11px 0 8px;
                font-weight: 500;
            }
            QPushButton:hover {
                background: rgba(245, 158, 11, 0.10);
                color: #e2e8f0;
                border: 1px solid rgba(245, 158, 11, 0.35);
            }
        """
        if hasattr(self, "_model_selector_btn"):
            if is_local:
                self._model_selector_btn.setText("Model: Local AI — Ollama ▾")
                self._model_selector_btn.setIcon(_render_svg_icon("ollama_llama", 14, "#fbbf24"))
            else:
                self._model_selector_btn.setText("Model: Cloud AI ▾")
                self._model_selector_btn.setIcon(_render_svg_icon("gemini_color", 14))
        if hasattr(self, "_cloud_ai_btn") and hasattr(self, "_local_ai_btn"):
            if is_local:
                self._cloud_ai_btn.setStyleSheet(cloud_inactive)
                self._cloud_ai_btn.setIcon(_render_svg_icon("gemini_sparkle", 15, "#64748b"))
                self._local_ai_btn.setStyleSheet(local_active)
                self._local_ai_btn.setIcon(_render_svg_icon("ollama_llama", 15, "#fbbf24"))
            else:
                self._cloud_ai_btn.setStyleSheet(cloud_active)
                self._cloud_ai_btn.setIcon(_render_svg_icon("gemini_color", 15))
                self._local_ai_btn.setStyleSheet(local_inactive)
                self._local_ai_btn.setIcon(_render_svg_icon("ollama_llama", 15, "#64748b"))

    def _set_ai_engine(self, provider: str):
        import json
        from memory.config_manager import CONFIG_FILE, load_api_keys
        cfg = load_api_keys()
        is_local = "ollama" in provider.lower() or "local" in provider.lower()
        new_prov = "ollama" if is_local else "gemini"
        cfg["llm_provider"] = new_prov
        try:
            CONFIG_FILE.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
        except Exception:
            pass
        self._update_ai_engine_buttons(is_local)
        if is_local:
            self._log.append_log("SYS: Switched to 100% Private Offline Local AI (Ollama).")
        else:
            self._log.append_log("SYS: Switched to Cloud AI (Gemini Live multi-modal).")

    def _toggle_ai_engine(self):
        from memory.config_manager import load_api_keys
        cfg = load_api_keys()
        current = str(cfg.get("llm_provider", "gemini")).lower()
        if "ollama" in current or "local" in current:
            self._set_ai_engine("gemini")
        else:
            self._set_ai_engine("ollama")

    def _inspect_active_screen(self):
        try:
            screen = QApplication.primaryScreen()
            if not screen:
                self._log.append_log("ERR: No screen detected.")
                return
            grab = getattr(screen, "grabWindow", None)
            if callable(grab):
                pix = grab(0)
            else:
                return
            from memory.config_manager import BASE_DIR
            out_dir = BASE_DIR / "scratch"
            out_dir.mkdir(parents=True, exist_ok=True)
            shot_path = out_dir / "screen_capture.png"
            pix.save(str(shot_path), "PNG")

            text_snippet = ""
            try:
                from engine import vision_ocr
                res = vision_ocr.extract_screen_text()
                if res and res.get("text"):
                    text_snippet = res["text"][:600].strip()
            except Exception:
                pass

            prompt = "Analyze what is visible on my screen right now and explain it or help with current task."
            if text_snippet:
                prompt += f"\n[Screen OCR]:\n{text_snippet}"
            self._input.setText(prompt)
            self._send()
            self._log.append_log("SYS: Captured active screen & sent to Vision Agent.")
        except Exception as e:
            self._log.append_log(f"ERR: Screen inspection failed — {e}")

    def _build_input_row(self) -> QHBoxLayout:
        row = QHBoxLayout(); row.setSpacing(5)
        self._input = QLineEdit()
        self._input.setPlaceholderText("Type a command or question…")
        self._input.setFont(QFont(APP_FONT_NAME, 10))
        self._input.setFixedHeight(40)
        self._input.setStyleSheet(f"""
            QLineEdit {{
                background: {C.PANEL}; color: {C.TEXT};
                border: 1px solid {C.BORDER}; border-radius: 8px; padding: 4px 10px;
                selection-background-color: {C.PRI};
                selection-color: {C.DARK};
            }}
            QLineEdit:focus {{
                background: {C.PANEL2}; color: {C.TEXT};
                border: 1px solid {C.PRI};
            }}
        """)
        self._refresh_message_input_contrast()
        self._input.setPlaceholderText("Ask anything or give a task…")
        self._input.returnPressed.connect(self._send)
        row.addWidget(self._input)

        self._dictate_btn = QPushButton("Speak")
        self._dictate_btn.setFixedSize(64, 40)
        self._dictate_btn.setFont(QFont(APP_FONT_NAME, 9, QFont.Weight.DemiBold))
        self._dictate_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._dictate_btn.setToolTip("Speak one message and place the words in the AI Chat box")
        self._dictate_btn.clicked.connect(self._toggle_chat_dictation)
        self._dictate_btn.hide()
        row.addWidget(self._dictate_btn)

        self._send_btn = QPushButton("Send")
        self._send_btn.setFixedSize(62, 40)
        self._send_btn.setFont(QFont(APP_FONT_NAME, 9, QFont.Weight.DemiBold))
        self._send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._send_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C.PRI}; color: {C.DARK};
                border: 1px solid {C.PRI}; border-radius: 8px;
            }}
            QPushButton:hover {{ background: {C.WHITE}; border: 1px solid {C.WHITE}; }}
            QPushButton:disabled {{
                background: {C.PANEL2}; color: {C.TEXT_DIM}; border-color: {C.BORDER};
            }}
        """)
        self._send_btn.clicked.connect(self._send)
        row.addWidget(self._send_btn)
        return row

    def _refresh_message_input_contrast(self) -> None:
        """Keep typed, placeholder and selected text readable in every theme."""
        if not hasattr(self, "_input"):
            return
        # Some Windows/Qt styles override QLineEdit foreground roles on focus,
        # so set the palette as well as the stylesheet.
        palette = self._input.palette()
        palette.setColor(QPalette.ColorRole.Base, QColor(C.PANEL))
        palette.setColor(QPalette.ColorRole.Text, QColor(C.TEXT))
        palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(C.TEXT_DIM))
        palette.setColor(QPalette.ColorRole.Highlight, QColor(C.PRI))
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor(C.DARK))
        self._input.setPalette(palette)

    def _refresh_chat_mode_buttons(self) -> None:
        if not hasattr(self, "_voice_mode_btn"):
            return
        active = f"background: {C.PRI}; color: {C.DARK}; border: 1px solid {C.PRI};"
        idle = f"background: {C.PANEL2}; color: {C.TEXT_MED}; border: 1px solid {C.BORDER};"
        common = "border-radius: 7px; padding: 0 8px;"
        self._voice_mode_btn.setStyleSheet((idle if self._chat_mode else active) + common)
        self._chat_mode_btn.setStyleSheet((active if self._chat_mode else idle) + common)
        self._new_chat_btn.setStyleSheet(idle + common)
        self._new_chat_btn.setVisible(self._chat_mode)
        if hasattr(self, "_dictate_btn"):
            self._dictate_btn.setVisible(self._chat_mode)
            self._style_chat_dictation_button()

    def _activate_voice_assistant_nav(self):
        self._close_active_overlays()
        if getattr(self, "_chat_mode", False):
            self._set_chat_mode(False)
        self._set_active_nav_index(2)
        if getattr(self, "_muted", False):
            self._toggle_mute()

    def _set_chat_mode(self, enabled: bool) -> None:
        enabled = bool(enabled)
        if enabled == self._chat_mode:
            return
        self._chat_mode = enabled
        if enabled:
            # 1. Hide the 3D assistant face panel on the right
            if hasattr(self, "_right_panel") and self._right_panel is not None:
                self._right_panel.hide()

            # 2. Hide bottom dashboard feature cards
            if hasattr(self, "_center_cards_widget") and self._center_cards_widget is not None:
                self._center_cards_widget.hide()

            # 3. Swap home greeting header with dedicated chat header
            if hasattr(self, "_center_greet_widget") and self._center_greet_widget is not None:
                self._center_greet_widget.hide()
            if hasattr(self, "_chat_header_widget") and self._chat_header_widget is not None:
                self._chat_header_widget.show()
            if hasattr(self, "_welcome_widget") and self._welcome_widget is not None:
                self._welcome_widget.hide()
            if hasattr(self, "_log") and self._log is not None:
                self._log.show()
            self._chat_restore_sizes = self._center_split.sizes()
            self._chat_restore_content = self._content_panel.isVisible()
            self._chat_restore_quiz = self._quiz_panel.isVisible()
            self._content_panel.hide()
            self._quiz_panel.hide()
            total = max(1, self._center_split.height())
            self._center_split.setSizes([total, 0, 0])
            self._mic_before_chat = not self._muted
            if not self._muted:
                self._muted = True
                self.hud.muted = True
                self._style_mute_btn()
                self._apply_state("MUTED")
                self._log.append_log("SYS: Voice microphone paused for AI Chat.")
            self._conversation_title.setText("AI text chat")
            self._input.setPlaceholderText("Ask a question, solve a problem, or write code...")
            self._log.append_log("SYS: AI Chat mode — full focus chat interface, 3D face hidden.")
        else:
            if self._chat_dictating:
                self._stop_chat_dictation()
            if self._chat_restore_content:
                self._content_panel.show()
            if self._chat_restore_quiz:
                self._quiz_panel.show()
            if self._chat_restore_sizes:
                self._center_split.setSizes(self._chat_restore_sizes)
            if self._mic_before_chat and self._muted:
                self._toggle_mute()
            self._mic_before_chat = False
            self._conversation_title.setText("Voice conversation")
            self._input.setPlaceholderText("Message Charlie AI...")

            # Restore right 3D avatar panel
            if hasattr(self, "_right_panel") and self._right_panel is not None:
                self._right_panel.show()

            # Restore bottom feature cards
            if hasattr(self, "_center_cards_widget") and self._center_cards_widget is not None:
                self._center_cards_widget.show()

            # Restore greeting header
            if hasattr(self, "_chat_header_widget") and self._chat_header_widget is not None:
                self._chat_header_widget.hide()
            if hasattr(self, "_center_greet_widget") and self._center_greet_widget is not None:
                self._center_greet_widget.show()
            if hasattr(self, "_log") and not getattr(self._log, "_entries", []):
                if hasattr(self, "_welcome_widget") and self._welcome_widget is not None:
                    self._welcome_widget.show()
                    self._log.hide()

            self._log.append_log("SYS: Voice mode restored.")

        self._set_active_nav_index(1 if enabled else 0)

        self._style_mute_btn()
        self._refresh_chat_mode_buttons()
        self._input.setFocus()

    def _style_chat_dictation_button(self) -> None:
        if not hasattr(self, "_dictate_btn"):
            return
        if self._chat_dictating:
            text = "Stop"
            style = (
                f"background: {C.MUTED_C}; color: {C.WHITE}; "
                f"border: 1px solid {C.MUTED_C}; border-radius: 8px;")
        else:
            text = "Speak"
            style = (
                f"background: {C.PANEL2}; color: {C.PRI}; "
                f"border: 1px solid {C.PRI_DIM}; border-radius: 8px;")
        self._dictate_btn.setText(text)
        self._dictate_btn.setStyleSheet(style)
        if hasattr(self, "_chat_workspace"):
            self._chat_workspace.set_dictating(self._chat_dictating)

    def _toggle_chat_dictation(self) -> None:
        if not self._chat_mode:
            return
        if self._chat_dictating:
            self._stop_chat_dictation()
            return
        if self._chat_busy:
            self._log.append_log("SYS: Wait for the current answer before dictating another message.")
            return
        if getattr(self, "_starter_exhausted_locked", False):
            self._show_pricing_overlay(forced_paywall=True)
            return
        self._set_chat_dictation_state(True, "Listening - speak naturally, then pause.")
        if callable(self.on_chat_dictation):
            try:
                self.on_chat_dictation(True)
            except Exception as exc:
                self._set_chat_dictation_state(False, f"Dictation could not start: {exc}")
        else:
            self._set_chat_dictation_state(False, "Dictation service is not ready.")

    def _stop_chat_dictation(self) -> None:
        if callable(self.on_chat_dictation):
            try:
                self.on_chat_dictation(False)
            except Exception:
                pass
        self._set_chat_dictation_state(False, "Dictation stopped.")

    def _set_chat_dictation_state(self, active: bool, message: str = "") -> None:
        self._chat_dictating = bool(active and self._chat_mode)
        self._style_chat_dictation_button()
        self._style_mute_btn()
        if self._chat_dictating:
            self._apply_state("LISTENING")
        elif self._chat_mode and not self._chat_busy:
            self._apply_state("MUTED")
        if message:
            self._log.append_log(f"SYS: {message}")

    def _apply_chat_dictation_text(self, text: str) -> None:
        self._set_chat_dictation_state(False)
        text = str(text or "").strip()
        if not self._chat_mode or not text:
            return
        existing = self._input.text().strip()
        self._input.setText(f"{existing} {text}".strip())
        self._input.setCursorPosition(len(self._input.text()))
        self._input.setFocus()
        self._log.append_log("SYS: Dictation added to the message box. Review it, then press Send.")

    def _use_chat_prompt(self, prompt: str) -> None:
        self._input.setText(str(prompt or ""))
        self._input.setFocus()
        self._input.setCursorPosition(len(self._input.text()))

    def _start_new_chat(self) -> None:
        if self._chat_busy:
            return
        if callable(self.on_new_chat):
            self.on_new_chat()
        self._log.clear()
        self._log.append_log(f"SYS: New AI chat started with {self._assistant_name}.")
        self._chat_workspace.set_busy(False)

    def _set_chat_busy(self, busy: bool) -> None:
        if busy and self._chat_dictating:
            self._stop_chat_dictation()
        self._chat_busy = bool(busy)
        self._input.setEnabled(not self._chat_busy)
        self._send_btn.setEnabled(not self._chat_busy)
        if self._chat_busy:
            self._send_btn.setText("")
            self._send_btn.setIcon(_render_svg_icon("sparkles", 15, "#818cf8"))
            self._send_btn.setToolTip("Charlie is thinking...")
        else:
            self._send_btn.setText("")
            self._send_btn.setIcon(_render_svg_icon("send_arrow", 15, "#ffffff"))
            self._send_btn.setToolTip("Send Message (Enter)")
        if self._chat_mode:
            self._apply_state("THINKING" if self._chat_busy else "MUTED")
            self._chat_workspace.set_busy(self._chat_busy)
        if not self._chat_busy:
            self._input.setFocus()

    def _build_content_panel(self) -> QWidget:
        """
        Collapsible panel below the HUD — shows search results, news, briefings.
        Hidden by default; appears when show_content() is called.
        """
        w = QWidget()
        w.setObjectName("ContentPanel")
        w.setStyleSheet(f"""
            QWidget#ContentPanel {{
                background: {C.PANEL};
                border-top: 1px solid {C.BORDER_B};
            }}
        """)
        w.hide()

        lay = QVBoxLayout(w)
        lay.setContentsMargins(16, 12, 16, 14)
        lay.setSpacing(8)

        # ── header row ───────────────────────────────────────────────────────
        hdr = QHBoxLayout(); hdr.setSpacing(6)

        dot = QLabel("◈")
        dot.setFont(QFont(APP_FONT_NAME, 10, QFont.Weight.DemiBold))
        dot.setStyleSheet(f"color: {C.PRI}; background: transparent;")
        hdr.addWidget(dot)

        self._content_title_lbl = QLabel("BRIEFING")
        self._content_title_lbl.setFont(QFont(APP_FONT_NAME, 11, QFont.Weight.DemiBold))
        self._content_title_lbl.setStyleSheet(
            f"color: {C.WHITE}; background: transparent;"
        )
        hdr.addWidget(self._content_title_lbl)
        hdr.addStretch()

        self._content_ts_lbl = QLabel("")
        self._content_ts_lbl.setFont(QFont(APP_FONT_NAME, 8))
        self._content_ts_lbl.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        hdr.addWidget(self._content_ts_lbl)

        dismiss = QPushButton("DISMISS  ✕")
        dismiss.setFont(QFont(APP_FONT_NAME, 8, QFont.Weight.Medium))
        dismiss.setFixedHeight(24)
        dismiss.setCursor(Qt.CursorShape.PointingHandCursor)
        dismiss.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {C.TEXT_DIM};
                border: 1px solid {C.BORDER}; border-radius: 6px; padding: 0 7px;
            }}
            QPushButton:hover {{ color: {C.TEXT}; border-color: {C.BORDER_B}; }}
        """)
        dismiss.clicked.connect(w.hide)
        hdr.addWidget(dismiss)
        lay.addLayout(hdr)

        # ── separator ─────────────────────────────────────────────────────────
        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {C.BORDER};"); lay.addWidget(sep)

        # ── text display ──────────────────────────────────────────────────────
        self._content_display = QTextEdit()
        self._content_display.setReadOnly(True)
        self._content_display.setFont(QFont(APP_FONT_NAME, 10))
        self._content_display.setMinimumHeight(60)
        self._content_display.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self._content_display.setStyleSheet(f"""
            QTextEdit {{
                background: {C.DARK};
                color: {C.TEXT};
                border: 1px solid {C.BORDER};
                border-radius: 10px;
                padding: 10px 12px;
                selection-background-color: {C.PRI_GHO};
            }}
            QScrollBar:vertical {{
                background: {C.BG}; width: 6px; border: none;
            }}
            QScrollBar::handle:vertical {{
                background: {C.BORDER_B}; border-radius: 8px; min-height: 16px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0; border: none;
            }}
        """)
        lay.addWidget(self._content_display)

        return w

    def _show_content(self, title: str, text: str):
        """Slot — runs on Qt main thread. Updates and shows the content panel."""
        import time as _time
        # The panel opens below the head, so the head looks down at it. It is a
        # tiny thing that answers "did that land?" before you read a word.
        self.hud.glance(0.0, -0.85, hold=1.3)
        self._content_title_lbl.setText(title.upper()[:48])
        self._content_ts_lbl.setText(_time.strftime("%H:%M:%S"))
        self._content_display.setPlainText(text)
        self._content_display.moveCursor(
            self._content_display.textCursor().MoveOperation.Start
        )
        first_show = not self._content_panel.isVisible()
        self._content_panel.show()
        if first_show:
            total = self._center_split.height()
            self._center_split.setSizes([max(total - 220, 120), 220])

    # ── document review ──────────────────────────────────────────────────────
    # Rendered as rich text into the content panel that already exists, rather
    # than into a panel of its own. A review is read, not clicked, so QTextEdit
    # gives scrolling, selection and copy for nothing, and the HUD gains no
    # widget it has to lay out. Severity decides colour and order here because
    # that is presentation; the plugin supplies no styling and knows no palette,
    # which is also what lets a re-theme repaint a review correctly.

    # Severity is marked by a symbol and a colour, not by a word. The findings
    # themselves are in the user's language, and "[SERIOUS]" sitting inside a
    # Turkish sentence is the kind of seam this project tries not to have —
    # while translating the tag would mean a table per language, which is worse.
    # A shape carries it in every language, and shape plus colour still reads
    # for someone who cannot separate red from amber. What the marks mean
    # arrives the way everything else does: CHARLIE says it out loud.
    _REVIEW_MARKS = {"serious": ("RED", "▲"), "caution": ("ACC2", "●"), "note": ("PRI_DIM", "·")}

    @staticmethod
    def _esc(s) -> str:
        return (str(s or "").replace("&", "&amp;").replace("<", "&lt;")
                .replace(">", "&gt;").replace("\n", "<br>"))

    def _show_review(self, title: str, summary: str, findings, unclear):
        """Slot — Qt main thread. Lays a document review into the content panel."""
        e = self._esc
        parts = [f'<div style="color:{C.TEXT}; font-family:\'Segoe UI Variable Text\', \'Segoe UI\', \'Inter\', sans-serif;">']

        if summary:
            parts.append(
                f'<div style="color:{C.WHITE}; border-left:2px solid {C.PRI};'
                f' padding-left:8px; margin-bottom:10px;">{e(summary)}</div>')

        for f in (findings or []):
            key, mark = self._REVIEW_MARKS.get(f.get("severity"), ("PRI_DIM", "·"))
            colour = getattr(C, key)
            parts.append(f'<div style="margin-bottom:11px;">')
            parts.append(
                f'<span style="color:{colour}; font-weight:bold;">{mark}</span> '
                f'<span style="color:{C.WHITE}; font-weight:bold;">'
                f'{e(f.get("heading"))}</span>')
            if f.get("detail"):
                parts.append(f'<div style="margin-left:12px;">{e(f["detail"])}</div>')
            if f.get("quote"):
                # The document's own wording, visually separated from the
                # explanation so the two are never mistaken for each other.
                parts.append(
                    f'<div style="margin-left:12px; color:{C.TEXT_DIM};'
                    f' border-left:1px solid {C.BORDER}; padding-left:7px;">'
                    f'&ldquo;{e(f["quote"])}&rdquo;</div>')
            if f.get("suggestion"):
                parts.append(
                    f'<div style="margin-left:12px; color:{C.PRI};">'
                    f'&rarr; {e(f["suggestion"])}</div>')
            parts.append('</div>')

        if unclear:
            parts.append(
                f'<div style="margin-top:6px; border-top:1px solid {C.BORDER};'
                f' padding-top:7px; color:{C.TEXT_MED};">'
                'The document does not settle:</div>')
            for u in unclear:
                parts.append(
                    f'<div style="margin-left:12px; color:{C.TEXT_MED};">'
                    f'&middot; {e(u)}</div>')
        parts.append('</div>')

        import time as _time
        self.hud.glance(0.0, -0.85, hold=1.3)
        # Left as written, not upper-cased. The other content-panel titles are
        # the app's own English labels, but this one is the document's name in
        # the user's language, and str.upper() applies English casing rules to
        # it: Turkish "Sözleşmesi" comes back "SÖZLEŞMESI", having lost the
        # dotted capital İ. Python has no locale-aware upper to reach for, and
        # imposing one language's rules on all of them is the bug, not the fix.
        self._content_title_lbl.setText((title or "Document")[:48])
        self._content_ts_lbl.setText(_time.strftime("%H:%M:%S"))
        self._content_display.setHtml("".join(parts))
        self._content_display.moveCursor(
            self._content_display.textCursor().MoveOperation.Start)
        first_show = not self._content_panel.isVisible()
        self._content_panel.show()
        if first_show:
            total = self._center_split.height()
            self._center_split.setSizes([max(total - 260, 120), 260, 0])

    # ── quiz panel ───────────────────────────────────────────────────────────
    # An interactive twin of the content panel. The plugin only ever hands over
    # questions; everything about asking, marking and reporting happens here,
    # and the finished result is pushed back into the conversation the same way
    # a dropped file is — as a message CHARLIE reads and responds to. That keeps
    # the tool call short (it returns the moment the board is up) and leaves the
    # talking to the assistant, in the user's own language.

    def _quiz_btn(self, text: str, primary: bool = False) -> QPushButton:
        b = QPushButton(text)
        b.setFont(QFont(APP_FONT_NAME, 8))
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setMinimumHeight(24)
        edge = C.BORDER_B if primary else C.BORDER
        col = C.PRI if primary else C.TEXT_MED
        b.setStyleSheet(f"""
            QPushButton {{
                background: {C.PANEL2}; color: {col};
                border: 1px solid {edge}; border-radius: 2px;
                padding: 3px 9px; text-align: left;
            }}
            QPushButton:hover {{ color: {C.WHITE}; border-color: {C.PRI_DIM}; }}
            QPushButton:disabled {{ color: {C.TEXT_DIM}; border-color: {C.BORDER}; }}
        """)
        return b

    def _build_quiz_panel(self) -> QWidget:
        w = QWidget()
        w.setObjectName("QuizPanel")
        w.setStyleSheet(f"""
            QWidget#QuizPanel {{
                background: {C.PANEL};
                border-top: 1px solid {C.BORDER_B};
            }}
        """)
        w.hide()

        lay = QVBoxLayout(w)
        lay.setContentsMargins(12, 7, 12, 8)
        lay.setSpacing(6)

        hdr = QHBoxLayout(); hdr.setSpacing(6)
        dot = QLabel("◈")
        dot.setFont(QFont(APP_FONT_NAME, 9, QFont.Weight.Bold))
        dot.setStyleSheet(f"color: {C.PRI}; background: transparent;")
        hdr.addWidget(dot)

        self._quiz_title_lbl = QLabel("QUIZ")
        self._quiz_title_lbl.setFont(QFont(APP_FONT_NAME, 8, QFont.Weight.Bold))
        self._quiz_title_lbl.setStyleSheet(
            f"color: {C.PRI}; background: transparent; letter-spacing: 1px;")
        hdr.addWidget(self._quiz_title_lbl)
        hdr.addStretch()

        self._quiz_count_lbl = QLabel("")
        self._quiz_count_lbl.setFont(QFont(APP_FONT_NAME, 7))
        self._quiz_count_lbl.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        hdr.addWidget(self._quiz_count_lbl)

        quit_btn = QPushButton("DISMISS  ✕")
        quit_btn.setFont(QFont(APP_FONT_NAME, 7))
        quit_btn.setFixedHeight(18)
        quit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        quit_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {C.TEXT_DIM};
                border: 1px solid {C.BORDER}; border-radius: 2px; padding: 0 5px;
            }}
            QPushButton:hover {{ color: {C.TEXT}; border-color: {C.BORDER_B}; }}
        """)
        quit_btn.clicked.connect(self._hide_quiz)
        hdr.addWidget(quit_btn)
        lay.addLayout(hdr)

        rule = QFrame(); rule.setFixedHeight(1)
        rule.setStyleSheet(f"background: {C.BORDER};")
        lay.addWidget(rule)

        self._quiz_q_lbl = QLabel("")
        self._quiz_q_lbl.setWordWrap(True)
        self._quiz_q_lbl.setFont(QFont(APP_FONT_NAME, 9))
        self._quiz_q_lbl.setStyleSheet(f"color: {C.WHITE}; background: transparent;")
        lay.addWidget(self._quiz_q_lbl)

        self._quiz_answers = QWidget()
        self._quiz_answers.setStyleSheet("background: transparent;")
        self._quiz_answers_lay = QVBoxLayout(self._quiz_answers)
        self._quiz_answers_lay.setContentsMargins(0, 2, 0, 0)
        self._quiz_answers_lay.setSpacing(4)
        lay.addWidget(self._quiz_answers)

        self._quiz_note_lbl = QLabel("")
        self._quiz_note_lbl.setWordWrap(True)
        self._quiz_note_lbl.setFont(QFont(APP_FONT_NAME, 8))
        self._quiz_note_lbl.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent;")
        self._quiz_note_lbl.hide()
        lay.addWidget(self._quiz_note_lbl)

        foot = QHBoxLayout()
        foot.addStretch()
        self._quiz_next_btn = self._quiz_btn("NEXT  →", primary=True)
        self._quiz_next_btn.setFixedWidth(110)
        self._quiz_next_btn.clicked.connect(self._quiz_next)
        self._quiz_next_btn.hide()
        foot.addWidget(self._quiz_next_btn)
        lay.addLayout(foot)

        self._quiz = None
        return w

    def _show_quiz(self, topic: str, questions, grader=None):
        """Slot — Qt main thread. Puts a fresh quiz on the board."""
        if not questions:
            return
        self._quiz = {
            "topic": topic or "",
            "questions": list(questions),
            "grader": grader,
            "i": 0,
            "results": [],
            "answered": False,
        }
        self._quiz_title_lbl.setText((topic or "quiz").upper()[:48])
        self.hud.glance(0.0, -0.85, hold=1.3)
        first_show = not self._quiz_panel.isVisible()
        self._quiz_panel.show()
        if first_show:
            total = self._center_split.height()
            self._center_split.setSizes([max(total - 250, 120), 0, 250])
        self._quiz_render()

    def _hide_quiz(self):
        self._quiz = None
        self._quiz_panel.hide()

    def _quiz_clear_answers(self):
        while self._quiz_answers_lay.count():
            item = self._quiz_answers_lay.takeAt(0)
            child = item.widget()
            if child is not None:
                child.setParent(None)
                child.deleteLater()

    def _quiz_render(self):
        if not self._quiz:
            return
        questions = self._quiz.get("questions") or []
        idx = int(self._quiz.get("i", 0))
        if not questions or idx >= len(questions):
            return
        q = questions[idx]
        if not isinstance(q, dict):
            return
        n, total = idx + 1, len(questions)
        self._quiz_count_lbl.setText(f"{n} / {total}")
        self._quiz_q_lbl.setText(str(q.get("question", "")))
        self._quiz_note_lbl.hide()
        self._quiz_next_btn.hide()
        self._quiz["answered"] = False
        self._quiz_clear_answers()

        opts = q.get("options") or []
        if opts and isinstance(opts, list):
            for text in opts:
                b = self._quiz_btn("   " + str(text))
                b.clicked.connect(lambda _=False, t=str(text): self._quiz_submit(t))
                self._quiz_answers_lay.addWidget(b)
        else:
            row = QWidget(); row.setStyleSheet("background: transparent;")
            h = QHBoxLayout(row); h.setContentsMargins(0, 0, 0, 0); h.setSpacing(6)
            field = QLineEdit()
            field.setFont(QFont(APP_FONT_NAME, 9))
            field.setPlaceholderText("your answer")
            field.setStyleSheet(f"""
                QLineEdit {{
                    background: {C.PANEL2}; color: {C.WHITE};
                    border: 1px solid {C.BORDER}; border-radius: 2px; padding: 4px 7px;
                }}
                QLineEdit:focus {{ border-color: {C.PRI_DIM}; }}
            """)
            send = self._quiz_btn("ANSWER", primary=True)
            send.setFixedWidth(90)
            field.returnPressed.connect(lambda: self._quiz_submit(field.text()))
            send.clicked.connect(lambda: self._quiz_submit(field.text()))
            h.addWidget(field, stretch=1)
            h.addWidget(send)
            self._quiz_answers_lay.addWidget(row)
            field.setFocus()

    def _quiz_submit(self, given: str):
        if not self._quiz or self._quiz.get("answered"):
            return
        self._quiz["answered"] = True
        questions = self._quiz.get("questions") or []
        idx = int(self._quiz.get("i", 0))
        if not questions or idx >= len(questions):
            return
        q = questions[idx]
        if not isinstance(q, dict):
            return
        grader = self._quiz.get("grader")
        verdict = None
        if callable(grader):
            try:
                verdict = grader(q, given)
            except Exception:
                verdict = None
        results = self._quiz.get("results")
        if isinstance(results, list):
            results.append({
                "question": q.get("question", ""),
                "type": q.get("type", ""),
                "given": str(given or "").strip(),
                "answer": q.get("answer", ""),
                "correct": verdict,
            })

        for i in range(self._quiz_answers_lay.count()):
            item = self._quiz_answers_lay.itemAt(i)
            if item is not None and item.widget() is not None:
                item.widget().setEnabled(False)

        if verdict is True:
            mark, colour = "✓  correct", C.GREEN
        elif verdict is False:
            mark, colour = "✕  " + str(q.get("answer", "")), C.RED
        else:
            # Open answers and near-miss gap-fills are CHARLIE's to judge. Saying
            # so is honest; marking it wrong here would be a guess.
            mark, colour = "…  noted — I'll go over this one with you", C.ACC2
        note = str(q.get("note") or "")
        self._quiz_note_lbl.setText(mark + (("\n" + note) if note else ""))
        self._quiz_note_lbl.setStyleSheet(f"color: {colour}; background: transparent;")
        self._quiz_note_lbl.show()

        last = idx >= len(questions) - 1
        self._quiz_next_btn.setText("FINISH  →" if last else "NEXT  →")
        self._quiz_next_btn.show()
        self._quiz_next_btn.setFocus()

    def _quiz_next(self):
        if not self._quiz:
            return
        questions = self._quiz.get("questions") or []
        idx = int(self._quiz.get("i", 0))
        if idx >= len(questions) - 1:
            self._quiz_finish()
        else:
            self._quiz["i"] = idx + 1
            self._quiz_render()

    def _quiz_finish(self):
        if not self._quiz:
            return
        topic = str(self._quiz.get("topic", ""))
        results = self._quiz.get("results")
        if not isinstance(results, list):
            results = []
        right = sum(1 for r in results if isinstance(r, dict) and r.get("correct") is True)
        unsure = sum(1 for r in results if isinstance(r, dict) and r.get("correct") is None)
        total = len(results)
        self._quiz_panel.hide()
        self._quiz = None

        self._log.append_log(f"QUIZ: {topic or 'quiz'} — {right}/{total} correct")

        # Hand it back to CHARLIE as a message, not as a tool return: the tool
        # call ended minutes ago. This is the same channel a dropped file uses.
        lines = [f"[QUIZ_DONE] topic={topic or 'general'} | "
                 f"auto-marked {right}/{total} correct"
                 + (f", {unsure} still need your marking" if unsure else "")]
        for i, r in enumerate(results, 1):
            if isinstance(r, dict):
                state = ("correct" if r.get("correct") is True
                         else "wrong" if r.get("correct") is False else "NEEDS MARKING")
                lines.append(
                    f"{i}. [{r.get('type', '')}] {r.get('question', '')} | they answered: "
                    f"{r.get('given', '') or '(blank)'} | expected: {r.get('answer', '')} | {state}")
        lines.append(
            "Mark every question flagged NEEDS MARKING yourself — accept an answer "
            "that means the same thing. Then tell them how they did in their own "
            "language: the score, what they got wrong and why, in a couple of "
            "sentences. Offer another round only if it fits. "
            "Remember something only if it would still matter next week — that they "
            "are working through a subject, or keep missing the same thing. A score "
            "from one session is not worth a memory, and a memory per quiz would "
            "bury the things that are.")
        msg = "\n".join(lines)
        if self.on_text_command:
            threading.Thread(target=self.on_text_command, args=(msg,), daemon=True).start()

    def _build_footer(self) -> QWidget:
        w = QWidget()
        w.setFixedHeight(32)
        w.setStyleSheet(f"background: {C.DARK}; border-top: 1px solid {C.BORDER};")
        lay = QHBoxLayout(w)
        lay.setContentsMargins(20, 0, 20, 0)
        lay.setSpacing(0)

        def _fl(txt, color=C.TEXT_MED):
            l = QLabel(txt)
            l.setFont(QFont(APP_FONT_NAME, 8))
            l.setStyleSheet(f"color: {color}; background: transparent;")
            return l

        # Version badge
        _ver = QLabel(f"v{RELEASE_VERSION}")
        _ver.setFont(QFont(APP_FONT_NAME, 7, QFont.Weight.Bold))
        _ver.setStyleSheet(f"color: {C.PRI_DIM}; background: {C.PRI_GHO}; border: 1px solid {C.BORDER}; border-radius: 6px; padding: 1px 6px;")
        lay.addWidget(_ver)
        lay.addSpacing(10)

        # Keyboard shortcuts hint
        lay.addWidget(_fl("F4  Mute"))
        _sep1 = QLabel("·")
        _sep1.setFont(QFont(APP_FONT_NAME, 8))
        _sep1.setStyleSheet(f"color: {C.BORDER}; background: transparent; padding: 0 4px;")
        lay.addWidget(_sep1)
        lay.addWidget(_fl("F11  Fullscreen"))
        _sep2 = QLabel("·")
        _sep2.setFont(QFont(APP_FONT_NAME, 8))
        _sep2.setStyleSheet(f"color: {C.BORDER}; background: transparent; padding: 0 4px;")
        lay.addWidget(_sep2)
        lay.addWidget(_fl("Ctrl+Space  Command Bar"))
        lay.addStretch()

        # Status indicator dot
        _status_dot = QLabel("●")
        _status_dot.setFont(QFont(APP_FONT_NAME, 7))
        _status_dot.setStyleSheet(f"color: {C.GREEN}; background: transparent; padding-right: 4px;")
        lay.addWidget(_status_dot)

        # Branded footer text
        _brand_lbl = QLabel(f"{self._assistant_name.upper()} — Personal AI Assistant")
        _brand_lbl.setFont(QFont(APP_FONT_NAME, 8, QFont.Weight.DemiBold))
        _brand_lbl.setStyleSheet(f"color: {C.PRI_DIM}; background: transparent; letter-spacing: 0.3px;")
        lay.addWidget(_brand_lbl)
        return w

    def _on_file_selected(self, path: str):
        self._current_file = path
        p    = Path(path)
        cat  = _file_category(p)
        icon, _ = _FILE_ICONS.get(cat, _FILE_ICONS["unknown"])
        size = _fmt_size(p.stat().st_size)
        self._file_hint.setText(f"{icon}  {p.name}  ·  {size}  ·  Tell {self._assistant_name} what to do with it")
        self._log.append_log(f"FILE: {p.name} ({size}) loaded")
        callback = self.on_chat_command if self._chat_mode else self.on_text_command
        if callback:
            msg = (
                f"[FILE_UPLOADED] path={path} | name={p.name} | "
                f"type={p.suffix.lstrip('.')} | size={size} | "
                f"Briefly tell the user you can see the file '{p.name}' "
                f"({size}) has been uploaded and ask what they'd like to do with it."
            )
            threading.Thread(target=callback, args=(msg,), daemon=True).start()

    def notify_phone_connected(self) -> None:
        if self._remote_overlay and self._remote_overlay.isVisible():
            self._remote_overlay.mark_connected()

    def _open_remote(self):
        if not self.on_remote_clicked:
            self._log.append_log("SYS: Dashboard not running — remote unavailable.")
            return
        result = self.on_remote_clicked()
        if not result:
            self._log.append_log("SYS: Could not generate remote key.")
            return
        url    = result[0]
        key    = result[1]
        auto   = result[2] if len(result) >= 3 else ""
        manual = result[3] if len(result) >= 4 else url
        if self._remote_overlay:
            self._remote_overlay._do_close()
        cw  = self.centralWidget()
        ow, oh = RemoteKeyOverlay._OW, RemoteKeyOverlay._OH
        ov  = RemoteKeyOverlay(url, key, auto_login_url=auto, manual_url=manual,
                               expiry_secs=600, parent=cw)
        ov.set_new_key_callback(self.on_remote_clicked)
        ov.setGeometry(
            (cw.width()  - ow) // 2,
            (cw.height() - oh) // 2,
            ow, oh,
        )
        ov.closed.connect(lambda: setattr(self, '_remote_overlay', None))
        ov.show()
        self._remote_overlay = ov
        self._log.append_log(f"SYS: Remote key generated — manual: {manual or url}")

    # ── Auto-start ──────────────────────────────────────────────────────────────

    def _check_autostart(self) -> bool:
        """Returns True if auto-start is currently registered on this OS."""
        try:
            if _OS == "Windows":
                import winreg
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_READ)
                try:
                    winreg.QueryValueEx(key, "CHARLIE_AI")
                    return True
                except FileNotFoundError:
                    return False
                finally:
                    winreg.CloseKey(key)
            elif _OS == "Darwin":
                return (Path.home() / "Library" / "LaunchAgents"
                        / "com.charlie.assistant.plist").exists()
            else:
                return (Path.home() / ".config" / "autostart" / "charlie.desktop").exists()
        except Exception:
            return False

    def _toggle_autostart(self):
        currently_on = self._check_autostart()
        try:
            script = str(Path(__file__).resolve().parent / "main.py")
            if _OS == "Windows":
                import winreg
                reg = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_ALL_ACCESS)
                if currently_on:
                    winreg.DeleteValue(reg, "CHARLIE_AI")
                else:
                    pythonw = Path(sys.executable).parent / "pythonw.exe"
                    exe = str(pythonw if pythonw.exists() else sys.executable)
                    winreg.SetValueEx(reg, "CHARLIE_AI", 0, winreg.REG_SZ,
                                      f'"{exe}" "{script}"')
                winreg.CloseKey(reg)
            elif _OS == "Darwin":
                plist_dir = Path.home() / "Library" / "LaunchAgents"
                plist_dir.mkdir(parents=True, exist_ok=True)
                plist = plist_dir / "com.charlie.assistant.plist"
                if currently_on:
                    plist.unlink(missing_ok=True)
                else:
                    plist.write_text(
                        '<?xml version="1.0" encoding="UTF-8"?>\n'
                        '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
                        '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
                        '<plist version="1.0"><dict>\n'
                        '  <key>Label</key><string>com.charlie.assistant</string>\n'
                        '  <key>ProgramArguments</key><array>\n'
                        f'    <string>{sys.executable}</string>\n'
                        f'    <string>{script}</string>\n'
                        '  </array>\n'
                        '  <key>RunAtLoad</key><true/>\n'
                        '</dict></plist>\n'
                    )
            else:
                desk_dir = Path.home() / ".config" / "autostart"
                desk_dir.mkdir(parents=True, exist_ok=True)
                desk = desk_dir / "charlie.desktop"
                if currently_on:
                    desk.unlink(missing_ok=True)
                else:
                    desk.write_text(
                        "[Desktop Entry]\n"
                        f"Name={self._assistant_name}\n"
                        f"Exec={sys.executable} {script}\n"
                        "Type=Application\nTerminal=false\n"
                        "X-GNOME-Autostart-enabled=true\n"
                    )
            enabled = not currently_on
            self._update_autostart_btn(enabled)
            self._log.append_log(
                f"SYS: Auto-start {'enabled' if enabled else 'disabled'}.")
        except Exception as e:
            self._log.append_log(f"ERR: Auto-start failed — {e}")

    def _update_autostart_btn(self, enabled: bool):
        if not hasattr(self, '_autostart_btn'):
            return
        if enabled:
            self._autostart_btn.setText("◉  AUTO-START: ON")
            self._autostart_btn.setStyleSheet(f"""
                QPushButton {{
                    background: #001a08; color: {C.GREEN};
                    border: 1px solid {C.GREEN_D}; border-radius: 8px;
                }}
                QPushButton:hover {{ background: #002010; }}
            """)
        else:
            self._autostart_btn.setText("◉  AUTO-START: OFF")
            self._autostart_btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent; color: {C.TEXT_DIM};
                    border: 1px solid {C.BORDER}; border-radius: 8px;
                }}
                QPushButton:hover {{ color: {C.TEXT}; border: 1px solid {C.BORDER_B}; }}
            """)

    def _toggle_brief(self):
        from memory.config_manager import get_brief_enabled, save_brief_enabled
        new_val = not get_brief_enabled()
        save_brief_enabled(new_val)
        self._update_brief_btn(new_val)

    # ── Wake word settings ───────────────────────────────────────────────────

    def _wake_state(self) -> dict:
        """Combined state for the two wake-word buttons. Readiness is a cheap,
        deterministic on-disk check now (see core.wake_word.is_ready), so there
        is nothing to cache — the button never flickers to a stale value."""
        if self.wake_get_state:
            try:
                s = self.wake_get_state()
                return {"ready": bool(s.get("ready")),
                        "enabled": bool(s.get("enabled")),
                        "awake": bool(s.get("awake"))}
            except Exception:
                pass
        # Before CharlieLive has wired its callback (drawer built at startup).
        ready, enabled = False, False
        try:
            from core.wake_word import is_ready
            from memory.config_manager import get_wake_word_enabled
            ready, enabled = is_ready(), get_wake_word_enabled()
        except Exception:
            pass
        return {"ready": ready, "enabled": enabled, "awake": True}

    def _refresh_wake_btns(self):
        if not hasattr(self, '_wake_btn'):
            return
        st = self._wake_state()
        _on = f"""
            QPushButton {{ background: #001a08; color: {C.GREEN};
                border: 1px solid {C.GREEN_D}; border-radius: 8px;
                text-align: left; padding: 0 8px; }}
            QPushButton:hover {{ background: #002010; }}"""
        _off = f"""
            QPushButton {{ background: transparent; color: {C.TEXT_DIM};
                border: 1px solid {C.BORDER}; border-radius: 8px;
                text-align: left; padding: 0 8px; }}
            QPushButton:hover {{ color: {C.TEXT}; border: 1px solid {C.BORDER_B}; }}"""
        self._wake_btn.setEnabled(True)
        if not st["ready"]:
            self._wake_btn.setText("⬇  WAKE WORD: DOWNLOAD")
            self._wake_btn.setStyleSheet(_off)
            self._wake_sleep_btn.hide()
        elif st["enabled"]:
            self._wake_btn.setText("🎙  WAKE WORD: ON")
            self._wake_btn.setStyleSheet(_on)
            self._wake_sleep_btn.show()
            self._wake_sleep_btn.setText("😴  SLEEP NOW" if st["awake"] else "👂  WAKE NOW")
            self._wake_sleep_btn.setStyleSheet(_off)
        else:
            self._wake_btn.setText("🎙  WAKE WORD: OFF")
            self._wake_btn.setStyleSheet(_off)
            self._wake_sleep_btn.hide()

        # Plain labels make the setting understandable without decoding icons
        # or terminal-style status text.
        if not st["ready"]:
            self._wake_btn.setText("Set up wake word")
        elif st["enabled"]:
            self._wake_btn.setText("Wake word is on")
            self._wake_sleep_btn.setText("Sleep Charlie" if st["awake"] else "Wake Charlie")
        else:
            self._wake_btn.setText("Wake word is off")

    def _refresh_talk_btns(self):
        """Repaint the push-to-talk row from the saved setting."""
        if not hasattr(self, "_ptt_btn"):
            return
        from core.hotkey import chord_label
        from memory.config_manager import get_push_to_talk_enabled
        _on = f"""
            QPushButton {{ background: #001a08; color: {C.GREEN};
                border: 1px solid {C.GREEN_D}; border-radius: 8px;
                text-align: left; padding: 0 8px; }}
            QPushButton:hover {{ background: #002010; }}"""
        _off = f"""
            QPushButton {{ background: transparent; color: {C.TEXT_DIM};
                border: 1px solid {C.BORDER}; border-radius: 8px;
                text-align: left; padding: 0 8px; }}
            QPushButton:hover {{ color: {C.TEXT}; border: 1px solid {C.BORDER_B}; }}"""

        ptt = get_push_to_talk_enabled()
        self._ptt_btn.setText(f"🎚  PUSH-TO-TALK: {chord_label()}" if ptt
                              else "🎚  PUSH-TO-TALK: OFF")
        self._ptt_btn.setStyleSheet(_on if ptt else _off)
        self._ptt_btn.setToolTip(
            "Microphone stays closed until you hold the key — nothing is sent "
            "while you are not holding it." if ptt
            else "Hold a key to talk instead of streaming the mic continuously.")
        self._ptt_btn.setText(
            f"Push to talk: hold {chord_label()}" if ptt else "Push to talk is off"
        )

    def _refresh_hud_btn(self):
        if not hasattr(self, "_hud_btn") or self._hud_btn is None:
            return
        from memory.config_manager import get_hud_style
        style_key = get_hud_style()
        style = f"""
            QPushButton {{ background: {C.PANEL2}; color: {C.PRI};
                border: 1px solid {C.BORDER_A}; border-radius: 8px;
                text-align: left; padding: 0 8px; }}
            QPushButton:hover {{ color: {C.WHITE}; border: 1px solid {C.BORDER_B}; }}"""
        if style_key == "holo":
            label = "Appearance: Classic Hologram"
            tip = "Classic holographic vector wireframe head. Tap to switch to Reactor Core."
        else:
            label = "Appearance: Reactor Core"
            tip = "High-tech audio-reactive reactor core. Tap to switch to Classic Hologram."

        self._hud_btn.setText(label)
        self._hud_btn.setStyleSheet(style)
        self._hud_btn.setToolTip(tip)

    def _refresh_voice_profile_btns(self):
        """Reflect the saved male/female voice profile in Settings."""
        if not hasattr(self, "_voice_profile_btns"):
            return
        from memory.config_manager import get_assistant_persona, get_persona_voice
        active_persona = get_assistant_persona()

        # The commercial engine is initialized in the background. Importing and
        # validating it here used to stall startup while this hidden drawer was
        # being built.
        comm_engine = self._commercial_engine

        for persona, button in self._voice_profile_btns.items():
            active = persona == active_persona
            button.setChecked(active)
            voice_name = get_persona_voice(persona)
            is_allowed = True
            lock_msg = ""
            if comm_engine:
                is_allowed, lock_msg = comm_engine.verify_voice_access(persona)

            if not is_allowed:
                button.setText(f"{persona.upper()} 🔒")
                button.setToolTip(f"{persona.title()} voice: {lock_msg}")
            else:
                button.setText(persona.upper())
                button.setToolTip(f"Use the {persona} assistant avatar and {voice_name} voice.")

            if active:
                button.setStyleSheet(f"""
                    QPushButton {{ background: {C.GREEN_D}; color: {C.WHITE};
                        border: 1px solid {C.GREEN}; border-radius: 8px; }}
                    QPushButton:hover {{ background: {C.PRI_GHO}; color: {C.WHITE}; }}""")
            elif not is_allowed:
                button.setStyleSheet(f"""
                    QPushButton {{ background: {C.PANEL}; color: {C.TEXT_DIM};
                        border: 1px dashed {C.BORDER_A}; border-radius: 8px; }}
                    QPushButton:hover {{ color: {C.ACC}; border-color: {C.ACC}; }}""")
            else:
                button.setStyleSheet(f"""
                    QPushButton {{ background: {C.PANEL2}; color: {C.PRI};
                        border: 1px solid {C.BORDER_A}; border-radius: 8px; }}
                    QPushButton:hover {{ color: {C.WHITE}; background: {C.PRI_GHO};
                        border-color: {C.PRI_DIM}; }}""")

    def test_voice_sample(self, text: str = "Hello! Charlie voice engine is operational.") -> None:
        """Preview synthesized voice sample in background thread."""
        def _worker():
            try:
                from core.tts import create_tts_player
                from memory.config_manager import load_api_keys, get_custom_voice_id
                cfg = load_api_keys()
                custom_id = get_custom_voice_id()
                if custom_id:
                    cfg["tts_engine"] = "elevenlabs"
                    cfg["tts_voice"] = custom_id
                player = create_tts_player(cfg)
                player.speak(text)
                self._log_sig.emit(f"SYS: Voice test sample played successfully.")
            except Exception as e:
                self._log_sig.emit(f"ERR: Voice test failed  -  {e}")

        threading.Thread(target=_worker, daemon=True, name="voice-test-thread").start()

    def _refresh_personal_controls(self):

        """Refresh active family profile and companion behavior controls."""
        if not hasattr(self, "_profile_combo"):
            return
        from memory.personal_hub import load_hub
        from memory.profile_manager import list_profiles
        profiles = list_profiles()
        self._profile_combo.blockSignals(True)
        self._profile_combo.clear()
        active_index = 0
        for index, profile in enumerate(profiles):
            self._profile_combo.addItem(profile["name"], profile["id"])
            if profile.get("active"):
                active_index = index
        self._profile_combo.setCurrentIndex(active_index)
        self._profile_combo.blockSignals(False)

        mode = load_hub().get("companion", {}).get("mode", "advice")
        mode_index = self._companion_mode_combo.findData(mode)
        self._companion_mode_combo.blockSignals(True)
        self._companion_mode_combo.setCurrentIndex(max(0, mode_index))
        self._companion_mode_combo.blockSignals(False)
        if hasattr(self, "_emotion_btn"):
            self._refresh_brain_controls()

    def _brain_button_style(self, button: QPushButton, enabled: bool, text: str) -> None:
        button.blockSignals(True)
        button.setChecked(enabled)
        button.setText(text)
        button.setStyleSheet(f"""
            QPushButton {{ background: {C.GREEN_D if enabled else C.PANEL2};
                color: {C.WHITE if enabled else C.TEXT_MED};
                border: 1px solid {C.GREEN if enabled else C.BORDER_A}; border-radius: 8px; }}
            QPushButton:hover {{ color: {C.WHITE}; border-color: {C.PRI_DIM}; }}""")
        button.blockSignals(False)

    def _refresh_brain_controls(self):
        if not hasattr(self, "_emotion_btn"):
            return
        from memory.learning_brain import load_brain
        data = load_brain()
        settings = data["settings"]
        self._brain_button_style(self._emotion_btn, settings["emotion_support"],
                                 "EMOTION: ON" if settings["emotion_support"] else "EMOTION: OFF")
        self._brain_button_style(self._routine_btn, settings["routine_suggestions"],
                                 "ROUTINES: ON" if settings["routine_suggestions"] else "ROUTINES: OFF")
        self._brain_button_style(self._daily_intel_btn, settings["daily_intelligence"],
                                 "DAILY IQ: ON" if settings["daily_intelligence"] else "DAILY IQ: OFF")
        enrolled = bool(data.get("voiceprint", {}).get("samples"))
        voice_on = bool(settings["voice_identification"] and enrolled)
        self._brain_button_style(self._voice_identity_btn, voice_on,
                                 "VOICE ID: ON" if voice_on else "VOICE ID: SET UP" if not enrolled else "VOICE ID: OFF")
        self._voice_identity_btn.setToolTip(
            "Say 'enroll my voice' to provide explicit consent and capture a local convenience voiceprint. "
            "Voice ID never authorizes sensitive actions." if not enrolled else
            "Convenience profile matching only; sensitive actions still require confirmation.")
        index = self._vision_copilot_combo.findData(settings["vision_copilot"])
        self._vision_copilot_combo.blockSignals(True)
        self._vision_copilot_combo.setCurrentIndex(max(0, index))
        self._vision_copilot_combo.blockSignals(False)

    def _toggle_brain_setting(self, key: str):
        from memory.learning_brain import load_brain, update_settings
        current = bool(load_brain()["settings"].get(key, True))
        settings = update_settings(**{key: not current})
        self._refresh_brain_controls()
        label = key.replace("_", " ").title()
        self._log.append_log(f"SYS: {label} — {'on' if settings[key] else 'off'}.")

    def _start_surprise_mode(self):
        from memory.learning_brain import start_surprise
        instruction = start_surprise()
        request_say = getattr(self, "request_say", None)
        if callable(request_say):
            request_say(instruction)
        else:
            self._log.append_log("SYS: CHARLIE is still connecting. Try Surprise Me again in a moment.")

    def _open_game_room(self):
        from memory.game_room import menu_instruction
        request_say = getattr(self, "request_say", None)
        if callable(request_say):
            request_say(menu_instruction())
        else:
            self._log.append_log("SYS: CHARLIE is still connecting. Try Game Room again in a moment.")

    def _on_vision_mode(self, index: int):
        mode = self._vision_copilot_combo.itemData(index)
        if not mode:
            return
        from memory.learning_brain import load_brain, update_settings
        if load_brain()["settings"].get("vision_copilot") != mode:
            update_settings(vision_copilot=mode)
            self._log.append_log(f"SYS: Vision Copilot privacy mode — {mode}.")

    def _toggle_voice_identity(self):
        from memory.learning_brain import load_brain, update_settings
        data = load_brain()
        enrolled = bool(data.get("voiceprint", {}).get("samples"))
        if not enrolled:
            self._log.append_log(
                "SYS: To set up Voice ID, say 'Enroll my voice' and explicitly confirm local storage.")
            self._refresh_brain_controls()
            return
        want = not bool(data["settings"].get("voice_identification"))
        update_settings(voice_identification=want)
        self._refresh_brain_controls()
        self._log.append_log(f"SYS: Voice ID — {'on' if want else 'off'} (convenience only).")

    def _on_profile_selected(self, index: int):
        profile_id = self._profile_combo.itemData(index)
        if not profile_id:
            return
        from memory.profile_manager import active_profile_id, switch_profile
        if profile_id != active_profile_id():
            switch_profile(profile_id)
            self._refresh_personal_controls()
            self._log.append_log(f"SYS: Private profile switched — {self._profile_combo.currentText()}.")

    def _add_profile(self):
        name, ok = QInputDialog.getText(
            self, "New family profile", "Person's name:")
        if not ok or not name.strip():
            return
        from memory.profile_manager import create_profile, switch_profile
        profile = create_profile(name)
        switch_profile(profile["id"])
        self._refresh_personal_controls()
        self._log.append_log(f"SYS: Private profile created — {profile['name']}.")

    def _on_companion_mode_selected(self, index: int):
        mode = self._companion_mode_combo.itemData(index)
        if not mode:
            return
        from memory.personal_hub import load_hub, set_companion
        if load_hub().get("companion", {}).get("mode") != mode:
            settings = set_companion(mode=mode)
            self._log.append_log(f"SYS: Companion mode — {settings['mode']}.")

    def _activate_voice_profile(self, persona: str):
        """Apply the selected avatar and its paired voice immediately.

        Visual switch (face, landmarks, config) is unconditional.
        Voice pairing is gated behind the commercial subscription check.
        """
        persona = "female" if persona == "female" else "male"

        from memory.config_manager import (get_assistant_persona, get_voice,
                                           get_persona_voice,
                                           save_assistant_persona, save_hud_style,
                                           get_hud_style,
                                           )
        persona_changed = get_assistant_persona() != persona

        # ── 1. Visual switch — always immediate, no subscription required ──
        save_assistant_persona(persona)
        cur_style = get_hud_style()
        target_style = cur_style if cur_style in ("core", "holo") else "core"
        save_hud_style(target_style)
        try:
            self.hud.set_persona(persona)
            self.hud.hud_style = target_style
            if hasattr(self.hud, "_update_avatar_geometry"):
                self.hud._update_avatar_geometry()
            self.hud.update()
        except Exception:
            pass
        self._refresh_voice_profile_btns()
        self._refresh_hud_btn()
        if persona_changed:
            self._log.append_log(f"SYS: Switched to {persona.title()} avatar.")

        # ── 2. Voice pairing — requires subscription check ─────────────────
        voice = get_persona_voice(persona)
        voice_changed = get_voice() != voice
        try:
            comm_eng = self._get_commercial_engine()
            if comm_eng is None:
                # Engine still loading — visual already applied, voice will
                # follow once the engine finishes its background startup.
                return
            allowed, reason = comm_eng.verify_voice_access(persona)
            if not allowed:
                self._log.append_log(f"SYS: {persona.title()} voice is locked. {reason}")
                if hasattr(self, "_show_pricing_overlay"):
                    self._show_pricing_overlay()
                return
        except Exception:
            pass  # Best-effort; don't block the voice change on engine errors

        if voice_changed:
            self._log.append_log(
                f"SYS: Voice switched to {voice}.")
        # Persona also changes the assistant's grammatical self-reference.
        # Rebuild even when both profiles happen to use the same audio voice.
        if (persona_changed or voice_changed) and self.on_voice_change:
            self.on_voice_change()

    def _get_commercial_engine(self):
        if self._commercial_engine is None and not self._commercial_error:
            self._start_commercial_load()
        return self._commercial_engine

    def _start_commercial_load(self) -> None:
        """Load and validate subscription state without blocking the GUI."""
        if self._commercial_engine is not None or self._commercial_loading:
            return
        self._commercial_loading = True

        def _work():
            try:
                from engine.commercial.core import get_commercial_engine
                engine = get_commercial_engine()
                engine.startup_subscription_check()
                self._commercial_engine = engine
                self._subscription_checked = True
            except Exception as exc:
                self._commercial_error = str(exc)
                print(f"[CommercialUI] Background subscription load failed: {exc}")
            finally:
                self._commercial_loading = False
                self._commercial_ready_sig.emit()

        threading.Thread(target=_work, daemon=True,
                         name="subscription-loader").start()

    def _on_commercial_ready(self) -> None:
        if self._commercial_engine is None:
            if hasattr(self, "_plan_header_btn"):
                self._plan_header_btn.setText("Plan unavailable")
            if hasattr(self, "_subscription_btn"):
                self._subscription_btn.setText("Subscription unavailable")
            return
        self._refresh_subscription_ui()
        self._refresh_voice_profile_btns()

    def _refresh_subscription_ui(self):
        """Keep the visible plan badge and Settings subscription row current."""
        try:
            engine = self._get_commercial_engine()
            if engine is None:
                return
            account = engine.get_account()
            status = engine.get_starter_time_status()
            plan_name = engine.plan_registry.get_plan(account.plan).name
            if plan_name == "Premium":
                plan_name = "Pro"
            if status["is_starter"]:
                remaining = max(0, int(status.get("remaining_seconds") or 0))
                m = remaining // 60
                s = remaining % 60
                detail = f"{m:02d}:{s:02d} left"
                if remaining > 180:
                    active_colour = "#fbbf24"
                    bg_col = "#1f1d17"
                    border_col = "#d97706"
                elif remaining > 60:
                    active_colour = "#fb923c"
                    bg_col = "#271c19"
                    border_col = "#ea580c"
                elif remaining > 0:
                    active_colour = "#f87171"
                    bg_col = "#2b1419"
                    border_col = "#dc2626"
                else:
                    detail = "00:00 EXPIRED"
                    active_colour = "#f87171"
                    bg_col = "#3b1820"
                    border_col = "#ef4444"
            else:
                detail = account.subscription_status.value.replace("_", " ").title()
                active_colour = C.GREEN
                bg_col = C.PANEL2
                border_col = C.BORDER_B

            if hasattr(self, "_plan_header_btn"):
                self._plan_header_btn.setText(f"{plan_name} · {detail}")
                self._plan_header_btn.setStyleSheet(f"""
                    QPushButton {{ background: {bg_col}; color: {active_colour};
                        border: 1px solid {border_col}; border-radius: 12px;
                        padding: 0 12px; font-weight: 700; font-size: 11px; }}
                    QPushButton:hover {{ background: {active_colour};
                        border-color: #ffffff; color: #0f172a; }} """)
            if hasattr(self, "_subscription_btn"):
                self._subscription_btn.setText(f"Current plan: {plan_name} — {detail}")
                self._subscription_btn.setStyleSheet(f"""
                    QPushButton {{ background: {C.PANEL2}; color: {active_colour};
                        border: 1px solid {C.BORDER_B}; border-radius: 8px;
                        text-align: left; padding: 0 10px; font-weight: 600; }}
                    QPushButton:hover {{ background: {C.PRI_GHO};
                        border-color: {C.PRI}; color: {C.WHITE}; }} """)
            if hasattr(self, "_profile_avatar_btn"):
                u_initial = (account.display_name or account.email or "A").strip()[:1].upper() or "A"
                self._profile_avatar_btn.setText(u_initial)
                self._profile_avatar_btn.setToolTip(f"Profile: {account.display_name or 'User'} ({plan_name})")
        except Exception as exc:
            if hasattr(self, "_plan_header_btn"):
                self._plan_header_btn.setText("Plan unavailable")
            if hasattr(self, "_subscription_btn"):
                self._subscription_btn.setText("Subscription unavailable")
            print(f"[CommercialUI] Subscription status failed: {exc}")

    def _on_subscription_plan_selected(self, tier):
        engine = self._get_commercial_engine()
        if engine is None:
            self._log.append_log("SYS: Subscription is still loading — please try again.")
            return
        plan = engine.plan_registry.get_plan(tier)
        from engine.commercial.models import PlanTier, SubscriptionStatus
        current = engine.get_account().plan
        if current == tier and tier != PlanTier.STARTER:
            self._log.append_log(f"SYS: {plan.name} is already your current plan.")
            self._refresh_voice_profile_btns()
            return

        account = engine.get_account()
        account.plan = tier
        if tier == PlanTier.LIFETIME:
            account.subscription_status = SubscriptionStatus.LIFETIME_ACTIVE
        elif tier != PlanTier.STARTER:
            account.subscription_status = SubscriptionStatus.ACTIVE
        else:
            account.subscription_status = SubscriptionStatus.FREE
        engine.save_account(account)

        # Clear lockout if paid plan chosen
        if tier != PlanTier.STARTER:
            self._starter_exhausted_locked = False
            self._muted = False
            self.hud.muted = False
            if hasattr(self, "_input"):
                self._input.setEnabled(True)
                self._input.setPlaceholderText("Ask anything or give a task…")
            self._style_mute_btn()

        self._refresh_subscription_ui()
        self._refresh_voice_profile_btns()

        if self._pricing_overlay:
            self._pricing_overlay.hide()

        self._log.append_log(
            f"SYS: 🎉 {plan.name.upper()} Plan activated successfully! (₹{plan.price_inr}{'/mo' if plan.is_recurring else ' one-time'})"
        )
        self._log.append_log(f"SYS: All {plan.name} features and entitlements are now unlocked.")

    def _show_pricing_overlay(self, forced_paywall: bool = False):
        """Displays commercial pricing and subscription plan comparison in full screen."""
        try:
            engine = self._get_commercial_engine()
            if engine is None:
                self._log.append_log(
                    "SYS: Subscription is loading — pricing will be ready in a moment.")
                return
            from engine.commercial.ui_components import PricingOverlay
            if self._pricing_overlay:
                self._pricing_overlay.hide()
                self._pricing_overlay.deleteLater()
                self._pricing_overlay = None
            cw = self.centralWidget() or self
            ov = PricingOverlay(
                cw,
                engine=engine,
                on_select_plan=self._on_subscription_plan_selected,
                forced_paywall=forced_paywall,
            )
            ov.setGeometry(0, 0, cw.width(), cw.height())
            ov.show()
            ov.raise_()
            self._pricing_overlay = ov
        except Exception as e:
            print(f"[CommercialUI] Failed to display PricingOverlay: {e}")

    def _toggle_hud_style(self):
        """Cycle between: Reactor Core ↔ Classic Hologram."""
        if getattr(self, "_chat_mode", False):
            self._set_chat_mode(False)
        from memory.config_manager import get_hud_style, save_hud_style
        cur = get_hud_style()
        want = "core" if cur == "holo" else "holo"
        save_hud_style(want)
        try:
            self.hud.hud_style = want
            if hasattr(self.hud, "_update_avatar_geometry"):
                self.hud._update_avatar_geometry()
            self.hud.update()
        except Exception:
            pass
        self._refresh_hud_btn()
        _msg = {
            "holo": "SYS: HUD switched to Classic Hologram.",
            "core": "SYS: HUD switched to Reactor Core.",
        }.get(want, "SYS: HUD appearance updated.")
        self._log.append_log(_msg)

    def _refresh_slow_speech_btn(self):
        if not hasattr(self, "_slow_speech_btn"):
            return
        from memory.config_manager import get_slow_speech_enabled
        enabled = get_slow_speech_enabled()
        if enabled:
            self._slow_speech_btn.setText("Slow speech listening: ON")
            self._slow_speech_btn.setStyleSheet(f"""
                QPushButton {{ background: #001a08; color: {C.GREEN};
                    border: 1px solid {C.GREEN_D}; border-radius: 8px;
                    text-align: left; padding: 0 10px; }}
                QPushButton:hover {{ background: #002010; }}""")
        else:
            self._slow_speech_btn.setText("Slow speech listening: OFF")
            self._slow_speech_btn.setStyleSheet(f"""
                QPushButton {{ background: {C.PANEL2}; color: {C.TEXT};
                    border: 1px solid {C.BORDER}; border-radius: 8px;
                    text-align: left; padding: 0 10px; }}
                QPushButton:hover {{ color: {C.WHITE}; background: {C.PRI_GHO};
                    border-color: {C.PRI_DIM}; }}""")

    def _toggle_slow_speech(self):
        from memory.config_manager import (get_slow_speech_enabled,
                                           save_slow_speech_enabled)
        enabled = not get_slow_speech_enabled()
        save_slow_speech_enabled(enabled)
        self._refresh_slow_speech_btn()
        self._log.append_log(
            "SYS: Slow speech listening enabled — I will wait through longer pauses."
            if enabled else
            "SYS: Slow speech listening disabled — normal response timing restored.")
        if self.on_listening_change:
            self.on_listening_change()

    def _toggle_ptt(self):
        from memory.config_manager import (get_push_to_talk_enabled,
                                           save_push_to_talk_enabled)
        want = not get_push_to_talk_enabled()
        save_push_to_talk_enabled(want)
        scope = None
        if self.on_push_to_talk:
            try:
                scope = self.on_push_to_talk(want)
            except Exception as e:
                self._log.append_log(f"ERR: Push-to-talk failed — {e}")
                save_push_to_talk_enabled(False)
                want = False
        self._apply_ptt_shortcut(want and scope != "global")
        self._refresh_talk_btns()

    def _apply_ptt_shortcut(self, needed: bool):
        """Bind the chord inside the window when no global hook is available.

        On macOS and Linux there is no dependency-free way to read global key
        state, so the chord is at least live whenever this window has focus.
        Qt gives no key-release for a QShortcut, so a press latches the mic open
        and a short timer closes it; held down, auto-repeat keeps pushing that
        timer out, which behaves like holding a key.
        """
        from PyQt6.QtGui import QKeySequence, QShortcut
        from core.hotkey import qt_sequence

        if not needed:
            sc = getattr(self, "_ptt_sc", None)
            if sc is not None:
                sc.setEnabled(False)
                self._ptt_sc = None
            self._ptt_hold(False)
            return
        if getattr(self, "_ptt_sc", None) is not None:
            return

        self._ptt_release = QTimer(self)
        self._ptt_release.setSingleShot(True)
        self._ptt_release.setInterval(420)
        self._ptt_release.timeout.connect(lambda: self._ptt_hold(False))

        def _press():
            self._ptt_hold(True)
            self._ptt_release.start()

        self._ptt_sc = QShortcut(QKeySequence(qt_sequence()), self)
        self._ptt_sc.setAutoRepeat(True)
        self._ptt_sc.activated.connect(_press)

    def _ptt_hold(self, held: bool):
        """Report a windowed press/release to whoever owns the microphone."""
        cb = getattr(self, "ptt_hold", None)
        if cb:
            try:
                cb(bool(held))
            except Exception:
                pass

    def _toggle_wake_word(self):
        st = self._wake_state()
        if not st["ready"]:
            # First time: download openwakeword + model in a worker thread.
            self._wake_btn.setText("⬇  DOWNLOADING… (one-time)")
            self._wake_btn.setEnabled(False)
            def _work():
                try:
                    from core.wake_word import install_and_download
                    ok, msg = install_and_download(
                        logger=lambda m: self._log_sig.emit(f"SYS: {m}"))
                except Exception as e:
                    ok, msg = False, str(e)
                if ok and self.on_wake_toggle:
                    try:
                        self.on_wake_toggle(True)   # auto-enable after a successful download
                    except Exception:
                        pass
                self._wake_dl_sig.emit(ok, msg)
            threading.Thread(target=_work, daemon=True).start()
            return
        # Already downloaded → just flip enabled/disabled through CharlieLive.
        if self.on_wake_toggle:
            try:
                self.on_wake_toggle(not st["enabled"])
            except Exception:
                pass
        self._refresh_wake_btns()

    def _on_wake_install_done(self, ok: bool, msg: str):
        self._log_sig.emit(f"SYS: {'Wake word ready.' if ok else 'Wake word setup failed: ' + msg}")
        self._refresh_wake_btns()

    def _tap_wake_manual(self):
        if self.on_wake_manual:
            try:
                self.on_wake_manual()
            except Exception:
                pass
        self._refresh_wake_btns()

    def _update_brief_btn(self, enabled: bool):
        if not hasattr(self, '_brief_btn'):
            return
        if enabled:
            self._brief_btn.setText("☀  MORNING BRIEF: ON")
            self._brief_btn.setStyleSheet(f"""
                QPushButton {{
                    background: #001a08; color: {C.GREEN};
                    border: 1px solid {C.GREEN_D}; border-radius: 8px;
                    text-align: left; padding: 0 8px;
                }}
                QPushButton:hover {{ background: #002010; }}
            """)
        else:
            self._brief_btn.setText("☀  MORNING BRIEF: OFF")
            self._brief_btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent; color: {C.TEXT_DIM};
                    border: 1px solid {C.BORDER}; border-radius: 8px;
                    text-align: left; padding: 0 8px;
                }}
                QPushButton:hover {{ color: {C.TEXT}; border: 1px solid {C.BORDER_B}; }}
            """)

    # ── Customization ────────────────────────────────────────────────────────────

    def _save_appearance(self, theme: str, colour: str) -> None:
        """Persist appearance without disturbing API keys or voice settings."""
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        data = _read_full_config()
        data["ui_theme"] = normalize_ui_theme(theme)
        data["ui_color"] = str(colour or DEFAULT_UI_COLOR).strip().lower()
        API_FILE.write_text(json.dumps(data, indent=4), encoding="utf-8")

    def _sync_accent_combo(self, colour: str) -> None:
        if not hasattr(self, "_accent_combo"):
            return
        selected = str(colour or DEFAULT_UI_COLOR).strip().lower()
        index = self._accent_combo.findData(selected)
        if index < 0:
            self._accent_combo.addItem(f"Colour: Custom ({selected})", selected)
            index = self._accent_combo.count() - 1
        self._accent_combo.blockSignals(True)
        self._accent_combo.setCurrentIndex(index)
        self._accent_combo.blockSignals(False)

    def _refresh_all_logos(self):
        """Re-render all dynamic brand logos with the active theme and accent colors."""
        for k in list(_SVG_PIXMAP_CACHE.keys()):
            if k[0] == "brand_c":
                _SVG_PIXMAP_CACHE.pop(k, None)
        for k in list(_SVG_ICON_CACHE.keys()):
            if k[0] == "brand_c":
                _SVG_ICON_CACHE.pop(k, None)

        if hasattr(self, "_c_logo_badge") and self._c_logo_badge:
            self._c_logo_badge.setPixmap(_render_hub_svg("brand_c", 26, "#ffffff"))
        if hasattr(self, "_sidebar_brand_icon") and self._sidebar_brand_icon:
            self._sidebar_brand_icon.setPixmap(_render_hub_svg("brand_c", 36, "#ffffff"))
        if hasattr(self, "_avatar_brand_icon") and self._avatar_brand_icon:
            self._avatar_brand_icon.setPixmap(_render_hub_svg("brand_c", 30, "#ffffff"))
        if hasattr(self, "_chat_icon_box") and self._chat_icon_box:
            self._chat_icon_box.setPixmap(_render_hub_svg("brand_c", 20, "#ffffff"))
            self._chat_icon_box.setStyleSheet(f"""
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {C.PRI_DIM}, stop:1 {C.PRI});
                border: 1px solid rgba(147, 197, 253, 0.5);
                border-radius: 10px;
            """)

        if hasattr(self, "_log") and self._log:
            self._log.refresh_avatar_resources()

    def _open_theme_studio(self):
        """Open the interactive Theme & Color Studio overlay."""
        cw = self.centralWidget()
        if cw is None:
            return
        if hasattr(self, "_theme_studio_overlay") and self._theme_studio_overlay and self._theme_studio_overlay.isVisible():
            self._theme_studio_overlay.hide()
            self._hide_modal_backdrop()
            return
        self._close_active_overlays(exclude="theme_studio")
        self._show_modal_backdrop()
        cfg = _read_full_config()
        cur_theme = normalize_ui_theme(cfg.get("ui_theme", DEFAULT_UI_THEME))
        cur_color = str(cfg.get("ui_color") or DEFAULT_UI_COLOR).lower()
        ov = ThemeStudioOverlay(cur_theme, cur_color, parent=cw)
        ov.theme_changed.connect(self._apply_theme_from_studio)
        ov.custom_wheel_requested.connect(self._open_customize)
        self._centre_overlay(ov)
        self._theme_studio_overlay = ov

    def _apply_theme_from_studio(self, theme: str, colour: str):
        """Instantly re-theme all widgets and dynamic logos when studio updates."""
        old = current_palette()
        selected = apply_ui_theme(theme, colour)
        retheme_all_widgets(old, current_palette())
        self._refresh_message_input_contrast()
        self._refresh_chat_mode_buttons()
        self._refresh_all_logos()

        if hasattr(self, "_theme_combo"):
            idx = self._theme_combo.findData(selected)
            if idx >= 0:
                self._theme_combo.blockSignals(True)
                self._theme_combo.setCurrentIndex(idx)
                self._theme_combo.blockSignals(False)
        if hasattr(self, "_accent_combo"):
            self._sync_accent_combo(colour)

        try:
            self._save_appearance(selected, colour)
            self._log.append_log(f"SYS: Theme applied — {UI_THEME_LABELS.get(selected, selected)}.")
        except Exception as exc:
            self._log.append_log(f"ERR: Theme save failed — {exc}")

    def _on_theme_selected(self, index: int) -> None:
        theme = self._theme_combo.itemData(index)
        if not theme:
            return
        config = _read_full_config()
        colour = str(config.get("ui_color") or DEFAULT_UI_COLOR).lower()
        old = current_palette()
        selected = apply_ui_theme(theme, colour)
        retheme_all_widgets(old, current_palette())
        self._refresh_message_input_contrast()
        self._refresh_chat_mode_buttons()
        self._refresh_all_logos()
        try:
            self._save_appearance(selected, colour)
            self._log.append_log(f"SYS: Theme changed — {UI_THEME_LABELS.get(selected, selected)}.")
        except Exception as exc:
            self._log.append_log(f"ERR: Theme save failed — {exc}")

    def _on_accent_selected(self, index: int) -> None:
        colour = self._accent_combo.itemData(index)
        if not colour:
            return
        old = current_palette()
        if not apply_ui_accent(str(colour)):
            return
        retheme_all_widgets(old, current_palette())
        self._refresh_message_input_contrast()
        self._refresh_chat_mode_buttons()
        self._refresh_all_logos()
        theme = self._theme_combo.currentData() or DEFAULT_UI_THEME
        try:
            self._save_appearance(theme, colour)
            self._log.append_log(f"SYS: Interface colour changed — {colour}.")
        except Exception as exc:
            self._log.append_log(f"ERR: Colour save failed — {exc}")

    def _open_customize(self):
        cfg = _read_full_config()
        if self._customize_overlay:
            self._customize_overlay.hide()
        cw = self.centralWidget()
        ov = CustomizeOverlay(
            cfg.get("assistant_name", "CHARLIE") or "CHARLIE",
            cfg.get("user_name", ""),
            cfg.get("ui_color", "") or DEFAULT_UI_COLOR,
            cfg.get("voice_name", ""),
            cfg.get("assistant_persona", "male"),
            parent=cw,
        )
        ow, oh = CustomizeOverlay._OW, CustomizeOverlay._OH
        oh = min(oh, cw.height() - 16)
        ov.setGeometry(
            (cw.width()  - ow) // 2,
            (cw.height() - oh) // 2,
            ow, oh,
        )
        ov.on_preview = self._preview_ui_color
        ov.on_persona_preview = self.hud.set_persona
        ov.saved.connect(self._apply_name_update)
        ov.show()
        self._customize_overlay = ov

    def _preview_ui_color(self, hex_color: str):
        """Live preview — paints the whole interface the new colour (does NOT write to config)."""
        old = current_palette()
        if apply_ui_accent(hex_color):
            retheme_all_widgets(old, current_palette())

    def _apply_name_update(self, name: str, user_name: str, ui_color: str = "",
                           voice: str = "", persona: str = "male",
                           preferences: object = None):
        """Update all name/theme-dependent UI elements and persist to config."""
        self._assistant_name = name.strip() or "CHARLIE"
        if self._assistant_name.upper() in ("JARVIS", "J.A.R.V.I.S.", "J.A.R.V.I.S"):
            self._assistant_name = "CHARLIE"
        display = self._assistant_name.upper()
        self.setWindowTitle(f"{display} — {APP_VERSION} · v{RELEASE_VERSION}")
        self._title_lbl.setText(display)
        if hasattr(self, "_brand_title_lbl"):
            self._brand_title_lbl.setText(self._assistant_name.title())
        if display in ("CHARLIE", "C.H.A.R.L.I.E"):
            self._sub_lbl.setText("Personal AI Desktop Assistant")
        else:
            self._sub_lbl.setText("Personal AI Assistant")
        self._log._ai_name_lc = self._assistant_name.lower()
        self._log.set_user_name(user_name)
        self.hud._assistant_name = display

        color_changed = False
        if ui_color:
            old = current_palette()
            if apply_ui_accent(ui_color):
                # Live-paint the whole interface (panels, buttons, borders, HUD)
                retheme_all_widgets(old, current_palette())
                color_changed = old["PRI"] != C.PRI

        # Voice change → persist and, if it actually changed, rebuild the Live
        # session so the new voice takes effect (it's fixed at connect time).
        from memory.config_manager import (
            get_assistant_persona, get_voice, save_assistant_persona,
            save_persona_voice,
        )
        old_voice = get_voice()
        old_persona = get_assistant_persona()
        extra = preferences if isinstance(preferences, dict) else {}
        persona_voices = extra.get("persona_voices")
        if isinstance(persona_voices, dict):
            for profile, selected_voice in persona_voices.items():
                save_persona_voice(profile, selected_voice)
        elif voice:
            save_persona_voice(persona, voice)
        persona = save_assistant_persona(persona)
        voice = get_voice()
        voice_changed = voice != old_voice
        persona_changed = persona != old_persona

        speech = extra.get("speech")
        speech_changed = False
        if isinstance(speech, dict):
            from memory.personal_hub import load_hub, set_speech_preferences
            current_speech = load_hub().get("speech", {})
            speech_changed = any(current_speech.get(key) != value
                                 for key, value in speech.items())
            if speech_changed:
                set_speech_preferences(**speech)
                # Hot-swap STT language on the live WhisperSTT instance (no model reload)
                new_lang = speech.get("language")
                if new_lang:
                    try:
                        import sys
                        for _mod_name in ("__main__", "main"):
                            _app = getattr(sys.modules.get(_mod_name), "app", None)
                            if _app is None:
                                _app = getattr(sys.modules.get(_mod_name), "_app", None)
                            _stt = getattr(_app, "_fallback_stt", None) if _app else None
                            if _stt and hasattr(_stt, "set_language"):
                                _stt.set_language(new_lang)
                                break
                    except Exception:
                        pass
        self.hud.set_persona(persona)
        self._refresh_voice_profile_btns()
        self._refresh_hud_btn()

        try:
            data = _read_full_config()
            data["assistant_name"] = self._assistant_name
            data["user_name"] = user_name.strip()
            if ui_color:
                data["ui_color"] = ui_color.strip().lower()
            API_FILE.write_text(json.dumps(data, indent=4), encoding="utf-8")
            if ui_color:
                self._sync_accent_combo(ui_color)
            self._log.append_log(f"SYS: Identity updated — {display}")
            if color_changed:
                self._log.append_log(f"SYS: UI colour applied — {ui_color}")
            if voice_changed:
                self._log.append_log(f"SYS: Voice set — {voice}")
            if persona_changed:
                self._log.append_log(f"SYS: Assistant profile set — {persona}")
            if speech_changed:
                lang_label = speech.get('language', 'auto').title()
                gender_label = speech.get('voice_gender', 'female').title()
                self._log.append_log(
                    f"SYS: Natural speech — {speech.get('style', 'warm')} style, "
                    f"{speech.get('pace', 'natural')} pace, "
                    f"{lang_label} language, {gender_label} voice.")
        except Exception as e:
            self._log.append_log(f"ERR: Config save failed — {e}")

        if (persona_changed or voice_changed) and self.on_voice_change:
            self.on_voice_change()

    def _nav_click_home(self):
        self._close_active_overlays()
        if getattr(self, "_chat_mode", False):
            self._set_chat_mode(False)
        self._set_active_nav_index(0)

    def _nav_click_chat(self):
        self._close_active_overlays()
        if not getattr(self, "_chat_mode", False):
            self._set_chat_mode(True)
        self._set_active_nav_index(1)

    def _nav_click_avatar(self):
        self._close_active_overlays()
        self._toggle_hud_style()
        self._restore_primary_nav()

    def _set_active_nav_index(self, active_idx: int) -> None:
        if not hasattr(self, "_nav_buttons") or not self._nav_buttons:
            return
        active_ss = f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 rgba(99, 102, 241, 0.28), stop:1 rgba(79, 70, 229, 0.16));
                color: #ffffff;
                border: 1px solid rgba(99, 102, 241, 0.45);
                border-left: 3px solid {C.PRI};
                border-radius: 10px;
                text-align: left;
                padding-left: 14px;
                font-weight: 600;
            }}
        """
        idle_ss = f"""
            QPushButton {{
                background: transparent; color: {C.TEXT_MED};
                border: 1px solid transparent; border-radius: 10px;
                text-align: left; padding-left: 12px;
            }}
            QPushButton:hover {{
                background: rgba(99, 102, 241, 0.1); color: #ffffff;
                border-color: rgba(99, 102, 241, 0.25);
            }}
        """
        for i, btn in enumerate(self._nav_buttons):
            svg_key = _NAV_SVGS[i] if i < len(_NAV_SVGS) else "nav_home"
            if i == active_idx:
                btn.setStyleSheet(active_ss)
                btn.setIcon(_render_svg_icon(svg_key, 16, "#ffffff"))
                btn.setFont(QFont(APP_FONT_NAME, 9, QFont.Weight.DemiBold))
            else:
                btn.setStyleSheet(idle_ss)
                btn.setIcon(_render_svg_icon(svg_key, 16, "#94a3b8"))
                btn.setFont(QFont(APP_FONT_NAME, 9, QFont.Weight.Medium))

    def _restore_primary_nav(self) -> None:
        if getattr(self, "_chat_mode", False):
            self._set_active_nav_index(1)
        else:
            self._set_active_nav_index(0)

    def _get_or_create_modal_backdrop(self):
        cw = self.centralWidget()
        if cw is None:
            return None
        if not hasattr(self, "_modal_backdrop") or self._modal_backdrop is None:
            self._modal_backdrop = ModalBackdrop(parent=cw)
            self._modal_backdrop.clicked.connect(self._close_active_overlays)
        self._modal_backdrop.setGeometry(0, 0, cw.width(), cw.height())
        return self._modal_backdrop

    def _show_modal_backdrop(self):
        bd = self._get_or_create_modal_backdrop()
        if bd is not None:
            cw = self.centralWidget()
            if cw is not None:
                bd.setGeometry(0, 0, cw.width(), cw.height())
            bd.show()
            bd.raise_()

    def _hide_modal_backdrop(self):
        if hasattr(self, "_modal_backdrop") and self._modal_backdrop is not None:
            self._modal_backdrop.hide()

    def _close_active_overlays(self, exclude=None):
        """Cleanly close open modal overlays and backdrop."""
        overlay_map = {
            "screen": getattr(self, "_screen_copilot_overlay", None),
            "mobile": getattr(self, "_mobile_bridge_overlay", None),
            "memory": getattr(self, "_memory_overlay", None),
            "knowledge": getattr(self, "_knowledge_overlay", None),
            "proactive": getattr(self, "_proactive_overlay", None),
            "audio": getattr(self, "_audio_overlay", None),
            "remote": getattr(self, "_remote_overlay", None),
            "customize": getattr(self, "_customize_overlay", None),
            "theme_studio": getattr(self, "_theme_studio_overlay", None),
        }
        for name, ov in overlay_map.items():
            if ov is not None and ov != exclude and name != exclude:
                if hasattr(ov, "isVisible") and ov.isVisible():
                    ov.hide()
        if getattr(self, "_quick_drawer", None) is not None and self._quick_drawer != exclude and exclude != "settings":
            if self._quick_drawer.isVisible():
                self._quick_drawer.hide()
        if exclude is None:
            self._hide_modal_backdrop()
            self._restore_primary_nav()

    def _on_overlay_closed(self, ov=None):
        active_overlays = [
            getattr(self, "_screen_copilot_overlay", None),
            getattr(self, "_mobile_bridge_overlay", None),
            getattr(self, "_memory_overlay", None),
            getattr(self, "_knowledge_overlay", None),
            getattr(self, "_proactive_overlay", None),
            getattr(self, "_audio_overlay", None),
            getattr(self, "_remote_overlay", None),
            getattr(self, "_customize_overlay", None),
            getattr(self, "_theme_studio_overlay", None),
        ]
        any_visible = any(o is not None and o.isVisible() for o in active_overlays)
        drawer_visible = getattr(self, "_quick_drawer", None) is not None and self._quick_drawer.isVisible()
        if not any_visible:
            self._hide_modal_backdrop()
            if not drawer_visible:
                self._restore_primary_nav()

    def _centre_overlay(self, ov) -> None:
        """Place a floating overlay in the middle of the HUD and show it."""
        cw = self.centralWidget()
        if cw is None:
            return
        self._show_modal_backdrop()
        ov.adjustSize()
        ov.setGeometry(
            max(0, (cw.width()  - ov.width())  // 2),
            max(0, (cw.height() - ov.height()) // 2),
            ov.width(), ov.height(),
        )
        ov.show()
        ov.raise_()

    # ── Audio devices ────────────────────────────────────────────────────────

    def _open_audio_devices(self):
        ov = AudioDeviceOverlay(parent=self.centralWidget())
        ov.picked.connect(self._on_audio_devices_applied)
        self._centre_overlay(ov)
        self._audio_overlay = ov            # keep a reference so it isn't GC'd

    def _on_audio_devices_applied(self):
        self._log.append_log("SYS: Audio devices updated.")
        if self.on_audio_device_change:
            self.on_audio_device_change()

    # ── Memory panel ─────────────────────────────────────────────────────────

    def _open_memory_panel(self):
        cw = self.centralWidget()
        if cw is None:
            return
        if hasattr(self, "_memory_overlay") and self._memory_overlay is not None and self._memory_overlay.isVisible():
            self._memory_overlay.hide()
            self._hide_modal_backdrop()
            self._restore_primary_nav()
            return
        self._close_active_overlays(exclude="memory")
        self._set_active_nav_index(6)
        self._show_modal_backdrop()
        ov = MemoryOverlay(parent=cw)
        self._centre_overlay(ov)
        self._memory_overlay = ov

    # ── Knowledge Base (RAG) panel ───────────────────────────────────────────

    def _open_knowledge_panel(self):
        cw = self.centralWidget()
        if cw is None:
            return
        if hasattr(self, "_knowledge_overlay") and self._knowledge_overlay is not None and self._knowledge_overlay.isVisible():
            self._knowledge_overlay.hide()
            self._hide_modal_backdrop()
            self._restore_primary_nav()
            return
        self._close_active_overlays(exclude="knowledge")
        self._set_active_nav_index(4)
        self._show_modal_backdrop()
        ov = KnowledgeOverlay(parent=cw)
        ow = KnowledgeOverlay._OW
        oh = min(540, cw.height() - 20)
        ov.setGeometry(
            max(0, (cw.width()  - ow)  // 2),
            max(0, (cw.height() - oh) // 2),
            ow, oh,
        )
        ov.show()
        ov.raise_()
        self._knowledge_overlay = ov

    # ── Proactive Daemon panel ───────────────────────────────────────────────

    def _display_proactive_nudge(self, nudge):
        try:
            from engine.intelligence.proactive_advisor import load_proactive_settings
            st = load_proactive_settings()
            msg = f"🔔 [{nudge.category}]: {nudge.title} — {nudge.message}"
            self._log.append_log(msg)
            if hasattr(self, "hud") and self.hud is not None:
                self.hud.glance(0.0, -0.6, hold=1.5)
            if st.get("voice_alerts", False) and callable(self.request_say):
                threading.Thread(target=self.request_say, args=(f"Advisory alert. {nudge.message}",), daemon=True).start()
        except Exception as e:
            print(f"[ProactiveUI] display error: {e}")

    def _open_proactive_panel(self):
        cw = self.centralWidget()
        if cw is None:
            return
        if hasattr(self, "_proactive_overlay") and self._proactive_overlay is not None and self._proactive_overlay.isVisible():
            self._proactive_overlay.hide()
            self._hide_modal_backdrop()
            return
        self._close_active_overlays(exclude="proactive")
        self._show_modal_backdrop()
        ov = ProactiveDaemonOverlay(parent=cw, on_action=self._handle_nudge_action)
        ow = ProactiveDaemonOverlay._OW
        oh = min(540, cw.height() - 20)
        ov.setGeometry(
            max(0, (cw.width()  - ow)  // 2),
            max(0, (cw.height() - oh) // 2),
            ow, oh,
        )
        ov.show()
        ov.raise_()
        self._proactive_overlay = ov

    def _open_screen_copilot(self):
        cw = self.centralWidget()
        if cw is None:
            return
        if hasattr(self, "_screen_copilot_overlay") and self._screen_copilot_overlay is not None and self._screen_copilot_overlay.isVisible():
            self._screen_copilot_overlay.hide()
            self._hide_modal_backdrop()
            self._restore_primary_nav()
            return
        self._close_active_overlays(exclude="screen")
        self._set_active_nav_index(5)
        self._show_modal_backdrop()
        try:
            ov = ScreenCopilotOverlay(parent=cw, on_send_to_chat=self._submit_universal_command)
            ow = max(980, min(1280, cw.width() - 40))
            oh = max(660, min(860, cw.height() - 30))
            ov.setGeometry(
                max(0, (cw.width()  - ow)  // 2),
                max(0, (cw.height() - oh) // 2),
                ow, oh,
            )
            ov.show()
            ov.raise_()
            self._screen_copilot_overlay = ov
            if hasattr(self, "hud") and self.hud is not None:
                self.hud.glance(0.0, -0.4, hold=1.0)
        except Exception as e:
            self._log.append_log(f"🖥️ [Screen Copilot] Launch error: {e}")
            self._hide_modal_backdrop()
            self._restore_primary_nav()

    def _open_mobile_bridge(self):
        cw = self.centralWidget()
        if cw is None:
            return
        if hasattr(self, "_mobile_bridge_overlay") and self._mobile_bridge_overlay is not None and self._mobile_bridge_overlay.isVisible():
            self._mobile_bridge_overlay.hide()
            self._hide_modal_backdrop()
            self._restore_primary_nav()
            return
        self._close_active_overlays(exclude="mobile")
        self._show_modal_backdrop()
        try:
            ov = MobileBridgeOverlay(parent=cw)
            ow = MobileBridgeOverlay._OW
            oh = min(480, cw.height() - 20)
            ov.setGeometry(
                max(0, (cw.width()  - ow)  // 2),
                max(0, (cw.height() - oh) // 2),
                ow, oh,
            )
            ov.show()
            ov.raise_()
            self._mobile_bridge_overlay = ov
            if hasattr(self, "hud") and self.hud is not None:
                self.hud.glance(0.0, -0.3, hold=1.2)
        except Exception as e:
            self._log.append_log(f"📱 [Mobile Bridge] Launch error: {e}")
            self._hide_modal_backdrop()
            self._restore_primary_nav()


    def _handle_nudge_action(self, nudge):
        tool = getattr(nudge, "action_tool", "") or ""
        if tool == "daily_briefing":
            self._submit_universal_command("daily briefing")
        elif tool == "system_monitor":
            self._submit_universal_command("check system health")
        elif tool == "file_organizer":
            self._submit_universal_command("organize desktop files")
        elif tool == "focus_timer":
            self._submit_universal_command("start 5 minute break")
        elif tool == "tasks":
            self._submit_universal_command("check my tasks")
        else:
            self._use_chip_prompt(f"{nudge.suggested_action}: ")

    # ── Irreversible-action confirmation ─────────────────────────────────────

    def _show_confirm_banner(self, title: str, detail: str):
        self._hide_confirm_banner()
        ov = ConfirmBanner(title, detail, parent=self.centralWidget())
        ov.answered.connect(self._on_confirm_answered)
        self._centre_overlay(ov)
        self._confirm_overlay = ov

    def _hide_confirm_banner(self):
        ov = getattr(self, "_confirm_overlay", None)
        if ov is not None:
            ov.hide()
            ov.deleteLater()
            self._confirm_overlay = None

    def _on_confirm_answered(self, accepted: bool):
        # Tear the banner down first: core.confirm.resolve() may be about to
        # shut the machine down, and a live widget mid-callback is not where you
        # want to be when that happens.
        self._hide_confirm_banner()
        try:
            from core.confirm import resolve
            resolve(bool(accepted))
        except Exception as e:
            self._log.append_log(f"ERR: Confirmation failed — {e}")

    def _open_plugin_manager(self):
        plugins = []
        if self.get_plugins:
            try:
                plugins = self.get_plugins() or []
            except Exception as e:
                print(f"[Plugins] get_plugins error: {e}")

        if not plugins:
            try:
                from core.plugin_loader import discover_plugins
                pdir = BASE_DIR / "plugins"
                if str(BASE_DIR) not in sys.path:
                    sys.path.insert(0, str(BASE_DIR))
                reg = discover_plugins(pdir, set())
                plugins = reg.list_for_ui()
                self.get_plugins = reg.list_for_ui
                self.get_plugin_settings = reg.settings_schemas
                self.rescan_plugins = lambda: reg.rescan(pdir, set())
            except Exception as e:
                print(f"[Plugins] fallback discovery error: {e}")

        cw = self.centralWidget()

        def _refresh():
            if self.rescan_plugins:
                try:
                    self.rescan_plugins()
                except Exception as e:
                    print(f"[Plugins] live rescan error: {e}")
            else:
                try:
                    from core.plugin_loader import discover_plugins
                    pdir = BASE_DIR / "plugins"
                    if str(BASE_DIR) not in sys.path:
                        sys.path.insert(0, str(BASE_DIR))
                    reg = discover_plugins(pdir, set())
                    self.get_plugins = reg.list_for_ui
                    self.get_plugin_settings = reg.settings_schemas
                    self.rescan_plugins = lambda: reg.rescan(pdir, set())
                except Exception as e:
                    print(f"[Plugins] fallback rescan error: {e}")

            if hasattr(self, "_plugin_manager_overlay") and self._plugin_manager_overlay:
                new_plugins = self.get_plugins() if self.get_plugins else []
                self._plugin_manager_overlay.refresh_installed(new_plugins)

        ov = PluginManagerOverlay(plugins, parent=cw, on_configure=self._open_plugin_settings, on_refresh=_refresh)
        ow = min(PluginManagerOverlay._OW, cw.width() - 32)
        oh = min(580, cw.height() - 20)
        ov.setGeometry(
            (cw.width()  - ow)  // 2,
            (cw.height() - oh) // 2,
            ow, oh,
        )
        ov.show()
        ov.raise_()
        self._plugin_manager_overlay = ov   # keep a reference so it isn't GC'd

    def _open_plugin_settings(self):
        sections = []
        if self.get_plugin_settings:
            try:
                sections = self.get_plugin_settings() or []
            except Exception:
                sections = []
        if not sections:
            try:
                from core.plugin_loader import discover_plugins
                pdir = BASE_DIR / "plugins"
                if str(BASE_DIR) not in sys.path:
                    sys.path.insert(0, str(BASE_DIR))
                reg = discover_plugins(pdir, set())
                self.get_plugins = reg.list_for_ui
                self.get_plugin_settings = reg.settings_schemas
                self.rescan_plugins = lambda: reg.rescan(pdir, set())
                sections = reg.settings_schemas()
            except Exception as e:
                print(f"[Plugins] settings fallback discovery error: {e}")

        cw = self.centralWidget()
        ov = PluginSettingsOverlay(sections, parent=cw)
        ow = min(PluginSettingsOverlay._OW, cw.width() - 32)
        oh = min(600, cw.height() - 20)
        ov.setGeometry(
            (cw.width()  - ow) // 2,
            (cw.height() - oh) // 2,
            ow, oh,
        )
        ov.show()
        ov.raise_()
        self._plugin_settings_overlay = ov   # keep a reference so it isn't GC'd

    # ── Clipboard intelligence ───────────────────────────────────────────────────

    def _open_about_panel(self):
        ov = AppInfoOverlay("about", parent=self.centralWidget())
        self._centre_overlay(ov)
        self._about_overlay = ov

    def _open_profile_panel(self):
        ov = ProfileOverlay(parent=self.centralWidget())
        ov.saved.connect(self._on_profile_details_saved)
        self._centre_overlay(ov)
        self._profile_overlay = ov

    def _on_profile_details_saved(self, profile: dict) -> None:
        self._refresh_personal_controls()
        if hasattr(self, "_profile_avatar_btn"):
            name = profile.get("name") or "A"
            letter = name.strip()[:1].upper() or "A"
            self._profile_avatar_btn.setText(letter)
        self._log.append_log(
            f"SYS: Profile updated — {profile.get('name', 'Current user')}.")

    def _open_developer_panel(self):
        ov = AppInfoOverlay("developer", parent=self.centralWidget())
        self._centre_overlay(ov)
        self._developer_overlay = ov

    def _on_clipboard_changed(self):
        try:
            text = QApplication.clipboard().text().strip()
            if len(text) >= 10:
                self._clipboard_sig.emit(text)
        except Exception:
            pass

    def _show_clipboard_panel(self, text: str):
        self._clipboard_panel.show_clipboard(text)
        self._position_clipboard_panel()

    def _position_clipboard_panel(self):
        cw = self.centralWidget()
        pw = ClipboardPanel._W
        ph = self._clipboard_panel.sizeHint().height() or ClipboardPanel._H
        x = (cw.width() - pw) // 2
        y = cw.height() - ph - 6
        self._clipboard_panel.setGeometry(x, y, pw, ph)
        self._clipboard_panel.raise_()

    def _on_clipboard_action(self, cmd: str):
        if self.on_text_command:
            threading.Thread(target=self.on_text_command, args=(cmd,), daemon=True).start()

    # ────────────────────────────────────────────────────────────────────────────

    def _do_interrupt(self):
        if self.on_interrupt:
            self.on_interrupt()

    def _toggle_mute(self):
        if self._chat_mode:
            self._toggle_chat_dictation()
            return
        if getattr(self, "_starter_exhausted_locked", False):
            self._log.append_log("SYS: Starter daily time expired. Please purchase a subscription plan to unlock the microphone.")
            self._show_pricing_overlay(forced_paywall=True)
            return
        self._muted = not self._muted
        self.hud.muted = self._muted
        self._style_mute_btn()
        if hasattr(self, "_mini_hud") and self._mini_hud:
            self._mini_hud.set_muted(self._muted)
        if self._muted:
            self._apply_state("MUTED")
            self._log.append_log("SYS: Microphone muted.")
        else:
            self._apply_state("LISTENING")
            self._log.append_log("SYS: Microphone active.")

    def _style_mute_btn(self):
        if not hasattr(self, "_mute_btn"):
            return
        self._mute_btn.setText("")
        self._mute_btn.setObjectName("MainMicBtn")
        if self._chat_mode:
            if self._chat_dictating:
                self._mute_btn.setIcon(_render_svg_icon("mic_solid", 26, "#ffffff"))
                self._mute_btn.setIconSize(QSize(26, 26))
                self._mute_btn.setToolTip("Listening for chat — click to stop")
                self._mute_btn.setStyleSheet("""
                    QPushButton#MainMicBtn {
                        background: qradialgradient(cx:0.5, cy:0.4, radius:0.5, fx:0.5, fy:0.35,
                            stop:0 #34d399, stop:0.65 #10b981, stop:1 #047857);
                        border: 2px solid #6ee7b7;
                        border-radius: 30px;
                    }
                    QPushButton#MainMicBtn:hover {
                        background: qradialgradient(cx:0.5, cy:0.4, radius:0.5, fx:0.5, fy:0.35,
                            stop:0 #6ee7b7, stop:0.65 #34d399, stop:1 #059669);
                        border: 2px solid #a7f3d0;
                    }
                """)
            else:
                self._mute_btn.setIcon(_render_svg_icon("mic_solid", 26, C.PRI))
                self._mute_btn.setIconSize(QSize(26, 26))
                self._mute_btn.setToolTip("Speak to type — click to dictate")
                self._mute_btn.setStyleSheet(f"""
                    QPushButton#MainMicBtn {{
                        background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {C.PANEL2}, stop:1 {C.PANEL});
                        border: 2px solid {C.BORDER};
                        border-radius: 30px;
                    }}
                    QPushButton#MainMicBtn:hover {{
                        border-color: {C.PRI};
                        background: {C.PRI_GHO};
                    }}
                """)
            return
        if self._muted:
            self._mute_btn.setIcon(_render_svg_icon("mic_off", 26, "#ffffff"))
            self._mute_btn.setIconSize(QSize(26, 26))
            self._mute_btn.setToolTip("Microphone muted — click to unmute")
            self._mute_btn.setStyleSheet("""
                QPushButton#MainMicBtn {
                    background: qradialgradient(cx:0.5, cy:0.4, radius:0.5, fx:0.5, fy:0.35,
                        stop:0 #fb7185, stop:0.65 #e11d48, stop:1 #9f1239);
                    border: 2px solid #fda4af;
                    border-radius: 30px;
                }
                QPushButton#MainMicBtn:hover {
                    background: qradialgradient(cx:0.5, cy:0.4, radius:0.5, fx:0.5, fy:0.35,
                        stop:0 #fda4af, stop:0.65 #fb7185, stop:1 #be123c);
                    border: 2px solid #ffe4e6;
                }
            """)
        else:
            self._mute_btn.setIcon(_render_svg_icon("mic_solid", 28, "#ffffff"))
            self._mute_btn.setIconSize(QSize(28, 28))
            self._mute_btn.setToolTip("Microphone active — click to mute")
            self._mute_btn.setStyleSheet("""
                QPushButton#MainMicBtn {
                    background: qradialgradient(cx:0.5, cy:0.35, radius:0.5, fx:0.5, fy:0.3,
                        stop:0 #818cf8, stop:0.55 #6366f1, stop:1 #4338ca);
                    border: 3px solid rgba(165, 180, 252, 0.70);
                    border-radius: 30px;
                }
                QPushButton#MainMicBtn:hover {
                    background: qradialgradient(cx:0.5, cy:0.35, radius:0.5, fx:0.5, fy:0.3,
                        stop:0 #a5b4fc, stop:0.55 #818cf8, stop:1 #4f46e5);
                    border: 3px solid #c7d2fe;
                }
            """)

    def _send(self):
        if getattr(self, "_starter_exhausted_locked", False):
            self._log.append_log("SYS: Starter daily time expired. Please purchase a subscription plan to unlock commands.")
            self._show_pricing_overlay(forced_paywall=True)
            return
        txt = self._input.text().strip()
        if not txt or (self._chat_mode and self._chat_busy): return
        if self._chat_mode and self._chat_dictating:
            self._stop_chat_dictation()
        self._input.clear()
        if hasattr(self, "_welcome_widget") and self._welcome_widget.isVisible():
            self._welcome_widget.hide()
            self._log.show()
        self._log.append_log(f"You: {txt}")
        callback = self.on_chat_command if self._chat_mode else self.on_text_command
        if callback:
            threading.Thread(target=callback, args=(txt,), daemon=True).start()

    def _apply_state(self, state: str):
        self.hud.state    = state
        self.hud.speaking = (state == "SPEAKING")
        labels = {
            "OFFLINE": ("OFFLINE", "#94a3b8", "rgba(255,255,255,0.06)", "rgba(255,255,255,0.1)"),
            "INITIALIZING": ("READY", "#10b981", "rgba(16,185,129,0.12)", "rgba(16,185,129,0.28)") if getattr(self, "_ready", True) else ("INITIALIZING", "#818cf8", "rgba(129,140,248,0.12)", "rgba(129,140,248,0.28)"),
            "READY": ("READY", "#10b981", "rgba(16,185,129,0.12)", "rgba(16,185,129,0.28)"),
            "LISTENING": ("LISTENING", "#10b981", "rgba(16,185,129,0.16)", "rgba(16,185,129,0.40)"),
            "THINKING": ("THINKING", "#a855f7", "rgba(168,85,247,0.15)", "rgba(168,85,247,0.35)"),
            "PROCESSING": ("PROCESSING", "#a855f7", "rgba(168,85,247,0.15)", "rgba(168,85,247,0.35)"),
            "SPEAKING": ("SPEAKING", "#818cf8", "rgba(129,140,248,0.15)", "rgba(129,140,248,0.35)"),
            "ERROR": ("ERROR", "#ef4444", "rgba(239,68,68,0.15)", "rgba(239,68,68,0.35)"),
            "RECONNECTING": ("RECONNECTING", "#f59e0b", "rgba(245,158,11,0.15)", "rgba(245,158,11,0.35)"),
            "MUTED": ("MUTED", "#f43f5e", "rgba(244,63,94,0.15)", "rgba(244,63,94,0.35)"),
            "SLEEPING": ("STANDBY", "#94a3b8", "rgba(255,255,255,0.06)", "rgba(255,255,255,0.1)"),
        }
        res = labels.get(state, ("READY", "#10b981", "rgba(16,185,129,0.12)", "rgba(16,185,129,0.28)"))
        text, colour, bg, border = res

        if hasattr(self, "_state_lbl"):
            self._state_lbl.setText(text)
            self._state_lbl.setStyleSheet(
                f"color: {colour}; background: {bg}; border: 1px solid {border}; border-radius: 8px; padding: 1px 8px;"
            )

        if hasattr(self, "_status_pill"):
            self._status_pill.setText(text.capitalize())
            self._status_pill.setStyleSheet(
                f"color: {colour}; background: {bg}; border: 1px solid {border}; border-radius: 11px; padding: 0 8px;"
            )

        if hasattr(self, "_voice_status_lbl"):
            voice_prompts = {
                "LISTENING": "Listening...",
                "THINKING": "Thinking...",
                "PROCESSING": "Processing...",
                "SPEAKING": f"{self._assistant_name.capitalize()} is speaking...",
                "ERROR": "Connection error • Click mic to retry",
                "RECONNECTING": "Reconnecting...",
                "OFFLINE": "Charlie is offline • Click mic to connect",
                "MUTED": "Microphone muted",
            }
            v_text = voice_prompts.get(state, "Hold or click microphone to talk")
            self._voice_status_lbl.setText(v_text)
            if state in ("LISTENING", "SPEAKING"):
                self._voice_status_lbl.setStyleSheet(f"color: {colour}; background: transparent; font-weight: bold;")
            else:
                self._voice_status_lbl.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent;")

        if hasattr(self, "_mini_hud") and self._mini_hud:
            self._mini_hud.set_state(state, text, colour, bg, border)

    def show_mini_hud(self):
        """Minimize full window into lightweight always-on-top Mini HUD overlay."""
        self.hide()
        if hasattr(self, "_mini_hud") and self._mini_hud:
            self._mini_hud.show()
            self._mini_hud.raise_()
            self._mini_hud.activateWindow()

    def _check_config(self) -> bool:
        try:
            from memory.config_manager import is_configured
            if is_configured():
                return True
        except Exception:
            pass
        if not API_FILE.exists():
            return False
        try:
            d = json.loads(API_FILE.read_text(encoding="utf-8"))
            return bool(d.get("gemini_api_key")) and bool(d.get("os_system"))
        except Exception:
            return False

    def _show_setup(self):
        if self._overlay is not None:
            self._overlay.raise_()
            self._overlay.activateWindow()
            return
        ov = SetupOverlay(self.centralWidget())
        cw = self.centralWidget()
        ow, oh = 460, 390
        ov.setGeometry(
            (cw.width()  - ow) // 2,
            (cw.height() - oh) // 2,
            ow, oh,
        )
        ov.done.connect(self._on_setup_done)
        ov.show()
        self._overlay = ov

    def _on_setup_done(self, key: str, os_name: str):
        clean_key = str(key or "").strip()
        if len(clean_key) < 10:
            if self._overlay:
                self._overlay.set_error("Invalid Gemini key: minimum 10 characters.")
            return

        # 1. DPAPI Save + Verification
        from memory.config_manager import save_api_keys
        saved = False
        try:
            saved = bool(save_api_keys(clean_key))
        except Exception as e:
            saved = False
        if not saved:
            if self._overlay:
                self._overlay.set_error("Failed to securely save credential via DPAPI vault.")
            return

        # 2. DPAPI Read-back Verification in memory
        from core.credential_vault import get_secret, has_secret, list_configured
        readback = None
        try:
            readback = (get_secret("gemini", "api_key", fallback_legacy=False) or "").strip()
        except Exception:
            readback = None
        if not readback or readback != clean_key:
            if self._overlay:
                self._overlay.set_error("Credential verification failed: DPAPI read-back mismatch.")
            return

        # 3. DPAPI Index Verification
        if not has_secret("gemini", "api_key") or "gemini/api_key" not in list_configured():
            if self._overlay:
                self._overlay.set_error("Credential verification failed: DPAPI index verification failed.")
            return

        # 3. Gemini Client Validation
        test_client = None
        try:
            from google import genai
            test_client = genai.Client(api_key=readback)
        except Exception as e:
            if self._overlay:
                self._overlay.set_error(f"Gemini client validation failed: {type(e).__name__}")
            return
        finally:
            if test_client is not None:
                try:
                    from core.gemini import safe_close_client
                    safe_close_client(test_client)
                except Exception:
                    pass

        # 4. ONLY THEN mark initialization complete
        os.makedirs(CONFIG_DIR, exist_ok=True)
        data = _read_full_config()
        data["os_system"] = os_name
        data.pop("gemini_api_key", None)
        try:
            API_FILE.write_text(
                json.dumps(data, indent=4),
                encoding="utf-8",
            )
        except Exception:
            pass
        self._ready = True
        if self._overlay:
            self._overlay.hide()
            self._overlay = None
        self._apply_state("LISTENING")
        self._assistant_name = _read_full_config().get("assistant_name", "CHARLIE") or "CHARLIE"
        self._log.append_log(f"SYS: Initialised. OS={os_name.upper()}. {self._assistant_name} online.")


class _RootShim:
    def __init__(self, app: QApplication):
        self._app = app
    def mainloop(self):
        self._app.exec()
    def protocol(self, *_):
        pass


class CharlieUI:
    def __init__(self, face_path: str, size=None):
        print("[CHARLIE-UI] 1/4 Constructing QApplication...", flush=True)
        self._app = QApplication.instance() or QApplication(sys.argv)
        self._app.setQuitOnLastWindowClosed(False)
        self._app.setStyle("Fusion")
        _f = get_app_font(9, QFont.Weight.Normal)
        self._app.setFont(_f)
        self._app.setStyleSheet("""
            QWidget {
                font-family: 'Inter', 'Segoe UI Variable Text', 'Segoe UI', -apple-system, sans-serif;
            }
            QLabel, QPushButton, QLineEdit, QTextEdit, QComboBox, QCheckBox, QProgressBar, QFrame {
                font-family: 'Inter', 'Segoe UI Variable Text', 'Segoe UI', -apple-system, sans-serif;
            }
            QToolTip {
                background-color: #192234;
                color: #f8fafc;
                border: 1px solid #1e2a40;
                border-radius: 6px;
                padding: 5px 8px;
                font-family: 'Inter', 'Segoe UI Variable Text', 'Segoe UI', sans-serif;
                font-size: 11px;
            }
            QScrollBar:vertical {
                background: transparent;
                width: 6px;
                margin: 0px;
                border-radius: 3px;
            }
            QScrollBar::handle:vertical {
                background: rgba(255, 255, 255, 0.12);
                min-height: 24px;
                border-radius: 3px;
            }
            QScrollBar::handle:vertical:hover {
                background: #6366f1;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
                background: transparent;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: transparent;
            }
            QScrollBar:horizontal {
                background: transparent;
                height: 6px;
                margin: 0px;
                border-radius: 3px;
            }
            QScrollBar::handle:horizontal {
                background: rgba(255, 255, 255, 0.12);
                min-width: 24px;
                border-radius: 3px;
            }
            QScrollBar::handle:horizontal:hover {
                background: #6366f1;
            }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
                width: 0px;
                background: transparent;
            }
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
                background: transparent;
            }
        """)
        print("[CHARLIE-UI] 2/4 Constructing MainWindow...", flush=True)
        self._win = MainWindow(face_path)
        self.root = _RootShim(self._app)
        print("[CHARLIE-UI] 3/4 Showing MainWindow...", flush=True)
        self._win.show()
        self._win.raise_()
        self._win.activateWindow()
        print("[CHARLIE-UI] 4/4 MainWindow is active and visible.", flush=True)

    @property
    def muted(self) -> bool:
        return self._win._muted

    @muted.setter
    def muted(self, v: bool):
        if v != self._win._muted:
            self._win._toggle_mute()

    @property
    def current_file(self) -> str | None:
        return self._win._drop_zone.current_file()

    @property
    def on_text_command(self):
        return self._win.on_text_command

    @on_text_command.setter
    def on_text_command(self, cb):
        self._win.on_text_command = cb

    @property
    def on_chat_command(self):
        return self._win.on_chat_command

    @on_chat_command.setter
    def on_chat_command(self, cb):
        self._win.on_chat_command = cb

    @property
    def on_new_chat(self):
        return self._win.on_new_chat

    @on_new_chat.setter
    def on_new_chat(self, cb):
        self._win.on_new_chat = cb

    @property
    def on_chat_dictation(self):
        return self._win.on_chat_dictation

    @on_chat_dictation.setter
    def on_chat_dictation(self, cb):
        self._win.on_chat_dictation = cb

    @property
    def chat_mode(self) -> bool:
        return bool(self._win._chat_mode)

    @property
    def chat_dictating(self) -> bool:
        return bool(self._win._chat_dictating)

    def set_chat_dictation_text(self, text: str) -> None:
        self._win._dictation_text_sig.emit(str(text or ""))

    def set_chat_dictation_state(self, active: bool, message: str = "") -> None:
        self._win._dictation_state_sig.emit(bool(active), str(message or ""))

    def set_chat_busy(self, busy: bool) -> None:
        self._win._chat_busy_sig.emit(bool(busy))

    @property
    def request_say(self):
        return self._win.request_say

    @request_say.setter
    def request_say(self, cb):
        self._win.request_say = cb

    @property
    def on_remote_clicked(self):
        return self._win.on_remote_clicked

    @on_remote_clicked.setter
    def on_remote_clicked(self, cb):
        self._win.on_remote_clicked = cb

    @property
    def on_interrupt(self):
        return self._win.on_interrupt

    @on_interrupt.setter
    def on_interrupt(self, cb):
        self._win.on_interrupt = cb

    @property
    def on_voice_change(self):
        return self._win.on_voice_change

    @on_voice_change.setter
    def on_voice_change(self, cb):
        self._win.on_voice_change = cb

    @property
    def on_listening_change(self):
        return self._win.on_listening_change

    @on_listening_change.setter
    def on_listening_change(self, cb):
        self._win.on_listening_change = cb

    @property
    def on_audio_device_change(self):
        return self._win.on_audio_device_change

    @on_audio_device_change.setter
    def on_audio_device_change(self, cb):
        self._win.on_audio_device_change = cb

    def show_confirm(self, title: str, detail: str) -> None:
        """Thread-safe: raise the irreversible-action gate. Called from action
        handlers running in executor threads, so it goes through a signal."""
        self._win._confirm_sig.emit(str(title)[:120], str(detail)[:300])

    def hide_confirm(self) -> None:
        """Thread-safe: take the gate down."""
        self._win._confirm_hide_sig.emit()

    @property
    def get_plugins(self):
        return self._win.get_plugins

    @get_plugins.setter
    def get_plugins(self, cb):
        self._win.get_plugins = cb

    @property
    def get_plugin_settings(self):
        return self._win.get_plugin_settings

    @get_plugin_settings.setter
    def get_plugin_settings(self, cb):
        self._win.get_plugin_settings = cb

    @property
    def rescan_plugins(self):
        return self._win.rescan_plugins

    @rescan_plugins.setter
    def rescan_plugins(self, cb):
        self._win.rescan_plugins = cb

    @property
    def on_wake_toggle(self):
        return self._win.on_wake_toggle

    @on_wake_toggle.setter
    def on_wake_toggle(self, cb):
        self._win.on_wake_toggle = cb

    @property
    def on_wake_manual(self):
        return self._win.on_wake_manual

    @on_wake_manual.setter
    def on_wake_manual(self, cb):
        self._win.on_wake_manual = cb

    @property
    def wake_get_state(self):
        return self._win.wake_get_state

    @wake_get_state.setter
    def wake_get_state(self, cb):
        self._win.wake_get_state = cb

    def set_audio_level(self, level: float) -> None:
        """Thread-safe: feed a 0.0–1.0 live audio level to the HUD waveform.
        Called from the audio threads; a plain float store is atomic under the
        GIL, so no signal/lock is needed for this cosmetic value."""
        try:
            self._win.hud.set_audio_level(level)
            if hasattr(self._win, "_mini_hud") and self._win._mini_hud:
                self._win._mini_hud.set_audio_level(level)
        except Exception:
            pass

    def glance(self, dx: float, dy: float, hold: float = 1.1) -> None:
        """Ask the avatar to look somewhere for a moment (see HoloAvatar.glance)."""
        try:
            if hasattr(self._win, "hud") and self._win.hud is not None:
                self._win.hud.glance(dx, dy, hold)
        except Exception:
            pass

    def classify_and_set_emotion(self, text: str) -> None:
        try:
            if hasattr(self._win, "hud") and self._win.hud is not None:
                self._win.hud.classify_and_set_emotion(text)
        except Exception:
            pass

    def set_emotion(self, emotion: object, intensity: float = 0.3) -> None:
        try:
            if hasattr(self._win, "hud") and self._win.hud is not None:
                self._win.hud.set_emotion(emotion, intensity)
        except Exception:
            pass

    def trigger_nod(self, amplitude: float = 0.005, duration: float = 0.65) -> None:
        try:
            if hasattr(self._win, "hud") and self._win.hud is not None:
                self._win.hud.trigger_nod(amplitude, duration)
        except Exception:
            pass

    @property
    def ptt_hold(self):
        return self._win.ptt_hold

    @ptt_hold.setter
    def ptt_hold(self, cb):
        self._win.ptt_hold = cb

    @property
    def on_push_to_talk(self):
        return self._win.on_push_to_talk

    @on_push_to_talk.setter
    def on_push_to_talk(self, cb):
        self._win.on_push_to_talk = cb

    def push_visemes(self, frames, hop: float, at: float) -> None:
        """Thread-safe: post a schedule of (level, openness, width) mouth frames
        for CHARLIE's own speech. `at` is the wall-clock time the batch begins to
        sound, not the time of the call. See HudCanvas.push_visemes()."""
        try:
            self._win.hud.push_visemes(frames, hop, at)
        except Exception:
            pass

    def notify_phone_connected(self) -> None:
        self._win.notify_phone_connected()

    def set_state(self, state: str):
        self._win._state_sig.emit(state)

    def write_log(self, text: str):
        self._win._log_sig.emit(text)

    def wait_for_api_key(self):
        while not self._win._ready:
            time.sleep(0.1)

    def show_content(self, title: str, text: str):
        """Thread-safe: display content in the panel below the HUD."""
        self._win._content_sig.emit(title[:48], text[:4000])

    def show_quiz(self, topic: str, questions, grade=None) -> None:
        """Thread-safe: put an interactive quiz on the board.

        `grade(question, given)` decides each answer — the plugin supplies it so
        the marking rules live with the questions rather than being duplicated
        here. Returning None from it means "CHARLIE should judge this one", which
        is how open answers and near-miss gap-fills are handled.

        Returns immediately: the user answers at their own pace and the finished
        result is delivered back through on_text_command.
        """
        self._win._quiz_sig.emit(str(topic or ""), list(questions or []), grade)

    def hide_quiz(self) -> None:
        """Thread-safe: clear any quiz currently on the board."""
        self._win._quiz_hide_sig.emit()

    def show_review(self, title: str, summary: str, findings, unclear=None) -> None:
        """Thread-safe: lay a document review into the panel below the HUD.

        `findings` is a list of {heading, detail, severity, quote, suggestion};
        severity is one of 'serious' / 'caution' / 'note' and decides colour and
        order here, so the caller supplies no styling of its own.
        """
        self._win._review_sig.emit(str(title or ""), str(summary or ""),
                                   list(findings or []), list(unclear or []))

    def prompt_reconfig(self):
        """Thread-safe: show the API key setup overlay (e.g. after an auth error)."""
        self._win._ready = False
        self._win._reconfig_sig.emit()

    def show_camera_frame(self, img_bytes: bytes):
        """Thread-safe: show a webcam frame in the small overlay (screen captures)."""
        self._win._camera_sig.emit(img_bytes)

    def start_camera_stream(self) -> None:
        """Thread-safe: start live camera feed in the full HUD area."""
        self._win.start_camera_stream()

    def stop_camera_stream(self) -> None:
        """Thread-safe: stop the live camera feed."""
        self._win.stop_camera_stream()

    @property
    def assistant_name(self) -> str:
        return self._win._assistant_name

    def start_speaking(self):
        self.set_state("SPEAKING")

    def stop_speaking(self):
        if not self.muted:
            self.set_state("LISTENING")

    def open_knowledge_panel(self):
        self._win._open_knowledge_panel()

    def open_proactive_panel(self):
        self._win._open_proactive_panel()


# Backward-compatible alias
JarvisUI = CharlieUI
