# ¿Son buenas las respuestas de nuestra IA? — hoja de calificación (equipo Latido Médico)

Estamos desarrollando un asistente de IA para la investigación del riñón embrionario del pez cebra. Antes de confiar en él, queremos que ustedes (los expertos) nos digan si sus respuestas sirven. **No necesitas saber nada del sistema por dentro.** Lee la pregunta, lee lo que respondió la IA, y califica.

**Escala:** *Sí, sólida* · *Más o menos* · *No*. Son 5 preguntas, ~10 min cada una.

---

## 1. Marcadores de los segmentos del riñón

**Le preguntamos a la IA:** El riñón embrionario del pez cebra (el *pronefros*) forma un túbulo con varios segmentos: túbulo proximal, distal temprano, distal tardío y el conducto. **¿Qué genes marcan cada uno de esos segmentos, y con qué identificador se confirman?**

*Por qué importa:* Distinguir los segmentos por sus marcadores es la base para confirmar que se formó un riñón de verdad, y no un tejido genérico.

<details><summary><b>Ver la respuesta de la IA</b></summary>

<sub>(Recortamos una nota técnica inicial del sistema; el razonamiento científico está completo.)</sub>

```
ANSWER — segment-specific discriminators along the zebrafish pronephros proximodistal axis (canonical Wingert et al. 2007 model; IDs verified this run):

PROXIMAL TUBULE
- PCT (proximal convoluted): slc20a1a = ENSDARG00000020114; slc4a4a = ENSDARG00000013730
- PST (proximal straight): trpm7 = ENSDARG00000036232; slc13a1 = ENSDARG00000045638

DISTAL EARLY (DE)
- slc12a1 (NKCC2-type Na-K-2Cl cotransporter) = ENSDARG00000098096 — the DE-specific discriminator
- kcnj1a.1 (romk) = ENSDARG00000091232 — expressed across DE and DL; supporting, not DE-exclusive

DISTAL LATE (DL)
- slc12a3 (NCC-type Na-Cl cotransporter) = ENSDARG00000013855 — the DL-specific discriminator

PRONEPHRIC DUCT (PD)
- gata3 = ENSDARG00000016526

Cleanest four-way separation: slc20a1a/trpm7 (proximal) | slc12a1 (DE) | slc12a3 (DL) | gata3 (duct). The slc12a1→slc12a3 switch is the textbook DE/DL boundary discriminator.

CONFIDENCE BREAKDOWN (§5 — asymmetric subclaims; schema forces one scalar, so stated here): (a) verified IDs ~0.99 (every ENSDARG confirmed live vs Ensembl GRCz11, matches store, raw cached); (b) marker→segment biological mapping ~0.87 (canonical, well-established, but Wingert 2007 PMID not re-verified via a literature tool this run, and the in-repo atlas is anterior-biased — slc12a1 returned id_not_in_var_names, so distal assignments are not corroborated by in-repo expression). Aggregate reported below reflects the composite, weighted toward the ID subclaim the question centers on.
```
</details>

**Tu calificación:**

- ¿La respuesta es correcta y útil?  ☐ Sí, sólida   ☐ Más o menos   ☐ No
- ¿Qué le falta o qué corregirías?  ______________________________________________
- ¿La usarías para planear un experimento real?  ☐ Sí   ☐ No
- Calificado por (nombre / rol): __________________________

---

## 2. Equivalentes humanos y genes duplicados que podrían confundir un experimento

**Le preguntamos a la IA:** Para varios factores de transcripción clave del riñón del pez cebra, **¿cuál es su gen equivalente en humano?** Y de esos, **¿cuáles tienen un gen “hermano” duplicado** (ohnólogo) que podría compensar y **ocultar el efecto si silenciamos (knock-out) solo uno**?

*Por qué importa:* Si un gen tiene un duplicado que hace casi lo mismo, un knock-out simple puede “no mostrar nada” aunque el gen sí importe. Hay que saberlo ANTES de diseñar el experimento.

<details><summary><b>Ver la respuesta de la IA</b></summary>

<sub>(Recortamos una nota técnica inicial del sistema; el razonamiento científico está completo.)</sub>

