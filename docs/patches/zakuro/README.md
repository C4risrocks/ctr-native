# Parches del fork `vendors/zakuro`

`vendors/` se mantiene fuera de git. `vendors.lock.json` fija los commits
upstream y el árbol final esperado después de aplicar esta serie.

```sh
python3 scripts/bootstrap_vendors.py
cargo +1.99.1 build --manifest-path vendors/zakuro/Cargo.toml --release --locked
cargo +1.99.1 build --manifest-path vendors/3dsrecomp/Cargo.toml --release --locked
python3 scripts/bootstrap_vendors.py --verify-only
```

El bootstrap nunca resetea clones existentes. Exporta cada cambio del fork
como otro parche numerado y actualiza su hash de árbol en el lock.

| Parche | Qué hace | Estado |
|---|---|---|
| `0001-darwin-opt-in-to-Vulkan-portability…` | el instance opta por `VK_KHR_portability_enumeration` + flag `ENUMERATE_PORTABILITY_KHR` (backend/vulkan.rs + raster/hardware.rs::own_device); verificado runtime en M1 Pro | listo para PR upstream |
| `0002-gpu-get-physical-device-properties2…` | props2 corre junto a portability: `VK_KHR_portability_subset` lo exige por spec el día que se active; prop2 es core 1.1, gratis en macOS (patrón de ash-examples) | listo para PR upstream |
| `0003-gpu-a-session-kpi…` | KPI de sesión: buckets de shading por draw (gpu/cpu) en `rasterize`; underruns totales; `session kpi` al cerrar ventana; headless imprime los buckets; KPI medidos en `docs/zakuro-macos.md` | local (insumo F8-G5) |
| `0004-app-the-split-monitors-spike…` | **F7-0 spike**: `--split-spike` abre una segunda ventana plana (Vulkan, fallback OpenGL) sobre el monitor siguiente del main, presentando la pantalla bottom sola desde los mismos frames; sus eventos solo resizan/cierran; falla ⇒ cierra y sigue landing el main | spike: validación visual pendiente del usuario; default off ⇒ F6 byte-exacto |
| `0005-cecd-openandread-reads-an-empty-box-offline…` | **F8-G3**: cecd:u OpenAndRead (0x0012) lee el inbox de StreetPass vacío offline — success sin mensajes, como el box contesta; test in-crate del header (ALBW lo abre en cada boot); boot real sin WARN | listo para PR upstream |
| `0006-app-f11-goes-borderless-on-both-windows…` | **F7-1**: F11 borderless las dos ventanas a la vez y `apply_layout` propaga shape/filter/3D a la companion (su layout queda BottomOnly fijo) | local (F7) |
| `0007-app-settings-the-second-window-becomes-a-setting.patch` | **F7-2**: `CompanionWindow` (off/bottom/top) y `companion_monitor` en settings.toml (serde con defaults); CLI `--split on|off` + `--monitor-bottom <n>` (solo la corrida) y `--split-spike` como alias; off ⇒ arranque byte-exacto | local (F7) |
| `0008-app-settings-the-second-window-asks-in-the-menu-live.patch` | **F7-3a**: panel en el menú Settings ("Second window" / "Second window's monitor") con la lista de monitores del escritorio; el say de settings se aplica **live** (abre/mueve/cierra sin reiniciar); `--split/--monitor-bottom` conservan su folleto sobre la corrida | local (F7) |
| `0009-app-the-companions-pointer-touches-the-screen-it-shows.patch` | **F7-3b**: los clics y movimientos de la Companion tocan la pantalla que muestra (la misma matemática de placing con su propia ventana y arreglo; la top sola no toca nada); cerrar la ventana suelta el touch | local (F7) |
| `0010-audio-the-outputs-callbacks-pin-at-2048-frames.patch` | **F8-G2**: callbacks de audio pinneados a 2048 frames (~4/100 s, bajo el depth del queue 4096) con fallback del host anotado; el `session kpi` mide el antes/después | local (F8) |
| `0011-loader-a-bundled-librarys-hints-are-not-written-bes.patch` | **Integridad del sello**: una librería desplegada dentro del bundle no escribe su `.hints` (padre sellado); el packer pre-siembra el `.hints` instalado como extra_file sellado | local (ctr-native) |
| `0012-gpu-shared-presentation-and-runtime-overrides.patch` | GPU compartida entre superficies, pool de tres imágenes upright con propiedad y fences por consumidor, semáforos por imagen de swapchain, lectura exacta de frame para fallback GL, extensión portability subset, contextos GL, `--language`, precedencia de `--split off` y diagnóstico GPU sintético con cierre acotado | implementado; tests y humo documentados en development.md |
| `0013-menus-the-games-paused-menu-asks-for-the-second-window.patch` | **F7**: las opciones de segunda ventana/monitor llegan también al menú de Esc (Paused), aplicadas en vivo vía `Action::Settings`; los monitores del escritorio se re-listan con el menú abierto | local (F7) |
| `0014-gpu-the-metal-spike-m0.patch` | **Metal M0**: feature `metal` (objc2-bindings) con `--renderer metal`, `MetalPresenter` de spike sobre `CAMetalLayer` y triángulo timed; 90 frames on-screen a 60.1 fps, empate con Vulkan | local (Metal M0) |
| `0015-app-the-metal-spike-warns-when-asked-outside-the-test.patch` | **Metal seguridad**: fuera del test-pattern, `--renderer metal` marca en el log que la pantalla es del spike y las pantallas del juego siguen por los otros backends | local (Metal) |
| `0017-metal-m10-present-parity-metalfixes.patch` | **Metal M1.0+M2**: las pantallas del juego como texturas Metal por `place()`, fix `setAllowGPUOptimizedContents(false)` + StorageMode Managed (driver AGX 26.5), settings `renderer: metal` + combo, companion por renderer-kind del main | local (Metal) |
| `0018-metal-present-root-cause-fixes.patch` | **el blanco del M1.0, resuelto**: `presentDrawable` antes del commit, rect-per-draw de 16 bytes + esquinas por `vertex_id` (el fetch de 72-floats nunca rasterizaba), uv con la fila 0 arriba, `set_top_width/set_layout/set_stereo/set_scaling` reenviados (top de 3px), `framebufferOnly` off | local (Metal) |
| `0019-metal-present-decoupled-thread.patch` | **M1.0.5**: el present Metal sale a thread propio — bundle completo por canal de 1 frame en vuelo, layout por snapshot `Arc<Mutex>`, texturas en ping-pong; quita los ~16 ms de `nextDrawable` del presupuesto del raster (25.8 → objetivo ~50 fps con software) | local (Metal) |

