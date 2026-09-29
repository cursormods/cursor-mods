"""Desktop composition for the application's own HWND; no OS settings changed."""
import ctypes
from ctypes import wintypes
import sys


class AccentPolicy(ctypes.Structure):
    _fields_ = [("state", ctypes.c_int), ("flags", ctypes.c_int),
                ("color", wintypes.DWORD), ("animation", ctypes.c_int)]


class CompositionData(ctypes.Structure):
    _fields_ = [("attribute", ctypes.c_int), ("data", ctypes.c_void_p), ("size", ctypes.c_size_t)]


def enable_desktop_blur(hwnd):
    """Use Windows 10's compositor blur without fading the foreground window.

    This Windows 10 composition entry point is optional. The caller retains
    ordinary desktop translucency if the compositor refuses the request.
    """
    if sys.platform != "win32":
        return False
    try:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        apply = user32.SetWindowCompositionAttribute
        apply.argtypes = [wintypes.HWND, ctypes.POINTER(CompositionData)]
        apply.restype = wintypes.BOOL
        # BlurBehind is considerably smoother during live window dragging than
        # Windows 10 AcrylicBlurBehind. QML supplies the tint and borders.
        policy = AccentPolicy(3, 0, 0, 0)
        data = CompositionData(19, ctypes.addressof(policy), ctypes.sizeof(policy))
        return bool(apply(hwnd, ctypes.byref(data)))
    except (AttributeError, OSError):
        return False


def update_window_region(hwnd, width, height, radius, maximized=False):
    """Clip both the Qt surface and desktop blur to real rounded outer corners."""
    if sys.platform != "win32":
        return
    user32, gdi32 = ctypes.windll.user32, ctypes.windll.gdi32
    user32.SetWindowRgn.argtypes = [wintypes.HWND, wintypes.HRGN, wintypes.BOOL]
    user32.SetWindowRgn.restype = ctypes.c_int
    gdi32.CreateRoundRectRgn.argtypes = [ctypes.c_int] * 6
    gdi32.CreateRoundRectRgn.restype = wintypes.HRGN
    gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
    if maximized:
        user32.SetWindowRgn(hwnd, None, True)
        return
    region = gdi32.CreateRoundRectRgn(0, 0, round(width) + 1, round(height) + 1,
                                    round(radius * 2), round(radius * 2))
    if region and not user32.SetWindowRgn(hwnd, region, True):
        gdi32.DeleteObject(region)
