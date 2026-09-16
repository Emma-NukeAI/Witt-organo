"""
smoke_figures_http.py — gate HTTP de las puertas de figuras (ADR-0083 (I), rebanada F5, contrato 1.12).

Vía ASGI TestClient (el mismo camino que la webapp — lección ADR-0075), con un frozen 1.12 SEMBRADO en la BD sqlite
temporal (F4 aún no congela: el bloque `figures` sale de figures.attach() sobre los 2 XML fixture con un `_get_bytes`
FALSO que escribe el zip fixture — bytes REALES CC BY de PMC11379296 y SINTÉTICOS CC BY-NC de PMC11647118) y la caché
de figuras en TMP (WITT_MCP_CACHE_DIR temporal: la puerta la honra igual que la etapa).

Lo que FIJA (fila `smoke_figures_http.py` de la tabla de gates NO-SPEND del ADR):
  · 401 sin sesión · 404 corrida · 409 sin frozen {state, note} · 409 identidad (question_matches_run false, la regla
    de record.pdf) · 400 sha malformado
  · ÍNDICE 200: 9 ítems `servable {state 'yes'}` medidos con verify_cached, SIN b64 ni cache_path_rel, `url` relativa
    /runs/{id}/figures/{sha}; la b64 del fixture y 'data:image' NO aparecen en el JSON; run_no, license_table_version 'lt-1'
  · BYTES 200 image/jpeg · ETag "<sha>" · X-Witt-Figure-License cc-by · X-Witt-Figure-Sha256 · Cache-Control ·
    Content-Disposition inline · body sha == path == MANIFEST · If-None-Match ⇒ 304
  · NC ⇒ índice `forbidden-by-license` (undfig1 sin sha ⇒ 'no-bytes', url null); bytes 403 con el sobre TIPADO
    {error 'not-embeddable', state, license {id, words_es, source}, reason, source_url}; zfin sintético ⇒ 403
  · sha ∉ registro ⇒ 404 · archivo borrado ⇒ 404 `bytes-not-in-cache` + refetch 'disabled (WITT_FIGURES_REFETCH_ON_GET=0)'
    (índice lo declara) · REFETCH_ON_GET=1 + fake igual ⇒ 200 + X-Witt-Figure-Refetch 'attempted: verified' (1 `_get_bytes`,
    archivo restaurado); fake DISTINTO ⇒ 409 `figure-bytes-mismatch` {expected, actual, refetch 'attempted: mismatch'} y
    NUNCA 200 después; fake que LANZA ⇒ 404 refetch 'attempted: error: …' · archivo alterado ⇒ 409 y no se sirve (índice
    `bytes-mismatch` + sha256_actual) · WITT_FIGURES_EMBED_LICENSES restringida HOY ⇒ 403 / índice 'forbidden-by-license'
    con reason declarada · kill-switch WITT_FIGURES=0 ⇒ índice state + servable 'kill-switch', bytes 404
  · frozen 1.10 (sin llave `figures`) ⇒ índice 'not-instrumented (contrato < 1.12)' items [], bytes 404
  · CORS: access-control-expose-headers trae ETag / X-Witt-Figure-* / Content-Disposition en la respuesta con Origin
  · /runs/{id}/figures no captura /runs/{id}/events · record.pdf 200 con y sin caché (build_pdf recibe cache_dir/thumbs
    sólo si su firma los declara — costura hasta F6) · /usage.figures cuenta 1 corrida con figuras · _run_view intacto:
    epistemic_summary.figures_* fluye lista == detalle · urlopen bloqueado y contado == 0 · mcp_cache real byte-idéntico

NO-SPEND: sin red, sin modelo. Máscara (una .db por smoke):
  WITT_BACKEND_DB_URL="sqlite:///C:/Users/Emmanuel/AppData/Local/Temp/claude/witt-smokes/adr83-figures-http.db"
  NEO4J_URI="" RAG_BACKEND=sparse OPENAI_API_KEY="" ANTHROPIC_API_KEY="" WITT_RUN_ORIGIN=smoke WITT_MCP_CACHE_DIR=<tmp>
  python rag_index/query_service/smoke_figures_http.py
"""
import base64
import hashlib
import io
import json
import os
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "analysis" / "scripts"))
FX = HERE / "fixtures" / "figures"
TMP = Path(tempfile.mkdtemp(prefix="smoke_figures_http_"))
REPO_CACHE = ROOT / "mcp_cache"

# --- máscara offline ANTES de importar la app (misma disciplina que los otros gates) ----------------
SMOKES_DIR = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Temp" / "claude" / "witt-smokes"
SMOKES_DIR.mkdir(parents=True, exist_ok=True)
_url = os.environ.get("WITT_BACKEND_DB_URL") or f"sqlite:///{(SMOKES_DIR / 'adr83-figures-http.db').as_posix()}"
os.environ["WITT_BACKEND_DB_URL"] = _url
if _url.startswith("sqlite:///"):
    _f = Path(_url[len("sqlite:///"):])
    if _f.exists():
        _f.unlink()
os.environ["NEO4J_URI"] = ""
os.environ["RAG_BACKEND"] = "sparse"
os.environ["OPENAI_API_KEY"] = ""
os.environ["ANTHROPIC_API_KEY"] = ""
os.environ["WITT_RUN_ORIGIN"] = "smoke"
for _k in list(os.environ):
    if _k.startswith("WITT_FIGURES"):           # sin env de figuras heredada: defaults declarados (E1–E5)
        os.environ.pop(_k, None)
# F8 (integrador): raíz de caché FRESCA por corrida — mkdtemp DENTRO de WITT_MCP_CACHE_DIR (si la máscara la trae) o de TMP.
# Una raíz reutilizada haría cache-hit en attach() (0 _get_bytes) y las precondiciones del gate fallarían (F5 lo declaró
# como ruido operativo); se borra al final. La máscara sigue mandando DÓNDE (jamás <repo>/mcp_cache).
_cache_parent = Path((os.environ.get("WITT_MCP_CACHE_DIR") or "").strip() or (TMP / "mcp_cache"))
_cache_parent.mkdir(parents=True, exist_ok=True)
FRESH_CACHE = Path(tempfile.mkdtemp(prefix="figures_http_", dir=str(_cache_parent)))
os.environ["WITT_MCP_CACHE_DIR"] = str(FRESH_CACHE)
os.environ["WITT_EPMC_MIN_INTERVAL_S"] = "0.01"
os.environ["WITT_CORS_ORIGINS"] = "http://localhost:5173"   # el middleware CORS sólo se monta con orígenes declarados
ORIGIN = "http://localhost:5173"