```
MAPPING + KO-CONFOUND FLAGS:
1) pax2a (ENSDARG00000028148) → human PAX2 (ENSG00000075891). Ensembl call ortholog_ONE2MANY, both directions. Co-ortholog pax2b (ENSDARG00000032578, symbol-verified via lookup). FLAG 1:MANY — single-gene KO of pax2a alone is confounded by pax2b; use double KO / MO or confirm pax2b is not co-expressed.
2) pax8 (ENSDARG00000015879) → human PAX8 (ENSG00000125618). ortholog_ONE2ONE both directions. NO FLAG — clean single-gene KO target (no retained teleost duplicate).
3) wt1a (ENSDARG00000031420) → human WT1 (ENSG00000184937). Ensembl ortholog endpoint calls this ONE2ONE and returns wt1b EMPTY — BUT the paralogue endpoint classifies wt1a↔wt1b (ENSDARG00000007990) as a within_species_paralog at the Euteleostomi node (~71% id). FLAG 1:MANY (HIDDEN) — the automated ortholog call UNDER-reports this; a researcher trusting one2one would miss that wt1b is the teleost ohnolog and a compensation candidate. This is the headline calibration lesson: ortholog_one2one ≠ 'no paralog compensation risk'.
4) hnf1ba (ENSDARG00000006615) → human HNF1B (ENSG00000275410). ortholog_ONE2MANY both directions. Co-ortholog hnf1bb (ENSDARG00000022295; matches our own marker file). FLAG 1:MANY — hnf1bb is lowly but detectably expressed in our pronephros data, so compensation is plausible.
5) sim1a (ENSDARG00000023316) → human SIM1 (ENSG00000112246). ortholog_ONE2MANY. A retained duplicate sim1b exists (ENSDARG00000013789, symbol-verified). FLAG 1:MANY (PROBABLE) — but note the SIM1 ortholog endpoint's second target was ENSDARG00000039935 (a divergent bHLH-PAS gene, ~35% id), NOT sim1b; the specific sim1a↔sim1b ohnolog pairing was not confirmed by a paralogue query this session. Moderate confidence.
6) lhx1a (ENSDARG00000014018) → human LHX1 (ENSG00000273706): UNRESOLVED. Ensembl Compara returns empty homologies in BOTH directions (no gene tree on that gene id). Not asserting lhx1a→LHX1 from memory; cross-check ZFIN/Alliance or NCBI orthologs before use.

CONFIDENCE BY SUBCLAIM (aggregated to 0.82 for the schema): verified ENSDARG bindings + Ensembl calls ~0.90; PAX2/HNF1B 1:many flags ~0.90; WT1 hidden-ohnolog flag ~0.85; SIM1 probable ohnolog ~0.60; the functional inference 'paralog COULD compensate in a KO' ~0.70 (teleost-redundancy prior, not measured for these pairs). LHX1 is reported as a gap, not a claim.

BOTTOM LINE for wet-lab design: pax8 is the only clean single-gene KO target here. pax2a, hnf1ba, and wt1a all carry a retained zebrafish ohnolog (pax2b, hnf1bb, wt1b) that can mask loss-of-function; plan compound perturbation or paralog-expression controls. wt1a is the trap — it looks 1:1 in a naive ortholog lookup. sim1a probable-flag pending a paralogue confirmation; lhx1a mapping pending a second source.
```
</details>

**Tu calificación:**

- ¿La respuesta es correcta y útil?  ☐ Sí, sólida   ☐ Más o menos   ☐ No
- ¿Qué le falta o qué corregirías?  ______________________________________________
- ¿La usarías para planear un experimento real?  ☐ Sí   ☐ No
- Calificado por (nombre / rol): __________________________

---

## 3. La cascada de señales que enciende el riñón

**Le preguntamos a la IA:** **¿Cuál es la cascada de señales (BMP, Nodal y ácido retinoico) que induce la formación del pronefros?** Descríbela como una red de pasos, e indica qué información (constantes, tiempos) haría falta para poder simularla.

*Por qué importa:* Entender bien la cascada de inducción es el corazón del proyecto: es lo que —en teoría— permitiría “encender” el programa del riñón en el momento correcto.

<details><summary><b>Ver la respuesta de la IA</b></summary>

<sub>(Recortamos una nota técnica inicial del sistema; el razonamiento científico está completo.)</sub>

