# Audit implementation — 0.2.0

> Historical record: measurements and completion claims below refer to their
> original revisions. For current status see [the audit backlog](../PLAN_REFACTOR_PIPELINE.md)
> and [development](development.md). Metal presentation now exists, while the
> HardwareMetal raster and the documented P2 fixes remain pending.

Implemented against ctr-native baseline `8d3e87e`. Native delta: zakuro
`8f21f68`, exported as patch 0012; upstream bases and expected patched trees
are fixed in `vendors.lock.json`.

## Findings closed in code

| Area | Implementation and regression surface |
|---|---|
| Decryption blockers | Correct boot9 path/map, NCCH magic, 16-entry NCSD table and readable writer; `t_decrypt`, `t_regressions`. |
| Silent ExeFS corruption | Original/content key groups, unaligned padding, sorted sections, section hashes and streamed superblocks; independent AES synthetic fixtures. |
| Parser limits and truncation | All eight partitions, all ten ExeFS entries, container bounds/overlaps, complete SMDH/NCSD headers and controlled failures; bounded mutation corpus. |
| Ciphertext read before decrypt | Builder inspects all partitions, publishes verified working copy before metadata/icon reads, preserves original input identity; mixed clear/encrypted-card integration test. |
| Save overwrite | Collision preflight, no-follow source access, create-only destinations and retained legacy archive; transient-publication rollback and archive-failure recovery tests. |
| Invalid build reuse | Candidate constructed/signed/verified before atomic exchange; reuse verifies required files and signatures. Real macOS smoke covers successful reuse, rebuild and missing dependency. |
| Ignored language/scale | Effective launcher exports HOME and passes language/scale; native CLI applies temporary language override without rewriting settings. |
| Icon/reuse errors | Content fingerprints include icon pixels and all deployed inputs; plist icon path matches actual resource. Native smoke changes icon pixels and verifies rebuilding. |
| Broken JSON/progress | Seven fixed stages, closed failure event, subprocess errors controlled, TTY-aware auto mode; CLI tests and optimized-Python help checks. |
| Missing/unsafe diagnostics | Shared actual data paths, explicit file allowlist, no-follow reads, key-table rejection, bounded UTF-8 log tails and malformed-plist handling. |
| Ineffective/unsafe cleanup | Current/legacy caches, correct file sizes, exact preview, whole-app activity checks including spaces and parent segments, failure-closed process inspection. |
| GPU companion blank frames | Same Vulkan device/queue, Arc-owned upright outputs, pool of at most three images per surface, completion fences for both consumers, per-image swapchain semaphores and explicit barriers. |
| GL fallback frame mismatch | Read pixels from the captured GPU image/crop/generation, including an interpolated twin; real synthetic GPU readback regression. |
| Split override ignored | Explicit `--split off` takes precedence over persistent companion settings. |
| CI and reproducibility | Full synthetic Python suite, real macOS package smoke, type/lint/fuzz checks, pinned native reconstruction and Rust workspace tests. |

## Executed validation (2026-10-31)

- 62 Python tests passed, including actual clang/iconutil/codesign bundle lifecycle.
- 2,000 deterministic synthetic mutations passed after fixing a discovered truncated-header crash.
- Ruff and Pyright (Python 3.12 target) passed.
- Rust workspace: 483 tests passed; three default ignores comprise two speed probes and the live-GPU readback test. The latter was explicitly executed and passed with validation layers.
- Release workspace compilation passed; both native sources reconstruct from clean upstream fetches to the expected locked trees.
- Khronos validation layers were unpacked in a temporary directory rather than installed globally. Live Vulkan readback and both debug/release presentation smokes passed without validation errors.

Release presentation results on the local Apple Silicon host, scale 3, 120
manufactured frames per case, isolated HOME/data:

| Case | FPS | Shared device | GPU-only source |
|---|---:|---|---|
| Single Vulkan window | 60.1 | no companion | yes |
| Two Vulkan windows | 60.0 | yes | yes |
| Resize / close / reopen companion | 60.1 | yes | yes |
| Vulkan main → OpenGL companion | 60.5 | no | yes, exact readback |
| Two OpenGL contexts | 60.4 | no | no |

These are presentation diagnostics, not game-performance benchmarks. They do
not establish the old/new single-window performance budget for a real title.
No real ROM, boot9, console keys, saves or game-derived assets were used by
these checks. No existing player app or sibling sandbox was rebuilt.

## Validation requiring physical hardware/session

The implementation is complete; record a real two-monitor session separately
for monitor selection, mixed DPI, touch and fullscreen behavior. A real-game
before/after performance comparison (single-window regression budget: 5%) and
windowed audio/underrun measurement remain unverified. The synthetic results
above must not be reported as closing those physical/game-specific checks.

Use the commands in [development.md](development.md) and
`scripts/native_smoke.py` to reproduce automated checks. No advanced save
migration tool, CIA packaging, seeded crypto or Metal-direct backend was added.
