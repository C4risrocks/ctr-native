#!/usr/bin/env python3
# Copyright (c) 2026 ctr-native contributors — MIT license.
"""Turn your 3DS dump into a double-clickable Mac app (the ctr-native pipeline).

    python3 scripts/build_app_from_3ds.py ~/ctr-native-roms/ALBW -o ~/Desktop

One script, one deliverable, like nxnative's NSP builder: parse the container
(NCSD/NCCH, no keys needed for decrypted or FixedKey dumps), verify it against
the profile when the profile pins a hash, generate the Azahar configuration
(sandboxed per game), and pack a `<name>.app` that keeps saves, caches and
logs inside its own bundle.

Console keys and your dumps stay on your machine and out of git: passing
`--boot9` (or `--keys`) only ever decrypts into `<id>_build/` — it is never
committed, bundled, or reported.

All options:

    -h, --help                  this text; everything below is optional
    -o, --output DIR            where the .app lands (default: beside the dump)
    --azahar-app PATH           the Azahar.app to launch with (default: /Applications)
    --app-name NAME             override the name (default: the SMDH long title)
    --language CODE             emulated region (ja|en|fr|de|it|es|...) (default: en)
    --resolution-factor N       quick per-build resolution override (1..6)
    --no-icon                   skip the .icns work (a square-grey icon shows)
    --allow-damaged             pack a dump whose verification hash does not match
    --no-verify                 skip the profile's MD5 verification
    --boot9 PATH                your boot9: decrypt encrypted partitions first
    --keys PATH                 a tsv keys file instead of boot9 (slot=hexkey)
    --progress json|bar|lines|off    reporting mode (default: bar on a tty)
    --no-keep-extracted         delete <id>_build/extract after success
    --launch                    open the app when the build finishes
"""

from __future__ import annotations

import argparse
import shutil
import sys
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dm.games import Profile, load_profile  # noqa: E402
from dm.tools import config_ini, ncch, pack_app, progress as progress_module  # noqa: E402
from dm.tools.decrypt import DecryptError, KeySource, decrypt_card_image  # noqa: E402
from dm.tools.ncch import (  # noqa: E402
    ContainerError,
    GameFile,
    PartitionInfo,
    Smdh,
)

TOOLKIT_VERSION = "ctr-native 0.1.0"
LANGUAGE_REGION = {
    "ja": 0, "en": 1, "fr": 2, "de": 3, "it": 4, "es": 5,
    "zh-Hans": 6, "ko": 7, "nl": 8, "pt": 9, "ru": 10, "zh-Hant": 11,
}


@dataclass
class Build:
    """One game's build folder state (mirrors nxnative's `<id>_build/`)."""

    source: Path
    title_id: str
    partition: PartitionInfo
    profile: Profile
    build_dir: Path
    logs: Path = field(init=False)
    extract: Path = field(init=False)

    def __post_init__(self) -> None:
        self.logs = self.build_dir / "logs"
        self.logs.mkdir(parents=True, exist_ok=True)
        self.extract = self.build_dir / "extract"


class BuildFailed(Exception):
    """A build step that cannot continue (the log carries the detail)."""


def main(argv: list[str] | None = None) -> int:
    started = time.monotonic()
    args = parse_args(argv)
    progress = progress_module.Progress(args.progress)
    ok = run(args, progress)
    if not ok:
        return 1
    total = time.monotonic() - started
    progress.say(f"build finished in {int(total)}s")
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Pack a 3DS dump into a per-game Mac app (ctr-native).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.splitlines()[1].strip(),
    )
    parser.add_argument("game", help="a game folder (card images and/or CIAs) or one file")
    parser.add_argument("-o", "--output", default=None, help="where the .app lands")
    parser.add_argument("--host", default="zakuro", choices=("zakuro", "azahar"),
                        help="the HLE host the app runs on (default: zakuro, the native Rust one)")
    parser.add_argument("--zakuro-bin", default=None, type=Path,
                        help="path to the zakuro binary (default: vendors/zakuro/target/release/zakuro)")

    parser.add_argument("--azahar-app", default="/Applications/Azahar.app", type=Path)
    parser.add_argument("--app-name", default=None)
    parser.add_argument("--language", default="en", choices=sorted(LANGUAGE_REGION))
    parser.add_argument("--resolution-factor", default=None, type=int)
    parser.add_argument("--no-icon", action="store_true")
    parser.add_argument("--allow-damaged", action="store_true")
    parser.add_argument("--no-verify", action="store_true")
    parser.add_argument("--boot9", default=None, type=Path)
    parser.add_argument("--keys", default=None, type=Path)
    parser.add_argument("--progress", default="auto",
                        choices=("json", "bar", "lines", "off", "auto"))
    parser.add_argument("--no-keep-extracted", action="store_true")
    parser.add_argument("--launch", action="store_true")
    return parser.parse_args(argv)


