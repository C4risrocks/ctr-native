# Plan Metal (G4→M): backend Metal directo para ctr-native

## Estado (2026-11-01) — M0 ✅ **ejecutado y merged a master**

| Dato | Valor |
|---|---|
| Pipeline Metal (device+queue+layer+MSL→library+pipeline) | creado en el arranque de la ventana, sin fallos |
| Present loop por `CAMetalLayer` (drawable→render→commit→present) | **90 frames / 1.481 s = 60.1 fps** on-screen |
| Comparación Vulkan mismo test (`--test-pattern --test-frames 90`) | 57–61 fps (native_smoke, 5 escenarios) — **empate** |
| Fallos/panics | 0 · sin mensajes de validación |
| Seguridad añadida | fuera del test-pattern, `--renderer metal` marca en el log que es el spike (patch 0015) |

**Conclusión M0:** la capa de presentación Metal funciona al ritmo de
pantalla con el mismo coste aparente que Vulkan. El **go** del backend
completo queda sujeto a M0.5 (el dato que decide de verdad): el coste de un
PICA-VS trasladado a MSL con shading por GPU frente al CPU-shading
(2409 MIPS) — **M0.5 medido y GO**: 189/189 programas PICA aleatorios
(aritmética+flujo) escritos en MSL y compilados por el device en 606 ms
(3.2 ms por programa, cero rechazos).

## Fases

| Fase | Contenido | Criterio de salida |
|---|---|---|
| **M0 ✅** | feature `metal` (objc2-bindings), `MetalPresenter` con CAMetalLayer sobre el NSView del window de winit, `--renderer metal` en CLI/settings/menús, spike timed | el present a 60 fps on-screen ✓ (hecho) |
| **M0.5 ✅ GO** | naga `msl-out` + `compile_msl` y test con 189 programas aleatorios: **189/189 MSL escritos, 189/189 compilados por el device en 606 ms (3.2 ms/programa, cero rechazos)** | **GO al backend completo (M1-M3)** |
| **M1.0 ✅ present parity (2026-11-01)** | las pantallas del juego como texturas Metal (`replaceRegion`), quads por el layout compartido `place()` (12 quads/frame), overlays egui **pendientes (M2.1)**; **fix del crash del driver AGX en macOS 26.5** (`writeRegion` en Privateoptmizada crasheaba en `convertTiles2D`): `setAllowGPUOptimizedContents(false)` + StorageMode **Managed** | test-pattern metal: **120 frames on-screen a 60.2 fps**; `native_smoke` metal: single + shared-companion a 60.2 fps |
| **M2 ✅** | companion Metal (por renderer-kind del main), settings persistentes (`renderer: "metal"` toml + combo menús), `native_smoke` +2 casos metal | **7/7 escenarios nativos verdes** (5 vulkan + 2 metal, single y shared) |
| **M1.1 ⏳ backlog (raster)** | `HardwareMetal` PICA-pipeline a Metal (formatos→MTLPixelFormat, depth 32f, blending, shaders GPU-metal) — multi-sesión, el resto del fork depende de Vulkan | headless ×600: MIPS ≥ 85% del mejor camino |
| **M3 ⏳ cierre** | kpi real del jugador con Metal; tabla Vulkan-vs-Metal; decision de shading default | docs y el kpi del jugador |
| **M3 cierre G4** | kpi real del jugador con Metal; tabla comparativa Vulkan-vs-Metal en `docs/zakuro-macos.md`; patches 0014+ exportados y PR de cortesía preparado | docs cerrados; decisión de shading default documentada |

## Riesgos (los mismos del informe G4, actualizados)

1. **objc2 churn** — lock por `vendors.lock.json` (ya existe el mecanismo).
2. **naga msl-out** puede pedir overrides de binding por textura/buffer — se
   mide en M0.5 antes de comprometer M1.
3. **AppKit/main-thread** — los drawables se adquieren y presentan en el
   hilo main; el raster corre en el hilo de emulación (patrón del patch
   0012 ya separa ambos con fences).
4. **Dos backends GPU que mantener** — Vulkan queda como red de seguridad y
   herramienta de comparación; no se deprecia.

## Referencias

- `docs/zakuro-macos.md` — la tabla de KPIs (G5) y las corridas medidas.
- `docs/metal-direct.md` — el informe go/no-go anterior (HOLD) que este plan
  reabre con el disparador cumplido (MM3D 59.6 fps).
- `docs/patches/zakuro/` — la serie de parches del fork (0001…0017).

## Riesgos consumados del M1.0

- **AGX writeRegion en Private crasheaba (KERN_INVALID 0x4000)** en macOS
  26.5 con texturas "GPU optimized": la solución estándar
  (`setAllowGPUOptimizedContents(false)` + StorageMode Managed) ya está en
  el MetalPresenter del fork — el upload por frame termina en 1600-byte
  rows lineales.
