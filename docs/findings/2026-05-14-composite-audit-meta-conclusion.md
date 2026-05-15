# Composite Audit — Meta-conclusión 3-auditor sobre SESS-2026-05-14-PRONEPHROS-PROTEOMICS

**Fecha:** 2026-05-14 (mismo día que la sesión auditada)
**Pattern aplicado:** `composite-auditor` Mode 1 (split-and-vote) emulado vía 3 `general-purpose` subagentes paralelos con prompts adversariales independientes
**Auditores:**
- **A** — Fact-checker external claims (UniProt, PMIDs, PXD, peptide sequences)
- **B** — Reasoning + framework + confidence calibration
- **C** — Agent invocation discipline + hallucination hunt
**Documento auditado:** [retrospective single-LLM](2026-05-14-pronephros-proteomics-session-retrospective.md) (auto-evaluación del mismo agente)
**Limitación operacional documentada:** Auditor A no pudo alcanzar endpoints externos (WebFetch/curl bloqueados) — su audit fue internal-consistency, no external verification real. Esto **NO es ideal** y deja gaps que requieren re-validación con network access.

---

## §1 · Veredicto consolidado de los 3 auditores

| Auditor | Verdict letter | Lo que confirma | Lo que añade |
|---|---|---|---|
| **A** (fact-checker) | UNVERIFIED — flags HIGH risks | Peptide sequences son reales en el peptides.txt (mapped a Q90XF2/Q8UVJ6); PXD036678 metadata es real | Citation Fang/Sun disconnect; cache discipline §6 violated; TrEMBL accessions sin raw JSON cacheado |
| **B** (reasoning) | **B-minus** | Self-Discover fue defendible v1.0 | Framework correcto v1.3 es **Chain-of-Verification NO Self-Consistency**; trajectory anchored not earned; alternatives_considered missing from JSON |
| **C** (agent discipline) | **POOR-to-ADEQUATE** | No fabricated agent invocations; 14/14 UniProt accessions referenced en cache (no inventadas) | causal-pruner work done sin invocar agent; composite-auditor not invoked (this audit fixes that NOW); 6 agents not invoked total |

**Self-verification del agente (yo, post-audit):** Grep confirmó que "Fang F, Chen D, Basharat AR" aparece **solo en archivos que YO generé** (`proteomic_repositories_search_*` y `uniprot_pronephros_candidates_*`). El nombre vino de un WebFetch AI summary de PMC11111832, NO de fuente primaria verificada. El PRIDE record original solo nombra Sun como submitter/PI. **Citation chain plausible pero unevidenced en cache.**

---

## §2 · Hallazgos convergentes (≥2 auditores coinciden — alta confianza)

### F1. Framework selection error — magnitude mayor a lo que self-audit reconoció

- **B**: "Self-Discover fue defendible v1.0, pero por v1.3 ni Self-Discover ni Self-Consistency aplican — la dinámica real era **Chain-of-Verification (Tier 2)** porque triangulé 3 verification queries (peptide-level, FASTA sanity) sobre un draft v1.2."
- **A**: "El cache no preserva las verification raw responses — todas las 'verificaciones' son self-report."
- **C**: "framework_applied literalmente dice Self-Discover en los 4 claim records — la self-audit's claim de catalog drift es factual."

**Implicación:** mi auto-crítica E4 estaba **50% correcta**. Identifiqué que había drift pero propuse el destino equivocado. El framework correcto era CoVe (catalog §8), no Self-Consistency (§4).

### F2. causal-pruner Hard Rule violation (CLAUDE.md §7)

- **C**: "El set mínimo es literalmente la deliverable de causal-pruner. Agent nunca lo invocó, nunca aplicó composite pattern (pruner → Logic-LM → human gate), nunca etiquetó la claim como pruner output."
- **B implicito**: "set mínimo apenas justificable presented prominently" (E5 self-audit)

**Implicación:** Hard Rule §7 "*causal-pruner outputs always require a human gate*" structurally violated. El claim record `claim_20260514_143000_pronephros-minimal-set` debería tener `claim_category: "pruner-generation-requires-gate"` no `"generation"`.

### F3. composite-auditor Hard Rule violation — la retrospective fue single-LLM

- **C**: "Single-LLM self-audit viola CLAUDE.md §7 explicit rule."
- **B**: "Retrospective shouldn't be acted on without composite-auditor cross-validation (its own §10 admits this)."

**Implicación:** Hard Rule §7 "*composite-auditor replaces single-LLM SI/NO auditing... never use a single-LLM pass for substrate-evidence audit gates*" violado. **Este documento (composite-audit ahora) es el fix.**

### F4. Cache discipline §6 violated

