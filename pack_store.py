"""Validated, atomic folder/ZIP imports. No system changes happen in this module."""
import json
import logging
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import tempfile
import threading
import zipfile

MAX_FILES = 10000
MAX_BYTES = 512 * 1024 * 1024
_config_lock = threading.RLock()


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with _config_lock:
        fd, temporary = tempfile.mkstemp(prefix=".write-", dir=path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(value, stream, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)


def contained(root, relative):
    """Reject Windows aliases as well as traversal, on every host."""
    text = str(relative).replace("\\", "/")
    pieces = PurePosixPath(text).parts
    reserved = {"con", "prn", "aux", "nul"} | {f"{p}{n}" for p in ("com", "lpt") for n in range(1, 10)}
    if not pieces or text.startswith("/") or any(
        p in ("..", ".") or ":" in p or p.endswith((".", " "))
        or any(c in p for c in '<>"|?*') or any(ord(c) < 32 for c in p)
        or p.split(".")[0].lower() in reserved for p in pieces
    ):
        raise ValueError("The pack contains an unsupported file path.")
    root = Path(root).resolve()
    target = root.joinpath(*pieces)
    resolved = target.resolve()
    if not resolved.is_relative_to(root) or resolved == root:
        raise ValueError("A pack file points outside its destination.")
    return target


class PackStore:
    def __init__(self, root, tag):
        self.root = str(root)
        self.tag = tag
        Path(root).mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def list_packs(self):
        return sorted(p.name for p in Path(self.root).iterdir()
                      if p.is_dir() and not p.name.startswith(".") and not p.is_symlink())

    def _unique_name(self, name):
        candidate, i = name, 2
        while Path(self.root, candidate).exists():
            candidate = f"{name} ({i})"
            i += 1
        return candidate

    def _validate(self, directory):
        files = [p for p in Path(directory).rglob("*") if p.is_file()]
        extensions = {"CURSOR": (".cur", ".ani"), "ROBLOX-CUR": (".png",),
                      "SKY": (".tex",), "FONT": (".ttf", ".otf")}
        if self.tag == "UI":
            valid = any("textures" in [part.lower() for part in p.relative_to(directory).parts[:-1]] for p in files)
            message = "Choose a UI pack containing a textures folder (usually inside content)."
        else:
            allowed = extensions.get(self.tag, ())
            valid = any(p.suffix.lower() in allowed for p in files)
            message = f"This section needs {' / '.join(allowed)} files. Choose the matching pack section."
        if not valid:
            raise ValueError(message)

    def import_pack(self, source, progress=None):
        source = Path(source).resolve()
        if not source.exists():
            raise ValueError("That file or folder is no longer available.")
        with self._lock:
            with tempfile.TemporaryDirectory(prefix=".import-", dir=self.root) as temporary:
                stage = Path(temporary, "pack")
                stage.mkdir()
                if source.is_file() and source.suffix.lower() == ".zip":
                    self._extract(source, stage, progress)
                    name = source.stem
                elif source.is_dir():
                    if Path(self.root).resolve().is_relative_to(source):
                        raise ValueError("Choose a pack folder, rather than the entire Cursor Mods library.")
                    target = stage
                    if self.tag == "UI" and source.name.lower() == "textures":
                        target = stage / "textures"
                        target.mkdir()
                    self._copy_folder(source, target, progress)
                    name = source.name
                elif source.is_file() and ((self.tag == "FONT" and source.suffix.lower() in (".ttf", ".otf"))
                                          or (self.tag == "ROBLOX-CUR" and source.suffix.lower() == ".png")):
                    if source.stat().st_size > MAX_BYTES:
                        raise ValueError("This file exceeds the 512 MB import limit.")
                    shutil.copy2(source, contained(stage, source.name))
                    name = source.stem
                else:
                    raise ValueError("Choose a ZIP archive or a pack folder.")
                self._validate(stage)
                name = self._unique_name(name or "Untitled pack")
                destination = contained(self.root, name)
                os.replace(stage, destination)
                return name

    def _extract(self, source, stage, progress):
        try:
            archive = zipfile.ZipFile(source)
        except zipfile.BadZipFile as exc:
            raise ValueError("This ZIP is damaged or incomplete. Download it again.") from exc
        with archive:
            entries = archive.infolist()
            if len(entries) > MAX_FILES or sum(e.file_size for e in entries) > MAX_BYTES:
                raise ValueError("This ZIP exceeds the import limit (10,000 files / 512 MB).")
            seen = set()
            for entry in entries:
                contained(stage, entry.filename)
                key = entry.filename.replace("\\", "/").rstrip("/").casefold()
                if key in seen:
                    raise ValueError("This ZIP has duplicate file names. Repack it and try again.")
                seen.add(key)
                if stat.S_ISLNK(entry.external_attr >> 16) or entry.flag_bits & 1:
                    raise ValueError("Linked or password-protected ZIP files are not supported.")
            total = 0
            for i, entry in enumerate(entries):
                destination = contained(stage, entry.filename)
                if entry.is_dir():
                    destination.mkdir(parents=True, exist_ok=True)
                    continue
                destination.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(entry) as src, destination.open("wb") as dst:
                    while chunk := src.read(1024 * 1024):
                        total += len(chunk)
                        if total > MAX_BYTES:
                            raise ValueError("The unpacked ZIP exceeds 512 MB.")
                        dst.write(chunk)
                if progress:
                    progress(f"Unpacking {i + 1} of {len(entries)} files…")

    def _copy_folder(self, source, stage, progress):
        count = size = 0
        for base, dirs, files in os.walk(source, followlinks=False):
            for name in dirs + files:
                path = Path(base, name)
                info = path.lstat()
                if path.is_symlink() or getattr(info, "st_file_attributes", 0) & 0x400:
                    raise ValueError("Pack folders must contain real files, rather than linked folders.")
            for name in files:
                path = Path(base, name)
                count += 1
                size += path.stat().st_size
                if count > MAX_FILES or size > MAX_BYTES:
                    raise ValueError("This folder exceeds the import limit (10,000 files / 512 MB).")
                dest = contained(stage, path.relative_to(source))
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, dest)
                if progress:
                    progress(f"Copying {count} files…")

    def import_files(self, paths):
        if len(paths) == 1:
            return self.import_pack(paths[0])
        if not paths or self.tag != "ROBLOX-CUR":
            raise ValueError("Choose one pack, or multiple PNG cursor files.")
        sources = [Path(p).resolve() for p in paths]
        if len(sources) > MAX_FILES or any(not p.is_file() or p.suffix.lower() != ".png" for p in sources):
            raise ValueError("Choose PNG cursor files.")
        if len({p.name.casefold() for p in sources}) != len(sources):
            raise ValueError("These cursor files have duplicate names.")
        if sum(p.stat().st_size for p in sources) > MAX_BYTES:
            raise ValueError("These cursor files exceed the 512 MB import limit.")
        with self._lock, tempfile.TemporaryDirectory(prefix=".import-", dir=self.root) as temporary:
            stage = Path(temporary, "pack")
            stage.mkdir()
            for source in sources:
                shutil.copy2(source, contained(stage, source.name))
            self._validate(stage)
            name = self._unique_name("Cursor pack")
            os.replace(stage, contained(self.root, name))
            return name

    def pack_dir(self, name):
        return str(contained(self.root, name))

    def effective_dir(self, name):
        current = Path(self.pack_dir(name))
        for _ in range(12):
            entries = list(current.iterdir())
            if len(entries) == 1 and entries[0].is_dir():
                current = entries[0]
            else:
                break
        return str(current)

    def find_files(self, name, extensions):
        result = {}
        base = Path(self.pack_dir(name))
        for path in sorted(base.rglob("*"), key=lambda p: (len(p.parts), str(p).casefold())):
            if path.is_file() and path.suffix.lower() in extensions:
                if path.name.lower() not in {key.lower() for key in result}:
                    result[path.name] = str(path)
        return result

    def delete_pack(self, name):
        with self._lock:
            dest = Path(self.pack_dir(name)).resolve()
            if dest.parent != Path(self.root).resolve():
                raise ValueError("Only a pack directly inside the library can be removed.")
            if dest.exists():
                shutil.rmtree(dest)
