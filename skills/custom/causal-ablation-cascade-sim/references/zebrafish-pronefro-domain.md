# Zebrafish Pronephros Domain Reference (Fase I)

Reference biology for the Fase I worked example. When the skill is applied to other tissues (córnea, mouse organs, etc.), this file does NOT apply — but its **structure** is the template for the equivalent domain reference for the other tissue.

---

## §1 Developmental Sequence

| Stage | hpf | t-norm | Event |
|---|---|---|---|
| Blástula | 3–6 | 0.00–0.13 | Cleavage, blastomere divisions |
| Gastrul · mesendodermo | 6–10 | 0.13–0.30 | Epibolia, involución/ingresión; convergencia-extensión |
| LPM bilateral · IM emergente | 10–14 | 0.30–0.50 | LPM stripes; IM emerges within LPM; AP elongation via PCP intercalation |
| MET · pre-tubulogénesis | 14–18 | 0.50–0.72 | Mesenchymal-to-epithelial transition; constricción apical; pre-tube polarization |
| Túbulo · lumenogénesis | 18–24 | 0.72–1.00 | Tube formation; lumen establishment; maduración |

---

## §2 Marker Genes by Stage

### Identity / Specification

| Stage | Markers (encendidos) | Markers (apagados) |
|---|---|---|
| Mesendodermo | gsc, ntl/tbxta, sox17, eve1 | — |
| LPM | hand2 (lateral), tbx5a | — |
| IM emergente | pax2a, lhx1a | mesoderm general |
| Pronephric progenitor | wt1a, pax2a, lhx1a | — |
| Túbulo cell | cdh17 (renal-specific cadherin), pax2a sustained | cdh2/N-cadherin (mesenchymal) |

### Mechanical / Mechanotransduction

| Category | Markers |
|---|---|
| Non-muscle myosin II | myh9a, myh9b, myh10, myh14 |
| Rho-asociated kinase | rock1, rock2a, rock2b |
| Stress response | fos, jun, egr1, hspa |
| YAP/TAZ targets | ctgf/ccn2, cyr61/ccn1, ankrd1 |
| PCP pathway | vangl2, prickle1 (pk1), fzd7 |
| Apical polarity | pard3, pard6, prkci (aPKC), crb2a |
| Tight junctions | zo1 (tjp1), claudins (cldn7), occludin |
| Lumen markers | podxl, prom1a |

---

## §3 Mechanical Events per Window

### 6–8 hpf (Etapa 1 · mesendodermo)

- Convergencia-extensión (C-E): cells move toward dorsal midline (convergence) and extend AP (extension)
- Involución / ingresión: mesendodermal cells internalize
- Actomyosin role: cortical tension drives directional movement
- Pronephros consequence: defines where LPM will form lateral to the axis
- **Perturbation phenotype signature**: DISLOCACIÓN — field positioned mal lateral and AP

### 10–12 hpf (Etapa 2 · LPM/IM)

- LPM bilateral stripes consolidate
- IM emerges as a sub-domain within LPM (pax2a/lhx1a+ stripe within hand2+ LPM)
- AP intercalation via PCP: cells slide between each other elongating the field
- Actomyosin role: provides cortical tension that PCP machinery uses to drive directional intercalation
- **Perturbation phenotype signature**: COMPRESIÓN — field compressed AP, position correct

### 14–16 hpf (Etapa 3 · pre-MET / MET)

- Cadherin switching: mesenchymal markers decrease, epithelial markers increase (cdh17 turning on)
- Apical-basal polarity establishment (Par3/aPKC apical; Lgl/Scrib basolateral)
- Constricción apical: actomyosin at the apical pole contracts, bending the cell sheet
- Lumen formation: hollow space forms at the apical surface, bordered by tight junctions
- Actomyosin role: **DIRECT** — the constricción itself builds the lumen
- **Perturbation phenotype signature**: FALLA DE PARED / LUMEN — bumpy wall (hipo), Swiss cheese (KO), or amorphous mass (persistent KO)

### 18–24 hpf (post-Etapa 3, READOUT WINDOW)

