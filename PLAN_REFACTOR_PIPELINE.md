# Refactor del pipeline común de ctr-native

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
