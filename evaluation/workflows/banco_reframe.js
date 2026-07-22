export const meta = {
  name: 'banco-reframe-es',
  description: 'Reformula las 30 preguntas técnicas del banco a español llano (nivel equipo médico) + "por qué importa" + un resumen FIEL de la respuesta real del sistema. Los identificadores técnicos (genes, ENSDARG, frameworks) se quedan en inglés (CLAUDE.md bilingüismo). No inventa nada: el resumen es fiel a la respuesta de origen.',
  phases: [{ title: 'Reformular ES', detail: 'agente por pregunta: pregunta llana + por qué importa + resumen fiel' }],
}

const IDS = Array.isArray(args) ? args : (function () {
  const out = []
  for (let i = 1; i <= 30; i++) out.push('Q' + String(i).padStart(2, '0'))
  return out
})()

const SCHEMA = {
  type: 'object',
  properties: {
    id: { type: 'string' },
    tema: { type: 'string', description: 'Etiqueta de tema corta en español (2-5 palabras), p.ej. "Marcadores de segmentos del riñón".' },
    pregunta_es: { type: 'string', description: 'La pregunta reformulada en español llano que un médico entiende. Identificadores técnicos (genes, ENSDARG, nombres de framework, hpf) SE QUEDAN en inglés/nomenclatura. Directa, una sola pregunta.' },
    por_que_importa: { type: 'string', description: '1-2 frases: por qué esta pregunta importa para el proyecto (riñón embrionario del pez cebra / estrategia de inducción). Tono llano, sin marketing.' },
    resumen_es: { type: 'string', description: 'Resumen FIEL de la respuesta real del sistema en 2-4 frases: (1) qué respondió, (2) qué tan seguro estaba / si se abstuvo, (3) el vacío o límite principal. PROHIBIDO agregar afirmaciones que no estén en la respuesta de origen. Si la respuesta se abstuvo o es débil, dilo con honestidad.' },
  },
  required: ['id', 'tema', 'pregunta_es', 'por_que_importa', 'resumen_es'],
}

function prompt(id) {
  return [
    'Eres editor científico bilingüe del proyecto Organogénesis × Witt (riñón embrionario del pez cebra — pronephros). Reformulas UNA pregunta técnica para que un equipo médico (Latido Médico, español) pueda leerla y calificarla, y resumes con FIDELIDAD la respuesta real que dio el sistema de IA.',
    '',
    'PASO 1 — lee la pregunta y su respuesta real. Corre en Bash:',
    "  python -c \"import json; d=json.load(open('evaluation/gold_set/work/banco_inputs.json',encoding='utf-8')); q=[x for x in d['questions'] if x['id']=='" + id + "'][0]; print('Q:',q['technical_q']); print('TIPO:',q['type']); print('CONF:',q['source_answer'].get('confidence'),'OUTCOME:',q['source_answer'].get('outcome'),'PROV:',q['source_answer'].get('provenance')); print('GAPS:',q['source_answer'].get('gap_flags')); print('---RESPUESTA REAL---'); print(q['source_answer']['answer'])\"",
    '',
    'PASO 2 — produce el esquema:',
    '  · tema: etiqueta corta en español.',
    '  · pregunta_es: la MISMA pregunta, en español llano y directo. NO la simplifiques al punto de cambiar su sentido científico. Los símbolos de gen (pax2a, slc12a1…), ENSDARG, nombres de framework, y las ventanas temporales (hpf) se quedan tal cual.',
    '  · por_que_importa: 1-2 frases, por qué importa para el proyecto. Sin lenguaje de marketing.',
    '  · resumen_es: 2-4 frases FIELES a la respuesta real. Incluye qué respondió, qué tan seguro estaba (o si se abstuvo por falta de evidencia), y el límite/vacío principal. Si la respuesta real es una abstención honesta ("no puedo confirmarlo con esta evidencia"), el resumen debe decirlo así — NO inventes una respuesta que el sistema no dio.',
    '',
    'REGLA DURA: el resumen no agrega ninguna afirmación científica que no esté en la respuesta de origen. Eres fiel, no generoso. id = "' + id + '".',
  ].join('\n')
}

const results = await pipeline(
  IDS,
  (id) => agent(prompt(id), { label: 'reframe:' + id, phase: 'Reformular ES', schema: SCHEMA, agentType: 'general-purpose' }),
)

return results.filter(Boolean)
