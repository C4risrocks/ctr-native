# Copyright (c) 2026 ctr-native contributors — MIT license.
"""The common pipeline: every title walks the same eight stages.

    1. discover            the entry point
    2. identify            title and profile
    3. verify              the original dump
    4. prepare             a clear working copy when one is needed
    5. obtain the AOT      compile, or reuse a matching cached library
    6. metadata            SMDH and icon
    7. pack                sign and publish the .app
    8. verify the app      headless smoke, then open with --launch

Identity must agree between original ROM, prepared copy, AOT artifact and
package; one edition never silently replaces another.
"""
from __future__ import annotations

import subprocess
import traceback
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Protocol
from collections.abc import Callable

from dm.build.aot import obtain_aot
from dm.build.models import (
    LANGUAGE_REGION,
    AotArtifact,
    BuildError,
    BuildRequest,
    BuildResult,
    PreparedGame,
    SmokeResult,
)
from dm.games import Profile, load_profile
from dm.tools import ncch, pack_app
from dm.tools.decrypt import KeySource, decrypt_card_image
from dm.tools.ncch import ContainerError, GameFile, PartitionInfo


class Runner(Protocol):
    """How external processes start; tests inject their own."""
    def __call__(self, command: list, *, env: dict | None = None, timeout: int | None = None,
                 capture: str = "text") -> subprocess.CompletedProcess: ...


class StageHelper:
    """Concrete runner: subprocess with capture, errors left to the caller."""
    def __call__(self, command: list, *, env: dict | None = None, timeout: int | None = None,
                 capture: str = "text") -> subprocess.CompletedProcess:
        kwargs: dict = {"capture_output": True, "timeout": timeout, "text": True}
        if env is not None:
            kwargs["env"] = env
        return subprocess.run(command, **kwargs)


@dataclass
class Build:
    """One title's build-folder state (the per-title scratch)."""
    source: Path
    title_id: str
    partition: PartitionInfo
    profile: Profile
    build_dir: Path
    working_source: Path | None = None
    logs: Path = field(init=False)
    extract: Path = field(init=False)

    def __post_init__(self) -> None:
        self.logs = self.build_dir / "logs"
        self.logs.mkdir(parents=True, exist_ok=True)
        self.extract = self.build_dir / "extract"

    @classmethod
    def from_prepared(cls, prepared: PreparedGame) -> Build:
        build = cls(source=prepared.source, title_id=prepared.title_id,
                    partition=prepared.partition, profile=prepared.profile,
                    build_dir=prepared.build_dir)
        build.working_source = prepared.working_source
        return build


def build(request: BuildRequest, *, progress, runner: Callable | None = None) -> BuildResult:
    """One title through the whole common flow;落幕 on BuildError per stage."""
    flow = Pipeline(request, progress, runner or StageHelper())
    return flow.execute()


