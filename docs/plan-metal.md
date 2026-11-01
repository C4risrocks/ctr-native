# Plan Metal (G4→M): backend Metal directo para ctr-native

## Estado (2026-11-01) — M0 spike completado

**M0 ✅ ejecutado** (branch `feat/metal-m0`, patch del fork `0014`):

| Dato | Valor |
|---|---|
| Pipeline Metal (device+queue+layer+MSL→library+pipeline) | creado en el arranque de la ventana, sin fallos |
| Present loop por `CAMetalLayer` (drawable→render→commit→present) | **90 frames / 1.481 s = 60.1 fps** on-screen |
| Comparación Vulkan mismo test (`--test-pattern --test-frames 90`) | 57–61 fps (native_smoke, 5 escenarios) — **empate** |
| Fallos/panics | 0 · sin mensajes de validación |

**Conclusión M0:** la capa de presentación Metal funciona al ritmo de
pantalla con el mismo coste aparente que Vulkan. El **go** del backend
completo queda sujeto a M0.5 (el dato que decide de verdad): el coste de un
PICA-VS trasladado a MSL con shading por GPU frente al CPU-shading
(2409 MIPS) — el commit M0 no toca shaders PICA todavía.

## Fases

| Fase | Contenido | Criterio de salida |
|---|---|---|
| **M0 ✅** | feature `metal` (objc2-bindings: objc2-metal/quartz-core/app-kit; sin crate `metal`), `MetalPresenter` con CAMetalLayer sobre el NSView del window de winit, `--renderer metal` en CLI/settings/menús, spike timed | el present a 60 fps on-screen ✓ (hecho) |
| **M0.5 spike de vértices** | el PICA-VS que el fork ya traduce a WGSL se lleva a **MSL** (naga `msl-out`); se corre el test-pattern con shading por GPU vía Metal y se mide: pipeline por draw, tiempo de vértices y fps | **go/no-go del shading GPU por Metal**: MSL GPU-shading ≤ CPU-shading ×1.3 |
| **M1 raster parity** | `HardwareMetal` con los mismos contratos de `hardware.rs`: formatos PICA→MTLPixelFormat, depth 32f, blending/culling, escala 3x, stats de G5 integrados | headless ×600 de ALBW y MM3D: MIPS ≥ 85% del mejor camino actual |
| **M2 present + F7** | `MetalPresenter` completo (imágenes de las pantallas, overlay egui, swapchain pool estilo 0012 con drawables); `--renderer metal` persistente en settings; casos metal en `native_smoke` (single/shared/cycle/fallback-GL) | 7 escenarios verdes; sesión windowed 10 min con kpi ≥ baseline |
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
- `docs/patches/zakuro/` — la serie de parches del fork (0001…0014).
