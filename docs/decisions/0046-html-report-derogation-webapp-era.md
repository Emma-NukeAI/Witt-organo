# ADR-0046 — Derogación CON ALCANCE del reporte HTML obligatorio (§5/§7): las corridas de la era webapp no emiten HTML; su rastro es el registro congelado, y los reportes históricos se indexan en la webapp

- **Status:** Accepted — decisión del fundador del 2026-08-04 (handoff webapp, `witt-ui-lab/05-backend/`), **alcance definido por Emmanuel el 2026-08-09 en sesión**: *"son sólo corridas de la era de la webapp; el resto se pueden quedar en master como ejemplos, pero sí me gustaría que también puedan ser consultables — agregarlas o indexarlas en la webapp"*.
- **Relates:** ADR-0007 (la regla HTML-at-conclusion v2.5), `references/html-report-contract.md`, decisión 1 del handoff webapp + `witt-ui-lab/01-mapa/registro-congelado.md` (una fuente, tres renders), ADR-0043/0044/0045 (correcciones pre-UI de la misma línea).
- **Affects:** CLAUDE.md §5 y §7 (notas de alcance, esta sesión) · el plan de bloques del backend webapp (NUEVO requisito: índice de artefactos históricos). No toca código.

## Context

v2.5/ADR-0007 hizo obligatorio un HTML auto-contenido en `reports/` al concluir cualquier salida analítica: *"el HTML ES el rastro de auditoría"*. La decisión webapp del 2026-08-04 reemplaza ese canal para las corridas del equipo: la respuesta vive en una **URL de la UI** renderizada desde un **registro congelado** (JSON, fuente única de tres renders: URL viva, PDF generado en servidor, entrada de bitácora M6). Mantener ambos canales duplicaría el rastro de auditoría — exactamente el anti-patrón "4 vistas paralelas de la misma evidencia" que el composite-audit del 2026-05-14 marcó como violación de *prueba pequeño antes de armar bien*.

## Decision

1. **Corridas de la era webapp** (las ejecutadas a través del pipeline backend/webapp cuando exista) **NO emiten HTML en `reports/`**. Su rastro de auditoría es el registro congelado + la URL de la UI + el **PDF generado en servidor** como único canal autorizado de exportación (nunca `window.print()` — el derivado fuera de pantalla sale limpio, y eso es la fuga que el producto existe para cerrar).
2. **Los reportes HTML históricos de `reports/` se quedan en master como ejemplos** y registro válido de su era — no se migran, no se borran, no se re-generan (versión-preservación). **NUEVO requisito de backend:** la webapp los **indexa y los hace consultables** (un índice read-only de artefactos históricos: reportes HTML + los ~30 runs de `evaluation/runs/`, estos últimos marcados como no-instrumentados donde les falte `decision_state`). Se incorpora al plan de bloques (bloque 2 o 4).
3. **Las salidas analíticas de sesiones de agente EN el repo (fuera de la webapp) CONSERVAN la regla §5/§7** mientras la webapp no sea el cliente. Excepción puntual ya ejercida: la línea de trabajo de backend pre-UI (esta y la sesión 2026-08-09) entrega código + ADRs + smokes deterministas, no HTML, por instrucción directa del fundador.
4. **La regla hermana de §7 (viz TYPE C obligatoria para conclusiones simulation-backed) se deroga en su MEDIO, no en su PRINCIPIO**, para corridas webapp: una conclusión respaldada por simulación debe renderizarse **interactiva en la UI** desde el registro congelado (módulo de viz de la UI — scrubable/explorable), nunca como imagen estática. Para sesiones de repo la regla sigue tal cual (TYPE C en el HTML).

## Consequences

- CLAUDE.md §5 y §7 ganan notas de alcance que apuntan a este ADR (mismo commit); `html-report-contract.md` **no se deroga** — sigue gobernando los reportes de sesiones de repo y sirve de referencia para las reglas de render de la UI.
- El registro congelado se convierte en la fuente del rastro de auditoría para corridas webapp — lo que hace más urgente la decisión pendiente #5 del plan (quién persiste ese registro: backend recomendado vs. webapp).
- El índice de históricos es alcance nuevo del backend (barato: listado read-only + metadatos; sin re-procesar los artefactos).
- La regla del §11 (visual-offer reflex) queda absorbida por la UI para corridas webapp (la UI *es* el artefacto visual); sin cambio para sesiones de repo.
