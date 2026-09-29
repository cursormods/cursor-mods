"""Qt Quick application bridge. Mod I/O is serialized off the GUI thread."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import os
from pathlib import Path
import sys
import time

from PySide6.QtCore import QObject, Property, Signal, Slot, QTimer, QUrl, Qt, QCoreApplication, QEvent
from PySide6.QtGui import QIcon, QPixmap, QKeySequence
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtWidgets import QApplication, QFileDialog, QMenu, QSystemTrayIcon

from native_glass import enable_desktop_blur, update_window_region
from qt_pet import Kitty

RESOURCE_ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
PALETTES = {
    "Black": {"base": "#242426", "ink": "#fcfaf6", "muted": "#d2cfc9", "accent": "#e9dbbd", "light": False},
    "White": {"base": "#e9e5df", "ink": "#262623", "muted": "#55524e", "accent": "#6d6258", "light": True},
    "Navy Blue": {"base": "#172c40", "ink": "#f7fbff", "muted": "#c2d7e8", "accent": "#9dd8ff", "light": False},
    "Dark Purple": {"base": "#2d243e", "ink": "#fcf8ff", "muted": "#d7c9e8", "accent": "#dcbcff", "light": False},
    "Dark Green": {"base": "#20382e", "ink": "#f4fff8", "muted": "#c4ddd0", "accent": "#abedcd", "light": False},
    "Light Pink": {"base": "#eedce4", "ink": "#392831", "muted": "#6a4d5b", "accent": "#975d7b", "light": True},
}


def initialize_startup(core, cfg, safe_mode=False):
    """Apply the default once; retain saved opt-outs and later Windows changes."""
    if safe_mode:
        return
    if not cfg.get("startup_initialized", False):
        if cfg.get("startup", True) and not core._is_startup_enabled():
            core._set_startup(True)
        cfg["startup_initialized"] = True
    cfg["startup"] = core._is_startup_enabled()


class Bridge(QObject):
    changed = Signal()
    packsChanged = Signal()
    statusChanged = Signal()
    jobFinished = Signal(str, str)
    progress = Signal(str, str)
    hotkeyTriggered = Signal(str)

    def __init__(self, core, safe_mode=False):
        super().__init__()
        self.core, self.safe_mode = core, safe_mode
        self.cfg = core.load_config()
        self.cfg["glass_opacity"] = max(.2, min(1., float(self.cfg.get("glass_opacity", .72))))
        self.cfg["cursor_size"] = self.cfg.get("cursor_size") or core._get_default_cursor_size()
        self.cfg["theme"] = self.cfg.get("theme") if self.cfg.get("theme") in PALETTES else "Black"
        initialize_startup(core, self.cfg, safe_mode)
        self.cfg.setdefault("always_on_top", False)
        self._pending = 0
        self._status, self._status_kind = "Ready.", "normal"
        self._recording = ""
        self._blur = False
        self._packs = {}
        self.window = self.pet = self.tray = None
        self.hotkeys = {}
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="cursor-mods")
        self.cursor_mgr = core.CursorManager()
        self.roblox = core.RobloxIntegration(self.cursor_mgr, self.cfg, status_callback=lambda msg, key=None: self.progress.emit(msg, "error" if key == "warn" else "normal"))
        self.progress.connect(self.set_status)
        self.jobFinished.connect(self._job_finished)
        self.hotkeyTriggered.connect(self._hotkey)
        self.save_timer = QTimer(self)
        self.save_timer.setSingleShot(True)
        self.save_timer.setInterval(250)
        self.save_timer.timeout.connect(self.save)
        self.cursor_timer = QTimer(self)
        self.cursor_timer.setSingleShot(True)
        self.cursor_timer.setInterval(300)
        self.cursor_timer.timeout.connect(self._resize_cursor)
        self.refresh_packs()
        self.save()

    @Property("QVariantMap", notify=changed)
    def settings(self):
        return dict(self.cfg)

    @Property("QVariantMap", notify=changed)
    def colors(self):
        return PALETTES[self.cfg["theme"]]

    @Property("QStringList", constant=True)
    def themes(self):
        return list(PALETTES)

    @Property("QVariantMap", notify=packsChanged)
    def packs(self):
        return self._packs

    @Property(str, notify=statusChanged)
    def status(self):
        return self._status

    @Property(str, notify=statusChanged)
    def statusKind(self):
        return self._status_kind

    @Property(bool, notify=statusChanged)
    def busy(self):
        return self._pending > 0

    @Property(str, notify=changed)
    def recording(self):
        return self._recording

    @Property(bool, notify=changed)
    def blurAvailable(self):
        return self._blur

    @Property(bool, constant=True)
    def testMode(self):
        return self.safe_mode

    def save(self):
        self.core.save_config(self.cfg)

    def store(self, kind):
        return {"windows": self.cursor_mgr.store, "cursor": self.roblox.rbx_cursor_store,
                "ui": self.roblox.ui_store, "sky": self.roblox.sky_store, "font": self.roblox.font_store}[kind]

    def key(self, kind):
        return "cursor_pack" if kind == "windows" else self.roblox.KEYS[kind]

    def refresh_packs(self):
        self._packs = {kind: [{"name": name, "active": self.cfg.get(self.key(kind)) == name}
                              for name in self.store(kind).list_packs()]
                       for kind in ("windows", "cursor", "ui", "sky", "font")}
        self.packsChanged.emit()

    @Slot(str, str)
    def set_status(self, message, kind="normal"):
        self._status, self._status_kind = message, kind
        self.statusChanged.emit()

    def submit(self, message, work):
        self._pending += 1
        self.set_status(message)
        def run():
            try:
                with self.roblox.operation_lock:
                    result = work()
                self.jobFinished.emit(result or "Done.", "success")
            except Exception as exc:
                self.core.log_exc("OPERATION", str(exc))
                self.jobFinished.emit(str(exc), "error")
        self.pool.submit(run)

    @Slot(str, str)
    def _job_finished(self, message, kind):
        self._pending = max(0, self._pending-1)
        self.refresh_packs()
        self.changed.emit()
        self.set_status(message, kind)

    def apply_sync(self, kind, name):
        if self.safe_mode:
            raise ValueError("System changes are disabled in this isolated test window.")
        if kind != "windows":
            self.roblox.apply_selection(kind, name)
            return
        mapping = self.cursor_mgr._get_pack_mapping(name)
        if not mapping:
            raise ValueError("No compatible Windows cursors were found in this pack.")
        previous = self.cfg.get("cursor_pack")
        self.cursor_mgr.restore_defaults()
        applied = self.cursor_mgr.apply_pack(name, self.cfg["cursor_size"])
        if applied != len(mapping):
            self.cursor_mgr.restore_defaults()
            if previous:
                self.cursor_mgr.apply_pack(previous, self.cfg["cursor_size"])
            raise ValueError("Some cursors could not be loaded. The previous selection was restored.")
        self.cfg["cursor_pack"] = name
        self.save()

    @Slot(str, str)
    def applyPack(self, kind, name):
        if kind not in self._packs:
            return
        def work():
            self.apply_sync(kind, name)
            return f"{name} applied." + (" Reopen Roblox to see your changes." if kind != "windows" else "")
        self.submit(f"Applying {name}…", work)

    @Slot(str, "QVariantList")
    def importPaths(self, kind, sources):
        if kind not in self._packs:
            return
        paths = []
        for source in sources:
            url = source if isinstance(source, QUrl) else QUrl(str(source))
            path = url.toLocalFile() if url.isLocalFile() else str(source)
            if path:
                paths.append(path)
        # A multi-file PNG drop is one pack so applying the next file does not
        # restore the cursor roles that were supplied by the previous file.
        groups = [paths] if kind == "cursor" and paths and all(Path(p).suffix.lower() == ".png" for p in paths) else [[p] for p in paths]
        for paths in groups:
            def work(paths=paths):
                last = [0.]
                def progress(message):
                    if time.monotonic()-last[0] > .08:
                        last[0] = time.monotonic()
                        self.progress.emit(message, "normal")
                name = self.store(kind).import_files(paths) if len(paths) > 1 else self.store(kind).import_pack(paths[0], progress=progress)
                try:
                    self.apply_sync(kind, name)
                except Exception as exc:
                    raise RuntimeError(f"{name} was imported but could not be applied: {exc}") from exc
                return f"{name} imported and applied." + (" Reopen Roblox to see your changes." if kind != "windows" else "")
            self.submit("Importing pack…", work)

    @Slot(str, bool)
    def browse(self, kind, folder):
        if kind not in self._packs:
            return
        if folder:
            path = QFileDialog.getExistingDirectory(None, "Choose a pack folder")
            if path:
                self.importPaths(kind, [path])
        else:
            pattern = {"font": "Font / ZIP (*.zip *.ttf *.otf)",
                       "cursor": "PNG / ZIP (*.zip *.png)"}.get(kind, "ZIP (*.zip)")
            paths, _ = QFileDialog.getOpenFileNames(None, "Import a pack", "", pattern)
            self.importPaths(kind, paths)

    def restore_windows(self):
        if self.safe_mode:
            raise ValueError("System changes are disabled in this isolated test window.")
        self.cursor_mgr.restore_defaults()
        self.cfg["cursor_pack"] = None
        self.save()

    @Slot(str)
    def unapply(self, kind):
        def work():
            if kind == "windows":
                self.restore_windows()
            else:
                self.apply_sync(kind, None)
            return "Original cursors restored." if kind == "windows" else "Section restored. Reopen Roblox to see your changes."
        if kind in self._packs:
            self.submit("Restoring originals…", work)

    @Slot(str, str)
    def removePack(self, kind, name):
        if kind not in self._packs:
            return
        def work():
            if self.cfg.get(self.key(kind)) == name:
                self.restore_windows() if kind == "windows" else self.apply_sync(kind, None)
            self.store(kind).delete_pack(name)
            return f"{name} removed."
        self.submit(f"Removing {name}…", work)

    @Slot()
    def restoreRoblox(self):
        def work():
            if self.safe_mode:
                raise ValueError("System changes are disabled in this isolated test window.")
            self.roblox.restore_all_roblox()
            return "Roblox restored. Reopen the game to see your changes."
        self.submit("Restoring Roblox…", work)

    @Slot(str)
    def setTheme(self, theme):
        if theme in PALETTES:
            self.cfg["theme"] = theme
            self.changed.emit()
            self.save_timer.start()

    @Slot(str, "QVariant")
    def setSetting(self, key, value):
        limits = {"glass_opacity": (.2, 1., float), "cat_size": (16, 96, int),
                  "speed": (2, 30, int), "cursor_size": (16, 96, int)}
        if key in limits:
            lo, hi, cast = limits[key]
            self.cfg[key] = cast(max(lo, min(hi, float(value))))
        elif key in ("enabled", "always_on_top", "startup"):
            self.cfg[key] = bool(value)
        else:
            return
        if key == "enabled" and self.pet:
            self.pet.toggle(self.cfg[key])
        elif key == "cat_size" and self.pet:
            self.pet.set_size(self.cfg[key])
        elif key == "speed" and self.pet:
            self.pet.speed = self.cfg[key]
        elif key == "cursor_size":
            self.cursor_timer.start()
        elif key == "startup" and not self.safe_mode:
            self.core._set_startup(self.cfg[key])
            actual = self.core._is_startup_enabled()
            if actual != self.cfg[key]:
                self.cfg[key] = actual
                self.set_status("Windows could not update the startup setting. Your previous setting was kept.", "error")
        elif key == "always_on_top" and self.window:
            self.window.setFlag(Qt.WindowStaysOnTopHint, self.cfg[key])
            self.window.show()
            QTimer.singleShot(50, self.reapplyGlass)
        self.changed.emit()
        self.save_timer.start()

    @Slot()
    def resetCursorSize(self):
        self.setSetting("cursor_size", self.core._get_default_cursor_size())

    def _resize_cursor(self):
        if self.cfg.get("cursor_pack"):
            self.applyPack("windows", self.cfg["cursor_pack"])

    @Slot()
    def freezeKitty(self):
        if self.pet:
            frozen = self.pet.freeze()
            self.set_status("Kitty paused." if frozen else "Kitty resumed.")

    @Slot(str)
    def captureHotkey(self, key):
        if key in ("freeze_hotkey", "toggle_hotkey"):
            self._recording = key
            self.changed.emit()

    @Slot(int, int)
    def recordKey(self, key, modifiers):
        if not self._recording:
            return
        if key == Qt.Key_Escape:
            self._recording = ""
            self.changed.emit()
            return
        if key in (Qt.Key_Control, Qt.Key_Shift, Qt.Key_Alt, Qt.Key_Meta):
            return
        # Keep the existing keyboard package's global shortcut format.
        name = QKeySequence(key).toString(QKeySequence.PortableText).lower()
        mods = [word for flag, word in ((Qt.ControlModifier, "ctrl"), (Qt.AltModifier, "alt"),
                 (Qt.ShiftModifier, "shift"), (Qt.MetaModifier, "windows")) if modifiers & flag.value]
        if modifiers & Qt.KeypadModifier.value:
            name = "num " + name
        hotkey = "+".join(mods + [name])
        setting = self._recording
        try:
            if not self.safe_mode and self.core.HAS_KEYBOARD:
                token = self.core._add_hotkey(hotkey, lambda: self.hotkeyTriggered.emit(setting))
                self.core._remove_hotkey(self.hotkeys.get(setting))
                self.hotkeys[setting] = token
            self.cfg[setting] = hotkey
            self.save()
        except Exception as exc:
            self.set_status(f"Could not use that shortcut: {exc}", "error")
        self._recording = ""
        self.changed.emit()

    @Slot(str)
    def _hotkey(self, key):
        if key == "freeze_hotkey":
            self.freezeKitty()
        elif self.window:
            if self.window.isVisible():
                self.window.hide()
            else:
                self.showWindow()

    @Slot()
    def showWindow(self):
        if self.window:
            self.window.showNormal()
            self.window.raise_()
            self.window.requestActivate()

    @Slot()
    def reapplyGlass(self):
        if not self.window:
            return
        self._blur = enable_desktop_blur(int(self.window.winId()))
        self.updateCorners()
        self.changed.emit()

    @Slot()
    def updateCorners(self):
        if self.window:
            ratio = self.window.devicePixelRatio()
            update_window_region(int(self.window.winId()), self.window.width()*ratio,
                                 self.window.height()*ratio, 26*ratio,
                                 self.window.windowState() == Qt.WindowMaximized)

    @Slot(int, int)
    def rememberSize(self, width, height):
        if self.window and self.window.windowState() != Qt.WindowMaximized:
            self.cfg["window_width"], self.cfg["window_height"] = width, height
            self.save_timer.start()

    @Slot(result=bool)
    def canClose(self):
        if self.busy:
            self.set_status("An operation is running. Quit when it finishes.")
            return False
        return True

    @Slot()
    def hideToTray(self):
        if self.window:
            self.window.hide()

    @Slot(result=bool)
    def requestClose(self):
        if getattr(self, "_quitting", False):
            return True
        self.hideToTray()
        return False

    @Slot()
    def quitApp(self):
        if self.canClose():
            self._quitting = True
            QApplication.instance().quit()
        else:
            self.showWindow()

    def start(self, window):
        self.window = window
        self.pet = Kitty(RESOURCE_ROOT / "assets/oneko.gif", self.cfg)
        QTimer.singleShot(80, self.reapplyGlass)
        if self.safe_mode:
            return
        if self.cfg.get("enabled"):
            self.pet.toggle(True)
        for key in ("toggle_hotkey", "freeze_hotkey"):
            try:
                if self.core.HAS_KEYBOARD:
                    self.hotkeys[key] = self.core._add_hotkey(self.cfg[key], lambda k=key: self.hotkeyTriggered.emit(k))
            except Exception as exc:
                self.set_status(f"Shortcut unavailable: {exc}", "error")
        self.tray = QSystemTrayIcon(QApplication.windowIcon(), self)
        self.tray_menu = menu = QMenu()
        menu.addAction("Show Cursor Mods", self.showWindow)
        menu.addAction("Quit", self.quitApp)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(lambda reason: self.showWindow() if reason == QSystemTrayIcon.DoubleClick else None)
        self.tray.setToolTip("Cursor Mods")
        self.tray.show()
        self.roblox.start_watcher()
        def reapply():
            if self.cfg.get("cursor_pack"):
                self.apply_sync("windows", self.cfg["cursor_pack"])
            self.roblox.reapply_all()
            return "Saved packs applied."
        if self.cfg.get("cursor_pack") or any(self.cfg.get(k) for k in self.roblox.KEYS.values()):
            QTimer.singleShot(350, lambda: self.submit("Loading packs…", reapply))

    def shutdown(self):
        if getattr(self, "_stopped", False):
            return
        self._stopped = True
        self.roblox.stop_watcher()
        self.pool.shutdown(wait=True, cancel_futures=True)
        self.save()
        if self.pet:
            self.pet.toggle(False)
            self.pet.close()
        if self.tray:
            self.tray.hide()
        for token in self.hotkeys.values():
            self.core._remove_hotkey(token)
        if not self.safe_mode:
            with self.roblox.operation_lock:
                self.cursor_mgr.restore_defaults()


def create_application(core, safe_mode=False):
    QQuickWindow.setDefaultAlphaBuffer(True)
    QQuickStyle.setStyle("Basic")
    application = QApplication.instance() or QApplication(sys.argv)
    application.setApplicationName("Cursor Mods")
    application.setQuitOnLastWindowClosed(False)
    application.setOrganizationName("CursorMods")
    application.setStyle("Fusion")
    application.setWindowIcon(QIcon(str(RESOURCE_ROOT / "cat.ico")))
    bridge = Bridge(core, safe_mode)
    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("backend", bridge)
    engine.load(QUrl.fromLocalFile(str(RESOURCE_ROOT / "qml/Main.qml")))
    if not engine.rootObjects():
        bridge.shutdown()
        raise RuntimeError("Could not load the Cursor Mods interface.")
    window = engine.rootObjects()[0]
    bridge.start(window)
    application.aboutToQuit.connect(bridge.shutdown)
    return application, engine, bridge, window


def run(core, safe_mode=False):
    QQuickWindow.setDefaultAlphaBuffer(True)
    app = QApplication.instance() or QApplication(sys.argv)
    # A second launch focuses the existing instance instead of racing its backups.
    if not safe_mode:
        name = "CursorMods-" + hashlib.sha256(core.APP_DIR.encode()).hexdigest()[:16]
        socket = QLocalSocket()
        socket.connectToServer(name)
        if socket.waitForConnected(150):
            socket.write(b"show")
            socket.flush()
            socket.waitForBytesWritten(150)
            return 0
        server = QLocalServer(app)
        QLocalServer.removeServer(name)
        server.listen(name)
    app, engine, bridge, window = create_application(core, safe_mode)
    if not safe_mode:
        def incoming():
            client = server.nextPendingConnection()
            bridge.showWindow()
            client.disconnectFromServer()
        server.newConnection.connect(incoming)
    if safe_mode and "--ui-capture-dir" in sys.argv:
        import json
        target = Path(sys.argv[sys.argv.index("--ui-capture-dir") + 1])
        target.mkdir(parents=True, exist_ok=True)
        def capture():
            frame = window.grabWindow()
            saved = frame.save(str(target / "packaged-window.png"))
            (target / "packaged-report.json").write_text(json.dumps({
                "rendered": saved and not frame.isNull(), "size": [frame.width(), frame.height()],
                "kitty_off": not bridge.pet.isVisible(), "blur": bridge.blurAvailable,
                "window_opacity": window.opacity(), "alpha": frame.hasAlphaChannel(),
                "frameless": bool(window.flags() & Qt.FramelessWindowHint),
            }, indent=2), encoding="utf-8")
            bridge.quitApp()
        QTimer.singleShot(1500, capture)
    result = app.exec()
    # QML must be destroyed while its Python context object is still alive.
    engine.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    return result
