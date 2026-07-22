"""Ensambla el instrumento final: banco_calibracion_v1.csv (llenable, Google-Sheets-ready) + la
llave oculta banco_llave_v1.json, desde banco_inputs.json (mergeado) + los resultados de reformulación
(Workflow 2). 100% determinista."""
import json, os, sys, csv
os.chdir(r'c:\Users\Emmanuel\dev\witt-organogenesis')
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

W2_JDIR = sys.argv[1] if len(sys.argv) > 1 else \
    r'C:\Users\Emmanuel\.claude\projects\c--Users-Emmanuel-dev-witt-organogenesis\b49314fd-484f-481a-baa2-c396e557fdb4\subagents\workflows\wf_14a1c00e-e22'

bank = json.load(open('evaluation/gold_set/work/banco_inputs.json', encoding='utf-8'))

# reframe results
reframe = {}
for line in open(os.path.join(W2_JDIR, 'journal.jsonl'), encoding='utf-8').read().splitlines():
    d = json.loads(line)
    if d.get('type') == 'result' and isinstance(d.get('result'), dict):
        r = d['result']
        if r.get('id'):
            reframe[r['id']] = r
print('reformulaciones extraídas:', len(reframe), sorted(reframe.keys()))
missing = [q['id'] for q in bank['questions'] if q['id'] not in reframe]
if missing:
    print('  ADVERTENCIA faltan reformulaciones:', missing)

# --- CSV llenable ---
COLS = ['id', 'tema', 'pregunta', 'por_que_importa', 'resumen_respuesta_ia', 'respuesta_completa',
        'P_objetiva', 'P_en_contexto', 'P_especificidad', 'P_comentario',
        'R_correcta_util', 'R_que_falta', 'R_la_usarias', 'revisor']
rows = []
key_qs = []
BUCKET_ES = {'rich_reuse': 'GoldSet (rica)', 'rerun': 're-corrida agéntica', 'baseline_reuse': 'baseline DI-only'}
for q in sorted(bank['questions'], key=lambda x: int(x['id'][1:])):
    qid = q['id']
    rf = reframe.get(qid, {})
    full = (q['source_answer'].get('answer') or '').strip()
    rows.append({
        'id': qid,
        'tema': rf.get('tema', ''),
        'pregunta': rf.get('pregunta_es', q['technical_q']),
        'por_que_importa': rf.get('por_que_importa', ''),
        'resumen_respuesta_ia': rf.get('resumen_es', ''),
        'respuesta_completa': full,
        'P_objetiva': '', 'P_en_contexto': '', 'P_especificidad': '', 'P_comentario': '',
        'R_correcta_util': '', 'R_que_falta': '', 'R_la_usarias': '', 'revisor': '',
    })
    key_qs.append({
        'id': qid,
        'tema': rf.get('tema', ''),
        'origen': BUCKET_ES[q['bucket']],
        'bucket': q['bucket'],
        'ia_confidence': q.get('ia_confidence'),
        'intended_labels': q['intended_labels'],
        'causal_pruner_flag': q['source_answer'].get('causal_pruner_flag', False),
        'niche': q.get('niche'), 'type': q.get('type'), 'system': q.get('system'),
    })

with open('evaluation/gold_set/banco_calibracion_v1.csv', 'w', encoding='utf-8', newline='') as f:
    w = csv.DictWriter(f, fieldnames=COLS)
    w.writeheader()
    w.writerows(rows)
print('escrito -> evaluation/gold_set/banco_calibracion_v1.csv', f'({len(rows)} filas)')

key = {'set_version': 'banco_calibracion_v1', 'generated': '2026-07-18',
       'note': 'LLAVE OCULTA — no compartir con los revisores. Etiquetas intencionales (hipótesis de diseño) + confianza declarada por la IA. La consume score_calibration.py.',
       'label_scales': {
           'objetividad': 'objetiva | parcial | abierta',
           'contexto': 'en_foco | exploratoria | fuera_de_alcance',
           'especificidad': 'generica | intermedia | especifica'},
       'questions': key_qs}
json.dump(key, open('evaluation/gold_set/banco_llave_v1.json', 'w', encoding='utf-8'),
          ensure_ascii=False, indent=2)
print('escrito -> evaluation/gold_set/banco_llave_v1.json')

# resumen
from collections import Counter
print('\n=== resumen del banco ===')
print('origen:', dict(Counter(k['origen'] for k in key_qs)))
print('especificidad intencional:', dict(Counter(k['intended_labels']['especificidad'] for k in key_qs)))
print('contexto intencional:', dict(Counter(k['intended_labels']['contexto'] for k in key_qs)))
print('objetividad intencional:', dict(Counter(k['intended_labels']['objetividad'] for k in key_qs)))
print('causal_pruner (human gate):', [k['id'] for k in key_qs if k['causal_pruner_flag']])
confs = [k['ia_confidence'] for k in key_qs if isinstance(k['ia_confidence'], (int, float))]
print(f'ia_confidence: n={len(confs)} min={min(confs)} max={max(confs)} mean={round(sum(confs)/len(confs),3)}')
