#!/usr/bin/env python3
# Copyright (c) 2026 ctr-native contributors — MIT license.
"""Collect what a bug report needs into one zip — and never key material.

    python3 scripts/bug_report.py <game.app> [-o report.zip]

Contents: allowlisted inputs metadata and runtime/build log tails, each
limited to 4 MiB, plus tool versions. Symlinks, binary files and recognizable
key tables are refused. No arbitrary user files are collected.
"""

from __future__ import annotations

import argparse
import platform
import re
import os
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from dm.tools.user_data import UserData, open_regular, safe_path  # noqa: E402

MAX_FILE = 4 * 1024 * 1024
REFUSED = ("boot9", "movable.sed", "keys", ".otp")
STAGE_LOGS = ("discover", "identify", "verify", "decrypt", "icon", "pack", "launch")
KEY_ROW = re.compile(rb"(?im)^\s*(?:0x)?[0-9a-f]{1,2}\s*=\s*(?:[0-9a-f]{2}\s*){16}\s*(?:#.*)?$")


def sources_for(target: Path) -> list[tuple[Path, str]]:
    sources: list[tuple[Path, str]] = []
    if target.name.endswith(".app"):
        metadata = target / "Contents/Resources/ctr-native"
        sources.append((metadata / "inputs.tsv", "pack/inputs.tsv"))
        data = UserData(target)
        for name in ("zakuro.log", "zakuro.previous.log"):
            for directory in data.log_dirs:
                candidate = directory / name
                if safe_path(candidate) and candidate.is_file():
                    sources.append((candidate, f"sandbox/{name}"))
                    break
        # The title ID is in the bundle's own metadata, not a user-controlled
        # arbitrary path from a diagnostic log.
        try:
            with open_regular(target / "Contents/Info.plist") as file:
                import plistlib
                if os.fstat(file.fileno()).st_size > MAX_FILE:
                    raise ValueError("oversized Info.plist")
                metadata = plistlib.loads(file.read(MAX_FILE))
                if not isinstance(metadata, dict):
                    raise ValueError("Info.plist must be a dictionary")
                identifier = str(metadata.get("CFBundleIdentifier", "")).split(".")[-1]
            builds = [p for p in target.parent.iterdir()
                      if p.name.lower() == f"{identifier.lower()}_build"]
            if not re.fullmatch(r"[0-9a-fA-F]{16}", identifier):
                builds = []
        except (OSError, ValueError, TypeError):
            builds = []
    else:
        builds = [target] if target.name.endswith("_build") else []
    for build in builds:
        for name in (*[f"{stage}.log" for stage in STAGE_LOGS], "pack.tsv"):
            sources.append((build / "logs" / name, f"build/{name}"))
    return sources


def read_diagnostic(path: Path) -> tuple[bytes, bool]:
    if any(needle in path.name.lower() for needle in REFUSED):
        raise ValueError("key material name refused")
    with open_regular(path) as file:
        length = os.fstat(file.fileno()).st_size
        if path.suffix == ".log":
            file.seek(max(0, length - MAX_FILE))
        data = file.read(MAX_FILE)
    if path.suffix == ".log" and length > MAX_FILE:
        # A bounded tail can start within a valid UTF-8 codepoint. Discard
        # only its at-most-three continuation bytes; validate the rest.
        skipped = 0
        while skipped < min(3, len(data)) and 0x80 <= data[skipped] < 0xC0:
            skipped += 1
        data = data[skipped:]
    data.decode("utf-8")  # binary material is never diagnostic text
    if b"\0" in data or KEY_ROW.search(data):
        raise ValueError("key-like or binary content refused")
    return data, length > MAX_FILE


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(__doc__ or "Collect bounded diagnostics without key material").splitlines()[0])
    parser.add_argument("app", type=Path, help="a ctr-native .app (or a <id>_build folder)")
    parser.add_argument("-o", "--output", type=Path, default=None)
    args = parser.parse_args(argv)
    target = args.app.absolute()
    if not safe_path(target) or not target.is_dir():
        print(f"not a safe app/build directory: {target}", file=sys.stderr)
        return 1
    out = args.output or target.with_name(target.stem + "-bugreport.zip")
    manifest = ["ctr-native bug report", f"source: {target}",
                f"python: {sys.version.split()[0]} ({platform.machine()})", f"macOS: {platform.mac_ver()[0]}"]
    count = 0
    try:
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as bundle:
            for path, arcname in sources_for(target):
                try:
                    data, truncated = read_diagnostic(path)
                except (OSError, ValueError, UnicodeError):
                    continue
                bundle.writestr(arcname, data)
                if truncated:
                    bundle.writestr(arcname + ".truncated.txt", "(limited to 4 MiB; logs keep their tail)\n")
                count += 1
            bundle.writestr("report.txt", "\n".join(manifest) + "\n")
    except OSError as error:
        print(f"report failed: {error}", file=sys.stderr)
        return 1
    print(f"report: {out} ({out.stat().st_size:,} bytes, {count} files)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
