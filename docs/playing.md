# Playing

## Where the game comes from

The app you built runs your dump directly; nothing is copied out of your
original file, and deleting the dump breaks the app (the launcher points at
it absolute).

## Controls

The keyboard profile (Azahar defaults) is: cursor keys (circle pad),
A/B = `A`/`S`?? actually Azahar maps by instrument panel label — open the
app; Azahar includes the mapping screen ("Configure Current Game"). A
Nintendo-pad or Xbox controller is detected automatically.

## Saves

`<game>.app/Contents/MacOS/sandbox/home/Library/Application Support/Azahar/`
— `nand` (their save), `sdmc`, `cache` (the compiled shader store: leave it,
it speeds up every next boot of this game), `log` (delicious diagnostics).
Saves follow the app; moving the app moves saves.

## Troubleshooting

- **Blank grey icon**: pass `--no-icon` or ask about `--app-name`; the SMDH
  icon never matched your bundle name otherwise. Not fatal.
- **"MD5 does not match the profile pin"**: your dump is a different release
  (update, another region) — correct, but tell ctr-native: copy the matching
  MD5 into the game profile or pass `--allow-damaged`.
- **Two consoles, one Mac**: multiple apps run at once; every second instance
  of the same emulator reports refuses to co-exist with another Azahar run — one per app, kill the outright one first.
- **Slow first minutes**: async shader compilation does its first-run compiles
  upfront; later runs warm from `sandbox/home/.../cache`.
- A bug report: `python3 scripts/bug_report.py "<game>.app"` — the zip
  collects logs, versions and the inputs record; no keys are ever inside.
