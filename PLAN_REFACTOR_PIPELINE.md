# Refactor del pipeline común de ctr-native

## Estado — auditoría corregida; integración Metal en curso

La implementación inicial se integró desde `refactor/pipeline` (`7cb83b0`,
`9a029b7`). La auditoría posterior identificó nueve hallazgos: cuatro P1
corregidos en `ca51d6a` y `725bb82`. En `dev`, P2-6/P2-7/P2-8 están
corregidos; P2-5 corregido en S3; P2-9 corregido en S4.
La tabla de auditoría al final es la referencia de sus estados.

Validación histórica anterior a S4: 77 pruebas Python (una omitida entonces), Ruff,
Pyright y bootstrap local y desde clones nuevos correctos. Los resultados
históricos no implican cierre de los pendientes ni validación de otra edición.
Las secciones de diseño siguientes conservan el objetivo; los detalles aún no
implementados, como la huella completa del compilador/SDK, siguen pendientes.

## 1. Objetivo y alcance

Permitir que **todos los juegos recorran el mismo flujo**, desde la ROM hasta la app validada. Añadir un título requerirá sus datos y pruebas de compatibilidad, sin modificar la orquestación.

El refactor cubrirá Python e integrará la compilación AOT. Se conservarán los parsers, el descifrado, el empaquetado transaccional y los motores Rust existentes.

Decisiones acordadas:

- Zakuro, 3dsrecomp y los compiladores se preparan por separado.
- Las bibliotecas AOT actuales sin procedencia registrada se reconstruyen una vez.
- Cada app conserva su copia de Zakuro y su sandbox.
- La reutilización se evaluará por responsabilidades compartidas y ausencia de lógica específica por juego, sin imponer un porcentaje de líneas artificial.

## 2. Organización e interfaces

Crear `dm/build/` como módulo reutilizable, organizado internamente en modelos, preparación de ROM, AOT, empaquetado y orquestación.

Su interfaz principal será:

```python
build(request: BuildRequest, *, progress, runner) -> BuildResult
```

- `BuildRequest`: entrada y opciones explícitas; no dependerá de `argparse.Namespace`.
- `PreparedGame`: identidad, ROM original, ROM preparada, hashes, perfil y metadatos.
- `AotArtifact`: biblioteca generada, huella y procedencia.
- `BuildResult`: identidad, aplicación publicada y resultados de reutilización y validación.
- `BuildError`: etapa fallida y mensaje útil, sin material de claves.

`scripts/build_app_from_3ds.py` conservará la CLI y sus códigos de salida, pero delegará el trabajo al módulo común.

Centralizar la invocación de Zakuro en `dm/tools/runtime.py`: argumentos, idioma, escala, rutas y entorno. El launcher, el arranque headless y el diagnóstico gráfico usarán esas mismas reglas. La validación recibirá las rutas como datos; dejará de reconstruirlas leyendo el script generado.

Ampliar los helpers existentes de rutas y datos de usuario para evitar definiciones paralelas. Mantener el packer como responsable de firma, publicación atómica y protección del sandbox.

## 3. Flujo completo y reutilización AOT

El pipeline tendrá **ocho etapas comunes**:

1. Descubrir la entrada.
2. Identificar título y perfil.
3. Verificar el dump original.
4. Preparar una copia descifrada cuando corresponda.
5. Obtener o compilar la biblioteca AOT.
6. Preparar metadatos e icono.
7. Empaquetar, firmar y publicar.
8. Verificar la app y, con `--launch`, ejecutar el smoke y abrirla.

La identidad del título deberá coincidir entre ROM original, copia preparada, artefacto AOT y paquete. Nunca se sustituirá automáticamente una edición por otra.

Para AOT:

- Invocar `3dsrecomp build <ROM preparada> <directorio>` mediante argumentos, sin shell.
- Guardar la caché en `<title_id>_build/aot/<huella>/`.
- Calcular la huella con la ROM preparada, los binarios de Zakuro y 3dsrecomp, la identidad del compilador/SDK, la arquitectura y la versión del formato de caché.
- Ejecutar la compilación con un HOME de trabajo aislado, evitando dependencias implícitas de los `.hints` globales. Se conservarán los hints incorporados en 3dsrecomp.
- Registrar un manifiesto versionado con identidad, entradas y hash de la biblioteca. Reutilizar únicamente si manifiesto y contenido coinciden.
- Compilar en un directorio temporal, bloquear por huella y publicar la entrada completa atómicamente.
- Ante error o cancelación, conservar la app anterior y las entradas válidas de caché.

