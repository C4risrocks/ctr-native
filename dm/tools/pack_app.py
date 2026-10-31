# Copyright (c) 2026 ctr-native contributors — MIT license.
"""A Mac app of one 3DS game: launches the native zakuro host with the game.

The generated bundle (mirroring nxnative's `pack_app.py`):

    <name>.app/
      Info.plist                 CFBundleName from the SMDH title, icon, id, versions
      ctr-native                 the double-clickable launcher (a tiny script)
      Resources/AppIcon.icns     the SMDH icon, through macOS's own sips + iconutil
      Resources/game/            the AOT library (zakuro host), self-contained
      Contents/MacOS/zakuro-host the host binary itself, for the zakuro host

    <name>.app.ctr-native/       the data sandbox (a SIBLING folder: a codesign
                                 seal over Contents/ refuses the sandbox's
                                 databases, so data beside the app is the
                                 industry pattern): settings, saves, mods,
                                 shader caches and logs, isolated per game.

Reusing a build: `ctr-native.key` records the packed inputs (ROM hash, zakuro
binary stamp, profile pin, icon hash); while it matches and the bundle exists,
nothing is rewritten — the sandbox, and therefore the save, is never touched.
Console keys never enter a bundle and no game content enters git (.gitignore);
the sandbox holds user data only (saves, logs, shader caches).
"""

from __future__ import annotations

import ctypes
import hashlib
import os
import sys
import tempfile
import plistlib
import shutil
import subprocess  # codesign/iconutil/sips: macOS tools, fixed paths, no shell
import time
import zlib
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any
from collections.abc import Callable

from .user_data import UserData, open_regular, safe_path

LAUNCHER_NAME = "ctr-native"
KEY_NAME = "ctr-native.key"
ICON_SIZES = (16, 32, 64, 128, 256, 512)


class PackError(Exception):
    """A bundle that cannot be built or refreshed."""


# bundle layout helpers ------------------------------------------------------

def contents_of(app: Path) -> Path:
    return app / "Contents"


def sandbox_of(app: Path) -> dict[str, Path]:
    """Where this game's data lives: a sibling folder of the app, never inside
    it. Inside `Contents/` the host resolves its paths under `$HOME`
    (the launcher runs it with HOME pointed at the sandbox), but a codesign
    seal over `Contents/` refuses the sandbox's databases, and the industry
    pattern is data beside the app: the bundle holds code only, the sandbox
    holds settings, saves, mods and logs.
    The launcher runs zakuro with HOME pointed at the sandbox: everything
    lands under `sandbox/home/Library/...` and never touches your global
    configuration."""
    sandbox = UserData(app).sandbox
    home = sandbox / "home"
    app_data = home / "Library/Application Support/zakuro"
    return {
        "sandbox": sandbox,
        "home": home,
        "user": app_data,
        "config": app_data / "config",
        "nand": app_data / "nand",
        "sdmc": app_data / "sdmc",
        "log": app_data,
        "cache": home / "Library/Caches/zakuro/pipelines",
    }


def ensure_sandbox(app: Path) -> None:
    for path in sandbox_of(app).values():
        if not safe_path(path):
            raise PackError(f"linked sandbox path: {path}")
        if path.name != "zakuro.log":  # the log is a file, its folder is the data root
            path.mkdir(parents=True, exist_ok=True)


