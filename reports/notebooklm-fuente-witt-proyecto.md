# Witt × Organogénesis — Documento fuente para NotebookLM

> **Propósito de este documento:** ser la fuente única que NotebookLM usa para generar un video explicativo del proyecto, dirigido a una persona nueva que se integra al equipo de Latido Médico Mexicano. Está escrito en prosa clara y auto-contenida: cualquier término técnico se explica la primera vez. La regla de honestidad del proyecto se mantiene en todo el texto — se distingue siempre lo que está *medido*, lo que está *afinado pero no resuelto*, y lo que *no está validado*.

---

## 1. Resumen en una idea

Witt es un sistema de inteligencia artificial diseñado para capturar el juicio experto, exponer su razonamiento en cada paso, y crecer con el uso — sin inventar datos. Su primer campo de prueba es un problema real de biología del desarrollo: inducir la formación temprana de un riñón en el pez cebra usando la receta mínima de señales. El proyecto tiene dos mitades: una que ya está viva y funcionando (la de rendición de cuentas), y una naciente que todavía no se construye (la de generación). Este documento explica el proyecto completo y, con más detalle, cómo funciona la mitad que ya opera.

El proyecto pertenece a Latido Médico Mexicano y lo lidera Emmanuel junto con el co-fundador Martín Gleizer. El principio operativo que gobierna cada decisión es de Martín: **"prueba pequeño antes de armar bien"** — ante la duda entre una validación más pequeña y una arquitectura más elegante, se elige siempre la validación pequeña.

---

## 2. Las dos capas: substrato y dominio

La distinción más importante del proyecto, y la que más se confunde, es que ocurren dos cosas a la vez.

**La capa substrato — Witt.** Es infraestructura de inteligencia artificial reutilizable. Su trabajo es capturar el juicio calibrado de una comunidad experta, exponer su razonamiento sin cajas negras, y acumular valor con cada uso. Su horizonte es de cinco a diez años. Su métrica del primer año son cinco pruebas de validación. El nombre "Witt" viene de Wittgenstein: "los límites de mi lenguaje son los límites de mi mundo".

**La capa dominio — Organogénesis.** Es un programa de investigación biológica concreto. Usa modelos computacionales que "podan" redes de señalización del desarrollo — es decir, quitan conexiones redundantes hasta dejar la vía mínima y coherente que forma un órgano. Su prueba de concepto es el pronefros del pez cebra: un riñón embrionario temprano. Su horizonte es de ocho meses a prueba de concepto. Su métrica son cuatro compuertas biológicas.

La jugada no obvia del proyecto es esta: la mayoría de los equipos construyen agentes de IA para *entregar* un resultado biológico. Witt construye agentes que entregan el resultado biológico **y además** generan evidencia de calidad-substrato en cada paso. Los agentes no son el producto final; son instrumentación. Cada acción de un agente es también un dato de calibración, una señal de aprendizaje y una pieza de evidencia.

---

## 3. La tesis del substrato

Un producto elegiría una sola función y construiría una herramienta vertical. Un substrato construye la capacidad subyacente de la que muchas funciones emergen con los años. Witt se compromete al substrato, con cuatro funciones o "pilares" que maduran a lo largo del tiempo: **amplificar** al experto en tiempo real, **transferir** experiencia a practicantes junior, **generar** nuevos hallazgos en colaboración humano-sistema, y **actuar** sobre decisiones rutinarias cuando la calibración lo respalde.

El substrato tiene tres compromisos estructurales: crece con el uso (cada interacción lo extiende), expone su razonamiento en cada paso (toda salida lleva confianza, evidencia y alternativas consideradas), y acumula un foso defensivo a partir del historial acumulado, no de características puntuales.

Es importante decir qué **no** es el substrato: no es una base de datos de hechos (captura juicio bajo incertidumbre), no es un chatbot (produce razonamiento estructurado y citado), no es una herramienta vertical de un solo mercado, y no genera ciencia desde cero — razona bien sobre el conocimiento existente, lo calibra e integra.

De las capacidades técnicas del substrato, la más difícil es la **calibración**: que cuando el sistema dice "ochenta por ciento de confianza", acierte cerca del ochenta por ciento de las veces. Los modelos de lenguaje están mal calibrados de fábrica; la literatura biomédica arranca alrededor de un treinta por ciento descalibrada. Corregirlo requiere métodos estadísticos aplicados después del hecho (regresión isotónica, histogram binning). Por eso la primera contratación senior del proyecto es de calibración e incertidumbre.

---

## 4. La ciencia: el pronefros del pez cebra