Añadir únicamente `--recompiler-bin` y `--rebuild-aot`. El modo predeterminado será compilar cuando falte una entrada válida y reutilizarla después.

## 4. Compatibilidad y datos por juego

Los perfiles conservarán `profile.tsv` y sus notas. No contendrán funciones Python, callbacks, comandos ni estrategias de compilación particulares.

Se mantendrán:

- Opciones actuales de idioma, escala, icono, claves y salida.
- Nombres y ubicaciones de aplicaciones y sandboxes existentes.
- ROM externa y publicación mediante un candidato firmado.
- Protección de partidas, configuración y fuentes originales.

Los eventos JSON conservarán sus nombres y campos actuales; el total de etapas pasará a ocho. Las salidas de herramientas se capturarán para no contaminar stdout JSON. Los fallos cerrarán su etapa y los fallos del reporte de progreso seguirán sin interrumpir el build.

Actualizar documentación, ayuda, registros y diagnósticos para distinguir compilación, arranque y verificación diferencial AOT. Esta última no se declarará realizada por ejecutar `build`.

## 5. Implementación y aceptación

Realizar el cambio en tres entregas: extracción del motor manteniendo comportamiento, integración AOT con caché y centralización de ejecución/validación.

Pruebas requeridas:

- Construir varios títulos sintéticos, incluido uno sin perfil, mediante la misma interfaz.
- Cubrir ROM clara, cifrada y con partición secundaria cifrada; comprobar que la fuente permanece intacta.
- Verificar reutilización e invalidación AOT por cambios de ROM o herramientas, corrupción, fallo y cancelación.
- Confirmar que cambiar idioma, escala o icono reconstruye el paquete sin recompilar AOT.
- Comprobar aislamiento entre títulos, rutas Unicode y propagación correcta de errores y progreso.
- Mantener las regresiones de firma, publicación atómica, ImageIO y conservación de guardados.
- Ejecutar suite Python, fuzz existente, Ruff, Pyright, bootstrap verificado y smoke gráfico sintético.
- Añadir una integración macOS con 3dsrecomp real y una ROM manufacturada; CI seguirá sin necesitar datos de juegos ni claves.

El refactor estará aceptado cuando un título nuevo pueda recorrer el flujo completo sin añadir condiciones específicas a la CLI o al motor común.

## Auditoría 2026-11-01 sobre be10b73

| Hallazgo | Prioridad | Estado |
|---|---|---|
| 1. Limpieza de builds ajenos | P1 | Corregido: solo extract del build seleccionado |
| 2. Metadatos antiguos tras descifrar | P1 | Corregido: nuevo PreparedGame con partición analizada |
| 3. Selección AOT sin validar contenido/procedencia | P1 | Corregido: manifiesto y SHA-256 verificados; se empaqueta la caché, no la librería global |
| 4. Fork irreproducible: parche 0019 y lock | P1 | Corregido: exportado f7c8e6f como 0018a; lock actualizado; bootstrap nuevo verificado |
| 5. Huella AOT incompleta | P2 | Corregido en dev: caché v2 con SHA-256 de ROM, host y recompilador; compilador C resuelto, hash, versión, argumentos y SDK registrados y fijados en el entorno de ejecución |
| 6. Errores y cierre de etapas JSON | P2 | Completo (branch `dev`): fallos inesperados se normalizan a `BuildError("pipeline", ...)` con `stage_end(ok:false)` del stage abierto; el JSON contiene un único `ev:error` estructurado (`kind`, `stage`, `traceback` solo en inesperados); tests incluidos |
| 7. Sincronización de texturas Metal | P2 | Corregido (branch `dev`): tres sets round-robin + `waitUntilCompleted` del job que muestreó el set antes de reusarlo |
| 8. Canal Metal bloqueante | P2 | Corregido (branch `dev`): el present entra por `try_send` — el loop suelta el frame si el worker va a la zaga; contado y registrado |
| 9. Integración real 3dsrecomp omitida | P2 | Corregido en S4: ARM sintético válido, raíz correcta, fallos sin skip y job macOS obligatorio |

Esta entrega se limita a P1-1 y P1-2. Conserva ROM original, preparada,
caché AOT, logs y sandbox. La preparación devuelve un estado nuevo y valida
que la copia conserve título y no retenga particiones cifradas.

