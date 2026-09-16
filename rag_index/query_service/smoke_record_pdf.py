"""smoke_record_pdf.py — gate de COBERTURA del PDF de servidor (ADR-0083 K, rebanada F6, contrato 1.12).

Lo que MIDE (fila `smoke_record_pdf.py` de la tabla de gates NO-SPEND del ADR):
  (1) cobertura: las llaves top-level del literal `frozen = {` + `frozen["k"] =` de runs.py (la MISMA técnica que
      witt-webapp/tools/parity_check.frozen_keys, copiada literal) → `record_pdf.pdf_sections_cover` da missing [] y
      extra [] (52 llaves: 50 de 1.10 + council + figures); con el frozen REAL de una corrida offline (execute_run con
      stubs, patrón smoke_run_pipeline) CERRADA (frozen_at/closed_by nacen al cerrar) igualdad EXACTA; el frozen abierto
      declara exactamente esas dos como extra; un registro 1.12 con figuras (frozen real + `figures` de figures.attach sobre
      el zip fixture) también EXACTA;
  (2) `PDF_ACCESS_RE` de la webapp copiada literal: record_pdf.py lee TODAS las llaves del frozen (0 huecos) y cada llave de
      `SECCIONES` tiene su `record.get("k")` literal (R10); `SECCIONES = (` existe como literal (segunda fuente de la webapp);
  (3) rutas anidadas en el TEXTO impreso: audit.quorum, token_usage.by_stage.panel.by_model (cada reviewer con in/out),
      search_ledger.rounds[].sources[] (una fila por fuente), citations_schema.source × 5 → 5 frases DISTINTAS y ninguna con
      'no constan (contrato pre-1.1)', citations_support_summary.by_state (5 peldaños), council.ledger/rounds/coverage
      (SINTÉTICO declarado: la corrida offline no arma consejo), figures.items[];
  (4) tres estados con el contrato de nacimiento CALCULADO: sin models → '< 1.10', competence → '< 1.9', thread → '< 1.8',
      council → '< 1.11', figures → '< 1.12'; null + _state → 'null declarado - razon: <glosa del state>'; valor impreso;
      registro pre-1.1 → todo NO INSTRUMENTADO con el born correcto por llave (1.1/1.3/1.4/1.6/1.7/1.8/1.9/1.10/1.11/1.12);
  (5) la regla del sha impresa == record['thread_parent_matches_run_rule'] (dos reglas → dos PDFs distintos; ausente →
      'regla no declarada en este registro');
  (6) figuras: fixture CC BY con caché TMP → N `/Subtype /Image` == min(n_embeddable, 12) y 'CC BY' + 'embebible' + sha[:16];
      NC → 0 imágenes + 'NO embebible' + 'caption + enlace'; unknown → 'licencia desconocida'; archivo alterado → 'bytes:
      mismatch' y esa figura sin imagen; caché vacía → 'bytes no en caché'; thumbs=0 → 0 imágenes; tope 8 MB forzado a
      0.05 MB → 'miniatura omitida por tope'; 'vista por 2 lentes' + 'JUICIO';
  (7) ADR-0073 a–f siguen verdes; (8) determinismo: dos build_pdf con fecha fija → bytes iguales; PDF ≤ 8 MB;
  (9) `urlopen` bloqueado y contado == 0; mcp_cache del repo byte-idéntico antes/después; sin literales fijos viejos en el módulo.

100% OFFLINE y PORTABLE: SQLite tmp (máscara), caché de figuras en TMP (WITT_MCP_CACHE_DIR), fixtures del repo, cero gasto
de modelo, cero mutación de la DATA INAMOVIBLE. Exit 0 = todo PASS.

Máscara:  WITT_BACKEND_DB_URL=sqlite:///<tmp>.db NEO4J_URI="" RAG_BACKEND=sparse OPENAI_API_KEY="" ANTHROPIC_API_KEY=""
          WITT_RUN_ORIGIN=smoke [WITT_MCP_CACHE_DIR=<tmp>] python rag_index/query_service/smoke_record_pdf.py
"""
import datetime
import io
import json
import os
import re
import sys
import tempfile
import zipfile
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "analysis" / "scripts"))
sys.path.insert(0, str(HERE))
FX = HERE / "fixtures" / "figures"
TMP = Path(tempfile.mkdtemp(prefix="smoke_record_pdf_"))
REPO_CACHE = ROOT / "mcp_cache"

# ---- máscara: BD tmp si no viene, sin env de figuras heredada, caché de figuras en TMP, corridas offline permitidas -----
os.environ.setdefault("WITT_BACKEND_DB_URL", f"sqlite:///{TMP / 'backend.db'}")
os.environ.pop("NEO4J_URI", None)
os.environ["WITT_ALLOW_RUNS_OFFLINE"] = "1"   # dev sparse siempre está OFFLINE (LOTE-01·A5 override, patrón smoke_run_pipeline)
for _k in list(os.environ):
    if _k.startswith("WITT_FIGURES"):
        os.environ.pop(_k, None)
# F8 (integrador): raíz de caché FRESCA por corrida — mkdtemp DENTRO de WITT_MCP_CACHE_DIR (si la máscara la trae) o de TMP;
# una raíz reutilizada haría cache-hit en attach() y las precondiciones del gate (GET_CALLS) fallarían. Se borra al final.
_cache_parent = Path((os.environ.get("WITT_MCP_CACHE_DIR") or "").strip() or (TMP / "mcp_cache"))
_cache_parent.mkdir(parents=True, exist_ok=True)
FRESH_CACHE = Path(tempfile.mkdtemp(prefix="record_pdf_", dir=str(_cache_parent)))
os.environ["WITT_MCP_CACHE_DIR"] = str(FRESH_CACHE)
CACHE_ENV = Path(os.environ["WITT_MCP_CACHE_DIR"])

# ---- red BLOQUEADA y CONTADA antes de importar nada (figures._urlopen se liga al importar) ---------------------------------
import urllib.request as _urlreq  # noqa: E402

NET_CALLS = []
_urlopen_real = _urlreq.urlopen


def _urlopen_blocked(*a, **kw):
    NET_CALLS.append(str(a[0].full_url if hasattr(a[0], "full_url") else a[0]) if a else "?")
    raise RuntimeError("red bloqueada en smoke_record_pdf")


_urlreq.urlopen = _urlopen_blocked


def _mcp_snapshot():
    if not REPO_CACHE.exists():
        return None
    out = []
    for p in sorted(REPO_CACHE.rglob("*")):
        if p.is_file() and not p.name.endswith(".log"):   # mcp_server.log es bitacora viva del MCP, no cache (smoke_run_pipeline igual)
            st = p.stat()
            out.append((str(p.relative_to(REPO_CACHE)), st.st_size, st.st_mtime_ns))
    return out


MCP_BEFORE = _mcp_snapshot()

import app  # noqa: E402
import db  # noqa: E402
import record_pdf as R  # noqa: E402
import runs as runs_mod  # noqa: E402
from lib import answer_pipeline, composite_auditor, rag_backend  # noqa: E402
from lib import figures as F  # noqa: E402
from lib.rag_backend import Hit, HitList  # noqa: E402

CHECKS = []


def check(name, cond, detail=""):
    CHECKS.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + name + (("  -> " + detail) if detail else ""))