class Pipeline:
    def __init__(self, request: BuildRequest, progress, runner: Callable | None = None) -> None:
        self.request = request
        self.progress = progress
        self.runner = runner or StageHelper()
        self.stages_total = 8
        self._open_stage = None

    # small helpers ------------------------------------------------------------
    def stage(self, index: int, name: str):
        self._open_stage = self.progress.stage(index, self.stages_total, name)
        return self._open_stage

    def say(self, message: str, error: bool = False) -> None:
        self.progress.say(message, error=error)

    def report_error(self, stage: str, message: str, *, kind: str = "build",
                     traceback: list[str] | None = None) -> None:
        """P2-6: exactly one structured failure record per build — a Progress
        duck-type without the method (test stubs) degrades to a say."""
        emitter = getattr(self.progress, "error", None)
        if emitter is not None:
            emitter(message, stage=stage, kind=kind, traceback=traceback)
        elif hasattr(self.progress, "say"):
            self.progress.say(f"[{stage}] {message}", error=True)

    def stage_end(self, message: str) -> None:
        if self._open_stage is not None:
            self.progress.stage_end(self._open_stage, message)
        self._open_stage = None

    # the eight stages ----------------------------------------------------------
    def execute(self) -> BuildResult:
        try:
            self.stage(1, "discover")
            prepared = self.discover(self._open_stage)
            self.verify_stage(prepared)
            prepared = self.prepare_stage(prepared)
            zakuro_bin = self.resolve_zakuro()
            zakuro_stamp = file_stamp(zakuro_bin)
            aot = self.aot_stage(prepared, zakuro_stamp)
            icon_pixels = self.icon_stage(prepared)
            published = self.publish_stage(prepared, zakuro_bin, zakuro_stamp, aot, icon_pixels)
            smoke = self.smoke_stage(prepared, published)
            return BuildResult(
                title_id=prepared.title_id,
                app=published["app"],
                sandbox_home=published["sandbox_home"],
                rom=published["rom"],
                reused_package=published["reused"],
                aot=aot,
                smoke=smoke,
                build_dir=prepared.build_dir,
            )
        except BuildError as error:
            if self._open_stage is not None:
                self.progress.stage_end(self._open_stage,
                                        f"{error.stage}: {error.message}", ok=False)
                self._open_stage = None
            self.report_error(error.stage, error.message)
            raise
        except Exception as error:  # unexpected: the edge normalizes so every
            # failure surfaces one structured BuildError with its open stage
            open_stage = self._open_stage
            label = open_stage.stage_name if open_stage is not None else "pipeline"
            if open_stage is not None:
                self.progress.stage_end(open_stage, f"unexpected: {error}", ok=False)
                self._open_stage = None
            self.report_error("pipeline", f"unexpected failure in '{label}': {error}",
                              kind="unexpected",
                              traceback=traceback.format_exception(
                                  type(error), error, error.__traceback__))
            raise BuildError("pipeline",
                             f"unexpected failure in '{label}': {error}") from error

    # 1 -------------------------------------------------------------------------
    def discover(self, stage1) -> PreparedGame:
        source = self.request.game.expanduser().resolve()
        if not source.exists():
            raise BuildError("discover", f"{source} does not exist")
        candidates = list(ncch.find_game_files(source))
        packable = [one for one in candidates if one.kind == "card image"]
        if not packable:
            raise BuildError("discover", "no card image (.3ds/.3dz/.cci) found;"
                                         " CIA packaging is not supported")
        chosen = packable[0]
        if len(packable) > 1:
            self.say(f"{len(packable)} games found; building the first ({chosen.path.name})")
        self.progress.stage_end(stage1, chosen.path.name)
        return self.identify(chosen)

    # 2 -------------------------------------------------------------------------
    def identify(self, chosen: GameFile) -> PreparedGame:
        stage2 = self.stage(2, "identify")
        self.progress.step(stage2, f"reading {chosen.path.name}")
        title_id, partition, media_units = ncch.parse_card_image(chosen.path)
        if not partition.magic_ok:
            raise BuildError("identify", f"{chosen.path.name}: partition 0 has no NCCH header")
        self.progress.count(stage2, 1, 1, "game")
        profile = load_profile(title_id)
        build_dir = chosen.path.parent / f"{title_id}_build"
        state_text = "pin" if profile.verified_md5 else "provisional"
        self.progress.stage_end(stage2, f"serial {partition.product_code} · {title_id} · profile {state_text}")
        return PreparedGame(source=chosen.path, title_id=title_id,
                            product_code=partition.product_code, version=2,
                            media_units=media_units,
                            partition_flags=partition.flag_byte,
                            partition=partition,
                            profile=profile, build_dir=build_dir,
                            working_source=chosen.path, prepared=False)

    # 3 -------------------------------------------------------------------------
    def verify_stage(self, prepared: PreparedGame) -> None:
        stage3 = self.stage(3, "verify the dump")
        if not prepared.profile.verified_md5:
            self.progress.stage_end(stage3, "no pin in the profile: skipped")
            return
        if self.request.no_verify:
            self.progress.stage_end(stage3, "skipped (--no-verify)")
            return
        self.progress.step(stage3, "md5 full-file check (about a second per GiB)")
        import hashlib
        digest = hashlib.md5()
        size = prepared.source.stat().st_size
        read_so_far = 0
        with open(prepared.source, "rb", buffering=0) as file:
            while chunk := file.read(0x100_0000):
                digest.update(chunk)
                read_so_far += len(chunk)
                self.progress.count(stage3, read_so_far, size, "bytes", est=True)
        actual = digest.hexdigest()
        if actual != prepared.profile.verified_md5:
            message = (f"MD5 {actual} does not match the profile pin "
                       f"{prepared.profile.verified_md5}:\n  {prepared.source.name}")
            if self.request.allow_damaged:
                self.say(message + "\n  packed as read (--allow-damaged)", error=True)
                self.progress.stage_end(stage3, "mismatch, packed as read")
            else:
                raise BuildError("verify", message + "\n  (pass --allow-damaged to pack it anyway)")
        else:
            self.progress.stage_end(stage3, "MD5 verified against the profile pin")

    # 4 -------------------------------------------------------------------------
    def prepare_stage(self, prepared: PreparedGame) -> PreparedGame:
        stage4 = self.stage(4, "prepare a working copy")
        opaque = any(not part.no_crypto for part in ncch.parse_card_partitions(prepared.source))
        if not opaque:
            self.progress.stage_end(stage4, "NoCrypto partitions: the original runs as is")
            return prepared
        out_dir = prepared.build_dir / "decrypted"
        out_dir.mkdir(parents=True, exist_ok=True)
        out = out_dir / (prepared.source.stem + ".prepared.3ds")
        total = prepared.source.stat().st_size
        self.progress.count(stage4, 0, total, "bytes", est=True)
        try:
            decrypt_card_image(prepared.source, out,
                               KeySource(boot9=self.request.boot9, keys_file=self.request.keys),
                               say=lambda message: self.progress.step(stage4, message))
        except (ContainerError, Exception) as error:
            raise BuildError("prepare", f"the working copy failed: {error}") from error
        title_id, partition, _ = ncch.parse_card_image(out)
        if title_id != prepared.title_id or any(not part.no_crypto for part in ncch.parse_card_partitions(out)):
            raise BuildError("prepare", "prepared copy changed title or retains encrypted partitions")
        self.progress.count(stage4, total, total, "bytes")
        self.progress.stage_end(stage4, f"{out.name} ({out.stat().st_size:,} bytes)")
        return replace(prepared, working_source=out, prepared=True,
                       partition=partition, partition_flags=partition.flag_byte)

    # 5 -------------------------------------------------------------------------
    def aot_stage(self, prepared: PreparedGame, zakuro_stamp: str) -> AotArtifact:
        self.stage(5, "obtain the AOT library")
        return obtain_aot(self, prepared, zakuro_stamp)

    # 6 -------------------------------------------------------------------------
    def icon_stage(self, prepared: PreparedGame) -> list | None:
        stage6 = self.stage(6, "metadata and icon")
        if self.request.no_icon:
            self.progress.stage_end(stage6, "skipped (--no-icon)")
            return None
        self.progress.step(stage6, "SMDH icon (48x48, RGB565 CTR layout)")
        from dm.tools.ncch import parse_smdh
        smdh_raw = ncch.read_exefrs_file(prepared.working_source, prepared.partition, "icon")
        data = parse_smdh(smdh_raw)
        rgba = ncch.icon_rgba(data.large_icon)
        self.progress.count(stage6, 1, 1, "icon")
        self.progress.stage_end(stage6, "decoded")
        return rgba

    # 7 -------------------------------------------------------------------------
    def publish_stage(self, prepared: PreparedGame, zakuro_bin: Path, zakuro_stamp: str,
                      aot: AotArtifact, icon_pixels: list | None) -> dict:
        stage7 = self.stage(7, "pack, sign and publish")
        request = self.request
        output_dir = request.output.expanduser().resolve() if request.output else prepared.source.parent
        output_dir.mkdir(parents=True, exist_ok=True)
        rom = prepared.working_source or prepared.source
        partition = prepared.partition
        smdh_raw = ncch.read_exefrs_file(rom, partition, "icon")
        smdh = ncch.parse_smdh(smdh_raw)
        lang_index = LANGUAGE_REGION[request.language]
        title = smdh.titles.get(lang_index) or smdh.titles.get(1) or next(iter(smdh.titles.values()), ())
        long_title = (title[1] or title[0]) if title else "Game"
        app_name = (request.app_name or pack_app.app_name_from_smdh(long_title)).replace("\n", " - ").strip()
        app_path = output_dir / f"{app_name}.app"
        hints_path = aot.hints_path
        extra_files = [
            (zakuro_bin, app_path / "Contents/MacOS/zakuro-host"),
            (aot.dylib, app_path / "Contents/Resources/game" / f"{prepared.title_id}.dylib"),
        ]
        if hints_path and hints_path.is_file():
            extra_files.append((hints_path, app_path / "Contents/Resources/game" / f"{prepared.title_id}.hints"))
        inputs = pack_app.PackInputs(
            rom_path=rom,
            whom=app_path,
            host_bin=zakuro_bin,
            host_version=zakuro_stamp,
            toolkit_version=request.toolkit_version,
            profile_hash=prepared.profile.verified_md5,
            icon_png=None,
            launcher_args=[],
            extra_files=extra_files,
            zakuro_bin=zakuro_bin,
            recompiled_dylib=aot.dylib,
            scale=request.scale,
        )
        inputs.host_bin_launcher = app_path / "Contents/MacOS/zakuro-host"
        inputs.recompiled_dylib_launcher = app_path / "Contents/Resources/game" / f"{prepared.title_id}.dylib"
        reused = pack_app.pack(
            app=app_path, app_name=app_name, title_id=prepared.title_id,
            version="1.0.0", language=request.language, inputs=inputs,
            icon_pixels=icon_pixels, icon_size=(48, 48),
            say=lambda message: self.progress.step(stage7, message),
        )
        sandbox = pack_app.sandbox_of(app_path)
        self.progress.stage_end(stage7, f"sandbox ready ({'reused' if reused else 'fresh'}) · host zakuro")
        logs = prepared.build_dir / "logs"
        logs.mkdir(parents=True, exist_ok=True)
        (logs / "pack.tsv").write_text("\n".join([
            f"appid\t{pack_app.app_bundle_id(prepared.title_id)}",
            f"app\t{app_path}",
            f"language\t{request.language}",
            f"profile\tpin in dm/games/{prepared.title_id}/profile.tsv",
        ]) + "\n")
        return {"app": app_path, "sandbox_home": sandbox["home"],
                "rom": rom, "reused": reused,
                "host_bin_launcher": inputs.host_bin_launcher,
                "dylib_launcher": inputs.recompiled_dylib_launcher}

    # 8 -------------------------------------------------------------------------
    def smoke_stage(self, prepared: PreparedGame, published: dict) -> SmokeResult | None:
        stage8 = self.stage(8, "verify the app")
        if not self.request.launch:
            self.progress.stage_end(stage8, "not launched (pass --launch to open it)")
            return None
        from dm.tools.runtime import environment, headless_command
        app = published["app"]
        env = environment(published["sandbox_home"])
        command = headless_command(published["host_bin_launcher"], rom=published["rom"],
                                   dylib=published["dylib_launcher"],
                                   language=self.request.language, scale=self.request.scale)
        completed = self.runner(command, env=env, timeout=180)
        output = (completed.stdout or "") + (completed.stderr or "")
        self.progress.count(stage8, 1, 1, "smoke")
        if completed.returncode == 0 and "Completed after" in output:
            lines = output.strip().splitlines()
            note = lines[-2].strip() if len(lines) > 1 else ""
            subprocess.run(["/usr/bin/open", str(app)],
                           check=True, capture_output=True)
            self.progress.stage_end(stage8, f"headless smoke passed · host zakuro ({note[:60]})")
            return SmokeResult(passed=True, opened=True, note=note)
        raise BuildError("verify the app", f"headless smoke failed:\n{output[-800:]}")

    # shared --------------------------------------------------------------
    def resolve_zakuro(self) -> Path:
        zakuro_bin = self.request.zakuro_bin or (self.request.root / "vendors/zakuro/target/release/zakuro")
        if not zakuro_bin.exists():
            raise BuildError("pack", f"the zakuro host is missing at {zakuro_bin}:\n"
                                     "  build it once: cd vendors/zakuro &&"
                                     " cargo build --release --locked --workspace\n")
        return zakuro_bin


def file_stamp(path: Path) -> str:
    stat = path.stat()
    return f"{stat.st_size}:{stat.st_mtime_ns}"