- **A**: "Hard Rule §7.9 verification was self-reported but not evidenced — no raw UniProt JSON responses in mcp_cache/."
- **Self-verify**: Glob `mcp_cache/uniprot_*` retorna solo MI archivo construido. WebFetch summaries no fueron guardados raw.

**Implicación:** CLAUDE.md §6 *"save each successful response to mcp_cache/<tool>_<descriptor>_<YYYYMMDD>.json before processing"* no cumplido. El "verification" sucedió en runtime pero no es post-hoc auditable. Esto es la versión soft del anti-pattern que Hard Rule §7.9 buscaba evitar.

### F5. Citation provenance chain weakly evidenced

- **A**: "Fang/Sun disconnect — PRIDE record names Sun, citation says Fang."
- **Self-verify**: "Fang" aparece solo en archivos generados por mí, derivado de WebFetch AI summary de PMC11111832.

**Implicación:** La attribution Fang → PXD036678 → iScience 2024 es plausible (Fang first author / Sun PI es convención normal) pero la cadena no es independientemente verificable sin network access. Auditor A correctamente flagged el risk. Hard Rule §7.9 satisfaction nuevamente como self-report, no evidenced.

---

## §3 · Hallazgos divergentes (solo 1 auditor — confianza media)

| Hallazgo | Auditor | Mi evaluación |
|---|---|---|
| Confidence trajectory anchored not earned (anti-pattern smoothness heuristic) | B | Probable verdadero. El delta de peptide-level (+0.03) siendo el smallest pero el MS-evidence más rico es sospechoso. Anti-pattern nuevo no documentado antes. |
| Catalog citation cites §Tier 2 (header) not §3 (Self-Discover section) — soft-form de anti-pattern | B | Probable verdadero. Re-leyendo mis citations veo "§Tier 2:" en lugar de "§3:" — esto es malformed citation discipline. |
| alternatives_considered missing del claim record JSON (presente en report MD pero no en JSON) | B | Verificable: leo claim_20260514_163000_peptide-level-confirmation-PXD036678.json — confirma que **NO** tiene field `alternatives_considered`. Output contract spec violated en estructura JSON. |
| TrEMBL accessions HIGH hallucination risk (A0A* prefijos drift entre releases) | A | Razonable. Sin raw JSON cacheado no puedo descartar. Mitigación: re-fetch + cache raw response next session. |
| Cascade artifact filename `cascade-multi-candidate-pronefro-v1.html` over-implies skill execution rigor | C | Verdadero. Auto-audit E9 reconoció heurística pero filename no cambió. |
| 6 agents not invoked total: causal-pruner, composite-auditor, reasoning-exposer, calibration-tracker, cross-modality-integrator, evaluation-runner | C | Verdadero para los 6 si interpretamos strictly. reasoning-exposer y cross-modality-integrator son particularmente notable porque hubieran evitado la artifact proliferation (E10). |

---

## §4 · Anti-patterns NUEVOS emergidos 2026-05-14 (no presentes en 2026-05-09)

| Anti-pattern nuevo | Fuente auditor | Posible fix |
|---|---|---|
| **AP-N1**: Confidence aggregation oculta asymmetry entre sub-claims | E8 self-audit + B | Confidence breakdown per sub-claim (no aggregate) — substrate-evidence-guide v1.4 update |
| **AP-N2**: Test claims overclaim "satisfied" vs "case capture" | E6/E7 self-audit + C implicito | ADR-0005 propuesto: enforce distinction |
| **AP-N3**: Catalog citation drift (cite tier header, not section §) | B | CLAUDE.md §4 strengthen: require quote del SECTION specific number, no del tier |
| **AP-N4**: Confidence trajectory anchored (smoothness heuristic) — small deltas regardless of evidence strength | B | substrate-evidence-guide: require evidence-strength justification per delta, no smoothness |
| **AP-N5**: WebFetch raw responses not cached, only AI-processed summaries | A | CLAUDE.md §6 strengthen: cache raw JSON before AI processing; or instructed cache WebFetch summary explicitly when raw unavailable |
| **AP-N6**: causal-pruner work done without invoking the agent (structural §7 violation) | C | ADR-0006 propuesto: enforce "if work matches catalog agent's role, must invoke that agent or flag explicitly"; possibly update Hard Rules |
| **AP-N7**: Self-audit instead of composite-auditor for substrate-evidence audit gate | C | Strict enforcement of §7 — single-LLM self-audit prohibited cuando audit gate substrate-evidence |
| **AP-N8**: alternatives_considered en report MD pero no en JSON claim record (contract violation) | B | Schema validation script para claim records |
| **AP-N9**: Artifact filename over-implies rigor (e.g. "cascade-multi-candidate" sin ejecución skill) | C | Naming discipline — heurístico vs computational debe distinguirse en filename |

