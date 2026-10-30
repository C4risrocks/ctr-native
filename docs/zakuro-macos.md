# zakuro-macOS — estado del port (Fases 0–2′ completadas)

Fork base: [fearkov/zakuro](https://github.com/fearkov/zakuro) + [3dsrecomp](https://github.com/fearkov/3dsrecomp) (MIT).
Clones de trabajo: `vendors/zakuro`, `vendors/3dsrecomp` (sin in-treechanges todavía).

## Resultados medidos (2026-10-30, MacBook Apple Silicon, 16 GB)

| Prueba | Modo | Resultado |
|---|---|---|
| `cargo check --workspace` (KPI 0) | — | ✅ 0 errores, 39 s |
| `cargo build --release` | zakuro app + recomp3ds | ✅ 1m24s + 6s |
| Boot ALBW windowed | `--interpreter` | ✅ loader · kernel HLE · DSP firmware · savedata (`~/Library/Application Support/zakuro/`) |
| Headless ×600 frames | `--interpreter --mute` | 32.11 s · 83.7 MIPS · software renderer |
| Headless ×600 frames | **AOT recompilado** | **6.10 s · 440.9 MIPS · interpreted 0.04%** |

- AOT build: `3dsrecomp build` → **259/259** funciones, 304 MiB de C, 226.6 s
- `.dylib` (arm64, Mach-O) instalado en `~/Library/Application Support/3dsrecomp/00040000000EC300.dylib` — pasa AMFI sin parches (firma válida embedida)
- El juego: ALBW USA `00040000000EC300` (dump decrypted verificado No-Intro, pin MD5 en `dm/games/00040000000EC300/`)

## Pendientes (delta darwin conocido)

1. **Vulkan instance**: dlopen funciona (`DYLD_LIBRARY_PATH=/opt/homebrew/lib`) pero la instancia no enumera MoltenVK — falta `VK_KHR_portability_enumeration` + `VK_INSTANCE_CREATE_ENUMERATE_PORTABILITY_BIT_KHR` en `crates/zakuro-gpu` (cfg macos). Mientras: `--renderer gl --rasterizer software` o software directo; el ICD de brew es `/opt/homebrew/etc/vulkan/icd.d/MoltenVK_icd.json` → pasar con `VK_DRIVER_FILES`
2. `--headless` corre sin pacing: las cifras de arriba son throughput, no fps realtime
3. **Empaquetado ctr-native**: `--host zakuro` (default) horneará `zakuro` + `--recompiled` dylib + `--data <sandbox>` en el `.app` por juego (F6: ver `docs/development.md`)
4. PR de cortesía upstream: LICENSE file en `3dsrecomp` (declara MIT en Cargo.toml pero no lleva el archivo)
