# Refactor del pipeline común de ctr-native

## Estado — implementación inicial realizada; auditoría con hallazgos abiertos

La implementación inicial se integró desde `refactor/pipeline` (`7cb83b0`,
`9a029b7`). La auditoría posterior identificó nueve hallazgos: cuatro P1
corregidos en `ca51d6a` y `725bb82`. En `dev`, P2-6/P2-7/P2-8 están
corregidos; P2-5 corregido en S3; P2-9 sigue pendiente.
La tabla de auditoría al final es la referencia de sus estados.

Validación posterior en `dev`: 77 pruebas Python (P2-9 sigue omitiendo una), Ruff,
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
| 9. Integración real 3dsrecomp omitida | P2 | Pendiente |

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
- Pendientes de esta ampliación: S4 integración real
  obligatoria, conexión completa M1.1, batches/presentación directa y M2.1.
- Se conserva Vulkan por defecto. El cierre de M1.1 exige paridad y >=85%
  del throughput Vulkan, con benchmark controlado y validación de usuario.

Validación S1/S2: suites nativas default y Metal correctas; bootstrap local
y reconstrucción desde clones nuevos correctos. S4/M1.1/M2.1 no están cerrados.

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
P2-9, HardwareMetal y overlay siguen pendientes.

Validación S3: 79 pruebas Python ejecutadas (una omitida por P2-9),
Ruff y Pyright correctos; diff sin errores de espacios.
