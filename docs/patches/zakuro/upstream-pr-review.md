# Candidatos a PR upstream — revisión de dependencias, base y pruebas

> Estado: **revisión, no PRs**. Ningún PR está abierto contra `fearkov/zakuro`;
> esta nota es el basework que falta antes de proponerlos. Base de la serie:
> upstream `80d78be` (pinneado en `vendors.lock.json`, árbol parcheado
> `87490d75…`). Verificado con `git apply --check` contra un worktree limpio
> de ese commit (2026-11-01).

## Veredicto por candidato

| Parche | Aplica solo sobre upstream | Dependencia | Prueba que lo respalda | Riesgo/pendiente para PR |
|---|---|---|---|---|
| **0001** darwin: opt-in a portability (MoltenVK…) | ✅ limpio (una línea con trailing whitespace a pulir) | ninguna | compila+smoke vulkan (native_smoke 5/5) | el opt-in tiene que quedar condicionado a macOS only del build; reformat línea 59 |
| **0002** get_physical_device_properties2 | ❌ solo | **necesita 0001 debajo** (toca vulkan.rs/hardware.rs mutados por 0001) | mismo smoke + el kpi de G3 | va en el mismo PR que 0001 (aplica sobre él verificado) |
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

## Orden propuesto (cuando se aprueben)

1. **PR 1**: 0001 + 0002 en un PR (la instancia portability de macOS), con el
   trailing whitespace de 0001 corregido y una nota de que la prueba es el
   smoke sintético de `ctr-native` (el upstream no reparte nuestra suite).
2. **PR 2**: 0005 solo.
3. **El resto** (0003+): consultar por hilo antes que PR — dependen de
   decisiones de diseño del port (kpi, segunda ventana, Metal).
