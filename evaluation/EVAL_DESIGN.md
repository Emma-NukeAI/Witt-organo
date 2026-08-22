# EVAL_DESIGN — disciplina de diseño para las evals del sistema (F5, ADR-0068)

> **Cuándo leer esto:** antes de construir o modificar cualquier eval (el Tapón 5 — evals
> periódicas como gate del código de producción — hereda TODO lo de aquí), y antes de reportar
> cualquier cifra de una eval. Origen: adopción de la disciplina anti-fuga del paper *The Virtual
> Biotech* (Stanford/Zou, bioRxiv 2026.02.23.707551) sobre nuestras reglas ya vigentes
> (ADR-0005/0011/0030/0037). Comparativa completa:
> `reports/2026-08-22_virtual-biotech-vs-witt-organo_comparativa_v1.html`.

## 1 · Anti-fuga (information leakage) — reglas duras

1. **Web tools APAGADAS en preguntas held-out.** Una corrida de eval no puede buscar en la web
   abierta: la respuesta podría estar publicada. Las fuentes permitidas se DECLARAN por eval
   (DI sola; DI + Ruta B acotada a APIs estructuradas, según qué se esté midiendo).
2. **Preferir verdad-terreno POSTERIOR al cutoff del modelo.** El patrón VB que adoptamos: sus
   casos se eligieron con readouts posteriores a enero-2025 y la Breakthrough Designation de
   ifinatamab (ago-2025) validó externamente una hipótesis que el modelo no pudo haber memorizado.
   Nuestra versión: al armar bancos nuevos, priorizar preguntas cuya resolución (paper, corrección
   de ZFIN, dato de wet-lab propio) sea posterior al cutoff del modelo sintetizador — y **registrar
   el cutoff del modelo en el artefacto de la eval** (hoy: el modelo de síntesis se declara en cada
   registro; el cutoff se anota en el banco).
3. **Verificar no-publicación cuando el claim es de novedad.** Si una eval reporta "el sistema
   encontró X que no estaba descrito", se busca X en literatura ANTES de reportarlo (VB lo hizo;
   nosotros ya lo exigimos vía §10 preflight — aquí queda explícito para evals).

## 2 · Validación de instrumento (F4) — para todo lote Método 1

Todo barrido/curación masiva (p. ej. `rag_index/curation/zfin_sweep.py`) entrega SIEMPRE:

- **Muestra aleatoria reproducible** (seed declarado) de n≥20 unidades para concordancia humana,
  con el protocolo de llenado junto al CSV.
- **Concordancia por campo** (no un solo % global cuando los campos difieren — el patrón VB:
  89.7% endpoints primarios / 83.9% secundarios / 92.4% AEs, cada uno con su n).
- **Taxonomía de desacuerdos:** *ambigüedad intrínseca* (la unidad no mapea limpio a la clase)
  vs *error del instrumento* — solo el segundo detiene la propuesta.
- **Lenguaje ADR-0005:** el resultado es *measured*, jamás *validated*; n y denominador viajan
  con la cifra.

## 3 · Reglas ya vigentes que las evals heredan (no se re-legislan aquí)

- EPS medido antes de claims de mejora (ADR-0011) · "aggregate-captured" ≠ "satisfied" (ADR-0030)
  · juez LLM = advisory, ancla = determinista o gold-set humano (ADR-0037/0038) · panel
  multi-familia para audit gates (§7) · poder declarado con n<umbral (ADR-0064).
- Fuente de etiquetas humanas: los ratings M5 (ADR-0064) + el banco de calibración v1.

## 4 · Pendiente que esto desbloquea

El **Tapón 5** (evals periódicas sobre el código de producción) se construye contra este diseño:
`run_held_out.py` migrado al run model + web-off estructural + banco con verdad-terreno
post-cutoff cuando exista volumen de ratings (insumo del Tapón 4).
