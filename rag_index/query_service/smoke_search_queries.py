"""smoke_search_queries.py — gate determinista del constructor de queries de la Ruta B (ADR-0078, I4).

Cubre lib/search_queries.py: golden de 6 casos (con/sin símbolos · con/sin anatomía · acentos ES en la
pregunta · símbolos con caracteres raros que se sanean · insumos vacíos → ausencia DECLARADA), el contrato
de salida (llaves fijas, builder_version), la regla "NUNCA ORGANISM:" en Europe PMC, el bloque anatómico
SOLO con términos presentes (sin default optimista), la no-activación por subcadena ('product',
'reduction' no son 'duct'), y DETERMINISMO byte a byte: la misma entrada produce los mismos bytes en dos
llamadas del mismo proceso Y en un intérprete fresco (subprocess), contrastados contra un hash golden.
Corrector ADR-0078 (2026-09-14): UNA política de anatomía para los tres índices (unión pregunta original +
formulación EN, procedencia en notes.anatomy / notes.anatomy_text_source); la pregunta original JAMÁS se
tokeniza como texto libre (sin símbolos ni EN → 'empty' declarado con razón).

100% offline: cero red, cero modelo, cero DB, cero mutación de la DATA INAMOVIBLE. stdlib puro.
Exit 0 = todo PASS.

Corre:  python rag_index/query_service/smoke_search_queries.py
"""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "analysis" / "scripts"))
from lib import search_queries as sq  # noqa: E402

CHECKS = []


def check(name, cond, detail=""):
    CHECKS.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + name + (("  -> " + detail) if detail else ""))


# ---- 6 casos golden --------------------------------------------------------------------------------------
# (id, symbols, question) — la pregunta alimenta la detección anatómica de los tres builders.
CASES = [
    ("c1_symbols_anatomy_en",
     ["osr1", "prkci", "pax2a"],
     "Is osr1 required for zebrafish pronephros development?"),
    ("c2_symbols_no_anatomy",
     ["wt1a"],
     "Does wt1a regulate heart development in zebrafish?"),
    ("c3_no_symbols_anatomy_en",
     [],
     "Is osr1 required for pronephric glomerulus and podocyte formation in zebrafish?"),
    ("c4_symbols_anatomy_es_accents",
     ["wt1a", "wt1b"],
     "¿Qué fenotipos de riñón, túbulo pronéfrico y glomérulo tiene wt1a?"),
    ("c5_symbols_dirty",
     [" Wt1a; DROP TABLE", '"pax2a"', "si:ch211-250g4.3", "", "x", None, "pax2a"],
     "Does the product reduction affect the duct?"),
    ("c6_empty",
     [],
     ""),
]

PUBMED_ORG = '(zebrafish[mh] OR zebrafish[tiab] OR "danio rerio"[tiab])'
EPMC_ORG = '(MESH:"Zebrafish" OR zebrafish)'

