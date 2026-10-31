# AGENTS.md — hey agents, this is ctr-native

Structure (mirrors nxnative's shape):

    scripts/build_app_from_3ds.py   the pipeline CLI (stages, keys cache, json progress)
    scripts/bug_report.py           diagnostics zip (never keys)
    scripts/clean_cache.py          delete old caches, keep saves/config
    dm/tools/ncch.py                NCSD/NCCH/ExeFS/SMDH parsers (bounded reads)
    dm/tools/decrypt.py             NCCH decryption (--boot9/--keys, superblock-verified)
    dm/tools/pack_app.py            the .app packer (launcher, plist, icon, signatures)
    dm/games/<title id>/            per-game profiles: profile.tsv + README.md
    dm/tests/                       synthetic-fixture unittests (no game data)
    docs/                           development.md (pipeline), playing.md (users)

## Ground rules

- **Nothing from any game** enters this repository: dumps, extracted content,
  icons or shader artifacts; `.gitignore` holds them out — keep it that way.
  Console keys (`boot9`, `movable.sed`, keys files) are the same: never commit,
  never bundle, never send to a collector (bug_report.py refuses them).
- Tests are synthetic: fixtures are manufactured from the format public docs
  (`dm/tests/fixtures.py`); guard bounded reads and clean failures.
- `dm/games.py` profiles pin the dump's `verified_md5`; the runtime reads its
  own `settings.toml` in the sandbox — never prewrite player settings.
- Progress must never crash a build; wrap prints in try/except at the seam
  (`dm/tools/progress.py::Progress._raw`).
- The `.app`'s sandbox is user data: builds may create, never update, and the
  reuse signature must cover every file the launcher depends on.

## Changes to make

- New or changed parsers: add a synthetic test stage here, and a fuzz target
  under `dm/tests` (Atheris optional; blind mutation corpus accepted).
- The CLI: keep `-h` and `--progress json` complete; `docs/development.md`
  documents the stage list (update it when stages change).
