"""Cursor Mods core: cursor packs, Roblox file changes, settings, and backups."""

import os
import sys
import json
import math
import random
import shutil
import time
import logging
import threading
import tempfile
import configparser
from io import BytesIO
from logging.handlers import RotatingFileHandler

import tkinter as tk
from tkinter import filedialog

from PIL import Image, ImageTk, ImageDraw
from pack_store import PackStore, atomic_json

try:
    import keyboard
    HAS_KEYBOARD = True
except Exception:
    HAS_KEYBOARD = False

import ctypes
IS_WINDOWS = sys.platform.startswith("win")

try:
    from tkinterdnd2 import TkinterDnD, DND_FILES
    HAS_DND = True
    _TkRoot = TkinterDnD.Tk
except Exception:
    HAS_DND = False
    _TkRoot = tk.Tk

try:
    import pystray
    from pystray import MenuItem as TrayItem
    HAS_TRAY = True
except Exception:
    HAS_TRAY = False


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
UI_TEST_MODE = "--ui-test" in sys.argv or os.path.basename(sys.executable).lower().endswith("-ui-test.exe")
if UI_TEST_MODE:
    os.environ.setdefault("CURSORMODS_DATA_DIR", os.path.join(tempfile.gettempdir(), "CursorMods-ui-test"))
APP_DIR       = os.environ.get("CURSORMODS_DATA_DIR") or os.path.join(os.path.expanduser("~"), ".cursormods")
CURSOR_PACKS  = os.path.join(APP_DIR, "cursor_packs")
RBX_CUR_PACKS = os.path.join(APP_DIR, "roblox_cursor_packs")
UI_PACKS      = os.path.join(APP_DIR, "ui_packs")
SKY_PACKS     = os.path.join(APP_DIR, "sky_packs")
FONT_PACKS    = os.path.join(APP_DIR, "font_packs")
CONFIG_PATH   = os.path.join(APP_DIR, "config.json")
SPRITE_CACHE  = os.path.join(APP_DIR, "oneko.gif")
FIRSTRUN_FLAG = os.path.join(APP_DIR, "firstrun.flag")
LOG_PATH      = os.path.join(APP_DIR, "cursormods.log")

for _d in (APP_DIR, CURSOR_PACKS, RBX_CUR_PACKS, UI_PACKS, SKY_PACKS, FONT_PACKS):
    os.makedirs(_d, exist_ok=True)


# ---------------------------------------------------------------------------
# Logging  (dual console + rotating file, tagged per subsystem)
# ---------------------------------------------------------------------------
DEBUG_MODE = ("--debug" in sys.argv) or ("-d" in sys.argv)

logger = logging.getLogger("cursormods")
logger.setLevel(logging.DEBUG)
logger.propagate = False

_fmt = logging.Formatter(
    "%(asctime)s  %(levelname)-7s %(message)s", datefmt="%H:%M:%S"
)

_console = logging.StreamHandler(sys.stdout)
_console.setLevel(logging.DEBUG if DEBUG_MODE else logging.INFO)
_console.setFormatter(_fmt)
logger.addHandler(_console)

try:
    _file = RotatingFileHandler(LOG_PATH, maxBytes=512_000, backupCount=3,
                                encoding="utf-8")
    _file.setLevel(logging.DEBUG)
    _file.setFormatter(logging.Formatter(
        "%(asctime)s  %(levelname)-7s %(message)s"))
    logger.addHandler(_file)
except Exception as _e:
    print("Could not open log file:", _e)


def log(tag, msg, level=logging.INFO):
    """Tagged log helper: log('CURSOR', 'applied 5 files')."""
    logger.log(level, f"[{tag}] {msg}")


def log_exc(tag, msg):
    """Log an error with full traceback when in debug mode."""
    if DEBUG_MODE:
        logger.exception(f"[{tag}] {msg}")
    else:
        logger.error(f"[{tag}] {msg}")


log("BOOT", f"Cursor Mods starting  (debug={DEBUG_MODE}, windows={IS_WINDOWS})")
log("BOOT", f"App dir: {APP_DIR}")
log("BOOT", f"Log file: {LOG_PATH}")


# ---------------------------------------------------------------------------
# Theme presets
# ---------------------------------------------------------------------------
# Each theme defines the full palette the UI uses.  "dark" flag controls a few
# contrast choices (e.g. checkbox check color).
THEMES = {
    "Black": {
        "dark": True,
        "bg": "#0b0b0d", "header": "#151518", "panel": "#0b0b0d",
        "accent": "#5e5ce6", "text": "#ffffff", "text_med": "#b8b8c0",
        "text_dim": "#7a7a85", "btn": "#1c1c22", "btn_hover": "#2a2a33",
        "section": "#20202a", "warn": "#e8a31a",
    },
    "White": {
        "dark": False,
        "bg": "#f5f5f7", "header": "#e8e8ec", "panel": "#f5f5f7",
        "accent": "#5e5ce6", "text": "#111114", "text_med": "#3a3a42",
        "text_dim": "#8a8a92", "btn": "#e2e2e8", "btn_hover": "#d2d2da",
        "section": "#d0d0d8", "warn": "#c07a00",
    },
    "Navy Blue": {
        "dark": True,
        "bg": "#0d1b2a", "header": "#12253a", "panel": "#0d1b2a",
        "accent": "#4aa3ff", "text": "#ffffff", "text_med": "#b6cbe0",
        "text_dim": "#6f8aa5", "btn": "#1a3049", "btn_hover": "#254264",
        "section": "#1f3a58", "warn": "#f0b429",
    },
    "Dark Purple": {
        "dark": True,
        "bg": "#160f22", "header": "#20152f", "panel": "#160f22",
        "accent": "#b388ff", "text": "#ffffff", "text_med": "#cbb8e6",
        "text_dim": "#8a75a5", "btn": "#2a1c3d", "btn_hover": "#3a2852",
        "section": "#301f47", "warn": "#e8a31a",
    },
    "Dark Green": {
        "dark": True,
        "bg": "#0d1a12", "header": "#12251a", "panel": "#0d1a12",
        "accent": "#3ecf7e", "text": "#ffffff", "text_med": "#b4d8c2",
        "text_dim": "#6f9a80", "btn": "#173026", "btn_hover": "#214536",
        "section": "#1c3a2b", "warn": "#e8a31a",
    },
    "Light Pink": {
        "dark": False,
        "bg": "#fdeef4", "header": "#f9dbe8", "panel": "#fdeef4",
        "accent": "#e75fa0", "text": "#3a1526", "text_med": "#7a3a55",
        "text_dim": "#b07a90", "btn": "#f7d0e0", "btn_hover": "#f2bcd3",
        "section": "#f0c2d7", "warn": "#c07a00",
    },
}
DEFAULT_THEME = "Black"


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
DEFAULT_CONFIG = {
    "startup":        True,
    "enabled":        False,
    "kitty_opt_in_v2": True,
    "opacity":        0.97,
    "speed":          10,
    "cat_size":       32,
    "toggle_hotkey":  "ctrl+shift+h",
    "freeze_hotkey":  "ctrl+shift+f",
    "panel_x":        None,
    "panel_y":        None,
    "theme":          DEFAULT_THEME,
    # windows cursor
    "cursor_pack":    None,
    "cursor_size":    None,
    # roblox
    "roblox_enabled": True,
    "roblox_cursor_pack": None,
    "ui_pack":        None,
    "sky_pack":       None,
    "font_pack":      None,
}


def load_config():
    cfg = dict(DEFAULT_CONFIG)
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            loaded = json.load(f)
            cfg.update(loaded)
        log("CONFIG", "Loaded config.json")
    except FileNotFoundError:
        log("CONFIG", "No config.json yet; using defaults")
    except Exception as e:
        log_exc("CONFIG", f"Failed to read config: {e}")
    # The old release enabled Kitty without asking. Migrate once to opt-in.
    if "kitty_opt_in_v2" not in locals().get("loaded", {}):
        cfg["enabled"] = False
        cfg["kitty_opt_in_v2"] = True
    return cfg


def save_config(cfg):
    try:
        atomic_json(CONFIG_PATH, dict(cfg))
        log("CONFIG", "Saved config.json", level=logging.DEBUG)
    except Exception as e:
        log_exc("CONFIG", f"Failed to save config: {e}")


# Embedded app icons (base64 PNG) - reused from original
_ICON_SMALL_B64 = "iVBORw0KGgoAAAANSUhEUgAAABQAAAAUCAYAAACNiR0NAAABvklEQVR4nJ3UPY9NURQG4OfcQZDQColgokBMQjHCNBKJTuE3SESlUdFISESvxD8QjUKh9BEKCSKmoHIrEhEfGTF35pyj2GvP3fe4rptZyU7O3nut96y13vXuCj002I/zOIm92I5NxtsAP/ARj3EH7wMLnMEXtOtcX3E2g21FPy4GqLEaWU8CqWMNYv8pqnIQywHwP5C8un5NgB/tYSZqr4oe3Yoe5YDSmvC9hrfFeYWNcBgrRfAyNuBC7Fc7ZbZBANzt+Mx3MyORswW38TwqqOMuA1+JuMVO7JDmwuo4b3G1KLkJ8EXcj/PPRVz7L8BtAVrhUgBl3wazuCfN6M8x8eaM9rDBCTwxmekXuGm0t/PdDLPzI3zAAVyMn6yEzw3sxENcjrs1nNyrErCHbzgnkdPHA2kkXkpE7cJ1vClaAdU4lltsxhF8l6Z/j0TGDuzGEhYi0zYw1mZ2zlA+pQp+47Whxt8V931/97TBMdiHX0alN05akySYe3wo9/GZoUpKp7rY18VPy/Nc3StJYeB4lLje56vGqQyWKV/A08hyWqAVifnTGasqQDP1s+Jdm8KWpHntYiDptDtC09pM/vgDEfrnHJaw+rcAAAAASUVORK5CYII="
_ICON_TRAY_B64  = "iVBORw0KGgoAAAANSUhEUgAAAEAAAABACAYAAACqaXHeAAAHq0lEQVR4nO2ba4hVVRTHf+feq44zas8p0+yBIiERpJFBFhlZRkGFRoEVBZkfIgiC6pMYYREE9vpURIY9vhQ9LVGDrIzSiEiKovJROVRaYzraTDN3Th/WXu5195wz955z7rzCP2zOnfPYe63/XnvtvdbeE1EfZaAfiM29acBs4BxgFnA60A6cBEwGWkyx3+dBBPQA/7jrIeAv4A+gA/gR+A74Hvg1QfZqvcrTUEKEVwUuBK4FLgPmIMqOJnQiRGwB3gW2mmclpBMbRtn8XgJ8jCfDlirQ50rVlX5Tkr7JU2ydVVO03aRvPgOWpejUkPKzgfcDIXpdo81UrpkkVZ2MVr4PgfMaJaHkrouB/a4C7eGRVjBrUQuJEb9xQz0SVPlFiLOJETZHWpGiRUnoNySorkcRuTIF2Bt8+H8o6icOITOW6nuUibJ7YQkyxfWRwWmMAZQQnSYBdyC6lvUB+CliqXs42PQ4VhEhul2P6F21D0AWMB348TLSZtvsojodAc50OpdKhoAZwCkZGB0NiDO8qxYwEThb71kCpuB9QdYhoE5muJFVTh3qp+r3djoY7655FCnnEKYoqohXh+wyj9MflgCtJI8ir+OdylBbgrbzFrJgy7TGD2EJyGtOe5DZ407391AOBx2evcBq4FNgvbs3aNSXhiQLaJRKwGYnwFpgJVChYK/UabMErAO+dL+fd89yDUHrBPNiO0LeBOBhpEfqxuE5oL1/AFiFD3G3AV348D0TigwBXSl+Gwh4F7DP/W6mJWjvrwZ+wTvefcBOI0MmDAgKGoQq22Ua1+VzB3A/OXskBVVX99fA03gLq7h2P3fvZSa8CAEgIXNnIGgFeBHJzDR7KDyARKq6qFFsz1thXgIUh4DuhPsxcA/JwmaF9v4HwAaE4HDK/cZdMwdwRS2gGz829V4VWWjsAB4nRz4ugBL40CBydDhZMpNdZBoEydTCQAfaj/TGo4iPyEtC1X37JpKXDIeUytyJzA5ZERUdAlapKLhfAg4D95F/qlXiHgzaCOvrQaI8KGABeYScYBoNG+5DQuwvkLFbE4M3gKqT6RmEyOnmXogYWR1mRZzXAmwOIS2CLCG9sgY4A28VjaKE9OxsxAGOd+0kTa+aAM2MogS0IySEAqmnvgK4CNlIichmZRGi9GIkgbEOieN1vVEy7+meQVZERZ1gG9BqBAFRvhdJsKxDkpBppltXQESxFuBiZDjdjt+bUGuoYELcLCjqAyYCJ5i/y4jyFyBBUjt+Hs8Lm7c8EXgB8QstCBERonxbkcohe3pJp7oZ7p4uS5cBHyFjV99pBnRG6AfuBjYimZ3YXU82smWqVJE3HzAPUbIHuBd4Cemdf/E5ed3DywPd8gIfvXYDC4D3XFvTEGvsJ5seuWcBTENXOwFvQjy+TkfjEWLKiHXobJHF0nSc67dHXLstrp25wBMIGfp+Jh0qGT+wUNOeh5jkKifAOISQd5D5X9PQlwML3TeNJF5V+T3AU8hUeBA4C7gZWO7eWYFYHwjRWRDbjy6lOXsCXyFOMAm3OWF1Gz2tDk2rbQdOS6nrRvxudaOy6bu3uDoqzSJABfkdGY8glpA0Pa0IhEnawOhHToHMNN/Z4aQr0JWm/TwEjGsWAVqxrtknICauw+Qa4Cr3u4Sc5LA9HZJpo7+FjrQI7wTVL7QCuwapKxMBl+QkQN8/AEw1iquwk4C/EdOf6tp6NVA2yQLmu3ffdvfPdX9X8HM/jvRGrWAAAUWjQfCedwPwG7WxQYzEAZ3utxKw3gmcFEZHSK/uwB+y2g+cH7yrbXzi/s613mgGAbG7ajgaKnUI2cTQZyUkt9dN7UGs2Hxz2NXXiuQAe/G7QKHsc9w1d+qtqA9Qk9UpCsQH6DjVXtoJHO+ev0y62eoBqOXu3QXAa8hSV52qdaxbGdypDsssoBVvxHtoi1a8id6Knwr1+w6k1+1psG78kZYkTAIeM6TlmQWaRoAVYhsyR09Heq0NGftX4p2fff9ZR9oMJNoLe3Mr8AhyRnE+cB3wJLA7h7xDNg2GSsWI598N/IyM3zil/oPAJsR67BG3RuRotOdTLcAuHWOKQyO2GDlvMMU80/uht56MJE5CqDNVJXVaVXJKFHfiUbMJAC+Usg7e+6dBPXjSVBbeq1dXFsQVvJBpKe68yJICG+4TaV36wzK5j5yp5TEE1Xevu8Y6ZiN3c5c+GGbBhgMxoud+4Ce9Z5OKVeRgMQzdAYeRhDrhbUikWQafEdIef8Vdm+VkRhsivI41+4g2dN3MwMXIWC+agPkBWZUOmEIj/IJoLqP7/wLyFI05ljodNaSugSVBY2zN7I7lojqsDZRPJMCS8Jxhb6xagiq/BUmb20TNACgBGsaCxOLWjMYKEfZ/iTYBxzl9NDxPXaBZEtRJrEDSXZYIbaB/FJWk/xdag88d1FXeEhBawizkQGIXw9uTectm5N/7VCerfA0BSWyE98r4vfeZSDy+CElFtSM7QHbPPjynk3ZuR9tJetYItN4+JKTeiexJvoEcoQV/atW2UdNemjkkHXaIqD2E0Ib8f0HbIPUMB3qAP11R6BAO84QDyB5M8KRnWrHdsBwt0CGbdlgi0dKK9FzWEx9DiTi4HsMxHENj+A+Nu1og880rBgAAAABJRU5ErkJggg=="