El dominio de prueba es inducir un riñón temprano — el pronefros — en el embrión del pez cebra, usando la receta mínima de señales.

Tres conceptos clave. **Organogénesis causal**: modelos que podan redes de señalización sobre-conectadas hasta dejar la vía coherente de formación del órgano. **Pronefros**: el riñón embrionario del pez cebra, cuyas cascadas de señalización (las vías BMP, Nodal y ácido retinoico) están bien caracterizadas. **Tejido chaperón** (chaperone tissue): un parche de tejido transitorio que emite las señales mínimas, en los tiempos correctos, para inducir el programa del órgano en el tejido competente vecino.

¿Por qué pez cebra? Porque es barato, rápido y transparente. Sus embriones son externos y translúcidos, se desarrollan en días, y su genética es manipulable. Es el modelo ideal para "probar pequeño". Una regla dura del proyecto: nunca se experimenta con embriones humanos, en línea con las guías internacionales ISSCR de 2025. El trabajo con pez cebra es investigación, no desarrollo terapéutico.

La pregunta científica central que el sistema atacó fue: ¿qué señal aguas arriba induce el conjunto mínimo de factores de transcripción del pronefros? El estado actual, en silico, es que la cascada `ácido retinoico → osr1 → wnt2b y pax2a` está sustancialmente anclada. Pero la **suficiencia** — es decir, si una señal sola basta para inducir un riñón ectópico — **no está probada**, y solo la puede cerrar un experimento de laboratorio húmedo (ganancia de función) en la Fase II.

---

## 5. Las cuatro compuertas biológicas

Qué cuenta como éxito en la biología se mide con cuatro compuertas. **Inducción**: estructuras renales reproducibles por encima de los controles negativos, en lotes independientes. **Especificidad**: que las estructuras se localicen en el tejido chaperón y sigan el calendario planeado, y no sean crecimiento desordenado inespecífico. **Identidad**: que los marcadores moleculares y la transcriptómica confirmen identidad renal — no un mesodermo genérico. **Parsimonia**: que el programa podado iguale o supere al de más señales, pero con menos pistas, mejor sincronización y un contexto más simple. La parsimonia es la firma del enfoque causal: que menos, bien elegido, baste.

---

## 6. Las fases del proyecto

El proyecto sube por una escalera de validación de tres peldaños. **Fase I** (cero a ocho meses): la prueba de concepto en pez cebra, con un presupuesto de doscientos noventa y siete mil dólares y socios como la instalación de acuáticos del Brigham and Women's Hospital en Boston, el laboratorio Morizane del Massachusetts General Hospital, y proveedores de secuenciación y de cómputo. **Fase II** (año dos): traslación al riñón de ratón y un piloto en sala de cateterismo cardiaco dentro de la red hospitalaria de Latido, que produce la primera evidencia de operación entre dominios distintos. **Fase III** (año tres en adelante): organoides renales derivados de células madre pluripotentes humanas, hacia la medicina regenerativa.

En la Fase I los campos activos son el modelado de sistemas, la embriología y genómica, y la señalización celular. Latido Médico, como empresa matriz, aporta el acceso operativo: el equipo de investigación y desarrollo y la presencia en salas de cateterismo.

---

## 7. Las cinco pruebas de validación del substrato

Junto a la biología corren cinco pruebas que responden una pregunta: ¿el substrato es real y construible con la IA de hoy?

La prueba uno mide la **orquestación y el razonamiento**: si el sistema produce respuestas que un investigador realmente accionaría. La prueba dos mide la **agencia**: si ejecuta flujos de trabajo acotados con puntos de control humanos, sin tomar decisiones irreversibles sin aprobación. La prueba tres mide la **iteración**: si el sistema mejora de forma medible con la retroalimentación a lo largo del año — esta es la afirmación central de defensibilidad de Witt. La prueba cuatro mide la **calibración**: si la confianza está bien ajustada y mejora. La prueba cinco, exploratoria en la Fase I, mide la **operación entre campos**: si el sistema integra conocimiento de un campo biológico distinto.

Una disciplina importante: el proyecto siempre presenta los umbrales *defensivos* como compromiso — por ejemplo, una mejora de al menos cinco puntos porcentuales en la prueba tres, o un error de calibración por debajo de cero coma veinte en la prueba cuatro. Los umbrales ambiciosos se reportan aparte, nunca como promesa. Y la prueba más incómoda es la tres: no mejorar en el año sería el resultado más informativo de las cinco, aunque el más incómodo.

---

## 8. Los dos métodos de operación