Validación: 72 pruebas Python (una omitida), 2.000 mutaciones sintéticas, Ruff
y Pyright correctos. La suite incluye
empaquetado nativo macOS. Ese registro corresponde a P1-1/P1-2; el bootstrap se verificó al cerrar P1-4.

### Cierre de P1-3 y P1-4

AOT exige la herramienta preparada y verifica formato, título, arquitectura,
huella y SHA-256 antes de reutilizar. Devuelve la biblioteca de esa caché y no
lee ni modifica la instalación global ni incorpora sus hints. Un bloqueo por
huella serializa compilaciones concurrentes. Los binarios instalados sin
manifiesto dejan de ser una vía de reutilización implícita.

El parche 0018a conserva el commit intermedio f7c8e6f antes de aplicar 0019.
Se verificaron ambos forks existentes y se reconstruyeron ambos desde sus
revisiones upstream en un directorio temporal nuevo, aplicando la serie completa.
Los cuatro P1 están corregidos; los cinco P2 conservan su estado indicado.

Validación del cierre P1: 75 pruebas Python (una omitida por la integración
registrada en P2-9), Ruff, Pyright y bootstrap local y desde clones nuevos correctos.

## Estabilización ampliada — ejecución iniciada 2026-11-02

- S1: corregidas las 14 referencias a Transfer, exportadas como 0036;
  lock sincronizado con toda la serie hasta 0036.
- S2: CI habilitado para dev y compilación de tests con Metal; los tests
  que requieren GPU física deben ejecutarse localmente y no contarse como
  validados por compilar en un runner sin GPU.
- Pendientes de esta ampliación: conexión completa M1.1, batches/presentación directa y M2.1.
- Se conserva Vulkan por defecto. El cierre de M1.1 exige paridad y >=85%
  del throughput Vulkan, con benchmark controlado y validación de usuario.

Validación S1/S2: suites nativas default y Metal correctas; bootstrap local
y reconstrucción desde clones nuevos correctos. M1.1/M2.1 no están cerrados.

### Estado documental e higiene — 2026-11-02

Referencia de esta revisión: `dev` en `d3225d2`. Validación local registrada:
483 pruebas nativas sin Metal y 495 con Metal; CI compila los tests Metal,
sin acreditar ejecución con GPU. Vulkan permanece por defecto.

Revisión de higiene: árbol limpio antes de esta actualización, 49 enlaces locales
válidos y ningún artefacto generado ni nombre sensible detectado entre los
archivos versionados. La automatización de higiene en CI sigue pendiente.
Estas comprobaciones no equivalen a una auditoría de secretos del historial.

La documentación conserva los resultados históricos con sus fechas y separa
el estado actual de sus mediciones. La entrega S3 incluye la publicación de `dev`; no integra la rama en `master`.

### S3 — huella AOT v2 implementada

La caché identifica el contenido de ROM, host y recompilador mediante SHA-256.
El compilador C se resuelve una vez y se fija mediante CC; su contenido,
versión y argumentos entran en la huella. SDKROOT se fija al SDK seleccionado
(explícito o xcrun en macOS), con hash de SDKSettings y entorno relevante.
Las entradas v1 quedan conservadas y no se reutilizan. Los SDK deben mantenerse
inmutables: no se calcula un hash de cada header o biblioteca del SDK.
S4 corrige posteriormente P2-9; HardwareMetal y overlay siguen pendientes.

Validación S3: 79 pruebas Python ejecutadas (una omitida por P2-9),
Ruff y Pyright correctos; diff sin errores de espacios.

### S4 — integración real obligatoria

La prueba resuelve el binario desde la raíz correcta y fabrica un NCSD/NCCH
con dos instrucciones ARM y segmento de texto válido en ExHeader. Compila
con 3dsrecomp real y verifica identidad, huella, hash, cabecera Mach-O y
los bytes de la biblioteca empaquetada. Ningún fallo de compilación se omite.

Localmente solo se omite si falta el binario. Con CTR_REQUIRE_REAL_AOT=1
la ausencia falla; el job real-aot-integration de macOS reconstruye los vendors,
compila 3dsrecomp y ejecuta esa prueba con dicha variable. El job es parte
del workflow; exigirlo mediante protección de rama requiere configuración
del repositorio y no se presupone aquí. No utiliza ROMs ni claves reales.