# ---- captura del TEXTO que la plantilla manda a imprimir (fpdf parte líneas: buscar frases en bytes es frágil) ----------
_PDF_TEXT = []
for _fn_name in ("_p", "_h", "_band"):
    _orig = getattr(R, _fn_name)

    def _capturing(pdf, text, *a, __orig=_orig, **kw):
        _PDF_TEXT.append(R._t(text))
        return __orig(pdf, text, *a, **kw)

    setattr(R, _fn_name, _capturing)

FIXED_NOW = datetime.datetime(2026, 9, 16, 12, 0, 0, tzinfo=datetime.timezone.utc)


def pdf_text(record, **kw):
    del _PDF_TEXT[:]
    kw.setdefault("compress", False)
    kw.setdefault("now", FIXED_NOW)
    raw = R.build_pdf(record, **kw)
    return raw, "\n".join(_PDF_TEXT)


def n_images(raw):
    return raw.count(b"/Subtype /Image")


# =====================================================================================================================
# 1. GATE ESTÁTICO — llaves del frozen (técnica de parity_check.frozen_keys copiada literal) vs SECCIONES vs lecturas
# =====================================================================================================================
print("== 1. gate estatico de cobertura ==")
RUNS_SRC = (HERE / "runs.py").read_text(encoding="utf-8")
PDF_SRC = (HERE / "record_pdf.py").read_text(encoding="utf-8")


def _top_level_keys_of_dict_literal(src, opener):
    """COPIA LITERAL de witt-webapp/tools/parity_check._top_level_keys_of_dict_literal (K.1)."""
    i = src.index(opener) + len(opener)
    depth = 1
    keys = []
    n = len(src)
    while i < n and depth > 0:
        c = src[i]
        if c == "#":
            while i < n and src[i] != "\n":
                i += 1
            continue
        if c in "\"'":
            q = c
            j = i + 1
            while j < n and src[j] != q:
                if src[j] == "\\":
                    j += 1
                j += 1
            lit = src[i + 1:j]
            k = j + 1
            while k < n and src[k] in " \t":
                k += 1
            if depth == 1 and k < n and src[k] == ":":
                keys.append(lit)
            i = j + 1
            continue
        if c in "{[(":
            depth += 1
        elif c in "}])":
            depth -= 1
        i += 1
    return keys


def frozen_keys():
    keys = _top_level_keys_of_dict_literal(RUNS_SRC, "frozen = {")
    for m in re.finditer(r'frozen\["([A-Za-z_]\w*)"\]\s*=', RUNS_SRC):
        if m.group(1) not in keys:
            keys.append(m.group(1))
    return keys


# COPIA LITERAL de parity_check.PDF_ACCESS_RE (K.2)
PDF_ACCESS_RE = re.compile(r"""record(?:\.get\(\s*["']([A-Za-z_]\w*)["']|\[\s*["']([A-Za-z_]\w*)["']\s*\])""")

FK = frozen_keys()
READ = {a or b for a, b in PDF_ACCESS_RE.findall(PDF_SRC)}
cov = R.pdf_sections_cover(FK)
check("(K.1) frozen_keys de runs.py (literal + asignaciones, tecnica de la webapp) = 52 llaves (50 de 1.10 + council + figures) y "
      "pdf_sections_cover da missing [] y extra [] — igualdad EXACTA",
      len(FK) == 52 and "figures" in FK and cov == {"missing": [], "extra": []},
      f"n_frozen={len(FK)} missing={cov['missing']} extra={cov['extra']}")
check("(K.2) PDF_ACCESS_RE (copiada de la webapp): record_pdf.py LEE todas las llaves del frozen salvo la zona de servicio — 0 huecos",
      [k for k in FK if k not in READ and k not in R.SERVICE_KEYS] == [],
      f"huecos={[k for k in FK if k not in READ and k not in R.SERVICE_KEYS]}")
_m_anch = re.search(r"^SECCIONES\s*=\s*\($", PDF_SRC, re.M)
_lit = PDF_SRC[_m_anch.end():PDF_SRC.index("\n)\n", _m_anch.end())] if _m_anch else ""
_keys_anch = re.findall(r'^\s*\("([a-z_]+)",\s*"[a-z_]+"\),?\s*$', _lit, re.M)
_unanch = [PDF_SRC.count("\n", 0, m.start()) + 1 for m in re.finditer(r"SECCIONES\s*=\s*\(", PDF_SRC)]
check("(K, corrector) la SEGUNDA fuente de la webapp debe usar la regex ANCLADA `^SECCIONES\\s*=\\s*\\($` (re.M): sobre el modulo devuelve las 52 llaves == "
      "record_pdf.SECTION_KEYS; la regex SIN anclar casa >= 2 sitios (ORDEN_SECCIONES y el literal) — trampa MEDIDA y declarada en el comentario del "
      "modulo (que ya no contiene el texto del literal)",
      _m_anch is not None and _keys_anch == list(R.SECTION_KEYS) and len(_keys_anch) == 52 and len(_unanch) >= 2
      and "regex ANCLADA" in PDF_SRC and "SECTION_KEYS" in PDF_SRC,
      f"anclada={len(_keys_anch)} sitios_sin_anclar(lineas)={_unanch}")
check("(R10) cada llave de SECCIONES tiene su record.get(\"k\") LITERAL en el modulo (la segunda fuente de la webapp lo exige); "
      "SECCIONES == KEY_BORN; el literal `SECCIONES = (` existe; SERVICE_KEYS = las que app._ratings_view fusiona",
      [k for k in R.SECTION_KEYS if k not in READ] == [] and set(R.SECTION_KEYS) == set(R.KEY_BORN)
      and "SECCIONES = (" in PDF_SRC and set(R.SERVICE_KEYS) >= {"consensus", "ratings", "ratings_masked"}
      and len(R.SECTION_KEYS) == 52,
      f"n_secciones={len(R.SECTION_KEYS)} sin_literal={[k for k in R.SECTION_KEYS if k not in READ]}")
_sec_lit = re.search(r"SECCIONES = \((.*?)\n\)", PDF_SRC, re.S).group(1)
_sec_keys_lit = re.findall(r'\(\s*"([A-Za-z_]\w*)"\s*,', _sec_lit)
check("(K webapp) las llaves del literal `SECCIONES = (` leidas por regex == SECTION_KEYS (la webapp lo leera asi)",
      _sec_keys_lit == list(R.SECTION_KEYS), f"n={len(_sec_keys_lit)}")
OLD_LITERALS = ("_NOT_INSTRUMENTED", "contrato pre-1.1", "sobre el blob sin frozen_at", "nacio antes de ADR-0079", "nacio antes de ADR-0082")
_fixed_born = re.findall(r"NO INSTRUMENTADO \(contrato < 1\.\d+\)", PDF_SRC)
check("(J.1) sin literales fijos viejos en record_pdf.py: ni _NOT_INSTRUMENTED*, ni 'contrato pre-1.1', ni la prosa fija del sha, "
      "ni un 'NO INSTRUMENTADO (contrato < 1.N)' tecleado — el numero sale de KEY_BORN",
      not any(lit in PDF_SRC for lit in OLD_LITERALS) and _fixed_born == [],
      f"viejos={[lit for lit in OLD_LITERALS if lit in PDF_SRC]} fijos={_fixed_born}")