Quién dirige el razonamiento es una decisión que se toma en el momento, y la toma el humano. En el **Método dos**, que es el modo por defecto, el humano dirige paso a paso y el sistema instrumenta; cada salida lleva su contrato de evidencia. Es el modo de todo lo que toca biología, presupuesto, cumplimiento o laboratorio. En el **Método uno**, un enjambre de agentes se orquesta con puntos de control humanos, pero solo para tareas de bajo riesgo, reversibles y repetibles, como el monitoreo de literatura o la re-ejecución de procesos ya validados. El Método uno nunca decide algo crítico sin aprobación humana.

---

## 9. Las dos mitades: A viva, B naciente

Un análisis conceptual reformuló a Witt como una máquina de dos mitades.

**La Mitad A — rendición de cuentas.** Es la maquinaria que convierte contenido generado en conocimiento *confiable y trazable*: la fuente de verdad, las compuertas de admisibilidad, la separación estricta entre quien genera y quien verifica, el registro de calibración, y el contrato de afirmaciones causales. Esta mitad está **desplegada y viva**, y es el foco del resto del documento.

**La Mitad B — generación.** Es el motor que *propone* ideas nuevas. Vive **aislada** en un repositorio de código aparte, porque puede arriesgar la estructura de la Mitad A. Lee la fuente de verdad solo en modo lectura, nunca la modifica, y opera solo proponiendo, nunca decidiendo. El motor todavía no se construye.

La razón de mantenerlas separadas es de principio: el diferenciador real de Witt es la capa de rendición de cuentas — la que hace que la inteligencia sea confiable. La regla que une a las dos mitades es una sola: el conocimiento solo entra a la fuente de verdad por un camino que siempre pasa por la aprobación de un humano.

---

## 10. Cómo funciona la Mitad A

### La fuente de verdad: tres capas y una puerta

El corazón de la Mitad A es una base de conocimiento verificada a la que el proyecto llama la "DATA INAMOVIBLE". Se llama inamovible no porque no cambie, sino porque **cada cambio pasa por la aprobación de un humano y queda especificado**. Las lecturas son libres; las modificaciones, nunca automáticas.

Tiene tres capas. La primera es la **guía**: un grafo de conocimiento que conecta documentos, sus fragmentos, sus representaciones numéricas de significado, y entidades verificadas — es el mapa para encontrar. La segunda es el **respaldo**: el dato crudo real; lo público se referencia en su fuente original con una huella de integridad, y lo privado se guarda aparte. La tercera es el **catálogo**: el registro de identificadores verificados y el método, bajo control de versiones. Sobre las tres capas hay una única puerta de consulta que ofrece tres formas de preguntar sin modificar nada: una consulta semántica por significado, una resolución determinista de identificadores, y un acceso directo al dato crudo.

### La búsqueda híbrida

Cuando el sistema busca, combina dos señales. La **léxica** captura la coincidencia exacta — símbolos de genes, identificadores, términos raros. La **semántica** captura el concepto — "qué induce el riñón" encuentra el documento correcto aunque no use esas palabras. Se usan juntas porque la semántica sola pierde los identificadores exactos, y este dominio *es* identificadores; y la léxica sola pierde el concepto. Juntas dan precisión donde importa y alcance en lo que se parece.

### El ciclo que se refuerza solo

El principio más importante de la Mitad A es que "no está en la base" **no es un freno, es un disparador de aprendizaje**. El ciclo funciona así: primero se consulta la base de verdad. Si la evidencia es suficiente — lo decide un umbral de confianza del propio modelo — el sistema responde. Si no es suficiente, el sistema trae evidencia externa de fuentes científicas confiables. Esa evidencia pasa por una auditoría adversarial de tres o más auditores independientes. Si sobrevive, se convierte en una *propuesta*, nunca en una decisión. Un humano la aprueba o la rechaza. Solo si la aprueba, la evidencia se incorpora a la base. Así, cada pregunta que la base no podía responder, tras la aprobación humana, la deja capaz de responderla para siempre. La base crece con el uso: su registro verificado pasó de treinta y dos a setenta y cuatro entradas, y cada salto fue aprobado por un humano.

### Los controles que no son IA

Antes de creerle a un agente, corren controles deterministas y re-ejecutables — reglas, no otra IA. Son baratos, corren primero y bloquean la invención temprano. Nacieron de una corrupción real: en una sesión, quince de dieciséis identificadores de marcadores estaban equivocados porque el modelo los había generado de su memoria. Los controles verifican que todo identificador externo resuelva en la fuente o quede marcado como hueco; que el identificador no solo exista, sino que esté ligado al símbolo correcto; que el método de razonamiento se cite con su fuente exacta y se asigne el agente adecuado a cada tarea; y que una afirmación causal exija una intervención explícita, porque correlacionar no es causar.

