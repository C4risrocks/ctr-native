# Copyright (c) 2026 ctr-native contributors — MIT license.
"""The AOT stage: fingerprint, isolated build, cache and atomic publish.

`3dsrecomp build <rom>` is invoked through arguments (no shell) with an
isolated working HOME, so the build never leans on the global `.hints`; the
result is published into the shared install place atomically and cached under
`<title_id>_build/aot/<fingerprint>/`, gated by a versioned manifest.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import tempfile
from pathlib import Path

from dm.build.models import AotArtifact, BuildError, PreparedGame

MANIFEST = "manifest.json"
_AOT_CACHE_FORMAT_CHUNK = b"ctr-native-aot-cache-v1\x00"


def _file_stamp(path: Path) -> str:
    stat = path.stat()
    return f"{stat.st_size}:{stat.st_mtime_ns}"


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb", buffering=0) as file:
        while chunk := file.read(0x100_0000):
            digest.update(chunk)
    return digest.hexdigest()


def fingerprint(prepared: PreparedGame, zakuro_stamp: str, compiler_bin: Path) -> str:
    """Prepared ROM + both tool stamps + compiler identity + arch + cache format."""
    digest = hashlib.sha256()
    digest.update(_AOT_CACHE_FORMAT_CHUNK)
    digest.update(_file_sha256(prepared.working_source).encode())
    digest.update(zakuro_stamp.encode())
    digest.update(_file_stamp(compiler_bin).encode())
    digest.update(platform.machine().encode())
    return digest.hexdigest()


def obtain_aot(flow, prepared: PreparedGame, zakuro_stamp: str) -> AotArtifact:
    request = flow.request
    library_installed = Path.home() / "Library/Application Support/3dsrecomp" / \
        f"{prepared.title_id}.dylib"
    hints_installed = library_installed.with_suffix(".hints")
    compiler_bin = request.recompiler_bin
    explicit = compiler_bin is not None or request.rebuild_aot
    if compiler_bin is None:
        compiler_bin = request.root / "vendors/3dsrecomp/target/release/3dsrecomp"
    if not compiler_bin.is_file():
        if library_installed.is_file():
            flow.stage_end("reused the installed AOT library")
            return AotArtifact(title_id=prepared.title_id, dylib=library_installed,
                               hints_path=hints_installed if hints_installed.is_file() else None,
                               fingerprint="", reused=True)
        raise BuildError("aot", f"the AOT compiler is missing at {compiler_bin}")
    cache_root = prepared.build_dir / "aot"
    fingerprint_value = fingerprint(prepared, zakuro_stamp, compiler_bin)
    cache_dir = cache_root / fingerprint_value
    manifest = cache_dir / MANIFEST

    reused = False
    compiled = False
    have_cache = manifest.is_file() and not request.rebuild_aot
    have_installed = library_installed.is_file() and not request.rebuild_aot
    if not explicit and have_installed:
        flow.stage_end("reused the installed AOT library")
        return AotArtifact(title_id=prepared.title_id, dylib=library_installed,
                           hints_path=hints_installed if hints_installed.is_file() else None,
                           fingerprint=fingerprint_value, reused=True)
    if have_cache:
        try:
            cached = json.loads(manifest.read_text())
            cached_dylib = cache_dir / f"{prepared.title_id}.dylib"
            if cached.get("fingerprint") == fingerprint_value and cached_dylib.is_file():
                reused = True
                if not library_installed.is_file():
                    _publish_atomic(cached_dylib, library_installed)
                flow.say(f"reused cached AOT library (fingerprint {fingerprint_value[:12]}…)")
        except (OSError, ValueError):
            reused = False
    if not reused:
        flow.say(f"building the AOT library with 3dsrecomp (fingerprint {fingerprint_value[:12]}…)")
        with tempfile.TemporaryDirectory(prefix="ctr-native-aot-home-") as home:
            isolated_home = Path(home)
            command = [str(compiler_bin), "build", str(prepared.working_source)]
            completed = flow.runner(
                command, env={**os.environ, "HOME": str(isolated_home)}, timeout=None)
            if completed.returncode != 0:
                tail = ((completed.stdout or "") + (completed.stderr or ""))[-800:]
                raise BuildError("aot", f"the AOT compiler failed:\n{tail}")
            built = isolated_home / "Library/Application Support/3dsrecomp" / \
                f"{prepared.title_id}.dylib"
            if not built.is_file():
                raise BuildError("aot", "the AOT compiler produced no library in its isolated home")
            cache_dir.mkdir(parents=True, exist_ok=True)
            _publish_atomic(built, cache_dir / f"{prepared.title_id}.dylib")
            manifest.write_text(json.dumps({
                "format": "aot-cache-v1",
                "title_id": prepared.title_id,
                "fingerprint": fingerprint_value,
                "arch": platform.machine(),
                "library_sha256": _file_sha256(cache_dir / f"{prepared.title_id}.dylib"),
            }, sort_keys=True, indent=1) + "\n")
            compiled = True
            library_installed.parent.mkdir(parents=True, exist_ok=True)
            _publish_atomic(cache_dir / f"{prepared.title_id}.dylib", library_installed)
            flow.stage_end(f"AOT library compiled ({library_installed.stat().st_size:,} bytes) and cached")
    return AotArtifact(
        title_id=prepared.title_id,
        dylib=library_installed,
        hints_path=hints_installed if hints_installed.is_file() else None,
        fingerprint=fingerprint_value,
        reused=reused,
        compiled=compiled,
    )


def _publish_atomic(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as partial:
        partial_path = Path(partial.name)
    try:
        with open(source, "rb", buffering=0) as reader, open(partial_path, "wb") as writer:
            while chunk := reader.read(0x100_0000):
                writer.write(chunk)
        os.replace(partial_path, target)
    finally:
        partial_path.unlink(missing_ok=True)
