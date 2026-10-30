# zakuro-macOS — estado del port (Fases 0–6 completadas)

Fork base: [fearkov/zakuro](https://github.com/fearkov/zakuro) + [3dsrecomp](https://github.com/fearkov/3dsrecomp) (MIT).
Clones de trabajo: `vendors/zakuro`, `vendors/3dsrecomp` (zakuro lleva un parche
local preventivo, ver "Resueltas").

## Resultados medidos (2026-10-30, MacBook Apple Silicon, 16 GB)

| Prueba | Modo | Resultado |
|---|---|---|
| `cargo check --workspace` (KPI 0) | — | ✅ 0 errores, 39 s |
| `cargo build --release` | zakuro app + recomp3ds | ✅ 1m24s + 6s |
| Boot ALBW windowed | `--interpreter` | ✅ loader · kernel HLE · DSP firmware · savedata |
| Headless ×600 frames | `--interpreter --mute` | 32.11 s · 83.7 MIPS · software renderer |
| Headless ×600 frames | **AOT recompilado** | **6.10 s · 440.9 MIPS · interpreted 0.04%** |
| **ALBW en ventana (sesión real)** | AOT + Vulkan portability | ✅ ~4 h 27 min · present FIFO · pantalla 3x · audio HLE · underruns de audio esporádicos |

- AOT build: `3dsrecomp build` → **259/259** funciones, 304 MiB de C, 226.6 s
- `.dylib` (arm64, Mach-O) instalado en `~/Library/Application Support/3dsrecomp/00040000000EC300.dylib` — pasa AMFI sin parches (firma válida embedida)
- El juego: ALBW USA `00040000000EC300` (dump decrypted verificado No-Intro, pin MD5 en `dm/games/00040000000EC300/`)

## Resueltas (delta darwin cerrado)

1. **Vulkan portable**: el instance opta por `VK_KHR_portability_enumeration` +
   flag `ENUMERATE_PORTABILITY_KHR` ya en el árbol del fork (`backend/vulkan.rs`,
   heurística `is_portability_system()`; también `raster/hardware.rs::own_device`).
   Parche local preventivo añadido: `get_physical_device_properties2` corre junto
   a portability porque `VK_KHR_portability_subset` (solo lo exponen estos
   drivers) la requiere por spec el día que se active (patrón de ash-examples).
   Evidencia runtime (log del sandbox, sesión windowed 2026-10-30): "Vulkan on
   Apple M1 Pro", present FIFO, pantalla 3x, shading de vértices en CPU.
2. **Empaquetado ctr-native**: `--host zakuro` (default) hornea `zakuro` + dylib
   AOT + datos en el `.app` por juego (F6: ver `docs/development.md`).

## Pendientes (delta darwin conocido)

1. `--headless` corre sin pacing: las cifras son throughput, no fps realtime
   (las sesiones en ventana sí van con pacing FIFO).
2. Audio: auditing de los "sound ran dry" esporádicos (underruns aislados en
   ~4.5 h de sesión, con un racimo al final) — sin causa identificada aún.
3. HLE gaps menores: `cecd:u` cmd 0x0012 (StreetPass) sin implementar — avisos
   benignos para ALBW.
4. PR de cortesía upstream: LICENSE file en `3dsrecomp` (declara MIT en
   Cargo.toml pero no lleva el archivo).
5. El renderer de shaders traduce POR CPU (naga wgsl-in→spv-out) y raster por
   GPU; performance de vértices sigue siendo el cuello cuando el CPU cede
   (ver underruns).
