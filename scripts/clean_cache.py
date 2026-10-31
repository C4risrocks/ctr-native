#!/usr/bin/env python3
# Copyright (c) 2026 ctr-native contributors — MIT license.
"""Free disk space by removing shader caches and logs of old builds.

    python3 scripts/clean_cache.py <game.app or games folder> [--dry-run]

Keeps what a running app could still open (live processes are detected by
their open files) and touches only inside `…/zakuro/cache` folders and stale
`zakuro.log` files — saves and settings are never candidates.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import time
from pathlib import Path

CANDIDATE_SUFFIXES = (".shadercache", ".tmp")   # contents, not saves
LOG_STALE_SECONDS = 30 * 24 * 3600


def active_files() -> set[str]:
    """Filenames currently open by running zakuro processes, for skip-if-live."""
    try:
        import subprocess

        pids = subprocess.run(["/usr/bin/pgrep", "-f", "MacOS/zakuro-host"],
                              capture_output=True, text=True)
        files: set[str] = set()
        for pid in pids.stdout.split():
            try:
                lsof = subprocess.run(["/usr/sbin/lsof", "-p", pid],
                                      capture_output=True, text=True, timeout=10)
                files.update(line.split()[-1] for line in lsof.stdout.splitlines()[-500:])
            except (OSError, subprocess.SubprocessError):
                continue
        return files
    except OSError:
        return set()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("target", type=Path, nargs="?", default=Path("."))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    target = args.target.resolve()
    users: set[str] = active_files()
    saved_candidates: list[tuple[Path, int]] = []

    apps = list(target.glob("*.app"))
    roots = apps or ([target] if target.is_dir() else [])
    for root in roots:
        sandbox = root / "Contents/MacOS/sandbox"
        for cache_dir in sandbox.glob("**/cache"):
            for item in cache_dir.iterdir():
                if item.name.endswith(CANDIDATE_SUFFIXES):
                    size = sum(f.stat().st_size for f in item.rglob("*") if f.is_file())
                    saved_candidates.append((item, size))
        log_file = sandbox / "home/Library/Application Support/zakuro/zakuro.previous.log"
        if log_file.is_file() and time.time() - log_file.stat().st_mtime > LOG_STALE_SECONDS:
            saved_candidates.append((log_file, log_file.stat().st_size))

    removed = 0
    for item, size in saved_candidates:
        if str(item) in users:
            continue
        print(f"{item} · {size:,} bytes")
        if not args.dry_run:
            if item.is_dir():
                shutil.rmtree(item)
            else:
                os.unlink(item)
        removed += size
    total = f"{'(dry run) ' if args.dry_run else ''}{'cleaned' if removed else 'nothing to clean'}: {removed:,} bytes"
    print(total)
    return 0


if __name__ == "__main__":
    sys.exit(main())
