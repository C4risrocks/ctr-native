# Walkthrough — de tu dump al juego corriendo en el Mac

Guía end-to-end para usar ctr-native. El camino corto:

    tu dump legítimo (.3ds/.cci) → build_app_from_3ds.py → <Juego>.app + sandbox → doble clic

Nada del juego entra a git ni se copia fuera del disco: la app apunta a tu dump
por ruta absoluta (o a su copia preparada si estaba cifrado); el original no se
mueve ni se borra. Conserva también esa copia preparada.

## 1. Qué necesitas

- macOS 13.4+ en un Mac Apple Silicon (probado en M1 Pro, 16 GB).
- Python 3.12+, Xcode Command Line Tools y los forks reconstruidos y compilados
  según [development.md](docs/development.md).
- Tu propia imagen de juego: tarjeta `.3ds`/`.3dz`/`.cci` ; CIA aún no se empaqueta.

## 2. Construir la app

Ejecuta los comandos desde la raíz del repositorio, indicando la ROM o carpeta:

    python3 scripts/build_app_from_3ds.py "/ruta/al/juego.3ds" --language es
    python3 scripts/build_app_from_3ds.py "/ruta/a/tus/dumps" --language es

Flags útiles:

| Flag | Para qué |
|---|---|
| `--app-name "Mi Nombre"` | nombre de la app distinto |
| `--scale n` | factor de escala de la ventana |
| `--no-icon` | saltar el icono si el SMDH no acompaña |
| `--allow-damaged` / `--no-verify` | versiones distintas al pin MD5 del profile |
| `--progress json` | progreso legible por máquinas, una línea JSON por acontecimiento |
| `--launch` | humo post-empaquetado: 120 frames headless con audio silenciado y apertura posterior de la app |

La salida produce dos carpetas que se llevan juntas:

    <Juego>.app                  el bundle generado (launcher, host, AOT, icono)
    <Juego>.app.ctr-native/      la sandbox de datos: settings, saves, mods,
                                 cheats, shader caches y zakuro.log — por juego

La llave `ctr-native.key` guarda las entradas (hash del ROM, sello del binario
host, perfil, icono y biblioteca AOT, entre las entradas desplegadas): si vuelves a hacer build sin cambios, nada se reescribe y
la sandbox —y con ella el save— no se toca. El idioma del build (`--language`, inglés por defecto) y la escala (`--scale`,
3 por defecto) son overrides de ejecución: no reescriben settings.toml.

Si cambias el binario host (por
ejemplo, actualizando el port), el re-pack re-firma cada Mach-O ad-hoc sin
tocar la sandbox.

Si mueves la app: haz rebuild para re-anclar sus rutas absolutas; **la sandbox
vale igual donde esté** (muévela junto a la app y la llave evita reconstruir
innecesariamente).

## 3. Jugar

Doble clic en `<Juego>.app`. El launcher apunta al dump absoluto, pone `HOME`
en la sandbox hermana (por eso ninguna configuración global del Mac se toca) y
exec el host:

- El host es **zakuro**: corre el código del juego **AOT recompilado a arm64**
  con fallback del runtime cuando corresponde; raster hardware por Vulkan
  (MoltenVK) con present FIFO,
  audio por el path HLE del DSP.

Controles (el teclado sigue el perfil clásico; un mando de consola o Xbox se
detecta solo): flechas = círculo pad, botones según el mapeado de la ventana
de configuración. Atajos con el juego abierto:

| Tecla | Acción |
|---|---|
| `Esc` | abrir el menú interno (pantallas, filtro, etc.) |
| `F1` | pausa / reanuda |
| `F9` | cicla el arreglo de pantallas (apiladas, lado a lado, top grande, solo top, solo bottom) |
| `F10` | cambia a la otra pantalla (cuando hay una sola) |
| `F11` | fullscreen (borderless del monitor actual) |
| `F5` / `F8` | guardar / cargar state (savestates del host) |