check("KEY_BORN fijado por el historial de runs.py: reasoning/agents_invoked/alternatives_considered 1.3 (ADR-0060), fallback/confidence/"
      "citations 1.1 (ADR-0051), plan 1.4, revision 1.6, citations_schema 1.7, thread 1.8, competence 1.9, models 1.10, council 1.11, figures 1.12",
      R.KEY_BORN["reasoning"] == "1.3" and R.KEY_BORN["agents_invoked"] == "1.3" and R.KEY_BORN["alternatives_considered"] == "1.3"
      and R.KEY_BORN["fallback"] == "1.1" and R.KEY_BORN["confidence"] == "1.1" and R.KEY_BORN["citations"] == "1.1"
      and R.KEY_BORN["plan"] == "1.4" and R.KEY_BORN["revision"] == "1.6" and R.KEY_BORN["citations_schema"] == "1.7"
      and R.KEY_BORN["thread"] == "1.8" and R.KEY_BORN["competence"] == "1.9" and R.KEY_BORN["models"] == "1.10"
      and R.KEY_BORN["council"] == "1.11" and R.KEY_BORN["figures"] == "1.12"
      and R.contract_of("models") == "1.10" and R.contract_of({"render_contract_version": "1.11"}) == "1.11"
      and R.born_of("no-existe") == R.BORN_UNKNOWN)
check("_tres_estados: ausente -> ('no-instrumentado', 'NO INSTRUMENTADO (contrato < 1.10) ...'); None + _state -> ('null', state); valor -> ('valor', v)",
      R._tres_estados({}, "models")[0] == "no-instrumentado" and "(contrato < 1.10)" in R._tres_estados({}, "models")[1]
      and R._tres_estados({"plan_parent_matches_run": None, "plan_parent_matches_run_state": "no-plan"}, "plan_parent_matches_run") == ("null", "no-plan")
      and R._tres_estados({"models": {"a": 1}}, "models") == ("valor", {"a": 1})
      and "contrato base 1.0" in R._tres_estados({}, "token_usage")[1])

# =====================================================================================================================
# 2. FROZEN REAL de una corrida OFFLINE (execute_run con stubs — patron smoke_run_pipeline)
# =====================================================================================================================
print("\n== 2. frozen real (execute_run offline) ==")


def _sin_keys(rec, *keys):
    return {k: v for k, v in rec.items() if k not in keys}


_sin = _sin_keys
_chunk = Hit(doc_id="CORPUS-2026-0003#c000", type="chunk", score=0.9, text="pronephros evidence", metadata={})
answer_pipeline.path_b = lambda q, n=2, **kw: []
answer_pipeline._cache_zfin = lambda symbol, res: []   # la cache por dia de ZFIN no se toca desde el gate (patron smoke_run_pipeline)
rag_backend.query = lambda text, k=6: HitList([_chunk], degraded=None)
ALL_A = {"correctness": "APPROVE", "overclaim": "APPROVE", "evidence-grounding": "APPROVE", "reproducibility": "APPROVE"}


def _caller(member, system, user_text):
    return ({"verdict": ALL_A[member["lens"]], "caught": f"({member['lens']})", "correction_applied": "",
             "confidence": 0.9, "reasons": []}, {"input_tokens": 10, "output_tokens": 5})


def _synth(question, evidence, pass_label):
    return {"direct_answer": "wt1a (ENSDARG00000031420) marks the zebrafish pronephros.",
            "stated_confidence": 0.85, "confidence_by_subclaim": {"marker-expression": 0.9},
            "absence_kind": "not-applicable", "gap_flags": [],
            "evidence_cited": [{"kind": "di-record", "id": "CORPUS-2026-0001"}],
            "alternatives_considered": ["wt1b como paralogo redundante: descartado, sin evidencia"],
            "framework_applied": "Logic-LM", "framework_criterion": "for any task whose criteria are formalizable",
            "framework_reason": "la admisibilidad del identificador es formalizable",
            "model": "stub-synth", "usage": {"input_tokens": 100, "output_tokens": 50}}


db.init_db()
db.upsert_user("natalia", "Natalia", "medico", "pw-natalia-123")
AUTH = "Bearer " + app.login(app.LoginBody(username="natalia", password="pw-natalia-123"))["token"]
rv = app.create_run(app.RunBody(question="smoke_record_pdf: does wt1a mark the pronephros?", entities=["wt1a"]), authorization=AUTH)
RID = rv["run_id"]
claimed = db.claim_next_queued(worker_id="smoke-record-pdf")
assert claimed and claimed["run_id"] == RID
runs_mod.execute_run(claimed, synthesizer=_synth, panel_caller=_caller)
_state_run = db.get_run(RID)["state"]
FROZEN_OPEN = json.loads(db.get_run(RID)["frozen_record_json"] or "{}")
_closed = runs_mod.close_run(RID, "natalia")   # frozen_at/closed_by NACEN al cerrar: el frozen completo es el CERRADO
_row = db.get_run(RID)
FROZEN = json.loads(_row["frozen_record_json"] or "{}")
REC = app.get_frozen_record(RID, authorization=AUTH)   # + zona de servicio (ratings/consensus), como get_record_pdf
check("la corrida offline congelo un registro con el contrato de runs.py; al cerrarla gana frozen_at/closed_by (52 llaves); la vista GET lo devuelve "
      "con la zona de servicio fusionada (SERVICE_KEYS)",
      _state_run == "awaiting_closure" and _closed.get("closed") is True and _row["state"] == "closed"
      and FROZEN.get("render_contract_version") == runs_mod.RENDER_CONTRACT_VERSION
      and set(FROZEN) - set(FROZEN_OPEN) == {"frozen_at", "closed_by"} and len(FROZEN) == 52
      and set(REC) >= set(FROZEN) and (set(REC) - set(FROZEN)) <= set(R.SERVICE_KEYS),
      f"state={_row['state']} contrato={FROZEN.get('render_contract_version')} n={len(FROZEN)} servicio={sorted(set(REC) - set(FROZEN))}")
cov_real = R.pdf_sections_cover(FROZEN.keys())
check("(K.1) cobertura EXACTA contra el frozen REAL cerrado (1.12 con `figures`): missing [] y extra [] — una llave nueva sin seccion ROMPE aqui",
      cov_real == {"missing": [], "extra": []}, f"{cov_real}")
cov_open = R.pdf_sections_cover(FROZEN_OPEN.keys())
check("(K.1) frozen ABIERTO (awaiting_closure): extra == ['frozen_at', 'closed_by'] exactamente — las dos llaves que solo nacen al cerrar",
      cov_open["missing"] == [] and sorted(cov_open["extra"]) == ["closed_by", "frozen_at"], f"{cov_open}")
check("(K.1) frozen_keys estatico == llaves del frozen real (la tecnica de la webapp mide lo que runs.py congela de verdad)",
      set(FK) == set(FROZEN), f"solo_estatico={sorted(set(FK) - set(FROZEN))} solo_real={sorted(set(FROZEN) - set(FK))}")

pdf_real, txt_real = pdf_text(REC)
REC11 = {**_sin_keys(REC, "figures"), "render_contract_version": "1.11"}
_, txt_11 = pdf_text(REC11)
check("PDF del registro real (1.12, sin Ruta B): %PDF, las 23 secciones rotuladas, FIGURAS con su estado declarado (glosado, NO 'NO INSTRUMENTADO'), "
      "CONSEJO con estado declarado, MODELOS con generacion, COMPETENCIA con componentes, CUORUM; el mismo registro SIN `figures` y contrato 1.11 -> "
      "FIGURAS 'NO INSTRUMENTADO (contrato < 1.12)' calculado",
      pdf_real[:5] == b"%PDF-"
      and all(t.split(" - ")[0].split(" (")[0] in txt_real for _s, t in R.ORDEN_SECCIONES if t)
      and "NO INSTRUMENTADO (contrato < 1.1" not in txt_real
      and f"estado: {FROZEN['figures']['state']} - " in txt_real and FROZEN["figures"]["state"] in R._FIGURES_STATE_GLOSS
      and "generacion " in txt_real and "conf1_ge_tau" in txt_real and "CUORUM" in txt_real
      and "NO INSTRUMENTADO (contrato < 1.12)" in txt_11 and "contrato < 1.11" not in txt_11,
      f"len={len(pdf_real)} figures.state={FROZEN['figures']['state']}")
