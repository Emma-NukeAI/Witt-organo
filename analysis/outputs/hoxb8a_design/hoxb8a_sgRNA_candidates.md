# hoxb8a sgRNA candidatos — pre-screening

**Ensembl ID:** ENSDARG00000056027
**Symbol:** hoxb8a
**Canonical transcript:** ENSDART00000046638
**CDS length:** 738 nt (246 codons)
**Search window:** primeros 300 nt de CDS (early KO target)

## Top 5 candidatos (ranked por heuristic score)

| Rank | Score | Strand | Pos | sgRNA 20nt | PAM | GC% | Notes |
|------|-------|--------|-----|-----------|-----|-----|-------|
| 1 | 70 | + | 57 | `CGACCAAACTATTACGAGTG` | `CGG` | 45% | GC ok (45%); G at position 20 |
| 2 | 70 | + | 76 | `GCGGATTTGCTCAGGACCTA` | `GGG` | 55% | GC ok (55%); G at position 1 (good for U6) |
| 3 | 70 | + | 111 | `GTCGTGTATGGTCCAGGCAC` | `CGG` | 60% | GC ok (60%); G at position 1 (good for U6) |
| 4 | 70 | + | 206 | `TTACCAGCAGAGTCCATGTG` | `CGG` | 50% | GC ok (50%); G at position 20 |
| 5 | 70 | + | 240 | `GGCGAGCCGGGTAACTTCTA` | `CGG` | 60% | GC ok (60%); G at position 1 (good for U6) |

## Recomendación al wet-lab partner

1. Select 2-3 candidatos de los top 5, prioritizing **strand diversity** (mix sense/antisense) and **position diversity** (no overlap).
2. Validate cada sgRNA candidato con production tool: ingresa la secuencia 23nt completa en CRISPRscan (https://www.crisprscan.org/), CHOPCHOP (https://chopchop.cbu.uib.no/), o CRISPOR (http://crispor.tefor.net/) — comparar scores.
3. Run in vitro cleavage assay con cada sgRNA + Cas9 + PCR amplicon de mafba antes de microinjection.
4. Order como Alt-R sgRNA from IDT (recomendado para zebrafish CRISPR-Cas9 RNP injection).

## Caveats importantes

- Este pre-screening NO incluye análisis de off-targets (requiere base de datos genoma-wide).
- Scoring es heurístico: GC content, polyT, position rules. No reemplaza scoring de tools production que usan CNN entrenados.
- En zebrafish, F0 crispants con 2 sgRNAs simultáneos típicamente generan deleciones grandes (entre los dos cuts), lo cual es deseable para LoF allele.
