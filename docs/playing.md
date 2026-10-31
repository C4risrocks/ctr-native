# Playing

## Where the game comes from

The app you built runs your dump directly; nothing is copied out of your
original file, and deleting the dump breaks the app (the launcher points at
it absolute).

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
— `nand` (system titles), `sdmc`, `user/savedata` (the game's save), `cache`,
and `zakuro.log` (diagnostics). Saves follow the app: moving the app moves
saves. Nothing gets overwritten between builds.

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
