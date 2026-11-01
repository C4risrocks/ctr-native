"""Public CLI progress and launch ordering with synthetic host dependencies."""
import contextlib
import io
import json
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from dm.tests.fixtures import build_card_image, build_cxi_partition, build_smdh
from scripts import build_app_from_3ds as builder


class TestBuilder(unittest.TestCase):
    def setUp(self):
        # CLI tests manufacture the native dependency at the AOT interface;
        # cache provenance and actual recompilation are tested in t_build.
        from dm.build.models import AotArtifact
        def synthetic_aot(flow, prepared, stamp):
            library = Path.home() / "Library/Application Support/3dsrecomp" / f"{prepared.title_id}.dylib"
            flow.stage_end("synthetic AOT dependency")
            return AotArtifact(prepared.title_id, library, None, "synthetic", True)
        adapter = patch("dm.build.pipeline.obtain_aot", side_effect=synthetic_aot)
        adapter.start()
        self.addCleanup(adapter.stop)

    def test_cleanup_is_confined_to_current_extract(self):
        from types import SimpleNamespace
        for directory_input in (False, True):
            with self.subTest(directory_input=directory_input), TemporaryDirectory() as folder:
                root = Path(folder)
                inputs = root / "roms"
                inputs.mkdir()
                rom = inputs / "synthetic.3ds"
                rom.write_bytes(b"synthetic")
                build_dir = inputs / "current_build"
                extract = build_dir / "extract"
                extract.mkdir(parents=True)
                (extract / "temporary").write_text("temporary")
                protected = [root / "unrelated_build/keep", build_dir / "decrypted/rom",
                             build_dir / "aot/library", inputs / "Game.app.ctr-native/save"]
                for path in protected:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text("keep")
                result = SimpleNamespace(build_dir=build_dir)
                with patch.object(builder, "build", return_value=result), contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(builder.main([str(inputs if directory_input else rom),
                                                  "--no-keep-directories"]), 0)
                self.assertFalse(extract.exists())
                self.assertTrue(all(path.read_text() == "keep" for path in protected))

    def test_cleanup_refuses_linked_extract(self):
        from types import SimpleNamespace
        with TemporaryDirectory() as folder:
            root = Path(folder)
            build_dir = root / "current_build"
            build_dir.mkdir()
            outside = root / "outside"
            outside.mkdir()
            sentinel = outside / "save"
            sentinel.write_text("keep")
            (build_dir / "extract").symlink_to(outside, target_is_directory=True)
            with patch.object(builder, "build", return_value=SimpleNamespace(build_dir=build_dir)), \
                    contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(builder.main([str(root), "--no-keep-directories"]), 1)
            self.assertEqual(sentinel.read_text(), "keep")

    def test_scale_must_be_positive(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            builder.parse_args(['synthetic.3ds', '--scale', '0'])

    def test_empty_smdh_titles_have_a_name_and_json_finishes(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            rom = build_card_image(build_cxi_partition(smdh=build_smdh(short='', long_title='', publisher='')),
                                   root / 'synthetic.3ds')
            host = root / 'host'
            host.write_bytes(b'synthetic')
            library = root / 'Library/Application Support/3dsrecomp/00040000000ec300.dylib'
            library.parent.mkdir(parents=True)
            library.write_bytes(b'synthetic')
            output = io.StringIO()
            with patch.object(Path, 'home', return_value=root), \
                    patch('dm.tools.pack_app.subprocess.run',
                          return_value=subprocess.CompletedProcess([], 0, '', '')), \
                    contextlib.redirect_stdout(output):
                result = builder.main([str(rom), '--zakuro-bin', str(host), '--no-icon',
                                       '--no-verify', '--progress', 'json'])
            self.assertEqual(result, 0)
            self.assertTrue((root / 'Game.app/Contents/MacOS/ctr-native').is_file())
            events = [json.loads(line) for line in output.getvalue().splitlines()]
            ends = [event for event in events if event['ev'] == 'stage_end']
            self.assertEqual([event['k'] for event in ends], list(range(1, ends[-1]['n'] + 1)))
            self.assertTrue(all(event['n'] == ends[-1]['n'] for event in ends))

    def test_failure_is_a_closed_json_stage(self):
        output = io.StringIO()
        with TemporaryDirectory() as folder, contextlib.redirect_stdout(output):
            result = builder.main([folder, '--progress', 'json'])
        self.assertEqual(result, 1)
        events = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertTrue(any(event['ev'] == 'stage_end' and not event['ok'] for event in events))

    def test_secondary_encryption_is_processed_even_with_clear_primary(self):
        import struct
        from dm.tests.fixtures import encrypted_partition
        real_run = subprocess.run
        def system_tool(command, *args, **kwargs):
            if command[0] == '/usr/bin/codesign':
                return subprocess.CompletedProcess(command, 0, '', '')
            return real_run(command, *args, **kwargs)
        for fixed in (True, False):
            with self.subTest(fixed=fixed), TemporaryDirectory() as folder:
                root = Path(folder)
                primary = build_cxi_partition()
                encrypted, clear = encrypted_partition(fixed=fixed)
                payload = bytearray(0x400) + primary + encrypted
                payload[0x100:0x104] = b'NCSD'
                struct.pack_into('<I', payload, 0x104, len(payload) // 512)
                struct.pack_into('<IIII', payload, 0x120, 2, len(primary) // 512,
                                 (0x400 + len(primary)) // 512, len(encrypted) // 512)
                rom = root / 'synthetic.3ds'
                rom.write_bytes(payload)
                host = root / 'host'
                host.write_bytes(b'synthetic')
                library = root / 'Library/Application Support/3dsrecomp/00040000000ec300.dylib'
                library.parent.mkdir(parents=True)
                library.write_bytes(b'synthetic')
                keys = root / 'synthetic-table.tsv'
                keys.write_text('2c=' + bytes(range(16)).hex() + '\n25=' + bytes(range(32, 48)).hex())
                argv = [str(rom), '--zakuro-bin', str(host), '--no-icon', '--no-verify', '--progress', 'json']
                if not fixed:
                    argv += ['--keys', str(keys)]
                output = io.StringIO()
                with patch.object(Path, 'home', return_value=root), \
                        patch('subprocess.run', side_effect=system_tool), contextlib.redirect_stdout(output):
                    result = builder.main(argv)
                self.assertEqual(result, 0, output.getvalue())
                self.assertEqual(rom.read_bytes(), payload)
                copies = list(root.glob('*_build/decrypted/*.3ds'))
                self.assertEqual(len(copies), 1)
                self.assertEqual(copies[0].read_bytes(), bytes(payload[:0x400 + len(primary)]) + clear)
                self.assertTrue(any(root.glob('*.app/Contents/MacOS/ctr-native')))
