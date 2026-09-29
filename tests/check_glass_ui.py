"""Render and exercise the real QML window using isolated user data.

Run separately from unittest discovery; no game, cursor, startup or hotkey changes.
"""
import argparse
import ctypes
from ctypes import wintypes
import importlib
import json
import os
from pathlib import Path
from unittest.mock import Mock, patch
import sys
import tempfile
import time
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
parser = argparse.ArgumentParser()
parser.add_argument("--render-dir", type=Path, default=ROOT / "build/glass-qa")
args = parser.parse_args()
args.render_dir.mkdir(parents=True, exist_ok=True)
data = tempfile.TemporaryDirectory(prefix="cursormods-glass-")
os.environ["CURSORMODS_DATA_DIR"] = data.name

from PySide6.QtCore import QPoint, Qt, QTimer, qInstallMessageHandler, QCoreApplication, QEvent
from PySide6.QtQuick import QQuickItem
from PySide6.QtTest import QTest
from PySide6.QtGui import QWheelEvent
from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QApplication
import catmouse as core
from glass_app import create_application, PALETTES

messages = []
def qt_message(kind, context, message):
    messages.append(message)
    print("QT:", message, flush=True)
qInstallMessageHandler(qt_message)
app, engine, bridge, window = create_application(core, True)
checks = []
def check(value, label):
    assert value, label
    checks.append(label)

def visual_item(name, item=None):
    item = item or window.contentItem()
    if item.objectName() == name:
        return item
    for child in item.childItems():
        result = visual_item(name, child)
        if result is not None:
            return result
    return None

def click_dock(index):
    dock = window.findChild(QQuickItem, "bottomDock")
    p = dock.mapToScene(QPointF(16 + (index+.5)*(dock.width()-32)/3, 81))
    QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, QPoint(round(p.x()), round(p.y())))

def wait_idle():
    until = time.monotonic()+8
    while bridge.busy and time.monotonic() < until:
        QTest.qWait(20)
    check(not bridge.busy, "Worker queue completes")

