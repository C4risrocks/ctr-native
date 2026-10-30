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
| F7-0 Spike | `zakuro-gpu`: poder crear 2 superficies sobre un device compartido (`Backend::shared_device()` ya exponía el Arc); dos ventanas winit, una por monitor, con `--test-pattern` | 2 superficies vivas, resize/fps por superficie; fallback documentado si MoltenVK se rehúsa |
| F7-1 Modelo | `zakuro/src/lib.rs`: ventanas por rol (main = top + GUI egui + menús + teclado; companion = bottom + touch), eventos por `WindowId`, fullscreen por ventana, cerrar la companion revierte | Con split off: comportamiento byte-exacto a F6 |
| F7-2 Config | `settings.rs` + menú Esc ("Pantallas en monitores": listar `available_monitors()`, asignar top/bottom, intercambio, aplicar al instante) + CLI `--split`, `--monitor-top/bottom` con `-h` completo | Persistencia settings.toml + elegir monitores desde el juego sin reiniciar |
| F7-3 Pulido | Escala entera por monitor (scale_factor por ventana), drag entre displays, touch exacto con DPI distinto | ALBW: tocar la bottom en el monitor externo pincha donde debe |
| F7-4 Empaquetado | `cargo build --release` (toolchain rustup a mano) + re-pack del builder: la llave `ctr-native.key` se invalida por el stamp del binario y repackea (firma ad-hoc por Mach-O, seal no recursiva), sandbox intacta | Humo headless del builder en verde; saves vivos |
| F7-5 Docs | `docs/zakuro-macos.md` fase F7 + KPI, `docs/playing.md` usuario, export de parches | Docs empujadas; diff upstream listo |

## F8 · Los gaps del "total"

| Sub | Gap | Ancla exacta | Trabajo | KPI de salida |
|---|---|---|---|---|
| G5 | KPI realtime sin formalizar | `zakuro/src/report.rs` + `--profile` | fps avg/min, underruns de audio y % de draws CPU-shaded en el reporte windowed; capturable por el builder | Tabla viva en `docs/zakuro-macos.md` |
| G2 | Audio: underruns ("sound ran dry") | `zakuro/src/audio.rs` (cpal 0.16) | `BufferSize::Fixed` con fallback, prebuffer ring, catch-up; contador visible | 0 underruns en 60 s de ALBW; el racimo final de sesión explicado |
| G1 | Shading de vértices por CPU | `raster/hardware.rs::shades()` + ramas en `raster.rs` | Telemetría de por qué caen a CPU; elevar caminos a SPIR-V compilable (naga ya en build) | ≥95% de draws GPU-shaded en ALBW |
| G3 | `cecd:u` 0x0012 sin implementar | `zakuro-core/src/services/cecd.rs` | Stub con códigos de resultado correctos + test in-crate | 0 WARN cecd en 60 s |
| G4 | Vulkan (MoltenVK) vs Metal-direct | `backend/vulkan.rs` | Solo informe go/no-go: MoltenVK es el estándar del sector y G1 mejora ambos caminos | Informe corto de coste/valor |

## Pases de ejecución (commit/push por fase)

- **Pase 1** — F7-0 → F7-1 → G5 (docs de KPI incluidas) → validación del usuario en la Mac.
- **Pase 2** — F7-2..F7-5.
- **Pase 3** — F8: G2 → G1 → G3 → informe G4.

## Guardas del repo (AGENTS.md)

- Nada del juego ni de keys entra a git (`.gitignore` ya lo bloquea).
- Los parsers no cambian en F7/F8; G3 añade su test in-crate del fork.
- `KNOWN_KEYS` no se toca (sin settings nuevos de Azahar).
- La lista de stages del builder no cambia; `docs/development.md` queda igual.