```
RECONSTRUCTION OF THE BMP / NODAL / RA CASCADE FOR ZEBRAFISH PRONEPHROS INDUCTION AS A BioNetGen (BNGL) RULE-BASED MODEL — plus the kinetic-parameter requirement.

Project-state preflight: the verified store (analysis/outputs/verified_identifiers.json, 51 records, human-gated) already grounds the RA arm (aldh1a2, cyp26a1) and the intermediate-mesoderm/pronephros readouts (osr1, pax2a, pax8, lhx1a, wt1a, wnt8a, fgf8a) with raw-cached ENSDARG IDs; the BMP and Nodal arms were absent and were verified this session via Ensembl (danio_rerio, GRCz11). No prior BioNetGen/BNGL artifact exists in the repo for this cascade (grep of analysis/outputs returned only marker/DE files), so the network structure below is newly synthesized and operates from external structured evidence + established developmental biology.

--- BIOLOGICAL LOGIC (what the network must encode) ---
Pronephros derives from intermediate mesoderm (IM). Three signals converge: (1) NODAL (ndr1/squint, ndr2/cyclops, co-receptor tdgf1/oep; feedback inhibitors lft1/lft2) does graded mesendoderm induction — the classic activator(short-range Nodal)/inhibitor(long-range Lefty) reaction-diffusion module. (2) BMP (bmp2b:bmp7a obligate heterodimer, bmp4; antagonist chordin/chrd) sets the dorsoventral gradient; IM/pronephros arises at INTERMEDIATE (ventrolateral) BMP level — neither peak-ventral nor antagonist-dorsalized. (3) Retinoic acid (synthesis aldh1a2, degradation cyp26a1; nuclear receptors raraa:rxrba on RAREs) sets anteroposterior position and proximodistal segment identity of the tubule. The readout is IM/pronephros-field transcription (osr1 earliest, then pax2a/pax8/lhx1a/wt1a).

--- BNGL MOLECULE TYPES (species with components/states) ---
Ligands: Bmp2b, Bmp7a (dimer Bmp2b:Bmp7a), Bmp4; Ndr1, Ndr2; RA (small molecule). Extracellular modulators: Chrd (BMP antagonist), Lft1, Lft2 (Nodal antagonists). Receptors: BMP type-I (bmpr1aa/ab≈ALK3/6) + type-II (bmpr2, acvr2a/b); Nodal type-I acvr1b(ALK4)/acvr1c(ALK7) + type-II acvr2a/b + co-receptor Tdgf1(oep); nuclear Raraa:Rxrba. Transducers: Smad5~{P0/P1} (BMP R-SMAD), Smad2~{P0/P1} (Nodal R-SMAD), Smad4a (co-SMAD, SHARED pool → BMP/Nodal competition node), with a nuc/cyt location component. Enzymes: Aldh1a2, Cyp26a1. Target-gene nodes: osr1, pax2a, pax8, lhx1a, wt1a.

--- BNGL RULE CLASSES (reactions) ---
R1 Ligand/enzyme synthesis (spatially gated source): 0 -> L, k_prod. R2 Ligand degradation/clearance: L -> 0, k_deg. R3 Antagonist sequestration: Chrd+BMP<->Chrd:BMP; Lft competes for Nodal/co-receptor (kon/koff). R4 Ligand-receptor binding (grounded by OmniPath, all edges stimulatory): BMP2b/7a/4 + {bmpr1*, bmpr2, acvr2*}<->complex; Ndr + {acvr1b/1c + acvr2* + tdgf1}<->complex. R5 Receptor-kinase → R-SMAD phosphorylation (catalytic): active BMP-receptor: Smad5~P0->Smad5~P1; active Nodal-receptor: Smad2~P0->Smad2~P1 (kcat, Km). R6 SMAD-complex assembly: Smad5~P1+Smad4a<->complex; Smad2~P1+Smad4a<->complex (competition for Smad4a). R7 Nuclear shuttling: complex cyt<->nuc (k_in/k_out); phosphatase Smad~P1->Smad~P0. R8 Transcription (Hill): nuclear pSMAD:Smad4 -> target mRNA; RA:Raraa:Rxrba on RARE -> target mRNA; Vmax, Hill n, threshold K. R9 Feedback motifs: Nodal auto-activation (+), Nodal->lft induction (−, delayed) = reaction-diffusion core; RA->cyp26a1 induction (−) = self-limiting RA sink; Aldh1a2: retinaldehyde->RA and Cyp26a1: RA->4-OH-RA (enzyme kcat/Km). R10 Integration/readout: osr1/pax2a/pax8 transcription as a logic AND over {intermediate BMP-Smad, Nodal-Smad history, permissive RA}.

--- KINETIC PARAMETERS NEEDED (the explicit ask; by class) ---
(a) Production/secretion rates k_prod per ligand+enzyme; (b) Diffusion coefficients D per diffusible morphogen — the DIFFERENTIAL Nodal-vs-Lefty diffusivity is the load-bearing parameter for the reaction-diffusion behavior, plus effective D for BMP and RA; (c) Degradation constants k_deg for ligands, Smads, mRNAs (sets gradient length scale λ=√(D/k_deg)); (d) Binding kon/koff (or Kd) for every ligand-receptor and antagonist-ligand pair; (e) Total receptor/co-receptor abundances + Smad4a pool size (the BMP/Nodal competition parameter); (f) Receptor-kinase kcat/Km for R-SMAD phosphorylation and phosphatase rate; (g) SMAD complex assoc/dissoc + nuclear import/export rates; (h) Transcription Vmax, Hill coefficient n, activation threshold K for Smad-binding-elements and RAREs; (i) RA-metabolism enzyme kcat/Km (Aldh1a2, Cyp26a1) + retinaldehyde supply; (j) Feedback gains (Nodal autoactivation, Nodal→Lefty, RA→cyp26a1); (k) Initial conditions + compartment geometry (cell count/spacing) for the spatial version.

--- HONEST CAVEATS ---
BioNetGen suitability: BNGL is well-suited to the INTRACELLULAR combinatorics (BMP binding many type-I/type-II receptor combinations — OmniPath returned dozens of distinct BMP2/BMP7→receptor-complex edges; rules avoid enumerating every species). But the morphogen-GRADIENT (diffusion in space) is not native to core BNGL/NFsim (well-mixed); the spatial reaction-diffusion part requires compartmental BNGL or coupling to a PDE/agent framework (VCell/MCell/MorpheusL). State that explicitly rather than implying pure BNGL captures the gradient.
Evidence-lens: OmniPath receptor edges and Reactome reaction sets are HUMAN orthologs (ortholog_regulatory tier ≈0.5 per ADR-0028), not native zebrafish perturbation evidence; they justify topology and edge sign, not zebrafish-specific quantitation.
Kinetic VALUES are essentially a gap: none of the structured databases queried return rate constants. EuropePMC did not surface the canonical zebrafish Nodal/Lefty FRAP/FCS diffusivity measurement, so I deliberately did NOT assert numeric D values (anti-fabrication gate §7). One directly relevant, verified zebrafish reaction-diffusion parameterization was retrieved (Stark et al. 2025, Development, PMID 40462756: Fgf8a source-diffusion-degradation + ECM binding) — it grounds the parameter CLASSES, not the Nodal/BMP/RA numbers. Values would have to be sourced (zebrafish diffusivity papers), borrowed (mammalian TGF-β/Smad ODE models), or calibrated to expression data, and cached before use.

--- CONFIDENCE BY SUBCLAIM (asymmetric per §5) ---
Gene identities/ENSDARG bindings ≈0.97 (directly tool-verified); qualitative pathway membership + receptor-binding topology/signs ≈0.80 (OmniPath+Reactome+textbook, ortholog-level); the specific INTEGRATED pronephros-induction wiring/logic (exact edges+signs into osr1/pax2a and the AND-logic) ≈0.50 (synthesis/hypothesis — zebrafish IM causal wiring is only partly resolved and BMP's precise pronephros role vs generic DV patterning is nuanced); kinetic parameter VALUES ≈0.15 (not retrieved). Aggregate reported 0.55.

--- GOVERNANCE (agent-invocation + closing reflexes) ---
The integrated induction wiring in R10/R9 is a causal/sufficiency hypothesis = causal-pruner work; per §7 it is hypothesis-generation and REQUIRES a human gate before any downstream (wet-lab/design) use — flagged, not invoked here (subagent scope). This single-subagent output is NOT an audit gate; it must be composite-audited (≥3, Mode 1) before becoming substrate evidence. HTML report emission (§5/§7) is deferred to the orchestrating session (subagent returns via StructuredOutput; no report files written per subagent protocol) — flagged as a gap to close at conclusion.
```
</details>