Los cuatro P1 y cinco P2 de esta auditoría están corregidos en dev.
HardwareMetal M1.1, overlay M2.1 y automatización de higiene siguen pendientes.

Validación S4 local: 80 pruebas Python, sin omisiones, con
CTR_REQUIRE_REAL_AOT=1; Ruff y Pyright correctos, 49 enlaces locales válidos
y git diff --check limpio. El resultado remoto de CI se verifica por separado.

### M1.1 A4 — conservación entre draws (0037)

El executor recibe `PlacedDraw.clear`: inicialización explícita o carga del
color y profundidad existentes. Antes borraba ambos en cada draw. La prueba
GPU emite dos draws separados y verifica que el segundo conserva el primero.
Suite Metal completa correcta (rustc/cargo 1.99.1 mediante alias stable local);
la instalación nombrada 1.99.1 requirió reparación de rustup y su proxy cargo
seguía sin funcionar. La versión efectiva se comprobó explícitamente.

Este incremento no cierra M1.1: siguen pendientes despacho real, bindings
completos, batching, presentación compartida y comparación de rendimiento.
`with_hosts` no tiene llamadas en el código actual: el slot de Resources
por sí solo no activa el backend. Vulkan continúa como predeterminado.

Validación 0037: 483 pruebas default y 495 Metal, cero fallos y tres
ignoradas habituales por suite; bootstrap local y desde clones nuevos correcto.
No se ejecutaron benchmarks de juegos ni se acredita cierre de M1.1.

### M1.1 A4 — estado del pipeline (0038)

El PSO respeta las máscaras RGBA PICA mediante conversión al orden de bits
Metal. Los passes sin profundidad usan formato Invalid en ambos attachments
opcionales. El executor rechaza vértices Interpreted y discrepancias entre
key.depth y el attachment antes de reservar staging o enviar trabajo al GPU.

Regresión reproducida: escribir solo rojo modificaba también verde/azul.
La prueba GPU ahora comprueba canales preservados, máscara cero y pass sin
profundidad; otra prueba recorre las 16 combinaciones RGBA. Suite Metal:
496 pruebas correctas, tres ignoradas habituales.

Siguen pendientes bindings completos de texturas/samplers, depth/stencil y
blend efectivos, despacho real, batching y validación de paridad/rendimiento.
Este incremento no cierra M1.1 ni M2.1. Vulkan continúa por defecto.

Validación 0038: 483 pruebas sin Metal y 496 con Metal correctas; bootstrap
local y desde clones nuevos verificado; 49 enlaces locales válidos y diff limpio.

### M1.1 A4 — bindings completos del executor (0039)

`PlacedDraw.textures` contiene tres pares explícitos textura/sampler; sustituye
texture0 y elimina la segunda fuente de uniformes que estaba sin usar. Se
enlazan texturas 0–2, samplers 10–12, Draw en 3, Tables en 4 y la longitud
en bytes de Tables en 30, según el ABI de Naga para el array dinámico.
Las unidades desactivadas se desenlazan explícitamente; activar una unidad
sin su par textura/sampler falla antes del staging. Draw exige sus 408 words
completos: 376 no cubrían luces, procedural y fog según el std140 real.
Los recursos prestados se mantienen válidos hasta terminar el draw síncrono.

Pruebas GPU: cada unidad selecciona un color distinto mediante raster.frag;
la niebla mezcla azul y amarillo mediante Tables y el último vec4 de Draw;
uniformes truncados y unidad activa sin recurso fallan de forma explícita.
La suite Metal mantiene 496 pruebas correctas y tres ignoradas habituales.

Esto cierra los bindings del executor, no M1.1: siguen pendientes generar
el bloque completo desde el estado real (draw_uniform_block aún es parcial),
crear samplers desde el estado PICA, conectar rasterize, depth/stencil, blend,
batching y presentación compartida. No se acredita jugabilidad ni rendimiento.

Validación 0039: 483 pruebas default y 496 Metal correctas, tres ignoradas
habituales por suite; prueba GPU focalizada repetida sobre el árbol final;
bootstrap local y desde clones nuevos correcto; diff sin errores de espacios.

## Plan PICA → Metal — seguimiento por hitos