_reviewers = list((FROZEN.get("token_usage", {}).get("by_stage", {}).get("panel", {}).get("by_model") or {}).keys())
check("(K.3) anidadas en el texto: audit.quorum (validos n/min, familias, lentes, regla), token_usage.by_stage.panel.by_model (CADA reviewer "
      "con in/out), citations_support_summary.by_state (los 5 peldaños), search_ledger state/plan_state, agents_invoked filas, plan null declarado",
      "validos " in txt_real and "regla de familias" in txt_real and "regla de lentes" in txt_real
      and len(_reviewers) >= 3 and all(f"      {r}: in " in txt_real for r in _reviewers)
      and all(f"{rung}: " in txt_real for rung in ("unresolved", "resolved", "passage_delivered", "supported", "unsupported"))
      and "plan_state:" in txt_real and "composite-auditor" in txt_real and "verify_output" in txt_real
      and "plan: null declarado - razon: plan_declared false" in txt_real,
      f"reviewers={_reviewers}")

# --- (K.7) ADR-0073 a–f siguen verdes -----------------------------------------------------------------------------------
check("ADR-0073a: %PDF + banda de modo con PALABRAS completas + APROBADA + PREGUNTA + CONGELADO",
      pdf_real[:5] == b"%PDF-" and b"SELLADA" in pdf_real and b"CONGELADO" in pdf_real and b"APROBADA" in pdf_real and b"PREGUNTA" in pdf_real)
try:
    R.build_pdf({**REC, "question_matches_run": False})
    _ident_ok = False
except ValueError:
    _ident_ok = True
check("ADR-0073c: identidad rota -> el PDF NO se genera (ValueError, misma regla que la hoja)", _ident_ok)
pdf_ni, txt_ni = pdf_text({k: v for k, v in REC.items() if k != "retrieval_summary"})
check("ADR-0073d: sin retrieval_summary la banda dice NO INSTRUMENTADO con palabras completas y la llave se declara del contrato base 1.0",
      b"NO INSTRUMENTADO" in pdf_ni and "contrato base 1.0" in txt_ni)
resp_pdf = app.get_record_pdf(RID, authorization=AUTH)
check("ADR-0073e: GET /runs/{id}/record.pdf sirve application/pdf con Content-Disposition (la firma build_pdf(record) sigue siendo compatible)",
      resp_pdf.media_type == "application/pdf" and bytes(resp_pdf.body)[:5] == b"%PDF-" and "registro_" in resp_pdf.headers.get("content-disposition", ""))
check("ADR-0073f: el pie declara el canal unico + el saneo latin-1 + las miniaturas embebidas (0 en un registro sin figuras)",
      b"latin-1" in pdf_real and b"UNICO" in pdf_real and "Miniaturas: 0 embebidas" in txt_real)
_rec_rev = {**REC, "revision": {"enabled": True, "performed": True, "cap": 1, "findings_used": 1, "initial_verdict": "REVISE", "final_verdict": "APPROVE"},
            "answer_initial": {"direct_answer": "respuesta inicial superada"},
            "audit_initial": {"verdict": "REVISE", "n_valid": 4, "panel": [{"reviewer": "x", "lens": "correctness", "verdict": "REVISE"}]}}
pdf_rev, txt_rev = pdf_text(_rec_rev)
check("ADR-0073b: el ciclo de revision viaja al PDF — RONDA 0 completa y marcada SUPERADA (nada se borra)",
      b"RONDA 0" in pdf_rev and b"SUPERADA" in pdf_rev and "[ronda 0] x (correctness): REVISE" in txt_rev)

# =====================================================================================================================
# 3. (K.4) tres estados con el born CALCULADO
# =====================================================================================================================
print("\n== 3. tres estados por llave ==")




for key, born in (("models", "1.10"), ("competence", "1.9"), ("thread", "1.8"), ("council", "1.11"), ("citations_schema", "1.7"),
                  ("revision", "1.6"), ("plan", "1.4"), ("reasoning", "1.3"), ("confidence", "1.1")):
    _, txt = pdf_text(_sin(REC, key))
    check(f"(K.4) sin `{key}` -> 'NO INSTRUMENTADO (contrato < {born})' (calculado de KEY_BORN, no literal fijo)",
          f"NO INSTRUMENTADO (contrato < {born})" in txt and f"NO INSTRUMENTADO (contrato < {born})" not in txt_real,
          f"presente_en_real={f'(contrato < {born})' in txt_real}")
_, txt_1_8 = pdf_text(_sin(REC, "thread", "thread_context", "thread_context_skipped_reason", "thread_parent_matches_run",
                            "thread_parent_matches_run_state", "thread_parent_matches_run_rule"))
check("(J) grupo con ANCLA ausente: quitar el grupo `thread` entero imprime UNA linea NO INSTRUMENTADO (contrato < 1.8) listando sus facetas — "
      "no seis lineas iguales; el precedente (otro ancla) sigue con valor",
      txt_1_8.count("NO INSTRUMENTADO (contrato < 1.8)") == 1 and "facetas del grupo tampoco constan: thread_context, " in txt_1_8
      and "precedente citado: ninguno" in txt_1_8, f"n={txt_1_8.count('NO INSTRUMENTADO (contrato < 1.8)')}")
_rec_null = {**REC, "user_id": None, "alternatives_considered": None,
             "plan_parent_matches_run": None, "plan_parent_matches_run_state": "no-plan"}
_, txt_null = pdf_text(_rec_null)
check("(K.4) None + _state -> 'null declarado - razon: <glosa del state>'; None sin state -> 'null declarado - razon: no consta'; "
      "alternatives_considered None -> hueco del sistema (distinto de [])",
      "procedencia plan<->padre: null declarado - razon: no aplica (corrida sin plan)" in txt_null
      and "quien corrio (user_id): null declarado - razon: no consta" in txt_null
      and "AUSENTE: hueco del sistema" in txt_null)
PRE11 = {"run_id": "r" + "0" * 31, "question": "pre-1.1 question", "decision_state": {"state": "AUDIT_APPROVED", "may_answer_now": True},
         "retrieval_summary": {"mode": "semantic", "retrievals": 3, "aggregation": "rrf"},
         "audit": {"verdict": "APPROVE", "n_valid": 3, "panel": []}, "answer": {"direct_answer": "old answer"},
         "deterministic_checks": {"pass": 1, "admissible": True, "reasons": []}, "bundle_identity": {"sha256": "ab" * 32},
         "question_matches_run": True}
pdf_pre, txt_pre = pdf_text(PRE11)
_borns_pre = {b: (f"(contrato < {b})" in txt_pre) for b in ("1.1", "1.3", "1.4", "1.6", "1.7", "1.8", "1.9", "1.10", "1.11", "1.12")}
check("registro PRE-1.1 (sin render_contract_version): cada seccion dice NO INSTRUMENTADO con SU contrato (1.1 confidence/citations/fallback, "
      "1.3 reasoning, 1.4 plan, 1.6 revision, 1.7 citations_schema, 1.8 thread/origin/ejes, 1.9 competence, 1.10 models, 1.11 council, 1.12 figures); "
      "token_usage/usage_raw ausentes -> 'contrato base 1.0'; render_contract_version ausente -> 'no consta'",
      all(_borns_pre.values()) and "contrato base 1.0" in txt_pre and "contrato de render: no consta" in txt_pre
      and pdf_pre[:5] == b"%PDF-", json.dumps(_borns_pre))