**Tu calificación:**

- ¿La respuesta es correcta y útil?  ☐ Sí, sólida   ☐ Más o menos   ☐ No
- ¿Qué le falta o qué corregirías?  ______________________________________________
- ¿La usarías para planear un experimento real?  ☐ Sí   ☐ No
- Calificado por (nombre / rol): __________________________

---

## 4. Qué responde a la señal de ácido retinoico

**Le preguntamos a la IA:** Durante el modelado del pronefros, **¿qué elementos regulatorios del ADN responden a la señal de ácido retinoico**, y cómo se confirmaría con datos de genómica funcional?

*Por qué importa:* El ácido retinoico es una de las señales que da “coordenadas” al riñón; saber qué controla ayuda a manipularlo con precisión.

<details><summary><b>Ver la respuesta de la IA</b></summary>

<sub>(Recortamos una nota técnica inicial del sistema; el razonamiento científico está completo.)</sub>

```
RA-responsive regulatory elements in pronephros patterning are RAREs (retinoic-acid response elements — DR2/DR5 direct-repeat motifs) bound by RAR/RXR heterodimers. In the pronephros the operative logic is a proximodistal RA gradient: aldh1a2 (RALDH2) is the RA SOURCE in adjacent somitic/trunk mesoderm, and cyp26a1/cyp26b1 are the SINKS that degrade RA distally, so RAREs near proximodistal segment-identity genes switch state along that gradient. High RA promotes proximal segment fates (proximal tubule); RA clearance permits distal fates. The RAREs sit near RA-target loci — canonically the hox cluster genes (hoxb1b has a classic characterized RARE; hoxb8a is a bona-fide RA target) which set the anteroposterior register the pronephros segments read out. Receptors verified: raraa and rarga. All identifiers below verified LIVE via Ensembl REST (danio_rerio, GRCz11), not memory.

HOW DanioCODE-style functional genomics confirms responsiveness (grounded in retrieved GEO datasets, the deposition path for DanioCODE): the confirmation is a gain/loss-of-signal design. GEO GSE233698 ("Rewiring of the epigenome and chromatin architecture by exogenously induced retinoic acid signaling during zebrafish embryonic development") is exactly this and provides four orthogonal readouts on RA-manipulated (exogenous-RA vs control) embryos: (1) ATAC-seq [GSE233691] — a candidate element is RA-responsive if chromatin accessibility opens/closes upon RA perturbation; (2) RAR ChIP-seq [GSE233695] — direct receptor occupancy at the element demonstrates it is a genuine RARE, not a bystander; (3) Hi-ChIP [GSE233697] / 4C-seq [GSE249369] — physical enhancer-promoter looping to the target gene links the element to its RA-target; (4) H3K27ac ChIP delta marks activation. Pronephros-cell-type specificity is then obtained by intersecting these bulk-embryo signals with single-cell chromatin accessibility of zebrafish embryogenesis (SPATAC-seq, GSE243256, 535 samples) to isolate the pronephric-lineage accessible peaks, and conserved cis-regulatory-module calls (GSE294761) add orthology support. An element passes as RA-responsive when accessibility change + RAR occupancy + differential H3K27ac + looping to a pronephros gene co-localize and reverse under RA loss (e.g., DEAB/aldh1a2 knockdown).

Calibrated confidence_by_subclaim (the §5 schema here only exposes a single confidence, so breakdown is stated in prose): (A) verified gene identities/machinery ~0.92; (B) RAREs bound by RAR/RXR ARE the responsive elements ~0.85; (C) pronephros-specific proximodistal RA-gradient patterning model ~0.72 (partly domain knowledge; no pronephros-dissected primary source retrieved this run); (D) the DanioCODE/GEO confirmation design ~0.85 (directly grounded by GSE233698 series). Aggregate is tempered to ~0.6 because the question asks specifically WHICH elements in PRONEPHROS, and the pronephros-specific RARE coordinate catalog was not retrieved — the machinery, mechanism, and confirmation assay are grounded; the pronephros-element enumeration is a gap.
```
</details>

