# Conectarte a la DATA INAMOVIBLE — guía para el equipo de Latido

Esta guía te deja **consultando y revisando la DATA INAMOVIBLE** desde tu computadora, con las mismas facultades que Emmanuel (preguntar, resolver, ver datos crudos e ingestar). **No necesitas saber programar** — un asistente (Claude Code) hace lo técnico por ti. Son 4 pasos.

---

## Antes de empezar (una sola vez)
Necesitas **Claude Code** instalado (el asistente). Si no lo tienes, pídele a Emmanuel el instalador y el link. Nada más — lo demás se instala solo en el Paso 3.

---

## Paso 1 — Baja el proyecto a una carpeta de ruta CORTA
- Descarga la carpeta del proyecto (Emmanuel te la comparte por Drive o GitHub) y descomprímela.
- Ponla en una **ruta corta**. En Windows, ideal: `C:\dev\Witt-organo`. En Mac: tu carpeta de usuario.
- ⚠️ **Windows — esto importa:** que la ruta sea corta. Si la dejas en `Descargas` dentro de carpetas muy anidadas, la parte "inteligente" (semántica) falla en silencio. `C:\dev\Witt-organo` evita el problema.

## Paso 2 — Agrega tus llaves
- En el **Drive del equipo**, descarga el archivo **`deploy.env`**.
- Ponlo **dentro** de la carpeta del proyecto (la misma del Paso 1). No lo abras ni lo edites.
- 🔒 **Nunca lo compartas fuera del equipo** — son las llaves de acceso al sistema.

## Paso 3 — Abre Claude Code en esa carpeta y pega este mensaje
Abre Claude Code apuntando a la carpeta del proyecto y **pega esto tal cual**:

```
Hola. Soy del equipo de Latido y quiero dejar configurada la DATA INAMOVIBLE en esta
computadora. Por favor hazlo por mí y explícame cada resultado en lenguaje simple, no técnico.
Pídeme permiso si necesitas correr algo y espera mi "sí":

1. Confirma que estás en la carpeta correcta del proyecto: debe existir el archivo
   rag_index/mcp_server/smoke_rag.py. Si no existe, dime que abra Claude Code dentro de la
   carpeta del proyecto y detente.
2. Revisa si existe .secrets/deploy.env. Si NO existe, busca un archivo llamado deploy.env
   (o deploy.env.txt) en esta carpeta o en mi carpeta de Descargas; si lo encuentras, crea la
   carpeta .secrets y muévelo ahí como .secrets/deploy.env. Si no lo encuentras, dime que
   descargue "deploy.env" del Drive del equipo, lo ponga en esta carpeta, y detente.
3. Revisa si el comando "uv" está instalado. Si no, instálalo
   (Windows: powershell -c "irm https://astral.sh/uv/install.ps1 | iex" ;
    Mac/Linux: curl -LsSf https://astral.sh/uv/install.sh | sh).
4. Corre: uv sync --locked   (instala lo necesario; la primera vez tarda 1-2 min).
5. Prueba mis llaves y la conexión a la DATA INAMOVIBLE:
   uv run --locked python rag_index/mcp_server/smoke_rag.py
6. Dime en lenguaje simple si dio "6/6 PASS" (todo funciona) o exactamente qué falló.
   Si falló "semantic score alto", casi siempre es que la carpeta quedó en una ruta muy
   larga (Paso 1) o que falta/está mal el deploy.env (Paso 2).
7. Si todo salió bien, dime que ya puedo empezar a preguntarle a la DATA INAMOVIBLE, y que
   si aparece una pregunta para aprobar el conector "data-inamovible", le diga que sí.

Regla: NO borres ni modifiques .secrets/deploy.env; solo úsalo.
```

Claude instalará lo que falte, colocará tus llaves y probará que todo funcione. Si te pide permiso para correr algo, dile que **sí**. Al final te dirá **"✅ Todo listo (6/6)"**.