check("registro PRE-1.1: NADA se rellena — sin 'turno', sin 'origen: production', sin 'MUNDO:', sin 'generacion', sin 'competent:'",
      "turno 1" not in txt_pre and "origen: production" not in txt_pre and "MUNDO:" not in txt_pre
      and "generacion " not in txt_pre and "competent:" not in txt_pre)

# --- (K.5) la regla del sha LEIDA de la llave ------------------------------------------------------------------------------
_rule_a = FROZEN.get("thread_parent_matches_run_rule")
_rec_rb = {**REC, "thread_parent_matches_run_rule": "REGLA-B sintetica: otro texto para medir que se lee de la llave"}
pdf_ra, txt_ra = pdf_text(REC)
pdf_rb, txt_rb = pdf_text(_rec_rb)
_, txt_rn = pdf_text(_sin(REC, "thread_parent_matches_run_rule"))
check("(K.5) la regla del sha impresa == record['thread_parent_matches_run_rule'] (regla A del frozen real y una REGLA-B distinta -> dos PDFs "
      "distintos); sin la llave -> 'regla no declarada en este registro'; la prosa fija del sha ya no existe",
      isinstance(_rule_a, str) and f"regla del sha del padre: {_rule_a}" in txt_ra
      and "regla del sha del padre: REGLA-B sintetica" in txt_rb and pdf_ra != pdf_rb
      and "regla del sha del padre: regla no declarada en este registro" in txt_rn
      and "sobre el blob sin frozen_at" not in txt_rn)

# --- (K.3) citations_schema: 5 literales -> 5 frases DISTINTAS -----------------------------------------------------------------
_phrases = {}
for src in ("list", "string-reparsed", "string-unparseable", "absent", "unsupported-type"):
    _, txt = pdf_text({**REC, "citations_schema": {"source": src, "n_raw": 2, "n_valid": 1, "raw_type": "dict"}})
    line = next((l for l in txt.split("\n") if l.startswith(f"source {src}: ")), None)
    _phrases[src] = line
check("(K.3) citations_schema.source x 5 -> 5 frases DISTINTAS, ninguna contiene 'no constan (contrato pre-1.1)'; 'list' trae n_raw/n_valid, "
      "'unsupported-type' trae raw_type",
      all(_phrases.values()) and len(set(_phrases.values())) == 5
      and not any("no constan (contrato pre-1.1)" in p for p in _phrases.values())
      and "2 crudas / 1 validas" in _phrases["list"] and "(dict)" in _phrases["unsupported-type"]
      and 'no es "cito 0"' in _phrases["absent"] and 'NO es "cito 0"' in _phrases["string-unparseable"],
      json.dumps(_phrases, ensure_ascii=False)[:400])
_, txt_c0 = pdf_text({**_sin(REC, "citations_schema"), "citations": []})
check("citations [] SIN citations_schema -> 'medido-vacio o NO INSTRUMENTADO (contrato < 1.7): no distinguible, declarado'",
      "citas []: medido-vacio o NO INSTRUMENTADO (contrato < 1.7): no distinguible, declarado" in txt_c0)

# --- (K.3) search_ledger: una fila por fuente; council sintetico con ledger/rondas/cobertura -------------------------------------
_rec_sl = {**REC, "search_ledger": {**REC["search_ledger"], "state": "harness", "rounds": [
    {"round": 1, "trigger": "structural", "budget_s": 60.0, "n_admitted": 2, "elapsed_s": 3.2, "stop_reason": "no-new-inputs",
     "sources": [{"family": "europepmc", "status": "ran", "n_found": 5, "n_new": 2, "elapsed_s": 1.1, "cache_hit": True, "label": "search",
                  "query_sent": "wt1a pronephros"},
                 {"family": "zfin", "status": "error", "n_found": None, "n_new": None, "elapsed_s": 2.0, "cache_hit": False, "label": None,
                  "error": "TimeoutError: fake"}]}]}}
_, txt_sl = pdf_text(_rec_sl)
check("(K.3) search_ledger.rounds[].sources[] -> UNA FILA POR FUENTE: 'round | family | status | n_found (null = no midio) | n_new | elapsed | "
      "cache_hit | label | query | error'",
      "    1 | europepmc | ran | n_found 5 | n_new 2 | 1.1 s | cache_hit True | label search | query wt1a pronephros" in txt_sl
      and "    1 | zfin | error | n_found null (no midio) | n_new null | 2.0 s | cache_hit False | label None | TimeoutError: fake" in txt_sl
      and "ronda 1 (trigger structural, presupuesto 60.0 s): admitidos 2" in txt_sl)
_council_syn = {  # SINTETICO declarado (forma (J) de ADR-0082): la corrida offline no arma consejo
    "state": "applicable", "membership_version": "cm-1", "membership_source": "table", "n_members": 17, "full_council": True,
    "quorum_required": 9, "model": {"requested": "claude-sonnet-5", "source": "table", "effort": None}, "catalog_sha": "c" * 64,  # models-literal-doc (fixture SINTÉTICO declarado)
    "plan_catalog_matches_run": True,
    "ledger": {"state": "approved", "n_requirements": 2, "n_kept": 1, "n_discarded": 1, "n_attested": 0, "n_pending": 0, "n_hard_rule": 0,
               "approved_by": "natalia", "approved_by_is_author": True, "knowledge_now": {"present": False},
               "requirements": [{"requirement_id": "R1", "priority": "must", "gap": "expresion en pronefros", "source_family": "zfin",
                                 "evidence_kind": "expression", "n_requested_by": 9, "n_members": 17, "decision": "keep", "decided_by": "natalia"},
                                {"requirement_id": "R2", "priority": "should", "gap": "figura de ISH", "source_family": "europepmc",
                                 "evidence_kind": "figure", "n_requested_by": 3, "n_members": 17, "decision": "discard", "decided_by": "natalia",
                                 "harness_state": "unsatisfiable-by-harness (evidence_kind figure — ADR-0083)"}], "flags": []},
    "coverage": {"pre_search": {"state": "judged", "must_total": 1, "must_uncovered": 0, "must_uncovered_strict": 0, "must_partial": 0,
                                "must_not_judged": 0, "must_attested": 0, "must_discarded": 0, "must_unsatisfiable": 0, "n_hallucinated_votes": 0,
                                "class": "council-judgment",
                                "by_requirement": [{"requirement_id": "R1", "coverage_final": "covered", "n_valid_votes": 9, "n_annulled_votes": 0, "votes": []}]},
                 "after_search": {"by_requirement": [{"requirement_id": "R1", "state": "covered-pre"}], "figures_available_n": 9},
                 "post_search": {"state": "not-run (no search round)"}},
    "directives": [], "directives_state": "empty",
    "rounds": [{"round": "r2", "kind": "coverage", "phase": "run", "n_valid": 9, "n_members": 17, "state": "applicable", "n_invoked": 9,
                "n_errored": 0, "n_timeout": 0, "elapsed_s": 12.0, "usage": {"in": 900, "out": 90, "cache_creation": 100, "cache_read": 800}}],
    "cache": {"enabled": True, "ttl": "5m", "hit_ratio_r2": 0.9}}
