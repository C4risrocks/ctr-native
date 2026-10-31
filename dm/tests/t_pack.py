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

    def test_migration_conflicts_do_not_touch_either_save(self):
        legacy = self.app / 'Contents/MacOS/sandbox/home/save.dat'
        current = pack_app.sandbox_of(self.app)['home'] / 'save.dat'
        legacy.parent.mkdir(parents=True)
        current.parent.mkdir(parents=True)
        legacy.write_bytes(b'OLD')
        current.write_bytes(b'NEW')
        with patch('dm.tools.user_data.runtime_in_use', return_value=False), self.assertRaises(pack_app.PackError):
            self.build()
        self.assertEqual(legacy.read_bytes(), b'OLD')
        self.assertEqual(current.read_bytes(), b'NEW')
        self.assertFalse((self.app / 'Contents/MacOS/ctr-native').exists())

    def test_migration_keeps_an_archive_of_the_original(self):
        legacy = self.app / 'Contents/MacOS/sandbox/home/save.dat'
        legacy.parent.mkdir(parents=True)
        legacy.write_bytes(b'OLD')
        with patch('dm.tools.user_data.runtime_in_use', return_value=False):
            self.build()
        self.assertEqual((pack_app.sandbox_of(self.app)['home'] / 'save.dat').read_bytes(), b'OLD')
        archive = self.app.with_name(self.app.name + '.ctr-native-legacy')
        self.assertEqual((archive / 'Contents/MacOS/sandbox/home/save.dat').read_bytes(), b'OLD')

    def test_migration_refuses_a_running_app(self):
        legacy = self.app / 'Contents/MacOS/sandbox/home/save.dat'
        legacy.parent.mkdir(parents=True)
        legacy.write_bytes(b'OLD')
        with patch('dm.tools.user_data.runtime_in_use', return_value=True), self.assertRaises(pack_app.PackError):
            self.build()
        self.assertFalse(pack_app.sandbox_of(self.app)['home'].exists())
        self.assertEqual(legacy.read_bytes(), b'OLD')

    def test_archive_failure_preserves_recovery_bundle(self):
        legacy = self.app / 'Contents/MacOS/sandbox/home/save.dat'
        legacy.parent.mkdir(parents=True)
        legacy.write_bytes(b'OLD')
        original_replace = Path.replace
        def fail_archive(path, destination):
            if str(destination).endswith('.ctr-native-legacy'):
                raise OSError('synthetic archive failure')
            return original_replace(path, destination)
        with patch('dm.tools.user_data.runtime_in_use', return_value=False), \
                patch.object(Path, 'replace', fail_archive), self.assertRaisesRegex(pack_app.PackError, 'preserved at'):
            self.build()
        recovered = list(self.root.glob('.Synthetic-*.app/Contents/MacOS/sandbox/home/save.dat'))
        self.assertEqual(len(recovered), 1)
        self.assertEqual(recovered[0].read_bytes(), b'OLD')

    def test_migration_rejects_linked_ancestors(self):
        foreign = self.root / 'foreign'
        legacy = foreign / 'MacOS/sandbox/home/save.dat'
        legacy.parent.mkdir(parents=True)
        legacy.write_bytes(b'FOREIGN')
        self.app.mkdir()
        (self.app / 'Contents').symlink_to(foreign, target_is_directory=True)
        with patch('dm.tools.user_data.runtime_in_use', return_value=False), self.assertRaises(pack_app.PackError):
            self.build()
        self.assertFalse(pack_app.sandbox_of(self.app)['home'].exists())
        self.assertEqual(legacy.read_bytes(), b'FOREIGN')

    def test_failed_publication_can_retry_migration(self):
        legacy = self.app / 'Contents/MacOS/sandbox/home/save.dat'
        legacy.parent.mkdir(parents=True)
        legacy.write_bytes(b'OLD')
        with patch('dm.tools.user_data.runtime_in_use', return_value=False):
            with patch('dm.tools.pack_app.publish_bundle', side_effect=OSError('temporary failure')), \
                    self.assertRaises(OSError):
                self.build()
            self.assertFalse((pack_app.sandbox_of(self.app)['home'] / 'save.dat').exists())
            self.assertFalse(self.build())
        self.assertEqual((pack_app.sandbox_of(self.app)['home'] / 'save.dat').read_bytes(), b'OLD')