ONEKO_URL = (
    "https://raw.githubusercontent.com/adryd325/oneko.js/"
    "14bab15a755d0e35cd4ae19c931d96d306f99f42/oneko.gif"
)


# ---------------------------------------------------------------------------
# Win32 overlay helpers
# ---------------------------------------------------------------------------
if IS_WINDOWS:
    user32 = ctypes.windll.user32
    GWL_EXSTYLE       = -20
    WS_EX_LAYERED     = 0x00080000
    WS_EX_TRANSPARENT = 0x00000020
    WS_EX_TOOLWINDOW  = 0x00000080
    WS_EX_NOACTIVATE  = 0x08000000
    HWND_TOPMOST      = -1
    SWP_NOMOVE        = 0x0002
    SWP_NOSIZE        = 0x0001
    SWP_NOACTIVATE    = 0x0010

    if ctypes.sizeof(ctypes.c_void_p) == 8:
        _get_long = user32.GetWindowLongPtrW
        _set_long = user32.SetWindowLongPtrW
    else:
        _get_long = user32.GetWindowLongW
        _set_long = user32.SetWindowLongW

    def make_click_through(hwnd):
        s = _get_long(hwnd, GWL_EXSTYLE)
        s |= WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE
        _set_long(hwnd, GWL_EXSTYLE, s)

    def remove_click_through(hwnd):
        s = _get_long(hwnd, GWL_EXSTYLE)
        _set_long(hwnd, GWL_EXSTYLE, s & ~WS_EX_TRANSPARENT)

    def force_topmost(hwnd):
        user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0,
                            SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)
else:
    def make_click_through(hwnd): pass
    def remove_click_through(hwnd): pass
    def force_topmost(hwnd): pass


# ---------------------------------------------------------------------------
# Win32 cursor API
# ---------------------------------------------------------------------------
if IS_WINDOWS:
    _cur = ctypes.WinDLL("user32")
    _cur.LoadImageW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_uint,
                                ctypes.c_int, ctypes.c_int, ctypes.c_uint]
    _cur.LoadImageW.restype = ctypes.c_void_p
    _cur.SetSystemCursor.argtypes = [ctypes.c_void_p, ctypes.c_uint]
    _cur.SetSystemCursor.restype  = ctypes.c_bool
    _cur.SystemParametersInfoW.argtypes = [ctypes.c_uint, ctypes.c_uint,
                                           ctypes.c_void_p, ctypes.c_uint]
    _cur.SystemParametersInfoW.restype = ctypes.c_bool
    _cur.GetSystemMetrics.argtypes = [ctypes.c_int]
    _cur.GetSystemMetrics.restype  = ctypes.c_int
else:
    _cur = None


def _get_default_cursor_size() -> int:
    if IS_WINDOWS:
        try:
            sz = _cur.GetSystemMetrics(13)
            return sz if sz > 0 else 32
        except Exception:
            pass
    return 32


# ---------------------------------------------------------------------------
# Hotkey helpers
# ---------------------------------------------------------------------------
_NUMPAD_SCANCODES = {
    "num 0": 82, "num 1": 79, "num 2": 80, "num 3": 81,
    "num 4": 75, "num 5": 76, "num 6": 77, "num 7": 71,
    "num 8": 72, "num 9": 73, "num *": 55, "num /": 53,
    "num +": 78, "num -": 74, "num decimal": 83, "num enter": 28,
}


def _add_hotkey(display_str, callback):
    parts = [p.strip() for p in display_str.lower().split("+")]
    numpad_part = next((p for p in parts if p in _NUMPAD_SCANCODES), None)
    if numpad_part is not None and HAS_KEYBOARD:
        scan_code = _NUMPAD_SCANCODES[numpad_part]
        mods = [p for p in parts if p not in _NUMPAD_SCANCODES]
        def _handler(event):
            if (event.event_type == keyboard.KEY_DOWN
                    and event.scan_code == scan_code
                    and all(keyboard.is_pressed(m) for m in mods)):
                callback()
        return ("hook", keyboard.hook(_handler, suppress=False))
    else:
        if HAS_KEYBOARD:
            keyboard.add_hotkey(display_str, callback)
        return ("hotkey", display_str)


def _remove_hotkey(token):
    if token is None or not HAS_KEYBOARD:
        return
    kind, value = token
    try:
        keyboard.unhook(value) if kind == "hook" else keyboard.remove_hotkey(value)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Cursor role constants  (added Help = 32651)
# ---------------------------------------------------------------------------
# .crs [section] name -> Win32 OCR id
CRS_ROLE_MAP = {k.lower(): v for k, v in {
    "Arrow":       32512,
    "IBeam":       32513,
    "Wait":        32514,
    "Crosshair":   32515,
    "Cross":       32515,
    "UpArrow":     32516,
    "Help":        32651,
    "SizeNWSE":    32642,
    "SizeNESW":    32643,
    "SizeWE":      32644,
    "SizeNS":      32645,
    "SizeAll":     32646,
    "No":          32648,
    "Hand":        32649,
    "AppStarting": 32650,
}.items()}

# install.inf registry role name -> Win32 OCR id
INF_ROLE_MAP = {
    "Arrow":       32512,
    "Help":        32651,
    "AppStarting": 32650,
    "Wait":        32514,
    "Crosshair":   32515,
    "Cross":       32515,
    "IBeam":       32513,
    "NWPen":       32631,   # pen / handwriting -> no direct swap target; kept for completeness
    "No":          32648,
    "SizeNS":      32645,
    "SizeWE":      32644,
    "SizeNWSE":    32642,
    "SizeNESW":    32643,
    "SizeAll":     32646,
    "UpArrow":     32516,
    "Hand":        32649,
}

NUMBER_MAP = {
    "1":  32512, "2": 32651, "3":  32650, "4":  32514, "5":  32515,
    "6":  32513, "8":  32648, "9":  32645, "10": 32644,
    "11": 32642, "12": 32643, "13": 32646, "14": 32516, "15": 32649,
}

CURSOR_ROLES = [
    (32512, "Arrow",    ["arrow", "normal", "default", "standard"]),
    (32513, "IBeam",    ["ibeam", "text", "beam", "edit"]),
    (32514, "Wait",     ["wait", "busy", "loading", "hourglass"]),
    (32515, "Cross",    ["cross", "precision", "crosshair", "target"]),
    (32516, "UpArrow",  ["uparrow", "alternate", "alt"]),
    (32651, "Help",     ["help", "question", "whatsthis"]),
    (32642, "SizeNWSE", ["nwse", "sizenwse", "diagonal1"]),
    (32643, "SizeNESW", ["nesw", "sizenesw", "diagonal2"]),
    (32644, "SizeWE",   ["sizewe", "horizontal", "ew"]),
    (32645, "SizeNS",   ["sizens", "vertical", "ns"]),
    (32646, "SizeAll",  ["move", "sizeall", "drag", "crawl", "fly", "pan"]),
    (32648, "No",       ["no", "unavail", "forbidden", "deny", "block"]),
    (32649, "Hand",     ["hand", "link", "pointer", "finger", "click"]),
    (32650, "AppStart", ["appstart", "working", "starting", "background"]),
]

ROLE_NAMES = {rid: name for rid, name, _ in CURSOR_ROLES}
ROLE_NAMES[32651] = "Help"