_, txt_co = pdf_text({**REC, "council": _council_syn})
check("(K.3) council SINTETICO (declarado): ledger con decisiones, requisito 'figure' unsatisfiable-by-harness contado, cobertura pre-busqueda, "
      "figures_available_n (O.2) y ronda r2 n/N con cache",
      "LEDGER approved - 2 requisitos: 1 keep, 1 discard" in txt_co and "unsatisfiable-by-harness" in txt_co
      and "pre-busqueda covered (cubierto; 9 votos validos" in txt_co and "figuras disponibles tras buscar (ADR-0083 O.2): 9" in txt_co
      and "ronda r2 (coverage, fase run): 9/17 validos" in txt_co)

# =====================================================================================================================
# 4. (K.6) FIGURAS — registro 1.12 = frozen real + figures.attach sobre el zip fixture (bytes REALES CC BY en cache TMP)
# =====================================================================================================================
print("\n== 4. figuras: registro 1.12 con miniaturas gateadas ==")
MANIFEST = json.loads((FX / "MANIFEST.json").read_text(encoding="utf-8"))
ZIP_BY = (FX / "PMC11379296-figures.zip").read_bytes()
ZIP_NC = (FX / "PMC11647118-figures-SYNTHETIC.zip").read_bytes()
XML_BY, XML_NC = FX / "epmc_fulltext_PMC11379296_20260613.xml", FX / "epmc_fulltext_PMC11647118_20260613.xml"
CACHE_ROOT = F.cache_dir()[0]
GET_CALLS = []
_REAL_GET_BYTES = F._get_bytes


def _mk_get(zip_bytes):
    def _fake(url, timeout, max_bytes, dest=None):
        GET_CALLS.append(url)
        Path(dest).write_bytes(zip_bytes)
        return {"status": "ok", "http_status": 200, "content_length": len(zip_bytes), "content_type": "application/zip",
                "bytes": len(zip_bytes), "elapsed_s": 0.02, "url": url, "path": str(dest)}
    return _fake


def _paper(pmcid, xml_path, rank=1):
    return {"source": "europepmc", "evidence_id": pmcid, "search_rec": {"pmid": None, "pmcid": pmcid, "doi": None, "title": f"paper {pmcid}"},
            "selection_rank": rank, "fetched": {"found": True, "full_text": True, "n_chunks": 3, "raw_cached": [str(xml_path)], "raw_ref": None},
            "text_excerpt": None}


F._get_bytes = _mk_get(ZIP_BY)
FIG_BY = F.attach({"path_a": {"hits": []}, "path_b": {"papers": [_paper("PMC11379296", XML_BY)]}}, cache_root=CACHE_ROOT)
F._get_bytes = _mk_get(ZIP_NC)
FIG_NC = F.attach({"path_a": {"hits": []}, "path_b": {"papers": [_paper("PMC11647118", XML_NC)]}}, cache_root=CACHE_ROOT)
F._get_bytes = _REAL_GET_BYTES
check("figures.attach con zip fixture (fake _get_bytes, 0 red): BY n_figures 9 / n_verified 9 / n_embeddable 9; NC n_figures 6 / n_verified 5 / "
      "n_embeddable 0 / n_panel_view 5 — insumos REALES para el PDF",
      FIG_BY["n_figures"] == 9 and FIG_BY["n_verified"] == 9 and FIG_BY["n_embeddable"] == 9
      and FIG_NC["n_figures"] == 6 and FIG_NC["n_verified"] == 5 and FIG_NC["n_embeddable"] == 0 and FIG_NC["n_panel_view"] == 5
      and len(GET_CALLS) == 2, f"BY={FIG_BY['n_verified']}/{FIG_BY['n_embeddable']} NC={FIG_NC['n_verified']}/{FIG_NC['n_embeddable']}")
LENSES = ["evidence-grounding", "reproducibility"]


def _rec12(fig, cited=(0,)):
    """Registro 1.12: frozen real + figures (attach) + lo que F4 añade (vision, seen_by_lenses, cited_by_answer, cita kind figure,
    deterministic_checks.figures, saw_figures/figure_readings en dos filas del panel, by_model[*].vision) — SINTÉTICO declarado en
    la forma (L) del ADR; los bytes/sha/licencia de las figuras son MEDIDOS por attach."""
    fig = json.loads(json.dumps(fig))
    fig.pop("papers", None)
    for i, it in enumerate(fig["items"]):
        if it["bytes_state"] == "verified" and it["panel_view"]:
            it["seen_by_lenses"] = list(LENSES)
        if i in cited:
            it["cited_by_answer"] = [3]
    fig["n_cited"] = len(cited)
    fig["selection"]["n_sent_to_panel_by_lens"] = {l: fig["n_panel_view"] for l in LENSES}
    fig["vision"] = {"state": "sent", "lenses": LENSES, "lenses_source": "default-unset:WITT_FIGURES_VISION_LENSES",
                     "rule": "You may be shown figure images from the cited papers. NEVER derive numbers from the image.",
                     "openai_detail": "high", "sent": {"n_panels": 1, "n_attempts_with_images": 2, "bytes_b64_sent_total": 1700000,
                                                       "visual_tokens_projected_total": 10562},
                     "cost_projection": {"per_lens": [], "total_usd_projected": 0.019, "prices_source": "models.prices() (ADR-0081)", "class": "proyeccion"}}
    rec = json.loads(json.dumps(REC))
    rec["render_contract_version"] = "1.12"
    rec["figures"] = fig
    first = fig["items"][cited[0]] if fig["items"] else None
    if first:
        rec["citations"] = list(rec.get("citations") or []) + [
            {"n": 3, "kind": "figure", "id": first["id"], "note": "figura citada por caption", "support_state": "passage_delivered",
             "figure_verification": {"bytes": first["bytes_state"], "content": "panel-judgment", "figure_id": first["id"]}}]
    rec["deterministic_checks"] = {**rec["deterministic_checks"], "figures": {
        "state": "checked", "decided_by": "code",
        "figure_id_resolves": {"ok": True, "gating": True, "unresolved_ids": [], "n_checked": 1},
        "figure_sha_matches": {"ok": True, "gating": True, "n_checked": 1, "n_not_verifiable": 0, "mismatches": []},
        "figure_only_not_asserted": {"ok": True, "gating": True, "positive_claim": True, "absence_kind_state": "declared", "n_figure_citations": 1,
                                     "n_non_figure_citations": 1},
        "figure_numerals_grounded": {"ok": None, "gating": False, "n_marker_absent": 1, "evaluations": []},
        "figure_license_known": {"ok": True, "gating": False, "unknown": []},
        "rules": {"figure_only_not_asserted": "a positive claim whose valid citations are all kind figure is inadmissible"}}}
    rec["citations_support_summary"] = {**rec["citations_support_summary"],
                                        "figure_citations": {"n": 1, "n_verified_bytes": 1, "n_not_fetched": 0, "n_mismatch": 0, "n_unresolved": 0}}
    shas = [it["sha256"] for it in fig["items"] if it["bytes_state"] == "verified" and it["panel_view"]]
    for row in rec["audit"]["panel"]:
        if row.get("lens") in LENSES:
            row["saw_figures"] = {"n": len(shas), "sha256s": shas, "bytes_b64_total": 850000, "detail": "sent"}
            row["figure_readings"] = [{"fig_id": fig["items"][0]["fig_id"], "reading": "the panel shows what the caption says", "consistent_with_caption": True}]
            row["figure_readings_class"] = "model-judgment"
        else:
            row["saw_figures"] = {"n": 0, "sha256s": [], "bytes_b64_total": 0, "detail": "lens-not-in-vision-lenses"}
    rec["audit"]["vision"] = {"enabled": True, "lenses": LENSES, "lenses_source": "default-unset:WITT_FIGURES_VISION_LENSES",
                              "n_images_by_lens": {l: len(shas) for l in LENSES}, "bytes_b64_sent_total": 1700000}
    bm = rec["token_usage"]["by_stage"]["panel"]["by_model"]
    for r in list(bm)[:1]:
        bm[r]["vision"] = {"n_images": len(shas), "bytes_b64": 850000, "visual_tokens_projected": 5037,
                           "formula": "anthropic: sum ceil(w/28) x ceil(h/28) (tier cap)", "tier": "standard-1568", "class": "proyeccion",
                           "input_tokens_measured_includes_images": True}
    return rec


