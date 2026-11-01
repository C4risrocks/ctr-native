# Contributing to ctr-native

1. **Clone, run the tests** (no game or console data needed):

       python3 -m unittest discover -s dm/tests -t . -p "t_*.py"
       ruff check dm scripts   # after pip install ruff; never reformat

2. **Code pace**: small functions on bounded reads; the pipeline's stages are
   independent — new stages add a number, not a rewrite. The lint is a
   ratchet in nxnative style: fix your own findings or leave a reason on the
   line (`# noqa`), don't widen buckets.
3. **Privacy invariant**: everything user-side (dumps, keys, saves, logs) stays
   on the player's machine; the repo tests build fixtures in code, so CI
   needs no console material.
4. **Game notes live in `dm/games/<title id>/README.md`** — a bring-up story
   is a repayable contribution for the next player of that title.
5. PRs: one subject per PR, tests for container parsing changes, and a line
   of context in the commit ("why now").

## Current checks and native changes

Run `pyright dm scripts`, `python3 -m dm.tests.fuzz_containers --iterations 2000`
and `python3 scripts/bootstrap_vendors.py --verify-only` alongside the checks
above. The shared builder has eight stages and obtains AOT automatically.
Export every native commit in dependency order, update the locked tree, and
reconstruct the full patch series in a fresh directory before publishing it.
See [development](docs/development.md) and the
[open audit findings](PLAN_REFACTOR_PIPELINE.md#auditoría-2026-11-01-sobre-be10b73).
