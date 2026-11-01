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
| **M1.0 ✅ present parity (2026-11-01, verificada con ojos)** | las pantallas del juego como texturas Metal (`replaceRegion`), un draw por pantalla: rect NDC de 16 bytes inline (`setVertexBytes`) y esquinas sintetizadas por `vertex_id` — el fetch de 72-floats por puntero, correcto en papel, **nunca rasterizaba**; overlays egui **pendientes (M2.1)**; fix driver AGX 26.5: `AllowGPUOptimizedContents(false)` + **Managed** | test-pattern metal **VISTO en pantalla**: rojo 400×240 arriba, azul 320×240 abajo, letterbox navy ✓ · 120 frames a 60.2 fps · `native_smoke` 7/7 · el bug del blanco documentado en patch 0018 |
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

## La lección del presupuesto del M1.0 (2026-11-01)

La primera sesióm real del jugador dispuso un freeze **al entrar** y 25.8
fps medios. El `sample` del proceso congelado lo explicó todo: el 85% del
loop estaba dormido en `CAMetalLayer nextDrawable` (espera del vsync) —
el present Metal bloquea el mismo hilo donde corre el raster software
(MM3D 3x ≈ 18–20 ms) → ~35 ms/frame → 26 fps. La vía vulkan-hardware
corre a 57.9 porque el dibujo vive EN OTRO HILO.

|朱元璋 Camino (MM3D, este M1 Pro) | fps | origen |
|---|---|---|
| Vulkan, raster hardware + present vulkan | 57.9–60 | dibujo off-thread |
| Software + present metal **sin presentDrawable** (bug) | 54.6 | invisible al compositor: sin contrapresión |
| Software + present metal **correcto, en el hilo principal** | 25.8 | nextDrawable bloquea el hilo del raster |
| Software + present metal **desacoplado (M1.0.5)** | ⏳ ~50 objetivo | el present a thread propio por mpsc |

## M1.0.5 ✅ — el present sale del hilo del juego (patch 0019)

El bundle Metal completo (device, queue, layer, pipeline, texturas con
ping-pong de dos sets) vive en un hilo propio; el hilo del juego clona
los píxeles (~7 MB, ~1 ms) y los manda por un canal de **un frame en
vuelo** — el raster y la espera del drawable se solapan en vez de
encolarse. Config de layout por `Arc<Mutex>` snapshot, tamaño de ventana
sellado en cada job, y el drop del presentador cierra el canal.

Verificado: el patrón compone idéntico al mono-hilo (captura), y
`native_smoke` queda 7/7. **Y medido en la partida real: 30084 frames/
633 s = avg 47.5 fps (×1.84 vs el 25.8 de M1.0), 10.5 min sin freeze**;
los 131 dry/min son la cadencia sub-60. Con esto, la cuenta del M3
queda: Vulkan 58.1 · metal+software 47.5 · HardwareMetal (M1.1)
el camino de los 60.

**Y la confirmación del flame-graph (la sesión del 2026-11-01, con el
present desacoplado corriendo): el 66% del hilo del juego ya no espera
el drawable — espera el `rayon::LockLatch` del fill del raster software**
(529% CPU en el pool de bandas). El present salió del presupuesto del
todo; lo que queda es la pared de CPU del raster MM3D a 3x, y esa es
exactamente la diana del M1.1 (`HardwareMetal`). A 2x el fill baja ~×0.4
y la jugabilidad vuelve a ~55 fps mientras M1.1 llega.

## Riesgos consumados del M1.0

### El bug del blanco, de caza (2026-11-01)

La primera sesión del jugador con `--renderer metal` mostró una ventana
**en blanco** con el juego corriendo a ciegas (audio y navegación OK).
Cinco fugas reales detrás, encontradas con readback de píxeles del
drawable (blit 2×2 → `getBytes`) y con validación de Metal:

1. **`presentDrawable` ausente** — el frame se codificaba y se hacía
   commit, pero CoreAnimation nunca compone: ventana blanca eterna.
2. **el fetch de vértices de 72-floats** — bytes correctos verificados
   por log, binding correcto, validación silenciosa… y cero fragmentos.
   Con esquinas compiladas por `vertex_id` y el rect por draw, sí dibuja.
   El fetch-por-puntero queda en la lista de "noconfiables" para Metal.
3. **uv invertido** — la fila 0 del upload es la parte alta de la
   pantalla; `v` debe crecer hacia abajo.
4. **tomos de textura** — solo se vinculaba una textura para todos los
   quads; ahora un draw por pantalla vincula la suya.
5. **`top_width` en `1.0`** — `present.rs` no reenviaba
   `set_top_width/set_layout/set_stereo/set_scaling` a Metal: el layout
   corría con top_width 1.0 y el top screen quedó de **3 px de ancho**.

`framebufferOnly` queda en false (el sample y el readback lo exigen;
coste de composición asumido hasta M2.1). El resto del presente usa
solo caminos que Metal demostró dibujar en esta máquina.

## Riesgos consumados del M1.0

- **AGX writeRegion en Private crasheaba (KERN_INVALID 0x4000)** en macOS
  26.5 con texturas "GPU optimized": la solución estándar
  (`setAllowGPUOptimizedContents(false)` + StorageMode Managed) ya está en
  el MetalPresenter del fork — el upload por frame termina en 1600-byte
  rows lineales.
