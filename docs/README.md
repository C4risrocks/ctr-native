# Documentación de ctr-native — índice

Guía de quién lee qué. El código fuente de la verdad es el repo; estos documentos
lo cuentan en distintos niveles.

## Para el jugador (empezar aquí)

- **[walkthrough.md](walkthrough.md)** — la guía end-to-end: de tu dump al doble
  clic: build, controles, atajos (F1/F9/F10/F11/Esc), modo dual monitor (F7),
  diagnóstico y glosario.
- **[playing.md](playing.md)** — controles y troubleshooting clásico del host
  (sandbox, shader cache, modo dual monitor, bug reports sin llaves).

## Diagramas históricos (HTML explorables)

Estos HTML están anclados a la revisión indicada dentro de cada documento.
El flujo actualizado está en [development.md](development.md); las imágenes
previas no certifican la sincronización ni publicación del código actual.

- [pipeline-build.dataflow.html](diagrams/pipeline-build.dataflow.html) —
  *De tu dump a la app*: los stages del builder (discover→identify→verify→pack),
  la llave de reuso y qué jamás entra a git.
- [runtime-zakuro.architecture.html](diagrams/runtime-zakuro.architecture.html) —
  *El runtime de una partida*: CPU AOT + kernel HLE + raster Vulkan/portability,
  las dos ventanas (F7) y la sandbox de datos.
- [f7-ventana-segunda.workflow.html](diagrams/f7-ventana-segunda.workflow.html) —
  *El modo segunda ventana*: cómo se pide (menú de Esc / Settings / CLI), qué
  cambia en vivo, y la línea `session kpi` al cerrar.

## Planes

- **[plan-metal.md](plan-metal.md)** — el plan del backend Metal (M0..M3) y
  el progreso de presentación Metal, raster hardware pendiente y límites actuales.

## Para el que mantiene el repo

- **[audit-implementation.md](audit-implementation.md)** — cierre de hallazgos,
  pruebas ejecutadas y validaciones físicas pendientes.

- **[roadmap.md](roadmap.md)** — el plan heredado F7+F8 con decisiones, fases,
  KPIs y su estado histórico, separado del panorama actual.
- **[zakuro-macos.md](zakuro-macos.md)** — el port en sí: resultados medidos
  (KPI 0–F6, 3 corridas de G5), resueltas y pendientes del delta darwin.
- **[metal-direct.md](metal-direct.md)** — informe go/no-go (F8-G4): HOLD con
  datos, disparadores para reabrir.
- **[development.md](development.md)** — los stages del pipeline Python y el
  boceto del goal nativo.
- **[patches/zakuro/](patches/zakuro/README.md)** — la serie de parches del fork
  `vendors/zakuro` exportados (`git am`), con estado por parche y qué está listo
  para PR upstream.

## Reglas de oro (recordar a los agentes)

- Nada del juego ni de llaves entra al repo (`.gitignore` los excluye; revisar también el diff antes de publicar).
- La sandbox `<app>.ctr-native/` es usuario: se crea, nunca se actualiza.
- Cambios de parsers con test sintético; lista de stages en development.md.
- Los diagramas HTML arriba son el destino de `/archify` (candidates en
  `.archify/`, fuera de git).

## Estado y planes vigentes

- [Pipeline y auditoría](../PLAN_REFACTOR_PIPELINE.md): cuatro P1 cerrados,
  P2-6/P2-7/P2-8 corregidos en `dev`; P2-5 corregido (S3); P2-9 pendiente.
- [Majora’s Mask](../PLAN_MAJORAS_MASK_3D.md): USA validada, EUR pendiente.
- [Desarrollo](development.md): ocho etapas, caché AOT validada y comandos actuales.
- [Metal](plan-metal.md): presentación experimental con raster software; sincronización y
  entrega no bloqueante corregidas en `dev`; HardwareMetal y overlay pendientes.
