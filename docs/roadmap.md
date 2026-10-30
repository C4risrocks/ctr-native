# Roadmap F7–F8 (pendientes y decisiones)

Este archivo persiste el plan en el repo para retomar sesiones futuras sin
perder hilo. El estado de partida es la rama `master` con el port zakuro F0–F6
completado (ver `docs/zakuro-macos.md` para KPI base) y la intención de cerrar
dos frentes: **F7** (multi-monitor) y **F8** (gaps del "nativo-total").

## Decisiones locked (2026-10-30)

1. El modo split de monitores es **Off por defecto**: con split off el arranque
   es byte-exacto a F6 (el humo headless del builder no cambia).
2. El teclado manda al juego **solo desde la ventana main**; la ventana
   companion es touch-only y solo refleja la pantalla inferior.
3. Se avanza **fase a fase** con validación del usuario entre pases; un
   commit/push por fase.
4. **G5 (KPI realtime) entra en el Pase 1**, antes de tocar audio y vértices:
   sin medición formal no se puede juzgar las demás mejoras.
5. Los cambios al fork (`vendors/zakuro`) no entran a git (vendors ignorado);
   cada fase exporta sus parches a `docs/patches/zakuro/` para reproducibilidad
   y PR de cortesía upstream (junto con el parche props2 ya cargado en árbol).

## F7 · Detach de pantallas por monitor

Comportamiento objetivo: con el juego corriendo, decidir dónde vive cada
pantalla — la ventana única de siempre (5 disposiciones) o dividida en hasta
2 ventanas, una por monitor, eligiendo top/bottom desde el menú in-game (Esc),
sin reiniciar y persistente por juego (el settings.toml del sandbox hermano).

| Fase | Contenido | Criterio de salida |
|---|---|---|
| F7-0 Spike ✅ **código done, visual pendiente** | `zakuro-gpu`/app: **ya en el fork** — `--split-spike` abre 2ª ventana plana (Vulkan→OpenGL fallback) sobre el monitor siguiente, presentando la bottom sola desde los mismos frames (patch `0004-*`); eventos solo resize/close; presentación que falla cierra la ventana y sigue el main | KPI: compila limpio, headless intacto (1100+ MIPS spot); la validación de las DOS superficies en DOS monitores queda para el usuario (visual). El device-sharing menor queda para F7-1 |
| F7-1 Modelo ✅ hecho | **ya en el fork (0004 + 0006)**: ventanas por rol (main = top + GUI + teclado; companion = bottom), eventos por `WindowId`, fullscreen ambas, cerrar la companion revierte, settings propagan | Split off ⇒ byte-exacto a F6 ✓ |
| F7-2 Config | `settings.rs` + menú Esc ("Pantallas en monitores": listar `available_monitors()`, asignar top/bottom, intercambio, aplicar al instante) + CLI `--split`, `--monitor-top/bottom` con `-h` completo | Persistencia settings.toml + elegir monitores desde el juego sin reiniciar |
| F7-3 Pulido | Escala entera por monitor (scale_factor por ventana), drag entre displays, touch exacto con DPI distinto | ALBW: tocar la bottom en el monitor externo pincha donde debe |
| F7-4 Empaquetado | `cargo build --release` (toolchain rustup a mano) + re-pack del builder: la llave `ctr-native.key` se invalida por el stamp del binario y repackea (firma ad-hoc por Mach-O, seal no recursiva), sandbox intacta | Humo headless del builder en verde; saves vivos |
| F7-5 Docs | `docs/zakuro-macos.md` fase F7 + KPI, `docs/playing.md` usuario, export de parches | Docs empujadas; diff upstream listo |

## F8 · Los gaps del "total"

| Sub | Gap | Ancla exacta | Trabajo | KPI de salida |
|---|---|---|---|---|
| **G5 ✅ hecho** | KPI realtime sin formalizar | `zakuro/src/report.rs` + `--profile` | fps avg/min, underruns de audio y % de draws CPU-shaded en el reporte windowed; capturable por el builder | **Tabla viva en `docs/zakuro-macos.md`**: 3 corridas de 600 f measured (471.2 MIPS software / 2409.1 MIPS hardware-CPU-shading / 357.0 MIPS hardware-GPU-shading) + línea `session kpi` al cerrar ventana |
| G2 | Audio: underruns ("sound ran dry") | `zakuro/src/audio.rs` (cpal 0.16) | `BufferSize::Fixed` con fallback, prebuffer ring, catch-up; contador visible | 0 underruns en 60 s de ALBW; el racimo final de sesión explicado |
| **G1 ✅ auditado (medido)** | Shading de vértices por CPU | `raster/hardware.rs::shades()` + ramas en `raster.rs` | El path GPU ya existe y llega al 100% (`ZAKURO_GPU_SHADERS=1`); en M1 Pro corre 6.7× más lento que el CPU shading (357 vs 2409 MIPS en las mismas 600 frames) → **el default del fork es correcto en Apple Silicon** | Se mantiene el default CPU en integradas; se revisita si mejora MoltenVK o tras G4 (Metal-direct) |
| **G3 ✅ hecho** | `cecd:u` 0x0012 (OpenAndRead, el inbox de StreetPass) | `zakuro-core/src/services/cecd.rs` | 3dbrew confirma la ABI (0x00120104 = OpenAndRead); el box offline lee vacío con success, como el daemon ya piensa ALBW | Test in-crate `the_inbox_reads_empty_offline` en verde + boot real sin WARN cecd; patch `0005-*` |
| G4 | Vulkan (MoltenVK) vs Metal-direct | `backend/vulkan.rs` | Solo informe go/no-go: **con dato nuevo de costo** — el GPU shading MoltenVK corta 6.7× en M1 Pro; Metal-direct valdría en raster/PSO, no en vértices | Informe corto de coste/valor |

## Pases de ejecución (commit/push por fase)

- **Pase 1** — F7-0 → F7-1 → G5 (docs de KPI incluidas) → validación del usuario en la Mac.
- **Pase 2** — F7-2..F7-5.
- **Pase 3** — F8: G2 → G1 → G3 → informe G4.

## Guardas del repo (AGENTS.md)

- Nada del juego ni de keys entra a git (`.gitignore` ya lo bloquea).
- Los parsers no cambian en F7/F8; G3 añade su test in-crate del fork.
- `KNOWN_KEYS` no se toca (sin settings nuevos de Azahar).
- La lista de stages del builder no cambia; `docs/development.md` queda igual.
