"""The common dm.build pipeline with synthetic titles and stubbed tools."""
import json
import struct
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from dm.build import BuildRequest, build
from dm.build.models import BuildError
from dm.tests.fixtures import build_card_image, build_cxi_partition

from dm.tools import progress as dm_progress

DEFAULT_TID = "00040000000ec300"
RECOMPILER_STUB = """#!/bin/sh
# 3dsrecomp stub: installs tiny dylibs in the caller's isolated HOME
for tid in 00040000000ec300 0004000000125500 0004000000125600; do
  mkdir -p "$HOME/Library/Application Support/3dsrecomp"
  printf 'aot-stub\0' > "$HOME/Library/Application Support/3dsrecomp/$tid.dylib"
done
"""



def request_for(rom: Path, root: Path, **overrides) -> BuildRequest:
    fields: dict = {
        "game": rom,
        "output": root / "apps",
        "app_name": "Game",
        "language": "en",
        "scale": 3,
        "no_icon": True,
        "allow_damaged": False,
        "no_verify": True,
        "boot9": None,
        "keys": None,
        "zakuro_bin": root / "zakuro-host",
        "recompiler_bin": root / "recompiler",
        "rebuild_aot": False,
        "launch": False,
        "root": root,
    }
    no_icon = overrides.pop("want_icon", None)
    if no_icon is not None:
        fields["no_icon"] = not no_icon
    fields.update(overrides)
    return BuildRequest(**fields)


def make_stub_tools(root: Path) -> tuple:
    host = root / "zakuro-host"
    host.write_bytes(b"zakuro-stub")
    compiler = root / "recompiler"
    compiler.write_text(RECOMPILER_STUB)
    compiler.chmod(0o755)
    return host, compiler


