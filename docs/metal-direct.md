# G4 · Vulkan (MoltenVK) vs Metal-direct — informe go/no-go

> Registro histórico: las mediciones y cierres se refieren a sus revisiones
> originales. El estado vigente está en [el backlog](../PLAN_REFACTOR_PIPELINE.md)
> y [development.md](development.md). La presentación Metal ya existe; el raster
> HardwareMetal sigue pendiente; P2-6/P2-7/P2-8 están corregidos en `dev`.

Pregunta: ¿vale la pena un backend Metal directo en `zakuro-gpu` en vez de
pasar por MoltenVK (Vulkan→Metal)?

## El costo medido del camino actual (M1 Pro, 600 frames AOT de ALBW)

| Configuración | 600 frames | MIPS | Comentario |
|---|---|---|---|
| Software renderer | 5.71 s | 471.2 | CPU 100% de la geometría |
| Hardware Vulkan + **CPU vertex-shading** (default del fork) | **1.12 s** | **2409.1** | raster GPU, vértices CPU |
| Hardware Vulkan + **GPU vertex-shading** (`ZAKURO_GPU_SHADERS=1`) | 7.53 s | 357.0 | franja `gpu` 6.3 s — cada draw compila/fila pipeline con VS |

Conclusión del dato: el cuello NO está en la traducción Vulkan→Metal del
raster (que corre 2409 MIPS), sino en el pipeline de *shading de vértices por
GPU* a través de MoltenVK. Con el default actual del fork (CPU shading en
GPUs integradas/embedded), **el camino Vulkan ya llega a 2.4 K MIPS** — un
backend Metal-direct replicaría precisamente ese número, no lo borraría.

## Veredicto: HOLD (no este pase)

1. **El caso fuerte de Metal sería el PSO/raster pipeline** (puedes ahorra la
   capa de traducción y el costo del descriptor), no el vértices: con el
   default actual, el vértices ya es el lado rápido (CPU).
2. Es un **segundo backend completo** (~3000+ líneas de metal-rs: device,
   swapchain, pipelines por shader-unit, semáforos, present) con dos ABI
   distintas por mantener; el costo de mantenimiento compite con las mejoras
   del propio fork upstream (que va por Vulkan/GL).
3. El `session kpi` de G5 mide desde ya, así que la decisión metal se puede
   **tomar con datos por sesión**, no por intuición.

## Disparadores para reabrir (revisión con datos)

- `session kpi` windowed muestra fps sostenido < 60 con el raster hardware
  (el actual 2409 MIPS headless lo hace improbable).
- MoltenVK/KosmicKrisp mejora el pipeline de VS por GPU (franja `gpu` < CPU).
- Las APIs de shader pre-transladado (naga→MSL, vía metal-rs o el portal
  Apple dev en Context7) serían el único ahorro real del backend propio.

## Referencias

- `/websites/rs_metal` (metal-rs, 9 512 snippets) y
  `/websites/developer_apple_metal` (Apple dev portal, 15 977) en Context7,
  para dimensionar la plataforma el día que se decida.
- `docs/zakuro-macos.md` — la tabla de KPI con las 3 corridas medidas.
- `docs/roadmap.md` — F8-G4 como informe go/no-go (este archivo).
