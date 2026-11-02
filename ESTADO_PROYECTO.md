# Estado actual de ctr-native

Base técnica revisada: `fd6b6f1`, rama `dev`, H4 implementado. Esta actualización
es documental; los resultados siguientes corresponden a las revisiones técnicas
indicadas, no a una nueva sesión de juego ni al resultado remoto de CI.

| Área | Estado real |
|---|---|
| Pipeline común | Ocho etapas; AOT automática, caché v2 y paquete validado |
| Auditoría | Cuatro P1 y cinco P2 corregidos en dev |
| Ejecución disponible | AOT con kernel/servicios HLE y raster Vulkan/MoltenVK por defecto |
| Metal presentación | Experimental; sincronización y entrega no bloqueante corregidas |
| HardwareMetal | H1–H4 implementados; despacho del juego H5 pendiente |
| H6 / H7 | Batching/presentación directa y paridad/rendimiento pendientes |
| M2.1 | Overlay egui sobre Metal pendiente |
| Reproducibilidad | Serie hasta 0043, incluyendo 0018a, y árboles fijados en vendors.lock.json |
| Majora’s Mask | USA validada en sesiones anteriores; edición EUR pendiente |
| QA física | F7 con dos monitores reales y mediciones de sesión pendientes de registro |
| Higiene | Revisiones manuales realizadas; automatización de higiene en CI pendiente |
| Upstream | Revisión y publicación de la serie según el registro de PRs; sin nuevas publicaciones en esta entrega |

## Evidencia registrada

- S4: 80 pruebas Python sin omisiones con integración AOT real obligatoria;
  Ruff y Pyright correctos en aquella entrega.
- H4: 484 pruebas Rust por defecto y 503 con Metal correctas, con tres ignoradas
  habituales por suite; compilación Metal sin Vulkan correcta.
- H4: reconstrucción de ambos vendors desde clones nuevos y verificación local
  del lock correctas. Las pruebas GPU usaron exclusivamente datos sintéticos.
- CI ejecuta la suite nativa default, compila la suite Metal y dispone de un
  job macOS para la integración AOT real. El estado de una corrida remota debe
  consultarse en GitHub; las pruebas locales no lo certifican.

## Límites vigentes

H4 conserva memoria guest canónica mediante write-through síncrono y renderiza
superficies a 1x/2x/3x con readback al pixel nativo. No activa el raster en un
juego ni acredita los 60 FPS. Los modos no soportados se rechazan explícitamente;
H5 conectará el fallback. Un fallo GPU exige recrear el backend.

La huella AOT v2 supone instalaciones SDK inmutables: registra sus metadatos,
no calcula el hash de todos sus headers y bibliotecas. Las pruebas sintéticas
no certifican compatibilidad de otra región, audio ni QA física.

## Documentos de continuidad

- [Plan restante en la raíz](PLAN_REFACTOR_PIPELINE.md#plan-restante-después-de-h4).
- [Walkthrough completo](WALKTHROUGH.md).
- [Detalle técnico Metal](docs/plan-metal.md).
- [Desarrollo y comandos](docs/development.md).
- [Plan Majora’s Mask](PLAN_MAJORAS_MASK_3D.md).
- [Revisión upstream](docs/patches/zakuro/upstream-pr-review.md).