## Paso 4 — Aprueba la conexión (la primera vez)
Claude te preguntará una vez si apruebas el conector **`data-inamovible`**. Dile que **sí**. Ya está — pregúntale lo que necesites; para verificar en cualquier momento puedes pedirle: *"corre el health de la DATA INAMOVIBLE"*.

---

## Aportar una fuente nueva (opcional) — así crece el conocimiento del equipo

Cuando en tus preguntas encuentres una fuente valiosa (un artículo, un dataset), puedes **agregarla a la DATA INAMOVIBLE** y **queda disponible para todo el equipo al instante** — nadie tiene que volver a bajar ni configurar nada. Tú decides qué se agrega (ese es el control humano); el asistente hace lo técnico.

Abre Claude Code en la carpeta del proyecto y **pega esto tal cual**:

```
Hola. Soy del equipo de Latido y quiero AGREGAR una fuente nueva a la DATA INAMOVIBLE,
para que quede disponible para todo el equipo. Hazlo por mí, explícame en lenguaje simple, y
pídeme confirmación antes de agregar nada. Reglas: YO apruebo (tú no agregas solo); nunca
inventes IDs de genes. Nota técnica: antes de correr los comandos, asegúrate de que las
variables de .secrets/deploy.env estén cargadas en el entorno de la forma correcta para este
sistema operativo (las versiones nuevas de los scripts ya lo hacen solas; si no, cárgalas tú).

1. Confirma que estamos en la carpeta del proyecto (debe existir rag_index/graphrag/ingest.py)
   y que existe .secrets/deploy.env. Si falta algo, dímelo y detente.
2. Pregúntame: (a) el enlace (URL público) de la fuente —p. ej. un artículo de Europe PMC /
   PubMed, o un dataset de GEO—, y (b) un nombre corto para identificarla.
3. Elige la fuente registrada según el enlace: europepmc/pubmed -> EuropePMC ;
   ncbi.nlm.nih.gov/geo -> GEO_NCBI ; si no estás seguro, pregúntame.
4. Prepara el registro (esto todavía NO lo agrega, solo lo propone):
   uv run --locked python analysis/scripts/lib/add_dataset.py --name "<nombre>" --source-db <FUENTE> --url "<URL>" --download
   Explícame en simple: qué nicho propuso, cuántos genes verificados encontró, y si hay genes
   que NO están en el store (esos quedan en cuarentena, no se inventan; anótalos para Emmanuel).
5. Muéstrame el resumen y pregúntame: "¿lo agrego a la DATA INAMOVIBLE?". Espera mi "sí".
6. Si digo que sí, apruébalo e ingesta (esto SÍ lo mete a Neo4j, disponible para todos):
   uv run --locked python analysis/scripts/lib/approve_dataset.py <CORPUS-id> --by "<mi nombre>"
7. Verifica que ya quedó en vivo:
   uv run --locked python rag_index/mcp_server/cli.py query "<tema de la fuente>" -k 3
   Dime si aparece y confírmame "✅ Agregado y disponible para el equipo".

No hagas git push ni borres nada. Si algo falla, cópiame el error para mandárselo a Emmanuel.
```

Qué esperar: el asistente te enseña un resumen (nicho + genes verificados), tú das el "sí", y en segundos queda en Neo4j para todos. Si un gen del artículo **no está aún en el store**, no se inventa: queda marcado para que Emmanuel lo verifique y lo añada (así el sistema nunca mete datos sin verificar).

---

## ¿Algo falló?
Copia lo que te dijo Claude y mándaselo a Emmanuel. Las dos causas más comunes:
1. **Ruta larga** (Paso 1) → muévela a `C:\dev\Witt-organo`.
2. **Falta el `deploy.env`** (Paso 2) → descárgalo del Drive y ponlo en la carpeta del proyecto.

> Guía técnica completa (para colaboradores/desarrolladores): `ONBOARDING.md` y `rag_index/mcp_server/README.md`.