# ---------------------------------------------------------------------------
# Generic pack manager  (import/list/delete a folder of files)
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Windows Cursor Manager  (.inf -> .crs -> keyword -> numeric)
# ---------------------------------------------------------------------------
class CursorManager:
    def __init__(self):
        self.store = PackStore(CURSOR_PACKS, "CURSOR")

    def list_packs(self):
        return self.store.list_packs()

    def import_pack(self, folder_path):
        return self.store.import_pack(folder_path)

    def delete_pack(self, name):
        self.store.delete_pack(name)

    def apply_pack(self, pack_name, cursor_size=32):
        mapping = self._get_pack_mapping(pack_name)
        log("CURSOR", f"Applying '{pack_name}' size={cursor_size}: "
                      f"{ {ROLE_NAMES.get(r, r): os.path.basename(p) for r, p in mapping.items()} }")
        applied = 0
        for role_id, path in mapping.items():
            if self._set_cursor(role_id, path, cursor_size):
                applied += 1
            else:
                log("CURSOR", f"  FAILED role {ROLE_NAMES.get(role_id, role_id)} <- {path}",
                    level=logging.WARNING)
        log("CURSOR", f"Applied {applied}/{len(mapping)} cursors")
        return applied

    def _get_pack_mapping(self, pack_name):
        if not IS_WINDOWS:
            return {}
        pack_dir = self.store.pack_dir(pack_name)
        if not os.path.isdir(pack_dir):
            log("CURSOR", f"Pack dir missing: {pack_dir}", level=logging.WARNING)
            return {}

        # Recursively find cursor + scheme files (handles nested folders)
        all_files = self.store.find_files(pack_name, (".cur", ".ani"))
        inf_files = self.store.find_files(pack_name, (".inf",))
        crs_files = self.store.find_files(pack_name, (".crs",))
        role_to_path = {}

        # 1. install.inf  (authoritative Windows scheme)
        if inf_files:
            inf_path = next(iter(inf_files.values()))
            inf_map = self._parse_inf(inf_path)
            log("CURSOR", f".inf provided {len(inf_map)} role(s): {list(inf_map.keys())}")
            for role_name, filename in inf_map.items():
                role_id = INF_ROLE_MAP.get(role_name)
                if role_id is None:
                    continue
                path = self._find_file_ci(all_files, filename)
                if path:
                    role_to_path[role_id] = path

        # 2. .crs scheme
        if not role_to_path and crs_files:
            crs_path = next(iter(crs_files.values()))
            crs_map = self._parse_crs(crs_path)
            log("CURSOR", f".crs provided {len(crs_map)} role(s)")
            for role_name, filename in crs_map.items():
                role_id = CRS_ROLE_MAP.get(role_name.lower())
                if role_id is None:
                    continue
                path = self._find_file_ci(all_files, filename)
                if path:
                    role_to_path[role_id] = path

        # 3. keyword + numeric fallback for anything unclaimed
        claimed = set(role_to_path.values())
        kw_best, unmatched = {}, []
        for fname, fpath in all_files.items():
            if fpath in claimed:
                continue
            stem = os.path.splitext(fname)[0]
            if stem.isdigit():
                num_role = NUMBER_MAP.get(stem)
                if num_role and num_role not in role_to_path and num_role not in kw_best:
                    kw_best[num_role] = (0, fpath)
                continue
            role_id, score = self._match_keyword(fname)
            if role_id is not None and role_id not in role_to_path:
                prev = kw_best.get(role_id, (-1, ""))[0]
                if score > prev:
                    kw_best[role_id] = (score, fpath)
            else:
                unmatched.append(fpath)
        for role_id, (_, fpath) in kw_best.items():
            role_to_path[role_id] = fpath

        _ARROW = 32512
        if _ARROW not in role_to_path and unmatched:
            role_to_path[_ARROW] = unmatched[0]

        return role_to_path

    def restore_defaults(self):
        if IS_WINDOWS:
            _cur.SystemParametersInfoW(0x0057, 0, None, 0x0002)
            log("CURSOR", "Restored system cursor defaults")

    # ---- parsers ----
    @staticmethod
    def _parse_inf(inf_path):
        """Parse a Windows cursor install.inf -> {RoleName: filename}."""
        result = {}
        try:
            for enc in ("utf-8-sig", "utf-8", "latin-1"):
                try:
                    with open(inf_path, "r", encoding=enc, errors="replace") as fh:
                        lines = fh.read().splitlines()
                    break
                except Exception:
                    continue
            in_reg = False
            for line in lines:
                s = line.strip()
                if s.lower().startswith("[") and s.endswith("]"):
                    in_reg = s.lower() == "[scheme.reg]"
                    continue
                if in_reg and "control panel\\cursors" in s.lower():
                    # HKCU,"Control Panel\Cursors","Arrow",,"%25%\Cursors\Arrow.cur"
                    parts = s.split(",")
                    if len(parts) >= 5:
                        role = parts[2].strip().strip('"')
                        val = parts[-1].strip().strip('"')
                        if not role or role == "(Default)":
                            continue
                        fname = val.replace("\\", "/").split("/")[-1]
                        if fname:
                            result[role] = fname
        except Exception as e:
            log_exc("CURSOR", f"_parse_inf failed: {e}")
        return result

    @staticmethod
    def _parse_crs(crs_path):
        cp = configparser.RawConfigParser()
        cp.optionxform = str
        for enc in ("utf-8-sig", "utf-8", "latin-1"):
            try:
                with open(crs_path, "r", encoding=enc, errors="replace") as fh:
                    raw = fh.read()
                cp.read_string(raw.replace("\ufeff", ""))
                break
            except Exception:
                continue
        result = {}
        for section in cp.sections():
            try:
                result[section] = cp.get(section, "Path")
            except Exception:
                pass
        return result

    @staticmethod
    def _find_file_ci(file_dict, target):
        tl = target.lower()
        for fname, fpath in file_dict.items():
            if fname.lower() == tl:
                return fpath
        return None

    @staticmethod
    def _match_keyword(filename):
        name = os.path.splitext(filename)[0].lower()
        best_id, best_score = None, 0
        for role_id, _, keywords in CURSOR_ROLES:
            score = sum(1 for kw in keywords if kw in name)
            if score > best_score:
                best_score, best_id = score, role_id
        return best_id, best_score

    @staticmethod
    def _set_cursor(cursor_id, cur_path, size):
        if not IS_WINDOWS:
            return False
        try:
            IMAGE_CURSOR = 2
            LR_LOADFROMFILE = 0x0010
            LR_DEFAULTSIZE = 0x0040
            flags = LR_LOADFROMFILE
            # For .ani (animated) let Windows use the native size for correct animation
            is_ani = cur_path.lower().endswith(".ani")
            w = h = size
            if is_ani:
                w = h = 0
                flags |= LR_DEFAULTSIZE
            hcur = _cur.LoadImageW(None, cur_path, IMAGE_CURSOR, w, h, flags)
            if not hcur:
                return False
            return bool(_cur.SetSystemCursor(hcur, cursor_id))
        except Exception as e:
            log_exc("CURSOR", f"_set_cursor {cur_path}: {e}")
            return False


# ---------------------------------------------------------------------------
# Roblox integration
# ---------------------------------------------------------------------------
ROBLOX_VERSIONS_DIR = os.path.join(
    os.environ.get("LOCALAPPDATA", os.path.expanduser("~")),
    "Roblox", "Versions"
)
ROBLOX_BACKUP_DIR = os.path.join(APP_DIR, "roblox_backups")

# Cursor role -> Roblox PNG filenames (in KeyboardMouse folder)
ROBLOX_CURSOR_MAP = {
    32512: ["ArrowCursor.png", "ArrowFarCursor.png"],
    32513: ["IBeamCursor.png"],
    32515: ["CrosshairCursor.png"],
    32649: ["HandCursor.png"],
    32646: ["MoveCursor.png"],
    32644: ["ResizeHorizontalCursor.png"],
    32645: ["ResizeVerticalCursor.png"],
    32642: ["ResizeDiagonalCursor.png"],
    32643: ["ResizeDiagonal2Cursor.png"],
    32648: ["NotAllowedCursor.png"],
    32514: ["WaitCursor.png"],
    32650: ["WaitCursor.png"],
}
# MouseLockedCursor.png lives in content/textures/ (root), NOT KeyboardMouse.
MOUSELOCKED_NAME = "MouseLockedCursor.png"

# Feature keys used for backup subfolders and status
FEAT_CURSOR = "cursors"
FEAT_UI     = "ui"
FEAT_SKY    = "sky"
FEAT_FONT   = "fonts"


