"""Merge de las respuestas re-corridas (Workflow 1) al banco_inputs.json + QA anti-fabricación (§7).
Lee el journal.jsonl del workflow, extrae los contratos, verifica que cada ENSDARG resuelva contra
la fuente de verdad, y reemplaza source_answer de las 11 débiles. Construye ia_confidence para las 30."""
import json, os, sys
os.chdir(r'c:\Users\Emmanuel\dev\witt-organogenesis')
sys.path.insert(0, 'analysis/scripts')
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass
from lib import resolve_id

JDIR = sys.argv[1] if len(sys.argv) > 1 else \
    r'C:\Users\Emmanuel\.claude\projects\c--Users-Emmanuel-dev-witt-organogenesis\b49314fd-484f-481a-baa2-c396e557fdb4\subagents\workflows\wf_526cd616-b6a'

# 1. extraer resultados del journal
results = {}
for line in open(os.path.join(JDIR, 'journal.jsonl'), encoding='utf-8').read().splitlines():
    d = json.loads(line)
    if d.get('type') == 'result' and isinstance(d.get('result'), dict):
        r = d['result']
        if r.get('id'):
            results[r['id']] = r
print('re-corridas extraídas:', sorted(results.keys()), '=', len(results))

# 2. QA anti-fabricación: cada ENSDARG afirmado debe resolver (o venir marcado ensembl_rest con raw)
print('\n=== QA anti-fabricación (§7) ===')
for qid, r in sorted(results.items()):
    binds = r.get('identifier_bindings', [])
    bad = []
    for b in binds:
        ens = (b.get('ensdarg') or '').strip()
        if not ens:
            continue
        rec = resolve_id.resolve(ens)
        if rec is resolve_id.NOT_FOUND:
            # no está en el store: aceptable SOLO si el agente lo marcó verificado por ensembl_rest
            via = (b.get('verified_via') or '').lower()
            if 'ensembl' not in via:
                bad.append(f"{b.get('symbol')}={ens} (via={via or '?'})")
    flag = '  [!] CAUSAL-PRUNER (human gate)' if r.get('causal_pruner_flag') else ''
    status = 'OK' if not bad else 'REVISAR: ' + '; '.join(bad)
    print(f"  {qid} conf={r.get('confidence')} nIDs={len(binds)} -> {status}{flag}")

# 3. merge al banco_inputs.json
bank = json.load(open('evaluation/gold_set/work/banco_inputs.json', encoding='utf-8'))
RICH_CONF = {'Q26': 0.87, 'Q08': 0.82, 'Q07': 0.55, 'Q24': 0.60, 'Q16': 0.55}  # de la prosa del GoldSet
for q in bank['questions']:
    qid = q['id']
    if qid in results:
        r = results[qid]
        q['source_answer'] = {
            'answer': r.get('direct_answer', ''),
            'confidence': r.get('confidence'),
            'outcome': 'rerun_agentic',
            'gap_flags': r.get('gap_flags', []),
            'framework': r.get('framework_applied'),
            'identifier_bindings': r.get('identifier_bindings', []),
            'causal_pruner_flag': r.get('causal_pruner_flag', False),
            'improved_over_baseline': r.get('improved_over_baseline', ''),
            'provenance': 're-corrida agéntica Level-2 (18-jul): resolve_id + Ensembl REST, honesty-gated',
        }
        q['ia_confidence'] = r.get('confidence')
    elif q['bucket'] == 'rich_reuse':
        q['ia_confidence'] = RICH_CONF.get(qid)
    else:  # baseline_reuse
        q['ia_confidence'] = q['source_answer'].get('confidence')

json.dump(bank, open('evaluation/gold_set/work/banco_inputs.json', 'w', encoding='utf-8'),
          ensure_ascii=False, indent=2)

# resumen de confianzas
print('\n=== ia_confidence por bucket ===')
for b in ('rich_reuse', 'rerun', 'baseline_reuse'):
    qs = [(q['id'], q.get('ia_confidence')) for q in bank['questions'] if q['bucket'] == b]
    print(f"  {b}: {qs}")
print('\nmerge OK -> banco_inputs.json actualizado')