# Golden: {case: {index: (query, symbols_used, anatomy_terms_used, mode)}}
GOLDEN = {
    "c1_symbols_anatomy_en": {
        "pubmed": ("(osr1[tiab] OR prkci[tiab] OR pax2a[tiab]) AND " + PUBMED_ORG +
                   " AND (pronephros[tiab] OR pronephric[tiab])",
                   ["osr1", "prkci", "pax2a"], ["pronephros", "pronephric"], "symbols"),
        "europepmc": ("(TITLE:osr1 OR ABSTRACT:osr1 OR TITLE:prkci OR ABSTRACT:prkci OR TITLE:pax2a OR ABSTRACT:pax2a)"
                      " AND " + EPMC_ORG + " AND (pronephros OR pronephric)",
                      ["osr1", "prkci", "pax2a"], ["pronephros", "pronephric"], "symbols"),
        "zfin": ("pronephr", [], ["pronephros", "pronephric"], "anatomy-filter"),
    },
    "c2_symbols_no_anatomy": {
        "pubmed": ("(wt1a[tiab]) AND " + PUBMED_ORG, ["wt1a"], [], "symbols"),
        "europepmc": ("(TITLE:wt1a OR ABSTRACT:wt1a) AND " + EPMC_ORG, ["wt1a"], [], "symbols"),
        "zfin": (None, [], [], "no-filter"),
    },
    "c3_no_symbols_anatomy_en": {
        "pubmed": ("(osr1 pronephric glomerulus podocyte formation) AND " + PUBMED_ORG +
                   " AND (pronephros[tiab] OR pronephric[tiab] OR glomerulus[tiab] OR glomerular[tiab] OR podocyte[tiab])",
                   [], ["pronephros", "pronephric", "glomerulus", "glomerular", "podocyte"], "question-only"),
        "europepmc": ("(osr1 pronephric glomerulus podocyte formation) AND " + EPMC_ORG +
                      " AND (pronephros OR pronephric OR glomerulus OR glomerular OR podocyte)",
                      [], ["pronephros", "pronephric", "glomerulus", "glomerular", "podocyte"], "question-only"),
        "zfin": ("pronephr|glomer|podocyte", [],
                 ["pronephros", "pronephric", "glomerulus", "glomerular", "podocyte"], "anatomy-filter"),
    },
    "c4_symbols_anatomy_es_accents": {
        "pubmed": ("(wt1a[tiab] OR wt1b[tiab]) AND " + PUBMED_ORG +
                   " AND (pronephros[tiab] OR pronephric[tiab] OR glomerulus[tiab] OR glomerular[tiab]"
                   " OR kidney[mh] OR kidney[tiab] OR tubule[tiab])",
                   ["wt1a", "wt1b"],
                   ["pronephros", "pronephric", "glomerulus", "glomerular", "kidney", "tubule"], "symbols"),
        "europepmc": ("(TITLE:wt1a OR ABSTRACT:wt1a OR TITLE:wt1b OR ABSTRACT:wt1b) AND " + EPMC_ORG +
                      " AND (pronephros OR pronephric OR glomerulus OR glomerular OR kidney OR tubule)",
                      ["wt1a", "wt1b"],
                      ["pronephros", "pronephric", "glomerulus", "glomerular", "kidney", "tubule"], "symbols"),
        "zfin": ("pronephr|glomer|kidney|tubul", [],
                 ["pronephros", "pronephric", "glomerulus", "glomerular", "kidney", "tubule"], "anatomy-filter"),
    },
    "c5_symbols_dirty": {
        "pubmed": ('(wt1a[tiab] OR pax2a[tiab] OR "si:ch211-250g4.3"[tiab]) AND ' + PUBMED_ORG +
                   " AND (duct[tiab])",
                   ["wt1a", "pax2a", "si:ch211-250g4.3"], ["duct"], "symbols"),
        "europepmc": ('(TITLE:wt1a OR ABSTRACT:wt1a OR TITLE:pax2a OR ABSTRACT:pax2a'
                      ' OR TITLE:"si:ch211-250g4.3" OR ABSTRACT:"si:ch211-250g4.3") AND ' + EPMC_ORG +
                      " AND (duct)",
                      ["wt1a", "pax2a", "si:ch211-250g4.3"], ["duct"], "symbols"),
        "zfin": ("duct", [], ["duct"], "anatomy-filter"),
    },
    "c6_empty": {
        "pubmed": (None, [], [], "empty"),
        "europepmc": (None, [], [], "empty"),
        "zfin": (None, [], [], "no-filter"),
    },
}

# Hash golden del volcado canónico de los 6 casos (json.dumps sort_keys, ensure_ascii, separators fijos).
# Si cambia una tabla o una regla, cambia este hash: ese es el punto — subir QUERY_BUILDER_VERSION y regrabar.
# Regrabado 2026-09-14 (corrector ADR-0078): cambiaron SOLO las notes (anatomy 'from-both', anatomy_text_source,
# question_terms_source, reason, semantics de ZFIN); las 18 queries golden de abajo son byte-idénticas a la
# grabación anterior (se asertan una por una, independientes del hash). builder_version sigue en "1".
GOLDEN_SHA256 = "20496be7ee54ea94a74a6fa80a69bbf94bc5d7e04a6d967516c4205f1a03e41e"

CONTRACT_KEYS = ("query", "builder_version", "symbols_used", "anatomy_terms_used", "notes")

_DUMP_SNIPPET = r"""
import json, sys
sys.path.insert(0, sys.argv[1])
from lib import search_queries as sq
cases = json.loads(sys.argv[2])
out = {cid: sq.build_all(syms, q, q) for cid, syms, q in cases}
sys.stdout.buffer.write(json.dumps(out, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode("utf-8"))
"""