Los saves del juego viven en la sandbox (`Application Support/zakuro/user/
savedata/…`, más `nand`, `sdmc`). El shader cache acelera los próximos
arranques; déjalo estar.

## 4. Pantallas y monitores

Hoy el port trae **los dos**: el de la ventana única de siempre y el de la
segunda ventana por monitor.

**Ventana única** — las dos pantallas 3DS compuestas dentro, con 5
disposiciones (F9/F10). F11 fullscreen del monitor actual.

**Segunda ventana** (el modo multi-monitor): menú Esc → Settings →

| Setting | Qué elige |
|---|---|
| `Second window` | `Off, one window` · `The bottom screen alone` (la del touch) · `The top screen alone` |
| `Second window's monitor` | el monitor después del de la main, o cualquiera de la lista de escritorio (nombres reales del sistema) |

El cambio se aplica **al instante** (se abre/mueve/cierra sin reiniciar el
juego) y **queda recordado** en el settings.toml de la sandbox por juego.
Detalles:

- F11 va fullscreen **ambas** ventanas a la vez.
- La ventana complementaria maneja el touch de la pantalla que muestra: los
  clics en la bottom de la companion llegan al juego con la misma matemática
  de coloca-pantalla que la main.
- El teclado sigue llegando desde la main; la companion sólo resizes y
  cierres.
- Cerrar la companion deja la partida como estaba: la main vuelve con todas
  las pantallas.
- Por línea de comandos (solo para la corrida actual): `--split on|off` y
  `--monitor-bottom <n>` (orden del escritorio, 0 primero); `--split-spike`
  es el alias antiguo de `--split on`.

⚠️ El truco de arrancar dos veces el emulador **no** es el mismo modo: son
dos ejecuciones divergentes del juego.

## 5. Cuando algo falla

- **El log vivo de la última sesión**:
  `…/<Juego>.app.ctr-native/home/Library/Application Support/zakuro/zakuro.log`.
  Es el primer dato a leer: boot, presentación (Vulkan/GL), underruns de audio.
- **Reporte de bug**: `python3 scripts/bug_report.py "<Juego>.app"` arma un
  archivo con logs, versiones y entradas; **solo metadatos y logs admitidos; rechaza enlaces y tablas de keys**.
- **"MD5 does not match…"**: tu dump es otra edición (región/versión). O
  utiliza el perfil de esa edición; `--allow-damaged` permite continuar pero
  no verifica compatibilidad ni sustituye la validación del dump.
- **Icono gris**: revisa el SMDH o utiliza `--no-icon` para omitirlo. Cambiar
  `--app-name` solo cambia el nombre del bundle.
- **Arranque lento la primera vez**: compilación de shaders por delante; los
  próximos arranques parten del cache guardado.
- **Ya no corre tras un update del port**: rebuild completo
  (`cargo build --release` en `vendors/zakuro` y fase 2 de nuevo).

## 6. El estado conocido ("nativo-total")

El boot nativo usa AOT, raster Vulkan/MoltenVK y audio HLE. La companion
Vulkan comparte dispositivo e imágenes con la main; OpenGL usa píxeles de
reserva cuando no puede compartir ese dispositivo. `--split off` prevalece
sobre la preferencia guardada.

La implementación y las pruebas sintéticas no sustituyen una sesión física:
quedan por registrar resultados en dos monitores reales y métricas de audio
windowed. Metal presenta de forma experimental con raster software.
HardwareMetal tiene H1–H4 implementados y probados, pero H5 todavía no
conecta el despacho del juego; H6/H7 y el overlay M2.1 siguen pendientes.
Vulkan continúa como opción predeterminada.

## 7. Glosario

- **NCSD/NCCH**: la caja de la ROM del cart (tabla de particiones) y cada
  partición estructural del juego 3DS. Nuestros parsers hacen solo lecturas
  acotadas de cabeceras; el decipher ocurre en el stage decrypt.
