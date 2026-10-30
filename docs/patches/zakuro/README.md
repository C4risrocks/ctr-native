# Parches del fork `vendors/zakuro`

`vendors/` no entra a git (grande y ajeno). Cada cambio local al fork se
commitea en el clone y se exporta aquí con `format-patch`, para reproducir el
binario en un máquina fresca y para el PR de cortesía upstream:

    git clone https://github.com/fearkov/zakuro vendors/zakuro
    git -C vendors/zakuro am ../../docs/patches/zakuro/*.patch
    cargo build --release

| Parche | Qué hace | Estado |
|---|---|---|
| `0001-gpu-get-physical-device-properties2…` | props2 corre junto a portability: `VK_KHR_portability_subset` lo exige por spec el día que se active; prop2 es core 1.1, gratis en macOS | listo para PR upstream |
| `0002-gpu-a-session-kpi…` | KPI de sesión: buckets de shading por draw (gpu/cpu) en `rasterize`, los underruns del queue ditos, la sesión lanza una línea `session kpi` al salir y headless imprime los buckets | local (insumo F8) |
