# Walkthrough — de tu dump al juego corriendo en el Mac

Guía end-to-end para usar ctr-native. El camino corto:

    tu dump legítimo (.3ds/.cia) → build_app_from_3ds.py → <Juego>.app + sandbox → doble clic

Nada del juego entra a git ni se copia fuera del disco: la app apunta a tu dump
por ruta absoluta y el archivo original no se mueve ni se borra.

## 1. Qué necesitas

- macOS 11+ en un Mac Apple Silicon (probado en M1 Pro, 16 GB).
- Tu propia imagen de juego: tarjeta `.3ds`/`.3dz`/`.cci` o CIA (la legal tuya).
- Si la imagen va encriptada, tus `boot9` y keys: **nunca salen de tu máquina**
  y no se incluyen en ninguna app ni en los reportes de bug.
- (Opcional, host clásico) Azahar instalado en `/Applications/Azahar.app`.

## 2. Construir la app

En la carpeta donde tengas el(los) dump(s):

    python3 scripts/build_app_from_3ds.py .

Flags útiles:

| Flag | Para qué |
|---|---|
| `--host zakuro` | (default) host Rust AOT nativo: binario + librería AOT dentro del bundle |
| `--host azahar` | el host clásico de Azahar, mismo sandbox por juego |
| `--app-name "Mi Nombre"` | nombre de la app distinto |
| `--resolution-factor n` | factor de escala de la ventana |
| `--no-icon` | saltar el icono si el SMDH no acompaña |
| `--allow-damaged` / `--no-verify` | versiones distintas al pin MD5 del profile |
| `--progress json` | progreso legible por máquinas, una línea JSON por acontecimiento |
| `--launch` | humo post-empaquetado: `zakuro --headless 120 --mute` (~3 s) |

La salida produce dos carpetas que se llevan juntas:

    <Juego>.app                  el bundle (solo código: launcher, host, AOT, icono)
    <Juego>.app.ctr-native/      la sandbox de datos: settings, saves, mods,
                                 cheats, shader caches y zakuro.log — por juego

La llave `ctr-native.key` guarda las entradas (hash del ROM, sello del binario
host, perfil, icono): si vuelves a hacer build sin cambios, nada se reescribe y
la sandbox —y con ella el save— no se toca. Si cambias el binario host (por
ejemplo, actualizando el port), el re-pack re-firma cada Mach-O ad-hoc sin
tocar la sandbox.

Si mueves la app: haz rebuild para re-anclar sus rutas absolutas; **la sandbox
vale igual donde esté** (muévela junto a la app y la llave evita reconstruir
innecesariamente).

## 3. Jugar

Doble clic en `<Juego>.app`. El launcher apunta al dump absoluto, pone `HOME`
en la sandbox hermana (por eso ninguna configuración global del Mac se toca) y
exec el host:

- Con `--host zakuro`: corre el código del juego **AOT recompilado a arm64**
  (no interpreta), raster hardware por Vulkan (MoltenVK) con present FIFO,
  audio por el path HLE del DSP.
- Con `--host azahar`: corre `-f <rom>` con el mismo flujo de sandbox.

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
segunda ventana por monitor (F7).

**Ventana única** — las dos pantallas 3DS compuestas dentro, con 5
disposiciones (F9/F10). F11 fullscreen del monitor actual.

**Segunda ventana** (el modo multi-monitor, F7): menú Esc → Settings →

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
  archivo con logs, versiones y entradas; **sin keys dentro, por diseño**.
- **"MD5 does not match…"**: tu dump es otra edición (región/versión). O
  actualiza el pin del profile (`dm/games/<title id>/profile.tsv`) o corre con
  `--allow-damaged`.
- **Icono gris**: `--no-icon` o `--app-name "…"` (evita el SMDH). No es fatal.
- **Arranque lento la primera vez**: compilación de shaders por delante; los
  próximos arranques parten del cache guardado.
- **Ya no corre tras un update del port**: rebuild completo
  (`cargo build --release` en `vendors/zakuro` y fase 2 de nuevo).

## 6. El estado conocido ("nativo-total")

El boot nativo (CPU vía AOT, GPU por Vulkan/MoltenVK, audio HLE) está medido y
funcionando. Lo que aún NO es perfecto —en `docs/roadmap.md` como F8—:

1. el shading de vértices puede caer a CPU según el juego (el raster es GPU);
2. underruns de audio esporádicos ("the sound ran dry");
3. el servicio cecd (StreetPass) deja avisos por comandos sin implementar (ALBW no lo usa);
4. Vulkan pasa por MoltenVK→Metal (estándar del sector; no es Metal directo);
5. KPI realtime en ventana sin formalizar del todo (G5 en curso).

## 7. Glosario

- **NCSD/NCCH**: la caja de la ROM del cart (tabla de particiones) y cada
  partición estructural del juego 3DS. Nuestros parsers hacen solo lecturas
  acotadas de cabeceras; el decipher ocurre en el stage decrypt.
- **AOT**: `3dsrecomp` traduce el código ARM11 del dump a código arm64 nativo
  por adelantado; el runtime lo ejecuta sin interpretar (440.9 MIPS medidos en
  headless ×600 frames vs 83.7 del intérprete).
- **HLE**: emulación de propósito alto: el kernel y los servicios (FS, DSP,
  HID…) deciden sus llamadas sin emular sus circuitos.
- **MoltenVK / portability**: el driver traductor de Vulkan sobre Metal en
  macOS; para que el instance lo liste, se pide
  `VK_KHR_portability_enumeration` + el flag `ENUMERATE_PORTABILITY_KHR`.
- **Sandbox**: la carpeta hermana `<app>.ctr-native/` con tu `HOME` del juego:
  settings, saves, caches, logs. Se crea y jamás se actualiza en un re-pack.
- **`.key`**: `ctr-native.key` — fingerprint de las entradas del build;
  coincide = nada se reescribe; cambia = re-pack con firma nueva.