| Hito | Entrega y aceptación | Estado |
|---|---|---|
| H1 | Estado común: uniformes std140 de 408 words, tablas y Filtering; regresiones Vulkan/Metal | Implementado en 0040 |
| H2 | Texturas/mipmaps y samplers desde PICA, identidad propietaria e invalidación | Implementado en 0041; casos no soportados rechazados |
| H3 | Especialización de fragmentos, depth/stencil, blend, viewport/scissor y pipelines cacheados | Implementado en 0042; validación GPU correcta |
| H4 | Superficies coherentes, fills/transfers, sync CPU, solapamientos y savestates | Pendiente |
| H5 | Selección explícita del backend y despacho real desde carga del título y rasterize | Pendiente |
| H6 | Contexto compartido, batching y presentación directa a ambas ventanas | Pendiente |
| H7 | Paridad, sesiones y benchmark Metal >=85% Vulkan; regresión Vulkan <=5% | Pendiente |

Orden H1→H2→H3→H4→H5→H6→H7; cada hito requiere pruebas, parche, lock,
reconstrucción limpia, documentación y publicación en dev. Vulkan sigue por
defecto; vértices CPU para la primera integración. Overlay M2.1 separado.

### H1 — estado común PICA (0040)

El módulo pica_state comparte el bloque Draw completo, el empaquetado de
lighting/procedural/fog y Filtering con Vulkan. Metal elimina su constructor
parcial de dos unidades y la prueba GPU obtiene uniformes desde registros
mediante el mismo constructor. Los samplers Metal efectivos llegan en H2.
Una fixture comprueba offsets, tres unidades, profundidad, padding y fog.
La asignación temporal al empaquetar tablas se mide junto al rendimiento
en H7; no se presume cumplimiento del presupuesto por pasar los tests.

Validación H1: 484 pruebas default y 497 Metal correctas (tres ignoradas
habituales por suite); bootstrap local y desde clones nuevos verificado.

### H2 — texturas y samplers PICA (0041)

BoundTexture alimenta la subida de todos los mipmaps y el sampler derivado
de Filtering compartido: nearest/linear, mip filter, wrapping y clamps LOD.
La caché retiene el Arc de texels y no vuelve a subir la misma identidad;
una identidad nueva crea una entrada nueva. Se validan dimensiones y longitud.
OwnedTextureBinding conserva textura/sampler durante el draw.

LOD bias no cero, texturas procedentes de superficies y texture packs devuelven
rechazo explícito antes de subir: su fallback coherente se conecta en H4/H5.
El color de borde sigue siendo responsabilidad del shader común.
Prueba aislada de H2: mip cargado y leído, identidad cacheada, propiedad Arc,
longitud inválida y bias no soportado correctos. H3 amplía la prueba de muestreo.

### H3 — estado PICA del pipeline (0042)

RasterState::from_pica interpreta máscara, blend, operaciones lógicas, depth,
stencil y especialización de fragmentos. Las variantes activan iluminación,
procedural y WRITES_DEPTH. El bloque de uniformes/tablas compartido de H1
continúa como fuente de datos; H2 aporta los bindings desde BoundTexture.
El executor aplica viewport/scissor validados, blend constante, depth/stencil
y carga/store del attachment stencil, con cachés de PSO y depth/stencil.
La referencia stencil es dinámica y no multiplica la clave del pipeline.

Pruebas GPU integradas: nearest/linear, repeat/mirror/border, selección mip,
niebla, blend constante, scissor, comparaciones de profundidad, stencil Equal
y Replace, iluminación ambiental, LUT procedural, alpha Never y profundidad
w escrita desde fragmento; además se verifica reutilización de ambas cachés.

Los modos no representables se rechazan antes del draw: operaciones lógicas
distintas de Copy/Noop, bias LOD no cero, fuentes GPU y texture packs. Esto
prepara el fallback; no se declara conectado antes de H4/H5. No se ejecutó
un juego con este raster ni se midió el presupuesto de rendimiento.

Validación H2/H3: 484 pruebas default y 499 Metal correctas (tres ignoradas
habituales por suite), prueba GPU repetida sobre el árbol final y compilación
metal-only de zakuro-gpu sin Vulkan correcta. H4–H7 y M2.1 siguen abiertos.

Cierre H2/H3: serie 0041/0042 y lock verificados localmente y desde clones
nuevos; 49 enlaces locales válidos, catálogo completo de 43 parches y diff
sin errores de espacios. Publicación en dev; no integración en master.
