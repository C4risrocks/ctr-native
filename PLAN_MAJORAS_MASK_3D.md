# Majora’s Mask 3D: compilación y prueba jugable en macOS

## Estado (2026-10-31) — USA validada; objetivo EUR pendiente

La app existente corresponde a la edición USA `0004000000125500`
(CTR-P-AJRE), distinta de la EUR `0004000000125600` solicitada originalmente.
La validación USA no completa el objetivo EUR ni supone aceptar una sustitución
de edición. Para completar EUR falta una copia descifrada de esa misma edición,
su perfil, su biblioteca AOT y sus pruebas de aceptación.

La fuente USA tiene la partición principal NoCrypto/FixedKey y una secundaria
cifrada. Su copia de trabajo se preparó con boot9 local y tiene ambas particiones
NoCrypto; las claves no se incorporan al paquete ni al repositorio.

La validación registrada para USA incluye español, ambas pantallas, controles,
audio, redimensionado/fullscreen, menús sin fallo ImageIO, guardado persistente
confirmado por el jugador y reuso del builder con sandbox intacta. Los 63 tests,
Ruff y Pyright pasan; la reproducción del fork requiere el árbol actualizado
en vendors.lock.json.

- Sesión real medida (kpi automático de G5): 289 s, **avg 59.6 fps**,
  min 6.9 (cargas), **5 underruns (1.04/min)** con el pin de audio de G2,
  vértices CPU (como G1 dicta en Apple Silicon).
- Perfil: `dm/games/0004000000125500/profile.tsv` con el pin
  `verified_md5=070077e99b3ab90cbfc8c2e6161c17d7` (copia que corre), notas en
  su `README.md` (incluye la procedencia del recibido EUR cifrado:
  md5 `4a491c638cf770278a392ebd677f6bef`, sha256 `8f9a53b7…`).
- AOT: 248/248 unidades compiladas (144.7 s), `~/Library/Application Support/
  3dsrecomp/0004000000125500.dylib`.
- Empaquetado: `The Legend of Zelda - Majoras Mask 3D.app` (humo headless
  verde, firma ad-hoc verificada, sandbox hermana propia); el launcher apunta
  a la copia descifrada en `0004000000125500_build/decrypted/`.
- Guardado USA: confirmado por el jugador (guardar → cerrar → reabrir → recuperar).
- Verificación diferencial AOT: no realizada; el binario instalado no incluye
  `--features verify`. El arranque headless no sustituye esa comprobación.

## Objetivo y requisito previo

Generar `The Legend of Zelda - Majoras Mask 3D.app`, en español, y validar una sesión con controles, audio y persistencia de partida.

La inspección del archivo recibido identifica:

- Título: `0004000000125600`; producto: `CTR-P-AJRP`.
- Tamaño: 708.091.904 bytes.
- Cabeceras de cifrado activas.
- Sin perfil propio ni biblioteca AOT instalada.

**Requisito pendiente:** disponer de la ruta de una copia descifrada de esta misma edición, conforme a la opción elegida. Esa ruta será `ROM_DESCIFRADA` en los comandos siguientes. El archivo recibido se conservará intacto.

## Preparación y recompilación

1. Validar que `ROM_DESCIFRADA` contiene el mismo título y que todas sus particiones son legibles sin claves. Leer SMDH y ExeFS y calcular MD5 y SHA-256.
2. Añadir el perfil de `0004000000125600`, fijando el MD5 de la copia descifrada como referencia local de integridad. Documentar su procedencia y distinguirla de una verificación externa.
3. Reutilizar los binarios ARM64 existentes de Zakuro y 3dsrecomp, comprobando las revisiones fijadas. Revisar espacio disponible antes de compilar; al preparar el plan quedaban aproximadamente 8 GiB.
4. Ejecutar desde la raíz del proyecto:

   ```sh
   vendors/3dsrecomp/target/release/3dsrecomp analyze "$ROM_DESCIFRADA"
   vendors/3dsrecomp/target/release/3dsrecomp build "$ROM_DESCIFRADA"
   ```

5. Comprobar que se instala `0004000000125600.dylib`. No reutilizar bibliotecas, indicios ni parches específicos de la edición `0004000000125500`.

La ejecución seguirá el mismo modelo que A Link Between Worlds: Zakuro y la biblioteca AOT ejecutan código ARM64 nativo en Apple Silicon, sin Rosetta. Las funciones que AOT no consiga recompilar seguirán usando el intérprete de Zakuro.

## Empaquetado

Usar el builder existente, con compilación AOT automática en la etapa 5:

```sh
python3 scripts/build_app_from_3ds.py "$ROM_DESCIFRADA" \
  --app-name "The Legend of Zelda - Majoras Mask 3D" \
  --language es --scale 3 \
  --output "/Users/christiandejmorenomarin/ctr-native" \
  --progress lines --launch
```

Verificar firma, icono, biblioteca incluida y rutas del launcher. Mantener las
correciones de ImageIO ya en master (`c346dbd`: el launcher ya no ensombrece
los codecs del sistema; y el re-encode del icono vía `sips` en el stage de
icono).

La app dependerá de la ROM externa en su ubicación definitiva. Guardados y configuración pertenecerán exclusivamente al sandbox de Majora’s Mask.

## Pruebas y criterios de aceptación

- Ejecutar la suite Python, Ruff, Pyright y los cinco escenarios gráficos sintéticos existentes.
- Exigir que el arranque automático complete los 120 fotogramas sin errores fatales.
- Comprobar visualmente el idioma español, ambas pantallas, controles, audio, redimensionado y pantalla completa.
- Abrir los menús nativos repetidamente para comprobar que no reaparece el fallo de ImageIO.
- Avanzar hasta poder guardar dentro del juego; cerrar, reabrir y recuperar esa partida. Un savestate no sustituirá esta prueba.
- Repetir el builder y confirmar reutilización del paquete y conservación del guardado.

Documentar resultados, rendimiento observado y fallos reproducibles en las notas del título. Mantener la velocidad original, sin activar parches de 60 FPS. No declarar el juego validado mientras falte la prueba interactiva de audio y guardado.

## Actualización 2026-11-01

Los comandos manuales AOT y rutas de instalación anteriores documentan el
bring-up histórico. El builder actual obtiene AOT automáticamente y empaqueta
la biblioteca de caché validada. Los cuatro P1 están cerrados; los cinco P2
figuran en [el plan del pipeline](PLAN_REFACTOR_PIPELINE.md). EUR sigue pendiente.
