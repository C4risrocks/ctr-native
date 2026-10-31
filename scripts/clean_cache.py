#!/usr/bin/env python3
# Copyright (c) 2026 ctr-native contributors — MIT license.
"""Remove inactive per-app pipeline caches and previous logs older than 30 days.

    python3 scripts/clean_cache.py <game.app or games folder> [--dry-run]

Saves, configuration and the current log are never candidates. If process
inspection fails, nothing is deleted.
"""
from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from dm.tools import user_data  # noqa: E402

LOG_STALE_SECONDS = 30 * 24 * 3600
PIPELINE_NAME = re.compile(r"[0-9a-fA-F]{16}\.bin")


def candidates(app: Path, now: float) -> list[Path]:
    data = user_data.UserData(app)
    paths: set[Path] = set()
    for directory in data.pipeline_dirs:
        if not user_data.safe_path(directory):
            continue
        if directory.is_dir():
            paths.update(item for item in directory.iterdir()
                         if PIPELINE_NAME.fullmatch(item.name) and item.is_file() and user_data.safe_path(item))
        old = directory.parent / "pipelines.bin"
        if user_data.safe_path(old) and old.is_file():
            paths.add(old)
    for directory in data.old_cache_dirs:
        if user_data.safe_path(directory) and directory.is_dir():
            paths.update(item for item in directory.iterdir()
                         if item.suffix in {".shadercache", ".tmp"}
                         and (item.is_file() or item.is_dir()) and user_data.safe_path(item))
    for directory in data.log_dirs:
        previous = directory / "zakuro.previous.log"
        if (user_data.safe_path(previous) and previous.is_file()
                and now - previous.stat().st_mtime > LOG_STALE_SECONDS):
            paths.add(previous)
    return sorted(paths)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(__doc__ or "Remove inactive known caches without touching saves").splitlines()[0])
    parser.add_argument("target", type=Path, nargs="?", default=Path("."))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    target = args.target.absolute()
    if not user_data.safe_path(target) or not target.is_dir():
        print(f"not a safe app/games directory: {target}", file=sys.stderr)
        return 1
    apps = [target] if target.name.endswith(".app") else sorted(target.glob("*.app"))
    try:
        observed = user_data.active_files()
        removed = 0
        for app in apps:
            if not user_data.safe_path(app) or user_data.runtime_in_use(app, observed):
                continue
            for item in candidates(app, time.time()):
                # Re-check before each deletion, including the app executable;
                # cache files need not be held open for the whole session.
                if not args.dry_run and user_data.runtime_in_use(app):
                    break
                size = user_data.cache_size(item)
                if not args.dry_run:
                    if not user_data.safe_path(item):
                        raise OSError("cache path changed during cleanup")
                    user_data.remove_cache(item)
                print(f"{item} · {size:,} bytes")
                removed += size
    except OSError as error:
        print(f"cleanup stopped: {error}", file=sys.stderr)
        return 1
    print(f"{'(dry run) ' if args.dry_run else ''}cleaned: {removed:,} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
