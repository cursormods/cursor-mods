import importlib
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import time
import unittest
from unittest.mock import patch, Mock
import zipfile
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pack_store import PackStore
from mod_engine import BackupJournal
import mod_engine


class IsolatedTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="cursormods-test-")
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()


class ImportTests(IsolatedTest):
    def store(self, kind="CURSOR"):
        return PackStore(self.root / "library", kind)

    def archive(self, files, filename="test pack.zip"):
        path = self.root / filename
        with zipfile.ZipFile(path, "w") as archive:
            for name, value in files.items():
                archive.writestr(name, value)
        return path

    def test_nested_zip_preserves_scheme_and_names(self):
        archive = self.archive({"outer/inner/Arrow.cur": b"cursor", "outer/inner/install.inf": b"scheme"})
        store = self.store()
        messages = []
        name = store.import_pack(archive, messages.append)
        self.assertEqual(name, "test pack")
        self.assertEqual(list(store.find_files(name, (".cur",))), ["Arrow.cur"])
        self.assertTrue(messages)
        self.assertEqual(store.import_pack(archive), "test pack (2)")

    def test_archive_cannot_escape(self):
        for path in ("../escaped.cur", "C:/escaped.cur", "folder/../../escaped.cur", "file.cur:stream", "CON.cur"):
            with self.subTest(path=path):
                archive = self.archive({path: b"bad"})
                store = self.store()
                with self.assertRaises(ValueError):
                    store.import_pack(archive)
                self.assertEqual(store.list_packs(), [])

    def test_bad_zip_does_not_leave_pack(self):
        archive = self.root / "broken.zip"
        archive.write_bytes(b"broken")
        store = self.store()
        with self.assertRaises(ValueError):
            store.import_pack(archive)
        self.assertEqual(store.list_packs(), [])

    def test_wrong_section_rejected(self):
        store = self.store()
        with self.assertRaises(ValueError):
            store.import_pack(self.archive({"font.ttf": b"font"}))
        self.assertEqual(store.list_packs(), [])

    def test_symlink_zip_rejected(self):
        archive = self.root / "linked.zip"
        with zipfile.ZipFile(archive, "w") as z:
            info = zipfile.ZipInfo("link.cur")
            info.create_system = 3
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            z.writestr(info, "outside")
        with self.assertRaises(ValueError):
            self.store().import_pack(archive)

    def test_fonts_and_ui_accept_nested_zip(self):
        font = self.archive({"font/font.ttf": b"font"}, "fonts.zip")
        self.assertEqual(self.store("FONT").import_pack(font), "fonts")
        ui = self.archive({"pack/content/textures/ui/a.png": b"ui"}, "ui.zip")
        self.assertEqual(self.store("UI").import_pack(ui), "ui")

    def test_size_limits_checked_before_extracting(self):
        with patch("pack_store.MAX_BYTES", 2):
            with self.assertRaises(ValueError):
                self.store().import_pack(self.archive({"arrow.cur": b"123"}))

    def test_duplicate_case_names_rejected(self):
        with self.assertRaises(ValueError):
            self.store().import_pack(self.archive({"Arrow.cur": b"1", "arrow.cur": b"2"}))

    def test_direct_textures_folder_can_be_imported(self):
        source = self.root / "textures"
        (source / "ui").mkdir(parents=True)
        (source / "ui" / "image.png").write_bytes(b"image")
        store = self.store("UI")
        name = store.import_pack(source)
        self.assertTrue(Path(store.pack_dir(name), "textures/ui/image.png").is_file())

    def test_loose_png_preserves_filename(self):
        image = self.root / "MouseLockedCursor.PNG"
        Image.new("RGBA", (32, 32), "blue").save(image)
        store = self.store("ROBLOX-CUR")
        name = store.import_pack(image)
        self.assertEqual(name, "MouseLockedCursor")
        self.assertEqual(list(store.find_files(name, (".png",))), [image.name])

    def test_multiple_pngs_form_one_pack(self):
        paths = [self.root / name for name in ("ArrowCursor.png", "MouseLockedCursor.png")]
        for path in paths:
            Image.new("RGBA", (32, 32), "blue").save(path)
        store = self.store("ROBLOX-CUR")
        name = store.import_files(paths)
        self.assertEqual(set(store.find_files(name, (".png",))), {p.name for p in paths})
        self.assertEqual(len(store.list_packs()), 1)

    def test_loose_png_limits_and_wrong_section(self):
        image = self.root / "ArrowCursor.png"
        Image.new("RGBA", (32, 32), "blue").save(image)
        store = self.store("ROBLOX-CUR")
        with patch("pack_store.MAX_BYTES", 2), self.assertRaises(ValueError):
            store.import_pack(image)
        self.assertEqual(store.list_packs(), [])
        with self.assertRaises(ValueError):
            self.store("UI").import_pack(image)

    def test_multi_png_duplicate_names_rejected_atomically(self):
        paths = []
        for folder in ("one", "two"):
            path = self.root / folder / "ArrowCursor.png"
            path.parent.mkdir()
            Image.new("RGBA", (32, 32), "blue").save(path)
            paths.append(path)
        store = self.store("ROBLOX-CUR")
        with self.assertRaises(ValueError):
            store.import_files(paths)
        self.assertEqual(store.list_packs(), [])