REC12 = _rec12(FIG_BY)
check("(K.1) cobertura EXACTA con un registro 1.12 (frozen real + figures): pdf_sections_cover == {missing: [], extra: []}",
      R.pdf_sections_cover(REC12.keys()) == {"missing": [], "extra": []}, f"{R.pdf_sections_cover(REC12.keys())}")
_sha1 = FIG_BY["items"][0]["sha256"]
pdf12, txt12 = pdf_text(REC12, cache_dir=CACHE_ROOT)
_g001 = MANIFEST["zips"]["PMC11379296"]["entries"][0]
check("(K.6) fixture CC BY + cache TMP + sha recalculado: 9 '/Subtype /Image' == min(n_embeddable, 12); texto con 'CC BY', 'embebible', "
      "sha[:16] del MANIFEST, dims medidas 750x417 '(== declaradas)', 'miniatura embebida' x9 con el conteo de bytes",
      n_images(pdf12) == min(FIG_BY["n_embeddable"], 12) == 9 and "CC BY (Atribuci" in txt12 and "- embebible" in txt12
      and _g001["sha256"][:16] in txt12 and _sha1 == _g001["sha256"] and "750x417 px (== declaradas)" in txt12
      and txt12.count("miniatura embebida (") == 9 and f"miniaturas embebidas: 9 ({sum(e['bytes'] for e in MANIFEST['zips']['PMC11379296']['entries'])} bytes)" in txt12
      and "leida de <ext-link>" in txt12,
      f"n_images={n_images(pdf12)} len={len(pdf12)}")
check("(K.6) 'vista por 2 lentes (evidence-grounding, reproducibility): JUICIO', 'citada como [3]', la cita kind figure con figure_verification en "
      "palabras, saw_figures del juez ('vio 9 figuras (recibio imagenes)'), LECTURAS DE IMAGEN con placa JUICIO, gate figures con 5 predicados y "
      "GATEA/informativo, figure_citations en el resumen de soporte, vision proyectada en by_model, estado VISION",
      "vista por 2 lentes (evidence-grounding, reproducibility): JUICIO" in txt12 and "citada como [3]" in txt12
      and "figura PMC11379296#pone.0307390.g001: bytes verificados por sha   -   contenido: juicio del panel" in txt12
      and "vio 9 figuras (recibio imagenes)" in txt12 and "JUICIO DEL JUEZ SOBRE LA IMAGEN" in txt12
      and "figure_id_resolves: OK - GATEA" in txt12 and "figure_numerals_grounded: null (no midio) - informativo (gating false)" in txt12
      and "citas de figura (ADR-0083): n 1 - bytes verificados 1" in txt12
      and "vision: 9 imagenes, ~5037 tokens [PROYECCION" in txt12 and "VISION: sent - las lentes con vision RECIBIERON imagenes" in txt12
      and "vio 0 figuras (lente sin vision)" in txt12)
check("(K.8) tamano acotado: el PDF 1.12 con 9 miniaturas pesa < 8 MB (tope declarado) y > la suma de sus JPEG",
      len(pdf12) < R.PDF_MAX_MB * 1024 * 1024 and len(pdf12) > sum(e["bytes"] for e in MANIFEST["zips"]["PMC11379296"]["entries"]),
      f"len={len(pdf12)} bytes")
pdf12b, _ = pdf_text(REC12, cache_dir=CACHE_ROOT)
pdf12c = R.build_pdf(REC12, compress=True, cache_dir=CACHE_ROOT, now=FIXED_NOW)
pdf12d = R.build_pdf(REC12, compress=True, cache_dir=CACHE_ROOT, now=FIXED_NOW)
check("(K.8) determinismo: dos build_pdf del mismo registro 1.12 con fecha fija -> bytes IGUALES (sin y con compresion); comprimido < sin comprimir",
      pdf12 == pdf12b and pdf12c == pdf12d and len(pdf12c) < len(pdf12), f"sin={len(pdf12)} con={len(pdf12c)}")

os.environ["WITT_FIGURES_EMBED_LICENSES"] = "cc0"
try:
    pdf_env, txt_env = pdf_text(REC12, cache_dir=CACHE_ROOT)
finally:
    os.environ.pop("WITT_FIGURES_EMBED_LICENSES", None)
check("(J.2/tabla env, corrector) WITT_FIGURES_EMBED_LICENSES=cc0 de HOY restringe una cc-by CONGELADA embebible → 0 '/Subtype /Image' (las 9 miniaturas "
      "degradan a palabras) + 'embebible al congelar; NO embebible HOY (restringida por WITT_FIGURES_EMBED_LICENSES)' + 'la misma puerta que el 403 de "
      "GET /figures'; THUMB_RULE lo declara; sin la env vuelven las 9 (dos puertas, UN veredicto)",
      n_images(pdf_env) == 0 and "embebible al congelar; NO embebible HOY (restringida por WITT_FIGURES_EMBED_LICENSES)" in txt_env
      and "la misma puerta que el 403 de GET /figures" in txt_env and txt_env.count("miniatura: embebible al congelar; NO embebible HOY") == 9
      and "WITT_FIGURES_EMBED_LICENSES de HOY" in R.THUMB_RULE and n_images(pdf_text(REC12, cache_dir=CACHE_ROOT)[0]) == 9,
      f"n_images={n_images(pdf_env)}")
REC12_NC = _rec12(FIG_NC, cited=(1,))
pdf_nc, txt_nc = pdf_text(REC12_NC, cache_dir=CACHE_ROOT)
check("(K.6) fixture NC (bytes SINTETICOS declarados): 0 imagenes; 'CC BY-NC' + 'NO embebible: caption + enlace'; 'miniatura: no embebible: cc-by-nc'; "
      "undfig1 'caption: AUSENTE' + 'no bajados (no-caption)'; mime medido image/png != extension image/jpeg declarado; '(!= declaradas)'",
      n_images(pdf_nc) == 0 and "CC BY-NC (No Comercial)" in txt_nc and "NO embebible: caption + enlace" in txt_nc
      and "miniatura: no embebible: cc-by-nc - caption + enlace https://www.ebi.ac.uk/europepmc/webservices/rest/PMC11647118/supplementaryFiles#gr1.jpg" in txt_nc
      and "caption: AUSENTE en el XML" in txt_nc and "no bajados (no-caption)" in txt_nc
      and "image/png (extension dice image/jpeg)" in txt_nc and "(!= declaradas)" in txt_nc and "leida de la URL en <license-p>" in txt_nc,
      f"n_images={n_images(pdf_nc)}")