def run_checks():
    code = 1
    try:
        check(not bridge.cfg["enabled"] and not bridge.pet.isVisible(), "Kitty is off by default")
        check(not bridge.pet.sheet.isNull(), "Offline Kitty sprite loads")
        check(bool(window.flags() & Qt.FramelessWindowHint), "Native caption removed")
        check(window.opacity() == 1, "Foreground stays fully opaque")
        check(window.property("pageIndex") == 0, "Roblox opens by default")
        check(bridge.cfg["startup"], "Start with Windows defaults to on")
        window.grabWindow().save(str(args.render_dir / "default-roblox.png"))
        sections = [visual_item("robloxSection_"+kind) for kind in ("cursor","ui","sky","font")]
        check(all(sections), "All four Roblox sections exist")
        check([s.property("title") for s in sections] == ["Roblox Cursor","UI Wheel","Skybox","Font"], "Exact requested labels")
        check(sections[0].x() < sections[1].x() and sections[0].y() == sections[1].y()
              and sections[2].y() > sections[0].y() and sections[2].y() == sections[3].y(), "Roblox panels form a two-by-two grid")
        scroll = window.findChild(QQuickItem, "pageScroll")
        bottom = sections[3].mapToItem(scroll, QPointF(0, sections[3].height())).y()
        check(bottom <= scroll.height(), "All four empty panels fit the default window")
        check(not window.findChild(QQuickItem, "windowsCursorSection"), "Windows cursors are absent from Roblox")
        window.close()
        QTest.qWait(80)
        check(not window.isVisible() and not getattr(bridge, "_stopped", False), "X hides the window without shutting down")
        check(not app.quitOnLastWindowClosed(), "Hidden main window keeps the application running")
        bridge.showWindow()
        QTest.qWait(100)
        check(window.isVisible(), "Tray show restores the main window")
        print("COMPOSITOR BLUR:", bridge.blurAvailable, flush=True)
        gdi, user = ctypes.windll.gdi32, ctypes.windll.user32
        gdi.CreateRectRgn.restype = wintypes.HRGN
        user.GetWindowRgn.argtypes = [wintypes.HWND, wintypes.HRGN]
        gdi.PtInRegion.argtypes = [wintypes.HRGN, ctypes.c_int, ctypes.c_int]
        gdi.DeleteObject.argtypes = [wintypes.HGDIOBJ]
        region = gdi.CreateRectRgn(0,0,0,0)
        check(user.GetWindowRgn(int(window.winId()), region) != 0, "Native rounded region exists")
        check(not gdi.PtInRegion(region, 0, 0) and gdi.PtInRegion(region, 40,40), "Actual outer corners are clipped")
        gdi.DeleteObject(region)

        for theme in PALETTES:
            bridge.setTheme(theme)
            for index in range(3):
                click_dock(index)
                QTest.qWait(340)
                check(window.property("pageIndex") == index, f"{theme}: dock opens page {index}")
                frame = window.grabWindow()
                check(not frame.isNull(), f"{theme}: page {index} renders")
                check(frame.hasAlphaChannel(), f"{theme}: transparency available")
                if index in (0,2) or theme == "Black":
                    frame.save(str(args.render_dir / f"{theme.lower().replace(' ', '-')}-{index}.png"))
        for index in [1,2,0,1,2,1,2,0]:
            click_dock(index)
            QTest.qWait(30)
        QTest.qWait(350)
        dock = window.findChild(QQuickItem, "bottomDock")
        check(abs(dock.property("indicatorX") - (16+(dock.width()-32)/6)) < .5,
              "Interrupted dock animations settle on the latest selection")

        window.resize(720,560)
        QTest.qWait(150)
        click_dock(0)
        QTest.qWait(200)
        scroll = window.findChild(QQuickItem, "pageScroll")
        check(scroll.property("contentHeight") > scroll.height(), "Small window preserves scrollable content")
        pos = QPointF(window.width()/2, 280)
        QApplication.sendEvent(window, QWheelEvent(pos, window.mapToGlobal(pos.toPoint()), QPoint(), QPoint(0,-120),
                              Qt.NoButton, Qt.NoModifier, Qt.NoScrollPhase, False))
        QTest.qWait(400)
        check(scroll.property("contentY") > 0, "Mouse wheel scrolls the page")
        scroll.setProperty("contentY", scroll.property("contentHeight")-scroll.height())
        QTest.qWait(100)
        window.grabWindow().save(str(args.render_dir / "small-roblox-bottom.png"))
        click_dock(2)
        QTest.qWait(350)
        check(bool(window.findChild(QQuickItem, "windowsCursorSection")), "Settings contains the full Windows cursor panel")
        bridge.setSetting("glass_opacity", .2)
        QTest.qWait(80)
        check(window.opacity() == 1, "Low glass opacity does not fade text")
        frame = window.grabWindow()
        check(frame.pixelColor(400,70).alpha() < 180, "Low glass tint leaves real desktop transparency")
        frame.save(str(args.render_dir / "small-pink-low-opacity.png"))
        bridge.setSetting("glass_opacity", 1)
        QTest.qWait(80)
        check(window.grabWindow().pixelColor(400,70).alpha() > 245, "High opacity makes the background solid")
        bridge.setSetting("glass_opacity", .72)

        window.showMaximized()
        QTest.qWait(200)
        check(window.windowState() == Qt.WindowMaximized, "Maximize works")
        window.showNormal()
        window.showMinimized()
        QTest.qWait(100)
        bridge.showWindow()
        QTest.qWait(120)
        check(window.isVisible() and window.windowState() == Qt.WindowNoState, "Minimize and restore work")
        bridge.setSetting("always_on_top", True)
        QTest.qWait(100)
        check(bool(window.flags() & Qt.WindowStaysOnTopHint), "Always-on-top flag applies to the custom window")
        bridge.setSetting("always_on_top", False)
        QTest.qWait(100)
        check(not bool(window.flags() & Qt.WindowStaysOnTopHint), "Always-on-top can be disabled")

        bridge.captureHotkey("freeze_hotkey")
        QTest.keyClick(window, Qt.Key_G, Qt.ControlModifier | Qt.ShiftModifier)
        check(bridge.cfg["freeze_hotkey"] == "ctrl+shift+g", "Shortcut capture accepts modifier keys")
        bridge.captureHotkey("freeze_hotkey")
        QTest.keyClick(window, Qt.Key_Escape)
        check(bridge.recording == "" and bridge.cfg["freeze_hotkey"] == "ctrl+shift+g", "Esc cancels shortcut capture")

        # Exercise ZIP imports through the real Qt bridge and worker queue while
        # replacing the system-changing apply with a recording test double.
        applied = []
        click_dock(0)
        QTest.qWait(340)
        bridge.apply_sync = lambda kind, name: applied.append((kind,name))
        archive = Path(data.name) / "Nested pack.zip"
        with zipfile.ZipFile(archive, "w") as output:
            output.writestr("wrapper/cursors/Arrow.cur", b"test-data-only")
        bridge.importPaths("windows", [archive.as_uri()])
        check(bridge.busy and not bridge.canClose(), "Close waits for in-progress imports")
        wait_idle()
        check(applied == [("windows", "Nested pack")], "Nested ZIP import applies automatically")
        check(bridge.packs["windows"][0]["name"] == "Nested pack", "Imported pack reaches the QML model")
        bridge.removePack("windows", "Nested pack")
        wait_idle()
        check(not bridge.packs["windows"], "Remove updates the library")
        bad = Path(data.name) / "bad.zip"
        with zipfile.ZipFile(bad,"w") as output:
            output.writestr("../../escape.cur", b"bad")
        bridge.importPaths("windows", [bad.as_uri()])
        wait_idle()
        check(bridge.statusKind == "error" and not bridge.packs["windows"], "Unsafe ZIP reports an error without a partial pack")
        from PIL import Image
        pngs = [Path(data.name) / n for n in ("ArrowCursor.png", "MouseLockedCursor.png")]
        for png in pngs:
            Image.new("RGBA", (32,32), "green").save(png)
        before = len(applied)
        bridge.importPaths("cursor", [p.as_uri() for p in pngs])
        wait_idle()
        check(len(applied) == before+1 and applied[-1][0] == "cursor", "PNG files dropped together apply once as one pack")
        check(len(bridge.packs["cursor"]) == 1, "Grouped PNG drop creates one library entry")
        bridge._pending = 1
        window.close()
        QTest.qWait(80)
        check(not window.isVisible(), "X hides while an operation is running")
        fake_app = Mock()
        with patch("glass_app.QApplication") as app_class:
            app_class.instance.return_value = fake_app
            bridge.quitApp()
            check(not fake_app.quit.called and window.isVisible(), "Tray Quit waits for an active operation and shows its status")
            bridge._pending = 0
            bridge.quitApp()
            check(fake_app.quit.call_count == 1 and bridge.requestClose(), "Tray Quit requests a full exit after operations finish")
        check(not messages, "All pages render and interact without Qt warnings")
        code = 0
    finally:
        report = {"passed": code == 0, "checks": checks, "qt_messages": messages, "blur_requested_successfully": bridge.blurAvailable}
        (args.render_dir / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps({"passed": code == 0, "checks": len(checks)}, indent=2), flush=True)
        app.exit(code)

QTimer.singleShot(500, run_checks)
result = app.exec()
engine.deleteLater()
QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
for handler in core.logger.handlers[:]:
    handler.close()
    core.logger.removeHandler(handler)
data.cleanup()
sys.exit(result)
