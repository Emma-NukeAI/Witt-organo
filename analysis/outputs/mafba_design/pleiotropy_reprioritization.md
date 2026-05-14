# Re-priorización de candidatos novel basada en pleiotropy

**Análisis:** % cells expressing per gene en Wagner 14-24 hpf, en pronephros clusters (69, 105, 109, 187) vs todos los demás clusters.
**Métrica clave:** Specificity ratio = pronephros_avg / non_pronephros_max. >= 1.5 = LOW pleiotropy risk; 0.7-1.5 = MEDIUM; < 0.7 = HIGH.

## Candidatos NOVEL ranked por specificity

| Gene | Tier | Pronefros avg % | Non-PN max % | Specificity ratio | Risk |
|------|------|-----------------|--------------|-------------------|------|
| `hoxb8a` | T3 | 41.5% | 52.9% | 0.785 | MEDIUM |
| `sall1a` | T3 | 49.8% | 100.0% | 0.498 | HIGH |
| `hipk2` | T3 | 12.7% | 28.6% | 0.443 | HIGH |
| `mafba` | T1 | 14.5% | 100.0% | 0.145 | HIGH |
| `ripply1` | T2 | 8.6% | 66.2% | 0.129 | HIGH |
| `prox1a` | T3 | 4.3% | 92.3% | 0.046 | HIGH |

## Candidatos VALIDADOS (referencia)

| Gene | Tier | Pronefros avg % | Non-PN max % | Specificity ratio | Risk |
|------|------|-----------------|--------------|-------------------|------|
| `pax2a` | T1 | 83.0% | 88.4% | 0.939 | MEDIUM |
| `wt1a` | T2 | 0.0% | 12.5% | 0.0 | N/A |
| `wt1b` | T2 | 0.0% | 28.5% | 0.0 | N/A |
| `sim1a` | T3 | 0.0% | 23.3% | 0.0 | N/A |
| `dzip1l` | T3 | 7.3% | 31.2% | 0.233 | HIGH |
| `tbx2b` | bonus | 14.5% | 80.4% | 0.18 | HIGH |

## Recomendación operativa

Basada en specificity ratio (mayor = más pronephros-específico), el orden re-priorizado de candidatos novel para experimento KO global es:

1. **`hoxb8a`** ~ (SR=0.785, risk=MEDIUM)
2. **`sall1a`** ⚠️ (SR=0.498, risk=HIGH)
3. **`hipk2`** ⚠️ (SR=0.443, risk=HIGH)
4. **`mafba`** ⚠️ (SR=0.145, risk=HIGH)
5. **`ripply1`** ⚠️ (SR=0.129, risk=HIGH)
6. **`prox1a`** ⚠️ (SR=0.046, risk=HIGH)

**Implicación:** el ranking original priorizaba `mafba` por familia bZIP + Tier 1. Pero en términos de pleiotropy (qué tan limpio sería un KO global), el nuevo top puede no ser mafba.