REC12_UNK = json.loads(json.dumps(REC12))
for it in REC12_UNK["figures"]["items"]:
    it["license"] = {**it["license"], "id": "unknown", "source": "none", "rule_no": 7}
    it["embeddable"], it["panel_view"], it["seen_by_lenses"] = False, False, []
_, txt_unk = pdf_text(REC12_UNK, cache_dir=CACHE_ROOT)
check("(K.6) licencia unknown -> 'licencia desconocida' + 'NO embebible' + 'sin <permissions> legible' + 0 miniaturas + 'ninguna lente la vio'",
      "licencia desconocida" in txt_unk and "NO embebible" in txt_unk and "sin <permissions> legible" in txt_unk
      and "miniaturas embebidas: 0 (0 bytes)" in txt_unk and "ninguna lente la vio" in txt_unk)
# archivo alterado en la cache TMP (nuestra): el sha RECALCULADO no cuadra -> esa figura sin miniatura, declarada
_alt_path = CACHE_ROOT / FIG_BY["items"][2]["cache_path_rel"]
_alt_orig = _alt_path.read_bytes()
_alt_path.write_bytes(_alt_orig[:-1] + bytes([_alt_orig[-1] ^ 0xFF]))
pdf_alt, txt_alt = pdf_text(REC12, cache_dir=CACHE_ROOT)
_alt_path.write_bytes(_alt_orig)
check("(K.6) archivo alterado en cache (1 byte): esa figura 'miniatura: bytes: mismatch ... NO se embebe' y 8 imagenes (las otras siguen); "
      "restaurado el byte, vuelven 9",
      n_images(pdf_alt) == 8 and "miniatura: bytes: mismatch" in txt_alt and "NO se embebe (ADR-0077)" in txt_alt
      and n_images(pdf_text(REC12, cache_dir=CACHE_ROOT)[0]) == 9, f"n_images={n_images(pdf_alt)}")
_empty = TMP / "empty_cache"
_empty.mkdir()
pdf_emp, txt_emp = pdf_text(REC12, cache_dir=_empty)
check("(K.6) cache vacia (Dokploy efimero, E4): 0 imagenes + 'bytes no en caché del servidor' + sha 12 declarado + enlace; el registro sigue integro",
      n_images(pdf_emp) == 0 and txt_emp.count("miniatura: bytes no en caché del servidor") == 9 and _sha1[:12] in txt_emp
      and "supplementaryFiles#pone.0307390.g001.jpg" in txt_emp)
pdf_t0, txt_t0 = pdf_text(REC12, cache_dir=CACHE_ROOT, thumbs=False)
check("(M.3) thumbs=False (WITT_FIGURES_PDF_THUMBS=0): 0 imagenes + 'omitida por WITT_FIGURES_PDF_THUMBS=0' aunque la licencia permita",
      n_images(pdf_t0) == 0 and txt_t0.count("miniatura: omitida por WITT_FIGURES_PDF_THUMBS=0") == 9)
os.environ["WITT_FIGURES_PDF_THUMBS"] = "0"
pdf_env0, txt_env0 = pdf_text(REC12, cache_dir=CACHE_ROOT)
os.environ.pop("WITT_FIGURES_PDF_THUMBS", None)
pdf_env1, _ = pdf_text(REC12, cache_dir=CACHE_ROOT)
check("(M.4) la env se lee EN LA LLAMADA: WITT_FIGURES_PDF_THUMBS=0 en el entorno -> 0 imagenes con fuente 'env:WITT_FIGURES_PDF_THUMBS'; "
      "sin la env -> 9",
      n_images(pdf_env0) == 0 and "(env:WITT_FIGURES_PDF_THUMBS)" in txt_env0 and n_images(pdf_env1) == 9)
pdf_cap, txt_cap = pdf_text(REC12, cache_dir=CACHE_ROOT, pdf_max_mb=0.05)
pdf_mid, txt_mid = pdf_text(REC12, cache_dir=CACHE_ROOT, pdf_max_mb=1.0)
check("(K.6) tope del PDF forzado a 0.05 MB -> 0 imagenes, las 9 'miniatura omitida por tope de tamano del PDF' + enlace; a 1.0 MB algunas entran "
      "y el resto degrada (determinista: 3 con la reserva de 512 KB)",
      n_images(pdf_cap) == 0 and txt_cap.count("miniatura omitida por tope de tamano del PDF (0.05 MB") == 9
      and 0 < n_images(pdf_mid) < 9 and "miniatura omitida por tope de tamano del PDF (1.0 MB" in txt_mid
      and n_images(pdf_mid) == 3, f"n_cap={n_images(pdf_cap)} n_mid={n_images(pdf_mid)}")
REC12_KS = {**REC, "render_contract_version": "1.12",
            "figures": {"state": "kill-switch WITT_FIGURES=0", "module_version": "fig-1", "items": [],
                        "kill_switch": {"WITT_FIGURES": "0", "declared_exceptions": ["render_contract_version", "figures", "deterministic_checks.figures"]}},
            "deterministic_checks": {**REC["deterministic_checks"], "figures": {"state": "kill-switch WITT_FIGURES=0"}}}
_, txt_ks = pdf_text(REC12_KS, cache_dir=CACHE_ROOT)
check("(M.1) kill-switch: figures.state 'kill-switch WITT_FIGURES=0' -> glosa APAGADO + excepciones declaradas; gate figures con su estado; 0 miniaturas",
      "APAGADO por kill-switch - camino 1.11" in txt_ks and "declared_exceptions" not in txt_ks
      and "['render_contract_version', 'figures', 'deterministic_checks.figures']" in txt_ks
      and "figures (ADR-0083): estado kill-switch WITT_FIGURES=0" in txt_ks)
_, txt_nofig = pdf_text({**REC12, "figures": {**REC12["figures"], "state": "no-papers-with-xml", "items": [], "n_figures": 0, "n_verified": 0}})
check("figures.state 'no-papers-with-xml' con items [] -> glosa 'ningun paper seleccionado trajo XML' + conteos 0 [MEDICION] (0 medido != null)",
      "ningun paper seleccionado trajo XML" in txt_nofig and "figuras 0 - con caption" in txt_nofig)

# =====================================================================================================================
# 5. cero red + mcp_cache intacto
# =====================================================================================================================
print("\n== 5. offline ==")
check("(K.9) urlopen bloqueado y contado == 0 durante TODO el smoke (execute_run offline, attach con fake, 20+ PDFs)",
      NET_CALLS == [], f"net_calls={NET_CALLS[:3]}")
check("mcp_cache del repo byte-idéntico antes/después (la cache de figuras del smoke vive en TMP: %s)" % CACHE_ENV,
      _mcp_snapshot() == MCP_BEFORE and (MCP_BEFORE is None or not str(CACHE_ENV).startswith(str(REPO_CACHE))),
      "mcp_cache ausente: NO MEDIDO (declarado)" if MCP_BEFORE is None else f"n_files={len(MCP_BEFORE)}")
_urlreq.urlopen = _urlopen_real

import shutil as _shutil_f8  # noqa: E402
_shutil_f8.rmtree(FRESH_CACHE, ignore_errors=True)   # la caché del gate es efímera: nada queda en WITT_MCP_CACHE_DIR
npass = sum(CHECKS)
print("\n== %d/%d PASS ==" % (npass, len(CHECKS)))
sys.exit(0 if npass == len(CHECKS) else 1)