def write_atomic(path: Path, payload: bytes) -> None:
    """tmp + rename: a killed build never leaves half a file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(payload)
    tmp.replace(path)


def stage_file(path: Path, payload: bytes, only_changed: bool = True) -> bool:
    """Write through a temp when the content differs; report whether anything was written."""
    if only_changed and path.exists() and path.read_bytes() == payload:
        return False
    write_atomic(path, payload)
    return True


# content builders -----------------------------------------------------------

def launcher_text(host_bin: Path, rom_path: Path, sandbox_dir: Path,
                  language: str, tool_version: str,
                  recompiled_dylib: Path | None = None,
                  scale: int | None = None) -> str:
    """The launcher script: baked absolute paths, then exec.

    `open` (and Finder) may hand the launcher a relative argv[0]; a cwd-side
    sandbox would silently land the host in its *global* configuration
    instead of this app's own. nxnative bakes paths the same way: a moved
    bundle rebuilds, the game's data does not follow it.

    The zakuro host (native Rust runtime, AOT): bundled binary + the game's
    recompiled library + `--data`/`HOME` inside the bundle; Vulkan through the
    brew Vulkan loader, whose friend MoltenVK ships its own ICD.
    """
    def quote(value: Any) -> str:
        return "'" + str(value).replace("'", "'\\''") + "'"

    header = [
        "#!/bin/bash",
        "# Generated by ctr-native — do not edit; rebuild instead.",
        f"# host: zakuro · language: {language} · toolkit: {tool_version}",
        f"HOST_BIN={quote(host_bin)}",
        f"ROM={quote(rom_path)}",
        f"export HOME={quote(sandbox_dir / 'home')}",
        'mkdir -p "$HOME"',
    ]
    scale_arg = (" --scale " + str(scale)) if scale else ""
    lines = [*header,
        'DYLD_LIBRARY_PATH="/opt/homebrew/lib'
        '${DYLD_LIBRARY_PATH:+:$DYLD_LIBRARY_PATH}"',
        "export DYLD_LIBRARY_PATH",
        f'RECOMPILED={quote(recompiled_dylib)}',
        'exec "$HOST_BIN" --recompiled "$RECOMPILED"'
        f"{scale_arg} --language {language} \"$ROM\"",
    ]
    return "\n".join([*lines, ""])


def info_plist(app_name: str, bundle_id: str, version: str) -> bytes:
    data: dict[str, Any] = {
        "CFBundleDevelopmentRegion": "English",
        "CFBundleExecutable": LAUNCHER_NAME,
        "CFBundleIconFile": "AppIcon",
        "CFBundleIdentifier": bundle_id,
        "CFBundleInfoDictionaryVersion": "6.0",
        "CFBundleName": app_name,
        "CFBundleDisplayName": app_name,
        "CFBundlePackageType": "APPL",
        "CFBundleShortVersionString": version,
        "CFBundleVersion": version,
        "LSMinimumSystemVersion": "11.0",
        "NSHighResolutionCapable": True,
        "CFBundleAllowMixedLocalizations": True,
    }
    return plistlib.dumps(data)


def schema_hash(items: dict[str, str]) -> str:
    digest = hashlib.sha256()
    for key in sorted(items):
        digest.update(key.encode())
        digest.update(b"=")
        digest.update(items[key].encode())
        digest.update(b"\x00")
    return digest.hexdigest()


def app_bundle_id(title_id: str) -> str:
    return f"org.ctrnative.{title_id.lower()}"


# icon -----------------------------------------------------------------------

def app_name_from_smdh(long_title: str) -> str:
    """Filesystem-safe app name (Finder refuses ':' inside file names)."""
    cleaned = long_title.strip().replace(":", " -").replace("/", "-")[:120].strip() or "Game"
    return cleaned


class IconSet:
    """SMDH icon -> AppIcon.icns with the macOS builtins sips + iconutil only.

    The 48x48 SMDH icon is written as a PNG with the standard-library zlib
    (no dependencies), then sips resamples the sizes iconutil needs and the
    .icns gets built. Both tools ship with macOS, so icon work adds nothing
    external to the pipeline.
    """

    def __init__(self, iconset_dir: Path) -> None:
        self.iconset_dir = iconset_dir

    def refresh(self, pixels: list[tuple[int, int, int, int]], width: int, height: int) -> Path | None:
        iconset_dir = self.iconset_dir.with_name(self.iconset_dir.name + ".iconset")
        iconset_dir.mkdir(parents=True, exist_ok=True)
        for stale_png in iconset_dir.glob("*.png"):
            stale_png.unlink()
        source = iconset_dir / "icon_512x512.png"
        source.write_bytes(png_bytes(pixels, width, height, upsample=True))
        # macOS 26's IconServices composes the running window's icon from
        # these PNGs, and ImageIO faulted (EXC_ARM_DA_ALIGN inside
        # PNGReadPlugin::InitializePluginData) reading a custom-encoded
        # one: re-encode the source through sips, so every size of the set
        # is Apple's own encoder's bytes.
        apple_source = source.with_name("icon_512x512.png.sips.png")
        if resample(source, 512, apple_source):
            apple_source.replace(source)
        results = []
        for size in ICON_SIZES:
            target = iconset_dir / f"icon_{size}x{size}.png"
            if not resample(source, size, target):
                results = []
                break
            results.append(target)
        if not results:
            return None
        icns = self.iconset_dir.parent.parent / "AppIcon.icns"
        icns_tmp = icns.with_suffix(".tmp.icns")
        try:
            subprocess.run(
                ["/usr/bin/iconutil", "-c", "icns", str(iconset_dir), "-o", str(icns_tmp)],
                check=True, capture_output=True,
            )
        except (OSError, subprocess.SubprocessError) as error:
            raise PackError(f"iconutil failed: {error}") from error
        icns_tmp.replace(icns)
        return icns if icns.exists() else None


def png_bytes(pixels: list[tuple[int, int, int, int]], width: int, height: int, upsample: bool = False) -> bytes:
    """A minimal RGBA PNG writer (stdlib zlib); nearest-neighbour 48 -> 512 for crisp docks."""
    if upsample:
        pixels = resize_nearest(pixels, width, height, 512, 512)
        width = height = 512
    rows = bytearray()
    for y in range(height):
        rows.append(0)
        for (r, g, b, _a) in pixels[y * width : (y + 1) * width]:
            rows += bytes((r, g, b, 255))
    def chunk(kind: bytes, data: bytes) -> bytes:
        return len(data).to_bytes(4, "big") + kind + data + zlib.crc32(kind + data).to_bytes(4, "big")
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", width.to_bytes(4, "big") + height.to_bytes(4, "big") + bytes((8, 6, 0, 0, 0)))
            + chunk(b"IDAT", zlib.compress(bytes(rows), 9))
            + chunk(b"IEND", b""))


def resize_nearest(
    pixels: list[tuple[int, int, int, int]], width: int, height: int, new_width: int, new_height: int
) -> list[tuple[int, int, int, int]]:
    out: list[tuple[int, int, int, int]] = []
    for y in range(new_height):
        sy = min(y * height // new_height, height - 1)
        for x in range(new_width):
            sx = min(x * width // new_width, width - 1)
            out.append(pixels[sy * width + sx])
    return out


def resample(source: Path, size: int, target: Path) -> bool:
    try:
        subprocess.run(
            ["/usr/bin/sips", "-z", str(size), str(size), str(source), "--out", str(target)],
            check=True, capture_output=True,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return target.exists()


# signing --------------------------------------------------------------------

def sign_executable(path: Path, identity: str = "-") -> None:
    """Ad-hoc sign one Mach-O (the AMFI requirement for pinned executables).

    Non-recursive on purpose: `codesign --deep` would walk the bundle and hit
    the sandbox's save databases, so each embedded executable gets signed on
    its own and the bundle seal signs only the launcher.
    """
    result = subprocess.run(
        ["/usr/bin/codesign", "--force", "--sign", identity, str(path)],
        capture_output=True, text=True,
    )
    if result.returncode:
        raise PackError(f"codesigning {path.name} failed: {result.stderr.strip()}")


def codesign(app: Path, identity: str = "-", say: Callable[[str], None] | None = None) -> None:
    """Sign the bundle seal (launcher + Info.plist + resources) non-recursively."""
    cmd = ["/usr/bin/codesign", "--force", "--sign", identity, str(app)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode:
        raise PackError(f"codesign failed: {result.stderr.strip()}")
    if say:
        say(f"signed ({identity or 'ad-hoc'})")


# the pack stage -------------------------------------------------------------

@dataclass
class PackInputs:
    """Everything that decides whether a rebuild changes the bundle."""

    rom_path: Path
    whom: Path  # the bundle being packed (sandbox paths are part of its signature)
    host_bin: Path  # the zakuro host binary under the launcher
    host_version: str
    toolkit_version: str
    profile_hash: str
    icon_png: bytes | None
    launcher_args: list[str]  # extra argv for the launcher (e.g. env-style config)
    extra_files: list[tuple[Path, Path]] | None = None  # (source, target inside bundle)
    zakuro_bin: Path | None = None  # the zakuro binary path for the launcher
    recompiled_dylib: Path | None = None  # 3dsrecomp's per-game library (aot)
    scale: int | None = None  # zakuro's --scale (window factor)
    language: str = "en"
    host_bin_launcher: Path | None = None  # the BUNDLED host copy the launcher execs
    recompiled_dylib_launcher: Path | None = None  # the BUNDLED library copy

    @property
    def sandbox_dir(self) -> Path:
        return sandbox_of(self.whom)["sandbox"]


def effective_launcher(inputs: PackInputs) -> str:
    return launcher_text(
        inputs.host_bin_launcher or inputs.host_bin, inputs.rom_path, inputs.sandbox_dir,
        inputs.language, inputs.toolkit_version,
        inputs.recompiled_dylib_launcher or inputs.recompiled_dylib, inputs.scale,
    )


def verify_bundle(app: Path, required: list[Path]) -> None:
    """Validate the seal and each executable rather than trusting the reuse marker."""
    for relative in [Path("Contents/MacOS") / LAUNCHER_NAME, Path("Contents/Info.plist"), *required]:
        path = app / relative
        linked = any(one.is_symlink() for one in [path, *path.parents] if one == app or app in one.parents)
        if not path.is_file() or linked:
            raise PackError(f"missing or linked bundle dependency: {relative}")
    executables = [app / rel for rel in required if rel.suffix == ".dylib" or rel.name.endswith("-host")]
    for target in [*executables, app]:
        result = subprocess.run(["/usr/bin/codesign", "--verify", "--strict", str(target)],
                                capture_output=True, text=True)
        if result.returncode:
            raise PackError(f"signature verification failed: {target.name}: {result.stderr.strip()}")


def publish_bundle(candidate: Path, app: Path) -> None:
    """Publish on the same filesystem; an existing bundle is exchanged atomically."""
    if not app.exists():
        candidate.replace(app)
        return
    libc = ctypes.CDLL(None, use_errno=True)
    if sys.platform == "darwin":
        rename = libc.renamex_np
        rename.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
        result = rename(os.fsencode(candidate), os.fsencode(app), 2)  # RENAME_SWAP
    elif sys.platform.startswith("linux") and hasattr(libc, "renameat2"):
        rename = libc.renameat2
        rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        result = rename(-100, os.fsencode(candidate), -100, os.fsencode(app), 2)  # RENAME_EXCHANGE
    else:
        raise PackError("atomic directory exchange is unavailable on this platform")
    if result:
        raise OSError(ctypes.get_errno(), "atomic bundle exchange failed", str(app))


def rollback_migration(created: list[tuple[Path, int, int]]) -> None:
    """Undo only files this attempt created, never a replacement at the same path."""
    for path, device, inode in reversed(created):
        if safe_path(path) and path.exists():
            current = path.stat()
            if (current.st_dev, current.st_ino) == (device, inode):
                path.unlink()


def migrate_legacy(app: Path) -> list[tuple[Path, int, int]] | None:
    """Create missing data only; preserve the old bundle as an explicit legacy archive."""
    legacy = app / "Contents/MacOS/sandbox"
    if not legacy.exists():
        return None
    from .user_data import runtime_in_use

    if runtime_in_use(app):
        raise PackError("close the app before migrating its legacy sandbox")
    archive = app.with_name(app.name + ".ctr-native-legacy")
    if archive.exists() or not safe_path(archive):
        raise PackError(f"legacy archive already exists: {archive}; merge it manually first")
    root = sandbox_of(app)["sandbox"]
    if not safe_path(legacy):
        raise PackError("legacy sandbox contains links; manual migration is required")
    entries = list(legacy.rglob("*"))
    if any(not safe_path(path) for path in entries):
        raise PackError("legacy sandbox contains links; manual migration is required")
    files = [path for path in entries if path.is_file()]
    for path in entries:
        target = root / path.relative_to(legacy)
        if not safe_path(target) or (target.exists() and (path.is_file() or not target.is_dir())):
            raise PackError(f"sandbox collision: {target}; both copies were preserved")
    created: list[tuple[Path, int, int]] = []
    try:
        for source in files:
            target = root / source.relative_to(legacy)
            target.parent.mkdir(parents=True, exist_ok=True)
            with open_regular(source) as reader, target.open("xb") as writer:
                info = os.fstat(writer.fileno())
                created.append((target, info.st_dev, info.st_ino))
                shutil.copyfileobj(reader, writer)
            shutil.copystat(source, target)
    except (OSError, ValueError):
        rollback_migration(created)
        raise
    return created


def pack(
    app: Path,
    app_name: str,
    title_id: str,
    version: str,
    language: str,
    inputs: PackInputs,
    icon_pixels: list[tuple[int, int, int, int]] | None,
    icon_size: tuple[int, int],
    sign_identity: str = "-",
    say: Callable[[str], None] = print,
) -> bool:
    """Sign and verify a fresh candidate before publishing it as a single transaction."""
    if app.is_symlink():
        raise PackError("the bundle destination must not be a symbolic link")
    if inputs.scale is not None and inputs.scale < 1:
        raise PackError("scale must be positive")
    if language not in {"ja", "en", "fr", "de", "it", "es", "zh-Hans", "ko", "nl", "pt", "ru", "zh-Hant"}:
        raise PackError("unsupported language")
    inputs = replace(inputs, whom=app, language=language)
    extra = list(inputs.extra_files or [])
    required: list[Path] = []
    for _source, target in extra:
        try:
            relative = target.relative_to(app)
        except ValueError as error:
            raise PackError("an extra file destination is outside the app") from error
        if ".." in relative.parts or relative in required:
            raise PackError("invalid or duplicate extra file destination")
        required.append(relative)
    if icon_pixels:
        required.append(Path("Contents/Resources/AppIcon.icns"))
    signature = schema_hash({
        "inputs": pack_inputs_hash(inputs, icon_pixels), "name": app_name,
        "title_id": title_id, "version": version, "icon_size": repr(icon_size), "identity": sign_identity,
    })
    key = app / "Contents/Resources/ctr-native" / KEY_NAME
    if app.exists() and key.is_file() and key.read_text().strip() == signature:
        try:
            verify_bundle(app, required)
        except PackError:
            pass  # changed or incomplete bundles are rebuilt from verified inputs
        else:
            say(f"app packed (inputs unchanged, signatures verified): {app.name}")
            return True
    app.parent.mkdir(parents=True, exist_ok=True)
    candidate = Path(tempfile.mkdtemp(prefix=f".{app.stem}-", suffix=".app", dir=app.parent))
    started = time.monotonic()
    preserve_candidate = False
    published = False
    migrated = None
    try:
        contents = contents_of(candidate)
        macos, resources = contents / "MacOS", contents / "Resources"
        for source, target in extra:
            staged = candidate / target.relative_to(app)
            staged.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, staged)
            if target.suffix == ".dylib" or target.name.endswith("-host"):
                staged.chmod(0o755)
        if icon_pixels and IconSet(resources / "ctr-native/iconset").refresh(icon_pixels, *icon_size) is None:
            raise PackError("icon generation failed")
        write_atomic(macos / LAUNCHER_NAME, effective_launcher(inputs).encode())
        (macos / LAUNCHER_NAME).chmod(0o755)
        write_atomic(contents / "Info.plist", info_plist(app_name, app_bundle_id(title_id), version))
        overlay = resources / "ctr-native"
        write_atomic(overlay / KEY_NAME, (signature + "\n").encode())
        write_atomic(overlay / "inputs.tsv", "".join(f"{key}\t{value}\n" for key, value in {
            "host_version": inputs.host_version, "toolkit_version": inputs.toolkit_version,
            "language": language, "scale": inputs.scale, "profile_hash": inputs.profile_hash,
            "appid": app_bundle_id(title_id), "rom_path": inputs.rom_path,
        }.items()).encode())
        for _source, target in extra:
            if target.suffix == ".dylib" or target.name.endswith("-host"):
                sign_executable(candidate / target.relative_to(app), sign_identity)
        codesign(candidate, sign_identity, say=say)
        verify_bundle(candidate, required)
        migrated = migrate_legacy(app)
        ensure_sandbox(app)
        publish_bundle(candidate, app)
        published = True
        if migrated is not None:
            preserve_candidate = True
            try:
                candidate.replace(app.with_name(app.name + ".ctr-native-legacy"))
            except OSError as error:
                raise PackError(f"new app published; original legacy bundle preserved at {candidate}") from error
            preserve_candidate = False
        say(f"app packed in {int(time.monotonic() - started)}s: {app}")
        return False
    finally:
        if not published and migrated:
            rollback_migration(migrated)
        if not preserve_candidate:
            shutil.rmtree(candidate, ignore_errors=True)


def pack_inputs_hash(inputs: PackInputs, icon_pixels: list[tuple[int, int, int, int]] | None) -> str:
    """Versioned content fingerprint; timestamps are not evidence of unchanged inputs."""
    return schema_hash({
        "format": "2", "rom": hash_file(inputs.rom_path),
        "host": hash_file(inputs.zakuro_bin or inputs.host_bin),
        "aot": hash_file(inputs.recompiled_dylib) if inputs.recompiled_dylib else "none",
        "profile": inputs.profile_hash, "toolkit": inputs.toolkit_version,
        "launcher": effective_launcher(inputs),
        "extra_files": schema_hash({str(target): hash_file(source) for source, target in (inputs.extra_files or [])}),
        "launcher_args": repr(inputs.launcher_args),
        "icon": hashlib.sha256(repr(icon_pixels).encode()).hexdigest(),
    })


def file_stamp(path: Path) -> str:
    stat = path.stat()
    return f"{stat.st_size}:{stat.st_mtime_ns}"


def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb", buffering=0) as file:
        while chunk := file.read(0x100_0000):
            digest.update(chunk)
    return digest.hexdigest()
