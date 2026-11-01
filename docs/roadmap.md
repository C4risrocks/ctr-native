# Roadmap F7–F8 (pendientes y decisiones)

## Estado actual — 2026-11-01

- Pipeline común de ocho etapas; AOT automática desde caché validada.
- P1-1/P1-2 corregidos en `ca51d6a`; P1-3/P1-4 en `725bb82`.
- Los cinco P2 conservan su detalle y estado en el [plan del refactor](../PLAN_REFACTOR_PIPELINE.md).
- Majora USA validada; objetivo EUR pendiente en su [plan](../PLAN_MAJORAS_MASK_3D.md).
- Metal: presentación experimental con raster software; HardwareMetal y overlays
  pendientes. Consultar [plan Metal](plan-metal.md).
- Validación física con dos monitores y comparación controlada de rendimiento
  siguen separadas de los smokes sintéticos. Las mediciones de sesiones están
  fechadas en [zakuro-macos](zakuro-macos.md).

## Registro histórico F7–F8


> Registro histórico: las mediciones y cierres se refieren a sus revisiones
> originales. El estado vigente está en [el backlog](../PLAN_REFACTOR_PIPELINE.md)
> y [development.md](development.md). La presentación Metal ya existe; el raster
> HardwareMetal y las correcciones P2 documentadas siguen pendientes.

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
| F7-2 Config ✅ hecho | **ya en el fork (0007)**: settings `CompanionWindow` + `companion_monitor` (toml con defaults), CLI `--split on|off` / `--monitor-bottom <n>` con `-h` completo, `--split-spike` alias | Persistencia settings.toml ✓ |
| F7-3 Pulido ✅ hecho | **a. menú live (0008)**: panel Esc aplicado al instante; **b. touch en la companion (0009)**: misma matemática de placing sobre su propia ventana/arreglo (top sola = sin touch); cerrar suelta el touch. El DPI exacto por monitor lo da el `layout()` físico que ya corría | ALBW: tocar la bottom en la companion pincha donde debe (por verificar en la Mac real con el replay del 4.5 h) |
| F7-4 Empaquetado ✅ hecho | `cargo build --release` (toolchain rustup a mano) + `build_app_from_3ds.py . --progress json --launch`: llave invalidada por el stamp del binario → re-pack firmado ad-hoc por Mach-O + seal; **saves intactos (mtime previo/presente iguales)**, `codesign --verify --strict` OK, humo headless 3.2 s verde | Hecho y verificado |
| F7-5 Docs ✅ hecho | `docs/walkthrough.md` sección 4 con el modo dual (menú + CLI + atajos), `docs/roadmap.md` cerrado, serie de parches `0001..0009` con README | Hecho |

## F8 · Los gaps del "total"

| Sub | Gap | Ancla exacta | Trabajo | KPI de salida |
|---|---|---|---|---|
| **G5 ✅ hecho** | KPI realtime sin formalizar | `zakuro/src/report.rs` + `--profile` | fps avg/min, underruns de audio y % de draws CPU-shaded en el reporte windowed; capturable por el builder | **Tabla viva en `docs/zakuro-macos.md`**: 3 corridas de 600 f measured (471.2 MIPS software / 2409.1 MIPS hardware-CPU-shading / 357.0 MIPS hardware-GPU-shading) + línea `session kpi` al cerrar ventana |
| **G2 ✅ hecho (verificación de sesión windowed pendiente)** | Audio: underruns ("sound ran dry") | `zakuro/src/audio.rs` (cpal 0.16) | Context7 `/rustaudio/cpal`: `BufferSize::Fixed` con fallback documentado | Callback pinneado a 2048 frames (CONFIG TARGET 4096 deja profundidad) con fallback al buffer del host + log de qué se llevó; el contador de underruns de G5 mide el antes/después en la próxima sesión windowed | 0 "sound ran dry" en 60 s de ALBW (por medir en sesión real) |
| **G1 ✅ auditado (medido)** | Shading de vértices por CPU | `raster/hardware.rs::shades()` + ramas en `raster.rs` | El path GPU ya existe y llega al 100% (`ZAKURO_GPU_SHADERS=1`); en M1 Pro corre 6.7× más lento que el CPU shading (357 vs 2409 MIPS en las mismas 600 frames) → **el default del fork es correcto en Apple Silicon** | Se mantiene el default CPU en integradas; se revisita si mejora MoltenVK o tras G4 (Metal-direct) |
| **G3 ✅ hecho** | `cecd:u` 0x0012 (OpenAndRead, el inbox de StreetPass) | `zakuro-core/src/services/cecd.rs` | 3dbrew confirma la ABI (0x00120104 = OpenAndRead); el box offline lee vacío con success, como el daemon ya piensa ALBW | Test in-crate `the_inbox_reads_empty_offline` en verde + boot real sin WARN cecd; patch `0005-*` |
| **G4 → M en marcha** | Vulkan (MoltenVK) vs Metal-direct | — | El disparador se cumplió (MM3D 59.6 fps < 60) → plan Metal aprobado: `docs/plan-metal.md`; **M0 spike verificado (60.1 fps on-screen con CAMetalLayer)**; M0.5 ✓ GO (189/189 MSL) · **M1.0 present-parity ✓** (presente por CAMetalLayer a 60.2 fps, fix AGX 26.5) · **M2 ✓** (companion Metal, settings, smoke 7/7) · M1.0.5 present-desacoplado ✓ (patch 0019) · M1.1 raster HardwareMetal ⏳ backlog | Plan Metal abierto |

## Pases de ejecución (commit/push por fase) — **todos ejecutados 2026-10-30**

- **Pase 1 ✅** — F7-0 (spike, `fb83a92`) → F7-1 modelo (`b55352d`) → G5 KPI (`12e136d` antes del refactor).
- **Pase 2 ✅** — F7-2 settings+CLI (`2d54507`) → F7-3 menú live (`b4c7109`) → F7-3b touch (`5b223a7`) → F7-4 re-pack (`29cd138`) → F7-5 docs (`5a79b74`).
- **Pase 3 ✅** — G3 cecd (`10d95c7`) → G2 audio (`7448621`) → G4 informe (este commit).

Queda abierto por diseño: la **validación visual del modo dual en Mac con
dos monitores reales** (por el usuario, cuando quiera) y la medición
windowed del audio (la `session kpi` lo da sola al cerrar la sesión).

## Guardas del repo (AGENTS.md)

- Nada del juego ni de keys entra a git (`.gitignore` ya lo bloquea).
- Los parsers no cambian en F7/F8; G3 añade su test in-crate del fork.
- `dm/games.py` perfiles afianzan `verified_md5`; el runtime lee su propio
  `settings.toml` en la sandbox — nada de prereescribir ajustes de jugador.
- La lista de stages del builder no cambia; `docs/development.md` queda igual.


## Auditoría de integridad — 0.2.0 (2026-10-31)

La implementación posterior a F7/F8 corrige descifrado y límites de todos los
contenedores, publicación transaccional, reutilización verificada, overrides
reales de idioma/escala y diagnósticos/limpieza acotados. F7 ahora comparte el
dispositivo Vulkan y un pool de hasta tres imágenes de presentación por surface,
retenidas hasta finalizar sus consumidores. OpenGL recupera el frame seleccionado.

La serie completa está fijada en `vendors.lock.json`, incluido el parche 0012.
Resultados y límites de la validación: [audit-implementation.md](audit-implementation.md).
Los estados históricos de las tablas anteriores no sustituyen esa evidencia.
La validación física con dos monitores y el audio de una sesión real continúan
separados de las pruebas sintéticas automatizadas.
