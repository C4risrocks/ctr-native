# ctr-native

Play your own Nintendo 3DS games in **native, double-clickable Mac apps**, one
app per game, with everything (settings, saves, shader caches, logs) beside the
app in its own sandbox. Bring your dumps; one script does the rest.

It is not a port portal and not affiliated with Nintendo: an `.app` is built
from *your* dump and holds nothing from any game in this repository.

## Status: the native path (zakuro) — running on macOS 26, arm64

| nxnative (Switch) | ctr-native (this repo) |
| --- | --- |
| NSP/XCI/NSZ + `prod.keys` | `.3ds`/`.cci`, decrypted or your `boot9` for the encrypted ones |
| NSO rewriter (already ARM64) | **zakuro**: ARM11→AOT por 3dsrecomp, runtime HLE Rust nativo |
| Horizon HLE host in C | zakuro's CTR HLE (kernel, DSP, HID, cecd), sandboxed per game (`$HOME` redirection) |
| NVN → Metal, offline shaders | PICA200 → Vulkan/Metal (MoltenVK) with per-game profiles |
| `build_ipa_from_nsp.py --platform mac-app` | `build_app_from_3ds.py` → `<game>.app` |

## How to play

1. **Requirements**: a Mac with Apple silicon, macOS 13.4+, Python 3.12+,
   Xcode Command Line Tools and Rust. Reconstruct the pinned native sources
   with `python3 scripts/bootstrap_vendors.py`, then build both forks using
   the commands in [development.md](docs/development.md). Run one
   `vendors/3dsrecomp/target/release/3dsrecomp build <rom>` per game to install
   its AOT library. Vulkan presentation uses the system Vulkan loader and
   MoltenVK; OpenGL remains a fallback.
2. **Put your dump in a folder** (next to nothing else needed):

       ~/Games/ALBW/Legend of Zelda, The - A Link Between Worlds (USA) (En,Fr,Es).3ds

3. **Build**:

       python3 scripts/build_app_from_3ds.py ~/Games/ALBW -o ~/Desktop

   The app lands beside the dump by default, with **bundled native code** (host
   binary + the game's AOT library inside), data beside it in
   `<name>.app.ctr-native/`. Verified dumps: `verified_md5=…`
   in the profile re-verifies every build (~1 s per GiB).

4. **Play** by double-clicking the app. Esc opens the in-game menu, F1 pauses,
   F9/F10 rearrange the screens, F11 toggles fullscreen. Saves live beside the
   app: `…app.ctr-native/home/Library/Application Support/zakuro`.

### Encrypted dumps

Partitions that are neither `NoCrypto` nor `FixedKey` need the standard NCCH
keys, which derive from your console's `boot9`:

    python3 scripts/build_app_from_3ds.py ~/Games/X --boot9 ~/keys/boot9.bin

For newer crypto methods, provide the missing slots with `--keys <table.tsv>`;
this can complement `--boot9`. Seeded crypto is unsupported.

The decrypted copy is written into `<title id>_build/`, your keys never enter
git or the app, and nothing ships them with the app. FixedKey applications and already-decrypted dumps need **no keys at all**.
The original dump remains external to the app.

### Adding a game

A folder under `dm/games/<title id>/` — a `profile.tsv` pinning the verbatim
`verified_md5=` and a `README.md` of notes ([see how](dm/games/README.md)).
Missing folders build anyway with a provisional profile.

## For developers

How it works, the stages, the JSON progress mode and the pipeline details:
[docs/development.md](docs/development.md). The full user guide, controls,
dual-monitor mode and troubleshooting: [docs/walkthrough.md](docs/walkthrough.md)
and [docs/playing.md](docs/playing.md). The project's plan and state:
[docs/roadmap.md](docs/roadmap.md). Building it
([CONTRIBUTING.md](CONTRIBUTING.md)) runs its tests with

    python3 -m unittest discover -s dm/tests -t . -p "t_*.py"

and checks with `ruff check dm scripts`.

## License

MIT ([LICENSE](LICENSE)). Third-party components (none is bundled) keep their
own licenses; the knowledge base is 3dbrew/GBATEK-format documentation.
