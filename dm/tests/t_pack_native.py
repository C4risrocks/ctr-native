"""Real macOS bundle smoke with manufactured code and assets only."""
import os
import plistlib
import subprocess
import sys
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from dm.tests.fixtures import synthetic_icon
from dm.tools import ncch, pack_app


@unittest.skipUnless(sys.platform == 'darwin', 'requires macOS signing and icon tools')
class TestNativePack(unittest.TestCase):
    def test_signed_bundle_reuse_rebuild_and_launcher(self):
        with TemporaryDirectory(prefix='ctr-native-smoke-') as folder:
            root = Path(folder)
            source = root / 'host.c'
            source.write_text('#include <stdio.h>\n#include <stdlib.h>\n'
                              'int main(int argc,char **argv) { puts(getenv("HOME")); '
                              'for(int i=1;i<argc;i++) puts(argv[i]); return 0; }\n')
            host = root / 'host'
            subprocess.run(['/usr/bin/clang', str(source), '-o', str(host)], check=True, capture_output=True)
            source.write_text('int synthetic(void) { return 0; }\n')
            library = root / 'synthetic.dylib'
            subprocess.run(['/usr/bin/clang', '-dynamiclib', str(source), '-o', str(library)],
                           check=True, capture_output=True)
            rom = root / 'synthetic.3ds'
            rom.write_bytes(b'synthetic input, no game data')
            app = root / 'Synthetic.app'
            bundled_host = app / 'Contents/MacOS/zakuro-host'
            bundled_lib = app / 'Contents/Resources/game/synthetic.dylib'
            inputs = pack_app.PackInputs(rom, app, host, 'test', 'test', '', None, [],
                                        extra_files=[(host, bundled_host), (library, bundled_lib)],
                                        host_bin_launcher=bundled_host,
                                        recompiled_dylib_launcher=bundled_lib, scale=3)
            pixels = ncch.icon_rgba(synthetic_icon())
            def build(language='en', config=inputs):
                return pack_app.pack(app, 'Synthetic', '0004000000000000', '1', language,
                                     config, pixels, (48, 48), say=lambda _: None)
            self.assertFalse(build())
            self.assertTrue(build())
            pixels[0] = (0, 0, 255, 255)
            self.assertFalse(build())
            self.assertTrue(build())
            self.assertFalse(build('es', replace(inputs, scale=7)))
            plist = plistlib.loads((app / 'Contents/Info.plist').read_bytes())
            self.assertTrue((app / 'Contents/Resources' / (plist['CFBundleIconFile'] + '.icns')).is_file())
            env = {key: value for key, value in os.environ.items() if key != 'HOME'}
            result = subprocess.run([str(app / 'Contents/MacOS/ctr-native')], env=env,
                                    check=True, capture_output=True, text=True)
            lines = result.stdout.splitlines()
            self.assertEqual(lines[0], str(pack_app.sandbox_of(app)['home']))
            self.assertIn('--language', lines)
            self.assertEqual(lines[lines.index('--language') + 1], 'es')
            self.assertEqual(lines[lines.index('--scale') + 1], '7')
            bundled_host.unlink()
            self.assertFalse(build())
            pack_app.verify_bundle(app, [Path('Contents/MacOS/zakuro-host'),
                                        Path('Contents/Resources/game/synthetic.dylib')])