- **AOT**: `3dsrecomp` traduce el código ARM11 del dump a código arm64 nativo
  por adelantado; el runtime puede recurrir al intérprete para código no
  recompilado (440.9 MIPS históricos medidos en
  headless ×600 frames vs 83.7 del intérprete).
- **HLE**: emulación de alto nivel: el kernel y los servicios (FS, DSP,
  HID…) deciden sus llamadas sin emular sus circuitos.
- **MoltenVK / portability**: el driver traductor de Vulkan sobre Metal en
  macOS; para que el instance lo liste, se pide
  `VK_KHR_portability_enumeration` + el flag `ENUMERATE_PORTABILITY_KHR`.
- **Sandbox**: la carpeta hermana `<app>.ctr-native/` con tu `HOME` del juego:
  settings, saves, caches, logs. Se crea y jamás se actualiza en un re-pack.
- **`.key`**: `ctr-native.key` — fingerprint de las entradas del build;
  coincide = nada se reescribe; cambia = re-pack con firma nueva.

## Comportamiento actual del builder

AOT se genera automáticamente; las herramientas nativas se preparan una vez.
Conserva la ROM externa, incluida su copia preparada, en la ruta del launcher.
`--no-keep-directories` elimina solo `extract` del build seleccionado: conserva
ROM preparada, caché AOT, logs y datos del jugador. Consulta
[development.md](docs/development.md) para las ocho etapas y sus limitaciones.

## 8. Walkthrough del mantenimiento y la siguiente entrega

El panorama vigente está en [ESTADO_PROYECTO.md](ESTADO_PROYECTO.md).
El trabajo restante y los criterios de cierre están en el
[plan raíz](PLAN_REFACTOR_PIPELINE.md#plan-restante-después-de-h4).

Para reconstruir las herramientas desde el árbol fijado:

```sh
python3 scripts/bootstrap_vendors.py
rustup toolchain install 1.99.1 --profile minimal
cargo +1.99.1 build --release --locked --manifest-path vendors/zakuro/Cargo.toml
cargo +1.99.1 build --release --locked --manifest-path vendors/3dsrecomp/Cargo.toml
python3 scripts/bootstrap_vendors.py --verify-only
```

Para compilar y probar el código Metal experimental, añade `--features metal`
al build/test de Zakuro. Esto habilita sus módulos; todavía no conecta el raster
HardwareMetal al juego. La presentación Metal existente es una función distinta.

Validaciones locales, sin datos de juegos:

```sh
python3 -m unittest discover -s dm/tests -t . -p 't_*.py'
ruff check dm scripts
pyright dm scripts
python3 -m dm.tests.fuzz_containers --iterations 2000
CTR_REQUIRE_REAL_AOT=1 python3 -m unittest dm.tests.t_build.PipelineTests.test_real_3dsrecomp_integration_when_available -v
cargo +1.99.1 test --locked --workspace --manifest-path vendors/zakuro/Cargo.toml
cargo +1.99.1 test --locked --workspace --features metal --manifest-path vendors/zakuro/Cargo.toml
```

La integración AOT obligatoria requiere haber compilado 3dsrecomp. Las pruebas
GPU necesitan un Mac con los backends correspondientes. En CI, la variante Metal
se compila con `--no-run`; esa compilación no equivale a ejecutar sus pruebas GPU.
Los smokes gráficos usan el binario release con los features de cada escenario;
consulta [desarrollo](docs/development.md) antes de lanzarlos.

Después de cada hito: ejecutar sus pruebas, exportar el cambio del vendor como
parche numerado, actualizar el lock y reconstruir desde clones nuevos. Actualizar
el estado, este walkthrough si cambia el flujo y el plan raíz antes de publicar
en `dev`. No integrar en `master` ni declarar M1.1 cerrado por pasar una fixture.

El siguiente paso es H5: conectar configuración, carga del título y rasterize a
GuestDraw, con fallback coherente y errores tipados. H6 añadirá batching y
presentación compartida; H7 medirá paridad y rendimiento. Los resultados reales
se registrarán por ROM/edición y revisión, conservando el sandbox del jugador.
