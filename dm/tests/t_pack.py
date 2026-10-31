"""Bundle publication contract, using synthetic inputs and a fake system signer."""
import subprocess
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from dm.tools import pack_app


class TestPack(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.rom = self.root / 'synthetic.3ds'
        self.host = self.root / 'host'
        self.lib = self.root / 'synthetic.dylib'
        for path in (self.rom, self.host, self.lib):
            path.write_bytes(b'synthetic')
        self.app = self.root / 'Synthetic.app'
        self.inputs = pack_app.PackInputs(
            self.rom, self.app, self.host, 'test', 'test', '', None, [],
            extra_files=[(self.host, self.app / 'Contents/MacOS/zakuro-host'),
                         (self.lib, self.app / 'Contents/Resources/game/test.dylib')],
            host_bin_launcher=self.app / 'Contents/MacOS/zakuro-host',
            recompiled_dylib_launcher=self.app / 'Contents/Resources/game/test.dylib', scale=3)
        self.signer = patch('dm.tools.pack_app.subprocess.run',
                            return_value=subprocess.CompletedProcess([], 0, '', ''))
        self.signer.start()
        self.addCleanup(self.signer.stop)

    def build(self, **kwargs):
        return pack_app.pack(self.app, 'Synthetic', '0004000000000000', '1',
                             kwargs.pop('language', 'en'), kwargs.pop('inputs', self.inputs),
                             kwargs.pop('icon_pixels', None), (48, 48), say=lambda _: None, **kwargs)

    def test_signing_failure_does_not_publish_candidate(self):
        with patch('dm.tools.pack_app.subprocess.run',
                   return_value=subprocess.CompletedProcess([], 1, '', 'synthetic signer failure')), \
                self.assertRaises(pack_app.PackError):
            self.build()
        self.assertFalse(self.app.exists())
        self.assertFalse(self.build())
        self.assertTrue(self.build())

    def test_failed_rebuild_preserves_previous_bundle(self):
        self.build()
        old = (self.app / 'Contents/MacOS/ctr-native').read_bytes()
        self.host.write_bytes(b'changed')
        with patch('dm.tools.pack_app.subprocess.run',
                   return_value=subprocess.CompletedProcess([], 1, '', 'failure')), \
                self.assertRaises(pack_app.PackError):
            self.build()
        self.assertEqual((self.app / 'Contents/MacOS/ctr-native').read_bytes(), old)
        self.assertEqual((self.app / 'Contents/MacOS/zakuro-host').read_bytes(), b'synthetic')

    def test_effective_launcher_and_settings_invalidate_reuse(self):
        self.build()
        self.assertFalse(self.build(language='es', inputs=replace(self.inputs, scale=7)))
        launcher = (self.app / 'Contents/MacOS/ctr-native').read_text()
        self.assertIn('--language es', launcher)
        self.assertIn('--scale 7', launcher)
        self.assertIn('export HOME=', launcher)

    def test_content_hash_detects_changes_with_preserved_stamp(self):
        import os
        self.build()
        stamp = self.lib.stat()
        self.lib.write_bytes(b'SYNTHETIC')
        os.utime(self.lib, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
        self.assertFalse(self.build())

    def test_missing_dependency_is_rebuilt(self):
        self.build()
        (self.app / 'Contents/MacOS/zakuro-host').unlink()
        self.assertFalse(self.build())
        self.assertTrue((self.app / 'Contents/MacOS/zakuro-host').exists())

    def test_foreign_destination_is_rejected(self):
        inputs = replace(self.inputs, extra_files=[(self.host, self.root / 'outside')])
        with self.assertRaises(pack_app.PackError):
            self.build(inputs=inputs)
        self.assertFalse((self.root / 'outside').exists())
