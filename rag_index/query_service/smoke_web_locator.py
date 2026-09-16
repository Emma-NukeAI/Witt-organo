"""smoke_web_locator.py — gate offline del LOCALIZADOR web (ADR-0084, rebanada W2: lib/web_locator.py).

Cubre:
  * GOLDEN del resolutor (fixtures/web_locator_urls_golden.json, >= 40 URLs fijas con expectativa A MANO + 3 lotes):
    cada URL -> located {id, kind, resolver_rule, confidence, canonical_url} | unresolved {reason}; reglas ORDENADAS
    (doi-org-path gana a doi-in-url-any-host; biorxiv con label 'preprint'; ensembl con versión recortada y declarada;
    zfin ZDB-PUB located); trampas (DOI con '.' final y ?utm, pubmed /?dopt=, PMC en ambos hosts, europepmc
    /abstract/MED/, uniprot inválida, GEO acc= no primero, host cualquiera con DOI en path -> pattern-only, sin patrón,
    ftp://, 'not a url', host fuera de la lista blanca, misma DOI en 2 URLs -> duplicate-in-response, PMID en
    existing_ids -> already-present); determinismo byte a byte; carve-out doi.org == answer_pipeline._normalize_doi.
  * provider_state x 9 combinaciones env/llave con provider_source EXACTO y unavailable_reason LITERAL (off explícito o
    derivado == 'tool-unavailable (ADR-0084)', byte-idéntico a search_harness.SEARCH_DISPATCH['web'] @ 7d9ce15).
  * env_config tolerante: 17 filas, defaults de la tabla del ADR, basura -> default con 'default-invalid-env', clamp declarado.
  * locate(): secuencia caché -> cuota -> proveedor -> resolver -> registro con spies (quota_fn que niega -> skipped-cap
    SIN llamar al proveedor; cache_probe positivo -> cuota NO reservada; proveedor que lanza -> fila error; auth -> is_auth_error).
  * alterno Anthropic con fixture SINTÉTICO (_post_json parcheada): cuerpo SIN tool_choice y con allowed_domains == lista;
    URLs de web_search_tool_result + citations (dedup); encrypted_content / cited_text / prosa del modelo AUSENTES por
    substring; web_search_requests y tokens MEDIDOS; input.query != directiva -> query_altered_by_provider; variantes
    (error object -> error max_uses_exceeded; 400 «not enabled» -> tool-unavailable (… Console) recordado en el proceso;
    pause_turn -> provider-paused; declined -> no-match; 401 -> auth).
  * cost_of: 3 facturables brave -> 0.015 'proyección'; cache_hit no factura; tokens clase 'medición'.
  * (K) NOT_ADMISSIBLE_PRECEDENTS: los 2 cachés agénticos existen (o se declara), fetch_paper._cache_lookup no los devuelve,
    grep == 0 en lib/query_service/tools (salvo este módulo y este smoke, declarados); `mcp_cache` byte-idéntico.
  * store real (resolve_id, 0 red): ENSDARG del store -> in-store (RAW), inventado -> not-in-store.

100% offline: urllib.request.urlopen bloqueado y CONTADO == 0; cero modelo; cero DB; caché en tempdir. Exit 0 = todo PASS.

Corre:  python rag_index/query_service/smoke_web_locator.py
"""
import hashlib
import json
import os
import re
import sys
import tempfile
import urllib.error
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# máscara offline (disciplina de la casa)
os.environ.setdefault("NEO4J_URI", "")
os.environ.setdefault("RAG_BACKEND", "sparse")
os.environ.setdefault("OPENAI_API_KEY", "")
os.environ.setdefault("ANTHROPIC_API_KEY", "")
os.environ.setdefault("BRAVE_API_KEY", "")
os.environ.setdefault("WITT_RUN_ORIGIN", "smoke")

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
FIX = HERE / "fixtures"
sys.path.insert(0, str(ROOT / "analysis" / "scripts"))

# ---- cero red: urlopen bloqueado y CONTADO durante TODO el smoke ---------------------------------------------------
import urllib.request as _urlreq  # noqa: E402

_NET_CALLS = []
_urlopen_real = _urlreq.urlopen


def _urlopen_blocked(*a, **kw):
    import traceback as _tb
    frames = [f for f in _tb.extract_stack()[:-1] if "urllib" not in f.filename.replace("\\", "/")]
    who = f"{Path(frames[-1].filename).name}:{frames[-1].lineno}:{frames[-1].name}" if frames else "?"
    req = a[0] if a else kw.get("url")
    url = getattr(req, "full_url", None) or str(req)
    _NET_CALLS.append(f"{who} -> {url[:120]}")
    raise RuntimeError("network blocked by smoke_web_locator (offline gate)")


_urlreq.urlopen = _urlopen_blocked

from lib import web_locator as wl  # noqa: E402
from lib import search_harness as sh  # noqa: E402
from lib import fetch_paper  # noqa: E402
from lib import models  # noqa: E402

CHECKS = []


def check(name, cond, detail=""):
    CHECKS.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + name + (("  -> " + detail) if detail else ""))


def _canon(obj):
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _fx(name):
    with open(FIX / name, encoding="utf-8") as f:
        return json.load(f)


_cache_env = (os.environ.get("WITT_MCP_CACHE_DIR") or "").strip()
TMP = Path(_cache_env) if _cache_env else Path(tempfile.mkdtemp(prefix="witt-smoke-web-locator-"))
TMP.mkdir(parents=True, exist_ok=True)
REAL_MCP = ROOT / "mcp_cache"
_MCP_BEFORE = sorted((p.name, p.stat().st_size, p.stat().st_mtime_ns) for p in REAL_MCP.glob("*")) if REAL_MCP.exists() else []

FAKE_BRAVE_KEY = "BSA-smoke-fake-key-000000000000"
FAKE_ANTH_KEY = "sk-ant-smoke-fake-key-000000000000"