class RobloxIntegration:
    def __init__(self, cursor_mgr, cfg, status_callback=None):
        self.cursor_mgr = cursor_mgr
        self.cfg = cfg
        self.status_callback = status_callback
        self.rbx_cursor_store = PackStore(RBX_CUR_PACKS, "ROBLOX-CUR")
        self.ui_store   = PackStore(UI_PACKS,   "UI")
        self.sky_store  = PackStore(SKY_PACKS,  "SKY")
        self.font_store = PackStore(FONT_PACKS, "FONT")
        self._watcher_thread = None
        self._stop_event = threading.Event()
        self._last_version = None
        os.makedirs(ROBLOX_BACKUP_DIR, exist_ok=True)

    # ---- status ----
    def _status(self, msg, fg=None):
        if self.status_callback:
            self.status_callback(msg, fg)

    # ---- version resolution ----
    def find_latest_version_folder(self):
        if not os.path.isdir(ROBLOX_VERSIONS_DIR):
            log("ROBLOX", f"Versions dir not found: {ROBLOX_VERSIONS_DIR}",
                level=logging.WARNING)
            return None
        dirs = [d for d in os.listdir(ROBLOX_VERSIONS_DIR)
                if d.startswith("version-")
                and os.path.isdir(os.path.join(ROBLOX_VERSIONS_DIR, d))
                and os.path.isdir(os.path.join(ROBLOX_VERSIONS_DIR, d, "content"))]
        if not dirs:
            log("ROBLOX", "No version-* folders with content/ found",
                level=logging.WARNING)
            return None
        dirs.sort(reverse=True)
        chosen = os.path.join(ROBLOX_VERSIONS_DIR, dirs[0])
        log("ROBLOX", f"Latest version: {dirs[0]}", level=logging.DEBUG)
        return chosen

    def _version_name(self):
        v = self.find_latest_version_folder()
        return os.path.basename(v) if v else None

    def _backup_root(self):
        vn = self._version_name()
        return os.path.join(ROBLOX_BACKUP_DIR, vn) if vn else None

    # ---- generic backup-before-write ----
    def _backup_file(self, feature, version_root, rel_path):
        """Backup a single game file (by path relative to version root) once."""
        vn = os.path.basename(version_root)
        bdir = os.path.join(ROBLOX_BACKUP_DIR, vn, feature)
        backup_path = os.path.join(bdir, rel_path)
        if os.path.exists(backup_path):
            return  # already backed up this file for this version
        src = os.path.join(version_root, rel_path)
        if not os.path.isfile(src):
            return  # nothing to back up (file didn't exist originally)
        try:
            os.makedirs(os.path.dirname(backup_path), exist_ok=True)
            shutil.copy2(src, backup_path)
            log("BACKUP", f"{feature}: saved {rel_path}", level=logging.DEBUG)
        except Exception as e:
            log_exc("BACKUP", f"{feature}: failed to back up {rel_path}: {e}")

    def _overlay_file(self, feature, version_root, rel_path, src_file):
        """Backup then overwrite a game file with src_file."""
        self._backup_file(feature, version_root, rel_path)
        dest = os.path.join(version_root, rel_path)
        try:
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.copy2(src_file, dest)
            log(feature.upper(), f"wrote {rel_path}", level=logging.DEBUG)
            return True
        except Exception as e:
            log_exc(feature.upper(), f"failed writing {rel_path}: {e}")
            return False

    # ==================================================================
    # ROBLOX CURSORS  (PNG)
    # ==================================================================
    def cursor_folder(self, version_root):
        folder = os.path.join(version_root, "content", "textures",
                              "Cursors", "KeyboardMouse")
        return folder if os.path.isdir(folder) else None

    # Every Roblox cursor destination filename in KeyboardMouse (for exact match)
    _RBX_KM_FILES = {
        "ArrowCursor.png", "ArrowFarCursor.png", "IBeamCursor.png",
        "CrosshairCursor.png", "HandCursor.png", "MoveCursor.png",
        "ResizeHorizontalCursor.png", "ResizeVerticalCursor.png",
        "ResizeDiagonalCursor.png", "ResizeDiagonal2Cursor.png",
        "NotAllowedCursor.png", "WaitCursor.png",
    }

    def _get_roblox_cursor_mapping(self, pack_name):
        """Return (dest_filename -> src_path, mouselocked_src).

        Exact-filename matches win (so ArrowCursor vs ArrowFarCursor stay
        distinct). Anything not matched by name is routed by keyword to the
        Roblox roles it maps to, filling only destinations not already taken."""
        pack_dir = self.rbx_cursor_store.pack_dir(pack_name)
        if not os.path.isdir(pack_dir):
            return {}, None
        all_png = self.rbx_cursor_store.find_files(pack_name, (".png",))

        dest_to_src = {}          # KeyboardMouse filename -> source path
        mouselocked = None
        lower_map = {fn.lower(): fn for fn in self._RBX_KM_FILES}

        # 1. exact filename matches
        used = set()
        for fname, fpath in all_png.items():
            low = fname.lower()
            if low == MOUSELOCKED_NAME.lower():
                mouselocked = fpath; used.add(fname); continue
            if low in lower_map:
                dest_to_src[lower_map[low]] = fpath
                used.add(fname)

        # 2. keyword fallback for the rest -> fill any unfilled destinations
        for fname, fpath in all_png.items():
            if fname in used:
                continue
            if "mouselocked" in fname.lower() and mouselocked is None:
                mouselocked = fpath; continue
            role_id, _ = self.cursor_mgr._match_keyword(fname)
            if role_id is None or role_id not in ROBLOX_CURSOR_MAP:
                continue
            for dest in ROBLOX_CURSOR_MAP[role_id]:
                if dest not in dest_to_src:
                    dest_to_src[dest] = fpath

        # 3. Arrow fallback: if we still have no ArrowCursor, use first spare PNG
        if "ArrowCursor.png" not in dest_to_src:
            spare = [p for f, p in all_png.items()
                     if p not in dest_to_src.values() and p != mouselocked]
            if spare:
                dest_to_src["ArrowCursor.png"] = spare[0]

        return dest_to_src, mouselocked

    def apply_roblox_cursors(self, pack_name):
        if not IS_WINDOWS or not self.cfg.get("roblox_enabled", True):
            return
        version_root = self.find_latest_version_folder()
        if not version_root:
            self._status("Roblox not found, skipping cursor apply", "warn")
            return
        km = self.cursor_folder(version_root)
        if not km:
            self._status("Roblox cursor folder not found", "warn")
            return

        dest_to_src, mouselocked = self._get_roblox_cursor_mapping(pack_name)
        log("ROBLOX-CUR", f"mapping: "
            f"{ {d: os.path.basename(p) for d, p in dest_to_src.items()} } "
            f"mouselocked={os.path.basename(mouselocked) if mouselocked else None}")
        if not dest_to_src and not mouselocked:
            self._status("No PNGs in pack for Roblox", "text_dim")
            return

        applied, errors = 0, []
        for dest_fname, src in dest_to_src.items():
            png, err = self._prepare_png(src)
            if png is None:
                errors.append(err); continue
            rel = os.path.join("content", "textures", "Cursors", "KeyboardMouse", dest_fname)
            self._backup_file(FEAT_CURSOR, version_root, rel)
            try:
                png.save(os.path.join(version_root, rel), "PNG")
                applied += 1
            except Exception as e:
                errors.append(f"{dest_fname}: {e}")

        # MouseLockedCursor.png -> content/textures/ ROOT only
        if mouselocked:
            png, err = self._prepare_png(mouselocked)
            if png is not None:
                rel = os.path.join("content", "textures", MOUSELOCKED_NAME)
                self._backup_file(FEAT_CURSOR, version_root, rel)
                try:
                    png.save(os.path.join(version_root, rel), "PNG")
                    applied += 1
                    log("ROBLOX-CUR", "wrote MouseLockedCursor.png to textures root")
                except Exception as e:
                    errors.append(f"MouseLocked: {e}")

        if errors:
            self._status(f"Roblox cursor error: {errors[0]}", "warn")
            for e in errors:
                log("ROBLOX-CUR", f"error: {e}", level=logging.WARNING)
        else:
            self._status(f"Roblox cursors updated ({applied} files)", "accent")

    def _prepare_png(self, png_path):
        try:
            img = Image.open(png_path).convert("RGBA")
            return img.resize((32, 32), Image.NEAREST), None
        except Exception as e:
            return None, f"{os.path.basename(png_path)}: {e}"

    # ==================================================================
    # ROBLOX UI  (overlay content/textures subset)
    # ==================================================================
    def apply_ui(self, pack_name, reapply_cursors=True):
        if not IS_WINDOWS or not self.cfg.get("roblox_enabled", True):
            return
        version_root = self.find_latest_version_folder()
        if not version_root:
            self._status("Roblox not found, skipping UI apply", "warn")
            return
        pack_dir = self.ui_store.pack_dir(pack_name)
        # Pack usually contains a top-level 'content/' tree (sometimes wrapped
        # in a single named folder). Find the 'content' root inside the pack.
        content_root = self._find_content_root(pack_dir)
        if not content_root:
            self._status("UI pack has no content/ folder", "warn")
            log("UI", f"No content/ folder inside {pack_dir}", level=logging.WARNING)
            return
        applied, failed = 0, 0
        for dirpath, _, files in os.walk(content_root):
            for f in files:
                src = os.path.join(dirpath, f)
                rel_inside = os.path.relpath(src, content_root)  # e.g. textures/ui/...
                rel = os.path.join("content", rel_inside)
                if self._overlay_file(FEAT_UI, version_root, rel, src):
                    applied += 1
                else:
                    failed += 1
        log("UI", f"overlaid {applied} file(s), {failed} failed")
        self._status(f"Roblox UI applied ({applied} files)", "accent" if applied else "warn")
        # A UI pack can bundle cursor PNGs (KeyboardMouse/* and MouseLockedCursor).
        # Re-apply the active Roblox cursor set on top so cursors always win.
        if reapply_cursors:
            cur = self.cfg.get("roblox_cursor_pack")
            if cur and cur in self.rbx_cursor_store.list_packs():
                log("UI", "re-applying active Roblox cursor set so it overrides UI")
                self.apply_roblox_cursors(cur)

    @staticmethod
    def _find_content_root(pack_dir):
        """Return the path to the 'content' dir inside a pack, at any depth.
        Handles zips that extracted with extra redundant nesting."""
        # walk and return the shallowest directory literally named 'content'
        best = None
        best_depth = None
        for dirpath, dirs, _ in os.walk(pack_dir):
            for d in dirs:
                if d.lower() == "content":
                    full = os.path.join(dirpath, d)
                    depth = full[len(pack_dir):].count(os.sep)
                    if best_depth is None or depth < best_depth:
                        best, best_depth = full, depth
        return best

    # ==================================================================
    # ROBLOX SKYBOX  (.tex overlay into PlatformContent sky)
    # ==================================================================
    SKY_REL = os.path.join("PlatformContent", "pc", "textures", "sky")

    def apply_sky(self, pack_name):
        if not IS_WINDOWS or not self.cfg.get("roblox_enabled", True):
            return
        version_root = self.find_latest_version_folder()
        if not version_root:
            self._status("Roblox not found, skipping skybox apply", "warn")
            return
        pack_dir = self.sky_store.pack_dir(pack_name)
        # find the folder that actually holds the sky*.tex files
        tex_dir = self._find_tex_dir(pack_dir)
        if not tex_dir:
            self._status("Skybox pack has no .tex files", "warn")
            return
        sky_dest = os.path.join(version_root, self.SKY_REL)
        if not os.path.isdir(sky_dest):
            self._status("Roblox sky folder not found", "warn")
            return
        applied = 0
        for f in os.listdir(tex_dir):
            if not f.lower().endswith(".tex"):
                continue
            rel = os.path.join(self.SKY_REL, f)
            if self._overlay_file(FEAT_SKY, version_root, rel, os.path.join(tex_dir, f)):
                applied += 1
        log("SKY", f"overlaid {applied} skybox file(s)")
        self._status(f"Skybox applied ({applied} files)", "accent" if applied else "warn")

    @staticmethod
    def _find_tex_dir(pack_dir):
        for dirpath, _, files in os.walk(pack_dir):
            if any(f.lower().endswith(".tex") for f in files):
                return dirpath
        return None

    # ==================================================================
    # ROBLOX FONTS  (swap every family JSON to the uploaded font, all weights)
    # ==================================================================
    def apply_fonts(self, pack_name):
        if not IS_WINDOWS or not self.cfg.get("roblox_enabled", True):
            return
        version_root = self.find_latest_version_folder()
        if not version_root:
            self._status("Roblox not found, skipping font apply", "warn")
            return
        # find uploaded font file(s), searching nested folders too
        found = self.font_store.find_files(pack_name, (".otf", ".ttf"))
        if not found:
            self._status("Font pack has no .otf/.ttf", "warn")
            return
        font_file = next(iter(found.keys()))       # primary font used for all families
        font_src = found[font_file]
        log("FONT", f"Using '{font_file}' for all families")

        fonts_dir = os.path.join(version_root, "content", "fonts")
        families_dir = os.path.join(fonts_dir, "families")
        if not os.path.isdir(families_dir):
            self._status("Roblox fonts/families not found", "warn")
            return

        # 1. copy the font file into content/fonts/ (backup any same-named file first)
        rel_font = os.path.join("content", "fonts", font_file)
        self._backup_file(FEAT_FONT, version_root, rel_font)
        try:
            shutil.copy2(font_src, os.path.join(version_root, rel_font))
        except Exception as e:
            log_exc("FONT", f"copy font failed: {e}")
            self._status(f"Font copy failed: {e}", "warn")
            return
        asset_ref = f"rbxasset://fonts/{font_file}"

        # 2. rewrite every family JSON: point every face at our font
        rewritten, failed = 0, 0
        for jf in os.listdir(families_dir):
            if not jf.lower().endswith(".json"):
                continue
            rel_json = os.path.join("content", "fonts", "families", jf)
            self._backup_file(FEAT_FONT, version_root, rel_json)
            jpath = os.path.join(families_dir, jf)
            try:
                with open(jpath, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                faces = data.get("faces", [])
                for face in faces:
                    face["assetId"] = asset_ref
                with open(jpath, "w", encoding="utf-8") as fh:
                    json.dump(data, fh, indent=2)
                rewritten += 1
            except Exception as e:
                failed += 1
                log_exc("FONT", f"rewrite {jf} failed: {e}")
        log("FONT", f"rewrote {rewritten} family JSON(s), {failed} failed")
        self._status(f"Fonts applied to {rewritten} families", "accent" if rewritten else "warn")

    # ==================================================================
    # UNIVERSAL RESTORE  (all Roblox features from backup)
    # ==================================================================
    def restore_all_roblox(self):
        if not IS_WINDOWS:
            return False
        version_root = self.find_latest_version_folder()
        if not version_root:
            self._status("Roblox not found, cannot restore", "warn")
            return False
        vn = os.path.basename(version_root)
        backup_root = os.path.join(ROBLOX_BACKUP_DIR, vn)
        if not os.path.isdir(backup_root):
            self._status("No Roblox backups for this version", "warn")
            log("BACKUP", f"No backup dir: {backup_root}", level=logging.WARNING)
            return False

        total = 0
        for feature in (FEAT_CURSOR, FEAT_UI, FEAT_SKY, FEAT_FONT):
            fdir = os.path.join(backup_root, feature)
            if not os.path.isdir(fdir):
                continue
            count = 0
            for dirpath, _, files in os.walk(fdir):
                for f in files:
                    bpath = os.path.join(dirpath, f)
                    rel = os.path.relpath(bpath, fdir)
                    dest = os.path.join(version_root, rel)
                    try:
                        os.makedirs(os.path.dirname(dest), exist_ok=True)
                        shutil.copy2(bpath, dest)
                        count += 1
                    except Exception as e:
                        log_exc("BACKUP", f"restore {rel} failed: {e}")
            log("BACKUP", f"restored {count} {feature} file(s)")
            total += count

        # clear saved pack selections so UI reflects reverted state
        self.cfg["roblox_cursor_pack"] = None
        self.cfg["ui_pack"] = None
        self.cfg["sky_pack"] = None
        self.cfg["font_pack"] = None
        save_config(self.cfg)
        self._status(f"Restored all Roblox files ({total} total)", "accent")
        log("BACKUP", f"Universal restore complete: {total} files")
        return True

    # ==================================================================
    # WATCHER  (re-apply active packs when Roblox updates version)
    # ==================================================================
    def start_watcher(self):
        if self._watcher_thread and self._watcher_thread.is_alive():
            return
        self._stop_event.clear()
        self._watcher_thread = threading.Thread(target=self._watch_loop, daemon=True)
        self._watcher_thread.start()
        log("ROBLOX", "watcher started")

    def stop_watcher(self):
        self._stop_event.set()
        log("ROBLOX", "watcher stopped")

    def reapply_all(self):
        """Re-apply every active Roblox pack (used on version change / manual).

        Order matters: UI/sky/font first, then cursors LAST so the Roblox
        cursor set always overrides any cursor PNGs bundled inside a UI pack.
        """
        ui = self.cfg.get("ui_pack")
        if ui and ui in self.ui_store.list_packs():
            self.apply_ui(ui, reapply_cursors=False)
        sky = self.cfg.get("sky_pack")
        if sky and sky in self.sky_store.list_packs():
            self.apply_sky(sky)
        font = self.cfg.get("font_pack")
        if font and font in self.font_store.list_packs():
            self.apply_fonts(font)
        # cursors last -> they win over UI-bundled cursor files
        cur = self.cfg.get("roblox_cursor_pack")
        if cur and cur in self.rbx_cursor_store.list_packs():
            self.apply_roblox_cursors(cur)

    def _watch_loop(self):
        while not self._stop_event.is_set():
            if not self.cfg.get("roblox_enabled", True):
                time.sleep(5); continue
            current = self.find_latest_version_folder()
            if current != self._last_version:
                if self._last_version is not None:
                    log("ROBLOX", "new version detected, re-applying active packs")
                    self.reapply_all()
                self._last_version = current
            time.sleep(5)


# ---------------------------------------------------------------------------
# The cat
# ---------------------------------------------------------------------------
class OnekoPet:
    def __init__(self, master, cfg):
        self.cfg = cfg
        self.window = tk.Toplevel(master)
        self.window.withdraw()
        self.CHROMA_KEY = "#00ff01"
        self.window.overrideredirect(True)
        self.window.attributes("-topmost", True)
        self.window.wm_attributes("-transparentcolor", self.CHROMA_KEY)
        self.window.config(bg=self.CHROMA_KEY)
        self.sprite_sheet = self._load_sprite_sheet()
        self.size = int(cfg.get("cat_size", 32))
        self.frames = {}
        self._build_frames()
        self.label = tk.Label(self.window, image=self.frames["idle"][0],
                              bg=self.CHROMA_KEY, bd=0)
        self.label.pack()
        self.x, self.y = 500.0, 500.0
        self.speed = int(cfg.get("speed", 10))
        self.active = False
        self._animation_after = None
        self.frozen = False
        self.idle_time = self.idle_frame = self.frame_count = 0
        self.idle_animation = None
        self._hwnd = None

    def _load_sprite_sheet(self):
        bundled = os.path.join(getattr(sys, "_MEIPASS", os.path.dirname(__file__)), "assets", "oneko.gif")
        for path in (bundled, SPRITE_CACHE):
            try:
                with Image.open(path) as sprite:
                    return sprite.convert("RGBA")
            except (OSError, ValueError):
                continue
        log("CAT", "Bundled sprite unavailable; using offline placeholder", logging.WARNING)
        return self._make_placeholder_sheet()

    def _make_placeholder_sheet(self):
        sheet = Image.new("RGBA", (256, 128), (0, 0, 0, 0))
        d = ImageDraw.Draw(sheet)
        for row in range(4):
            for col in range(8):
                ox, oy = col * 32, row * 32
                d.ellipse((ox+6, oy+10, ox+26, oy+28), fill=(120,120,120,255))
                d.polygon([(ox+8,oy+12),(ox+12,oy+4),(ox+14,oy+12)], fill=(120,120,120,255))
                d.polygon([(ox+24,oy+12),(ox+20,oy+4),(ox+18,oy+12)], fill=(120,120,120,255))
                d.ellipse((ox+11,oy+16,ox+14,oy+19), fill=(0,0,0,255))
                d.ellipse((ox+18,oy+16,ox+21,oy+19), fill=(0,0,0,255))
        return sheet

    def _build_frames(self):
        s = self.size
        def get_sprite(col, row):
            box = (col*32, row*32, (col+1)*32, (row+1)*32)
            img = self.sprite_sheet.crop(box)
            if s != 32:
                img = img.resize((s, s), Image.NEAREST)
            bg = Image.new("RGBA", (s, s), self.CHROMA_KEY)
            bg.paste(img, (0, 0), img)
            return ImageTk.PhotoImage(bg)
        self.frames = {
            "idle": [get_sprite(3, 3)], "alert": [get_sprite(7, 3)],
            "tired": [get_sprite(3, 2)],
            "sleeping": [get_sprite(2, 0), get_sprite(2, 1)],
            "scratchSelf": [get_sprite(5, 0), get_sprite(6, 0), get_sprite(7, 0)],
            "N": [get_sprite(1, 2), get_sprite(1, 3)],
            "NE": [get_sprite(0, 2), get_sprite(0, 3)],
            "E": [get_sprite(3, 0), get_sprite(3, 1)],
            "SE": [get_sprite(5, 1), get_sprite(5, 2)],
            "S": [get_sprite(6, 3), get_sprite(7, 2)],
            "SW": [get_sprite(5, 3), get_sprite(6, 1)],
            "W": [get_sprite(4, 2), get_sprite(4, 3)],
            "NW": [get_sprite(1, 0), get_sprite(1, 1)],
        }

    def set_size(self, new_size):
        self.size = int(new_size); self._build_frames(); self.set_sprite("idle")

    def set_speed(self, new_speed):
        self.speed = int(new_speed)

    def toggle(self, state):
        if self._animation_after is not None:
            self.window.after_cancel(self._animation_after)
            self._animation_after = None
        self.active = bool(state)
        if self.active:
            self.window.deiconify()
            self.window.after(50, self._apply_overlay_styles)
            self.update()
        else:
            self.window.withdraw()

    def _apply_overlay_styles(self):
        try:
            self._hwnd = self.window.winfo_id()
            self._hwnd = ctypes.windll.user32.GetParent(self._hwnd) or self._hwnd
            make_click_through(self._hwnd)
            force_topmost(self._hwnd)
        except Exception:
            pass
        if not getattr(self, "_watchdog_running", False):
            self._watchdog_running = True
            self._topmost_watchdog()

    def _topmost_watchdog(self):
        if self.active:
            try:
                force_topmost(self._hwnd) if self._hwnd else \
                    self.window.attributes("-topmost", True)
            except Exception:
                pass
        self.window.after(500, self._topmost_watchdog)

    def toggle_freeze(self):
        self.frozen = not self.frozen
        if self.frozen:
            self.idle_animation = None; self.idle_frame = 0; self.set_sprite("idle")
        return self.frozen

    def update(self):
        if not self.active:
            return
        if self.frozen:
            self._animation_after = self.window.after(250, self.update); return
        force_topmost(self._hwnd) if self._hwnd else \
            self.window.attributes("-topmost", True)
        mx = self.window.winfo_pointerx(); my = self.window.winfo_pointery()
        dx, dy = self.x - mx, self.y - my
        dist = math.hypot(dx, dy)
        if dist < self.speed or dist < self.size * 1.5:
            self.handle_idle()
        else:
            self.handle_movement(dx, dy, dist)
        self.window.geometry(f"+{int(self.x - self.size//2)}+{int(self.y - self.size//2)}")
        self._animation_after = self.window.after(90, self.update)

    def handle_movement(self, dx, dy, dist):
        self.idle_animation = None; self.idle_frame = 0
        if self.idle_time > 1:
            self.set_sprite("alert"); self.idle_time = 0
        self.frame_count += 1
        dir_str = (("N" if dy/dist > 0.5 else "S" if dy/dist < -0.5 else "") +
                   ("W" if dx/dist > 0.5 else "E" if dx/dist < -0.5 else ""))
        self.set_sprite(dir_str or "idle", self.frame_count)
        self.x -= (dx / dist) * self.speed
        self.y -= (dy / dist) * self.speed

    def handle_idle(self):
        self.idle_time = min(self.idle_time + 1, 100)
        if (self.idle_time > 10 and self.idle_animation is None
                and random.randint(0, 100) == 0):
            self.idle_animation = random.choice(["sleeping", "scratchSelf"])
        if self.idle_animation == "sleeping":
            self.set_sprite("tired" if self.idle_frame < 8 else "sleeping",
                            self.idle_frame // 4)
            self.idle_frame += 1
            if self.idle_frame > 100:
                self.idle_animation = None; self.idle_frame = 0
        elif self.idle_animation == "scratchSelf":
            self.set_sprite("scratchSelf", self.idle_frame)
            self.idle_frame += 1
            if self.idle_frame > 10:
                self.idle_animation = None; self.idle_frame = 0
        else:
            self.set_sprite("idle")

    def set_sprite(self, name, frame=0):
        lst = self.frames.get(name, self.frames["idle"])
        self.label.config(image=lst[frame % len(lst)])


# ---------------------------------------------------------------------------
# Startup registry
# ---------------------------------------------------------------------------
REG_KEY_NAME = "CursorMods"

def _is_startup_enabled():
    if not IS_WINDOWS:
        return False
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                             r"Software\Microsoft\Windows\CurrentVersion\Run",
                             0, winreg.KEY_READ)
        winreg.QueryValueEx(key, REG_KEY_NAME)
        winreg.CloseKey(key)
        return True
    except Exception:
        return False


def _set_startup(enable):
    if not IS_WINDOWS:
        return
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                             r"Software\Microsoft\Windows\CurrentVersion\Run",
                             0, winreg.KEY_SET_VALUE)
        if enable:
            exe = sys.executable
            script = os.path.abspath(__file__)
            value = (f'"{exe}" "{script}"'
                     if os.path.basename(exe).lower() in ("python.exe", "pythonw.exe")
                     else f'"{exe}"')
            winreg.SetValueEx(key, REG_KEY_NAME, 0, winreg.REG_SZ, value)
            log("STARTUP", "enabled")
        else:
            try:
                winreg.DeleteValue(key, REG_KEY_NAME)
                log("STARTUP", "disabled")
            except FileNotFoundError:
                pass
        winreg.CloseKey(key)
    except Exception as e:
        log_exc("STARTUP", f"failed: {e}")


