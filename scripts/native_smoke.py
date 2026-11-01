#!/usr/bin/env python3
"""Exercise native presentation with synthetic GPU pixels and isolated player data."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dm.tools.runtime import environment  # noqa: E402
COMPLETE = re.compile(r'presentation test complete: (\d+) frames in ([\d.]+)s \(([\d.]+) fps\)')
CASES = (
    ('single-vulkan', ['--split', 'off'], {}, False, True),
    ('shared-vulkan', ['--split', 'on'], {}, True, True),
    ('shared-window-cycle', ['--split', 'on'], {'ZAKURO_TEST_WINDOW_CYCLE': '1'}, True, True),
    ('vulkan-to-gl', ['--split', 'on'], {'ZAKURO_TEST_COMPANION_GL': '1'}, False, True),
    ('two-gl-contexts', ['--split', 'on', '--renderer', 'gl'], {}, False, False),
    ('single-metal', ['--renderer', 'metal'], {}, False, False),
    ('shared-metal', ['--split', 'on', '--renderer', 'metal'], {}, False, False),
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', type=Path, default=ROOT / 'vendors/zakuro/target/release/zakuro')
    parser.add_argument('--frames', type=int, default=120)
    parser.add_argument('--validation-layer-dir', type=Path)
    args = parser.parse_args(argv)
    if args.frames < 80:
        parser.error('--frames must be at least 80 to cover the window lifecycle')
    host = args.host.resolve()
    try:
        for name, flags, switches, shared, gpu in CASES:
            with TemporaryDirectory(prefix='ctr-native-window-test-') as directory:
                root = Path(directory)
                env = environment(root / 'home', extra={'RUST_LOG': 'info'})
                for key in ('ZAKURO_TEST_COMPANION_GL', 'ZAKURO_TEST_WINDOW_CYCLE', 'ZAKURO_COPY_SCREENS'):
                    env.pop(key, None)
                env.update(switches)
                if args.validation_layer_dir:
                    env['VK_LAYER_PATH'] = str(args.validation_layer_dir.resolve())
                    env['VK_INSTANCE_LAYERS'] = 'VK_LAYER_KHRONOS_validation'
                    env['VK_LAYER_ENABLES'] = 'VK_VALIDATION_FEATURE_ENABLE_SYNCHRONIZATION_VALIDATION_EXT'
                result = subprocess.run([str(host), '--test-pattern', '--test-frames', str(args.frames),
                                         '--scale', '3', '--mute', '--data', str(root / 'data'), *flags],
                                        env=env, capture_output=True, text=True, timeout=90)
                output = result.stdout + result.stderr
                completed = COMPLETE.search(output)
                expected = f'companion shared: {str(shared).lower()}, GPU images: {str(gpu).lower()}'
                if (result.returncode or completed is None or expected not in output
                        or 'Validation Error' in output or 'VUID-' in output):
                    print(json.dumps({'case': name, 'ok': False, 'returncode': result.returncode,
                                      'output_tail': output[-12000:]}), flush=True)
                    return 1
                print(json.dumps({'case': name, 'ok': True, 'frames': int(completed[1]),
                                  'seconds': float(completed[2]), 'fps': float(completed[3]),
                                  'shared': shared, 'gpu_images': gpu,
                                  'validation': bool(args.validation_layer_dir)}), flush=True)
    except (OSError, subprocess.SubprocessError) as error:
        print(f'native smoke failed: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