# ---- cero red: urlopen bloqueado y CONTADO durante TODO el smoke ---------------------------------------
import urllib.request as _urlreq  # noqa: E402

_URLOPEN_CALLS = []


def _urlopen_blocked(*a, **kw):
    req = a[0] if a else kw.get("url")
    _URLOPEN_CALLS.append(getattr(req, "full_url", None) or str(req))
    raise RuntimeError("smoke_figures_http: red bloqueada")


_urlreq.urlopen = _urlopen_blocked

import db  # noqa: E402
import app as app_mod  # noqa: E402
from lib import figures as F  # noqa: E402
from lib import models  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


def _snapshot(root):
    if not root.exists():
        return None
    out = []
    for p in sorted(root.rglob("*")):
        try:
            st = p.stat()
            out.append((str(p.relative_to(root)).replace("\\", "/"), p.is_dir(), st.st_size if p.is_file() else 0, st.st_mtime_ns))
        except OSError:
            pass
    return out


SNAP_BEFORE = _snapshot(REPO_CACHE)
CHECKS = []


def check(name, cond, detail=""):
    CHECKS.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + name + (("  -> " + str(detail)[:400]) if detail else ""))


def _fin():
    n_pass = sum(CHECKS)
    print(f"\n{n_pass}/{len(CHECKS)} PASS")
    sys.exit(0 if n_pass == len(CHECKS) else 1)


def sha(b):
    return hashlib.sha256(b).hexdigest()


# ---- fixtures F1 ----------------------------------------------------------------------------------------------------
MANIFEST = json.loads((FX / "MANIFEST.json").read_text(encoding="utf-8"))
XML_BY = FX / "epmc_fulltext_PMC11379296_20260613.xml"
XML_NC = FX / "epmc_fulltext_PMC11647118_20260613.xml"
ZIP_BY = (FX / "PMC11379296-figures.zip").read_bytes()
ZIP_NC = (FX / "PMC11647118-figures-SYNTHETIC.zip").read_bytes()
MAN_BY = {e["href"]: e for e in MANIFEST["zips"]["PMC11379296"]["entries"]}
G001 = zipfile.ZipFile(io.BytesIO(ZIP_BY)).read("pone.0307390.g001.jpg")
G001_B64 = base64.b64encode(G001).decode("ascii")


