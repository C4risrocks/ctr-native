# Playing

## Where the game comes from

The app points to an external card image by absolute path: the original for
NoCrypto, or its verified working copy for encrypted inputs. Keep that file;
it is not bundled into the app. The original is never modified.

## Controls

The keyboard profile follows the classic hosts: cursor keys = circle pad,
the face buttons on the letters row (`A`/`S`-style labels may differ by
reader). A Nintendo-pad or Xbox controller is detected automatically.

In-game keys: `Esc` opens the menu, `F1` pauses, `F9` cycles the screen
arrangements, `F10` switches between the top and the bottom screen alone,
`F11` fullscreen, `F5`/`F8` save and load a state. The full guide, plus the
dual-monitor mode: [walkthrough.md](walkthrough.md).

## Saves

`<game>.app.ctr-native/home/Library/Application Support/zakuro/`
— `nand`, `sdmc`, game saves and `zakuro.log` (diagnostics). Vulkan caches
live separately under the sandbox HOME in `Library/Caches/zakuro/pipelines/`. Move the sibling sandbox with the app, then rebuild to anchor the new
absolute paths. Nothing gets overwritten between builds.

## Troubleshooting

- **Blank grey icon**: pass `--no-icon` or ask about `--app-name`; the SMDH
  icon never matched your bundle name otherwise. Not fatal.
- **"MD5 does not match the profile pin"**: your dump is a different release
  (update, another region) — correct, but tell ctr-native: copy the matching
  MD5 into the game's profile or pass `--allow-damaged`.
- **Slow first minutes**: the first session compiles shaders upfront; later
  runs warm from the sandbox's cache.
- A bug report: `python3 scripts/bug_report.py "<game>.app"` — the zip
  collects logs, versions and the inputs record; no keys are ever inside.

## Diagnostics and cleanup

`bug_report.py` collects allowlisted metadata and up to 4 MiB per log, keeping
its tail. It refuses links, binary content and recognizable key tables.
`clean_cache.py <game.app> --dry-run` previews exactly the cache/old-log
candidates. A running app is skipped; failure to inspect processes stops
cleanup. Saves, settings and the current log are never candidates.

## Comportamiento actual del builder

AOT se genera automáticamente; las herramientas nativas se preparan una vez.
Conserva la ROM externa, incluida su copia preparada, en la ruta del launcher.
`--no-keep-directories` elimina solo `extract` del build seleccionado: conserva
ROM preparada, caché AOT, logs y datos del jugador. Consulta
[development.md](development.md) para las ocho etapas y sus limitaciones.