def main():
    # ==================================================================================================
    # 0. identidad y vocabularios cerrados
    # ==================================================================================================
    print("\n# 0. identidad y vocabularios")
    check("MODULE_VERSION 'wl-1' y RESOLVER_VERSION 'wlr-2' (corrector: sufijos de publisher, PMC case-insensitive, europepmc /articles/)",
          wl.MODULE_VERSION == "wl-1" and wl.RESOLVER_VERSION == "wlr-2")
    check("SOURCE_STATES duplicado == search_harness.SOURCE_STATES (sin literal nuevo: skipped-cap + detail para la cuota)",
          tuple(wl.SOURCE_STATES) == tuple(sh.SOURCE_STATES), repr(sh.SOURCE_STATES))
    check("UNAVAILABLE_OFF byte-idéntico al literal de SEARCH_DISPATCH['web'].unavailable_reason @ 7d9ce15",
          wl.UNAVAILABLE_OFF == sh.SEARCH_DISPATCH["web"]["unavailable_reason"] == "tool-unavailable (ADR-0084)")
    check("RESOLVER_RULES: 12 reglas, rule_id únicos, doi-in-url-any-host la ÚLTIMA (primera que casa gana)",
          len(wl.RESOLVER_RULES) == 12 and len(set(wl.RULE_IDS)) == 12 and wl.RULE_IDS[-1] == "doi-in-url-any-host"
          and wl.RULE_IDS[0] == "doi-org-path", repr(wl.RULE_IDS))
    check("vocabularios: LOCATED_KINDS 7 · UNRESOLVED_REASONS 4 · QUOTA_STATES 5 · WEB_STATES_EXACT 5 · PROVIDERS 3 · FED_TO 4",
          len(wl.LOCATED_KINDS) == 7 and len(wl.UNRESOLVED_REASONS) == 4 and len(wl.QUOTA_STATES_EXACT) == 5
          and len(wl.WEB_STATES_EXACT) == 5 and wl.PROVIDERS == ("brave", "anthropic", "off") and len(wl.FED_TO) == 4)
    check("web_state_in_vocabulary: exactos y prefijos aceptan; basura no",
          all(wl.web_state_in_vocabulary(s) for s in wl.WEB_STATES_EXACT)
          and wl.web_state_in_vocabulary("tool-unavailable (ADR-0084: BRAVE_API_KEY unset)")
          and wl.web_state_in_vocabulary("skipped-cap (monthly cap WITT_WEB_MONTHLY_CAP=900 reached)")
          and wl.web_state_in_vocabulary("error: auth (HTTP 401)") and not wl.web_state_in_vocabulary("located!")
          and not wl.web_state_in_vocabulary(None))
    check("literales de unavailable_reason: 5, todos con el prefijo 'tool-unavailable (ADR-0084'",
          len(wl.UNAVAILABLE_REASONS) == 5 and all(s.startswith(wl.UNAVAILABLE_PREFIX) for s in wl.UNAVAILABLE_REASONS))
    check("EPMC_IDENT_RE acepta SÓLO PMID:<n> | PMC<n> | DOI:10.…; texto libre/título/URL NO (Context 4)",
          all(wl.EPMC_IDENT_RE.match(s) for s in ("PMID:15982647", "PMC2688018", "DOI:10.1242/dev.02071"))
          and not any(wl.EPMC_IDENT_RE.match(s) for s in ("wt1a pronephros", "https://doi.org/10.1/x", "10.1242/dev.02071",
                                                            "PMCID:PMC1", "15982647")))

    # ==================================================================================================
    # 1. GOLDEN del resolutor
    # ==================================================================================================
    print("\n# 1. golden del resolutor")
    G = _fx("web_locator_urls_golden.json")
    cases, batches = G["cases"], G["batches"]
    check("golden: >= 40 URLs fijas con expectativa A MANO y resolver_version == wl.RESOLVER_VERSION ('wlr-2')",
          len(cases) >= 40 and G["_golden"]["resolver_version"] == wl.RESOLVER_VERSION, f"n_cases={len(cases)}")
    n_ok = 0
    for c in cases:
        got = wl.resolve_url(c["url"], title=c["title"], **c["opts"])
        ok = _canon(got) == _canon(c["expected"])
        hand = c["hand"]
        # la expectativa A MANO también se re-verifica (el golden no se cree a sí mismo)
        if hand["outcome"] == "located":
            loc = got.get("located") or {}
            ok = ok and loc.get("id") == hand["id"] and loc.get("kind") == hand["kind"] \
                and loc.get("resolver_rule") == hand["rule"] and loc.get("confidence") == hand["confidence"]
        else:
            ok = ok and (got.get("unresolved") or {}).get("reason") == hand["reason"]
        n_ok += ok
        check(f"golden[{c['tag']}] {c['url'][:70]}", ok, "" if ok else _canon(got)[:200])
    check(f"golden: {n_ok}/{len(cases)} casos byte-idénticos a la expectativa", n_ok == len(cases))
    fake_store_map = G["_golden"]["fake_store"]
    for b in batches:
        got = wl.resolve_urls(b["results"], store=lambda k: fake_store_map.get(k), **b["opts"])
        check(f"golden lote [{b['name']}] byte-idéntico (contadores, dedup, store_state, unresolved)",
              _canon(got) == _canon(b["expected"]), "" if _canon(got) == _canon(b["expected"]) else _canon(got)[:300])
    blob = _canon({"cases": [{k: c[k] for k in ("url", "title", "opts", "tag", "hand", "expected")} for c in cases],
                   "batches": [{k: b[k] for k in ("name", "opts", "results", "store", "expected")} for b in batches]})
    check("golden: sha256 del canon == _golden.sha256 (el archivo no se editó a mano)",
          hashlib.sha256(blob.encode("utf-8")).hexdigest() == G["_golden"]["sha256"])
    runs = [_canon([wl.resolve_url(c["url"], title=c["title"], **c["opts"]) for c in cases]) for _ in range(3)]
    check("determinismo: 3 corridas del resolutor sobre las URLs del golden son byte-idénticas", len(set(runs)) == 1)
    b0 = [b for b in batches if b["name"].startswith("dedup")][0]["expected"]
    check("lote dedup: misma DOI en 2 URLs -> 2ª 'duplicate-in-response'; PMID y DOI en existing_ids -> 'already-present (existing_ids)'; "
          "n_located_new = located - dup - present",
          b0["n_duplicates_in_response"] == 1 and b0["n_already_present"] == 2
          and b0["n_located_new"] == b0["n_located"] - 1 - 2
          and [l["dedup"] for l in b0["located"]][:4] == [None, "duplicate-in-response", "already-present (existing_ids)",
                                                           "already-present (existing_ids)"])
    check("lote dedup: la 1ª aparición (doi-org-path) conserva la identidad; la 2ª (publisher, pattern-only) es la duplicada",
          b0["located"][0]["resolver_rule"] == "doi-org-path" and b0["located"][1]["resolver_rule"] == "doi-in-url-any-host"
          and b0["located"][0]["id"] == b0["located"][1]["id"])
    check("lote dedup: title_web (<= 120) viaja SÓLO en unresolved[]; ningún located lleva title_web/description",
          all("title_web" not in l and "description" not in l for l in b0["located"])
          and all("title_web" in u for u in b0["unresolved"]) and b0["unresolved"][0]["title_web"] == "Pronephros - Wikipedia"
          and b0["unresolved"][1]["title_web"] is None)

    # ==================================================================================================
    # 2. semántica de reglas, carve-out, formas
    # ==================================================================================================
    print("\n# 2. reglas, carve-out doi.org, formas nativas")
    r = wl.resolve_url("https://doi.org/10.1242/dev.02071")["located"]
    check("orden: en doi.org gana 'doi-org-path' (host-table), no la genérica", r["resolver_rule"] == "doi-org-path"
          and r["confidence"] == "host-table")
    r = wl.resolve_url("https://www.biorxiv.org/content/10.1101/2021.03.15.435418v2.full")["located"]
    check("biorxiv: DOI sin 'v2'/'.full', label 'preprint', canonical https://doi.org/<doi>",
          r["id"] == "10.1101/2021.03.15.435418" and r["label"] == "preprint" and r["canonical_url"] == "https://doi.org/10.1101/2021.03.15.435418")
    r = wl.resolve_url("https://ensembl.org/id/ENSDARG00000031420.7")["located"]
    check("ensembl: versión '.7' recortada y DECLARADA (version_stripped)", r["id"] == "ENSDARG00000031420" and r.get("version_stripped") == ".7")
    r = wl.resolve_url("https://zfin.org/action/publication/view?id=ZDB-PUB-050801-2")["located"]
    check("zfin ZDB-PUB: located kind 'zfin-curie' con 'ZFIN:' (W3 lo deja fed_to None / no-sink-in-1.13)",
          r["kind"] == "zfin-curie" and r["id"] == "ZFIN:ZDB-PUB-050801-2")
    from lib import answer_pipeline as ap
    samples = ["https://doi.org/10.1242/DEV.02071", "HTTP://DX.DOI.ORG/10.1016/J.YDBIO.2007.03.023", "doi:10.1101/2021.03.15.435418",
               "10.1002/(SICI)1097-0177(199906)215:2<143::AID-DVDY5>3.0.CO;2-K", "  ", None]
    check("carve-out: web_locator.normalize_doi == answer_pipeline._normalize_doi sobre 6 formas (réplica declarada)",
          all(wl.normalize_doi(s) == ap._normalize_doi(s) for s in samples), wl.NORMALIZE_DOI_SOURCE[:60])
    check("carve-out: el id del located de https://doi.org/<DOI> casa la llave DOI del pool (_candidate_keys) del MISMO paper",
          f"DOI:{wl.resolve_url('https://doi.org/10.1242/DEV.02071')['located']['id']}" in ap._candidate_keys({"doi": "https://doi.org/10.1242/dev.02071"}))
    lit = [c["expected"]["located"] for c in cases if "located" in c["expected"] and c["expected"]["located"]["kind"] in wl.LITERATURE_KINDS]
    check("epmc_ident: TODO located de literatura del golden da un ident que casa EPMC_IDENT_RE (PMID:n | PMCn | DOI:10.…)",
          lit and all(wl.EPMC_IDENT_RE.match(wl.epmc_ident(l) or "") for l in lit), f"n={len(lit)}")
    nonlit = [c["expected"]["located"] for c in cases if "located" in c["expected"] and c["expected"]["located"]["kind"] not in wl.LITERATURE_KINDS]
    check("epmc_ident: kinds no-literatura (zfin/ensdarg/uniprot/gse) -> None (jamás van a _resolve_one)",
          nonlit and all(wl.epmc_ident(l) is None for l in nonlit), f"n={len(nonlit)}")
    check("_ident_query de fetch_paper entiende los 3 idents que emite epmc_ident (pmid/pmcid/doi, sin texto libre)",
          fetch_paper._ident_query("PMID:15982647")[1] == {"pmid": "15982647"}
          and fetch_paper._ident_query("PMC2688018")[1] == {"pmcid": "PMC2688018"}
          and fetch_paper._ident_query("DOI:10.1242/dev.02071")[1] == {"doi": "10.1242/dev.02071"})
    check("identifier_provenance -> 'web-located:<rule_id>'", wl.identifier_provenance({"resolver_rule": "pubmed-path"}) == "web-located:pubmed-path")
    canon_ok = all(re.match(r"^https://(doi\.org|pubmed\.ncbi\.nlm\.nih\.gov|europepmc\.org)/", l["canonical_url"]) for l in lit)
    pub = wl.resolve_url("https://onlinelibrary.wiley.com/doi/10.1002/dvdy.24132")["located"]
    check("canonical_url de literatura ∈ doi.org | pubmed | europepmc y JAMÁS la URL hallada (publisher -> https://doi.org/<doi>)",
          canon_ok and pub["canonical_url"] == "https://doi.org/10.1002/dvdy.24132" and pub["canonical_url"] != pub["url"])
    forms = ["PMID:15982647", "15982647", " pmid:15982647 "]
    check("existing_id_key: PMID en 3 formas -> 'PMID:15982647'; PMCID:/PMC -> 'PMC…'; DOI:/https://doi.org/ -> doi minúsculas; EPMC:x -> None",
          all(wl.existing_id_key(f) == "PMID:15982647" for f in forms)
          and wl.existing_id_key("PMCID:PMC2688018") == wl.existing_id_key("pmc2688018") == "PMC2688018"
          and wl.existing_id_key("DOI:10.1242/DEV.02071") == wl.existing_id_key("https://doi.org/10.1242/dev.02071") == "10.1242/dev.02071"
          and wl.existing_id_key("EPMC:PPR123") is None and wl.existing_id_key("") is None)
    check("host_allowed: sufijo de host (pmc.ncbi.nlm.nih.gov ⊂ ncbi.nlm.nih.gov); 'notncbi.nlm.nih.gov' NO; lista vacía = todo",
          wl.host_allowed("pmc.ncbi.nlm.nih.gov", ["ncbi.nlm.nih.gov"]) and not wl.host_allowed("notncbi.nlm.nih.gov", ["ncbi.nlm.nih.gov"])
          and wl.host_allowed("anything.org", None) and wl.host_allowed("anything.org", []))
    long_title = "T" * 500
    u = wl.resolve_url("https://en.wikipedia.org/wiki/Pronephros", title=long_title)["unresolved"]
    check("unresolved.title_web recortado a 120 chars (SÓLO aquí viaja un título del buscador)", len(u["title_web"]) == 120)
    # store REAL (resolve_id, 0 red)
    st_raw = wl.store_state("ensdarg", "ENSDARG00000031420")
    st_none = wl.store_state("ensdarg", "ENSDARG00000000001")
    check("store real: ENSDARG00000031420 (wt1a) -> 'in-store (RAW)'; inventado -> 'not-in-store'; kinds no-store -> None",
          st_raw == "in-store (RAW)" and st_none == "not-in-store" and wl.store_state("doi", "10.1/x") is None, f"{st_raw} / {st_none}")

    def _boom(_k):
        raise OSError("store unreadable")
    check("store que lanza -> 'store-unavailable (OSError)' declarado (jamás se finge ausencia)",
          wl.store_state("uniprot", "Q90X47", store=_boom) == "store-unavailable (OSError)"
          and wl.store_state_in_vocabulary("store-unavailable (OSError)") and wl.store_state_in_vocabulary("in-store (DERIVED)"))
    check("resolve_urls acepta str y dict; n_results cuenta ambos; entrada None/[] -> ceros",
          wl.resolve_urls(["https://pubmed.ncbi.nlm.nih.gov/1234567/", {"url": "https://x.org/"}])["n_results"] == 2
          and wl.resolve_urls(None)["n_located"] == 0 and wl.resolve_urls([])["n_unresolved"] == 0)

    # ==================================================================================================
    # 3. provider_state × combinaciones
    # ==================================================================================================
    print("\n# 3. provider_state")
    wl._reset_process_memory()
    combos = [
        ({}, "off", "default-derived:BRAVE_API_KEY absent", False, wl.UNAVAILABLE_OFF, wl.UNAVAILABLE_BRAVE_NO_KEY),
        ({"BRAVE_API_KEY": FAKE_BRAVE_KEY}, "brave", "default-derived:BRAVE_API_KEY present", True, None, None),
        ({"WITT_WEB_LOCATOR": "off", "BRAVE_API_KEY": FAKE_BRAVE_KEY}, "off", "env:WITT_WEB_LOCATOR", False, wl.UNAVAILABLE_OFF, wl.WEB_KILL_SWITCH_STATE),
        ({"WITT_WEB_LOCATOR": "brave"}, "brave", "env:WITT_WEB_LOCATOR", False, wl.UNAVAILABLE_BRAVE_NO_KEY, wl.UNAVAILABLE_BRAVE_NO_KEY),
        ({"WITT_WEB_LOCATOR": "brave", "BRAVE_API_KEY": FAKE_BRAVE_KEY}, "brave", "env:WITT_WEB_LOCATOR", True, None, None),
        ({"WITT_WEB_LOCATOR": "anthropic"}, "anthropic", "env:WITT_WEB_LOCATOR", False, wl.UNAVAILABLE_ANTHROPIC_NO_KEY, wl.UNAVAILABLE_ANTHROPIC_NO_KEY),
        ({"WITT_WEB_LOCATOR": "anthropic", "ANTHROPIC_API_KEY": FAKE_ANTH_KEY}, "anthropic", "env:WITT_WEB_LOCATOR", True, None, None),
        ({"WITT_WEB_LOCATOR": "duckduckgo", "BRAVE_API_KEY": FAKE_BRAVE_KEY}, "off", "default-invalid-env:WITT_WEB_LOCATOR", False, wl.UNAVAILABLE_OFF, wl.UNAVAILABLE_INVALID_ENV),
        ({"WITT_WEB_LOCATOR": "  BRAVE ", "BRAVE_API_KEY": FAKE_BRAVE_KEY}, "brave", "env:WITT_WEB_LOCATOR", True, None, None),
    ]
    for env, prov, src, avail, reason, frozen_state in combos:
        ps = wl.provider_state(env=env)
        ok = ps["provider"] == prov and ps["provider_source"] == src and ps["available"] is avail \
            and ps["unavailable_reason"] == reason and wl.state_when_not_run(ps) == frozen_state
        check(f"provider_state({ {k: ('<key>' if 'KEY' in k else v) for k, v in env.items()} }) -> {prov} · {src} · available={avail}"
              f" · reason={reason!r} · frozen_state={frozen_state!r}", ok, "" if ok else repr(ps))
    ps = wl.provider_state(env={"WITT_WEB_LOCATOR": "anthropic", "ANTHROPIC_API_KEY": FAKE_ANTH_KEY})
    check("provider_state: key_present sólo PRESENCIA (bool), jamás el valor; env_raw es el literal crudo de WITT_WEB_LOCATOR",
          ps["key_present"] == {"brave": False, "anthropic": True} and FAKE_ANTH_KEY not in json.dumps(ps) and ps["env_raw"] == "anthropic")
    wl._PROCESS_MEMORY["anthropic_disabled"] = True
    ps = wl.provider_state(env={"WITT_WEB_LOCATOR": "anthropic", "ANTHROPIC_API_KEY": FAKE_ANTH_KEY})
    check("provider_state: 400 «not enabled» recordado en el proceso -> anthropic no disponible con literal '… Console)'",
          not ps["available"] and ps["unavailable_reason"] == wl.UNAVAILABLE_ANTHROPIC_DISABLED)
    wl._reset_process_memory()

    # ==================================================================================================
    # 4. env_config tolerante
    # ==================================================================================================
    print("\n# 4. env_config")
    ADR_TABLE = {"WITT_WEB_LOCATOR": "", "WITT_WEB_MAX_RESULTS": "10", "WITT_WEB_MAX_QUERIES": "3", "WITT_WEB_MAX_MATERIALIZE": "6",
                 "WITT_WEB_MAX_QUERY_CHARS": "400", "WITT_WEB_BUDGET_S": "30", "WITT_WEB_MIN_INTERVAL_S": "1.0", "WITT_WEB_COUNTRY": "",
                 "WITT_WEB_LANG": "en", "WITT_WEB_FRESHNESS": "", "WITT_WEB_ALLOWED_HOSTS": "", "WITT_WEB_GENERIC_DOI_RULE": "1",
                 "WITT_WEB_MONTHLY_CAP": "900", "WITT_WEB_TEST_QUERY": "", "WITT_ANTHROPIC_WEB_SEARCH_MAX_USES": "1",
                 "WITT_WEB_ANTHROPIC_TOOL_TYPE": "web_search_20250305", "WITT_WEB_LOCATOR_MODEL": ""}
    check("ENV_SPECS: 17 variables, EXACTAMENTE las de la tabla del ADR, defaults byte-iguales (W7 las copia a ENV_TABLE)",
          set(wl.ENV_VARS) == set(ADR_TABLE) and all(wl.ENV_DEFAULTS[k] == v for k, v in ADR_TABLE.items()), repr(sorted(set(wl.ENV_VARS) ^ set(ADR_TABLE))))
    check("ENV_SPECS: BRAVE_API_KEY y ANTHROPIC_API_KEY FUERA (secretos: sólo presencia viaja)",
          "BRAVE_API_KEY" not in wl.ENV_VARS and "ANTHROPIC_API_KEY" not in wl.ENV_VARS)
    cfg0 = wl.env_config(env={})
    exp0 = {"locator": None, "max_results": 10, "max_queries": 3, "max_materialize": 6, "max_query_chars": 400, "budget_s": 30.0,
            "min_interval_s": 1.0, "country": None, "lang": "en", "freshness": None, "allowed_hosts": None, "generic_doi": True,
            "monthly_cap": 900, "test_query": None, "anthropic_max_uses": 1, "anthropic_tool_type": "web_search_20250305",
            "locator_model": None}
    check("env vacía -> los 17 valores efectivos == defaults tipados y TODAS las fuentes 'default'",
          all(cfg0[k] == v for k, v in exp0.items()) and set(cfg0["sources"].values()) == {"default"} and cfg0["clamped"] == {},
          repr({k: cfg0[k] for k in exp0 if cfg0[k] != exp0[k]}))
    check("env vacía -> cache_dir default <repo>/mcp_cache (source 'default'); WITT_MCP_CACHE_DIR -> honrada (source 'env:…')",
          cfg0["cache_dir"] == wl.ROOT / "mcp_cache" and cfg0["cache_dir_source"] == "default"
          and wl.env_config(env={"WITT_MCP_CACHE_DIR": str(TMP)})["cache_dir"] == TMP)
    garbage = {"WITT_WEB_MAX_RESULTS": "abc", "WITT_WEB_MAX_QUERIES": "-4", "WITT_WEB_BUDGET_S": "nan", "WITT_WEB_LANG": "xx1",
               "WITT_WEB_FRESHNESS": "zz", "WITT_WEB_COUNTRY": "MEX", "WITT_WEB_GENERIC_DOI_RULE": "maybe",
               "WITT_WEB_MONTHLY_CAP": "900.5x", "WITT_WEB_LOCATOR_MODEL": "gpt-99-unknown", "WITT_WEB_LOCATOR": "bing"}   # models-literal-doc
    cfg1 = wl.env_config(env=garbage)
    check("basura -> default con 'default-invalid-env:<VAR>' (max_results, budget_s, lang, freshness, country, generic_doi, monthly_cap, locator_model, locator)",
          cfg1["max_results"] == 10 and cfg1["sources"]["max_results"] == "default-invalid-env:WITT_WEB_MAX_RESULTS"
          and cfg1["budget_s"] == 30.0 and cfg1["sources"]["budget_s"] == "default-invalid-env:WITT_WEB_BUDGET_S"
          and cfg1["lang"] == "en" and cfg1["sources"]["lang"] == "default-invalid-env:WITT_WEB_LANG"
          and cfg1["freshness"] is None and cfg1["sources"]["freshness"] == "default-invalid-env:WITT_WEB_FRESHNESS"
          and cfg1["country"] is None and cfg1["sources"]["country"] == "default-invalid-env:WITT_WEB_COUNTRY"
          and cfg1["generic_doi"] is True and cfg1["sources"]["generic_doi"] == "default-invalid-env:WITT_WEB_GENERIC_DOI_RULE"
          and cfg1["monthly_cap"] == 900 and cfg1["locator_model"] is None
          and cfg1["sources"]["locator_model"] == "default-invalid-env:WITT_WEB_LOCATOR_MODEL"
          and cfg1["locator"] is None and cfg1["sources"]["locator"] == "default-invalid-env:WITT_WEB_LOCATOR")
    check("clamp DECLARADO: MAX_QUERIES=-4 -> 1 con clamped {raw -4, clamp [1,10]} y source 'env:…' (el ADR dice clamp: se recorta)",
          cfg1["max_queries"] == 1 and cfg1["clamped"]["max_queries"] == {"raw": -4, "value": 1, "clamp": [1, 10]}
          and cfg1["sources"]["max_queries"] == "env:WITT_WEB_MAX_QUERIES")
    cfg2 = wl.env_config(env={"WITT_WEB_MAX_RESULTS": "50", "WITT_WEB_ALLOWED_HOSTS": " DOI.org ,pubmed.ncbi.nlm.nih.gov, ,europepmc.org.",
                              "WITT_WEB_FRESHNESS": "2026-01-01to2026-09-16", "WITT_WEB_COUNTRY": "mx", "WITT_WEB_LANG": "ES",
                              "WITT_WEB_LOCATOR_MODEL": "claude-sonnet-5", "WITT_WEB_LOCATOR": "anthropic", "WITT_WEB_TEST_QUERY": " wt1a pronephros "})   # models-literal-doc
    check("válidos: count 50 -> 20 (clamp); CSV de hosts saneado (minúsculas, sin vacíos, sin '.' final); freshness rango; country 'MX'; lang 'es'; "
          "modelo conocido; locator 'anthropic'; test_query recortada",
          cfg2["max_results"] == 20 and cfg2["allowed_hosts"] == ["doi.org", "pubmed.ncbi.nlm.nih.gov", "europepmc.org"]
          and cfg2["freshness"] == "2026-01-01to2026-09-16" and cfg2["country"] == "MX" and cfg2["lang"] == "es"
          and cfg2["locator_model"] == "claude-sonnet-5" and cfg2["sources"]["locator_model"] == "env:WITT_WEB_LOCATOR_MODEL"   # models-literal-doc
          and cfg2["locator"] == "anthropic" and cfg2["test_query"] == "wt1a pronephros", repr(cfg2["allowed_hosts"]))
    check("freshness: pd|pw|pm|py aceptadas; 'p1' no", all(wl.env_config(env={"WITT_WEB_FRESHNESS": f})["freshness"] == f for f in ("pd", "pw", "pm", "py"))
          and wl.env_config(env={"WITT_WEB_FRESHNESS": "p1"})["freshness"] is None)
    cfg_tt = wl.env_config(env={"WITT_WEB_ANTHROPIC_TOOL_TYPE": "web_search_20260318"})
    cfg_lang = wl.env_config(env={"WITT_WEB_LANG": ""})
    check("(corrector) WITT_WEB_ANTHROPIC_TOOL_TYPE es un VOCABULARIO cerrado (ANTHROPIC_TOOL_TYPES == ('web_search_20250305',)): "
          "'web_search_20260318' (dynamic filtering, «Qué NO se hace») -> default + 'default-invalid-env:WITT_WEB_ANTHROPIC_TOOL_TYPE'; el "
          "literal admitido pasa con 'env:…'; WITT_WEB_LANG presente y VACIA -> lang None con source 'env:WITT_WEB_LANG (empty: not sent)' "
          "(la tabla del ADR: vacío ⇒ no se envía) — ausente sigue siendo 'en' 'default'",
          wl.ANTHROPIC_TOOL_TYPES == ("web_search_20250305",) and cfg_tt["anthropic_tool_type"] == "web_search_20250305"
          and cfg_tt["sources"]["anthropic_tool_type"] == "default-invalid-env:WITT_WEB_ANTHROPIC_TOOL_TYPE"
          and wl.env_config(env={"WITT_WEB_ANTHROPIC_TOOL_TYPE": "web_search_20250305"})["sources"]["anthropic_tool_type"] == "env:WITT_WEB_ANTHROPIC_TOOL_TYPE"
          and cfg_lang["lang"] is None and cfg_lang["sources"]["lang"] == "env:WITT_WEB_LANG (empty: not sent)"
          and cfg0["lang"] == "en" and cfg0["sources"]["lang"] == "default",
          repr((cfg_tt["anthropic_tool_type"], cfg_tt["sources"]["anthropic_tool_type"], cfg_lang["lang"], cfg_lang["sources"]["lang"])))
    check("allowed_hosts_block / generic_doi_block (G.2): sin env -> value 'all (resolver table + doi-in-url on any host)'; con env -> la lista",
          wl.allowed_hosts_block(cfg0)["value"] == wl.ALLOWED_HOSTS_ALL and wl.allowed_hosts_block(cfg2)["value"] == cfg2["allowed_hosts"]
          and wl.generic_doi_block(cfg0) == {"enabled": True, "source": "default", "rule_id": "doi-in-url-any-host"})
    rr = wl.resolver_rules(generic_doi=False)
    check("resolver_rules(): 12 filas para el frozen con enabled; la genérica enabled False bajo WITT_WEB_GENERIC_DOI_RULE=0; biorxiv con label",
          len(rr) == 12 and [x for x in rr if x["rule_id"] == "doi-in-url-any-host"][0]["enabled"] is False
          and all(x["enabled"] for x in rr if x["rule_id"] != "doi-in-url-any-host")
          and [x for x in rr if x["rule_id"] == "biorxiv-doi"][0]["label"] == "preprint")

    # ==================================================================================================
    # 5. locate(): la secuencia caché -> cuota -> proveedor -> resolver -> registrar
    # ==================================================================================================
    print("\n# 5. locate()")
    ENV_BRAVE = {"BRAVE_API_KEY": FAKE_BRAVE_KEY, "WITT_MCP_CACHE_DIR": str(TMP / "cache-a")}
    (TMP / "cache-a").mkdir(parents=True, exist_ok=True)
    cfg_b = wl.env_config(env=ENV_BRAVE)
    SYN_RESULTS = [
        {"url": "https://pubmed.ncbi.nlm.nih.gov/15982647/", "title": "SYN 1", "host": "pubmed.ncbi.nlm.nih.gov", "age": None, "page_age": None},
        {"url": "https://doi.org/10.1242/dev.02071", "title": "SYN 2", "host": "doi.org", "age": None, "page_age": None},
        {"url": "https://zfin.org/ZDB-GENE-980526-558", "title": "SYN 3", "host": "zfin.org", "age": None, "page_age": None},
        {"url": "https://www.ensembl.org/Danio_rerio/Gene/Summary?g=ENSDARG00000031420", "title": "SYN 4", "host": "www.ensembl.org", "age": None, "page_age": None},
        {"url": "https://en.wikipedia.org/wiki/Pronephros", "title": "Pronephros - Wikipedia", "host": "en.wikipedia.org", "age": None, "page_age": None},
        {"url": "https://www.researchgate.net/publication/7742441_x", "title": "RG", "host": "www.researchgate.net", "age": None, "page_age": None},
    ]

    class Spy:
        def __init__(self, plan=None):
            self.calls, self.plan = [], list(plan or [])

        def provider(self, query, **kw):
            self.calls.append({"query": query, **kw})
            step = self.plan.pop(0) if self.plan else None
            if isinstance(step, Exception):
                raise step
            if isinstance(step, dict):
                return step
            return {"status": "success", "query_sent": query, "query_truncated": False, "elapsed_s": 0.31, "n_http_gets": 1,
                    "cache_hit": False, "api_key_present": True, "throttle": {"host": "api.search.brave.com", "min_interval_s": 1.0, "waited_s": 0.0},
                    "retries_429": 0, "http_status": 200, "data": {"query_original": query, "query_altered": None,
                                                                    "query_altered_by_provider": False, "n_results": len(SYN_RESULTS),
                                                                    "results": list(SYN_RESULTS)}}

    class QuotaSpy:
        def __init__(self, grant=True, n=0):
            self.calls, self.grant, self.n = [], grant, n

        def __call__(self, provider, month, cap, record=None):
            self.calls.append({"provider": provider, "month": month, "cap": cap, "record": record})
            if record is not None:
                return {"granted": None, "n_before": self.n, "n_after": self.n, "cap": cap}
            if not self.grant:
                return {"granted": False, "n_before": self.n, "n_after": self.n, "cap": cap}
            self.n += 1
            return {"granted": True, "n_before": self.n - 1, "n_after": self.n, "cap": cap}

    # 5a off -> tool-unavailable, cero llamadas
    sp, qs = Spy(), QuotaSpy()
    row = wl.locate("wt1a pronephros", wl.env_config(env={}), provider_fn=sp.provider, quota_fn=qs, env={}, round_no=1,
                    requirement_ids=["req-fff"], query_source="council-directive:req-fff")
    check("locate bajo off derivado (sin llave): provider_status 'tool-unavailable', state 'tool-unavailable (ADR-0084: BRAVE_API_KEY unset)', "
          "detail == literal de 7d9ce15, proveedor 0 llamadas, cuota 0 llamadas",
          row["provider_status"] == "tool-unavailable" and row["state"] == wl.UNAVAILABLE_BRAVE_NO_KEY and row["detail"] == wl.UNAVAILABLE_OFF
          and sp.calls == [] and qs.calls == [] and row["round"] == 1 and row["requirement_ids"] == ["req-fff"], repr(row["state"]))
    row = wl.locate("q", wl.env_config(env={"WITT_WEB_LOCATOR": "off", "BRAVE_API_KEY": FAKE_BRAVE_KEY}), provider_fn=sp.provider, quota_fn=qs,
                    env={"WITT_WEB_LOCATOR": "off", "BRAVE_API_KEY": FAKE_BRAVE_KEY})
    check("locate bajo off EXPLÍCITO: state 'kill-switch WITT_WEB_LOCATOR=off', 0 llamadas",
          row["state"] == wl.WEB_KILL_SWITCH_STATE and sp.calls == [] and qs.calls == [])
    # 5b cuota niega -> skipped-cap sin proveedor
    sp, qs = Spy(), QuotaSpy(grant=False, n=900)
    row = wl.locate("wt1a pronephros", cfg_b, provider_fn=sp.provider, quota_fn=qs, env=ENV_BRAVE)
    check("cuota niega -> provider_status 'skipped-cap', detail 'monthly cap WITT_WEB_MONTHLY_CAP=900 reached (n_queries=900, month <m>)', "
          "proveedor 0 llamadas (CERO red), quota.state 'cap-reached', state con prefijo 'skipped-cap ('",
          row["provider_status"] == "skipped-cap" and sp.calls == [] and len(qs.calls) == 1
          and row["detail"] == f"monthly cap WITT_WEB_MONTHLY_CAP=900 reached (n_queries=900, month {wl.month_utc()})"
          and row["quota"]["state"] == "cap-reached" and row["state"].startswith("skipped-cap (") and row["billable"] is False, repr(row["detail"]))
    # 5c camino normal
    sp, qs = Spy(), QuotaSpy()
    row = wl.locate("wt1a zebrafish pronephros podocyte", cfg_b, provider_fn=sp.provider, quota_fn=qs, env=ENV_BRAVE,
                    existing_ids=["PMID:15982647"], round_no=1, requirement_ids=["req-fff"], query_source="council-directive:req-fff")
    check("camino normal: proveedor 1 llamada con la query; cuota 2 llamadas (reservar ANTES con cap 900; registrar DESPUÉS con n_results y cost)",
          len(sp.calls) == 1 and sp.calls[0]["query"] == "wt1a zebrafish pronephros podocyte" and len(qs.calls) == 2
          and qs.calls[0]["record"] is None and qs.calls[0]["cap"] == 900 and qs.calls[0]["provider"] == "brave"
          and qs.calls[1]["record"] == {"n_results": 6, "cost": 0.005, "n_requests_extra": 0}, repr(qs.calls))   # corrector: extra declaradas
    check("camino normal: el proveedor recibe SÓLO kwargs de su firma (count/country/search_lang/freshness/timeout/cache_dir/cfg/requirement_ids via **kw)",
          sp.calls[0]["count"] == 10 and sp.calls[0]["search_lang"] == "en" and sp.calls[0]["country"] is None
          and sp.calls[0]["cache_dir"] == str(TMP / "cache-a"))
    check("camino normal: provider_status 'success', state 'located', n_results 6, n_located 4 (pmid ya presente, doi, zfin, ensdarg), n_unresolved 2, "
          "n_already_present 1, quota.state 'under-cap' n_after 1, cost 0.005 'proyección', billable True",
          row["provider_status"] == "success" and row["state"] == "located" and row["n_results"] == 6 and row["n_located"] == 4
          and row["n_unresolved"] == 2 and row["n_already_present"] == 1 and row["quota"]["state"] == "under-cap"
          and row["quota"]["n_after"] == 1 and row["cost"]["usd_projected"] == 0.005 and row["cost"]["class"] == "proyección"
          and row["cost_usd_projected"] == 0.005 and row["billable"] is True and row["n_billable"] == 1,
          f"located={[l['id'] for l in row['located']]} unresolved={[u['host'] for u in row['unresolved']]}")
    check("camino normal: la fila trae located[] con dedup/store_state y unresolved[] con title_web; NINGÚN located lleva title",
          [l["dedup"] for l in row["located"]] == ["already-present (existing_ids)", None, None, None]
          and row["located"][3]["store_state"] == "in-store (RAW)" and all("title_web" not in l for l in row["located"])
          and row["unresolved"][0]["title_web"] == "Pronephros - Wikipedia")
    check("camino normal: elapsed_s/throttle_wait_s/http_status/cache_hit copiados del proveedor; query_en verbatim; provider/provider_source; versiones",
          row["elapsed_s"] == 0.31 and row["throttle_wait_s"] == 0.0 and row["http_status"] == 200 and row["cache_hit"] is False
          and row["query_en"] == "wt1a zebrafish pronephros podocyte" and row["provider"] == "brave"
          and row["provider_source"] == "default-derived:BRAVE_API_KEY present" and row["resolver_version"] == "wlr-2"
          and row["module_version"] == "wl-1" and row["query_source"] == "council-directive:req-fff")
    check("camino normal: la llave fake JAMÁS aparece en la fila-query (M.5)", FAKE_BRAVE_KEY not in json.dumps(row))
    # 5d sin quota_fn / cap 0
    sp = Spy()
    row = wl.locate("q", cfg_b, provider_fn=sp.provider, env=ENV_BRAVE)
    check("sin quota_fn -> quota.state 'not-enforced (no quota callable)', el proveedor corre igual",
          row["quota"]["state"] == "not-enforced (no quota callable)" and len(sp.calls) == 1)
    sp, qs = Spy(), QuotaSpy()
    cfg_cap0 = wl.env_config(env={**ENV_BRAVE, "WITT_WEB_MONTHLY_CAP": "0"})
    row = wl.locate("q", cfg_cap0, provider_fn=sp.provider, quota_fn=qs, env=ENV_BRAVE)
    check("WITT_WEB_MONTHLY_CAP=0 -> quota.state 'disabled (WITT_WEB_MONTHLY_CAP=0)'; quota_fn se llama con cap 0 (la fila mensual se cuenta igual)",
          row["quota"]["state"] == "disabled (WITT_WEB_MONTHLY_CAP=0)" and qs.calls[0]["cap"] == 0 and len(qs.calls) == 2)
    # 5e cache_probe positivo -> cuota NO reservada
    cache_dir = TMP / "cache-a"
    stamp = __import__("time").strftime("%Y%m%d", __import__("time").gmtime())
    q_hit = "wt1a zebrafish pronephros podocyte"
    envelope = {"fetched_at": "2026-09-16T10:00:00Z",
                "url": "https://api.search.brave.com/res/v1/web/search?" + __import__("urllib.parse").parse.urlencode(
                    {"q": q_hit, "count": 10, "search_lang": "en"}),
                "headers": {}, "response": {"query": {"original": q_hit}, "web": {"results": []}},
                "cut": {"fields_dropped_from_output": ["description"]}}
    W1, _w1fn, _w1detail = wl._load_brave_tool()
    W1_PRESENT = W1 is not None and callable(getattr(W1, "cache_probe", None)) and callable(getattr(W1, "cache_path_for", None))

    def _envelope_path(cdir, q, count, lang):
        """Con W1 presente la sonda delega en la tool: el sobre va a SU ruta exacta (slug/sha8); sin W1, al escaneo."""
        if W1_PRESENT:
            return Path(W1.cache_path_for(W1.prepare(q, count=count, search_lang=lang), str(cdir)))
        return cdir / f"raw_brave_wt1a-zebrafish_deadbeef_{stamp}.json"
    epath = _envelope_path(cache_dir, q_hit, 10, "en")
    epath.write_text(json.dumps(envelope), encoding="utf-8")
    probe = wl.cache_probe(q_hit, cfg_b)
    check(f"cache_probe ({'DELEGA en brave_web_search.cache_probe: slug/sha8 exactos' if W1_PRESENT else 'escaneo de sobres: W1 ausente'}): "
          "sobre del día con los MISMOS parámetros (q, count 10, search_lang en) -> cache_hit True con cache_path/cached_at, 0 red",
          probe["cache_hit"] and Path(probe["cache_path"]).name == epath.name and probe["cached_at"] == "2026-09-16T10:00:00Z"
          and (probe["probe_method"].startswith("brave_web_search.cache_probe") if W1_PRESENT else probe["n_envelopes_scanned"] == 1), repr(probe))
    check("cache_probe: otra query o count distinto -> miss (la cuota se reserva de más, jamás de menos)",
          not wl.cache_probe("otra consulta", cfg_b)["cache_hit"]
          and not wl.cache_probe(q_hit, wl.env_config(env={**ENV_BRAVE, "WITT_WEB_MAX_RESULTS": "5"}))["cache_hit"])
    sp = Spy(plan=[{"status": "success", "query_sent": q_hit, "elapsed_s": 0.0, "n_http_gets": 0, "cache_hit": True, "api_key_present": True,
                    "data": {"query_original": q_hit, "results": list(SYN_RESULTS[:2])}}])
    qs = QuotaSpy()
    row = wl.locate(q_hit, cfg_b, provider_fn=sp.provider, quota_fn=qs, env=ENV_BRAVE)
    check("locate con cache_probe positivo: quota_fn 0 llamadas, quota.state 'not-consumed (cache-hit)', proveedor sirve de caché -> cache_hit True, "
          "n_http_gets 0 -> billable False, cost 0.0, n_located 2",
          qs.calls == [] and row["quota"]["state"] == "not-consumed (cache-hit)" and row["cache_hit"] is True and row["billable"] is False
          and row["cost_usd_projected"] == 0.0 and row["n_located"] == 2 and "cache_probe" in row)
    # 5f proveedor que lanza / error auth / skipped-budget / forma rara
    sp, qs = Spy(plan=[RuntimeError("socket boom")]), QuotaSpy()
    row = wl.locate("q", cfg_b, provider_fn=sp.provider, quota_fn=qs, env=ENV_BRAVE)
    check("proveedor que LANZA -> fila 'error' con 'RuntimeError: socket boom', state 'error: …', la cuota quedó reservada y NO se registró (1 llamada)",
          row["provider_status"] == "error" and row["error"] == "RuntimeError: socket boom" and row["state"].startswith("error: RuntimeError")
          and len(qs.calls) == 1 and row["billable"] is False and row["n_located"] is None)
    sp = Spy(plan=[{"status": "error", "http_status": 401, "error": "auth (HTTP 401)", "elapsed_s": 0.2, "n_http_gets": 1}])
    row = wl.locate("q", cfg_b, provider_fn=sp.provider, env=ENV_BRAVE)
    check("proveedor 'error: auth (HTTP 401)' -> is_auth_error True (cortacircuito de ronda para W3), http_status 401, state 'error: auth (HTTP 401)'",
          wl.is_auth_error(row) and row["http_status"] == 401 and row["state"] == "error: auth (HTTP 401)")
    sp = Spy(plan=[{"status": "skipped-budget", "reason": "timeout <= 0 (no request sent)", "elapsed_s": 0.0, "n_http_gets": 0}])
    row = wl.locate("q", cfg_b, provider_fn=sp.provider, env=ENV_BRAVE)
    check("proveedor 'skipped-budget' -> state 'skipped-budget (timeout <= 0 (no request sent))', sin resolver, sin facturar",
          row["provider_status"] == "skipped-budget" and row["state"] == "skipped-budget (timeout <= 0 (no request sent))" and row["located"] == [])
    sp = Spy(plan=[{"status": "weird"}])
    row = wl.locate("q", cfg_b, provider_fn=sp.provider, env=ENV_BRAVE)
    check("proveedor con status fuera de SOURCE_STATES -> 'error' shape-mismatch declarado",
          row["provider_status"] == "error" and row["error"].startswith("shape-mismatch"))
    sp = Spy(plan=[{"status": "no-match", "elapsed_s": 0.1, "n_http_gets": 1, "data": {"results": []}}])
    row = wl.locate("q", cfg_b, provider_fn=sp.provider, env=ENV_BRAVE)
    check("proveedor 'no-match' (buscó, 0 URLs) -> state 'no-results' con contadores 0 (medidos) y billable True (Brave cobra la petición)",
          row["provider_status"] == "no-match" and row["state"] == "no-results" and row["n_results"] == 0 and row["n_located"] == 0 and row["billable"] is True)
    sp = Spy()
    row = wl.locate("x" * 500, cfg_b, provider_fn=sp.provider, env=ENV_BRAVE)
    check("query de 500 chars -> query_sent recortada a WITT_WEB_MAX_QUERY_CHARS (400) y query_truncated True; el proveedor recibe la recortada",
          len(row["query_sent"]) == 400 and row["query_truncated"] is True and len(sp.calls[0]["query"]) == 400 and len(row["query_en"]) == 500)
    mod, fn, detail = wl._load_brave_tool()
    if fn is None:
        row = wl.locate("q", cfg_b, env=ENV_BRAVE)
        check("brave_web_search.py AUSENTE en este árbol (W1 paralela) -> locate sin provider_fn deja fila 'error' 'tool-module: …' (código, no configuración) y brave_tool_version None",
              row["provider_status"] == "error" and row["error"].startswith("tool-module:") and wl.brave_tool_version() is None, detail)
    else:
        check("brave_web_search.py presente -> locate carga `locate` por ruta y expone TOOL_VERSION", callable(fn) and wl.brave_tool_version() is not None,
              repr(wl.brave_tool_version()))
        # 5g COSTURA REAL W1<->W2 (offline): el sobre SINTÉTICO de W1 copiado a la ruta exacta de la tool -> la sonda lo ve ->
        # la cuota NO se reserva -> la tool REAL sirve de caché (0 GET, urlopen sigue bloqueado) -> el resolutor materializa ids.
        BFX = _fx("brave_web_search_SYNTHETIC_wt1a_20260916.json")
        q_w1 = BFX["_fixture"]["query_sent"]
        cnt_w1 = int(BFX["_fixture"]["count_sent"])
        cdir_w1 = TMP / "cache-w1"
        cdir_w1.mkdir(parents=True, exist_ok=True)
        ENV_W1 = {"BRAVE_API_KEY": FAKE_BRAVE_KEY, "WITT_WEB_MAX_RESULTS": str(cnt_w1), "WITT_MCP_CACHE_DIR": str(cdir_w1)}
        cfg_w1 = wl.env_config(env=ENV_W1)
        Path(mod.cache_path_for(mod.prepare(q_w1, count=cnt_w1, search_lang="en"), str(cdir_w1))).write_text(
            json.dumps({k: BFX[k] for k in ("tool_version", "fetched_at", "url", "http_status", "headers", "response", "cut")}), encoding="utf-8")
        probe_w1 = wl.cache_probe(q_w1, cfg_w1)
        qs = QuotaSpy()
        _saved = {k: os.environ.get(k) for k in ("BRAVE_API_KEY",)}
        os.environ["BRAVE_API_KEY"] = FAKE_BRAVE_KEY     # la tool lee su llave de os.environ; con caché del día NO hay GET
        try:
            row_w1 = wl.locate(q_w1, cfg_w1, quota_fn=qs, env=ENV_W1, round_no=1, requirement_ids=["req-fff"])
        finally:
            for k, v in _saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
        check("costura W1<->W2: la sonda de web_locator (delegada) ve el sobre sintético de W1 en la ruta exacta de la tool",
              probe_w1["cache_hit"] and probe_w1["probe_method"].startswith("brave_web_search.cache_probe"), repr(probe_w1))
        check("costura W1<->W2: locate SIN provider_fn -> la tool REAL sirve de caché (cache_hit True, 0 GET, quota_fn 0 llamadas, "
              "'not-consumed (cache-hit)', billable False, cost 0.0) y el resolutor da 9 located / 2 unresolved (researchgate, wikipedia)",
              row_w1["provider_status"] == "success" and row_w1["cache_hit"] is True and qs.calls == []
              and row_w1["quota"]["state"] == "not-consumed (cache-hit)" and row_w1["billable"] is False and row_w1["cost_usd_projected"] == 0.0
              and row_w1["n_results"] == 11 and row_w1["n_located"] == 9 and row_w1["n_unresolved"] == 2
              and sorted(u["host"] for u in row_w1["unresolved"]) == ["en.wikipedia.org", "www.researchgate.net"],
              f"status={row_w1['provider_status']} err={row_w1.get('error')} n_located={row_w1['n_located']} located={[l['id'] for l in row_w1['located']]}")
        check("costura W1<->W2: la fila-query NO trae description/extra_snippets de la tool (corte A.3 medido aguas arriba) ni la llave; title_web sólo en unresolved (<= 120)",
              "description" not in json.dumps(row_w1) and "extra_snippets" not in json.dumps(row_w1) and FAKE_BRAVE_KEY not in json.dumps(row_w1)
              and all(len(u["title_web"] or "") <= 120 for u in row_w1["unresolved"]))
        check("costura W1<->W2: los ids de literatura localizados casan EPMC_IDENT_RE y la forma nativa del pool (PMID:n / PMCn / doi minúsculas)",
              all(wl.EPMC_IDENT_RE.match(wl.epmc_ident(l) or "") for l in row_w1["located"] if l["kind"] in wl.LITERATURE_KINDS)
              and "PMID:19666820" in [l["id"] for l in row_w1["located"]] and "PMC11042071" in [l["id"] for l in row_w1["located"]]
              and "10.1016/j.ydbio.2007.06.022" in [l["id"] for l in row_w1["located"]])

    # ==================================================================================================
    # 6. alterno Anthropic con fixture SINTÉTICO
    # ==================================================================================================
    print("\n# 6. alterno Anthropic (web_search_20250305, caller propio)")
    AFX = _fx("anthropic_web_search_SYNTHETIC_wt1a_20260916.json")
    check("fixture SINTÉTICO declarado en nombre y cuerpo (_fixture.synthetic True, live False, shape_source con la doc)",
          AFX["_fixture"]["synthetic"] is True and AFX["_fixture"]["live"] is False and "web-search-tool" in AFX["_fixture"]["shape_source"]
          and "SYNTHETIC" in Path("anthropic_web_search_SYNTHETIC_wt1a_20260916.json").name)
    check("fixture: 4 web_search_result SIN encrypted_content + texto con 2 citations + usage.server_tool_use.web_search_requests 1",
          len(AFX["response"]["content"][1]["content"]) == 4 and all("encrypted_content" not in r for r in AFX["response"]["content"][1]["content"])
          and len(AFX["response"]["content"][2]["citations"]) == 2 and AFX["response"]["usage"]["server_tool_use"]["web_search_requests"] == 1)
    ENV_A = {"WITT_WEB_LOCATOR": "anthropic", "ANTHROPIC_API_KEY": FAKE_ANTH_KEY}
    cfg_a = wl.env_config(env=ENV_A)
    directive = AFX["directive_query"]
    model, msrc = wl.anthropic_model(cfg_a, env=ENV_A)
    check("anthropic_model: sin WITT_WEB_LOCATOR_MODEL -> models.resolve_role('elicitation') (tabla única ADR-0081; NINGÚN rol nuevo en PIPELINE_ROLES)",
          model == models.resolve_role("elicitation", env=ENV_A)["model"] and msrc.startswith("models.resolve_role('elicitation')")
          and "web_locator" not in models.PIPELINE_ROLES and "elicitation" in models.PIPELINE_ROLES, f"{model} · {msrc}")
    cfg_m = wl.env_config(env={**ENV_A, "WITT_WEB_LOCATOR_MODEL": "claude-sonnet-5"})   # models-literal-doc
    check("anthropic_model: WITT_WEB_LOCATOR_MODEL válido -> ese modelo con source 'env:WITT_WEB_LOCATOR_MODEL'",
          wl.anthropic_model(cfg_m, env=ENV_A) == ("claude-sonnet-5", "env:WITT_WEB_LOCATOR_MODEL"))   # models-literal-doc
    body = wl.build_anthropic_body(directive, cfg_a, model)
    check("cuerpo: SIN tool_choice, SIN allowed_callers, SIN blocked_domains; tools == [web_search type web_search_20250305, max_uses 1]; max_tokens 256; system literal",
          "tool_choice" not in body and len(body["tools"]) == 1 and body["tools"][0]["type"] == "web_search_20250305"
          and body["tools"][0]["name"] == "web_search" and body["tools"][0]["max_uses"] == 1 and "allowed_callers" not in body["tools"][0]
          and "blocked_domains" not in body["tools"][0] and body["max_tokens"] == 256 and body["system"] == wl.ANTHROPIC_SYSTEM
          and body["messages"] == [{"role": "user", "content": directive}])
    check("cuerpo: allowed_domains == hosts de la tabla del resolutor (11, <= 20, sin esquema) cuando WITT_WEB_ALLOWED_HOSTS está vacía",
          body["tools"][0]["allowed_domains"] == list(wl.RESOLVER_TABLE_HOSTS) and len(body["tools"][0]["allowed_domains"]) <= 20
          and not any("://" in d for d in body["tools"][0]["allowed_domains"]))
    cfg_h = wl.env_config(env={**ENV_A, "WITT_WEB_ALLOWED_HOSTS": "https://pubmed.ncbi.nlm.nih.gov/,europepmc.org,pubmed.ncbi.nlm.nih.gov"})
    check("cuerpo: con WITT_WEB_ALLOWED_HOSTS -> allowed_domains == esa lista (esquema quitado, dedup, orden)",
          wl.build_anthropic_body("q", cfg_h, model)["tools"][0]["allowed_domains"] == ["pubmed.ncbi.nlm.nih.gov", "europepmc.org"])
    check("cuerpo del fixture (request.body) == build_anthropic_body para el mismo modelo (la forma documentada es la que se envía)",
          _canon(AFX["request"]["body"]) == _canon(wl.build_anthropic_body(directive, cfg_a, "claude-opus-5")))   # models-literal-doc

    posts = []
    _post_real = wl._post_json

    def _fake_post_factory(status, payload, raw=None):
        def _fake(url, body, headers, timeout, inflight=None, urlopen=None):
            posts.append({"url": url, "body": body, "headers": dict(headers), "timeout": timeout})
            return status, payload, (raw if raw is not None else json.dumps(payload))
        return _fake

    # 6a sin llave -> cero red
    posts.clear()
    prow = wl._anthropic_web_search(directive, wl.env_config(env={"WITT_WEB_LOCATOR": "anthropic"}), env={"WITT_WEB_LOCATOR": "anthropic"})
    check("sin ANTHROPIC_API_KEY -> fila 'tool-unavailable' con detail literal '… ANTHROPIC_API_KEY unset)', api_key_present False, 0 POST",
          prow["status"] == "tool-unavailable" and prow["detail"] == wl.UNAVAILABLE_ANTHROPIC_NO_KEY and prow["api_key_present"] is False and posts == [])
    # 6b fixture principal
    wl._post_json = _fake_post_factory(200, AFX["response"])
    try:
        posts.clear()
        prow = wl._anthropic_web_search(directive, cfg_a, requirement_ids=["req-fff"], env=ENV_A)
        dumped = json.dumps(prow, ensure_ascii=False)
        check("fixture principal: status 'success', 5 URLs (4 resultados + 1 cita nueva; la cita duplicada de pubmed deduplicada), hosts derivados, title <= 120",
              prow["status"] == "success" and prow["data"]["n_results"] == 5
              and [r["url"] for r in prow["data"]["results"]] == ["https://pubmed.ncbi.nlm.nih.gov/15982647/", "https://europepmc.org/article/PMC/PMC2688018",
                                                                   "https://doi.org/10.1242/dev.02071", "https://zfin.org/ZDB-GENE-980526-558",
                                                                   "https://onlinelibrary.wiley.com/doi/10.1002/dvdy.24132"]
              and prow["data"]["results"][0]["host"] == "pubmed.ncbi.nlm.nih.gov", repr([r["url"] for r in prow["data"]["results"]]))
        # la fila SIN su declaración fields_dropped (que nombra las llaves descartadas): ahí no debe quedar ni valor ni llave
        values_only = json.dumps({k: v for k, v in prow.items() if k != "data"}, ensure_ascii=False) + json.dumps(
            {k: v for k, v in prow["data"].items() if k != "fields_dropped"}, ensure_ascii=False)
        check("fixture principal: prosa del modelo, cited_text y encrypted_* AUSENTES por substring (valores Y llaves, fuera de la declaración fields_dropped); "
              "n_text_blocks_discarded 1; n_fields_discarded 4",
              "MUST_NEVER_PERSIST" not in dumped and "encrypted" not in values_only and "cited_text" not in values_only
              and prow["n_text_blocks_discarded"] == 1 and prow["n_fields_discarded"] == 4,
              f"n_text={prow['n_text_blocks_discarded']} n_fields={prow['n_fields_discarded']}")
        check("fixture principal: fields_dropped declara encrypted_content/encrypted_index/cited_text/text; provider_property declara que el modelo LEE texto web",
              set(prow["data"]["fields_dropped"]) >= {"encrypted_content", "encrypted_index", "cited_text", "text"}
              and prow["provider_property"] == wl.ANTHROPIC_READS_WEB_TEXT)
        check("fixture principal: usage MEDIDO (input 1480, output 92, web_search_requests 1); model/model_source/model_reported; stop_reason end_turn",
              prow["usage"] == {"input_tokens": 1480, "output_tokens": 92, "web_search_requests": 1} and prow["model"] == model
              and prow["model_reported"] == "claude-opus-5" and prow["stop_reason"] == "end_turn")   # models-literal-doc
        check("fixture principal: input.query del modelo != directiva -> query_altered_by_provider True, query_sent_matches_directive False, query_altered declarada",
              prow["data"]["query_altered_by_provider"] is True and prow["query_sent_matches_directive"] is False
              and prow["data"]["query_altered"] == "wt1a zebrafish pronephros podocyte development" and prow["data"]["query_original"] == directive)
        check("POST: 1 llamada a ANTHROPIC_URL con anthropic-version, body SIN tool_choice y allowed_domains == lista; la llave fake JAMÁS en la fila",
              len(posts) == 1 and posts[0]["url"].endswith("/v1/messages") and "anthropic-version" in posts[0]["headers"]
              and "tool_choice" not in posts[0]["body"] and posts[0]["body"]["tools"][0]["allowed_domains"] == list(wl.RESOLVER_TABLE_HOSTS)
              and FAKE_ANTH_KEY not in dumped and prow["request_shape"] == {"has_tool_choice": False, "has_allowed_callers": False,
                                                                           "has_blocked_domains": False, "max_tokens": 256, "n_tools": 1})
        check("fila-proveedor: forma (A) — status/query_sent/query_truncated/url_sent/elapsed_s/n_http_gets 1/cache_hit False/identifier_provenance 'anthropic-web-search'/evidence_kind 'web'",
              all(k in prow for k in ("status", "query_sent", "query_truncated", "url_sent", "elapsed_s", "n_http_gets", "cache_hit", "identifier_provenance", "evidence_kind"))
              and prow["n_http_gets"] == 1 and prow["cache_hit"] is False and prow["identifier_provenance"] == "anthropic-web-search" and prow["evidence_kind"] == "web")
        # vía locate(): resolver + costo dos clases
        qs = QuotaSpy()
        row = wl.locate(directive, cfg_a, quota_fn=qs, env=ENV_A, round_no=2, requirement_ids=["req-fff"])
        check("locate(anthropic): 5 located (pmid, pmcid, doi, zfin, doi pattern-only), 0 unresolved, state 'located', cuota reservada y registrada (2 llamadas, provider 'anthropic')",
              row["provider"] == "anthropic" and row["n_located"] == 5 and row["n_unresolved"] == 0 and row["state"] == "located"
              and [l["kind"] for l in row["located"]] == ["pmid", "pmcid", "doi", "zfin-curie", "doi"] and len(qs.calls) == 2 and qs.calls[0]["provider"] == "anthropic",
              repr([l["id"] for l in row["located"]]))
        check("locate(anthropic): n_billable == web_search_requests (1) -> cost 0.01 'proyección'; tokens {in 1480, out 92, class 'medición', model}; tokens_usd_projected por models.prices",
              row["n_billable"] == 1 and row["cost"]["usd_projected"] == 0.01 and row["cost"]["class"] == "proyección"
              and row["cost"]["tokens"] == {"in": 1480, "out": 92, "class": "medición", "model": model}
              and row["cost"]["tokens_usd_projected"] is not None and row["cost"]["tokens_price_state"].startswith("projected (models.prices")
              and row["tokens"] == {"in": 1480, "out": 92, "class": "medición"} and row["web_search_requests"] == 1 and row["model"] == model)
        check("locate(anthropic): sin cache_probe (no hay caché por día en el alterno) y la fila JAMÁS lleva la llave ni prosa",
              "cache_probe" not in row and FAKE_ANTH_KEY not in json.dumps(row) and "MUST_NEVER_PERSIST" not in json.dumps(row))
        check("(corrector) locate(anthropic) copia a la fila-query lo que el alterno DECLARA (ANTHROPIC_ROW_KEYS): tool_type 'web_search_20250305', "
              "provider_property == ANTHROPIC_READS_WEB_TEXT, n_text_blocks_discarded 1, n_fields_discarded 4, request_shape {has_tool_choice False, …}, "
              "query_sent_matches_directive False, stop_reason 'end_turn', max_uses 1, allowed_domains == lista; cost.provider_detail {tool_type, "
              "tool_type_source, tool_types_allowed, reads_web_text True, property} — la propiedad viaja al frozen, no sólo al nivel tool; "
              "n_requests_extra 0 (web_search_requests 1 == la reserva)",
              row["tool_type"] == "web_search_20250305" and row["provider_property"] == wl.ANTHROPIC_READS_WEB_TEXT
              and row["n_text_blocks_discarded"] == 1 and row["n_fields_discarded"] == 4 and row["request_shape"]["has_tool_choice"] is False
              and row["query_sent_matches_directive"] is False and row["stop_reason"] == "end_turn" and row["max_uses"] == 1
              and row["allowed_domains"] == list(wl.RESOLVER_TABLE_HOSTS)
              and row["cost"]["provider_detail"] == wl.anthropic_provider_detail(cfg_a)
              and row["cost"]["provider_detail"]["reads_web_text"] is True and row["cost"]["provider_detail"]["tool_type"] == "web_search_20250305"
              and row["n_requests_extra"] == 0 and qs.calls[1]["record"]["n_requests_extra"] == 0,
              repr({k: row.get(k) for k in ("tool_type", "n_text_blocks_discarded", "stop_reason", "n_requests_extra")}))
    finally:
        wl._post_json = _post_real
    # 6c variantes
    V = AFX["variants"]
    wl._post_json = _fake_post_factory(200, V["tool_error_max_uses"]["response"])
    try:
        prow = wl._anthropic_web_search(directive, cfg_a, env=ENV_A)
        row = wl.locate(directive, cfg_a, env=ENV_A)
        check("variante error object -> status 'error', error 'max_uses_exceeded' (no facturado), state 'error: max_uses_exceeded', billable False",
              prow["status"] == "error" and prow["error"] == "max_uses_exceeded" and row["state"] == "error: max_uses_exceeded" and row["billable"] is False)
    finally:
        wl._post_json = _post_real
    wl._post_json = _fake_post_factory(200, V["pause_turn"]["response"])
    try:
        row = wl.locate(directive, cfg_a, env=ENV_A)
        check("variante stop_reason pause_turn -> 'error: provider-paused (no continuation by design)'",
              row["provider_status"] == "error" and row["error"] == "provider-paused (no continuation by design)")
    finally:
        wl._post_json = _post_real
    wl._post_json = _fake_post_factory(200, V["declined"]["response"])
    try:
        row = wl.locate(directive, cfg_a, env=ENV_A)
        check("variante web_search_requests 0 (el modelo no buscó) -> 'no-match' con detail 'provider-declined-to-search', n_billable 0, cost 0",
              row["provider_status"] == "no-match" and row["detail"] == "provider-declined-to-search" and row["n_billable"] == 0 and row["cost_usd_projected"] == 0.0)
    finally:
        wl._post_json = _post_real
    wl._reset_process_memory()
    wl._post_json = _fake_post_factory(400, V["http_400_not_enabled"]["body"])
    try:
        posts.clear()
        row = wl.locate(directive, cfg_a, env=ENV_A)
        ps_after = wl.provider_state(env=ENV_A)
        row2 = wl.locate(directive, cfg_a, env=ENV_A)
        check("variante HTTP 400 «not enabled» -> 'tool-unavailable' state '… org web_search disabled in Console)'; provider_state lo RECUERDA en el proceso; "
              "la 2ª llamada no hace POST (1 en total)",
              row["provider_status"] == "tool-unavailable" and row["state"] == wl.UNAVAILABLE_ANTHROPIC_DISABLED
              and not ps_after["available"] and ps_after["unavailable_reason"] == wl.UNAVAILABLE_ANTHROPIC_DISABLED
              and row2["provider_status"] == "tool-unavailable" and len(posts) == 1)
    finally:
        wl._post_json = _post_real
        wl._reset_process_memory()
    wl._post_json = _fake_post_factory(400, V["http_400_allowed_domains"]["body"])
    try:
        row = wl.locate(directive, cfg_a, env=ENV_A)
        check("variante HTTP 400 por allowed_domains -> 'error: allowed_domains rejected by org policy (HTTP 400)'",
              row["error"] == "allowed_domains rejected by org policy (HTTP 400)" and row["http_status"] == 400)
    finally:
        wl._post_json = _post_real
    wl._post_json = _fake_post_factory(401, V["http_401"]["body"])
    try:
        row = wl.locate(directive, cfg_a, env=ENV_A)
        check("variante HTTP 401 -> 'error: auth (HTTP 401)' e is_auth_error True (cortacircuito de ronda)", row["error"] == "auth (HTTP 401)" and wl.is_auth_error(row))
    finally:
        wl._post_json = _post_real

    def _raise_post(*a, **k):
        raise urllib.error.URLError("dns down")
    wl._post_json = _raise_post
    try:
        row = wl.locate(directive, cfg_a, env=ENV_A)
        check("URLError en el POST -> fila 'error' 'URLError: …' (§6 no-hang), sin facturar", row["provider_status"] == "error" and row["error"].startswith("URLError") and row["billable"] is False)
    finally:
        wl._post_json = _post_real
    check("_anthropic_constants: URL/versión de composite_auditor si importa (misma que el resto del proceso) o literales declarados",
          wl._anthropic_constants()[0] == "https://api.anthropic.com/v1/messages" and wl._anthropic_constants()[1] == "2023-06-01")
    parsed = wl.parse_anthropic_response({"content": [], "usage": {}}, "q")
    check("parse_anthropic_response tolerante: contenido vacío -> 0 resultados, query_model None, usage con None (no midió), sin excepción",
          parsed["results"] == [] and parsed["query_model"] is None and parsed["usage"]["web_search_requests"] is None)

    # ==================================================================================================
    # 7. cost_of / month_utc
    # ==================================================================================================
    print("\n# 7. costo")
    c = wl.cost_of("brave", 3)
    check("cost_of('brave', 3) -> usd_projected 0.015, price 5.0/1k, class 'proyección', price_as_of 2026-09-16, source URL",
          c["usd_projected"] == 0.015 and c["price_usd_per_1k"] == 5.0 and c["class"] == "proyección" and c["price_as_of"] == "2026-09-16"
          and "brave.com/search/api" in c["price_source_url"])
    c = wl.cost_of("anthropic", 1, tokens={"in": 1500, "out": 80}, model="claude-opus-5")   # models-literal-doc
    check("cost_of('anthropic', 1, tokens) -> 0.01 + tokens {class 'medición'} + tokens_usd_projected == 1500/1e6*5 + 80/1e6*25",
          c["usd_projected"] == 0.01 and c["tokens"]["class"] == "medición" and c["tokens_usd_projected"] == round(1500 / 1e6 * 5.0 + 80 / 1e6 * 25.0, 6))
    check("cost_of con 0 facturables (cache_hit) -> 0.0; provider 'off' -> price None y 0.0; modelo sin precio -> missing_price declarado",
          wl.cost_of("brave", 0)["usd_projected"] == 0.0 and wl.cost_of("off", 0)["price_usd_per_1k"] is None
          and wl.cost_of("anthropic", 1, tokens={"in": 1, "out": 1}, model="nope")["tokens_price_state"].startswith("missing_price"))
    check("month_utc() -> 'YYYY-MM'; con `now` fijo -> el mes UTC de ese instante", re.fullmatch(r"\d{4}-\d{2}", wl.month_utc()) is not None
          and wl.month_utc(now=0) == "1970-01")

    # ==================================================================================================
    # 8. (K) precedente 2026-05-14 — medición
    # ==================================================================================================
    print("\n# 8. precedente agéntico 2026-05-14 (K)")
    pst = wl.precedent_state()
    check("NOT_ADMISSIBLE_PRECEDENTS: 2 archivos declarados con state 'not-admissible (agentic web cache; …)' y su existencia MEDIDA",
          len(pst) == 2 and all(p["state"] == wl.NOT_ADMISSIBLE_STATE for p in pst) and all(isinstance(p["exists"], bool) for p in pst),
          repr([(p["file"], p["exists"]) for p in pst]))
    if not all(p["exists"] for p in pst):
        print("     (declarado: mcp_cache/ es caché gitignored; en este árbol falta al menos uno de los dos precedentes)")
    hits = []
    if REAL_MCP.exists():
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        for ident in ("PMID:15982647", "PMC2688018", "DOI:10.1242/dev.02071", "PMID:1", "PMC1"):
            got = fetch_paper._cache_lookup(ident, REAL_MCP, 36500, now)
            if got and "literature_pronephros" in str(got.get("path")):
                hits.append(ident)
    check("fetch_paper._cache_lookup (glob real raw_paper_*) JAMÁS devuelve los precedentes para ningún ident (sólo lectura del mcp_cache real)",
          hits == [], repr(hits))
    offenders = []
    for base in (ROOT / "analysis" / "scripts" / "lib", ROOT / "rag_index" / "query_service", ROOT / ".tooluniverse" / "tools"):
        for p in base.glob("*.py"):
            if p.name in ("web_locator.py", "smoke_web_locator.py"):
                continue   # los ÚNICOS que los nombran: la declaración (B.8) y este gate (declarado)
            if "literature_pronephros_" in p.read_text(encoding="utf-8", errors="replace"):
                offenders.append(str(p.relative_to(ROOT)))
    check("grep == 0: ningún módulo de lib/, query_service/ ni tools/ nombra literature_pronephros_* (salvo web_locator.py y este smoke, declarados)",
          offenders == [], repr(offenders))
    check("frozen_header (G.2): module/resolver/tool_version, state_vocabulary {exact, prefixes, rule}, resolver_rules 12, allowed_hosts, generic_doi_rule, text_policy, rule, gate",
          (lambda h: h["module_version"] == "wl-1" and h["resolver_version"] == "wlr-2" and "tool_version" in h and len(h["resolver_rules"]) == 12
           and h["state_vocabulary"]["exact"] == list(wl.WEB_STATES_EXACT) and h["text_policy"] == wl.TEXT_POLICY and h["gate"] == "directive-only"
           and h["allowed_hosts"]["value"] == wl.ALLOWED_HOSTS_ALL)(wl.frozen_header(env={})))

    # ==================================================================================================
    # cierre: cero red, mcp_cache intacto
    # ==================================================================================================
    print("\n# cierre")
    after = sorted((p.name, p.stat().st_size, p.stat().st_mtime_ns) for p in REAL_MCP.glob("*")) if REAL_MCP.exists() else []
    check("mcp_cache real byte-idéntico (nombres, tamaños, mtimes) — toda caché del smoke fue al tempdir", after == _MCP_BEFORE)
    check("el smoke corrió 100% OFFLINE — MEDIDO: urllib.request.urlopen bloqueado y contado == 0", _NET_CALLS == [], f"calls={_NET_CALLS[:5]}")
    _urlreq.urlopen = _urlopen_real
    n_pass, n_total = sum(CHECKS), len(CHECKS)
    print(f"\n{n_pass}/{n_total} PASS")
    return 0 if n_pass == n_total else 1


if __name__ == "__main__":
    sys.exit(main())
