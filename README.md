# ctr-native

Play your own Nintendo 3DS games in **native, double-clickable Mac apps**, one
app per game, with everything (config, saves, shader caches, logs) inside the
app itself. Bring your dumps; one script does the rest.

It is not a port portal and not affiliated with Nintendo: an `.app` is built
from *your* dump and holds nothing from any game in this repository.

## Status: Fase 1 (pack stage) — running on macOS 26, arm64

| nxnative (Switch) | ctr-native (this repo) |
| --- | --- |
| NSP/XCI/NSZ + `prod.keys` | `.3ds`/`.cci`, decrypted or your `boot9` for the encrypted ones |
| NSO rewriter (already ARM64) | Azahar HLE host (ARMv6 via its translator/JIT — the native one arrives in Fase 2) |
| Horizon HLE host in C | Azahar's CTR HLE, sandboxed per game (`$HOME` redirection) |
| NVN → Metal, offline shaders | PICA200 → Vulkan/Metal (MoltenVK) with per-game profiles |
| `build_ipa_from_nsp.py --platform mac-app` | `build_app_from_3ds.py` → `<game>.app` |

## How to play

1. **Requirements**: a Mac with Apple silicon, macOS 13.4+, and the
   [Azahar](https://github.com/azahar-emu/azahar) `macos-arm64` zip in
   `/Applications` ( unzip its `Azahar.app`).
2. **Put your dump in a folder** (next to nothing else needed):

       ~/Games/ALBW/Legend of Zelda, The - A Link Between Worlds (USA) (En,Fr,Es).3ds

3. **Build**:

       python3 scripts/build_app_from_3ds.py ~/Games/ALBW -o ~/Desktop

   The app lands beside the dump by default. Verified dumps: put the
   No-Intro MD5 into `dm/games/<title id>/profile.tsv` as `verified_md5=…`
   and every build re-verifies your copy (~1 s per GiB).

4. **Play** by double-clicking the app. It runs fullscreen; F11 toggles,
   Esc exits fullscreen. Saves live inside:
   `…app/Contents/MacOS/sandbox/home/Library/Application Support/Azahar`.

### Encrypted dumps

Partitions that are neither `NoCrypto` nor `FixedKey` need the standard NCCH
keys, which derive from your console's `boot9`:

    python3 scripts/build_app_from_3ds.py ~/Games/X --boot9 ~/keys/boot9.bin

The decrypted copy is written into `<title id>_build/`, your keys never enter
git or the app, and nothing ships them with the app. FixedKey games (many
2013+ releases) and already-decrypted dumps need **no keys at all**.

### Adding a game

A folder under `dm/games/<title id>/` — a `profile.tsv` of settings and a
`README.md` of notes ([see how](dm/games/README.md)). Missing folders build
anyway with the shared template ("provisional profile").

## For developers

How it works, the stages, the JSON progress mode and the pipeline details:
[docs/development.md](docs/development.md). Controls, saves, troubleshooting:
[docs/playing.md](docs/playing.md). Building it
([CONTRIBUTING.md](CONTRIBUTING.md)) runs its tests with

    python3 -m unittest discover -s dm/tests -t . -p "t_*.py"

and checks with `ruff check dm scripts`.

## License

MIT ([LICENSE](LICENSE)). Third-party components (none is bundled) keep their
own licenses; the host reflects [Azahar](https://github.com/azahar-emu/azahar)
(GPL), [LibHac](https://github.com/Thealexbarney/LibHac)/hactool-style
container knowledge, and 3dbrew/GBATEK-format documentation.