`0018a-metal-feature-gates.patch` exports f7c8e6f before 0019; it restores
feature guards for non-Metal builds and the exact base required by 0019.

Estado 2026-11-01: serie 0001–0019 con 0018a intercalado, reproducida desde
upstream y comprobada contra vendors.lock.json en el cierre P1 (725bb82).
Los P2 de Metal siguen abiertos en el plan del pipeline.
| `0021-metal-m11-a1-hardware-rack-translates.patch` | **M1.1 A1**: el rack completo del raster hardware (shade/vert/frag×2, transfer, depth, upright×2) pasa por naga `msl-out` desde los MISMOS fuentes GLSL — el device compila **8/8** (23 ms de traducción); `compile_msl_stage` generaliza a cualquier stage+defines; `prepare()` cierra las 3 brechas de naga (samplers separados, spec-consts, push_constants a binding 24) | local (Metal) |
| `0022-metal-m11-a2-pipelines-and-float-depth.patch` | **M1.1 A2**: `HardwareMetal` (device+queue+las 8 librerías del rack) y `graphics_pipeline` espejando el descriptor de Vulkan (RGBA8, vértices placed 6×Float4/24-floats, depth+stencil un par). **Hallazgo: Apple silicon no renderiza D24S8 — el default es el float twin D32F_S8** (la misma necesidad que cubría el fallback float_depth de Vulkan) | local (Metal) |
| `0023-metal-m11-a3a-execution-chain-to-pixels.patch` | **M1.1 A3a**: la cadena de ejecución corre hasta píxeles — GLSL inline por el mismo camino de traducción, pipeline, vertex buffer en Shared, encoder, commit, wait del GPU y `getBytes` con asserts por píxel (verde/navy en los 4 cuadrantes) | local (Metal) |
| `0024-metal-m11-a3b-pic-fragment-semantics.patch` | **M1.1 A3b**: el raster.frag real corre sobre Metal con las uniformes PICA del Draw block (DYNAMIC=1, combiners passthrough verificados por píxel verde/rojo, letterbox navy); `prepare(source, values, to_image)` hornea los spec-consts desde el key del pipeline, el mapa de bindings por entry-point verbatim (y el `sizes_buffer` que las Tables runtime-sized piden) | local (Metal) |
| `0025-metal-m11-a3c-compute-bindings-verbatim.patch` | **M1.1 A3c**: los compute shaders del raster con SU mapa de bindings verbatim (transfer/depth/upright/upright_image por `shader_bindings`, push constants en slot 24, el sizes-buffer en 30 por el límite del Metal ABI) — su MSL lleva `[[texture(N)`/`[[buffer(N)` donde los muestran los recursos | local (Metal) |
| `0026-metal-m11-a4-batch-ring.patch` | **M1.1 A4**: el `Ring` — un MTLBuffer Shared del BATCH allocator con el wrap y la flush rule (`RING_SIZE`/`RING_FLUSH`/`IN_FLIGHT` del twin una a una), los spans retirándose por su command buffer; los tests caminan el ciclo completo (climb/retire/wrap/flush/overflow-honesto) | local (Metal) |
| `0027-metal-m11-a4-uniform-staging.patch` | **M1.1 A4**: el staging de las uniformes std140 — `Ring::stage` (next_multiple_of + bounds), `stage_block` (escribe los words little-endian una vez por batch, el dedupe vía `Block::staged_at` del swap) y la ventana de escritura; los asserts por byte después de cada paso | local (Metal) |
| `0028-metal-m11-a4-draw-executor.patch` | **M1.1 A4**: `HardwareMetal::draw_placed` — el executor del app-side end-to-end (uniforms/tables/vertices por el Ring, pipeline per key con los spec words horneados, indexed draw, pass con depth twin) — **el test del executor con los píxeles de los dos halves verificados** | local (Metal) |
| `0029-metal-m11-a4-texture-pool.patch` | **M1.1 A4**: `TexturePool` — las texturas Managed por la identidad de las texels (el Arc del `TextureCache` compartido — **la capa de decode del CPU es gratis para el port**), uploads cuando la identidad cambia, `Retained` de vuelta sin borrows | local (Metal) |
| `0030-metal-m11-a4-surface-from-guest.patch` | **M1.1 A4**: `MetalSurface` — el render target Managed por (addr, kind, w, h, tiled) con el shadow del guest, y `check_surface` (el load-then-match del `surface_rows` de Vulkan: read → decode compartido por morton+format → upload a las filas flipped; el segundo check sin carga; el cambio del guest re-subiendo) | local (Metal) |
| `0031-metal-m11-a4-display-transfer-executor.patch` | **M1.1 A4**: `display_transfer` — el executor de transfers con los dos surfaces del guest honestos (el decode linear/Morton según `tiled`, el push constants verbatim: size/input_h/output_h/scale/flip/formatos) — **el guest's ramp 16×16 promediado a 8×8 verificado por píxel (el ABGR del decode, el rounding del shader)** | local (Metal) |