class StartupTests(unittest.TestCase):
    def test_first_launch_registers_startup(self):
        from glass_app import initialize_startup
        core = Mock()
        core._is_startup_enabled.side_effect = [False, True]
        cfg = {"startup": True}
        initialize_startup(core, cfg)
        core._set_startup.assert_called_once_with(True)
        self.assertTrue(cfg["startup"])
        self.assertTrue(cfg["startup_initialized"])

    def test_saved_opt_out_and_external_change_are_preserved(self):
        from glass_app import initialize_startup
        for cfg in ({"startup": False}, {"startup": True, "startup_initialized": True}):
            with self.subTest(config=cfg):
                core = Mock()
                core._is_startup_enabled.return_value = False
                initialize_startup(core, cfg)
                core._set_startup.assert_not_called()
                self.assertFalse(cfg["startup"])

    def test_ui_test_does_not_read_or_write_startup(self):
        from glass_app import initialize_startup
        core = Mock()
        cfg = {"startup": True}
        initialize_startup(core, cfg, safe_mode=True)
        self.assertTrue(cfg["startup"])
        core._set_startup.assert_not_called()
        core._is_startup_enabled.assert_not_called()


class RestoreTests(IsolatedTest):
    def setUp(self):
        super().setUp()
        self.version = self.root / "version-test"
        self.version.mkdir()
        self.target = self.version / "original.txt"
        self.target.write_bytes(b"original")
        self.backups = self.root / "backups"

    def journal(self):
        return BackupJournal(self.version, self.backups)

    def test_restore_removes_added_files_and_preserves_original(self):
        self.journal().commit({"original.txt": b"first mod", "new.txt": b"added"})
        self.journal().commit({"original.txt": b"second mod", "new.txt": b"added"})
        self.journal().commit({})
        self.assertEqual(self.target.read_bytes(), b"original")
        self.assertFalse((self.version / "new.txt").exists())

    def test_switching_pack_removes_leftovers(self):
        self.journal().commit({"one.txt": b"1"})
        self.journal().commit({"two.txt": b"2"})
        self.assertFalse((self.version / "one.txt").exists())
        self.assertEqual((self.version / "two.txt").read_bytes(), b"2")

    def test_case_variants_share_one_original(self):
        self.journal().commit({"Original.txt": b"first mod"})
        self.journal().commit({"ORIGINAL.txt": b"second mod"})
        journal = self.journal()
        self.assertEqual(len(journal.data['files']), 1)
        journal.commit({})
        self.assertEqual(self.target.read_bytes(), b"original")

    def test_backup_failure_prevents_game_writes(self):
        journal = self.journal()
        with patch("mod_engine.shutil.copy2", side_effect=PermissionError("blocked")):
            with self.assertRaises(PermissionError):
                journal.commit({"original.txt": b"mod"})
        self.assertEqual(self.target.read_bytes(), b"original")

    def test_mid_apply_failure_rolls_back_all_changed_files(self):
        journal = self.journal()
        real = mod_engine.replace_file
        failed = False
        def fail_once(source, dest):
            nonlocal failed
            if Path(dest).name == "z.txt" and not failed:
                failed = True
                raise PermissionError("blocked")
            real(source, dest)
        with patch("mod_engine.replace_file", side_effect=fail_once):
            with self.assertRaises(RuntimeError):
                journal.commit({"original.txt": b"mod", "z.txt": b"new"})
        self.assertEqual(self.target.read_bytes(), b"original")
        self.assertFalse((self.version / "z.txt").exists())
        self.assertEqual(self.journal().data["active"], [])

    def test_restore_failure_keeps_active_state(self):
        self.journal().commit({"original.txt": b"mod"})
        with patch("mod_engine.replace_file", side_effect=PermissionError("blocked")):
            with self.assertRaises(RuntimeError):
                self.journal().commit({})
        self.assertIn("original.txt", self.journal().data["active"])
        self.assertEqual(self.target.read_bytes(), b"mod")
        self.journal().commit({})
        self.assertEqual(self.target.read_bytes(), b"original")

    def test_conflicting_legacy_backups_fail_without_guessing(self):
        root = self.backups / self.version.name
        for feature, data in (("cursors", b"one"), ("ui", b"two")):
            (root / feature).mkdir(parents=True)
            (root / feature / "original.txt").write_bytes(data)
        with self.assertRaises(ValueError):
            self.journal()
        self.assertEqual(self.target.read_bytes(), b"original")