def run(args: argparse.Namespace, progress: progress_module.Progress) -> bool:
    source = Path(args.game).expanduser().resolve()
    if not source.exists():
        progress.say(f"{source} does not exist", error=True)
        return False
    candidates = list(ncch.find_game_files(source))
    packable = [c for c in candidates if c.kind == "card image"]
    if not packable:
        progress.say("no card image (.3ds/.cci) found — CIAs arrive in a later build",
                     error=True)
        for candidate in candidates:
            progress.step(progress.stage(0, 1, "discover"), f"{candidate.path.name}: {candidate.kind}")
        return False
    if len(packable) > 1:
        progress.say(f"{len(packable)} games in the folder; building the first ({packable[0].path.name})")

    chosen = packable[0]
    stages_total = 6
    game_build = None
    try:
        state = progress.stage(1, stages_total, "find the game", hint=chosen.path.name)
        game_build = identify_game(chosen, state, progress, args)

        state = progress.stage(2, stages_total, "verify the dump")
        verify_hash(game_build, state, progress, args)

        patch = {}
        if args.resolution_factor is not None:
            patch["Renderer.resolution_factor"] = str(args.resolution_factor)

        language = pick_language(game_build, args.language, progress)
        rom_for_app = game_build.source
        if not game_build.partition.no_crypto:
            state = progress.stage(3, stages_total, "decrypt a working copy", hint="--boot9")
            rom_for_app = decrypt_stage(game_build, state, progress, args)
            stages_total = 7
            state = progress.stage(4, stages_total, "finish the copy")
            progress.stage_end(state, "done")

        state = progress.stage(3 if stages_total == 6 else 5, stages_total, "make the icon")
        icon_pixels = icon_stage(game_build, state, progress, args)

        state = progress.stage(4 if stages_total == 6 else 6, stages_total, "pack the app")
        app = pack_stage(game_build, state, progress, args,
                         language=language, rom_for_app=rom_for_app, patch=patch,
                         icon_pixels=icon_pixels)

        state = progress.stage(5 if stages_total == 6 else 7, stages_total, "verify the app")
        launch_stage(app, state, progress, args)
    except (ContainerError, DecryptError, BuildFailed, OSError) as error:
        progress.say(str(error), error=True)
        if args.progress == "json":
            progress.say("-" * 40, error=True)
            for line in traceback.format_exc().splitlines():
                progress.say(line, error=True)
        return False
    if args.no_keep_extracted and game_build is not None:
        shutil.rmtree(game_build.extract, ignore_errors=True)
    return True


def identify_game(chosen: GameFile, state: progress_module.StageState,
                  progress: progress_module.Progress, args: argparse.Namespace) -> Build:
    progress.step(state, f"reading {chosen.path.name}")
    title_id, partition, _media_units = ncch.parse_card_image(chosen.path)
    if not partition.magic_ok:
        raise BuildFailed(f"{chosen.path.name}: partition 0 has no NCCH header")
    progress.count(state, 1, 1, "game")
    profile = load_profile(title_id)
    build_dir = chosen.path.parent / build_name(title_id)
    state_text = "provisional" if not profile.values else "yes"
    progress.stage_end(state, f"serial {partition.product_code} · {title_id} · profile {state_text}")
    return Build(source=chosen.path, title_id=title_id, partition=partition,
                 profile=profile, build_dir=build_dir)


def build_name(title_id: str) -> str:
    return f"{title_id}_build"


