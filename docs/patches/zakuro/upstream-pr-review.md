# Candidatos a PR upstream — revisión de dependencias, base y pruebas

> Estado (2026-11-01, con el PR upstream #26 en escena): **un PR abierto de
> esta serie — #27 cecd, base `80d78be`, un archivo, 31 líneas** — y los
> demais a la espera de su destino. Base de la serie: upstream `80d78be`
> (lock + árbol parcheado `87490d75…`), verificado con `git apply --check`
> contra un worktree limpio de ese commit (2026-11-01).

## Veredicto por candidato

**Lo que cambió con PR upstream #26** ("Run Vulkan on macOS through
MoltenVK", +90/−25 sobre 7 archivos, open, sin revisión aún): su
`instance.rs` unifica loader-rutas de Homebrew, portability enumeration y
subset en device, más `README`/`--help`/`CI macos-latest`. Cubre el PR-1
planeado: **0001 y 0002 quedan postergados — superseded si #26 se mergea**.
Cuando eso ocurra: rebase del fork al nuevo base, `vendors.lock.json`
nuevo y bootstrap re-verificado. Nota técnica que #26 puede aprovechar:
nuestro runtime ya neutraliza el loader-probing en contexto de bundle
(`DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib`), incluso sin Homebrew.

| Parche | Aplica solo sobre upstream | Dependencia | Prueba que lo respalda | Riesgo/pendiente para PR |
|---|---|---|---|---|
| **0001** darwin: opt-in a portability (MoltenVK…) | ✅ limpio (una línea con trailing whitespace a pulir) | ninguna | compila+smoke vulkan (native_smoke 5/5) | **postergado**: #26 (open) cubre y extiende el mismo terreno — no duplicar |
| **0002** get_physical_device_properties2 | ❌ solo | necesita 0001 debajo | mismo smoke | **postergado** con 0001, misma razón |
| **0003** session kpi | ❌ solo | rides 0001/0002 | el propio kpi imprimido en las sesiones | la métrica es formato-local del port; valor upstream discutible — evaluar si upstream lo quiere |
| **0005** cecd OpenAndRead offline | ✅ limpio | ninguna (services/cecd aislado) | el test de sesión del jugador + suite core | candidato PR más limpio en alcance; re-check del título del commit para upstream |
| **0012** shared-presentation + overrides | ❌ solo | cadena 0004→0011 | native_smoke shared-window-cycle | PR apilado grande; postergar |
| **0016** MSL (M0.5) | ❌ solo | necesita 0012/0014/0015 | test 189/189 del device | infra Metal opcional upstream: consultar antes de abrir; postergar |
| 0018–0020 | ❌ | 0014→0019 | smoke 7/7 | el backend Metal completo: período de consulta primero, no PR directo |

## Cómo reproducir la verificación

```
git -C vendors/zakuro worktree add /tmp/zakuro-base 80d78be
cd /tmp/zakuro-base && git apply --check <parche>
# pila: aplicar 0001 y luego --check 0002 sobre él
```

## Orden propuesto — estado

1. ~~PR 1: 0001+0002~~ → **postergado por PR upstream #26** (mismo objetivo,
   más completo para upstream). Reabrir solo si #26 muere.
2. **✅ PR 2: 0005 abierto como [#27](https://github.com/fearkov/zakuro/pull/27)**
   (branch `C4risrocks:pr-cecd-openandread`, base `80d78be`, un archivo,
   verificación con `git apply --check` previa).
3. **El resto** (0003+): consultar por hilo antes que PR — dependen de
   decisiones de diseño del port (kpi, segunda ventana, Metal). El hilo del
   PR #26 (open) confirma que la comunidad de upstream ya recibe parches de
   macOS sin respuesta censurada; la postergación no gana nada por su lado.