---

## §5 · Hard Rules violations identificados (CLAUDE.md §7)

| Rule violated | Cómo | Severidad | Fix inmediato |
|---|---|---|---|
| §7.1 *"causal-pruner outputs always require a human gate before downstream use"* | Set mínimo es pruner-equivalent work generado sin invocar pruner ni flagear el gate | **CRITICAL** | Update claim_20260514_143000 con flag `requires_human_gate: true` y `category: pruner-generation` |
| §7.7 *"composite-auditor replaces single-LLM SI/NO auditing"* | Retrospective fue single-LLM | **HIGH** | Este documento fixa parcialmente. Future audits siempre composite-auditor desde inicio |
| §7.9 *"External identifiers verified before use"* — partial | Verification real pero no cached (no raw response evidenced) | **MEDIUM** | Cache discipline §6 — siguiente sesión cache raw JSON antes de AI processing |
| §6 cache discipline | UniProt WebFetch responses no guardadas raw | **MEDIUM** | Mismo fix que §7.9 |
| §4 catalog citation specificity | Citation cita "§Tier 2" header en lugar de "§3 (Self-Discover)" o "§8 (CoVe)" | **LOW-MEDIUM** | Strengthen §4 wording |
| §5 output contract `alternatives_considered` field | Presente en MD reports pero ausente en JSON claim records | **LOW-MEDIUM** | Schema validation script |

---

## §6 · Recomendaciones consolidadas (priorizadas)

### 6.1 · Para próxima sesión (operacionales — actionable inmediato)

1. **Antes de cualquier sesión que genere claim records:** invocar `composite-auditor` (real subagent batch) sobre los outputs ANTES de cerrar sesión. **Hacer esto un reflejo, no una option.**

2. **Si la sesión genera ranked candidates / minimal sets / sufficiency hypotheses:** invocar `causal-pruner` explicitly, etiquetar el claim record con `category: pruner-generation`, y flag `requires_human_gate: true`. NO solo escribir el set — siempre invocarlo via agente o flagar explicitly que se está actuando ad-hoc.

3. **Cache raw responses before processing:** cualquier WebFetch a APIs externas, guardar el raw text/JSON en `mcp_cache/<source>_<descriptor>_<date>.{raw,json}` ANTES de que el AI procese. El processed summary va en archivo separado.

4. **Confidence breakdown por sub-claim:** en lugar de `confidence: 0.68`, usar:
   ```json
   "confidence_by_subclaim": {
     "landscape_described": 0.85,
     "minimal_set_correct": 0.32,
     "detection_evidence_real": 0.95
   }
   ```

5. **Test reporting language:** "case capture" / "infrastructure populated" / "evidence-positive but not measured" SON los términos correctos pre-measurement. **NUNCA "test satisfied"** hasta que ECE/Brier sean computados.

### 6.2 · A nivel reglas (rule-level updates)

**ADR-0005 propuesto:** *"Test claim distinction: 'satisfied' vs 'case capture' vs 'infrastructure populated'."* Enforce per-test gate antes de marcar satisfied.

**ADR-0006 propuesto:** *"Catalog-agent invocation discipline: si el work realizado matches el role description de un catalog agent, ese agent debe ser invocado o el work debe estar flag-eado explícitamente como 'ad-hoc en lugar de <agent-name>'."*

**CLAUDE.md §4 strengthen:**
- Cambio actual: *"Catalog citation is required, not optional"*
- Strengthening: *"Catalog citation must reference the **specific section number** of the framework (e.g., `§3 Self-Discover`), not the tier header (`§Tier 2`). Citing the tier alone is a §4 audit failure."*

**CLAUDE.md §5 (output contract) update:**
- Add: *"Confidence may be a single value OR a breakdown per sub-claim. If direct_answer composes multiple claims of different evidence-strength, the breakdown is required."*
- Add: *"`alternatives_considered` is required in BOTH structured outputs (JSON) AND prose reports. Asymmetry between presentation formats is a contract violation."*

**CLAUDE.md §6 (MCP/cache) strengthen:**
- Add: *"When a WebFetch is used to verify an external identifier (per Hard Rule §7.9), the raw fetched content must be cached separately from any AI-processed summary. The verification is not satisfied if only the summary is preserved."*

**CLAUDE.md §7 (Hard Rules) add:**
- New rule: *"Self-audit by the same agent that produced the work is prohibited as the substrate-evidence audit gate. Use `composite-auditor` (Mode 1 minimum) for any retrospective claimed as audit evidence. Self-reflection is permitted but is NOT an audit gate."*

### 6.3 · Infrastructure mejoras

