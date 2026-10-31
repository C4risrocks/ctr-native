"""Known per-app data locations and conservative access to player files."""
from __future__ import annotations

import os
import stat
import sys
import subprocess
from dataclasses import dataclass
from pathlib import Path


class DetectionError(OSError):
    """The runtime state could not be established; callers must not delete."""


@dataclass(frozen=True)
class UserData:
    app: Path

    @property
    def sandbox(self) -> Path:
        return self.app.with_name(self.app.name + ".ctr-native")

    @property
    def legacy(self) -> Path:
        return self.app / "Contents/MacOS/sandbox"

    @property
    def roots(self) -> tuple[Path, Path]:
        return self.sandbox, self.legacy

    @property
    def log_dirs(self) -> tuple[Path, ...]:
        return tuple(path for root in self.roots for path in
                     (root / "home/Library/Application Support/zakuro", root))

    @property
    def pipeline_dirs(self) -> tuple[Path, ...]:
        return tuple(root / "home/Library/Caches/zakuro/pipelines" for root in self.roots)

    @property
    def old_cache_dirs(self) -> tuple[Path, ...]:
        return tuple(root / "home/Library/Application Support/zakuro/cache" for root in self.roots)


def canonical_path(path: Path) -> Path:
    """Normalize macOS system aliases without following player symlinks."""
    absolute = path.absolute()
    if sys.platform == "darwin":
        for alias in (Path("/var"), Path("/tmp")):
            if absolute == alias or absolute.is_relative_to(alias):
                return Path("/private") / absolute.relative_to("/")
    return absolute


def safe_path(path: Path) -> bool:
    """Reject symlinks at every existing level, including directory aliases."""
    absolute = canonical_path(path)
    return not any(part.is_symlink() for part in (absolute, *absolute.parents))


def open_regular(path: Path):
    """Open a regular file without following a symlink at any path component.

    Directory descriptors keep traversal confined even if another process
    renames a parent while the file is opened.
    """
    absolute = canonical_path(path)
    flags = os.O_RDONLY | os.O_NOFOLLOW
    directory = os.open(absolute.anchor, flags | os.O_DIRECTORY)
    try:
        for name in absolute.parts[1:-1]:
            next_directory = os.open(name, flags | os.O_DIRECTORY, dir_fd=directory)
            os.close(directory)
            directory = next_directory
        descriptor = os.open(absolute.name, flags | os.O_NONBLOCK, dir_fd=directory)
    finally:
        os.close(directory)
    if not stat.S_ISREG(os.fstat(descriptor).st_mode):
        os.close(descriptor)
        raise OSError(f"not a regular file: {path}")
    return os.fdopen(descriptor, "rb")


def active_files() -> set[Path]:
    """Read lsof's NUL-delimited name fields, preserving whitespace in paths."""
    try:
        pids = subprocess.run(["/usr/bin/pgrep", "-f", "MacOS/zakuro-host"],
                              capture_output=True, timeout=10, check=False)
        if pids.returncode == 1:
            return set()
        if pids.returncode != 0:
            raise DetectionError("cannot detect running zakuro processes")
        files: set[Path] = set()
        for pid in pids.stdout.split():
            if not pid.isdigit():
                raise DetectionError("invalid process identifier")
            result = subprocess.run(["/usr/sbin/lsof", "-Fpn0", "-p", pid.decode("ascii")],
                                    capture_output=True, timeout=10, check=False)
            if result.returncode:
                raise DetectionError("cannot inspect a running zakuro process")
            for field in result.stdout.split(b"\0"):
                field = field.lstrip(b"\n")
                if field.startswith(b"n/"):
                    files.add(Path(os.fsdecode(field[1:])))
        return files
    except (OSError, subprocess.SubprocessError) as error:
        raise DetectionError("cannot establish runtime activity; no files may be removed") from error


def runtime_in_use(app: Path, files: set[Path] | None = None) -> bool:
    """True if the app executable or any of its data is open; errors fail closed."""
    observed = active_files() if files is None else files
    locations = (canonical_path(app), *(canonical_path(root) for root in UserData(app).roots))
    observed = {canonical_path(path) for path in observed}
    return any(path == root or path.is_relative_to(root) for path in observed for root in locations)


def cache_size(path: Path) -> int:
    """Count regular cache bytes; refuse an entire tree containing symlinks."""
    if not safe_path(path):
        raise OSError(f"unsafe cache path: {path}")
    if path.is_file():
        with open_regular(path) as file:
            return os.fstat(file.fileno()).st_size
    total = 0
    for entry in path.iterdir():
        total += cache_size(entry)
    return total


def remove_cache(path: Path) -> None:
    """Remove a preflighted cache tree without following links at deletion."""
    absolute = canonical_path(path)
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_DIRECTORY
    directory = os.open(absolute.anchor, flags)

    def remove(parent: int, name: str) -> None:
        mode = os.stat(name, dir_fd=parent, follow_symlinks=False).st_mode
        if stat.S_ISREG(mode):
            os.unlink(name, dir_fd=parent)
        elif stat.S_ISDIR(mode):
            child = os.open(name, flags, dir_fd=parent)
            try:
                for entry in os.listdir(child):
                    remove(child, entry)
            finally:
                os.close(child)
            os.rmdir(name, dir_fd=parent)
        else:
            raise OSError("cache contains a symlink or special file")

    try:
        for name in absolute.parts[1:-1]:
            next_directory = os.open(name, flags, dir_fd=directory)
            os.close(directory)
            directory = next_directory
        remove(directory, absolute.name)
    finally:
        os.close(directory)
