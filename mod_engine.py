"""Serialized Roblox operations with shared originals and transactional restore."""
import json
import logging
import os
from pathlib import Path
import re
import shutil
import tempfile
import threading
from io import BytesIO
from pack_store import atomic_json, contained


def replace_file(source, destination):
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".cursormods-", dir=destination.parent)
    os.close(fd)
    try:
        shutil.copyfile(source, temporary)
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class BackupJournal:
    def __init__(self, version, backup_root):
        self.version = Path(version)
        self.root = Path(backup_root, self.version.name)
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "manifest.json"
        self.data = {"files": {}, "active": []}
        if self.path.exists():
            self.data = json.loads(self.path.read_text(encoding="utf-8"))
        else:
            self._migrate_legacy()

    def _migrate_legacy(self):
        copies = {}
        for feature in ("cursors", "ui", "sky", "fonts"):
            directory = self.root / feature
            if directory.exists():
                for item in directory.rglob("*"):
                    if item.is_file():
                        rel = item.relative_to(directory).as_posix().casefold()
                        contained(self.version, rel)
                        copies.setdefault(rel, []).append(item)
        for rel, options in copies.items():
            if len({p.read_bytes() for p in options}) > 1:
                raise ValueError("Older Roblox backups disagree about an original file. Repair/reinstall Roblox before applying more mods; existing backups have been kept.")
            backup = contained(self.root / "originals", rel)
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(options[0], backup)
            self.data["files"][rel] = {"existed": True}
        self.data["active"] = list(copies)
        atomic_json(self.path, self.data)

    def original_bytes(self, rel):
        rel = str(rel).replace("\\", "/").casefold()
        item = self.data["files"].get(rel)
        if item:
            return contained(self.root / "originals", rel).read_bytes() if item["existed"] else None
        target = contained(self.version, rel)
        return target.read_bytes() if target.is_file() else None

    def commit(self, plan):
        """Preflight all writes, retain originals once, roll back failed operations."""
        # Roblox lives on Windows: UI packs and cursor packs may spell the same
        # destination differently. One original must cover both spellings.
        plan = {str(rel).replace("\\", "/").casefold(): source for rel, source in plan.items()}
        affected = sorted(set(self.data["active"]) | set(plan))
        with tempfile.TemporaryDirectory(prefix=".transaction-", dir=self.root) as temporary:
            stage, rollback = Path(temporary, "stage"), Path(temporary, "rollback")
            stage.mkdir(); rollback.mkdir()
            existed = {}
            for i, rel in enumerate(affected):
                target = contained(self.version, rel)
                if target.exists() and not target.is_file():
                    raise ValueError(f"A folder blocks the mod file: {rel}")
                existed[rel] = target.is_file()
                if existed[rel]:
                    shutil.copy2(target, rollback / str(i))
                if rel not in self.data["files"]:
                    if existed[rel]:
                        original = contained(self.root / "originals", rel)
                        original.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(target, original)
                    self.data["files"][rel] = {"existed": existed[rel]}
                if rel in plan:
                    source = plan[rel]
                    if isinstance(source, bytes):
                        (stage / str(i)).write_bytes(source)
                    else:
                        shutil.copyfile(source, stage / str(i))
                elif self.data["files"][rel]["existed"]:
                    shutil.copyfile(contained(self.root / "originals", rel), stage / str(i))
            # Persist recovery information BEFORE any game file can change.
            recovery_data = {"files": self.data["files"], "active": affected}
            atomic_json(self.path, recovery_data)
            touched = []
            try:
                for i, rel in enumerate(affected):
                    target = contained(self.version, rel)
                    touched.append((i, rel))
                    if (stage / str(i)).exists():
                        replace_file(stage / str(i), target)
                    elif target.exists():
                        target.unlink()
                next_data = {"files": self.data["files"], "active": list(plan)}
                atomic_json(self.path, next_data)
                self.data = next_data
            except Exception as exc:
                failures = []
                for i, rel in reversed(touched):
                    try:
                        target = contained(self.version, rel)
                        if existed[rel]:
                            replace_file(rollback / str(i), target)
                        elif target.exists():
                            target.unlink()
                    except Exception:
                        failures.append(rel)
                if failures:
                    raise RuntimeError(f"Operation failed; {len(failures)} files also need recovery. Close Roblox and use Restore all. Original backups were retained.") from exc
                atomic_json(self.path, self.data)
                raise RuntimeError("Could not update Roblox files. Close Roblox and try again. The previous files were restored.") from exc
        return len(affected)