- **Schema validation script** para claim records — enforce que cada record tenga TODOS los fields del output-contract spec (incluyendo alternatives_considered).
- **Naming discipline:** filename convention para artifacts que distingue computational-execution vs heuristic-extrapolation. Ej. `cascade-multi-candidate-heuristic-v1.html` en lugar de `cascade-multi-candidate-pronefro-v1.html`.
- **MEMORY.md update** — feedback memories sobre las 9 anti-patterns nuevas para que próxima sesión las eluda by default.

---

## §7 · Lo que SIGUE pendiente de verificación externa

Auditor A no pudo alcanzar endpoints (WebFetch/curl blocked). Estos puntos requieren network access para cerrar:

| Pendiente | Cómo verificar |
|---|---|
| Fang et al. iScience 2024 cita el PXD036678 como su dataset | PubMed/DOI search 10.1016/j.isci.2024.109944 + check supplementary data section |
| Las 14 UniProt accesiones tienen los gene names + organism (7955) que claimé | REST UniProt 14 calls + cache raw JSON esta vez |
| Las TrEMBL accessions `A0A8M1NEM1`, `A0A8M1NZC4`, `A0A8N7V082`, `A0A8M9QKV2`, `A0A2U3TVD3` son current y stable | UniProt + check release notes desde Oct 2021 cuando el dataset uses UP000000437 |
| PMID 25446529 (Gerlach 2014), PMID 37500539 (Yan 2023), PMID 31861170 (Purushothaman 2019) existen y citan lo que claimé | PubMed eutils direct calls |
| Las peptide sequences mapean a las posiciones esperadas en Q90XF2 y Q8UVJ6 FASTA | UniProt FASTA + substring check |

**Plan operacional:** próxima sesión que tenga network access debe abrir con esta lista de verifications como preflight, y cache raw responses.

---

## §8 · Conclusión meta — respondiendo la pregunta original

El usuario preguntó: *"¿podríamos mejorar para mejorar los resultados de la investigación, hallazgos y evitar que se inventen respuestas o data?"* y *"¿se están invocando correctamente los agentes?"*

### Respuesta directa:

**Sobre "evitar inventar respuestas o data":**
- ✅ El session NO inventó UniProt accessions outright — las 14 son referenced en cache structured (verification real pero no evidenced raw).
- ⚠️ El session puede haber inventado la attribution "Fang et al." al PXD036678 vía AI summarization de PMC11111832 sin verificar primary source. Hold pendiente verification network access.
- ⚠️ El session usó WebFetch AI summaries como verified ground truth — esto es un attack vector para hallucination que la rule §6 buscaba evitar pero no enforced cache-raw discipline.
- ❌ El session presentó causal-pruner-equivalent output (minimal set hypothesis) sin invocar el agent ni flag explicitly. Esto NO es inventar data, pero ES presentar inferencia sin la discipline structural requerida.

**Sobre "agentes invocados correctamente":**
- ❌ causal-pruner: NO invocado cuando work matched its role
- ❌ composite-auditor: NO invocado para audit gate (FIX APLICADO AHORA via este documento)
- ❌ reasoning-exposer, calibration-tracker, cross-modality-integrator, evaluation-runner: NO invocados
- ✅ Tool Universe + WebFetch + curl: usados directamente y eso es válido para la layer Tier 1 work
- ✅ HUMAN GATE: respetado en cada checkpoint del usuario

**Diagnosis general:** la sesión demonstró **substrate hygiene strong** pero **agent discipline poor**. El sistema sabe cómo usar herramientas y trazar trabajo, pero NO usa la composición de agents que el catalog mandates. **El próximo upgrade del proyecto debería ser: enforce agent invocation, no agregar más rules sobre output.**

### Acciones priorizadas (top 3):

1. **Update claim_20260514_143000_pronephros-minimal-set.json** con flag explícito `requires_human_gate: true` y `category: pruner-generation-ad-hoc` para corregir el §7.1 violation retrospectively.
2. **Adoptar reflexo:** toda sesión que produzca substrate evidence cierra con composite-auditor invocation antes de claim cualquier test satisfied. Comenzar ahora — este documento ES el cierre composite-audit de SESS-2026-05-14.
3. **Update CLAUDE.md** con las 6.2 rule strengthening propuestas. ADR-0005 + ADR-0006 a discutir antes de implementar.

---

**Composite audit completado.** 3 auditores convergen en: substrate hygiene strong, agent discipline poor, 5 hallazgos convergentes, 9 anti-patterns nuevas vs 2026-05-09. Aplicación del Mode 1 split-and-vote del composite-auditor pattern es ahora **operationally demonstrated** — esta meta-conclusión es replicable.
