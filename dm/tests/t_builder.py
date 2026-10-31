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