# ---------------------------------------------------------------------------
# First-run installer (frozen exe only)
# ---------------------------------------------------------------------------
def _first_run_installer():
    if not IS_WINDOWS or getattr(sys, 'frozen', False) is False:
        return
    if os.path.exists(FIRSTRUN_FLAG):
        return
    appdata = os.environ.get("APPDATA", os.path.expanduser("~"))
    target_dir = os.path.join(appdata, "CursorMods")
    os.makedirs(target_dir, exist_ok=True)
    exe_path = sys.executable
    new_exe_path = os.path.join(target_dir, os.path.basename(exe_path))
    try:
        shutil.copy2(exe_path, new_exe_path)
    except Exception:
        with open(FIRSTRUN_FLAG, "w") as f:
            f.write("skipped")
        return
    try:
        import pythoncom
        from win32com.client import Dispatch
    except ImportError:
        with open(FIRSTRUN_FLAG, "w") as f:
            f.write("no_shortcuts")
        return
    shell = Dispatch('WScript.Shell')
    def make_shortcut(link_path, target, work_dir, desc="Cursor Mods"):
        sc = shell.CreateShortCut(link_path)
        sc.Targetpath = target; sc.WorkingDirectory = work_dir
        sc.Description = desc; sc.IconLocation = target + ",0"; sc.Save()
    desktop = shell.SpecialFolders("Desktop")
    make_shortcut(os.path.join(desktop, "Cursor Mods.lnk"), new_exe_path, target_dir)
    downloads = os.path.join(os.path.expanduser("~"), "Downloads")
    if os.path.isdir(downloads):
        make_shortcut(os.path.join(downloads, "Cursor Mods.lnk"), new_exe_path, target_dir)
    programs = shell.SpecialFolders("Programs")
    startmenu = os.path.join(programs, "Cursor Mods")
    os.makedirs(startmenu, exist_ok=True)
    make_shortcut(os.path.join(startmenu, "Cursor Mods.lnk"), new_exe_path, target_dir)
    if _is_startup_enabled():
        _set_startup(True)
    with open(FIRSTRUN_FLAG, "w") as f:
        f.write("installed")


# ---------------------------------------------------------------------------
# Tray / icon helpers
# ---------------------------------------------------------------------------
def _make_tray_icon():
    # Use the Cursor Mods app icon (same as the panel header) for the tray.
    for b64 in (_ICON_TRAY_B64, _ICON_SMALL_B64):
        try:
            data = __import__('base64').b64decode(b64)
            img = Image.open(BytesIO(data)).convert('RGBA')
            if img.size[0] < 32:
                img = img.resize((64, 64), Image.NEAREST)
            return img
        except Exception:
            continue
    return Image.new('RGBA', (64, 64), (94, 92, 230, 255))


def _load_header_icon(master):
    try:
        data = __import__('base64').b64decode(_ICON_SMALL_B64)
        img = Image.open(BytesIO(data)).convert('RGBA')
        return ImageTk.PhotoImage(img, master=master)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Themeable UI widgets
# ---------------------------------------------------------------------------
# Shared journal engine keeps game-file operations independent of the UI.
from mod_engine import build_engine_type
RobloxIntegration = build_engine_type(sys.modules[__name__], RobloxIntegration)


class ThemedSlider(tk.Frame):
    def __init__(self, parent, theme, label, lo, hi, value, callback,
                 suffix="", is_float=False):
        super().__init__(parent, bg=theme["bg"])
        self.theme = theme
        self.callback = callback
        self.suffix = suffix
        self.is_float = is_float
        top = tk.Frame(self, bg=theme["bg"]); top.pack(fill="x")
        self.lbl = tk.Label(top, text=label, bg=theme["bg"], fg=theme["text_dim"],
                            font=("Segoe UI", 8, "bold"))
        self.lbl.pack(side="left")
        self.val_lbl = tk.Label(top, text=self._fmt(value), bg=theme["bg"],
                                fg=theme["text_med"], font=("Segoe UI", 8))
        self.val_lbl.pack(side="right")
        self.scale = tk.Scale(self, from_=lo, to=hi,
                              resolution=0.01 if is_float else 1,
                              orient="horizontal", showvalue=False,
                              command=self._on_change, bg=theme["bg"],
                              fg=theme["text_med"], troughcolor=theme["btn"],
                              highlightthickness=0, bd=0, sliderrelief="flat",
                              activebackground=theme["accent"], sliderlength=16, width=10)
        self.scale.set(value); self.scale.pack(fill="x")

    def _fmt(self, v):
        return f"{float(v):.2f}" if self.is_float else f"{int(float(v))}{self.suffix}"

    def _on_change(self, v):
        self.val_lbl.config(text=self._fmt(v)); self.callback(float(v))

    def set_value(self, v):
        self.scale.set(v); self.val_lbl.config(text=self._fmt(v))

    def restyle(self, theme):
        self.theme = theme
        self.config(bg=theme["bg"])
        for w in self.winfo_children():
            if isinstance(w, tk.Frame):
                w.config(bg=theme["bg"])
        self.lbl.config(bg=theme["bg"], fg=theme["text_dim"])
        self.val_lbl.config(bg=theme["bg"], fg=theme["text_med"])
        self.scale.config(bg=theme["bg"], fg=theme["text_med"],
                          troughcolor=theme["btn"], activebackground=theme["accent"])