def _zip_with_altered(zip_bytes, href):
    """El MISMO zip con UN byte del miembro `href` volteado (cabecera JPEG intacta: sniff/dims siguen; el sha cambia)."""
    src = zipfile.ZipFile(io.BytesIO(zip_bytes))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_STORED) as z:
        for info in src.infolist():
            data = src.read(info)
            if info.filename == href:
                b = bytearray(data)
                b[len(b) // 2] ^= 0xFF
                data = bytes(b)
            z.writestr(info.filename, data)
    return out.getvalue()


_GET_CALLS = []


def _fake_get_bytes(zip_bytes):
    """Misma firma que figures._get_bytes (url, timeout, max_bytes, dest=None): escribe el zip fixture en `dest`."""
    def fake(url, timeout, max_bytes, dest=None):
        _GET_CALLS.append(url)
        out = {"status": "ok", "http_status": 200, "content_length": len(zip_bytes), "content_type": "application/zip",
               "bytes": len(zip_bytes), "elapsed_s": 0.01, "url": url, "throttle_slept_s": 0.0}
        if dest is not None:
            part = Path(str(dest) + ".part")
            part.write_bytes(zip_bytes)
            os.replace(part, dest)
            out["path"] = str(dest)
        else:
            out["data"] = zip_bytes
        return out
    return fake


def _raising_get_bytes(url, timeout, max_bytes, dest=None):
    _GET_CALLS.append(url)
    raise RuntimeError("boom (fake que LANZA)")


def _bundle(pmcid, xml_path):
    return {"path_b": {"papers": [{"source": "europepmc", "evidence_id": f"europepmc:{pmcid}", "search_rec": {"pmcid": pmcid},
                                   "selection_rank": 1,
                                   "fetched": {"found": True, "full_text": True, "raw_cached": [str(xml_path)]}}]}}


CFG = F.env_config()
CACHE_ROOT, CACHE_SRC = F.cache_dir()
F._get_bytes = _fake_get_bytes(ZIP_BY)
FIG_BY = F.attach(_bundle("PMC11379296", XML_BY), cfg=CFG, cache_root=CACHE_ROOT)
F._get_bytes = _fake_get_bytes(ZIP_NC)
FIG_NC = F.attach(_bundle("PMC11647118", XML_NC), cfg=CFG, cache_root=CACHE_ROOT)
FIG_BY.pop("papers", None)
FIG_NC.pop("papers", None)
N_GET_AFTER_ATTACH = len(_GET_CALLS)
check("precondición F1: attach BY → 9 verificadas / 9 embebibles; NC → 6 figuras, 5 verificadas, 0 embebibles (bytes en caché TMP, "
      f"dir_source '{CACHE_SRC}')",
      FIG_BY["n_figures"] == 9 and FIG_BY["n_verified"] == 9 and FIG_BY["n_embeddable"] == 9 and FIG_NC["n_figures"] == 6
      and FIG_NC["n_verified"] == 5 and FIG_NC["n_embeddable"] == 0 and N_GET_AFTER_ATTACH == 2 and CACHE_SRC == "env",
      f"by={FIG_BY['n_verified']}/{FIG_BY['n_embeddable']} nc={FIG_NC['n_verified']}/{FIG_NC['n_embeddable']} gets={N_GET_AFTER_ATTACH}")
BY_ITEMS = {it["fig_id"]: it for it in FIG_BY["items"]}
NC_ITEMS = {it["fig_id"]: it for it in FIG_NC["items"]}
SHA_G001 = BY_ITEMS["pone.0307390.g001"]["sha256"]
SHA_G002 = BY_ITEMS["pone.0307390.g002"]["sha256"]
SHA_G003 = BY_ITEMS["pone.0307390.g003"]["sha256"]
SHA_G004 = BY_ITEMS["pone.0307390.g004"]["sha256"]
SHA_G005 = BY_ITEMS["pone.0307390.g005"]["sha256"]
SHA_NC1 = NC_ITEMS["fig1"]["sha256"]
SHA_NONE = "f" * 64                  # 64 hex válidos que NO están en ningún registro
SHA_ZFIN = "a" * 64                  # SINTÉTICO: un zfin-display-only jamás tiene bytes; el sha se inventa para probar el 403

# zfin sintético (declarado): item vía make_item con licencia zfin-display-only y sha inventado
_zfig = {"fig_id": "ZDB-FIG-SYNTH-1", "label": "Fig Z", "caption": "figura ZFIN sintética (sólo enlace)", "caption_truncated": False,
         "caption_state": "present", "caption_lang": None, "graphic_href": "zfin_synth.jpg",
         "dims_declared": {"original": None, "scaled": None}}
_zlic = {"id": "zfin-display-only", "source": "none", "evidence_text": "", "url": None, "rule_no": 7, "version": None,
         "scope": "article-level"}
ITEM_Z = F.make_item("ZFIN-SYNTH", "zfin:synth", _zfig, _zlic, F.license_flags("zfin-display-only", CFG))
ITEM_Z["sha256"], ITEM_Z["sha256_short"] = SHA_ZFIN, SHA_ZFIN[:12]
# cc-by SINTÉTICA sin bytes (jamás bajada: 'not-fetched (run-cap)', sha null) → el índice la mide 'no-bytes' (embeddable pero
# sin sha congelado que verificar; la licencia se evalúa ANTES que los bytes — orden de figures.servable_state, contrato F1)
_nbfig = dict(_zfig, fig_id="synth-nobytes", label="Fig NB", caption="figura cc-by sintética sin bytes", graphic_href="nb.jpg")
_nblic = {"id": "cc-by", "source": "ext-link", "evidence_text": "", "url": "https://creativecommons.org/licenses/by/4.0/",
          "rule_no": 2, "version": "4.0", "scope": "article-level"}
ITEM_NB = F.make_item("PMC-SYNTH", "europepmc:synth", _nbfig, _nblic, F.license_flags("cc-by", CFG),
                      bytes_row={"bytes_state": "not-fetched (run-cap)", "mime_from_extension": "image/jpeg"})
FIG_Z = dict(F.attach({"path_b": {"papers": []}}, cfg=CFG), state="attached", items=[ITEM_Z, ITEM_NB], n_figures=2)
FIG_Z.pop("papers", None)

# ---- registros congelados sembrados (plantilla mínima de smoke_precedent + `figures`) --------------------------------
_G2 = models.GENERATIONS["g2-2026-09"]["defaults"]
HAI, G4O = _G2["judge.evidence-grounding"], _G2["judge.reproducibility"]


def _rec(run_id, question, figures=None, version="1.12", identity=True):
    rec = {"run_id": run_id, "render_contract_version": version, "question": question, "user_id": "natalia",
           "question_matches_run": identity,
           "decision_state": {"state": "AUDIT_APPROVED", "may_answer_now": True},
           "retrieval_summary": {"mode": "semantic", "retrievals": 3, "aggregation": "rrf"},
           "audit": {"verdict": "APPROVE", "n_valid": 4, "panel": []},
           "answer": {"direct_answer": "respuesta sembrada", "gap_flags": []},
           "confidence": {"state": "value", "final": 0.7, "source": "stated", "pass1": 0.7},
           "citations": [], "alternatives_considered": []}
    if figures is not None:
        rec["figures"] = figures
    return rec


BYTES_BY = sum(e["bytes"] for e in MAN_BY.values())
USAGE_BY = {"input_tokens": 2000, "output_tokens": 300,
            "by_model": {HAI: {"in": 300, "out": 40}, G4O: {"in": 400, "out": 60}},
            "by_stage": {"panel": {"in": 700, "out": 100,
                                   "by_model": {HAI: {"in": 300, "out": 40,
                                                      "vision": {"n_images": 9, "visual_tokens_projected": 5037, "class": "proyección"}},
                                                G4O: {"in": 400, "out": 60,
                                                      "vision": {"n_images": 9, "visual_tokens_projected": 5525, "class": "proyección"}}}}},
            "estimated_cost_usd": 0.02, "cost_projection_complete": True,
            # contrato F4 (ADR-0083 (H)): espejo de frozen.figures en el usage_json de la corrida
            "figures": {"state": "attached", "n_figures": 9, "n_verified": 9, "n_cited": 2, "bytes_downloaded": BYTES_BY}}
USAGE_OLD = {"input_tokens": 100, "output_tokens": 10, "by_model": {}, "estimated_cost_usd": 0.001}
SUMMARY_BY = {"retrieval_mode": "graph", "verdict": "APPROVE", "confidence_state": "value", "panel_n_valid": 4,
              "figures_state": "attached", "figures_n_verified": 9, "figures_n_cited": 2}

db.init_db()
db.upsert_user("natalia", "Natalia", "medico", "pw-natalia")
RUNS = {
    "f-by":    (_rec("f-by", "¿figuras CC BY?", FIG_BY), USAGE_BY, SUMMARY_BY),
    "f-nc":    (_rec("f-nc", "¿figuras CC BY-NC?", FIG_NC), None, None),
    "f-zfin":  (_rec("f-zfin", "¿figuras zfin?", FIG_Z), None, None),
    "f-old":   (_rec("f-old", "¿registro 1.10 sin figuras?", None, version="1.10"), USAGE_OLD, None),
    "f-ident": (_rec("f-ident", "¿identidad rota?", FIG_BY, identity=False), None, None),
}
for rid, (rec, usage, summary) in RUNS.items():
    db.create_run(rid, "natalia", rec["question"])
    vals = {"state": "closed", "frozen_record_json": json.dumps(rec, ensure_ascii=False)}
    if usage is not None:
        vals["usage_json"] = json.dumps(usage, ensure_ascii=False)
    if summary is not None:
        vals["epistemic_summary_json"] = json.dumps(summary, ensure_ascii=False)
    db.update_run(rid, **vals)
db.create_run("f-run", "natalia", "¿corrida sin frozen (queued)?")

client = TestClient(app_mod.app)
r = client.post("/login", json={"username": "natalia", "password": "pw-natalia"})
assert r.status_code == 200, r.text
AUTH = {"Authorization": "Bearer " + r.json()["token"]}


def det(resp):
    try:
        return resp.json().get("detail")
    except Exception:
        return None


# =====================================================================================================================
print("\n== 1. puertas: 401 · 404 · 409 · 400 ==")
check("GET /runs/{id}/figures y /figures/{sha} sin token -> 401 (membresía antes del filesystem)",
      client.get("/runs/f-by/figures").status_code == 401
      and client.get(f"/runs/f-by/figures/{SHA_G001}").status_code == 401)
check("corrida inexistente -> 404 en índice y bytes",
      client.get("/runs/nope/figures", headers=AUTH).status_code == 404
      and client.get(f"/runs/nope/figures/{SHA_G001}", headers=AUTH).status_code == 404)
r = client.get("/runs/f-run/figures", headers=AUTH)
check("corrida sin frozen -> 409 {state, note 'no frozen record yet'} (el MISMO sobre que /record y /record.pdf)",
      r.status_code == 409 and (det(r) or {}).get("state") == "queued" and "no frozen record yet" in (det(r) or {}).get("note", ""),
      f"{r.status_code} {det(r)}")
r1, r2 = client.get("/runs/f-ident/figures", headers=AUTH), client.get(f"/runs/f-ident/figures/{SHA_G001}", headers=AUTH)
check("identidad rota (question_matches_run false) -> 409 'identity-mismatch' en índice Y bytes (la regla de record.pdf, ADR-0044)",
      r1.status_code == 409 and (det(r1) or {}).get("state") == "identity-mismatch"
      and r2.status_code == 409 and (det(r2) or {}).get("state") == "identity-mismatch", f"{det(r1)} {det(r2)}")
r = client.get("/runs/f-by/figures/XYZ", headers=AUTH)
r_up = client.get(f"/runs/f-by/figures/{SHA_G001.upper()}", headers=AUTH)
check("sha malformado (no ^[0-9a-f]{64}$; mayúsculas incluidas) -> 400 {state 'bad-sha256'}",
      r.status_code == 400 and (det(r) or {}).get("state") == "bad-sha256" and r_up.status_code == 400, f"{det(r)}")

# =====================================================================================================================
print("\n== 2. índice CC BY: 9 servable 'yes', sin b64, url relativa ==")
r = client.get("/runs/f-by/figures", headers=AUTH)
IDX = r.json() if r.status_code == 200 else {}
items = IDX.get("items") or []
check("índice 200: run_id · run_no entero · render_contract_version '1.12' · state 'attached' · n 9 · n_verified 9 · n_embeddable 9 · "
      "license_table_version 'lt-1' · cache {dir_source 'env', dir_state 'writable'}",
      r.status_code == 200 and IDX.get("run_id") == "f-by" and isinstance(IDX.get("run_no"), int)
      and IDX.get("render_contract_version") == "1.12" and IDX.get("state") == "attached" and IDX.get("n") == 9
      and IDX.get("n_verified") == 9 and IDX.get("n_embeddable") == 9 and IDX.get("license_table_version") == "lt-1"
      and IDX.get("cache") == {"dir_source": "env", "dir_state": "writable"},
      f"{r.status_code} { {k: IDX.get(k) for k in ('run_no', 'state', 'n', 'n_verified', 'n_embeddable', 'cache')} }")
_missing_root = FRESH_CACHE / "never_created_by_get"
os.environ["WITT_MCP_CACHE_DIR"] = str(_missing_root)
try:
    r_m = client.get("/runs/f-by/figures", headers=AUTH)
finally:
    os.environ["WITT_MCP_CACHE_DIR"] = str(FRESH_CACHE)
_idx_m = r_m.json() if r_m.status_code == 200 else {}
check("(B.3, corrector) GET índice con WITT_MCP_CACHE_DIR apuntando a un dir INEXISTENTE → 200, cache {dir_source 'env', dir_state 'missing'} MEDIDO "
      "con create=False, los 9 servable 'bytes-not-in-cache', y el directorio NO se crea (una GET jamás escribe: la caché perezosa de F8 también "
      "en esta puerta)",
      r_m.status_code == 200 and _idx_m.get("cache") == {"dir_source": "env", "dir_state": "missing"}
      and all(it["servable"]["state"] == "bytes-not-in-cache" for it in (_idx_m.get("items") or [])) and len(_idx_m.get("items") or []) == 9
      and not _missing_root.exists() and not (_missing_root / "figures").exists(),
      f"{r_m.status_code} cache={_idx_m.get('cache')} exists={_missing_root.exists()}")
check("los 9 ítems: servable {state 'yes'} MEDIDO (verify_cached) · n_servable 9 · servable_counts {yes: 9} · url '/runs/f-by/figures/<sha>'",
      len(items) == 9 and all(it["servable"] == {"state": "yes"} for it in items) and IDX.get("n_servable") == 9
      and IDX.get("servable_counts") == {"yes": 9}
      and all(it["url"] == f"/runs/f-by/figures/{it['sha256']}" for it in items),
      f"{[it['servable'] for it in items][:3]} {items[0].get('url') if items else None}")
expected_keys = (set(F.FIGURE_ITEM_KEYS) - {"cache_path_rel"}) | {"servable", "url"}
check("forma del ítem = FigureItem público (FIGURE_ITEM_KEYS sin cache_path_rel) + servable + url; jamás b64 / cache_path / data / raw bytes",
      all(set(it) == expected_keys for it in items)
      and not any(k in it for it in items for k in ("b64", "cache_path", "cache_path_rel", "data", "bytes_b64")),
      f"{sorted(set(items[0]) ^ expected_keys) if items else 'sin ítems'}")
check("nada binario en el índice: la b64 del fixture (g001) y 'data:image' NO aparecen en el JSON servido (ADR-0074)",
      G001_B64[:64] not in r.text and "data:image" not in r.text)
g1 = next((it for it in items if it["fig_id"] == "pone.0307390.g001"), {})
check("g001: sha256 == MANIFEST · sha256_short 12 · licencia {id cc-by, source ext-link} · embeddable true · media_type image/jpeg · "
      "dims_measured 750×417 · caption presente · class medición",
      g1.get("sha256") == MAN_BY["pone.0307390.g001.jpg"]["sha256"] and g1.get("sha256_short") == g1.get("sha256", "")[:12]
      and (g1.get("license") or {}).get("id") == "cc-by" and g1["license"].get("source") == "ext-link" and g1.get("embeddable") is True
      and g1.get("media_type") == "image/jpeg" and g1.get("dims_measured") == {"w": 750, "h": 417}
      and g1.get("caption_state") == "present" and g1.get("class") == F.FIGURE_CLASS, f"{ {k: g1.get(k) for k in ('sha256_short', 'license', 'dims_measured')} }")
check("vocabulario: todo servable.state ∈ figures.SERVABLE_STATES y el índice lo exporta (vocabulary.SERVABLE_STATES) con la regla en palabras",
      all(it["servable"]["state"] in F.SERVABLE_STATES for it in items)
      and IDX.get("vocabulary", {}).get("SERVABLE_STATES") == list(F.SERVABLE_STATES) and IDX.get("servable_rule") == app_mod.FIGURE_SERVABLE_RULE)

# =====================================================================================================================
print("\n== 3. bytes CC BY: 200 con cabeceras; 304; sha del body ==")
r = client.get(f"/runs/f-by/figures/{SHA_G001}", headers=AUTH)
h = {k.lower(): v for k, v in r.headers.items()}
check("bytes 200 · Content-Type image/jpeg (media_type MEDIDO por magic) · body sha == sha del path == MANIFEST g001 · 189021 B",
      r.status_code == 200 and h.get("content-type", "").startswith("image/jpeg") and sha(r.content) == SHA_G001
      and SHA_G001 == MAN_BY["pone.0307390.g001.jpg"]["sha256"] and len(r.content) == 189021,
      f"{r.status_code} {h.get('content-type')} {len(r.content)}")
check('cabeceras: ETag "<sha>" · X-Witt-Figure-License cc-by · X-Witt-Figure-Sha256 == sha · Cache-Control "private, max-age=86400" · '
      'Content-Disposition inline; filename="PMC11379296_pone.0307390.g001.jpg"',
      h.get("etag") == f'"{SHA_G001}"' and h.get("x-witt-figure-license") == "cc-by" and h.get("x-witt-figure-sha256") == SHA_G001
      and h.get("cache-control") == "private, max-age=86400"
      and h.get("content-disposition") == 'inline; filename="PMC11379296_pone.0307390.g001.jpg"',
      f"{ {k: h.get(k) for k in ('etag', 'x-witt-figure-license', 'x-witt-figure-sha256', 'cache-control', 'content-disposition')} }")
check("sin refetch no viaja X-Witt-Figure-Refetch (sólo cuando WITT_FIGURES_REFETCH_ON_GET=1 rebajó y verificó)",
      "x-witt-figure-refetch" not in h)
r304 = client.get(f"/runs/f-by/figures/{SHA_G001}", headers={**AUTH, "If-None-Match": f'"{SHA_G001}"'})
check('If-None-Match == ETag -> 304 sin cuerpo, con ETag (el sha ES la identidad de los bytes)',
      r304.status_code == 304 and not r304.content and r304.headers.get("etag") == f'"{SHA_G001}"', f"{r304.status_code}")
check("cero red en las GET: _get_bytes NO se llamó (REFETCH_ON_GET=0 default) y urlopen sigue en 0",
      len(_GET_CALLS) == N_GET_AFTER_ATTACH and len(_URLOPEN_CALLS) == 0, f"gets={len(_GET_CALLS)} urlopen={len(_URLOPEN_CALLS)}")

# =====================================================================================================================
print("\n== 4. CC BY-NC y zfin: forbidden-by-license, 403 tipado ==")
r = client.get("/runs/f-nc/figures", headers=AUTH)
NC = r.json() if r.status_code == 200 else {}
nc_items = {it["fig_id"]: it for it in (NC.get("items") or [])}
check("índice NC 200: 6 ítems · n_embeddable 0 · n_verified 5 · los 6 servable 'forbidden-by-license' (la licencia se evalúa ANTES que los "
      "bytes: undfig1 sin caption ni sha también cae ahí, con url null) · n_servable 0 · servable_counts {forbidden-by-license: 6}",
      r.status_code == 200 and NC.get("n") == 6 and NC.get("n_embeddable") == 0 and NC.get("n_verified") == 5
      and all(nc_items[f"fig{i}"]["servable"] == {"state": "forbidden-by-license"} for i in range(1, 6))
      and nc_items.get("undfig1", {}).get("servable") == {"state": "forbidden-by-license"}
      and nc_items.get("undfig1", {}).get("sha256") is None and nc_items.get("undfig1", {}).get("url") is None
      and NC.get("n_servable") == 0 and NC.get("servable_counts") == {"forbidden-by-license": 6},
      f"{NC.get('servable_counts')} undfig1={nc_items.get('undfig1', {}).get('servable')}")
r = client.get("/runs/f-zfin/figures", headers=AUTH)
z_items = {it["fig_id"]: it for it in (r.json().get("items") or [])} if r.status_code == 200 else {}
check("índice de sintéticos: zfin-display-only -> servable 'forbidden-by-license' (embeddable false; bytes_state 'never (zfin-display-only)'); "
      "cc-by SIN sha (not-fetched (run-cap)) -> servable 'no-bytes' con url null (embebible pero sin sha congelado que verificar)",
      r.status_code == 200 and z_items.get("ZDB-FIG-SYNTH-1", {}).get("servable") == {"state": "forbidden-by-license"}
      and z_items["ZDB-FIG-SYNTH-1"]["bytes_state"] == "never (zfin-display-only)"
      and z_items.get("synth-nobytes", {}).get("servable") == {"state": "no-bytes"} and z_items["synth-nobytes"]["url"] is None
      and z_items["synth-nobytes"]["embeddable"] is True and z_items["synth-nobytes"]["bytes_state"] == "not-fetched (run-cap)",
      f"{r.status_code} { {k: (v.get('servable'), v.get('bytes_state')) for k, v in z_items.items()} }")
r = client.get(f"/runs/f-nc/figures/{SHA_NC1}", headers=AUTH)
d = det(r) or {}
check("bytes NC -> 403 sobre TIPADO {error 'not-embeddable', state 'forbidden-by-license', license {id cc-by-nc, words_es, source license-p-url}, "
      "reason (words_es), source_url '…/PMC11647118/supplementaryFiles#gr1.jpg', sha256, license_table_version 'lt-1'}; sin cuerpo binario",
      r.status_code == 403 and d.get("error") == "not-embeddable" and d.get("state") == "forbidden-by-license"
      and (d.get("license") or {}).get("id") == "cc-by-nc" and d["license"].get("source") == "license-p-url"
      and d["license"].get("words_es") == F.LICENSE_TABLE["cc-by-nc"]["words_es"] and d.get("reason") == d["license"]["words_es"]
      and str(d.get("source_url", "")).endswith("/PMC11647118/supplementaryFiles#gr1.jpg") and d.get("sha256") == SHA_NC1
      and d.get("license_table_version") == "lt-1" and "image" not in r.headers.get("content-type", ""),
      f"{r.status_code} {d}")
r = client.get(f"/runs/f-zfin/figures/{SHA_ZFIN}", headers=AUTH)
d = det(r) or {}
check("zfin-display-only SINTÉTICO -> 403 con license.id 'zfin-display-only' y words_es 'jamás bytes' (la tabla cerrada gobierna, ZFIN incluido)",
      r.status_code == 403 and (d.get("license") or {}).get("id") == "zfin-display-only"
      and "jamás bytes" in (d["license"].get("words_es") or ""), f"{r.status_code} {d}")
r = client.get(f"/runs/f-by/figures/{SHA_NONE}", headers=AUTH)
check("sha bien formado pero ∉ registro -> 404 {state 'no such figure in this record', sha256}",
      r.status_code == 404 and (det(r) or {}).get("state") == "no such figure in this record" and (det(r) or {}).get("sha256") == SHA_NONE,
      f"{r.status_code} {det(r)}")

# =====================================================================================================================
print("\n== 5. caché efímera: borrado → 404 declarado; refetch encendido: verificado / mismatch / error ==")
p_g003 = CACHE_ROOT / "PMC11379296" / "pone.0307390.g003.jpg"
p_g003.unlink()
r = client.get(f"/runs/f-by/figures/{SHA_G003}", headers=AUTH)
d = det(r) or {}
idx = {it["fig_id"]: it for it in client.get("/runs/f-by/figures", headers=AUTH).json()["items"]}
check("archivo borrado (caché efímera, Context 10) -> 404 {state 'bytes-not-in-cache', source_url, sha256, refetch 'disabled "
      "(WITT_FIGURES_REFETCH_ON_GET=0)'} y el índice lo DECLARA servable 'bytes-not-in-cache' (n_servable 8) — nada se rellena",
      r.status_code == 404 and d.get("state") == "bytes-not-in-cache" and d.get("refetch") == "disabled (WITT_FIGURES_REFETCH_ON_GET=0)"
      and d.get("sha256") == SHA_G003 and str(d.get("source_url", "")).endswith("#pone.0307390.g003.jpg")
      and idx["pone.0307390.g003"]["servable"] == {"state": "bytes-not-in-cache"}
      and idx["pone.0307390.g002"]["servable"] == {"state": "yes"}, f"{r.status_code} {d}")
os.environ["WITT_FIGURES_REFETCH_ON_GET"] = "1"
F._get_bytes = _fake_get_bytes(ZIP_BY)
n0 = len(_GET_CALLS)
r = client.get(f"/runs/f-by/figures/{SHA_G003}", headers=AUTH)
h = {k.lower(): v for k, v in r.headers.items()}
check("REFETCH_ON_GET=1 + fake IGUAL -> 200 image/jpeg · body sha == congelado · X-Witt-Figure-Refetch 'attempted: verified' · UNA llamada a "
      "_get_bytes (la MISMA costura de la etapa) · archivo restaurado en caché con el sha congelado",
      r.status_code == 200 and sha(r.content) == SHA_G003 and h.get("x-witt-figure-refetch") == "attempted: verified"
      and len(_GET_CALLS) == n0 + 1 and p_g003.is_file() and sha(p_g003.read_bytes()) == SHA_G003,
      f"{r.status_code} gets={len(_GET_CALLS) - n0} refetch={h.get('x-witt-figure-refetch')}")
p_g004 = CACHE_ROOT / "PMC11379296" / "pone.0307390.g004.jpg"
p_g004.unlink()
F._get_bytes = _fake_get_bytes(_zip_with_altered(ZIP_BY, "pone.0307390.g004.jpg"))
r = client.get(f"/runs/f-by/figures/{SHA_G004}", headers=AUTH)
d = det(r) or {}
check("REFETCH_ON_GET=1 + fake DISTINTO -> 409 {state 'figure-bytes-mismatch', expected == congelado, actual ≠, refetch 'attempted: mismatch'}: "
      "JAMÁS se sirve un byte que no cuadre con el sha congelado",
      r.status_code == 409 and d.get("state") == "figure-bytes-mismatch" and d.get("expected") == SHA_G004
      and isinstance(d.get("actual"), str) and d["actual"] != SHA_G004 and d.get("refetch") == "attempted: mismatch"
      and "image" not in r.headers.get("content-type", ""), f"{r.status_code} {d}")
os.environ["WITT_FIGURES_REFETCH_ON_GET"] = "0"
r = client.get(f"/runs/f-by/figures/{SHA_G004}", headers=AUTH)
d = det(r) or {}
check("después del refetch fallido, con REFETCH=0: el archivo rebajado (sha ≠) sigue en caché -> 409 'figure-bytes-mismatch' {expected, actual}; "
      "nunca 200; el índice lo mide 'bytes-mismatch' + sha256_actual",
      r.status_code == 409 and d.get("state") == "figure-bytes-mismatch" and d.get("expected") == SHA_G004 and d.get("actual") != SHA_G004
      and client.get("/runs/f-by/figures", headers=AUTH).json()["items"][3]["servable"] == {"state": "bytes-mismatch", "sha256_actual": d.get("actual")},
      f"{r.status_code} {d}")
os.environ["WITT_FIGURES_REFETCH_ON_GET"] = "1"
p_g005 = CACHE_ROOT / "PMC11379296" / "pone.0307390.g005.jpg"
p_g005.unlink()
F._get_bytes = _raising_get_bytes
n0 = len(_GET_CALLS)
r = client.get(f"/runs/f-by/figures/{SHA_G005}", headers=AUTH)
d = det(r) or {}
check("REFETCH_ON_GET=1 + fake que LANZA -> 404 {state 'bytes-not-in-cache', refetch 'attempted: error: RuntimeError: …'}: la costura no relanza, "
      "la puerta responde tipado y el archivo NO aparece",
      r.status_code == 404 and d.get("state") == "bytes-not-in-cache" and str(d.get("refetch", "")).startswith("attempted: error: RuntimeError")
      and len(_GET_CALLS) == n0 + 1 and not p_g005.exists(), f"{r.status_code} {d}")
os.environ.pop("WITT_FIGURES_REFETCH_ON_GET", None)
F._get_bytes = _fake_get_bytes(ZIP_BY)

# =====================================================================================================================
print("\n== 6. archivo ALTERADO en caché → 409, jamás se sirve ==")
p_g002 = CACHE_ROOT / "PMC11379296" / "pone.0307390.g002.jpg"
b = bytearray(p_g002.read_bytes())
b[len(b) // 2] ^= 0xFF
p_g002.write_bytes(bytes(b))
r = client.get(f"/runs/f-by/figures/{SHA_G002}", headers=AUTH)
d = det(r) or {}
idx = {it["fig_id"]: it for it in client.get("/runs/f-by/figures", headers=AUTH).json()["items"]}
check("archivo alterado (1 byte) -> 409 {state 'figure-bytes-mismatch', expected == congelado, actual == sha(archivo alterado)} · sin cuerpo binario · "
      "índice servable {state 'bytes-mismatch', sha256_actual} (ADR-0077: sha verificado al LEER)",
      r.status_code == 409 and d.get("state") == "figure-bytes-mismatch" and d.get("expected") == SHA_G002 and d.get("actual") == sha(bytes(b))
      and "image" not in r.headers.get("content-type", "")
      and idx["pone.0307390.g002"]["servable"] == {"state": "bytes-mismatch", "sha256_actual": sha(bytes(b))}, f"{r.status_code} {d}")

# =====================================================================================================================
print("\n== 7. env de HOY: EMBED_LICENSES restringida; kill-switch ==")
os.environ["WITT_FIGURES_EMBED_LICENSES"] = "cc0"
r = client.get(f"/runs/f-by/figures/{SHA_G001}", headers=AUTH)
idx = client.get("/runs/f-by/figures", headers=AUTH).json()
os.environ.pop("WITT_FIGURES_EMBED_LICENSES", None)
check("WITT_FIGURES_EMBED_LICENSES=cc0 (restringe HOY, leída en la llamada): cc-by congelada embeddable true -> 403 y el índice 'forbidden-by-license' "
      "con reason 'restricted-by-env-now (…)' — la env sólo RESTRINGE, jamás amplía (A.3)",
      r.status_code == 403 and (det(r) or {}).get("state") == "forbidden-by-license"
      and all(it["servable"]["state"] == "forbidden-by-license" and it["servable"].get("reason", "").startswith("restricted-by-env-now")
              for it in idx["items"]) and all(it["embeddable"] is True for it in idx["items"]),
      f"{r.status_code} {idx['items'][0]['servable'] if idx.get('items') else None}")
r = client.get(f"/runs/f-by/figures/{SHA_G001}", headers=AUTH)
check("tras quitar la env, la misma GET vuelve a 200 (nada se cacheó del estado anterior)", r.status_code == 200 and sha(r.content) == SHA_G001)
os.environ["WITT_FIGURES"] = "0"
idx = client.get("/runs/f-by/figures", headers=AUTH).json()
r = client.get(f"/runs/f-by/figures/{SHA_G001}", headers=AUTH)
os.environ.pop("WITT_FIGURES", None)
check("kill-switch WITT_FIGURES=0 (HOY): índice state 'kill-switch WITT_FIGURES=0' · frozen_state 'attached' (lo congelado sigue siendo medición) · "
      "los 9 servable 'kill-switch' · n_servable 0; bytes -> 404 {state 'kill-switch WITT_FIGURES=0'}",
      idx.get("state") == "kill-switch WITT_FIGURES=0" and idx.get("frozen_state") == "attached" and idx.get("n") == 9
      and idx.get("servable_counts") == {"kill-switch": 9} and idx.get("n_servable") == 0
      and r.status_code == 404 and (det(r) or {}).get("state") == "kill-switch WITT_FIGURES=0",
      f"{idx.get('state')} {idx.get('servable_counts')} bytes={r.status_code} {det(r)}")

# =====================================================================================================================
print("\n== 8. registro 1.10: NO INSTRUMENTADO ==")
r = client.get("/runs/f-old/figures", headers=AUTH)
OLD = r.json() if r.status_code == 200 else {}
r2 = client.get(f"/runs/f-old/figures/{SHA_G001}", headers=AUTH)
check("frozen 1.10 sin llave `figures` -> índice 200 {state 'not-instrumented (contrato < 1.12)', frozen_state null, items [], n 0, n_verified null, "
      "n_embeddable null, license_table_version null} (ausencia ≠ 0 figuras); bytes -> 404 {state 'not-instrumented (contrato < 1.12)'}",
      r.status_code == 200 and OLD.get("state") == "not-instrumented (contrato < 1.12)" and OLD.get("frozen_state") is None
      and OLD.get("items") == [] and OLD.get("n") == 0 and OLD.get("n_verified") is None and OLD.get("n_embeddable") is None
      and OLD.get("license_table_version") is None and OLD.get("render_contract_version") == "1.10"
      and r2.status_code == 404 and (det(r2) or {}).get("state") == "not-instrumented (contrato < 1.12)",
      f"{r.status_code} {OLD.get('state')} bytes={r2.status_code} {det(r2)}")

# =====================================================================================================================
print("\n== 9. CORS expose_headers · rutas vecinas · record.pdf · /usage.figures · _run_view ==")
r = client.get(f"/runs/f-by/figures/{SHA_G001}", headers={**AUTH, "Origin": ORIGIN})
exposed = {x.strip().lower() for x in (r.headers.get("access-control-expose-headers") or "").split(",") if x.strip()}
check("CORS (juez 1): la respuesta de bytes con Origin trae access-control-expose-headers ⊇ {ETag, X-Witt-Figure-License, X-Witt-Figure-Sha256, "
      "X-Witt-Figure-Refetch, Content-Disposition} == app.FIGURE_EXPOSE_HEADERS y access-control-allow-origin == Origin",
      r.status_code == 200 and {h.lower() for h in app_mod.FIGURE_EXPOSE_HEADERS} <= exposed
      and {"etag", "x-witt-figure-license", "x-witt-figure-sha256", "content-disposition"} <= exposed
      and r.headers.get("access-control-allow-origin") == ORIGIN, f"{sorted(exposed)} allow={r.headers.get('access-control-allow-origin')}")
pre = client.options(f"/runs/f-by/figures/{SHA_G001}",
                     headers={"Origin": ORIGIN, "Access-Control-Request-Method": "GET", "Access-Control-Request-Headers": "authorization"})
check("preflight OPTIONS con Origin -> 200 y allow-origin/allow-methods (GET) — la webapp baja por fetch con bearer → blob, nunca <img src>",
      pre.status_code == 200 and pre.headers.get("access-control-allow-origin") == ORIGIN
      and "GET" in (pre.headers.get("access-control-allow-methods") or ""), f"{pre.status_code} {dict(pre.headers)}")
ev = client.get("/runs/f-by/events", headers=AUTH)
check("/runs/{id}/figures NO captura /runs/{id}/events (200 {events: [...]}) ni /runs/{id}/record (200 con figures)",
      ev.status_code == 200 and isinstance(ev.json().get("events"), list)
      and client.get("/runs/f-by/record", headers=AUTH).json().get("figures", {}).get("n_figures") == 9, f"{ev.status_code}")
pdf1 = client.get("/runs/f-by/record.pdf", headers=AUTH)
import inspect as _inspect  # noqa: E402
_src_pdf = _inspect.getsource(app_mod.get_record_pdf)
_idx_pdf = client.get("/runs/f-by/figures", headers=AUTH).json()
check("record.pdf 200 application/pdf CON caché: get_record_pdf llama build_pdf(rec, cache_dir=figures.cache_dir()[0], thumbs=None) "
      "DIRECTO (F8 retiró la costura inspect.signature de F5; la firma de F6 está en el árbol) y el PDF embebe EXACTAMENTE tantas miniaturas "
      "('/Subtype /Image') como ítems `servable 'yes'` declara el índice en este instante (mismo gate: embeddable ∧ archivo en caché ∧ sha "
      "recalculado == congelado; las secciones previas alteraron/borraron archivos y el PDF lo refleja, no lo disfraza) — y ≥ 1",
      pdf1.status_code == 200 and pdf1.content[:5] == b"%PDF-"
      and "build_pdf(rec, cache_dir=str(figures_mod.cache_dir()[0]), thumbs=None)" in _src_pdf
      and "_pdf_figures_kwargs" not in _src_pdf and not hasattr(app_mod, "_pdf_figures_kwargs")
      and pdf1.content.count(b"/Subtype /Image") == _idx_pdf.get("n_servable") >= 1,
      f"{pdf1.status_code} images={pdf1.content.count(b'/Subtype /Image')} n_servable={_idx_pdf.get('n_servable')} "
      f"servable_counts={_idx_pdf.get('servable_counts')}")
os.environ["WITT_FIGURES_PDF_THUMBS"] = "0"
pdf0 = client.get("/runs/f-by/record.pdf", headers=AUTH)
os.environ.pop("WITT_FIGURES_PDF_THUMBS", None)
check("WITT_FIGURES_PDF_THUMBS=0 se lee EN LA LLAMADA (thumbs=None → record_pdf lee la env y declara la fuente): 0 '/Subtype /Image' "
      "aunque la caché y la licencia lo permitan; el PDF sigue 200 (M.3)",
      pdf0.status_code == 200 and pdf0.content[:5] == b"%PDF-" and pdf0.content.count(b"/Subtype /Image") == 0,
      f"{pdf0.status_code} images={pdf0.content.count(b'/Subtype /Image')}")
U = client.get("/usage", headers=AUTH).json()
FGU = U.get("figures") or {}
check("/usage.figures: state 'measured' · n_runs_with_figures 1 · n_runs_figures_declared 1 · n_runs_without_figures_usage 1 (f-old: pre-1.12, "
      "ausencia ≠ 0) · n_figures_verified 9 · n_figures_cited 2 · bytes_downloaded == Σ MANIFEST · vision_tokens_projected_by_model "
      f"{{{HAI}: 5037, {G4O}: 5525}} · total 10562 · class PROJECTION/MEASUREMENT · totals NO suman visión",
      FGU.get("state") == "measured" and FGU.get("n_runs_with_figures") == 1 and FGU.get("n_runs_figures_declared") == 1
      and FGU.get("n_runs_without_figures_usage") == 1 and FGU.get("n_figures_verified") == 9 and FGU.get("n_figures_cited") == 2
      and FGU.get("bytes_downloaded") == BYTES_BY and FGU.get("vision_tokens_projected_by_model") == {HAI: 5037, G4O: 5525}
      and FGU.get("vision_tokens_projected_total") == 10562 and FGU.get("by_state") == {"attached": 1}
      and FGU.get("class") == app_mod.USAGE_FIGURES_CLASS and U.get("totals", {}).get("input_tokens") == 2100,
      f"{ {k: FGU.get(k) for k in ('state', 'n_runs_with_figures', 'n_runs_without_figures_usage', 'n_figures_verified', 'bytes_downloaded', 'vision_tokens_projected_by_model')} } totals={U.get('totals')}")
det_by = client.get("/runs/f-by", headers=AUTH).json()
lst = {row["run_id"]: row for row in client.get("/runs", headers=AUTH).json()["runs"]}
check("_run_view intacto: epistemic_summary.figures_state/figures_n_verified/figures_n_cited fluyen (passthrough del blob congelado) y lista == detalle; "
      "los blobs (frozen_record_json / usage_json) siguen fuera del renglón",
      (det_by.get("epistemic_summary") or {}).get("figures_n_verified") == 9 and det_by["epistemic_summary"].get("figures_state") == "attached"
      and det_by["epistemic_summary"] == lst.get("f-by", {}).get("epistemic_summary")
      and all(k not in det_by for k in ("frozen_record_json", "usage_json", "bundle_json")), f"{det_by.get('epistemic_summary')}")

# =====================================================================================================================
print("\n== 10. record.pdf SIN caché · cero red · mcp_cache intacto ==")
shutil.rmtree(CACHE_ROOT / "PMC11379296", ignore_errors=True)
pdf2 = client.get("/runs/f-by/record.pdf", headers=AUTH)
idx = client.get("/runs/f-by/figures", headers=AUTH).json()
check("record.pdf 200 SIN caché (Dokploy sin volumen: el PDF pasa a 'enlace + sha', honesto, no roto) y el índice declara 9 × 'bytes-not-in-cache'",
      pdf2.status_code == 200 and pdf2.content[:5] == b"%PDF-" and idx.get("servable_counts") == {"bytes-not-in-cache": 9},
      f"{pdf2.status_code} {idx.get('servable_counts')}")
check("cero red: urllib.request.urlopen bloqueado y contado == 0 en TODO el smoke", len(_URLOPEN_CALLS) == 0, f"{_URLOPEN_CALLS}")
check("mcp_cache real del repo byte-idéntico antes/después (la caché de figuras del gate vivió en TMP) — o ausente (clon limpio), declarado",
      _snapshot(REPO_CACHE) == SNAP_BEFORE, "difiere" if _snapshot(REPO_CACHE) != SNAP_BEFORE else "")

shutil.rmtree(FRESH_CACHE, ignore_errors=True)   # la caché del gate es efímera: nada queda en WITT_MCP_CACHE_DIR
shutil.rmtree(TMP, ignore_errors=True)
_fin()