class AppIntegrationTests(IsolatedTest):
    def setUp(self):
        super().setUp()
        os.environ["CURSORMODS_DATA_DIR"] = str(self.root / "data")
        import main
        self.core = importlib.reload(main)
        self.versions = self.root / "versions"
        self.core.ROBLOX_VERSIONS_DIR = str(self.versions)
        self.core.ROBLOX_BACKUP_DIR = str(self.root / "backups")
        self.cfg = dict(self.core.DEFAULT_CONFIG)
        self.engine = self.core.RobloxIntegration(self.core.CursorManager(), self.cfg)

    def make_version(self, name, timestamp):
        path = self.versions / name
        (path / "content/textures/Cursors/KeyboardMouse").mkdir(parents=True)
        exe = path / "RobloxPlayerBeta.exe"
        exe.write_bytes(b"test executable marker")
        os.utime(exe, (timestamp, timestamp))
        return path

    def tearDown(self):
        for handler in self.core.logger.handlers[:]:
            handler.close()
            self.core.logger.removeHandler(handler)
        super().tearDown()

    def test_default_off_and_one_time_migration(self):
        self.assertFalse(self.core.load_config()["enabled"])
        self.assertTrue(self.core.load_config()["startup"])
        self.core.atomic_json(self.core.CONFIG_PATH, {"enabled": True})
        migrated = self.core.load_config()
        self.assertFalse(migrated["enabled"])
        migrated["enabled"] = True
        self.core.save_config(migrated)
        self.assertTrue(self.core.load_config()["enabled"])

    def test_version_selection_uses_client_not_folder_name(self):
        self.make_version("version-zz-old", 100)
        newest = self.make_version("version-aa-new", 200)
        (self.versions / "version-zzz-studio/content").mkdir(parents=True)
        self.assertEqual(Path(self.engine.find_latest_version_folder()), newest)

    def test_missing_roblox_does_not_mark_pack_active(self):
        with self.assertRaises(ValueError):
            self.engine.apply_selection("cursor", "missing")
        self.assertIsNone(self.cfg["roblox_cursor_pack"])

    def test_ui_and_cursor_overlap_restore_to_original(self):
        version = self.make_version("version-test", 200)
        relative = "content/textures/Cursors/KeyboardMouse/ArrowCursor.png"
        Image.new("RGBA", (32, 32), "red").save(version / relative)
        original = (version / relative).read_bytes()
        ui = self.root / "ui source"
        (ui / Path(relative).parent).mkdir(parents=True)
        Image.new("RGBA", (32, 32), "blue").save(ui / relative)
        cursor = self.root / "cursor source"
        cursor.mkdir()
        Image.new("RGBA", (32, 32), "green").save(cursor / "ArrowCursor.png")
        ui_name = self.engine.ui_store.import_pack(ui)
        cur_name = self.engine.rbx_cursor_store.import_pack(cursor)
        self.engine.apply_selection("ui", ui_name)
        ui_bytes = (version / relative).read_bytes()
        self.engine.apply_selection("cursor", cur_name)
        self.assertNotEqual((version / relative).read_bytes(), ui_bytes)
        self.engine.apply_selection("cursor", None)
        self.assertEqual((version / relative).read_bytes(), ui_bytes)
        self.engine.restore_all_roblox()
        self.assertEqual((version / relative).read_bytes(), original)

    def test_loose_png_roles_match_folder_import_and_restore(self):
        version = self.make_version("version-test", 200)
        cursor_dir = version / "content/textures/Cursors/KeyboardMouse"
        original = {}
        for name in ("ArrowCursor.png", "HandCursor.png"):
            Image.new("RGBA", (32, 32), "red").save(cursor_dir / name)
            original[name] = (cursor_dir / name).read_bytes()
        sources = self.root / "loose"
        sources.mkdir()
        paths = []
        for name in ("ArrowCursor.png", "link.png", "MouseLockedCursor.png"):
            path = sources / name
            Image.new("RGBA", (32, 32), "green").save(path)
            paths.append(path)
        store = self.engine.rbx_cursor_store
        loose = store.import_files(paths)
        folder = store.import_pack(sources)
        loose_map, loose_locked = self.engine._get_roblox_cursor_mapping(loose)
        folder_map, folder_locked = self.engine._get_roblox_cursor_mapping(folder)
        self.assertEqual({k:Path(v).name for k,v in loose_map.items()}, {k:Path(v).name for k,v in folder_map.items()})
        self.assertIn("HandCursor.png", loose_map)
        self.assertEqual(Path(loose_locked).name, Path(folder_locked).name)
        self.engine.apply_selection("cursor", loose)
        for name, before in original.items():
            self.assertNotEqual((cursor_dir / name).read_bytes(), before)
        locked_dest = version / "content/textures/MouseLockedCursor.png"
        self.assertTrue(locked_dest.exists())
        self.engine.restore_all_roblox()
        for name, before in original.items():
            self.assertEqual((cursor_dir / name).read_bytes(), before)
        self.assertFalse(locked_dest.exists())


if __name__ == "__main__":
    unittest.main()
