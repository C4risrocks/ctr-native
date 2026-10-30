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

## KPI G5 · runs de 600 frames AOT (2026-10-30, M1 Pro, cabeza sin ventana)

| Corrida | Renderer | Shading de vértices | 600 frames | MIPS | Draws |
|---|---|---|---|---|---|
| headless | software | CPU (por definición) | 5.71 s | 471.2 | 10 067 · 0% GPU |
| headless | hardware (Vulkan) | **CPU — default en Apple Silicon** | 1.12 s | **2409.1** | 10 789 · 0% GPU |
| headless | hardware | GPU forzada (`ZAKURO_GPU_SHADERS=1`) | 7.53 s | 357.0 | 10 789 · 100% GPU |

Hallazgos medidos (cierran el misterio del "vertices shaded on the CPU"):

- El fork YA tiene el path completo de shading en GPU: se llega al 100% de
  draws GPU-shaded pidiéndolo; el default lo manda a CPU en GPUs
  integradas/embedded ("an integrated GPU does worse at it than the CPU",
  comentario del fork) y **la medición le da la razón**: CPU shading corre
  6.7× más rápido que el GPU shading en M1 Pro (franja `gpu`: 199.9 ms vs 6.3 s).
- La línea del log es una decisión de capacidad, no una deficiencia: F8-G1
  queda como "auditoría hecha — default correcto, path GPU verificado,
  revisitar si mejora MoltenVK o se decide Metal-direct (G4)".
- Desde G5 el runtime estampa al cerrar una línea `session kpi` (fps avg/min,
  underruns totales, % de draws GPU-shaded) que alimenta esta tabla por
  release; `docs/patches/zakuro/` lleva los parches del fork (0001 props2,
  0002 kpi).

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
   (las sesiones en ventana sí van con pacing FIFO; la `session kpi` de G5 da
   el fps real al cerrar).
2. Audio: auditing de los "sound ran dry" esporádicos (underruns aislados en
   ~4.5 h de sesión, con un racimo al final) — G2 pendiente, ya con contador
   acumulado por la sesión en la línea kpi.
3. ~~HLE gaps menores: `cecd:u` cmd 0x0012~~ — G3 cerrado: OpenAndRead lee
   el inbox vacío offline con test in-crate y boot real sin WARN (patch 0005).
4. Metal-direct (G4): informe go/no-go — ahora con dato de costo: el GPU
   shading vía MoltenVK corta 6.7× (357 MIPS) en M1 Pro, así que el valor de
   un backend Metal directo estaría en el raster/PSO, no en resolver esto.
5. F7 (pantalla por monitor): **hecho y re-empaquetado (F7-0..F7-4)** —
   settings + panel del menú Settings + CLI (`--split/--monitor-bottom`),
   touch en la companion, F11 ambas ventanas; validar en Mac con dos
   monitores queda por la sesión real.
6. PR de cortesía upstream: LICENSE file en `3dsrecomp` (declara MIT en
   Cargo.toml pero no lleva el archivo), y los parches de
   `docs/patches/zakuro/` como serie PR.