def verify_hash(build: Build, state: progress_module.StageState,
                progress: progress_module.Progress, args: argparse.Namespace) -> None:
    if not build.profile.verified_md5:
        progress.stage_end(state, "no pin in the profile: skipped")
        return
    if args.no_verify:
        progress.stage_end(state, "skipped (--no-verify)")
        return
    progress.step(state, "md5 full-file check (about a second per GiB)")
    import hashlib

    digest = hashlib.md5()
    size = build.source.stat().st_size
    read_so_far = 0
    with open(build.source, "rb", buffering=0) as file:
        while chunk := file.read(0x100_0000):
            digest.update(chunk)
            read_so_far += len(chunk)
            progress.count(state, read_so_far, size, "bytes", est=True)
    actual = digest.hexdigest()
    if actual != build.profile.verified_md5:
        message = (f"MD5 {actual} does not match the profile pin {build.profile.verified_md5}:\n"
                   f"  {build.source.name}")
        if args.allow_damaged:
            progress.say(message + "\n  packed as read (--allow-damaged)", error=True)
        else:
            raise BuildFailed(message + "\n  (pass --allow-damaged to pack it anyway)")
        progress.stage_end(state, "mismatch, packed as read")
    else:
        progress.stage_end(state, "MD5 verified against the profile pin")


def pick_language(build: Build, language: str, progress: progress_module.Progress) -> str:
    smdh = load_smdh(build)
    available = ncch.available_languages(smdh)
    if language in available:
        return language
    fallback = available[0] if available else "en"
    progress.say(f"language {language} is not on this card (SMDH: {', '.join( available)}); using {fallback!r}")
    return fallback


def load_smdh(build: Build) -> Smdh:
    rom = build.source
    smdh_raw = ncch.read_exefrs_file(rom, build.partition, "icon")
    return ncch.parse_smdh(smdh_raw)


def decrypt_stage(build: Build, state: progress_module.StageState,
                  progress: progress_module.Progress, args: argparse.Namespace) -> Path:
    if not args.boot9 and not args.keys:
        raise BuildFailed(
            "this dump's partitions are encrypted and no keys arrived:\n"
            "  --boot9 <your boot9.bin>   (most dumps; the copy stays in <id>_build)\n"
            "  --keys <slot=hexkeu tsv>   (if you keep a derived table instead)"
        )
    progress.step(state, "deriving keys from your own console data")
    out_dir = build.build_dir / "decrypted"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / (build.source.stem + ".decrypted.3ds")
    total = build.source.stat().st_size
    progress.count(state, 0, total, "bytes", est=True)

    decrypt_card_image(build.source, out, KeySource(boot9=args.boot9, keys_file=args.keys),
                       say=lambda message: progress.step(state, message))
    progress.count(state, total, total, "bytes")
    progress.stage_end(state, f"{out.name} ({out.stat().st_size:,} bytes)")
    return out


def read_full_header_size(source: Path) -> int:
    return source.stat().st_size


def icon_stage(build: Build, state: progress_module.StageState,
               progress: progress_module.Progress, args: argparse.Namespace) -> list[tuple[int, int, int, int]] | None:
    """Decode the SMDH large icon to RGBA (the .icns grows out of it in pack)."""
    if args.no_icon:
        progress.stage_end(state, "skipped (--no-icon)")
        return None
    progress.step(state, "SMDH icon (48x48, RGB565 CTR layout)")
    rgba = ncch.icon_rgba(load_smdh(build).large_icon)
    progress.count(state, 1, 1, "icon")
    progress.stage_end(state, "decoded")
    return rgba