def build_engine_type(core, base):
    class RobloxIntegration(base):
        KEYS = {"cursor": "roblox_cursor_pack", "ui": "ui_pack", "sky": "sky_pack", "font": "font_pack"}

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.operation_lock = threading.RLock()

        def find_latest_version_folder(self):
            root = Path(core.ROBLOX_VERSIONS_DIR)
            if not root.is_dir():
                return None
            candidates = [p for p in root.glob("version-*")
                          if (p / "RobloxPlayerBeta.exe").is_file() and (p / "content").is_dir()]
            if not candidates:
                return None
            # The registered player is authoritative when it points to a valid installation.
            if core.IS_WINDOWS:
                try:
                    import winreg
                    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Classes\roblox-player\shell\open\command") as key:
                        command = winreg.QueryValueEx(key, "")[0]
                    paths = re.findall(r'"([^\"]+\.exe)"', command, re.I)
                    for path in paths:
                        folder = Path(os.path.expandvars(path)).parent
                        if folder in candidates:
                            return str(folder)
                except OSError:
                    pass
            return str(max(candidates, key=lambda p: (p / "RobloxPlayerBeta.exe").stat().st_mtime_ns))

        def _plan(self, desired, version, journal):
            plan = {}
            ui = desired.get("ui_pack")
            if ui:
                root = Path(self.ui_store.pack_dir(ui))
                folders = sorted((p for p in root.rglob("*") if p.is_dir() and p.name.lower() == "textures"), key=lambda p: len(p.parts))
                if not folders:
                    raise ValueError("This UI pack needs a textures folder.")
                for source in folders[0].rglob("*"):
                    if source.is_file():
                        rel = "content/textures/" + source.relative_to(folders[0]).as_posix()
                        contained(version, rel)
                        plan[rel] = source
            sky = desired.get("sky_pack")
            if sky:
                files = self.sky_store.find_files(sky, (".tex",))
                if not files or not Path(version, self.SKY_REL).is_dir():
                    raise ValueError("No compatible skybox files or Roblox sky folder were found.")
                for name, source in files.items():
                    plan[Path(self.SKY_REL, name).as_posix()] = Path(source)
            font = desired.get("font_pack")
            if font:
                files = self.font_store.find_files(font, (".otf", ".ttf"))
                families = Path(version, "content", "fonts", "families")
                if not files or not families.is_dir():
                    raise ValueError("No compatible font file or Roblox font folder was found.")
                name, source = next(iter(files.items()))
                plan[f"content/fonts/{name}"] = Path(source)
                count = 0
                for item in families.glob("*.json"):
                    rel = item.relative_to(version).as_posix()
                    raw = journal.original_bytes(rel)
                    if raw is None:
                        continue
                    data = json.loads(raw)
                    for face in data.get("faces", []):
                        face["assetId"] = f"rbxasset://fonts/{name}"
                    plan[rel] = json.dumps(data, indent=2).encode("utf-8")
                    count += 1
                if not count:
                    raise ValueError("Roblox has no font families to update.")
            cursor = desired.get("roblox_cursor_pack")
            if cursor:
                mapping, locked = self._get_roblox_cursor_mapping(cursor)
                if not mapping and not locked:
                    raise ValueError("No compatible PNG cursors were found in this pack.")
                if not self.cursor_folder(version):
                    raise ValueError("The Roblox cursor folder is missing.")
                destinations = {f"content/textures/Cursors/KeyboardMouse/{n}": p for n, p in mapping.items()}
                if locked:
                    destinations["content/textures/MouseLockedCursor.png"] = locked
                for rel, source in destinations.items():
                    png, error = self._prepare_png(source)
                    if png is None:
                        raise ValueError(error)
                    output = BytesIO()
                    png.save(output, "PNG")
                    plan[rel] = output.getvalue()
            return plan

        def apply_selection(self, kind, name):
            with self.operation_lock:
                version = self.find_latest_version_folder()
                if not version:
                    raise ValueError("Roblox Player was not found. Install and launch Roblox once, then try again.")
                desired = dict(self.cfg)
                desired[self.KEYS[kind]] = name
                journal = BackupJournal(version, core.ROBLOX_BACKUP_DIR)
                plan = self._plan(desired, version, journal)
                journal.commit(plan)
                self.cfg[self.KEYS[kind]] = name
                core.save_config(self.cfg)
                self._status(f"{name or kind.title() + ' removed'} · restart Roblox to see changes", "accent")
                return True

        def apply_roblox_cursors(self, name):
            return self.apply_selection("cursor", name)

        def apply_ui(self, name, reapply_cursors=True):
            return self.apply_selection("ui", name)

        def apply_sky(self, name):
            return self.apply_selection("sky", name)

        def apply_fonts(self, name):
            return self.apply_selection("font", name)

        def restore_all_roblox(self):
            with self.operation_lock:
                version = self.find_latest_version_folder()
                if not version:
                    raise ValueError("Roblox Player was not found.")
                journal = BackupJournal(version, core.ROBLOX_BACKUP_DIR)
                count = journal.commit({})
                for key in self.KEYS.values():
                    self.cfg[key] = None
                core.save_config(self.cfg)
                self._status(f"Restored Roblox · {count} files · restart Roblox", "accent")
                return True

        def reapply_all(self):
            with self.operation_lock:
                if not any(self.cfg.get(key) for key in self.KEYS.values()):
                    return
                version = self.find_latest_version_folder()
                if not version:
                    raise ValueError("Roblox Player was not found; saved mods have been kept.")
                journal = BackupJournal(version, core.ROBLOX_BACKUP_DIR)
                journal.commit(self._plan(self.cfg, version, journal))
                self._status("Saved Roblox mods applied · restart Roblox", "accent")

        def _watch_loop(self):
            while not self._stop_event.wait(5):
                try:
                    current = self.find_latest_version_folder()
                    if current and current != self._last_version:
                        if self._last_version is not None:
                            self.reapply_all()
                        self._last_version = current
                except Exception as exc:
                    core.log_exc("ROBLOX", str(exc))
                    self._status(str(exc), "warn")
                    # Retry next poll, including after a half-installed version finishes.

    return RobloxIntegration
