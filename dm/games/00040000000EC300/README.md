# A Link Between Worlds (USA) · `00040000000EC300` · CTR-P-BZLE

First bring-up of ctr-native (2026-10-30).

- Dump: card image, **Decrypted**, No-Intro verified (`a7627c2e...` MD5):
  "Legend of Zelda, The - A Link Between Worlds (USA) (En,Fr,Es).3ds"
- Runs on the native zakuro host (AOT), window scale 3x in the sandbox settings.
- Savedata (the game's `SaveCommon.bin` and friends) lands in the app sandbox:
  `…app.ctr-native/home/Library/Application Support/zakuro/` (runtime-owned save directories).
- SMDH carries titles for 9 languages (the card itself is En,Fr,Es content).
- Knows issues: none so far; the first sessions measured 55.5 fps avg with
  audio underruns (F8-G2 pins the callbacks, pending a fresh-windowed re-measure).

Fase 2 (ctr HLE host) notes: ALBW loads its DSP firmware through MMIO-less
hle; keep the audio path HLE first.

## Estado del runtime después de H4

Las sesiones registradas anteriormente corresponden al camino Vulkan/MoltenVK.
HardwareMetal H1–H4 está implementado en dev, pero H5–H7 siguen abiertos;
no hay una nueva validación del título sobre ese raster.
Ver [estado del proyecto](../../../ESTADO_PROYECTO.md) y
[walkthrough](../../../WALKTHROUGH.md).
