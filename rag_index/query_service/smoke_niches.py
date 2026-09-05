"""
smoke_niches.py — gate de LOS DOS EJES DE NICHO (2026-09-05, decisión del fundador:
"catálogo medido + panel para el resto").

Fija la separación que da sentido al diseño: el eje del CATÁLOGO es medición (se lee de fichas
con gate humano) y el del PANEL es juicio (cuatro jueces sobre la respuesta). Se guardan aparte
y el juicio jamás tapa a la medición.

Del CATÁLOGO (niche_catalog):
  · la COBERTURA viaja siempre — un reparto sobre 1 de 7 ítems leído sin denominador se entiende
    como el reparto de la corrida entera (el defecto que ADR-0075 corrigió en `por_nicho`)
  · primario y secundario se cuentan APARTE: fundirlos borraría la distinción del catalogador
  · un chunk hereda la ficha de su registro (`CORPUS-x#c012` -> `CORPUS-x`)
  · lo no catalogado (PMIDs, resoluciones de identidad) se DECLARA con su tipo, no se rellena
  · los dos ejes se leen por separado: RN* jamás se infiere de N* ni al revés (ADR-0018)

Del PANEL (composite_auditor):
  · la TABLA de nichos viaja en el system prompt — juzgar contra una tabla que el modelo nunca
    vio fabrica coincidencias (mismo principio que agent_matrix.digest())
  · el consenso son CONTEOS, jamás un ganador: cuatro opiniones no hacen un hecho
  · el juez CAÍDO se excluye y su ausencia queda en n_classified < n_valid, nunca se reparte
  · un juez que no emite el campo "no clasificó" — distinto de "clasificó vacío"

NO-SPEND: jueces INYECTADOS, catálogo leído del repo. Sin red, sin modelo.
Uso:  python smoke_niches.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "analysis" / "scripts"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import niche_catalog  # noqa: E402
from lib import agent_matrix, composite_auditor  # noqa: E402

CHECKS = []


def check(name, cond, detail=""):
    CHECKS.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + name + (f"  -> {detail}" if detail else ""))


# ── el catálogo existe y trae los DOS ejes ─────────────────────────────────────────────────────
cat = niche_catalog._catalogo()
check("el catálogo del corpus se lee y trae fichas", len(cat) > 0, f"n_fichas={len(cat)}")
una = next(iter(cat.values()))
check("cada ficha trae los DOS ejes, catalogados aparte",
      isinstance(una.get("axis_data_niche"), dict)
      and isinstance(una.get("axis_scientific_domain"), dict),
      f"ejes={sorted(k for k in una if k.startswith('axis_'))}")
check("las fichas pasaron por gate HUMANO de categorización (por eso esto es medición)",
      any(g.get("gate") == "categorization" and g.get("status") == "approved"
          for g in (una.get("approval_chain") or [])),
      f"approval_chain={una.get('approval_chain')}")

# ── la evidencia REAL es mezcla: con ficha y sin ficha ─────────────────────────────────────────
# Reproduce la forma de la corrida 9b3140ab: 1 chunk del corpus + PMIDs + resolución de identidad.
EVIDENCIA = [
    {"id": "aldh1a2 -> ENSDARG00000053493", "kind": "store-resolution"},
    {"id": "ZFIN:ZDB-GENE-011010-3", "kind": "di-record"},
    {"id": "PMID:21761484", "kind": "paper"},
    {"id": "PMID:17953490", "kind": "paper"},
    {"id": "CORPUS-2026-0005#c003", "kind": "di-chunk"},
    {"id": "PMID:25078510", "kind": "paper"},
]
r = niche_catalog.niches_of_evidence(EVIDENCIA)

check("la COBERTURA viaja con el reparto (sin denominador, 1 de 6 se lee como el todo)",
      r["n_evidence"] == 6 and r["n_catalogued"] == 1 and r["coverage"] == "1 de 6",
      f"coverage={r['coverage']}")
check("el chunk hereda la ficha de su registro (CORPUS-x#c003 -> CORPUS-x)",
      r["catalogued_ids"] == ["CORPUS-2026-0005"], f"ids={r['catalogued_ids']}")
check("lo NO catalogado se declara con su tipo, jamás se rellena",
      len(r["uncatalogued"]) == 5
      and {u["kind"] for u in r["uncatalogued"]} == {"store-resolution", "di-record", "paper"},
      f"sin_ficha={len(r['uncatalogued'])}")
check("el eje de DATO se lee de la ficha (RN*)",
      r["data_niches"]["primary"] and all(c.startswith("RN") for c in r["data_niches"]["primary"]),
      f"data={r['data_niches']}")
check("el eje de DOMINIO se lee de la ficha (N*) — jamás inferido del otro eje",
      r["domain_niches"]["primary"] and all(c.startswith("N") and not c.startswith("RN")
                                            for c in r["domain_niches"]["primary"]),
      f"dominio={r['domain_niches']}")
check("primario y secundario se cuentan APARTE (fundirlos borra la distinción de la ficha)",
      set(r["domain_niches"]["primary"]) & set(r["domain_niches"]["secondary"]) == set()
      and r["domain_niches"]["secondary"],
      f"primary={r['domain_niches']['primary']} secondary={r['domain_niches']['secondary']}")
check("el reparto se declara CLASE medición", r["class"] == "medicion")

vacio = niche_catalog.niches_of_evidence([])
check("sin evidencia: cobertura 0 de 0, sin nichos inventados",
      vacio["coverage"] == "0 de 0" and not vacio["domain_niches"]["primary"])
solo_papers = niche_catalog.niches_of_evidence([{"id": "PMID:1", "kind": "paper"}])
check("evidencia SIN ficha: 0 de 1 y nichos vacíos — el vacío es honesto, no un cero medido",
      solo_papers["coverage"] == "0 de 1" and not solo_papers["domain_niches"]["primary"])

# ── el panel: la tabla viaja, y el consenso son conteos ────────────────────────────────────────
tabla = composite_auditor._niche_table()
check("la TABLA de nichos viaja al juez (juzgar contra una tabla no vista fabrica códigos)",
      all(c in tabla for c in agent_matrix.NICHES) and "RN*" in tabla,
      f"tabla[:70]={tabla[:70]!r}")
check("el esquema del juez pide domain_niches y NO lo hace obligatorio (no clasificar ≠ clasificar mal)",
      "domain_niches" in composite_auditor.VERDICT_TOOL["input_schema"]["properties"]
      and "domain_niches" not in composite_auditor.VERDICT_TOOL["input_schema"]["required"])

FILAS = [
    {"reviewer": "a", "verdict": "APPROVE", "domain_niches": ["N3", "N1"]},
    {"reviewer": "b", "verdict": "APPROVE_MINOR", "domain_niches": ["N3"]},
    {"reviewer": "c", "verdict": "APPROVE", "domain_niches": []},          # clasificó VACÍO
    {"reviewer": "d", "status": "errored", "error": "boom"},               # juez CAÍDO
    {"reviewer": "e", "verdict": "APPROVE"},                               # NO emitió el campo
]
t = composite_auditor.tally_domain_niches(FILAS, n_valid=4)
check("el consenso son CONTEOS por código, no un ganador",
      t["counts"] == {"N3": 2, "N1": 1}, f"counts={t['counts']}")
check("el juez CAÍDO no clasifica ni se le inventa voto",
      t["n_valid"] == 4 and t["n_classified"] == 3,
      f"n_valid={t['n_valid']} n_classified={t['n_classified']}")
check("'no emitió el campo' ≠ 'clasificó vacío': sólo el segundo cuenta como clasificar",
      t["n_classified"] == 3)
check("el denominador viaja (N3:2 no se confunde con 2 de 2 ni con 2 de 4)",
      "n_valid" in t and "n_classified" in t)
check("el panel se declara CLASE juicio — el eje medido vive en el catálogo",
      t["class"] == "juicio")

sin_nadie = composite_auditor.tally_domain_niches(
    [{"reviewer": "x", "status": "errored", "error": "boom"}], n_valid=0)
check("panel entero caído: conteos vacíos y n_classified 0, jamás un nicho fabricado",
      sin_nadie["counts"] == {} and sin_nadie["n_classified"] == 0)

# ── un código FUERA de la tabla se conserva crudo (visible), no se corrige en silencio ─────────
raro = composite_auditor.tally_domain_niches(
    [{"reviewer": "z", "verdict": "APPROVE", "domain_niches": ["N99"]}], n_valid=1)
check("un código fuera de la tabla queda VISIBLE en el conteo, no corregido en silencio",
      raro["counts"] == {"N99": 1}, f"counts={raro['counts']}")

n_pass = sum(CHECKS)
print(f"\n{n_pass}/{len(CHECKS)} PASS")
sys.exit(0 if n_pass == len(CHECKS) else 1)
