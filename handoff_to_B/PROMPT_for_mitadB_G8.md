# PROMPT → MITAD_B (ZF-G8 · generar el modelo RN3 Nodal/BMP)

> **Qué es esto.** El simétrico del prompt con que B le pidió a A validar la DI. A ya hizo su mitad de
> ZF-G8 (scope gate + datos medidos + mecanismo verificado) y dejó una **comisión de generación** en su
> canal de handback `handoff_to_B/`. Pega el bloque de abajo en una sesión abierta en `conciencia-universal`.

---

## PROMPT PARA PEGAR EN UNA SESIÓN ABIERTA EN `conciencia-universal` (MITAD_B)

> Eres **MITAD_B** (generación · Conciencia Universal). MITAD_A dejó una **comisión de generación** en el
> repo hermano, en su canal de handback: `../witt-organogenesis/handoff_to_B/G8_rn3_generation_commission_20260721.json`
> (+ `README.md`). Léela (**read-only**; nunca escribas el repo de A). Es la mitad-A ya aterrizada de la
> pregunta de crecimiento **ZF-G8** (`nodal-bmp-kinetics-from-zesta`): A aprobó el scope gate (GATE 1),
> extrajo las trayectorias **MEDIDAS** de Nodal/BMP desde ZESTA (3/5/10 hpf), y verificó el mecanismo
> (Müller 2012, **PMID 22499809**: *differential diffusivity*, con clearance similar → **D_Lefty > D_Nodal**).
> Te toca **generar y ajustar** el modelo de reacción-difusión RN3. Haz **solo trabajo de B (A1
> proposal-only)**: no escribas la DI, no mintees IDs.
>
> **1 · Aterriza contra la DI (read-only).** Resuelve los **15 marcadores** de la comisión vía el MCP
> `data-inamovible` (`resolve_identifier`) — nunca IDs de memoria (invariante #6). Lee el target de ajuste
> medido en la ruta read-only de A:
> `../witt-organogenesis/analysis/outputs/G8_zesta_nodal_bmp_trajectories_20260721.json`.
>
> **2 · Genera + ajusta.** Instancia la **topología BNGL** de la comisión (7 reglas: `Nodal+Oep→pSmad2`,
> feedback `pSmad2→Lefty`, inhibición competitiva `Lefty+Oep`, `BMP→pSmad5`, secuestro `Chordin+BMP`) y
> **ajusta D/k a los gradientes ZESTA medidos**, con el prior estructural **D(Lefty) > D(Nodal)**. Produce:
> (a) el `.bngl` ajustado (RN3), (b) la tabla de constantes cinéticas (fit a ZESTA), (c) el mapeo
> `gradiente → identidad-de-segmento` (`.json`).
>
> **3 · Demota a `Proposal`** (§5 del `A_B_CONTRACT`). Cada salida lleva **observable** (invariante #1),
> **candidate_falsifier** (una perturbación de Lefty NO mueve la frontera del dominio Nodal como predice el
> modelo ajustado), y **confidence** (claim-like — **no** es calibración hasta que A observe un outcome,
> invariante #3). Empaca todo como un `Proposal` en tu `proposals/`.
>
> **4 · Devuelve por el camino de promoción (§4).** Tu `Proposal` re-entra a A por su **scope-gate +
> selección humana** → si se selecciona, A lo **GATE-2ea** e ingiere como **CORPUS-2026-0004** (primer
> record RN3). Tú **nunca** escribes la DI; A **nunca** escribe tu repo; los dos gates humanos son
> irreducibles.
>
> Entrega el `Proposal` + una nota breve: qué generaste, contra qué lo ajustaste, y el falsifier. No toques
> `../witt-organogenesis` (read-only para ti).

---

## Invariantes que este canal respeta
- B genera **candidatos** (`Proposal`), A1 proposal-only; A dispone (scope gate + 2 gates humanos).
- Todo ID pasa por el `resolve_identifier` de A (inv #6). B nunca mintea IDs ni escribe la DI.
- Nada es calibración hasta que A observe un outcome (inv #3). El `.bngl` es candidato, no verdad (inv #7).
- El modelo re-entra a la DI solo por el camino human-gated de A (`add_dataset → revisión → approve → ingest`).