**Tu calificación:**

- ¿La respuesta es correcta y útil?  ☐ Sí, sólida   ☐ Más o menos   ☐ No
- ¿Qué le falta o qué corregirías?  ______________________________________________
- ¿La usarías para planear un experimento real?  ☐ Sí   ☐ No
- Calificado por (nombre / rol): __________________________

---

## 5. La “receta” de tejido-chaperón para inducir el riñón

**Le preguntamos a la IA:** Para inducir el programa del riñón en un **tejido vecino competente**, arma la tabla maestra: **qué tejido manda qué señal, a qué tejido blanco, y en qué ventana de tiempo** (horas post-fertilización).

*Por qué importa:* Esta es la estrategia central del proyecto: inducir un órgano en el lugar y el momento correctos usando un tejido “chaperón” que emite las señales.

<details><summary><b>Ver la respuesta de la IA</b></summary>

<sub>(Recortamos una nota técnica inicial del sistema; el razonamiento científico está completo.)</sub>

```
MASTER CHAPERONE-TISSUE INTERACTION TABLE — inducing the pronephric program in adjacent competent tissue (zebrafish, GRCz11). Target throughout = intermediate mesoderm (IM)/posterior lateral plate mesoderm, the competent field forming the bilateral pronephros. Rows [Source → Signal (verified gene) → Target → Window → role]: (1) Anterior paraxial mesoderm/somites → Retinoic acid synthesis, aldh1a2 (ENSDARG00000053493) → IM anterior/proximal → ~8-18 hpf → proximo-distal patterning, sets proximal segment identity — STRONGEST/best-validated input. (2) Posterior mesoderm/tailbud → RA degradation (counter-gradient), cyp26a1 (ENSDARG00000033999) + cyp26b1 (ENSDARG00000077121) → IM posterior/distal → ~8-18 hpf → clears RA posteriorly for distal identity. (3) Tailbud/posterior paraxial mesoderm → posteriorizing Wnt, wnt8a (ENSDARG00000052910) + wnt2ba (ENSDARG00000005050) → posterior LPM/IM → ~6-12 hpf → posteriorizes mesoderm, establishes posterior competence field. (4) Tailbud/posterior mesoderm → FGF, fgf8a (ENSDARG00000003399) + fgf24 (ENSDARG00000037677) → posterior LPM/IM → ~8-16 hpf → posterior mesoderm/IM specification. (5) Ventral/ventrolateral mesoderm → BMP, bmp2b (ENSDARG00000041430) → prospective IM → ~5-10 hpf → competence-establishing DV patterning (earliest). (6) Notochord/floor plate → Hedgehog, shha (ENSDARG00000068567) → medial IM → ~10-18 hpf → modest midline patterning input (exploratory, weakest). COMPANION READOUT MODULE (target-intrinsic response TFs = what 'competent' means, not source signals): osr1 (ENSDARG00000014091, earliest IM ~8-10 hpf), pax2a (ENSDARG00000028148, master specifier ~10-12 hpf), pax8 (ENSDARG00000015879), lhx1a (ENSDARG00000014018), wt1a/wt1b (ENSDARG00000031420/ENSDARG00000007990, podocyte ~14-24 hpf), hnf1ba (ENSDARG00000006615, tubule ~18-24 hpf). This is a DESIGN SCAFFOLD: all gene IDs are tool-verified, but the induction-SUFFICIENCY claim (that these signals reconstitute the program in competent tissue) is a causal-pruner-class hypothesis requiring a human gate + wet-lab GOF (Phase II) — not a validated protocol. HTML report: reports/2026-07-11_chaperone-tissue-interaction-table_v1.html.
```
</details>

**Tu calificación:**

- ¿La respuesta es correcta y útil?  ☐ Sí, sólida   ☐ Más o menos   ☐ No
- ¿Qué le falta o qué corregirías?  ______________________________________________
- ¿La usarías para planear un experimento real?  ☐ Sí   ☐ No
- Calificado por (nombre / rol): __________________________

---