### Los auditores

Cuando entra evidencia nueva, la revisan tres o más auditores adversariales e independientes, cada uno intentando refutar por separado, en una votación que reemplaza al sí-o-no de un solo modelo. Una regla dura: quien produjo el trabajo no puede auditarse a sí mismo. Los auditores mezclan familias de modelos e incluso proveedores distintos para lograr independencia real. La prueba de que funciona: la última auditoría de cierre votó revisar los siete resultados que examinó, y atrapó tanto un error de programación real como sobre-afirmaciones — incluidas las del propio equipo que opera el sistema. Un sistema cuyo trabajo es la rendición de cuentas que se defiende incluso de su operador es la prueba más fuerte.

### El contrato de confianza

Toda respuesta del sistema lleva su rastro de confianza: la respuesta directa, la confianza desglosada por cada sub-afirmación (no un número global que oculte lo débil), la evidencia citada con su nivel de verificación, las alternativas que se descartaron, los huecos declarados explícitamente, y el método de razonamiento con los agentes que intervinieron. Una advertencia honesta que el propio sistema hace: el campo que reporta "qué método razoné" es un auto-reporte, no una introspección fiel de lo que ocurrió por dentro.

### El ciclo de auto-mejora

El sistema aprende de cada error. Cada fallo queda registrado, se convierte en una prueba permanente que vigila que ese error no reaparezca, se re-verifica en cada corrida, y avisa antes de la aprobación humana. La lección que más se repite, y que el sistema ya "aprendió a no repetir", es no leer "ausente de una fuente" como "evidencia en contra".

---

## 11. El estado honesto

Aquí la disciplina del proyecto brilla: separa con cuidado tres cosas.

Lo que está **medido**, con matices: la maquinaria corre de extremo a extremo. Existe un baseline de evaluación, la calibración pasó de degenerada a no-degenerada, la base de verdad está íntegra con setenta y cuatro entradas, y el ciclo completo se ejerció.

Lo que está **afinado pero no resuelto**: la biología. La cascada de inducción del pronefros está sustancialmente anclada en silico, pero la suficiencia — si una señal sola induce un riñón — no está probada.

Lo que **no está validado**: toda métrica de "calidad" proviene de un modelo de lenguaje actuando como juez, con muestras pequeñas y una sola medición. Un juez de IA no es verdad de tierra. Por eso nada aquí se llama "validado"; se llama "medido y auditado y corregido".

Lo dice la propia auditoría de cierre, y también un auditor externo independiente que revisó el proyecto sin conocer su contexto: es un diseño disciplinado, pero es una capa de rendición de cuentas alrededor de un resultado científico que aún no existe. El reto real es de proporcionalidad, y demostrar que la maquinaria mejora las respuestas — no construir más maquinaria.

---

## 12. Qué falta y hacia dónde va

La próxima inversión grande no va a más infraestructura, sino a dos cosas. Primero, un conjunto de preguntas de referencia calificado por un experto humano — Martín — que es el ancla de verdad de tierra que ningún modelo ni cómputo sustituye, y es el verdadero cuello de botella. Segundo, el experimento de laboratorio húmedo de ganancia de función en la Fase II, que es lo único que puede cerrar la pregunta de suficiencia de la biología. Hay además una decisión explícita de congelar el crecimiento del substrato hasta que cada control demuestre haber atrapado un error real; el esfuerzo se dirige a medir y a la biología.

---

## 13. Glosario para narración correcta

- **Witt**: la capa substrato; el sistema de IA. Se pronuncia "vit".
- **Organogénesis**: la capa dominio; el programa de biología del desarrollo.
- **Pronefros**: el riñón embrionario temprano del pez cebra.
- **DATA INAMOVIBLE / fuente de verdad**: la base de conocimiento verificada, que solo cambia con aprobación humana.
- **Mitad A**: la mitad de rendición de cuentas, ya desplegada.
- **Mitad B / Conciencia Universal**: la mitad de generación, aislada y todavía sin construir.
- **Calibración**: qué tan bien la confianza declarada corresponde al acierto real.
- **Gate humano / aprobación humana**: el punto obligatorio por el que pasa todo cambio a la fuente de verdad.
- **Latido Médico Mexicano**: la empresa matriz.
- **Martín Gleizer**: co-fundador.

---

*Fin del documento fuente. Todo lo anterior respeta la disciplina de honestidad del proyecto: lo medido, lo afinado y lo no validado están separados y etiquetados como tales.*
