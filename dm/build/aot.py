# Copyright (c) 2026 ctr-native contributors — MIT license.
"""The AOT stage: fingerprint, isolated build, cache and atomic publish.

`3dsrecomp build <rom>` is invoked through arguments (no shell) with an
isolated working HOME, so the build never leans on the global `.hints`; the
result is kept independently of the global installed library under
`<title_id>_build/aot/<fingerprint>/`, gated by a versioned manifest.
"""
from __future__ import annotations

import fcntl
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
    compiler_bin = request.recompiler_bin or (request.root / "vendors/3dsrecomp/target/release/3dsrecomp")
    if not compiler_bin.is_file():
        raise BuildError("aot", f"the AOT compiler is missing at {compiler_bin}")
    fingerprint_value = fingerprint(prepared, zakuro_stamp, compiler_bin)
    cache_root = prepared.build_dir / "aot"
    cache_root.mkdir(parents=True, exist_ok=True)
    with (cache_root / f"{fingerprint_value}.lock").open("a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        return _obtain_locked(flow, prepared, compiler_bin, fingerprint_value)


def _obtain_locked(flow, prepared: PreparedGame, compiler_bin: Path, fingerprint_value: str) -> AotArtifact:
    request = flow.request
    cache_dir = prepared.build_dir / "aot" / fingerprint_value
    manifest = cache_dir / MANIFEST
    cached_dylib = cache_dir / f"{prepared.title_id}.dylib"
    reused = False
    compiled = False
    have_cache = manifest.is_file() and not request.rebuild_aot
    if have_cache:
        try:
            cached = json.loads(manifest.read_text())
            if (isinstance(cached, dict) and cached.get("format") == "aot-cache-v1"
                    and cached.get("title_id") == prepared.title_id
                    and cached.get("arch") == platform.machine()
                    and cached.get("fingerprint") == fingerprint_value
                    and cached_dylib.is_file() and not cached_dylib.is_symlink()
                    and cached.get("library_sha256") == _file_sha256(cached_dylib)):
                reused = True
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
            flow.stage_end(f"AOT library compiled ({cached_dylib.stat().st_size:,} bytes) and cached")
    if reused:
        flow.stage_end("reused verified cached AOT library")
    return AotArtifact(
        title_id=prepared.title_id,
        dylib=cached_dylib,
        hints_path=None,
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
