#!/usr/bin/env python3
"""Reproduce the pinned native forks without modifying an existing checkout."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def git(folder: Path, *args: str) -> str:
    return subprocess.run(['git', '-C', str(folder), *args], check=True,
                          capture_output=True, text=True).stdout.strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, default=ROOT / 'vendors')
    parser.add_argument('--verify-only', action='store_true')
    args = parser.parse_args(argv)
    lock = json.loads((ROOT / 'vendors.lock.json').read_text())
    try:
        for name, repo in lock['repositories'].items():
            target = args.directory / name
            if not target.exists():
                if args.verify_only:
                    raise ValueError(f'missing checkout: {target}')
                target.mkdir(parents=True)
                git(target, 'init', '--quiet')
                git(target, 'remote', 'add', 'origin', repo['url'])
                git(target, 'fetch', '--depth=1', 'origin', repo['commit'])
                git(target, 'checkout', '--detach', 'FETCH_HEAD')
                patches = []
                if repo.get('patch_directory'):
                    patches = sorted((ROOT / repo['patch_directory']).glob('*.patch'))
                if patches:
                    git(target, '-c', 'user.name=ctr-native build', '-c', 'user.email=build@ctr-native.invalid',
                        'am', *(str(path) for path in patches))
            if git(target, 'status', '--porcelain'):
                raise ValueError(f'{target} has changes; preserve them before rebuilding the fork')
            if git(target, 'rev-parse', 'HEAD^{tree}') != repo['tree']:
                raise ValueError(f'{target} differs from vendors.lock.json; existing checkouts are never reset')
            print(f'{name}: pinned tree verified')
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f'vendor setup failed: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