class ThemedButton(tk.Label):
    def __init__(self, parent, theme, text, command, **kw):
        super().__init__(parent, text=text, bg=theme["btn"], fg=theme["text"],
                         font=("Segoe UI", 9), padx=8, pady=5, cursor="hand2", **kw)
        self.theme = theme
        self.command = command
        self.bind("<Button-1>", lambda e: self.command())
        self.bind("<Enter>", lambda e: self.config(bg=self.theme["btn_hover"]))
        self.bind("<Leave>", lambda e: self.config(bg=self.theme["btn"]))

    def restyle(self, theme):
        self.theme = theme
        self.config(bg=theme["btn"], fg=theme["text"])


class Section(tk.Frame):
    """A titled, collapsible section container."""
    def __init__(self, parent, theme, title):
        super().__init__(parent, bg=theme["bg"])
        self.theme = theme
        self.title = title
        self.expanded = True
        self.header = tk.Frame(self, bg=theme["section"], cursor="hand2")
        self.header.pack(fill="x", pady=(0, 1))
        self.arrow = tk.Label(self.header, text="\u25be", bg=theme["section"],
                              fg=theme["text_med"], font=("Segoe UI", 8), padx=6)
        self.arrow.pack(side="left")
        self.title_lbl = tk.Label(self.header, text=title, bg=theme["section"],
                                  fg=theme["text"], font=("Segoe UI", 9, "bold"),
                                  pady=5)
        self.title_lbl.pack(side="left")
        self.body = tk.Frame(self, bg=theme["bg"])
        self.body.pack(fill="x", padx=2, pady=(2, 6))
        for w in (self.header, self.arrow, self.title_lbl):
            w.bind("<Button-1>", lambda e: self.toggle())

    def toggle(self):
        self.expanded = not self.expanded
        if self.expanded:
            self.body.pack(fill="x", padx=2, pady=(2, 6))
            self.arrow.config(text="\u25be")
        else:
            self.body.pack_forget()
            self.arrow.config(text="\u25b8")
        # ask the panel to resize
        self.event_generate("<<SectionToggled>>")

    def restyle(self, theme):
        self.theme = theme
        self.config(bg=theme["bg"])
        self.header.config(bg=theme["section"])
        self.arrow.config(bg=theme["section"], fg=theme["text_med"])
        self.title_lbl.config(bg=theme["section"], fg=theme["text"])
        self.body.config(bg=theme["bg"])


