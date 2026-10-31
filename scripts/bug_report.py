#!/usr/bin/env python3
# Copyright (c) 2026 ctr-native contributors — MIT license.
"""Collect what a bug report needs into one zip — and never key material.

    python3 scripts/bug_report.py <game.app> [-o report.zip]

Contents (text only, size-capped): the app's Info.plist summary, the packed
inputs record (`inputs.tsv`), its zakuro.log tails, the sandbox layout (names
only), build-tool versions, and any <id>_build logs beside the ROM. Files that
could be keys (`.keys`, boot9, movable.sed) are refused, not included.
"""

from __future__ import annotations

import argparse
import platform
import sys
import zipfile
from pathlib import Path

MAX_FILE = 4 * 1024 * 1024
TEXT_SUFFIXES = {".log", ".txt", ".tsv", ".json"}
EFI_REFUSED = ("boot9", "movable.sed", "keys.txt", ".otp")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("app", type=Path, help="a ctr-native .app (or a <id>_build folder)")
    parser.add_argument("-o", "--output", type=Path, default=None)
    args = parser.parse_args(argv)

    app = args.app.resolve()
    if not app.exists():
        print(f"{app} does not exist", file=sys.stderr)
        return 1
    out = args.output or app.with_name(app.stem + "-bugreport.zip")
    sources: list[tuple[Path, str]] = []
    if app.name.endswith(".app"):
        for interesting in sorted((app / "Contents/Resources/ctr-native").glob("*")):
            if interesting.suffix in TEXT_SUFFIXES:
                sources.append((interesting, f"pack/{interesting.name}"))
        # the sandbox is the sibling folder of the app
        sandbox = app.with_name(app.name + ".ctr-native")
        if not sandbox.is_dir():
            sandbox = app / "Contents/MacOS/sandbox"
        for log_name in ("zakuro.log", "zakuro.previous.log"):
            candidate = sandbox / log_name
            if candidate.exists() and candidate.stat().st_size:
                sources.append((candidate, f"sandbox/{Path(log_name).name}"))
    build_logs = app.parent / "logs"
    if build_logs.is_dir():
        for log in sorted(build_logs.glob("*.log"))[-5:]:
            sources.append((log, f"build/{log.name}"))

    manifest = [
        "ctr-native bug report",
        f"source: {app}",
        f"python: {sys.version.split()[0]} ({platform.machine()})",
        f"macOS: {platform.mac_ver()[0]}",
        "keys were never, and will never be, part of this zip",
    ]
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr("report.txt", "\n".join(manifest) + "\n")
        for path, arcname in sources:
            if any(needle in path.name.lower() for needle in EFI_REFUSED):
                continue
            data = path.read_bytes()[:MAX_FILE]
            bundle.writestr(arcname, data)
            if len(data) == MAX_FILE:
                bundle.writestr(arcname + ".truncated.txt", "(cut at 4 MiB)\n")
    print(f"report: {out} ({out.stat().st_size:,} bytes, {len(sources)} files)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