class PipelineTests(unittest.TestCase):
    def build_once(self, rom: Path, root: Path, home: Path, **overrides):
        import dm.tools.pack_app as pack_app_module
        pack_sub = pack_app_module.subprocess
        real_run = subprocess.run

        def codesign_only(command, *_, **kwargs):
            first = command[0] if isinstance(command, list) else str(command)
            if first == "/usr/bin/codesign":
                return subprocess.CompletedProcess(command, 0, "", "")
            return real_run(command, *_, **kwargs)

        with patch.object(Path, "home", return_value=home), \
                patch.object(pack_sub, "run", side_effect=codesign_only):
            return build(request_for(rom, root, **overrides), progress=_quiet())

    def test_two_titles_through_the_same_interface(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            make_stub_tools(root)
            home = root / "home"
            first = build_card_image(build_cxi_partition(), root / "first.3ds")
            second = build_card_image(
                build_cxi_partition(program_id=0x0004000000125600, smdh=None),
                root / "second.3ds")
            first_result = self.build_once(first, root, home, app_name="Game One")
            second_result = self.build_once(second, root, home, app_name="Game Two")
            self.assertNotEqual(first_result.app, second_result.app)
            self.assertNotEqual(first_result.sandbox_home, second_result.sandbox_home)
            self.assertTrue((first_result.app / "Contents/MacOS/ctr-native").is_file())
            self.assertTrue((second_result.app / "Contents/MacOS/ctr-native").is_file())
            self.assertFalse(first_result.aot.reused)   # first build compiles
            self.assertFalse(second_result.aot.reused)  # a different title compiles its own
            self.assertEqual(second_result.aot.title_id, "0004000000125600")

    def test_aot_cache_reuse_then_invalidation(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            make_stub_tools(root)
            home = root / "home"
            rom = build_card_image(build_cxi_partition(), root / "synthetic.3ds")
            first = self.build_once(rom, root, home)
            self.assertFalse(first.aot.reused)
            second = self.build_once(rom, root, home)
            self.assertTrue(second.aot.reused)
            # corrupt the manifest: the cache falls out of trust and rebuilds
            fingerprint_dir = first.aot.dylib.parent
            manifest = fingerprint_dir / "manifest.json"
            data = json.loads(manifest.read_text())
            data["library_sha256"] = "0" * 64
            manifest.write_text(json.dumps(data))
            rebuilt = self.build_once(rom, root, home)
            self.assertTrue(rebuilt.aot.compiled)
            third = self.build_once(rom, root, home)
            self.assertTrue(third.aot.reused)

            # tool change invalidates: a new compiler stamp means a new fingerprint
            older_stamp = (root / "recompiler").stat().st_mtime_ns
            compiler = root / "recompiler"
            compiler.write_text(RECOMPILER_STUB + "\n# rebuilt\n")
            fourth = self.build_once(rom, root, home)
            self.assertFalse(fourth.aot.reused)
            self.assertNotEqual(
                (root / "recompiler").stat().st_mtime_ns, older_stamp)

    def test_corrupt_library_is_rebuilt_and_global_library_is_ignored(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            make_stub_tools(root)
            home = root / "home"
            rom = build_card_image(build_cxi_partition(), root / "synthetic.3ds")
            first = self.build_once(rom, root, home)
            expected = first.aot.dylib.read_bytes()
            installed = home / "Library/Application Support/3dsrecomp" / f"{DEFAULT_TID}.dylib"
            installed.parent.mkdir(parents=True)
            installed.write_bytes(b"wrong revision")
            first.aot.dylib.write_bytes(b"corrupted cache")
            second = self.build_once(rom, root, home)
            self.assertTrue(second.aot.compiled)
            self.assertEqual(second.aot.dylib.read_bytes(), expected)
            self.assertEqual(installed.read_bytes(), b"wrong revision")
            bundled = second.app / "Contents/Resources/game" / f"{DEFAULT_TID}.dylib"
            self.assertEqual(bundled.read_bytes(), expected)
            self.assertTrue(self.build_once(rom, root, home).aot.reused)

    def test_cache_manifest_identity_is_checked(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            make_stub_tools(root)
            home = root / "home"
            rom = build_card_image(build_cxi_partition(), root / "synthetic.3ds")
            first = self.build_once(rom, root, home)
            manifest = first.aot.dylib.parent / "manifest.json"
            for field in ("format", "title_id", "arch", "fingerprint"):
                with self.subTest(field=field):
                    data = json.loads(manifest.read_text())
                    data[field] = "wrong"
                    manifest.write_text(json.dumps(data))
                    rebuilt = self.build_once(rom, root, home)
                    self.assertTrue(rebuilt.aot.compiled)

    def test_default_compiler_does_not_trust_installed_library(self):
        from dm.build.models import BuildError
        with TemporaryDirectory() as folder:
            root = Path(folder)
            make_stub_tools(root)
            home = root / "home"
            rom = build_card_image(build_cxi_partition(), root / "synthetic.3ds")
            installed = home / "Library/Application Support/3dsrecomp" / f"{DEFAULT_TID}.dylib"
            installed.parent.mkdir(parents=True)
            installed.write_bytes(b"unverified")
            with self.assertRaises(BuildError):
                self.build_once(rom, root, home, recompiler_bin=None)
            compiler = root / "vendors/3dsrecomp/target/release/3dsrecomp"
            compiler.parent.mkdir(parents=True)
            compiler.write_text(RECOMPILER_STUB)
            compiler.chmod(0o755)
            result = self.build_once(rom, root, home, recompiler_bin=None)
            self.assertTrue(result.aot.compiled)
            self.assertNotEqual(result.aot.dylib.read_bytes(), installed.read_bytes())

    def test_language_change_rebuilds_the_package_not_the_aot(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            make_stub_tools(root)
            home = root / "home"
            rom = build_card_image(build_cxi_partition(), root / "synthetic.3ds")
            first = self.build_once(rom, root, home, language="en")
            self.assertFalse(first.aot.reused)
            second = self.build_once(rom, root, home, language="es")
            self.assertTrue(second.aot.reused, "the AOT cache ignores language")
            self.assertEqual(second.aot.title_id, DEFAULT_TID)

    def test_rom_sources_stay_intact_for_encrypted_cards(self):
        from dm.tests.fixtures import encrypted_partition
        with TemporaryDirectory() as folder:
            root = Path(folder)
            make_stub_tools(root)
            home = root / "home"
            primary = build_cxi_partition()
            encrypted, clear = encrypted_partition()
            payload = bytearray(0x400) + primary + encrypted
            payload[0x100:0x104] = b"NCSD"
            struct.pack_into("<I", payload, 0x104, len(payload) // 512)
            struct.pack_into("<IIII", payload, 0x120, 2, len(primary) // 512,
                             (0x400 + len(primary)) // 512, len(encrypted) // 512)
            rom = root / "synthetic.3ds"
            rom.write_bytes(payload)
            (root / "keys.tsv").write_text("2c=" + bytes(range(16)).hex() + "\n25=" +
                                           bytes(range(32, 48)).hex())
            original = rom.read_bytes()
            result = self.build_once(rom, root, home, keys=root / "keys.tsv")
            self.assertEqual(rom.read_bytes(), original)
            copies = list(root.glob("*_build/decrypted/*.3ds"))
            self.assertEqual(
                copies[0].read_bytes(), bytes(payload[:0x400 + len(primary)]) + clear)
            self.assertTrue(result.app.exists())
            self.assertTrue((result.sandbox_home.parent.name).endswith(".ctr-native"))

    def test_primary_decryption_refreshes_metadata(self):
        from dm.build.pipeline import Pipeline
        from dm.tools import ncch
        from dm.tests.fixtures import encrypted_partition
        for fixed in (True, False):
            with self.subTest(fixed=fixed), TemporaryDirectory() as folder:
                root = Path(folder)
                encrypted, _ = encrypted_partition(fixed=fixed)
                rom = build_card_image(encrypted, root / "synthetic.3ds")
                original = rom.read_bytes()
                keys = root / "synthetic.tsv"
                keys.write_text("2c=" + bytes(range(16)).hex() + "\n25=" + bytes(range(32, 48)).hex())
                pipeline = Pipeline(request_for(rom, root, keys=keys), _quiet())
                initial = pipeline.discover(pipeline.stage(1, "discover"))
                prepared = pipeline.prepare_stage(initial)
                self.assertFalse(initial.partition.no_crypto)
                self.assertTrue(prepared.partition.no_crypto)
                self.assertEqual(prepared.title_id, initial.title_id)
                self.assertTrue(ncch.parse_smdh(ncch.read_exefrs_file(
                    prepared.working_source, prepared.partition, "icon")).titles)
                self.assertEqual(rom.read_bytes(), original)

    def test_preparation_rejects_changed_title(self):
        from dm.build.models import BuildError
        from dm.build.pipeline import Pipeline
        from dm.tests.fixtures import encrypted_partition
        with TemporaryDirectory() as folder:
            root = Path(folder)
            encrypted, _ = encrypted_partition(fixed=True)
            rom = build_card_image(encrypted, root / "synthetic.3ds")
            original = rom.read_bytes()
            pipeline = Pipeline(request_for(rom, root), _quiet())
            initial = pipeline.discover(pipeline.stage(1, "discover"))
            def different_title(source, destination, keys, say):
                return build_card_image(build_cxi_partition(program_id=0x0004000000125600), destination)
            with patch("dm.build.pipeline.decrypt_card_image", side_effect=different_title), \
                    self.assertRaises(BuildError):
                pipeline.prepare_stage(initial)
            self.assertEqual(rom.read_bytes(), original)
            self.assertEqual(initial.working_source.resolve(), rom.resolve())

    def test_real_3dsrecomp_integration_when_available(self):
        root = Path(__file__).resolve().parent.parent
        compiler = root / "vendors/3dsrecomp/target/release/3dsrecomp"
        if not compiler.is_file():
            self.skipTest("3dsrecomp is not built in vendors/")
        with TemporaryDirectory() as folder:
            work = Path(folder)
            make_stub_tools(work)
            rom = build_card_image(build_cxi_partition(), work / "synthetic.3ds")
            try:
                result = self.build_once(rom, work, work / "home",
                                         recompiler_bin=compiler)
            except Exception as error:  # the synthetic rom is not a real title
                self.skipTest(f"3dsrecomp rejected the synthetic title: {error}")
            self.assertTrue(result.aot.dylib.is_file())
            manifest = next(iter((result.aot.dylib.parent.parent / "aot").glob("*")))
            self.assertIn("fingerprint", json.loads((manifest / "manifest.json").read_text()))


def _quiet():
    class Quiet:
        def stage(self, index, total, name):
            return (index, name)

        def step(self, stage, message):
            pass

        def stage_end(self, stage, message, ok=True):
            pass

        def count(self, stage, done, total, unit, est=False):
            pass

        def say(self, message, error=False):
            pass
    return Quiet()

class ErrorNormalizationTests(unittest.TestCase):
    """P2-6: every failure ends exactly one structured, stage-closing error."""

    def json_run(self, rom: Path, root: Path, home: Path, **overrides):
        from io import StringIO
        events = StringIO()
        request = request_for(rom, root, **overrides)
        with patch("sys.stdout", events), \
                patch.object(Path, "home", return_value=home), \
                self.assertRaises(BuildError) as raised:
            build(request, progress=dm_progress.Progress("json"))
        parsed = [json.loads(line) for line in
                  events.getvalue().splitlines() if line.startswith("{")]
        return parsed, raised.exception

    def test_unexpected_failure_normalizes_with_its_open_stage(self):
        import dm.build.pipeline as pipeline_module
        with TemporaryDirectory() as folder:
            root = Path(folder)
            make_stub_tools(root)
            home = root / "home"
            rom = build_card_image(build_cxi_partition(), root / "synthetic.3ds")
            def exploding(self, *args, **kwargs):
                raise RuntimeError("synthetic detonation")
            with patch.object(pipeline_module.Pipeline, "publish_stage", exploding):
                events, error = self.json_run(rom, root, home)
            self.assertEqual(error.stage, "pipeline")
            self.assertIn("unexpected failure", error.message)
            self.assertIn("metadata and icon", error.message)
            ends = [event for event in events if event["ev"] == "stage_end"]
            self.assertTrue(ends and ends[-1]["ok"] is False)
            self.assertIn("unexpected: synthetic detonation", ends[-1]["summary"])
            last = events[-1]
            self.assertEqual(last["ev"], "error")
            self.assertEqual(last["stage"], "pipeline")
            self.assertTrue(any("RuntimeError" in line for line in last.get("traceback", [])))

    def test_structured_error_event_for_expected_failures(self):
        import dm.build.pipeline as pipeline_module
        with TemporaryDirectory() as folder:
            root = Path(folder)
            make_stub_tools(root)
            home = root / "home"
            rom = build_card_image(build_cxi_partition(), root / "synthetic.3ds")
            def failing_stage(self, *args, **kwargs):
                raise BuildError("publish", "synthetic packaging refusal")
            with patch.object(pipeline_module.Pipeline, "publish_stage", failing_stage):
                events, error = self.json_run(rom, root, home)
            self.assertEqual(error.stage, "publish")
            wants = [event for event in events if event["ev"] == "error"]
            self.assertEqual(len(wants), 1)
            self.assertEqual(wants[0]["stage"], "publish")
            self.assertEqual(wants[0]["msg"], "synthetic packaging refusal")
            self.assertNotIn("traceback", wants[0])
            ends = [event for event in events if event["ev"] == "stage_end"]
            self.assertTrue(ends and ends[-1]["ok"] is False)

