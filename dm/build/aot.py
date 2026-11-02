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
import shutil
import subprocess
import tempfile
from pathlib import Path

from dm.build.models import AOT_CACHE_FORMAT, AotArtifact, BuildError, PreparedGame

MANIFEST = "manifest.json"
def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb", buffering=0) as file:
        while chunk := file.read(0x100_0000):
            digest.update(chunk)
    return digest.hexdigest()


def toolchain_identity() -> tuple[dict, dict[str, str]]:
    """Resolve once and pin the compiler and SDK passed to the recompiler."""
    env = dict(os.environ)
    named = env.get("CC", "").strip()
    words = ([named] if named and Path(named).is_file() else named.split())
    if not words:
        words = [next((p for name in ("cc", "gcc", "clang")
                       if (p := shutil.which(name))), "cc")]
    program = shutil.which(words[0])
    if not program:
        raise BuildError("aot", f"C compiler not found: {words[0]}")
    program = str(Path(program).resolve())
    if any(c.isspace() for c in program) and len(words) > 1:
        raise BuildError("aot", "3dsrecomp cannot represent a compiler path with spaces and arguments")
    command = [program, *words[1:]]
    version = subprocess.run([*command, "--version"], capture_output=True,
                             text=True, timeout=30, check=True).stdout
    env["CC"] = " ".join(command)
    sdk = env.get("SDKROOT", "")
    if platform.system() == "Darwin" and not sdk:
        sdk = subprocess.run(["/usr/bin/xcrun", "--show-sdk-path"],
                             capture_output=True, text=True, timeout=30,
                             check=True).stdout.strip()
    settings = {}
    if sdk:
        sdk_path = Path(sdk).resolve()
        if not sdk_path.is_dir():
            raise BuildError("aot", f"SDK directory missing: {sdk_path}")
        env["SDKROOT"] = str(sdk_path)
        settings = {p.name: _file_sha256(p) for p in
                    (sdk_path / "SDKSettings.json", sdk_path / "SDKSettings.plist")
                    if p.is_file()}
    identity = {"compiler": program, "sha256": _file_sha256(Path(program)),
                "args": words[1:], "version": version,
                "sdk": env.get("SDKROOT", ""), "sdk_settings": settings,
                "environment": {k: env.get(k, "") for k in
                    ("DEVELOPER_DIR", "MACOSX_DEPLOYMENT_TARGET", "CPATH",
                     "C_INCLUDE_PATH", "LIBRARY_PATH", "PATH")}}
    return identity, env


def fingerprint(prepared: PreparedGame, zakuro_stamp: str, compiler_bin: Path,
                toolchain: dict) -> str:
    payload = {"format": AOT_CACHE_FORMAT,
               "rom": _file_sha256(prepared.working_source),
               "host": zakuro_stamp, "recompiler": _file_sha256(compiler_bin),
               "toolchain": toolchain, "arch": platform.machine()}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def obtain_aot(flow, prepared: PreparedGame, zakuro_stamp: str) -> AotArtifact:
    request = flow.request
    compiler_bin = request.recompiler_bin or (request.root / "vendors/3dsrecomp/target/release/3dsrecomp")
    if not compiler_bin.is_file():
        raise BuildError("aot", f"the AOT compiler is missing at {compiler_bin}")
    toolchain, build_env = toolchain_identity()
    host = request.zakuro_bin or flow.resolve_zakuro()
    fingerprint_value = fingerprint(prepared, _file_sha256(host), compiler_bin, toolchain)
    cache_root = prepared.build_dir / "aot"
    cache_root.mkdir(parents=True, exist_ok=True)
    with (cache_root / f"{fingerprint_value}.lock").open("a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        return _obtain_locked(flow, prepared, compiler_bin, fingerprint_value, toolchain, build_env)


def _obtain_locked(flow, prepared: PreparedGame, compiler_bin: Path, fingerprint_value: str,
                   toolchain: dict, build_env: dict[str, str]) -> AotArtifact:
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
            if (isinstance(cached, dict) and cached.get("format") == AOT_CACHE_FORMAT
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
                command, env={**build_env, "HOME": str(isolated_home)}, timeout=None)
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
                "format": AOT_CACHE_FORMAT,
                "toolchain": toolchain,
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
