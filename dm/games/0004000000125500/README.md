# The Legend of Zelda: Majora's Mask 3D (USA) · `0004000000125500` · CTR-P-AJRE

Segundo juego del port (2026-10-31), vía copia **USA Decrypted** por decisión del
plan (la tarjeta EUR `125600` recibida viene cifrada; la USA descifrada pasa
las flags `NoCrypto`/`FixedKey` del builder — cero llaves).

- Dump que corre: "The Legend of Zelda Majora's Mask 3D (USA) Decrypted.3ds"
  (663,506,944 bytes; la copia cifrada EUR y su MD5/SHA quedán documentados
  como procedencia del recibido: md5 `4a491c638cf770278a392ebd677f6bef`,
  sha256 `8f9a53b78948f3fd13bf8905663e5ffea4bcc8ed7edf325c1f1a8231a5759cf0`).
- Pin de la copia que corre: `verified_md5=070077e99b3ab90cbfc8c2e6161c17d7`
  (calculado localmente; la auto-verificación de superblocks compete al
  descifrado del pipeline y `3dsrecomp verify` chequea cada build de AOT).
- AOT: `3dsrecomp build` → **248/248** funciones (144.7 s), dylib de 110 MB
  instalado en `~/Library/Application Support/3dsrecomp/0004000000125500.dylib`.
- Idioma: `--language es` (la edición USA trae español).
- Sandbox propia de esta app, separada de la de ALBW.
- **Validación 2026-10-31: criterios del PLAN_MAJORAS_MASK_3D.md completos** —
  sesión 289 s (avg 59.6 fps, 5 underruns con el pin de G2), español, menús
  sin fallo ImageIO y **guardado persistente** (guardar→cerrar→reabrir→recuperar).
- Dependencia del launcher: la ROM que corre es la copia descifrada de
  `0004000000125500_build/decrypted/…Decrypted.decrypted.3ds` (borrar esa
  carpeta rompe la app; el dump original raíz queda intacto).