def canonical(obj):
    return json.dumps(obj, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode("utf-8")


def run_all():
    return {cid: sq.build_all(syms, q, q) for cid, syms, q in CASES}


def main():
    check("QUERY_BUILDER_VERSION == '1'", sq.QUERY_BUILDER_VERSION == "1", repr(sq.QUERY_BUILDER_VERSION))
    check("ANATOMY_TERMS_EN exacta y ordenada",
          sq.ANATOMY_TERMS_EN == ("pronephros", "pronephric", "glomerulus", "glomerular", "podocyte",
                                  "nephron", "kidney", "tubule", "duct"),
          repr(sq.ANATOMY_TERMS_EN))
    check("stdlib puro: el módulo no importa nada fuera de re/unicodedata",
          set(getattr(sq, "__dict__").keys()) >= {"re", "unicodedata"} and
          not any(m in sq.__dict__ for m in ("requests", "urllib", "answer_pipeline")))

    out = run_all()

    # ---- golden por caso/índice ----
    for cid, per_index in GOLDEN.items():
        for index, (g_query, g_syms, g_anat, g_mode) in per_index.items():
            r = out[cid][index]
            check(f"{cid}/{index}: contrato de llaves", tuple(r.keys()) == CONTRACT_KEYS, repr(tuple(r.keys())))
            check(f"{cid}/{index}: builder_version", r["builder_version"] == "1")
            check(f"{cid}/{index}: query", r["query"] == g_query, f"got {r['query']!r}")
            check(f"{cid}/{index}: symbols_used", r["symbols_used"] == g_syms, repr(r["symbols_used"]))
            check(f"{cid}/{index}: anatomy_terms_used", r["anatomy_terms_used"] == g_anat, repr(r["anatomy_terms_used"]))
            check(f"{cid}/{index}: notes.mode", r["notes"]["mode"] == g_mode, repr(r["notes"]["mode"]))
            # los casos pasan la MISMA cadena como question y question_en: con anatomía, ambos textos aportan
            check(f"{cid}/{index}: notes.anatomy declarada (+ anatomy_text_source)",
                  r["notes"]["anatomy"] == ("from-both" if g_anat else "none-in-question")
                  and r["notes"]["anatomy_text_source"] == (["question", "question_en"] if g_anat else []),
                  repr((r["notes"]["anatomy"], r["notes"]["anatomy_text_source"])))
            if index == "europepmc" and r["query"]:
                check(f"{cid}/{index}: NUNCA ORGANISM:", "ORGANISM:" not in r["query"])
                check(f"{cid}/{index}: organismo por MESH", 'MESH:"Zebrafish"' in r["query"]
                      and r["notes"]["organism_field"] == "MESH")
            if index == "pubmed" and r["query"]:
                check(f"{cid}/{index}: bloque organismo PubMed", PUBMED_ORG in r["query"])
            if not g_anat and r["query"]:
                check(f"{cid}/{index}: sin bloque anatómico cuando la pregunta no lo trae",
                      not any(t in r["query"] for t in sq.ANATOMY_TERMS_EN))

    # ---- saneo declarado (c5) ----
    n5 = out["c5_symbols_dirty"]["pubmed"]["notes"]
    check("c5: descartados declarados ('' y 'x')", n5["symbols_dropped"] == ["", "x"], repr(n5["symbols_dropped"]))
    check("c5: saneados declarados (original → limpio)",
          n5["symbols_sanitized"] == {" Wt1a; DROP TABLE": "wt1a", '"pax2a"': "pax2a"},
          repr(n5["symbols_sanitized"]))
    check("c5: 'pax2a' duplicado (sucio + limpio) entra UNA vez",
          out["c5_symbols_dirty"]["pubmed"]["symbols_used"].count("pax2a") == 1)

    # ---- question-only (c3) y empty (c6) declarados ----
    n3 = out["c3_no_symbols_anatomy_en"]["pubmed"]["notes"]
    check("c3: question_terms sin stopwords ni organismo",
          n3["question_terms"] == ["osr1", "pronephric", "glomerulus", "podocyte", "formation"],
          repr(n3["question_terms"]))
    n6 = out["c6_empty"]["pubmed"]["notes"]
    check("c6: ausencia declarada con razón", n6["organism_block"] is False and "reason" in n6, repr(n6))

    # ---- corrector ADR-0078: UNA política de anatomía para los tres índices, procedencia declarada ----
    mixed = sq.build_all(["osr1"], question_en="osr1 zebrafish pronephros induction",
                         question="pregunta en español sin anatomía")
    check("ES sin anatomía + EN con anatomía: los TRES índices llevan la anatomía del EN y lo declaran 'from-question-en'",
          all(mixed[i]["notes"]["anatomy"] == "from-question-en" for i in ("pubmed", "europepmc", "zfin"))
          and all(mixed[i]["notes"]["anatomy_text_source"] == ["question_en"] for i in ("pubmed", "europepmc", "zfin"))
          and "pronephros[tiab]" in mixed["pubmed"]["query"] and "pronephros" in mixed["europepmc"]["query"]
          and mixed["zfin"]["query"] == "pronephr",
          repr({i: mixed[i]["notes"]["anatomy"] for i in ("pubmed", "europepmc", "zfin")}))
    es_only = sq.build_all(["osr1"], question_en=None, question="¿Qué induce el pronefros?")
    check("ES con anatomía y sin EN: anatomía 'from-question' en los tres índices, mismo bloque anatómico",
          all(es_only[i]["notes"]["anatomy"] == "from-question" for i in ("pubmed", "europepmc", "zfin"))
          and "pronephros[tiab]" in es_only["pubmed"]["query"] and es_only["zfin"]["query"] == "pronephr")
    union = sq.build_all([], question_en="osr1 glomerulus formation", question="¿Qué induce el pronefros?")
    check("unión: ES aporta 'pronephr' y EN aporta 'glomer' -> 'from-both', raíces en orden de tabla",
          union["zfin"]["query"] == "pronephr|glomer" and union["zfin"]["notes"]["anatomy"] == "from-both"
          and union["pubmed"]["anatomy_terms_used"] == ["pronephros", "pronephric", "glomerulus", "glomerular"],
          repr(union["zfin"]))
    check("question_terms salen SOLO del EN (jamás tokens en español): ['osr1','glomerulus','formation']",
          union["pubmed"]["notes"]["question_terms"] == ["osr1", "glomerulus", "formation"]
          and union["pubmed"]["notes"]["question_terms_source"] == "question_en"
          and "pronefros" not in union["pubmed"]["query"] and "induce" not in union["pubmed"]["query"],
          repr(union["pubmed"]["notes"]["question_terms"]))
    es_nosym = sq.build_all([], question_en=None, question="¿Requiere osr1 la formación del pronefros?")
    check("sin símbolos y sin EN: la pregunta ES NO se manda como texto libre -> query None, mode 'empty', razón declarada; "
          "ZFIN conserva su filtro (no depende de texto libre)",
          es_nosym["pubmed"]["query"] is None and es_nosym["europepmc"]["query"] is None
          and es_nosym["pubmed"]["notes"]["mode"] == "empty" and "English formulation" in es_nosym["pubmed"]["notes"]["reason"]
          and es_nosym["pubmed"]["notes"]["question_terms"] == [] and es_nosym["zfin"]["query"] == "pronephr",
          repr(es_nosym["pubmed"]["notes"]))

    # ---- detección anatómica: acentos y no-activación por subcadena ----
    terms, stems = sq.detect_anatomy("riñón túbulo glomérulo pronéfrico nefrona podocitos conducto")
    check("detect_anatomy: ES con acentos activa las 7 raíces",
          stems == ["pronephr", "glomer", "podocyte", "nephron", "kidney", "tubul", "duct"], repr(stems))
    check("detect_anatomy: 'product'/'reduction'/'conductor' NO activan 'duct'",
          sq.detect_anatomy("the product reduction by the conductor") == ([], []))
    check("detect_anatomy: None/'' → ([], [])", sq.detect_anatomy(None) == ([], []) and sq.detect_anatomy("") == ([], []))
    check("detect_anatomy: sin default optimista (pregunta sin anatomía → [])",
          sq.detect_anatomy("Does wt1a regulate heart development?") == ([], []))

    # ---- determinismo byte a byte ----
    b1 = canonical(out)
    b2 = canonical(run_all())
    check("determinismo: dos llamadas, mismos bytes", b1 == b2)
    payload = json.dumps([[cid, syms, q] for cid, syms, q in CASES], ensure_ascii=True)
    proc = subprocess.run([sys.executable, "-c", _DUMP_SNIPPET, str(ROOT / "analysis" / "scripts"), payload],
                          capture_output=True, timeout=60)
    check("determinismo: intérprete fresco, mismos bytes", proc.returncode == 0 and proc.stdout == b1,
          proc.stderr.decode("utf-8", errors="replace")[-300:] if proc.returncode else f"{len(proc.stdout)} bytes")
    sha = hashlib.sha256(b1).hexdigest()
    check("determinismo: hash golden", sha == GOLDEN_SHA256, f"got {sha}")

    n_pass, n_total = sum(CHECKS), len(CHECKS)
    print(f"\n{n_pass}/{n_total} PASS")
    return 0 if n_pass == n_total else 1


if __name__ == "__main__":
    sys.exit(main())