- Tube extension and maduración
- Functional segmentation: glomérulo, neck, proximal tubule, distal tubule, cloaca
- This window is downstream of the perturbation windows; phenotypes here are READOUTS, not perturbation targets in the Fase I cascade
- Could become a perturbation target in later phases if needed

---

## §4 Why "Three Phenotypes from One Machinery" Is the Big Finding

The same protein complex (actomiosina) operates in three windows:

1. **6–8 hpf**: drives C-E → affects **position** (LPM lateral, IM dorsal-lateral, axis AP)
2. **10–12 hpf**: drives intercalación → affects **shape** (AP elongation)
3. **14–16 hpf**: drives constricción apical → affects **architecture** (lumen, polaridad apical)

If actomyosin had a single "function", perturbing it earlier vs later should produce *graduated* phenotypes (mild → severe along one axis).

If actomyosin has **stage-specific functions**, perturbations should produce **cualitativamente distinct** phenotypes.

The Fase I cascade observed the latter: dislocación, compresión, falla de lumen — three *qualitative* defects from one molecular machinery.

This is consistent with — and provides specific evidence for — the broader hypothesis: **"same machinery, different temporal contexts → different phenotypes"** as a core principle of organogenesis biology.

---

## §5 Validation Considerations

### Bulk RNA-seq is insufficient

For the morphology-vs-identity decouple test, bulk RNA-seq cannot distinguish dislocación-with-normal-identity from disrupted-identity. Identity markers in bulk look normal because their LEVELS are preserved — what changes is their SPATIAL DISTRIBUTION.

### Required techniques for full validation

- **HCR-FISH cuantitativa** — quantifies marker expression with spatial resolution
- **Spatial transcriptomics** (Visium, Stereo-seq) — bulk-level coverage with spatial registration
- **Live-imaging with photo-activable myosin inhibitors** (blebbistatin photo-cage) — gold standard for stage-specific in vivo perturbation
- **TUNEL or active-caspase-3 IHC** — assess apoptosis; ~10–25% expected in catastrophic scenarios

### Sample size considerations

- Hipomorfo scenarios: n ≥ 15 embriones per condition
- KO scenarios: n ≥ 25 because higher inter-embrión variance + survival sesgo
- Persistent Mode B catastrophic: account for lethality (~30–70% survival depending on dose/window)

---

## §6 Files (Canonical Example)

In `reports/`:

| File | Purpose |
|---|---|
| `etapa1-mesendodermo-conclusion.html` | Etapa 1 standalone (Modo A/B × hipo/KO) |
| `etapa2-im-conclusion.html` | Etapa 2 standalone + cross vs Etapa 1 |
| `cierre-cascada-completa.html` | Three-stage consolidated closure |
| `visualizacion-cascada-pronefro.html` | Single-scenario viz, 9 scenarios (Etapas 1+2 only) — v1 reference |
| `visualizacion-comparacion-pronefro.html` | Comparison viz, 9 scenarios — v1 reference |
| `visualizacion-cascada-pronefro-v2.html` | Single-scenario, 13 scenarios (3 stages) |
| `visualizacion-comparacion-pronefro-v2.html` | Comparison, 13 scenarios |

The v1 versions are preserved per the hard rule against modifying existing files. They demonstrate the 2-stage state of the cascade; v2 shows the 3-stage complete state.

---

## §7 Adapting to Other Tissues

When the skill is applied to a non-pronefro tissue:

1. **Replace developmental sequence** — identify the equivalent windows for that tissue
2. **Identify identity markers** — what defines that tissue's lineage at each stage
3. **Identify mechanical machinery** — is it actomyosin? PCP? something else?
4. **Map mechanical events per window** — which process is dominant in each stage
5. **Predict perturbation signatures** — what would each stage's defect look like?

Tissues considered for Fase II/III:
- **Córnea / segmento anterior** (Test 5 candidate partner field — see `PROJECT_SCOPE.md §11`)
- **Mouse organs** in Fase II
- **Human PSC organoids** in Fase III

For each, the skill template applies but the domain reference must be rebuilt. The 4-scenario protocol and decouple paradigm transfer directly; the biology specifics do not.
