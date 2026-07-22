# Banco de calibración v1 — LATIMED × Witt

Instrumento para **calibrar dos cosas a la vez**, con el juicio de 4 expertos de Latido Médico:

- **EJE INPUT — calibrar las PREGUNTAS** (lo nuevo): ¿son objetivas? ¿están en contexto con el proyecto? ¿qué tan específicas? La idea que planteaste: *la información es totalmente distinta entre una pregunta genérica y una muy específica* — este banco lo mide.
- **EJE OUTPUT — calibrar las RESPUESTAS** (lo del GoldSet que ya presentaste): ¿la respuesta de la IA es correcta y útil? ¿la usarías para un experimento real?

30 preguntas reales del proyecto (riñón embrionario del pez cebra), cada una con la **respuesta real del sistema**.

---

## Archivos

| Archivo | Qué es | Quién lo toca |
|---|---|---|
| `banco_calibracion_v1.csv` | **El instrumento llenable.** 30 filas: pregunta + respuesta + columnas de calificación en blanco. | Los 4 revisores (en Google Sheets) |
| `banco_llave_v1.json` | **Llave oculta.** Etiquetas intencionales (nuestra hipótesis de especificidad/contexto/objetividad) + confianza que declaró la IA. **Los revisores NO la ven** (calificación a ciegas). | Solo tú / el script |
| `../scripts/score_calibration.py` | El **test de calibración** (determinista). Ingiere las hojas llenas y computa todo. | Tú, al final |
| `README_banco_calibracion.md` | Este archivo. | — |

---

## Cómo lo despliegas (la opción más sencilla: Google Sheets)

1. Sube `banco_calibracion_v1.csv` a Google Drive → *Abrir con Google Sheets*. (O en una hoja nueva: *Archivo → Importar → Subir*.)
2. Las primeras columnas (`id`, `tema`, `pregunta`, `por_que_importa`, `resumen_respuesta_ia`, `respuesta_completa`) son de **solo lectura** — pídeles que no las editen. Puedes protegerlas (*Datos → Proteger hojas y rangos*).
3. **Una pestaña por revisor:** duplica la pestaña 4 veces (clic derecho en la pestaña → *Duplicar*), renómbralas con el nombre de cada médico. Cada quien llena sus 30 filas en su pestaña. *(Alternativa: una sola pestaña con la columna `revisor` y que cada quien agregue sus filas; el script acepta ambos formatos.)*
4. Comparte el link con permiso de edición a los 4. Se llena en línea; tú le das seguimiento en vivo. Nada se pierde (a diferencia de un HTML).
5. Para las columnas de calificación, conviene poner **validación de datos → lista desplegable** con los valores de abajo (evita erratas y te ahorra limpieza).

### Las columnas que llenan (y sus valores)

**Calificar la PREGUNTA (input):**

| Columna | Valores | Qué preguntamos |
|---|---|---|
| `P_objetiva` | `Objetiva` · `Parcial` · `Vaga` | ¿Admite una respuesta verificable/acotada, o es abierta/de opinión? |
| `P_en_contexto` | `En foco` · `Exploratoria` · `Fuera de alcance` | ¿Es relevante al desarrollo del proyecto? |
| `P_especificidad` | `Genérica` · `Intermedia` · `Muy específica` | ¿Qué tan específica es? |
| `P_comentario` | texto libre | ¿Cómo la reformularías para que el sistema la responda mejor? |

**Calificar la RESPUESTA (output):**

| Columna | Valores | Qué preguntamos |
|---|---|---|
| `R_correcta_util` | `Sí sólida` · `Más o menos` · `No` | ¿La respuesta es correcta y útil? |
| `R_que_falta` | texto libre | ¿Qué le falta o qué corregirías? |
| `R_la_usarias` | `Sí` · `No` | ¿La usarías para planear un experimento real? |

> **Importante:** los revisores califican **a ciegas** — no ven la confianza que declaró la IA. Eso lo compara el script (confianza de la máquina vs juicio humano). Así el juicio experto no queda "anclado" por el número de la IA.

---

## Cómo corres el test de calibración (al final)

Cuando estén llenas, exporta cada pestaña a CSV (*Archivo → Descargar → CSV*) a una carpeta, por ejemplo `evaluation/gold_set/respuestas/`, y corre:

```bash
python evaluation/scripts/score_calibration.py \
    --key   evaluation/gold_set/banco_llave_v1.json \
    --sheets evaluation/gold_set/respuestas/ \
    --out   reports/calibracion_banco_20260718.json
```

El script (100% determinista, sin depender del modelo) produce:

1. **Cobertura** — cuánto se llenó.
2. **Distribuciones** por eje (input y output).
3. **Acuerdo inter-revisor** — ¿los 4 expertos coinciden? Si no coinciden en un eje, la rúbrica de ese eje necesita afinarse.
4. **Diseño vs percepción experta** — ¿nuestras etiquetas intencionales de especificidad/contexto/objetividad coinciden con lo que percibe el experto? (valida cómo estamos etiquetando las preguntas).
5. **INPUT→OUTPUT** (tu hipótesis) — correlación de rangos: ¿preguntas más específicas / en-foco / objetivas ⇒ mejores respuestas?
6. **Calibración anclada en humanos** (ADR-0037) — la confianza que declaró la IA vs el juicio experto: qué preguntas quedaron **sobre-confiadas** (la IA se declaró más segura de lo que el experto valida) y cuáles **sub-confiadas**. Este es el gold-set humano que al proyecto le hacía falta.

---

## Nota de honestidad sobre las respuestas (partición híbrida)

Las 30 respuestas son reales, de tres orígenes (columna `origen` en la llave):

- **5 ricas** (reuso del GoldSet que presentaste — corridas agénticas dedicadas).
- **11 re-corridas hoy** por el camino agéntico Level-2 (verificación de IDs con herramientas + biología establecida, honesty-gated), porque su baseline era delgado.
- **14 del baseline** DI-only (11-jul) que ya salieron sólidas.

Ninguna respuesta usa identificadores de gen "de memoria": todo ENSDARG se resolvió contra la fuente de verdad (`resolve_id` / Ensembl). Algunas respuestas se **abstienen honestamente** ("no puedo confirmarlo con esta evidencia") — eso es válido y es justo lo que el eje de calibración mide: ¿el experto coincide en que la confianza debía ser baja?
