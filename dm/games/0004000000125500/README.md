# The Legend of Zelda: Majora's Mask 3D (USA) · `0004000000125500` · CTR-P-AJRE

Segundo juego probado (2026-10-31), vía copia **USA Decrypted**. Esta edición
es distinta de la EUR `125600` solicitada en el plan original; su validación no
completa aquel objetivo. La fuente USA tiene la partición principal
NoCrypto/FixedKey y una secundaria cifrada, descifrada con boot9 local en una
copia de trabajo. El launcher utiliza esa copia; no incluye claves.

- Dump que corre: "The Legend of Zelda Majora's Mask 3D (USA) Decrypted.3ds"
  (663,506,944 bytes; la copia cifrada EUR y su MD5/SHA quedán documentados
  como procedencia del recibido: md5 `4a491c638cf770278a392ebd677f6bef`,
  sha256 `8f9a53b78948f3fd13bf8905663e5ffea4bcc8ed7edf325c1f1a8231a5759cf0`).
- Pin de la copia que corre: `verified_md5=070077e99b3ab90cbfc8c2e6161c17d7`
  (calculado localmente como referencia de integridad, sin verificación externa).
  El descifrado verifica los superblocks. No se realizó verificación diferencial
  AOT: el binario instalado no incluye `--features verify`; `build` no ejecuta
  automáticamente `3dsrecomp verify`.
- AOT: `3dsrecomp build` → **248/248** unidades compiladas (144.7 s), dylib de 110 MB
  instalado en `~/Library/Application Support/3dsrecomp/0004000000125500.dylib`.
- Idioma: `--language es` (la edición USA trae español).
- Sandbox propia de esta app, separada de la de ALBW.
- **Validación USA 2026-10-31** —
  sesión 289 s (avg 59.6 fps, 5 underruns con el pin de G2), español, menús
  sin fallo ImageIO y **guardado persistente** (guardar→cerrar→reabrir→recuperar).
- Dependencia del launcher: la ROM que corre es la copia descifrada de
  `0004000000125500_build/decrypted/…Decrypted.decrypted.3ds` (borrar esa
  carpeta rompe la app; el dump original raíz queda intacto).

El builder actual obtiene AOT automáticamente desde una caché validada por
título; las rutas globales anteriores documentan solo el bring-up histórico.
