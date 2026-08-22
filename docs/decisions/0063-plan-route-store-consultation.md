# ADR-0063 — El plan rutea: corrida de evidencia vs consulta del sistema (plan v2)

- **Status:** Accepted — 2026-08-22. Origen: feedback del fundador probando producción el mismo día
  del estreno del planner (ADR-0061).
- **Relates:** ADR-0061 (el plan declarado), CLAUDE.md §3 (el filtro de nichos), ADR-0055 (las
  puertas de consulta: /status con auth, /taxonomia).
- **Affects:** `rag_index/query_service/runs.py` (PLAN_TOOL + build_plan + payload; `plan_version` →
  **2**), el gate; en la webapp `Preguntar.tsx` (card de ruta) + `types.ts` + fixtures. Contrato del
  registro intacto (1.4): `route` viaja dentro de `plan.judgment`, que ya viajaba.

## El hallazgo (con el plan real de producción)

Emmanuel preguntó **"dime que tenemos en data inamovible"** en producción. El planner clasificó BIEN el
work-type (*"consulta genérica sobre contenidos de un dataset — pregunta de inventario/estado sin
readout biológico ni tarea analítica definida"*) — pero su juicio **no tenía a dónde ir**: el único
destino del flujo es el pipeline de evidencia, así que el plan marcó FUERA DE ALCANCE (§3) y dejó el
botón de correr apuntando a gastar el panel de 4 jueces en una pregunta que el pipeline no puede
responder desde chunks.

Dos defectos distintos:

1. **De producto:** una pregunta META sobre el sistema ("¿qué tenemos?", versiones, conteos, estado) SÍ
   tiene respuesta en el sistema — vive en las puertas de consulta deterministas (/status, /taxonomia,
   la búsqueda del Rack) — pero nada se lo decía al usuario.
2. **De vocabulario:** marcarla FUERA DE ALCANCE es falso. §3 gobierna **tareas de sustrato**; una
   pregunta de inventario no es una tarea de sustrato ni pretende serlo. *No-aplica ≠ fuera-de-alcance*
   — la misma disciplina de tres estados de todo el contrato.

## Decisión

1. **`judgment.route`** (plan v2): el planner elige entre dos literales — `evidence-run` (pregunta
   biológica respondible con evidencia: el trabajo real del pipeline) y `store-consultation` (pregunta
   sobre el sistema mismo). Como todo en el plan: **el modelo elige el literal; la GUÍA la resuelve la
   tabla** — dónde vive la respuesta es un hecho del sistema, no un juicio.
2. **`route_guidance` resuelta por código** para `store-consultation`: las puertas (Rack — estado,
   búsqueda, resolución; taxonomía/crosswalk; estado del sistema en /consumo) + la nota de costo (el
   pipeline gastaría el panel en algo que no puede responder).
3. **El filtro §3 no aplica a consultas meta:** `scope.in_scope = null` con la nota declarada. La
   bandera FUERA DE ALCANCE queda reservada para lo que sí es: tareas fuera de los seis nichos
   (`in_scope: false`, p. ej. "¿cuál es la capital de Francia?").
4. **Correr sigue disponible** (never-stopper): la card informa y enlaza; el humano decide. Una corrida
   así ejecutada llevará su plan congelado con `route: store-consultation` — la decisión queda
   auditable.
5. **Fix de la clase de bug visual reportada junto con esto:** la `.bandera` del lenguaje es un
   marcador corto (nowrap por diseño del lab); las banderas que cargan oraciones (fuera-de-alcance,
   errores del servidor, juicios fallidos) usan ahora el modificador de capa-app `bandera--parrafo`
   (bloque envolvente). El CSS del lenguaje queda VERBATIM.

## Lo que esta decisión NO construye (nombrado)

La **consulta abierta** — un agente que lea /status + /taxonomia + el manifest y RESPONDA la pregunta
meta en lenguaje natural — sería un flujo nuevo con su propia historia de auditoría (una respuesta de
modelo sin panel no puede parecer una respuesta homologada). Hoy la guía apunta a las puertas
deterministas que ya existen. Si el equipo la pide, es un módulo propio, no un parche a Preguntar.

## Verification

**Offline:** `smoke_run_pipeline.py` → **94/94** (+3: la guía por tabla · `in_scope: null` con
no-aplica ≠ fuera-de-alcance · la ruta en el evento). Webapp → **130/130** (+1: la card con link real a
/rack, sin bandera de fuera-de-alcance, y correr habilitado).

**Con el planner real** (2026-08-22, local contra Neo4j real): la pregunta exacta de producción
*"dime que tenemos en data inamovible"* → `route: store-consultation`, work-type *"Consulta de
inventario del sistema"*, `in_scope: null`, guía con las tres puertas — y el contraste *"Is wt1a
required…"* → `route: evidence-run`, `in_scope: true`. El juicio de ruta discrimina en vivo.
