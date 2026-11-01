#!/usr/bin/env python3
# Copyright (c) 2026 ctr-native contributors — MIT license.
"""Turn your 3DS dump into a double-clickable Mac app (the ctr-native pipeline).

    python3 scripts/build_app_from_3ds.py ~/ctr-native-roms/ALBW -o ~/Desktop

One script, one deliverable, like nxnative's NSP builder: the common pipeline
(`dm/build`) walks discover → identify → verify → prepare → obtain the AOT →
metadata/icon → pack+sign → verify, and this CLI only shapes its inputs.
Saves, settings and logs of each game live in the app's own sandbox.

Console keys and your dumps stay on your machine and out of git: passing
`--boot9` (or `--keys`) only ever decrypts into `<id>_build/` — it is never
committed, bundled, or reported.

All options:

    -h, --help                  this text; everything below is optional
    -o, --output DIR            where the .app lands (default: beside the dump)
    --app-name NAME             override the name (default: the SMDH long title)
    --language CODE             emulated region (ja|en|fr|de|it|es|...) (default: en)
    --scale N                   the window's size, times the console's (default: 3)
    --no-icon                   skip the .icns work (a square-grey icon shows)
    --allow-damaged             pack a dump whose verification hash does not match
    --no-verify                 skip the profile's MD5 verification
    --boot9 PATH                your boot9: decrypt encrypted partitions first
    --keys PATH                 a tsv keys file instead of boot9 (slot=hexkey)
    --zakuro-bin PATH           the host binary (default: vendors/zakuro/target/release/zakuro)
    --recompiler-bin PATH       the 3dsrecomp binary (default: vendors/3dsrecomp/target/release/3dsrecomp)
    --rebuild-aot               ignore the AOT cache and rebuild the library
    --progress json|bar|lines|off    reporting mode (default: bar on a tty)
    --no-keep-directories       delete the per-title scratch folders after success
    --launch                    open the app when the build finishes
"""

from __future__ import annotations

import argparse
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dm.build import BuildError, BuildRequest, build  # noqa: E402
from dm.build.models import LANGUAGE_REGION  # noqa: E402


def positive_int(value: str) -> int:
    try:
        number = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("scale must be a positive integer") from error
    if number < 1:
        raise argparse.ArgumentTypeError("scale must be a positive integer")
    return number


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Pack a 3DS dump into a per-game Mac app (ctr-native).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Example: python3 scripts/build_app_from_3ds.py ~/Games/ALBW -o ~/Desktop",
    )
    parser.add_argument("game", help="a folder of .3ds/.3dz/.cci card images, or one card image")
    parser.add_argument("-o", "--output", default=None, help="where the .app lands")
    parser.add_argument("--app-name", default=None)
    parser.add_argument("--language", default="en", choices=sorted(LANGUAGE_REGION))
    parser.add_argument("--scale", default=3, type=positive_int,
                        help="window scale, times the console's size (default: 3)")
    parser.add_argument("--no-icon", action="store_true")
    parser.add_argument("--allow-damaged", action="store_true")
    parser.add_argument("--no-verify", action="store_true")
    parser.add_argument("--boot9", default=None, type=Path)
    parser.add_argument("--keys", default=None, type=Path)
    parser.add_argument("--zakuro-bin", default=None, type=Path)
    parser.add_argument("--recompiler-bin", default=None, type=Path)
    parser.add_argument("--rebuild-aot", action="store_true")
    parser.add_argument("--progress", default="auto",
                        choices=("json", "bar", "lines", "off", "auto"))
    parser.add_argument("--no-keep-directories", action="store_true",
                        help="delete only the selected build extraction directory after success")
    parser.add_argument("--launch", action="store_true")
    return parser.parse_args(argv)


def make_request(args: argparse.Namespace) -> BuildRequest:
    return BuildRequest(
        game=Path(args.game).expanduser().resolve(),
        output=Path(args.output).expanduser().resolve() if args.output else None,
        app_name=args.app_name,
        language=args.language,
        scale=args.scale,
        no_icon=args.no_icon,
        allow_damaged=args.allow_damaged,
        no_verify=args.no_verify,
        boot9=args.boot9,
        keys=args.keys,
        zakuro_bin=args.zakuro_bin,
        recompiler_bin=args.recompiler_bin,
        rebuild_aot=args.rebuild_aot,
        launch=args.launch,
        root=ROOT,
    )


def main(argv: list[str] | None = None) -> int:
    started = time.monotonic()
    args = parse_args(argv)
    from dm.tools import progress as progress_module
    progress = progress_module.Progress(args.progress)
    try:
        request = make_request(args)
    except Exception as error:  # before the pipeline: this side reports first
        progress.error(f"unexpected failure: {error}", kind="unexpected",
                       traceback=traceback.format_exc().splitlines())
        return 1
    try:
        result = build(request, progress=progress)
    except BuildError:
        # the pipeline emitted the one structured error event already
        return 1
    except Exception as error:  # the pipeline guarantees BuildError; belt and braces
        progress.error(f"unexpected failure: {error}", kind="unexpected",
                       traceback=traceback.format_exc().splitlines())
        return 1
    total = time.monotonic() - started
    progress.say(f"build finished in {int(total)}s")
    if args.no_keep_directories:
        from dm.tools.user_data import safe_path, remove_cache
        extract = result.build_dir / "extract"
        if not safe_path(extract):
            progress.say("refusing linked extraction directory", error=True)
            return 1
        if extract.is_dir():
            remove_cache(extract)
    return 0


if __name__ == "__main__":
    sys.exit(main())