def pack_stage(build: Build, state: progress_module.StageState, progress: progress_module.Progress,
               args: argparse.Namespace, language: str, rom_for_app: Path,
               patch: dict[str, str], icon_pixels: list[tuple[int, int, int, int]] | None) -> Path:
    """The app: name/plist/launcher/config/sandbox, atomically, with reuse."""
    progress.step(state, "making the configuration")
    profile_values = dict(build.profile.values)
    profile_values.update(patch)
    config_text = config_ini.render_template(profile_values)
    app_output_dir = Path(args.output).expanduser().resolve() if args.output else build.source.parent
    app_output_dir.mkdir(parents=True, exist_ok=True)
    smdh = load_smdh(build)
    lang_index = LANGUAGE_REGION[language]
    long_title = smdh.titles.get(lang_index, (smdh.titles.get(1) or next(iter(smdh.titles.values()))))[1]
    app_name = args.app_name or pack_app.app_name_from_smdh(long_title)
    # \n inside titles (a legal SMDH break) is not legal in a Finder name.
    app_name = app_name.replace("\n", " - ").strip()
    app_path = app_output_dir / f"{app_name}.app"

    if args.host == "zakuro":
        # the native Rust host: its binary was built in vendors/, its AOT
        # library came from 3dsrecomp build; both land INSIDE the bundle so
        # the app stays self-contained
        zakuro_bin = args.zakuro_bin or (ROOT / "vendors/zakuro/target/release/zakuro")
        if not zakuro_bin.exists():
            raise BuildFailed(
                f"the zakuro host is missing at {zakuro_bin}:\n"
                "  build it once: cd vendors/zakuro && cargo build --release --locked --workspace 2>&1 | tail -1\n"
                "  (or pass --host azahar for the published emulator)"
            )
        recompiled_dylib = Path.home() / "Library/Application Support/3dsrecomp" / f"{build.title_id}.dylib"
        if not recompiled_dylib.exists():
            raise BuildFailed(
                f"the AOT library for {build.title_id} is missing at {recompiled_dylib}:\n"
                "  build it once (about ten minutes):\n"
                "    cd vendors/3dsrecomp && cargo build --release && ./target/release/3dsrecomp build <the rom>\n"
                "  (or pass --host azahar)"
            )
        host_bin_for_inputs = zakuro_bin  # stamps the SOURCE; the launcher stays self-contained
        # the hints zakuro writes beside the installed library, seeded into
        # the bundle so the bundled copy keeps the file next to it; zakuro
        # never writes a bundled copy's hints (a sealed parent must not
        # change under it), so the seal holds.
        hints_path = recompiled_dylib.with_suffix(".hints")
        extra_files = [
            (zakuro_bin, app_path / "Contents/MacOS/zakuro-host"),
            (recompiled_dylib, app_path / "Contents/Resources/game" / f"{build.title_id}.dylib"),
        ]
        if hints_path.is_file():
            extra_files.append((hints_path, app_path / "Contents/Resources/game" / f"{build.title_id}.hints"))
        host_version = file_stamp(zakuro_bin)
    else:
        zakuro_bin = None
        recompiled_dylib = None
        extra_files = []
        host_bin_for_inputs = Path(args.azahar_app).expanduser() / "Contents/MacOS/azahar"
        if not host_bin_for_inputs.exists():
            raise BuildFailed(
                f"Azahar is missing at {host_bin_for_inputs}:\n"
                "  install the macos-arm64 release you prefer, or pass --azahar-app <path>"
            )
        host_version = azahar_version(host_bin_for_inputs)
        zakuro_bin = None
        recompiled_dylib = None

    inputs = pack_app.PackInputs(
        rom_path=rom_for_app,
        whom=app_path,
        azahar_bin=host_bin_for_inputs,
        azahar_version=host_version,
        toolkit_version=TOOLKIT_VERSION,
        profile_hash=pack_app.schema_hash({**profile_values, "_md5pin": build.profile.verified_md5}),
        icon_png=None,
        launcher_args=[],
        host=args.host,
        extra_files=extra_files,
        zakuro_bin=zakuro_bin,
        recompiled_dylib=recompiled_dylib,
        scale=3 if args.host == "zakuro" else None,
    )
    if args.host == "zakuro":
        # the launcher binds the bundle's own copies: self-contained; the
        # stamps above stay on the SOURCE binaries (the copy happens in pack)
        inputs.host_bin_launcher = app_path / "Contents/MacOS/zakuro-host"
        inputs.recompiled_dylib_launcher = app_path / "Contents/Resources/game" / f"{build.title_id}.dylib"
    reused = pack_app.pack(
        app=app_path,
        app_name=app_name,
        title_id=build.title_id,
        version=version_of(build),
        language=language,
        inputs=inputs,
        icon_pixels=icon_pixels,
        icon_size=(48, 48),
        say=lambda message: progress.step(state, message),
    )
    # The sandbox is the app's user directory: its config lands there once,
    # the first time, and later builds never touch it (saves inside). Zakuro
    # keeps its own settings.toml in the same root; nothing prewritten today.
    sandbox = pack_app.sandbox_of(app_path, args.host)
    if args.host == "zakuro":
        progress.stage_end(state, f"sandbox ready ({'reused' if reused else 'fresh'}) · host zakuro")
    else:
        config_path = sandbox["config"] / "qt-config.ini"
        if reused and config_path.exists():
            progress.stage_end(state, f"config reused ({len(profile_values)} keys)")
        else:
            pack_app.ensure_sandbox(app_path, args.host)
            pack_app.write_atomic(config_path, config_text.encode())
            progress.stage_end(state, f"config written ({len(profile_values)} keys)")
    # A record of what got packed, next to the logs.
    (build.logs / "pack.tsv").write_text(
        "\n".join([
            f"appid\t{pack_app.app_bundle_id(build.title_id)}",
            f"app\t{app_path}",
            f"language\t{language}",
            f"profile\tscreenshot in dm/games/{build.title_id}/README.md",
        ]) + "\n"
    )
    if args.launch:
        progress.step(state, "opening the app")
        import subprocess

        subprocess.run(["/usr/bin/open", str(app_path)], check=True)
    return app_path


