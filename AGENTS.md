# AGENTS.md — hey agents, this is ctr-native

Structure (mirrors nxnative's shape):

    scripts/build_app_from_3ds.py   thin CLI adapter (arguments and progress)
    scripts/bug_report.py           diagnostics zip (never keys)
    scripts/clean_cache.py          delete old caches, keep saves/config
    dm/build/                     shared eight-stage pipeline, models and AOT cache
    dm/tools/runtime.py           shared runtime invocation and environment
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

## Maintenance references

- For pipeline behavior and validation commands, read `docs/development.md`.
- For audit fixes and open P2 findings, read `PLAN_REFACTOR_PIPELINE.md`.
- For native changes, export each commit in dependency order under
  `docs/patches/zakuro/`, update `vendors.lock.json`, and verify a fresh bootstrap.
- Keep cache provenance separate from the unfinished compiler/SDK fingerprint
  work. Current cleanup removes only the selected build's `extract` directory.