# ---------------------------------------------------------------------------
# Control Panel
# ---------------------------------------------------------------------------
class ControlPanel(_TkRoot):
    PANEL_W = 580

    def __init__(self):
        super().__init__()
        self.cfg = load_config()
        self.theme = THEMES.get(self.cfg.get("theme", DEFAULT_THEME), THEMES[DEFAULT_THEME])
        self.cursor_mgr = CursorManager()

        if self.cfg.get("cursor_size") is None:
            self.cfg["cursor_size"] = _get_default_cursor_size()

        self.overrideredirect(True)
        self.attributes("-alpha", self.cfg["opacity"])
        self.attributes("-topmost", True)
        self.configure(bg=self.theme["bg"])

        self.is_hidden = False
        self.cat_enabled = tk.BooleanVar(value=self.cfg["enabled"])
        self.startup_var = tk.BooleanVar(value=_is_startup_enabled())
        self.cfg["roblox_enabled"] = True   # always on; no user toggle anymore
        self.tray_icon = None
        self._cur_size_after = None
        self._themed_widgets = []   # widgets with restyle()

        self.roblox = RobloxIntegration(
            self.cursor_mgr, self.cfg,
            status_callback=lambda msg, key=None: self._set_status(msg, key))

        self._build_ui()

        if self.cfg.get("roblox_enabled", True) and IS_WINDOWS:
            self.roblox.start_watcher()

        self._resize()

        self.pet = OnekoPet(self, self.cfg)
        if self.cfg["enabled"]:
            self.after(300, lambda: self.pet.toggle(True))

        # re-apply saved packs silently on launch
        self.after(500, self._reapply_saved_packs)

        self._hotkey_regs = {}
        self._register_hotkeys()
        if HAS_TRAY:
            self._setup_tray()
        self.protocol("WM_DELETE_WINDOW", self.quit_app)
        self.bind_all("<<SectionToggled>>", lambda e: self._resize())
        log("UI-APP", "panel ready")

    # ---- theme color resolver for status ----
    def _color(self, key):
        if key in ("accent", "warn", "text", "text_med", "text_dim"):
            return self.theme[key]
        return key or self.theme["text_dim"]

    def _reapply_saved_packs(self):
        cp = self.cfg.get("cursor_pack")
        if cp and cp in self.cursor_mgr.list_packs():
            self._apply_windows_pack(cp, silent=True)
        # Roblox packs (only re-apply if roblox enabled)
        if self.cfg.get("roblox_enabled", True) and IS_WINDOWS:
            self.roblox.reapply_all()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------
    def _build_ui(self):
        t = self.theme
        # Header (drag handle)
        self.header = tk.Frame(self, bg=t["header"], height=28)
        self.header.pack(fill="x")
        self._header_icon = _load_header_icon(self)
        if self._header_icon:
            il = tk.Label(self.header, image=self._header_icon, bg=t["header"], bd=0)
            il.pack(side="left", padx=(6, 2), pady=3)
            il.bind("<Button-1>", self._get_pos); il.bind("<B1-Motion>", self._move_window)
        self.title_lbl = tk.Label(self.header, text="Cursor Mods", bg=t["header"],
                                  fg=t["text"], font=("Segoe UI", 10, "bold"))
        self.title_lbl.pack(side="left")
        for w in (self.header, self.title_lbl):
            w.bind("<Button-1>", self._get_pos); w.bind("<B1-Motion>", self._move_window)
        self.close_lbl = tk.Label(self.header, text="\u2715", bg=t["header"], fg=t["text"],
                                  font=("Segoe UI", 10), padx=8, cursor="hand2")
        self.close_lbl.pack(side="right")
        self.close_lbl.bind("<Button-1>", lambda e: self.quit_app())
        self.close_lbl.bind("<Enter>", lambda e: self.close_lbl.config(bg="#e81123"))
        self.close_lbl.bind("<Leave>", lambda e: self.close_lbl.config(bg=self.theme["header"]))
        self.mini_lbl = tk.Label(self.header, text="\u2014", bg=t["header"], fg=t["text"],
                                 font=("Segoe UI", 10), padx=8, cursor="hand2")
        self.mini_lbl.pack(side="right")
        self.mini_lbl.bind("<Button-1>", lambda e: self.hide_panel())
        self.mini_lbl.bind("<Enter>", lambda e: self.mini_lbl.config(bg=self.theme["btn_hover"]))
        self.mini_lbl.bind("<Leave>", lambda e: self.mini_lbl.config(bg=self.theme["header"]))

        # swatches now live in Settings; keep the dict for theme marking
        self._swatches = {}

        # Body (no scrollbar; window grows to fit everything)
        self.body = tk.Frame(self, bg=t["bg"])
        self.body.pack(side="top", fill="both", expand=True)

        # Two equal-width columns via grid + uniform
        cols = tk.Frame(self.body, bg=t["bg"])
        cols.pack(fill="both", expand=True)
        self._track(cols, lambda th, w=cols: w.config(bg=th["bg"]))
        cols.grid_columnconfigure(0, weight=1, uniform="c")
        cols.grid_columnconfigure(1, weight=1, uniform="c")
        self.col_left = tk.Frame(cols, bg=t["bg"])
        self.col_left.grid(row=0, column=0, sticky="nsew", padx=(4, 3))
        self.col_right = tk.Frame(cols, bg=t["bg"])
        self.col_right.grid(row=0, column=1, sticky="nsew", padx=(3, 4))
        self._track(self.col_left, lambda th, w=self.col_left: w.config(bg=th["bg"]))
        self._track(self.col_right, lambda th, w=self.col_right: w.config(bg=th["bg"]))

        self._build_sections()

        # status line (spans full width at the bottom)
        self.status = tk.Label(self.body, text="", bg=t["bg"], fg=t["text_dim"],
                               font=("Segoe UI", 8), anchor="w", wraplength=540,
                               justify="left")
        self.status.pack(fill="x", padx=12, pady=(2, 8))
        if not HAS_KEYBOARD:
            self.status.config(text="\u26A0 'keyboard' not installed \u2014 hotkeys off",
                               fg=t["warn"])

    def _on_mousewheel(self, event):
        pass

    # ------------------------------------------------------------------
    # Sections
    # ------------------------------------------------------------------
    def _section(self, parent, title):
        sec = Section(parent, self.theme, title)
        sec.pack(fill="x", padx=4, pady=3)
        self._track(sec, sec.restyle)
        return sec

    def _build_sections(self):
        t = self.theme
        L, R = self.col_left, self.col_right

        # ================= LEFT COLUMN =================
        # ---- PC Cursor Set ----
        sec = self._section(L, "PC Cursor Set")
        self._pc_cursor_list = self._pack_section_ui(
            sec.body, drop_kind="folder",
            on_drop=self._pc_import, on_browse=self._pc_browse,
            list_getter=self.cursor_mgr.list_packs,
            active_getter=lambda: self.cfg.get("cursor_pack"),
            on_apply=self._apply_windows_pack,
            on_delete=self._pc_delete)
        self._build_cursor_size(sec.body)
        b = ThemedButton(sec.body, t, "Restore Windows cursors", self._restore_windows_cursors)
        b.pack(fill="x", pady=(6, 0)); self._track(b, b.restyle)

        # ---- Kitty (cat) + freeze hotkey ----
        sec = self._section(L, "Kitty")
        self._build_cat_controls(sec.body)

        # ---- Settings ----
        sec = self._section(L, "Settings")
        self._build_settings(sec.body)

        # ================= RIGHT COLUMN =================
        # ---- Roblox Cursor Set (own store) ----
        sec = self._section(R, "Roblox Cursor Set")
        self._rbx_cursor_list = self._pack_section_ui(
            sec.body, drop_kind="folder",
            on_drop=lambda p: self._rbx_import(p, "cursor"),
            on_browse=lambda: self._rbx_browse("cursor"),
            list_getter=self.roblox.rbx_cursor_store.list_packs,
            active_getter=lambda: self.cfg.get("roblox_cursor_pack"),
            on_apply=lambda n: self._apply_rbx(n, "cursor"),
            on_delete=lambda n: self._rbx_delete(n, "cursor"))

        # ---- UI ----
        sec = self._section(R, "UI")
        self._ui_list = self._pack_section_ui(
            sec.body, drop_kind="folder",
            on_drop=lambda p: self._rbx_import(p, "ui"),
            on_browse=lambda: self._rbx_browse("ui"),
            list_getter=self.roblox.ui_store.list_packs,
            active_getter=lambda: self.cfg.get("ui_pack"),
            on_apply=lambda n: self._apply_rbx(n, "ui"),
            on_delete=lambda n: self._rbx_delete(n, "ui"))

        # ---- Fonts ----
        sec = self._section(R, "Fonts")
        self._font_list = self._pack_section_ui(
            sec.body, drop_kind="file",
            on_drop=lambda p: self._font_drop(p),
            on_browse=self._font_browse, browse_label="Browse for font file\u2026",
            list_getter=self.roblox.font_store.list_packs,
            active_getter=lambda: self.cfg.get("font_pack"),
            on_apply=lambda n: self._apply_rbx(n, "font"),
            on_delete=lambda n: self._rbx_delete(n, "font"))

        # ---- Skyboxes ----
        sec = self._section(R, "Skyboxes")
        self._sky_list = self._pack_section_ui(
            sec.body, drop_kind="folder",
            on_drop=lambda p: self._rbx_import(p, "sky"),
            on_browse=lambda: self._rbx_browse("sky"),
            list_getter=self.roblox.sky_store.list_packs,
            active_getter=lambda: self.cfg.get("sky_pack"),
            on_apply=lambda n: self._apply_rbx(n, "sky"),
            on_delete=lambda n: self._rbx_delete(n, "sky"))

    def _track(self, widget, restyle_fn):
        self._themed_widgets.append((widget, restyle_fn))

    def _pack_section_ui(self, parent, drop_kind, on_drop, on_browse,
                         list_getter, active_getter, on_apply, on_delete,
                         browse_label="Browse for folder\u2026"):
        """Build a drop-zone + browse + pack list. Returns a refresh closure."""
        t = self.theme
        if HAS_DND:
            dz_text = ("\u2295  Drop font file here" if drop_kind == "file"
                       else "\u2295  Drop folder here")
            dz = tk.Label(parent, text=dz_text, bg=t["btn"], fg=t["text_med"],
                          font=("Segoe UI", 8), pady=7, cursor="hand2")
            dz.pack(fill="x", pady=(0, 2))
            try:
                dz.drop_target_register(DND_FILES)
                dz.dnd_bind("<<Drop>>", lambda e: self._handle_drop(e, on_drop, drop_kind))
            except Exception as e:
                log_exc("UI-APP", f"DND register failed: {e}")
            dz.bind("<Enter>", lambda e, w=dz: w.config(bg=self.theme["btn_hover"]))
            dz.bind("<Leave>", lambda e, w=dz: w.config(bg=self.theme["btn"]))
            self._track(dz, lambda th, w=dz: w.config(bg=th["btn"], fg=th["text_med"]))

        bb = ThemedButton(parent, t, browse_label, on_browse)
        bb.pack(fill="x", pady=(0, 4)); self._track(bb, bb.restyle)

        list_frame = tk.Frame(parent, bg=t["bg"])
        list_frame.pack(fill="x")
        self._track(list_frame, lambda th, w=list_frame: w.config(bg=th["bg"]))

        def refresh():
            for w in list_frame.winfo_children():
                w.destroy()
            packs = list_getter()
            active = active_getter()
            th = self.theme
            if not packs:
                lbl = tk.Label(list_frame, text="No packs loaded yet", bg=th["bg"],
                               fg=th["text_dim"], font=("Segoe UI", 8), anchor="w")
                lbl.pack(fill="x", padx=2, pady=2)
                return
            for name in packs:
                is_active = (name == active)
                row_bg = th["btn"] if is_active else th["bg"]
                row = tk.Frame(list_frame, bg=row_bg); row.pack(fill="x", pady=1)
                disp = (name[:24] + "\u2026") if len(name) > 25 else name
                nl = tk.Label(row, text=("\u25b6 " if is_active else "   ") + disp,
                              bg=row_bg, fg=th["text"] if is_active else th["text_med"],
                              font=("Segoe UI", 8), anchor="w", cursor="hand2",
                              padx=4, pady=3)
                nl.pack(side="left", fill="x", expand=True)
                nl.bind("<Button-1>", lambda e, n=name: on_apply(n))
                if not is_active:
                    nl.bind("<Enter>", lambda e, w=nl: w.config(fg=self.theme["text"]))
                    nl.bind("<Leave>", lambda e, w=nl: w.config(fg=self.theme["text_med"]))
                db = tk.Label(row, text="\u2715", bg=row_bg, fg=th["text_dim"],
                              font=("Segoe UI", 8), padx=6, pady=3, cursor="hand2")
                db.pack(side="right")
                db.bind("<Button-1>", lambda e, n=name: on_delete(n))
                db.bind("<Enter>", lambda e, w=db: w.config(fg="#e81123"))
                db.bind("<Leave>", lambda e, w=db: w.config(fg=self.theme["text_dim"]))
            self._resize()

        refresh()
        return refresh

    def _handle_drop(self, event, on_drop, drop_kind):
        raw = event.data.strip()
        if raw.startswith("{"):
            raw = raw[1:raw.index("}")]
        else:
            raw = raw.split()[0]
        raw = raw.strip('"')
        log("UI-APP", f"drop ({drop_kind}): {raw}")
        if drop_kind == "folder":
            if raw.lower().endswith(".zip"):
                self._set_status("\u26A0 Extract the zip first, then drop the folder", "warn")
                return
            if not os.path.isdir(raw):
                self._set_status("\u26A0 Please drop a folder", "warn")
                return
        else:  # file
            if not os.path.isfile(raw) or not raw.lower().endswith((".otf", ".ttf")):
                self._set_status("\u26A0 Please drop a .otf/.ttf font file", "warn")
                return
        on_drop(raw)

    def _build_cursor_size(self, parent):
        t = self.theme
        hdr = tk.Frame(parent, bg=t["bg"]); hdr.pack(fill="x", pady=(8, 0))
        self._track(hdr, lambda th, w=hdr: w.config(bg=th["bg"]))
        l1 = tk.Label(hdr, text="CURSOR SIZE", bg=t["bg"], fg=t["text_dim"],
                      font=("Segoe UI", 8, "bold")); l1.pack(side="left")
        self._track(l1, lambda th, w=l1: w.config(bg=th["bg"], fg=th["text_dim"]))
        self._cur_size_val = tk.Label(hdr, text=f"{self.cfg['cursor_size']}px",
                                      bg=t["bg"], fg=t["text_med"], font=("Segoe UI", 8))
        self._cur_size_val.pack(side="right")
        self._track(self._cur_size_val, lambda th, w=self._cur_size_val: w.config(bg=th["bg"], fg=th["text_med"]))
        rst = tk.Label(hdr, text="\u21BA", bg=t["bg"], fg=t["text_dim"],
                       font=("Segoe UI", 10), cursor="hand2", padx=4)
        rst.pack(side="right")
        rst.bind("<Button-1>", lambda e: self._reset_cursor_size())
        rst.bind("<Enter>", lambda e, w=rst: w.config(fg=self.theme["accent"]))
        rst.bind("<Leave>", lambda e, w=rst: w.config(fg=self.theme["text_dim"]))
        self._track(rst, lambda th, w=rst: w.config(bg=th["bg"], fg=th["text_dim"]))
        self.cursor_size_scale = tk.Scale(
            parent, from_=16, to=128, resolution=1, orient="horizontal",
            showvalue=False, command=self._on_cursor_size, bg=t["bg"],
            fg=t["text_med"], troughcolor=t["btn"], highlightthickness=0, bd=0,
            sliderrelief="flat", activebackground=t["accent"], sliderlength=16, width=10)
        self.cursor_size_scale.set(self.cfg["cursor_size"])
        self.cursor_size_scale.pack(fill="x")
        self._track(self.cursor_size_scale, lambda th, w=self.cursor_size_scale:
                    w.config(bg=th["bg"], fg=th["text_med"], troughcolor=th["btn"],
                             activebackground=th["accent"]))

    def _build_cat_controls(self, parent):
        t = self.theme
        cb = tk.Checkbutton(parent, text="Enable cat", variable=self.cat_enabled,
                            command=self._on_toggle_cat, bg=t["bg"], fg=t["text"],
                            selectcolor=t["btn"], activebackground=t["bg"],
                            activeforeground=t["text"], font=("Segoe UI", 9),
                            highlightthickness=0, bd=0, anchor="w")
        cb.pack(fill="x", pady=(0, 4)); self._track(cb, lambda th, w=cb: self._restyle_check(w, th))
        s1 = ThemedSlider(parent, t, "CAT SIZE", 16, 96, self.cfg["cat_size"],
                          self._on_size, suffix="px"); s1.pack(fill="x", pady=3)
        self._track(s1, s1.restyle)
        s2 = ThemedSlider(parent, t, "SPEED", 2, 30, self.cfg["speed"], self._on_speed)
        s2.pack(fill="x", pady=3); self._track(s2, s2.restyle)
        self.freeze_btn = ThemedButton(parent, t, f"Freeze cat:  {self.cfg['freeze_hotkey']}",
                                       lambda: self._rebind("freeze_hotkey", self.freeze_btn, "Freeze cat"))
        self.freeze_btn.pack(fill="x", pady=(4, 0)); self._track(self.freeze_btn, self.freeze_btn.restyle)

    def _build_settings(self, parent):
        t = self.theme
        # ---- Theme swatches ----
        theme_lbl = tk.Label(parent, text="APP THEME", bg=t["bg"], fg=t["text_dim"],
                             font=("Segoe UI", 8, "bold"), anchor="w")
        theme_lbl.pack(fill="x", pady=(0, 2))
        self._track(theme_lbl, lambda th, w=theme_lbl: w.config(bg=th["bg"], fg=th["text_dim"]))
        self.swatch_bar = tk.Frame(parent, bg=t["bg"])
        self.swatch_bar.pack(fill="x", pady=(0, 6))
        self._track(self.swatch_bar, self._restyle_swatch_bar)
        swatch_colors = {
            "White": "#ffffff", "Black": "#111114", "Navy Blue": "#1a3049",
            "Dark Purple": "#3a2852", "Light Pink": "#f2bcd3", "Dark Green": "#1c3a2b",
        }
        # two rows of three
        names = list(swatch_colors.items())
        for r in range(2):
            row = tk.Frame(self.swatch_bar, bg=t["bg"]); row.pack(fill="x", pady=1)
            self._track(row, lambda th, w=row: w.config(bg=th["bg"]))
            for name, col in names[r*3:(r+1)*3]:
                sw = tk.Label(row, bg=col, height=1, cursor="hand2", bd=1, relief="solid")
                sw.pack(side="left", fill="x", expand=True, padx=2)
                sw.bind("<Button-1>", lambda e, n=name: self._set_theme(n))
                self._swatches[name] = sw
        self._mark_active_swatch()

        # ---- Universal Roblox restore ----
        rb = ThemedButton(parent, t, "\u21ba  Restore ALL Roblox files",
                          self._restore_all_roblox)
        rb.pack(fill="x", pady=(0, 2)); self._track(rb, rb.restyle)
        note = tk.Label(parent, text="Reverts Roblox cursors, UI, fonts & skyboxes to originals.",
                        bg=t["bg"], fg=t["text_dim"], font=("Segoe UI", 7),
                        anchor="w", wraplength=250, justify="left")
        note.pack(fill="x", pady=(0, 6))
        self._track(note, lambda th, w=note: w.config(bg=th["bg"], fg=th["text_dim"]))
        sep = tk.Frame(parent, bg=t["section"], height=1); sep.pack(fill="x", pady=(0, 6))
        self._track(sep, lambda th, w=sep: w.config(bg=th["section"]))

        c1 = tk.Checkbutton(parent, text="Run on startup", variable=self.startup_var,
                            command=self._toggle_startup, bg=t["bg"], fg=t["text"],
                            selectcolor=t["btn"], activebackground=t["bg"],
                            activeforeground=t["text"], font=("Segoe UI", 9),
                            highlightthickness=0, bd=0, anchor="w")
        c1.pack(fill="x", pady=(0, 4)); self._track(c1, lambda th, w=c1: self._restyle_check(w, th))
        s3 = ThemedSlider(parent, t, "PANEL OPACITY", 0.2, 1.0, self.cfg["opacity"],
                          self._on_alpha, is_float=True); s3.pack(fill="x", pady=3)
        self._track(s3, s3.restyle)
        # Show/Hide hotkey (Freeze cat lives under Kitty)
        self.toggle_btn = ThemedButton(parent, t, f"Show/Hide:  {self.cfg['toggle_hotkey']}",
                                       lambda: self._rebind("toggle_hotkey", self.toggle_btn, "Show/Hide"))
        self.toggle_btn.pack(fill="x", pady=2); self._track(self.toggle_btn, self.toggle_btn.restyle)

    def _restyle_check(self, w, th):
        w.config(bg=th["bg"], fg=th["text"], selectcolor=th["btn"],
                 activebackground=th["bg"], activeforeground=th["text"])

    # ------------------------------------------------------------------
    # Theme handling
    # ------------------------------------------------------------------
    def _mark_active_swatch(self):
        active = self.cfg.get("theme", DEFAULT_THEME)
        for name, sw in self._swatches.items():
            sw.config(relief="solid", bd=3 if name == active else 1,
                      highlightbackground=self.theme["accent"])

    def _restyle_swatch_bar(self, th):
        self.swatch_bar.config(bg=th["bg"])
        for w in self.swatch_bar.winfo_children():
            if isinstance(w, tk.Label) and w not in self._swatches.values():
                w.config(bg=th["bg"], fg=th["text_dim"])

    def _set_theme(self, name):
        if name not in THEMES:
            return
        self.cfg["theme"] = name
        self.theme = THEMES[name]
        save_config(self.cfg)
        log("UI-APP", f"theme -> {name}")
        t = self.theme
        self.configure(bg=t["bg"])
        self.body.config(bg=t["bg"])
        # header
        self.header.config(bg=t["header"])
        self.title_lbl.config(bg=t["header"], fg=t["text"])
        self.close_lbl.config(bg=t["header"], fg=t["text"])
        self.mini_lbl.config(bg=t["header"], fg=t["text"])
        self.status.config(bg=t["bg"], fg=t["text_dim"])
        # all tracked widgets
        for widget, fn in self._themed_widgets:
            try:
                fn(t)
            except Exception as e:
                log_exc("UI-APP", f"restyle failed: {e}")
        self._mark_active_swatch()
        self._refresh_all_lists()

    def _refresh_all_lists(self):
        for r in (self._pc_cursor_list, self._rbx_cursor_list, self._ui_list,
                  self._font_list, self._sky_list):
            try:
                r()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------
    def _set_status(self, msg, key=None):
        if hasattr(self, "status"):
            self.status.config(text=msg, fg=self._color(key))
        log("STATUS", msg, level=logging.DEBUG)

    # ------------------------------------------------------------------
    # PC (Windows) cursor handlers
    # ------------------------------------------------------------------
    def _pc_import(self, folder):
        try:
            name = self.cursor_mgr.import_pack(folder)
            self._apply_windows_pack(name)
        except Exception as e:
            self._set_status(f"\u26A0 {str(e)[:40]}", "warn")
            log_exc("CURSOR", f"import failed: {e}")

    def _pc_browse(self):
        folder = filedialog.askdirectory(title="Select Windows cursor pack folder")
        if folder:
            self._pc_import(folder)

    def _apply_windows_pack(self, name, silent=False):
        self.cursor_mgr.restore_defaults()
        count = self.cursor_mgr.apply_pack(name, cursor_size=self.cfg.get("cursor_size", 32))
        self.cfg["cursor_pack"] = name
        save_config(self.cfg)
        self._pc_cursor_list()
        if not silent:
            self._set_status(f"\u2713 {name}  ({count} cursors applied)", "accent")

    def _pc_delete(self, name):
        self.cursor_mgr.delete_pack(name)
        if self.cfg.get("cursor_pack") == name:
            self.cursor_mgr.restore_defaults()
            self.cfg["cursor_pack"] = None
        save_config(self.cfg)
        self._pc_cursor_list()
        self._set_status(f"Deleted: {name}", "text_dim")

    def _restore_windows_cursors(self):
        self.cursor_mgr.restore_defaults()
        self.cfg["cursor_pack"] = None
        save_config(self.cfg)
        self._pc_cursor_list()
        self._set_status("Windows cursors restored", "text_dim")

    def _on_cursor_size(self, v):
        val = int(float(v))
        self.cfg["cursor_size"] = val
        self._cur_size_val.config(text=f"{val}px")
        if self._cur_size_after:
            self.after_cancel(self._cur_size_after)
        self._cur_size_after = self.after(200, self._reapply_cursor_size)

    def _reset_cursor_size(self):
        default = _get_default_cursor_size()
        self.cfg["cursor_size"] = default
        self.cursor_size_scale.set(default)
        self._cur_size_val.config(text=f"{default}px")
        save_config(self.cfg)
        self._reapply_cursor_size()

    def _reapply_cursor_size(self):
        save_config(self.cfg)
        pack = self.cfg.get("cursor_pack")
        if pack and pack in self.cursor_mgr.list_packs():
            self.cursor_mgr.restore_defaults()
            self.cursor_mgr.apply_pack(pack, cursor_size=self.cfg["cursor_size"])

    # ------------------------------------------------------------------
    # Roblox handlers  (cursor / ui / sky share import+apply+delete shape)
    # ------------------------------------------------------------------
    def _store_for(self, kind):
        return {"cursor": self.roblox.rbx_cursor_store, "ui": self.roblox.ui_store,
                "sky": self.roblox.sky_store, "font": self.roblox.font_store}[kind]

    def _cfg_key_for(self, kind):
        return {"cursor": "roblox_cursor_pack", "ui": "ui_pack",
                "sky": "sky_pack", "font": "font_pack"}[kind]

    def _list_refresh_for(self, kind):
        return {"cursor": self._rbx_cursor_list, "ui": self._ui_list,
                "sky": self._sky_list, "font": self._font_list}[kind]

    def _rbx_import(self, folder, kind):
        try:
            store = self._store_for(kind)
            name = store.import_pack(folder)
            self._apply_rbx(name, kind)
        except Exception as e:
            self._set_status(f"\u26A0 {str(e)[:40]}", "warn")
            log_exc(kind.upper(), f"import failed: {e}")

    def _rbx_browse(self, kind):
        folder = filedialog.askdirectory(title=f"Select {kind} pack folder")
        if folder:
            self._rbx_import(folder, kind)

    def _font_drop(self, path):
        name = self.roblox.font_store.import_files([path])
        if name:
            self._apply_rbx(name, "font")

    def _font_browse(self):
        f = filedialog.askopenfilename(title="Select font file",
                                       filetypes=[("Fonts", "*.otf *.ttf")])
        if f:
            self._font_drop(f)

    def _apply_rbx(self, name, kind):
        self.cfg[self._cfg_key_for(kind)] = name
        save_config(self.cfg)
        if kind == "cursor":
            self.roblox.apply_roblox_cursors(name)
        elif kind == "ui":
            self.roblox.apply_ui(name)
        elif kind == "sky":
            self.roblox.apply_sky(name)
        elif kind == "font":
            self.roblox.apply_fonts(name)
        self._list_refresh_for(kind)()

    def _rbx_delete(self, name, kind):
        self._store_for(kind).delete_pack(name)
        if self.cfg.get(self._cfg_key_for(kind)) == name:
            self.cfg[self._cfg_key_for(kind)] = None
            save_config(self.cfg)
        self._list_refresh_for(kind)()
        self._set_status(f"Deleted: {name}", "text_dim")

    def _restore_all_roblox(self):
        if not IS_WINDOWS:
            return
        ok = self.roblox.restore_all_roblox()
        if ok:
            self._refresh_all_lists()

    # ------------------------------------------------------------------
    # Cat handlers
    # ------------------------------------------------------------------
    def _on_toggle_cat(self):
        state = self.cat_enabled.get()
        self.pet.toggle(state)
        self.cfg["enabled"] = state
        save_config(self.cfg)

    def _on_size(self, v):
        self.pet.set_size(v); self.cfg["cat_size"] = int(v); save_config(self.cfg)

    def _on_speed(self, v):
        self.pet.set_speed(v); self.cfg["speed"] = int(v); save_config(self.cfg)

    def _on_alpha(self, v):
        self.attributes("-alpha", v)
        self.cfg["opacity"] = round(float(v), 2); save_config(self.cfg)

    def _toggle_startup(self):
        _set_startup(self.startup_var.get())

    # ------------------------------------------------------------------
    # Window management
    # ------------------------------------------------------------------
    def _get_pos(self, e):
        self.x_click, self.y_click = e.x, e.y

    def _move_window(self, e):
        nx, ny = e.x_root - self.x_click, e.y_root - self.y_click
        self.geometry(f"+{nx}+{ny}")
        self.cfg["panel_x"], self.cfg["panel_y"] = nx, ny
        save_config(self.cfg)

    def _resize(self):
        self.update_idletasks()
        w = self.PANEL_W
        h = self.header.winfo_reqheight() + self.body.winfo_reqheight() + 4
        x, y = self.cfg.get("panel_x"), self.cfg.get("panel_y")
        self.geometry(f"{w}x{h}+{x}+{y}" if x is not None else f"{w}x{h}")

    def hide_panel(self):
        self.withdraw(); self.is_hidden = True

    def show_panel(self):
        self.deiconify(); self.update_idletasks()
        self.attributes("-topmost", True); self.lift(); self.focus_force()
        self.is_hidden = False

    def toggle_panel(self):
        self.show_panel() if self.is_hidden else self.hide_panel()

    # ------------------------------------------------------------------
    # Hotkeys
    # ------------------------------------------------------------------
    def _register_hotkeys(self):
        if not HAS_KEYBOARD:
            return
        try:
            self._hotkey_regs["toggle_hotkey"] = _add_hotkey(
                self.cfg["toggle_hotkey"], self._safe(self.toggle_panel))
            self._hotkey_regs["freeze_hotkey"] = _add_hotkey(
                self.cfg["freeze_hotkey"], self._safe(self._do_freeze))
            log("HOTKEY", f"registered toggle={self.cfg['toggle_hotkey']} "
                          f"freeze={self.cfg['freeze_hotkey']}")
        except Exception as e:
            self._set_status(f"\u26A0 hotkey error: {e}", "warn")
            log_exc("HOTKEY", f"register failed: {e}")

    def _safe(self, fn):
        return lambda: self.after(0, fn)

    def _do_freeze(self):
        frozen = self.pet.toggle_freeze()
        self._set_status("Cat frozen in place" if frozen else "Cat unfrozen",
                         "accent" if frozen else "text_dim")

    def _capture_hotkey(self):
        modifiers = []
        mod_names = {"ctrl", "left ctrl", "right ctrl", "shift", "left shift",
                     "right shift", "alt", "left alt", "right alt", "alt gr",
                     "windows", "left windows", "right windows", "cmd"}
        def normalize_mod(name):
            if "ctrl" in name: return "ctrl"
            if "shift" in name: return "shift"
            if "alt" in name: return "alt"
            if "windows" in name or name == "cmd": return "windows"
            return name
        while True:
            event = keyboard.read_event(suppress=False)
            if event.event_type != keyboard.KEY_DOWN:
                continue
            name = event.name
            if name is None:
                continue
            if name in mod_names:
                mod = normalize_mod(name)
                if mod not in modifiers:
                    modifiers.append(mod)
                continue
            key = (name if name.startswith("num ") else f"num {name}") \
                if getattr(event, "is_keypad", False) else name
            return "+".join(modifiers + [key])

    def _rebind(self, key, btn, label):
        if not HAS_KEYBOARD:
            return
        btn.config(text=f"{label}:  press keys\u2026")
        self.update()
        def capture():
            try:
                new = self._capture_hotkey()
                _remove_hotkey(self._hotkey_regs.get(key))
                self.cfg[key] = new
                save_config(self.cfg)
                fn = self.toggle_panel if key == "toggle_hotkey" else self._do_freeze
                self._hotkey_regs[key] = _add_hotkey(new, self._safe(fn))
                btn.config(text=f"{label}:  {new}")
                log("HOTKEY", f"rebound {key} -> {new}")
            except Exception as e:
                btn.config(text=f"{label}:  error")
                self._set_status(str(e), "warn")
                log_exc("HOTKEY", f"rebind failed: {e}")
        threading.Thread(target=capture, daemon=True).start()

    # ------------------------------------------------------------------
    # Tray
    # ------------------------------------------------------------------
    def _setup_tray(self):
        icon_img = _make_tray_icon()
        menu = pystray.Menu(
            TrayItem("Show Panel", lambda i, it: self.after(0, self.show_panel), default=True),
            pystray.Menu.SEPARATOR,
            TrayItem("Run on Startup",
                     lambda i, it: self.after(0, self._toggle_startup_from_tray),
                     checked=lambda it: _is_startup_enabled()),
            pystray.Menu.SEPARATOR,
            TrayItem("Quit", lambda i, it: self.after(0, self.quit_app)),
        )
        self.tray_icon = pystray.Icon("cursormods", icon_img, "Cursor Mods", menu)
        threading.Thread(target=self.tray_icon.run, daemon=True).start()

    def _toggle_startup_from_tray(self):
        new_state = not _is_startup_enabled()
        _set_startup(new_state)
        self.startup_var.set(new_state)

    # ------------------------------------------------------------------
    # Quit
    # ------------------------------------------------------------------
    def quit_app(self):
        log("UI-APP", "quitting")
        self.cursor_mgr.restore_defaults()
        save_config(self.cfg)
        try:
            self.roblox.stop_watcher()
        except Exception:
            pass
        try:
            if HAS_KEYBOARD:
                for token in self._hotkey_regs.values():
                    _remove_hotkey(token)
                keyboard.unhook_all_hotkeys()
        except Exception:
            pass
        try:
            if self.tray_icon:
                self.tray_icon.stop()
        except Exception:
            pass
        self.destroy()
        os._exit(0)


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    if not IS_WINDOWS:
        log("BOOT", "Non-Windows: cat runs; Windows/Roblox features are no-ops",
            level=logging.WARNING)
    try:
        from glass_app import run
        safe_mode = UI_TEST_MODE
        if not safe_mode:
            _first_run_installer()
        # Keep user data separate when checking the packaged interface.
        sys.exit(run(sys.modules[__name__], safe_mode=safe_mode))
    except Exception as e:
        log_exc("BOOT", f"fatal: {e}")
        raise