def version_of(build: Build) -> str:
    # Without parsing control NCAs, the card shows no display version; honest 1.0.0.
    return "1.0.0"


def azahar_version(azahar_bin: Path) -> str:
    try:
        import subprocess

        result = subprocess.run([str(azahar_bin), "--version"], capture_output=True,
                                text=True, timeout=15)
        return result.stdout.strip().splitlines()[-1][:60] if result.stdout else file_stamp(azahar_bin)
    except (OSError, subprocess.SubprocessError):
        return file_stamp(azahar_bin)


def file_stamp(path: Path) -> str:

    stat = path.stat()
    return f"{stat.st_size}@{stat.st_mtime_ns}"


def launch_stage(app: Path, state: progress_module.StageState,
                 progress: progress_module.Progress, args: argparse.Namespace) -> None:
    """A smoke run of the packed app: windowless headless for the zakuro host."""
    if not args.launch:
        progress.stage_end(state, "not launched (pass --launch to open it)")
        return
    import os as _os
    import shlex
    import subprocess

    launcher_text_file = (app / "Contents/MacOS/ctr-native").read_text()
    host_is_zakuro = "zakuro-host" in launcher_text_file
    rom = None
    for line_text in launcher_text_file.splitlines():
        if line_text.startswith("ROM="):
            rom = Path(shlex.split(line_text.replace("ROM=", "ROM ", 1))[1])
            break
    if rom is None:
        raise BuildFailed("the launcher carries no ROM path")

    if host_is_zakuro:
        env = dict(_os.environ)
        env["HOME"] = str(pack_app.sandbox_of(app, "zakuro")["home"])
        env["DYLD_LIBRARY_PATH"] = "/opt/homebrew/lib"
        zakuro_bin = app / "Contents/MacOS/zakuro-host"
        headless_run = subprocess.run(
            [str(zakuro_bin), "--headless", "120", "--mute", "--recompiled",
             str(rom_dylib_path(app)), str(rom)],
            env=env, capture_output=True, text=True, timeout=180,
        )
        output = headless_run.stdout + headless_run.stderr
        progress.count(state, 1, 1, "smoke")
        if "Completed after" in output:
            speed_note = output.strip().splitlines()[-2].strip() if len(output.splitlines()) > 1 else ""
            progress.stage_end(state, f"headless smoke passed · host zakuro ({speed_note[:60]})")
            return
        raise BuildFailed(f"headless smoke failed:\n{output[-800:]}")

    # the azahar host: a real (windowed) launch, log-based smoke
    subprocess.run(["/usr/bin/open", str(app)], check=True)
    log = pack_app.sandbox_of(app, "azahar")["log"] / "azahar_log.txt"
    for _ in range(25):
        time.sleep(1)
        if log.exists() and log.stat().st_size > 0:
            progress.count(state, 1, 1, "smoke")
            progress.stage_end(state, "the app booted; its log is writing")
            return
    progress.stage_end(state, "no log yet — if the window is up, play; the log may be buffered", ok=True)


def rom_dylib_path(app: Path) -> Path:
    """The bundle's own copy of the game's AOT library (self-contained)."""
    return next(iter((app / "Contents/Resources/game").glob("*.dylib")))


if __name__ == "__main__":
    sys.exit(main())
