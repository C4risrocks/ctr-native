# A Link Between Worlds (USA) · `00040000000EC300` · CTR-P-BZLE

First bring-up of ctr-native (2026-10-30).

- Dump: card image, **Decrypted**, No-Intro verified (`a7627c2e...` MD5):
  "Legend of Zelda, The - A Link Between Worlds (USA) (En,Fr,Es).3ds"
- Runs on the stock Azahar host with the shared template, 4x resolution.
- Savedata (the game's `SaveCommon.bin` and friends) lands in the app sandbox:
  `…app/Contents/MacOS/sandbox/user/nand/data/…/title/00040000/000ec300/data/`.
- SMDH carries titles for 9 languages (the card itself is En,Fr,Es content).
- Knows issues: none so far; watch the first-boot shader hitch (async compile
  hides it).

Fase 2 (ctr HLE host) notes: ALBW loads its DSP firmware through MMIO-less
hle; keep the audio path HLE first.
