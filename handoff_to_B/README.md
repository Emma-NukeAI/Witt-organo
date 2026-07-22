# `handoff_to_B/` — canal A→B (pull)

El simétrico del `outbox/` de B. **B deja requests en su `outbox/`; A deja handbacks aquí.**
B **jala** (lee read-only); A **nunca** escribe el repo de B (`../conciencia-universal`), igual que
B nunca escribe la DI. El aislamiento es estructural (ver `../conciencia-universal/docs/A_B_CONTRACT.md`).

## Qué contiene

| archivo | qué es |
|---|---|
| `G8_rn3_generation_commission_20260721.json` | **Comisión de generación.** A aterrizó ZF-G8 (scope-gate GATE 1 aprobado + datos ZESTA medidos + mecanismo verificado + topología BNGL). Le pide a B que **genere y ajuste** el modelo de reacción-difusión Nodal/BMP. |

## Cómo consume B esta comisión (A1 proposal-only)

1. **Resuelve los 15 marcadores** vía el MCP read-only `data-inamovible` (`resolve_identifier`) — todos
   resuelven en la DI (store `2026-07-21.1`, 93 records). Invariante #6: nunca IDs de memoria.
2. **Lee el target de ajuste medido** en la ruta read-only de A:
   `analysis/outputs/G8_zesta_nodal_bmp_trajectories_20260721.json` (trayectorias ZESTA, dato medido).
3. **Genera** el `.bngl` ajustado + tabla de constantes + mapeo gradiente→identidad-de-segmento, con el
   prior estructural **D(Lefty) > D(Nodal)** (Müller 2012, PMID 22499809 — verificado por A, §7.9).
4. **Devuelve un `Proposal`** en tu `proposals/` (lado B) con observable + `candidate_falsifier` +
   confidence (claim-like, **no** calibración hasta que A observe outcome, invariante #3).

## Cómo re-entra a la DI (camino de promoción, §4 del contrato)

`B genera Proposal → A scope-gate + selección humana → si se selecciona: A GATE 2 →
add_dataset → revisión humana → approve_dataset → ingest` como **CORPUS-2026-0004 (primer record RN3)**.

B **nunca** escribe la DI; A **nunca** escribe el repo de B. Los dos gates humanos son irreducibles.
