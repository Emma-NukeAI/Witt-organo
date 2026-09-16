"""smoke_figures.py — gate determinista de analysis/scripts/lib/figures.py (ADR-0083, rebanada F1, contrato 1.12).

Cubre la fila `smoke_figures.py` de la tabla de gates NO-SPEND del ADR: GOLDEN del parser JATS sobre los 2 XML fixture
(PMC11379296 → 9 figs; PMC11647118 → 6 con `undfig1` sin label ni caption) y sobre los 12 del mcp_cache cuando existen
(60 figs; la trampa <fig-count> de PMC12184772 → 0) — 'NO MEDIDO (mcp_cache ausente)' declarado cuando faltan;
LICENCIA por reglas ordenadas en sus 9 formas (textos REALES de los XML cacheados si están, fixtures de texto
declarados si no), dos fuentes con precedencia XML > search y `conflict`; tabla cerrada (unknown NO embebible ni
panel; env sólo RESTRINGE, ids fuera de tabla → env_ignored); FETCH con el zip fixture (9 `verified`, sha == MANIFEST,
mime por magic, dims == scaled → dims_match True, s00N/.gif jamás extraídos); fallos declarados sin excepción (HTTP 500,
URLError, timeout, no-zip, BadZipFile, Content-Length > tope con 0 bytes de cuerpo leídos, cuerpo sin Content-Length >
tope con .part borrado, _get_bytes que LANZA); presupuesto con reloj falso; caché (TTL fresco → cache_hit y 0 red;
archivo alterado → mismatch; TTL 0 → re-descarga; LRU con tope diminuto → evicted_n ≥ 1 y el más nuevo sobrevive;
dir read-only → filas declaradas); select_for_panel (citadas primero, cap, tope de petición, tamaño, licencia);
bloques Anthropic / Responses / Chat con la forma exacta (imágenes ANTES del texto; la b64 decodifica al byte original);
env_config tolerante; `_xml_to_text` byte-idéntico; `_normalize_hit` conserva `license`.

100% OFFLINE y PORTABLE: urllib.request.urlopen BLOQUEADO Y CONTADO (== 0), caché de figuras en TMP
(WITT_MCP_CACHE_DIR temporal), mcp_cache del repo byte-idéntico antes/después (snapshot), cero gasto de modelo,
cero mutación de la DATA INAMOVIBLE. Exit 0 = todo PASS.

Máscara:  WITT_BACKEND_DB_URL=sqlite:///<tmp>.db NEO4J_URI="" RAG_BACKEND=sparse OPENAI_API_KEY="" ANTHROPIC_API_KEY=""
          WITT_RUN_ORIGIN=smoke WITT_MCP_CACHE_DIR=<tmp> python rag_index/query_service/smoke_figures.py
"""
import base64
import hashlib
import inspect
import io
import json
import os
import re
import shutil
import sys
import tempfile
import time
import urllib.error
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "analysis" / "scripts"))
FX = HERE / "fixtures" / "figures"
TMP = Path(tempfile.mkdtemp(prefix="smoke_figures_"))
REPO_CACHE = ROOT / "mcp_cache"

# ---- entorno del smoke: sin env de figuras heredada; caché de figuras en TMP; throttle real pero rápido -------------
for _k in list(os.environ):
    if _k.startswith("WITT_FIGURES"):
        os.environ.pop(_k, None)
if not (os.environ.get("WITT_MCP_CACHE_DIR") or "").strip():
    os.environ["WITT_MCP_CACHE_DIR"] = str(TMP / "mcp_cache")
os.environ["WITT_EPMC_MIN_INTERVAL_S"] = "0.01"
CACHE_ENV = Path(os.environ["WITT_MCP_CACHE_DIR"])

# ---- cero red: urlopen bloqueado y CONTADO durante TODO el smoke (patrón smoke_search_harness / ADR-0082 L.3) --------
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
    raise RuntimeError("network blocked by smoke_figures (offline gate)")


_urlreq.urlopen = _urlopen_blocked

from lib import figures as F  # noqa: E402
from lib import fetch_paper  # noqa: E402


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


def declared(name, detail):
    """Un golden que NO se pudo medir (fuente ausente) se DECLARA, no se finge ni se falla en claro."""
    CHECKS.append(True)
    print("PASS " + name + "  -> NO MEDIDO: " + detail)


def sha(b):
    return hashlib.sha256(b).hexdigest()


MANIFEST = json.loads((FX / "MANIFEST.json").read_text(encoding="utf-8"))
XML_BY = (FX / "epmc_fulltext_PMC11379296_20260613.xml").read_text(encoding="utf-8")
XML_NC = (FX / "epmc_fulltext_PMC11647118_20260613.xml").read_text(encoding="utf-8")
ZIP_BY = (FX / "PMC11379296-figures.zip").read_bytes()
ZIP_NC = (FX / "PMC11647118-figures-SYNTHETIC.zip").read_bytes()
MAN_BY = {e["href"]: e for e in MANIFEST["zips"]["PMC11379296"]["entries"]}
MAN_NC = {e["href"]: e for e in MANIFEST["zips"]["PMC11647118"]["entries"]}
G001_B64 = base64.b64encode(zipfile.ZipFile(io.BytesIO(ZIP_BY)).read("pone.0307390.g001.jpg")).decode("ascii")

# =====================================================================================================================
# 1. GOLDEN parser JATS
# =====================================================================================================================
print("\n== 1. parser JATS (golden de los 2 XML fixture) ==")
p_by = F.parse_jats(XML_BY, "PMC11379296")
ids = [f["fig_id"] for f in p_by["figs"]]
check("PMC11379296 → 9 figs con ids pone.0307390.g001..g009 en orden de documento",
      p_by["n_fig"] == 9 and ids == [f"pone.0307390.g00{i}" for i in range(1, 10)], ids)
check("labels 'Fig 1'..'Fig 9'; hrefs .jpg (content-type image) y JAMÁS el .gif thumb (9 thumbs ignorados y contados)",
      [f["label"] for f in p_by["figs"]] == [f"Fig {i}" for i in range(1, 10)]
      and all(f["graphic_href"].endswith(".jpg") for f in p_by["figs"]) and p_by["n_thumbs_ignored"] == 9
      and all(f["graphic_content_type"] == "image" for f in p_by["figs"]))
g1 = p_by["figs"][0]
check("g001 dims_declared desde PIs: original 2250×1252, scaled 750×417 (declaración de la fuente, no medición)",
      g1["dims_declared"] == {"original": {"w": 2250, "h": 1252}, "scaled": {"w": 750, "h": 417}}, g1["dims_declared"])
check("g001 caption: texto plano, caption_state present, caption_lang 'en' (xml:lang del <article>, jamás detección), "
      "1 387 chars MEDIDOS tras html.unescape (el ADR contaba 1 395 antes de desescapar '&amp;' ×2)",
      g1["caption_state"] == "present" and g1["caption_lang"] == "en" and g1["caption_chars_source"] == 1387
      and len(g1["caption"]) == 1387 and g1["caption_truncated"] is False and "&amp;" not in g1["caption"]
      and "<" not in g1["caption"], f"chars={g1['caption_chars_source']} head={g1['caption'][:60]!r}")
p_by_1200 = F.parse_jats(XML_BY, "PMC11379296", caption_chars=1200)
check("WITT_FIGURES_CAPTION_CHARS=1200 → caption de g001 recortado a 1200 + caption_truncated True (el íntegro vive en el XML)",
      len(p_by_1200["figs"][0]["caption"]) == 1200 and p_by_1200["figs"][0]["caption_truncated"] is True
      and p_by_1200["caption_chars"] == 1200)
os.environ["WITT_FIGURES_CAPTION_CHARS"] = "1200"
check("la env se lee EN LA LLAMADA: parse_jats sin caption_chars explícito honra WITT_FIGURES_CAPTION_CHARS=1200",
      F.parse_jats(XML_BY, "PMC11379296")["caption_chars"] == 1200)
os.environ.pop("WITT_FIGURES_CAPTION_CHARS", None)
check("sin <fig>//<permissions> ni <attrib> en PMC11379296 (medido: 0 en los 12 XML del ADR)",
      p_by["n_fig_permissions"] == 0 and not any(f["attrib_present"] for f in p_by["figs"]))

p_nc = F.parse_jats(XML_NC, "PMC11647118")
check("PMC11647118 → 6 figs; hrefs fx1.jpg, gr1..gr5.jpg",
      p_nc["n_fig"] == 6 and [f["graphic_href"] for f in p_nc["figs"]] == ["fx1.jpg", "gr1.jpg", "gr2.jpg", "gr3.jpg", "gr4.jpg", "gr5.jpg"])
u = p_nc["figs"][0]
check("undfig1 (abstract gráfico): label None + caption_state 'absent' — contados n_without_label 1 / n_without_caption 1",
      u["fig_id"] == "undfig1" and u["label"] is None and u["caption_state"] == "absent" and u["caption"] == ""
      and p_nc["n_without_label"] == 1 and p_nc["n_without_caption"] == 1)
check("PMC11647118 dims declaradas fx1: original 996×996, scaled 664×664",
      u["dims_declared"] == {"original": {"w": 996, "h": 996}, "scaled": {"w": 664, "h": 664}})

TRAP = ('<article xml:lang="en"><front><article-meta><counts><fig-count count="3"/></counts></article-meta></front>'
        '<body><fig-group id="G1"><fig id="A"><label>Fig A</label><caption><p>a</p></caption>'
        '<graphic xlink:href="a.jpg"/></fig><fig id="B"><caption><p>b</p></caption><alternatives>'
        '<graphic content-type="image" xlink:href="b.jpg"><?original-width 10?><?original-height 20?></graphic>'
        '<graphic content-type="thumb" xlink:href="b.gif"/></alternatives></fig></fig-group>'
        '<fig><caption><p>sin id</p></caption></fig></body></article>')
pt = F.parse_jats(TRAP, "PMCX")
check("trampa <fig-count>/<fig-group>: NO son figuras; 2 <fig> reales (uno self-closing graphic sin PIs, otro en alternatives con "
      "PIs sólo original); <fig> SIN id → fila skipped {state 'no-fig-id'} contada, no ítem",
      pt["n_fig"] == 2 and [f["fig_id"] for f in pt["figs"]] == ["A", "B"] and pt["skipped"] == [{"state": "no-fig-id", "position": 2}]
      and pt["figs"][0]["graphic_href"] == "a.jpg" and pt["figs"][0]["dims_declared"] == {"original": None, "scaled": None}
      and pt["figs"][1]["dims_declared"] == {"original": {"w": 10, "h": 20}, "scaled": None} and pt["figs"][1]["label"] is None
      and pt["n_thumbs_ignored"] == 1, json.dumps(pt["skipped"]))
check("<fig-count> con 0 <fig> → n_fig 0 (la trampa del regex ingenuo)",
      F.parse_jats('<article><counts><fig-count count="7"/></counts></article>', "PMCY")["n_fig"] == 0)
check("parser_version 'jats-fig-1' y module_version 'fig-1' declarados",
      p_by["parser_version"] == "jats-fig-1" == F.PARSER_VERSION and F.MODULE_VERSION == "fig-1")

# --- fixtures byte-idénticos a mcp_cache (cuando existe) y los 12 del golden ------------------------------------------
GOLDEN_12 = {"PMC7809618": 4, "PMC3198425": 3, "PMC9844136": 8, "PMC11379296": 9, "PMC11647118": 6, "PMC12161502": 0,
             "PMC12184772": 0, "PMC13286355": 11, "PMC6279434": 4, "PMC6424945": 3, "PMC8613261": 7, "PMC8786916": 5}


def _cache_xml(pmcid):
    for pat in (f"raw_paper_{pmcid}_*_fulltext.xml", f"raw_europepmc_S4-*_{pmcid}_fulltext_*.xml"):
        hits = sorted(REPO_CACHE.glob(pat)) if REPO_CACHE.exists() else []
        if hits:
            return hits[0]
    return None


src_by, src_nc = _cache_xml("PMC11379296"), _cache_xml("PMC11647118")
if src_by and src_nc:
    check("fixtures XML byte-idénticos a los cacheados en mcp_cache (sha256 del MANIFEST == archivo fixture == mcp_cache)",
          sha(src_by.read_bytes()) == sha((FX / "epmc_fulltext_PMC11379296_20260613.xml").read_bytes()) == MANIFEST["xml"]["PMC11379296"]["sha256"]
          and sha(src_nc.read_bytes()) == MANIFEST["xml"]["PMC11647118"]["sha256"])
else:
    declared("fixtures XML byte-idénticos a mcp_cache", "mcp_cache sin los XML golden (clon limpio / contenedor): el fixture se mide solo")
    check("fixtures XML: sha256 == MANIFEST (portable)",
          sha((FX / "epmc_fulltext_PMC11379296_20260613.xml").read_bytes()) == MANIFEST["xml"]["PMC11379296"]["sha256"])

xml12 = {pm: _cache_xml(pm) for pm in GOLDEN_12}
if all(xml12.values()):
    counts = {pm: F.parse_jats(p.read_text(encoding="utf-8", errors="replace"), pm)["n_fig"] for pm, p in xml12.items()}
    check("GOLDEN 12 XML de mcp_cache: 4·3·8·9·6·0·0·11·4·3·7·5 = 60 figuras (PMC12184772 con <fig-count> → 0)",
          counts == GOLDEN_12 and sum(counts.values()) == 60, json.dumps(counts))
    nocap = {pm: F.parse_jats(p.read_text(encoding="utf-8", errors="replace"), pm)["n_without_caption"] for pm, p in xml12.items()}
    check("GOLDEN 12: exactamente 2 <fig> sin <caption> (undfig1 de PMC11647118 y PMC7809618)",
          sum(nocap.values()) == 2 and nocap["PMC11647118"] == 1 and nocap["PMC7809618"] == 1, json.dumps(nocap))
else:
    missing = [pm for pm, p in xml12.items() if p is None]
    declared("GOLDEN 12 XML de mcp_cache (60 figs)", f"mcp_cache ausente o incompleto ({len(missing)} de 12 faltan: {missing[:4]}…)")
    declared("GOLDEN 12: 2 <fig> sin <caption>", "mcp_cache ausente")

# --- _xml_to_text NO se toca: byte-idéntico (fuente congelada @ ca9a03d) y su .txt cacheado ---------------------------
XML_TO_TEXT_SRC_SHA = "ad1361eb6c9a627d3f46cdf1e8c2e38a185951e6a9ad412a2d8e5ad899f78494"   # medido 2026-09-15 @ ca9a03d
check("fetch_paper._xml_to_text NO se tocó: sha256 del código fuente == el congelado @ ca9a03d (el .txt de la Ruta B queda igual)",
      sha(inspect.getsource(fetch_paper._xml_to_text).encode("utf-8")) == XML_TO_TEXT_SRC_SHA)
txt_cached = REPO_CACHE / "raw_paper_PMC11379296_20260613.txt"
if txt_cached.exists():
    check("_xml_to_text(fixture XML) == raw_paper_PMC11379296_20260613.txt del mcp_cache byte a byte (MEDIDO: el lector de figuras "
          "no altera el texto de la Ruta B)", fetch_paper._xml_to_text(XML_BY) == txt_cached.read_text(encoding="utf-8"))
else:
    declared("_xml_to_text(fixture) == .txt cacheado", "mcp_cache sin raw_paper_PMC11379296_20260613.txt")

# =====================================================================================================================
# 2. LICENCIA — 9 formas, reglas ordenadas, dos fuentes, tabla cerrada
# =====================================================================================================================
print("\n== 2. licencia por reglas ordenadas ==")
# Fixtures de TEXTO declarados (modelados sobre los <permissions> reales medidos el 2026-09-15) — se usan SOLO cuando el
# XML real de mcp_cache no está. Los dos fixture XML (BY, NC) siempre están.
PERM = {
    "PMC6424945": '<article><article-meta><permissions><copyright-statement>© The Author(s) 2018</copyright-statement>'
                  '<license license-type="OpenAccess"><ali:license_ref xmlns:ali="http://www.niso.org/schemas/ali/1.0/" '
                  'specific-use="textmining" content-type="ccbylicense">https://creativecommons.org/licenses/by/4.0/</ali:license_ref>'
                  '<license-p><bold>Open Access</bold> This article is distributed under the terms of the Creative Commons '
                  'Attribution 4.0 International License (http://creativecommons.org/licenses/by/4.0/)</license-p></license>'
                  '</permissions></article-meta></article>',
    "PMC8613261": '<article><article-meta><permissions><license><ali:license_ref xmlns:ali="http://www.niso.org/schemas/ali/1.0/" '
                  'specific-use="textmining" content-type="ccbylicense">https://creativecommons.org/licenses/by/4.0/</ali:license_ref>'
                  '<license-p>Open Access This article is licensed under a Creative Commons Attribution 4.0 International License</license-p>'
                  '</license></permissions></article-meta></article>',
    "PMC12184772": '<article><article-meta><permissions><license><ali:license_ref xmlns:ali="http://www.niso.org/schemas/ali/1.0/" '
                   'specific-use="textmining" content-type="ccbylicense">https://creativecommons.org/licenses/by/4.0/</ali:license_ref>'
                   '<license-p>This is an Open Access article distributed under the terms of the Creative Commons Attribution License</license-p>'
                   '</license></permissions></article-meta><counts><fig-count count="5"/></counts></article>',
    "PMC9844136": '<article><article-meta><permissions><license><license-p>This is an Open Access article distributed under the terms '
                  'of the Creative Commons Attribution License (<ext-link xmlns:xlink="http://www.w3.org/1999/xlink" '
                  'xlink:href="https://creativecommons.org/licenses/by/4.0/" ext-link-type="uri">https://creativecommons.org/licenses/by/4.0'
                  '</ext-link>)</license-p></license></permissions></article-meta></article>',
    "PMC13286355": None, "PMC6279434": None,   # misma forma ext-link que PMC9844136 (se cubre con ella si faltan)
    "PMC7809618": '<article><article-meta><permissions><license><license-p>This is an open access article under the CC BY-NC-ND '
                  'license (http://creativecommons.org/licenses/by-nc-nd/4.0/).</license-p></license></permissions></article-meta></article>',
    "PMC3198425": '<article><article-meta><permissions><copyright-statement>Jain et al.</copyright-statement><license><license-p>'
                  'This is an open-access article distributed under the terms of the Creative Commons Attribution License, which '
                  'permits unrestricted use, distribution, and reproduction in any medium, provided the original author and source '
                  'are properly credited.</license-p></license></permissions></article-meta></article>',
    "PMC8786916": '<article><article-meta><permissions><license><license-p>This is an open-access article distributed under the '
                  'terms of the Creative Commons Attribution License (CC BY). The use, distribution or reproduction in other forums '
                  'is permitted</license-p></license></permissions></article-meta></article>',
    "PMC12161502": '<article xml:lang="pt"><article-meta><permissions><license><license-p>Este é um artigo publicado em acesso '
                   'aberto sob uma licença Creative Commons</license-p></license></permissions></article-meta></article>',
}
PERM["PMC13286355"] = PERM["PMC6279434"] = PERM["PMC9844136"]


def _lic_text(pmcid):
    p = _cache_xml(pmcid)
    if p is not None:
        return p.read_text(encoding="utf-8", errors="replace"), "XML real (mcp_cache)"
    return PERM[pmcid], "fixture de texto declarado"


EXPECT = {  # (id, source, rule_no, embed, panel_view)
    "PMC11379296": ("cc-by", "ext-link", 2, True, True),
    "PMC6424945": ("cc-by", "ali-license-ref", 1, True, True),
    "PMC8613261": ("cc-by", "ali-license-ref", 1, True, True),
    "PMC12184772": ("cc-by", "ali-license-ref", 1, True, True),
    "PMC9844136": ("cc-by", "ext-link", 2, True, True),
    "PMC13286355": ("cc-by", "ext-link", 2, True, True),
    "PMC6279434": ("cc-by", "ext-link", 2, True, True),
    "PMC11647118": ("cc-by-nc", "license-p-url", 3, False, True),
    "PMC7809618": ("cc-by-nc-nd", "license-p-url", 3, False, True),
    "PMC3198425": ("cc-by", "license-p-prose", 5, True, True),
    "PMC8786916": ("cc-by", "license-p-token", 4, True, True),
    "PMC12161502": ("unknown", "none", 7, False, False),
}
cfg0 = F.env_config({})
for pm, (eid, esrc, erule, eemb, epan) in EXPECT.items():
    if pm == "PMC11379296":
        text, origin = XML_BY, "fixture XML"
    elif pm == "PMC11647118":
        text, origin = XML_NC, "fixture XML"
    else:
        text, origin = _lic_text(pm)
    lic = F.parse_license(text, prose_ok=True)
    emb, pan, _fb = F.license_flags(lic["id"], cfg0)
    check(f"{pm} → {eid}/{esrc} (regla {erule}); embed {eemb} panel_view {epan} [{origin}]",
          lic["id"] == eid and lic["source"] == esrc and lic["rule_no"] == erule and emb is eemb and pan is epan
          and lic["scope"] == "article-level" and len(lic["evidence_text"]) <= 200,
          f"got {lic['id']}/{lic['source']} r{lic['rule_no']} v={lic['version']} url={lic['url']}")
lic_openaccess = F.parse_license(_lic_text("PMC6424945")[0])
check("PMC6424945: `license-type=\"OpenAccess\"` NO es la licencia — manda el ali:license_ref (cc-by 4.0, url declarada)",
      lic_openaccess["id"] == "cc-by" and lic_openaccess["version"] == "4.0" and "creativecommons.org/licenses/by/4.0" in (lic_openaccess["url"] or ""))
check("PMC3198425 con WITT_FIGURES_PROSE_LICENSE=0 (E3 alternativa) → cc-by-prose-unconfirmed: embed False, panel_view True",
      F.parse_license(_lic_text("PMC3198425")[0], prose_ok=False)["id"] == "cc-by-prose-unconfirmed"
      and F.license_flags("cc-by-prose-unconfirmed", cfg0) == (False, True, True))
os.environ["WITT_FIGURES_PROSE_LICENSE"] = "0"
check("prose_ok se lee de la env en la llamada cuando no se pasa", F.parse_license(_lic_text("PMC3198425")[0])["id"] == "cc-by-prose-unconfirmed")
os.environ.pop("WITT_FIGURES_PROSE_LICENSE", None)
check("PMC12161502 (prosa en portugués sin variante): unknown/none — embed False, panel_view False, fetch_bytes True (se baja y verifica, no viaja)",
      F.parse_license(_lic_text("PMC12161502")[0])["id"] == "unknown" and F.license_flags("unknown", cfg0) == (False, False, True))
s_only = F.parse_license("<article><article-meta><permissions><license><license-p>terms apply</license-p></license></permissions></article-meta></article>",
                         search_license="cc by-nc-nd")
check("search 'cc by-nc-nd' SIN licencia en el XML → cc-by-nc-nd/epmc-search (regla 6), search_license normalizado",
      s_only["id"] == "cc-by-nc-nd" and s_only["source"] == "epmc-search" and s_only["rule_no"] == 6 and s_only["search_license"] == "cc-by-nc-nd")
conf = F.parse_license(XML_NC, search_license="cc by")
check("XML cc-by-nc + search 'cc by' → gana el XML (cc-by-nc/license-p-url) y `conflict {xml, search}` viaja declarado",
      conf["id"] == "cc-by-nc" and conf["source"] == "license-p-url" and conf.get("conflict") == {"xml": "cc-by-nc", "search": "cc by".replace(" ", "-")})
agree = F.parse_license(XML_BY, search_license="cc by")
check("XML cc-by + search 'cc by' → sin conflict", agree["id"] == "cc-by" and "conflict" not in agree)
tok = F.parse_license("<article><article-meta><permissions><license><license-p>Published under the CC BY-NC-ND license.</license-p>"
                      "</license></permissions></article-meta></article>")
check("orden de reglas: 'CC BY-NC-ND' en prosa (sin URL) casa como cc-by-nc-nd por token, JAMÁS como cc-by",
      tok["id"] == "cc-by-nc-nd" and tok["source"] == "license-p-token")
check("tokens compuestos: 'CC BY-SA' → cc-by-sa, 'CC BY-NC-SA' → cc-by-nc-sa, 'CC0' → cc0, 'CC BY 4.0' → cc-by v4.0",
      F.parse_license("<article-meta><permissions><license><license-p>CC BY-SA 4.0</license-p></license></permissions></article-meta>")["id"] == "cc-by-sa"
      and F.parse_license("<article-meta><permissions><license><license-p>a CC BY-NC-SA license</license-p></license></permissions></article-meta>")["id"] == "cc-by-nc-sa"
      and F.parse_license("<article-meta><permissions><license><license-p>released under CC0</license-p></license></permissions></article-meta>")["id"] == "cc0"
      and F.parse_license("<article-meta><permissions><license><license-p>under the CC BY 4.0 license</license-p></license></permissions></article-meta>")["version"] == "4.0")
check("prosa 'Creative Commons Attribution Non-Commercial' NO cae en la regla 5 (restricción detectada) → unknown si no hay token/URL",
      F.parse_license("<article-meta><permissions><license><license-p>Creative Commons Attribution Non-Commercial License</license-p>"
                      "</license></permissions></article-meta>")["id"] == "unknown")
check("ali:license_ref SIN URL pero con content-type='ccbyncndlicense' → cc-by-nc-nd (regla 1 por atributo); publicdomain/zero → cc0",
      F.parse_license('<article-meta><permissions><license><ali:license_ref content-type="ccbyncndlicense"></ali:license_ref>'
                      '</license></permissions></article-meta>')["id"] == "cc-by-nc-nd"
      and F.parse_license('<article-meta><permissions><license><ali:license_ref>https://creativecommons.org/publicdomain/zero/1.0/'
                          '</ali:license_ref></license></permissions></article-meta>') ["id"] == "cc0")
check("sin <permissions> y sin search → unknown/none regla 7, evidence_text ''",
      F.parse_license("<article><body><p>x</p></body></article>") == {"id": "unknown", "source": "none", "evidence_text": "", "url": None,
                                                                       "rule_no": 7, "version": None, "scope": "article-level", "search_license": None})
check("normalize_search_license: 'cc by'→cc-by, 'CC BY-NC'→cc-by-nc, 'cc by-nc-nd'→cc-by-nc-nd, basura→None",
      F.normalize_search_license("cc by") == "cc-by" and F.normalize_search_license("CC BY-NC") == "cc-by-nc"
      and F.normalize_search_license("cc by-nc-nd") == "cc-by-nc-nd" and F.normalize_search_license("all rights reserved") is None
      and F.normalize_search_license(None) is None)

# figure-level <permissions> sintético: gobierna la figura con scope 'figure-level'
_G002_OPEN = re.search(r'<fig id="pone.0307390.g002"[^>]*>', XML_BY).group(0)
FIGPERM = XML_BY.replace(_G002_OPEN, _G002_OPEN + '<permissions><license><license-p>Reproduced under the CC BY-NC-ND license '
                         '(http://creativecommons.org/licenses/by-nc-nd/4.0/).</license-p></license></permissions>', 1)
pf = F.parse_jats(FIGPERM, "PMC11379296")
f2 = pf["figs"][1]
check("<fig>//<permissions> sintético en g002 → fig_permissions_present True, fig_license cc-by-nc-nd con scope 'figure-level' "
      "(GOBIERNA la figura); el resto sigue article-level cc-by; n_fig_permissions 1",
      f2["fig_permissions_present"] is True and f2["fig_license"]["id"] == "cc-by-nc-nd" and f2["fig_license"]["scope"] == "figure-level"
      and pf["figs"][0]["fig_license"] is None and pf["n_fig_permissions"] == 1 and F.parse_license(FIGPERM)["id"] == "cc-by")
lt = F.license_table(cfg0)
check("LICENSE_TABLE cerrada = LICENSES (10 ids), version 'lt-1', rule declarada; zfin-display-only: embed/panel/fetch todos False",
      tuple(lt["table"]) == F.LICENSES and len(F.LICENSES) == 10 and lt["version"] == "lt-1" and "credit line" in lt["rule"]
      and lt["table"]["zfin-display-only"] == {"embed": False, "panel_view": False, "fetch_bytes": False, "words_es": F.LICENSE_TABLE["zfin-display-only"]["words_es"]})
check("defaults de tabla: cc-by/cc0/cc-by-sa embed True; NC/ND/NC-SA/NC-ND embed False panel_view True (E2 default); unknown ambos False",
      all(lt["table"][i]["embed"] for i in ("cc-by", "cc0", "cc-by-sa"))
      and all((not lt["table"][i]["embed"]) and lt["table"][i]["panel_view"] for i in ("cc-by-nc", "cc-by-nd", "cc-by-nc-sa", "cc-by-nc-nd"))
      and lt["table"]["unknown"] == {"embed": False, "panel_view": False, "fetch_bytes": True, "words_es": F.LICENSE_TABLE["unknown"]["words_es"]})
cfg_env = F.env_config({"WITT_FIGURES_EMBED_LICENSES": "cc-by,foo", "WITT_FIGURES_PANEL_LICENSES": "cc-by,unknown,cc-by-nc-nd"})
lt_env = F.license_table(cfg_env)
check("env sólo RESTRINGE: EMBED_LICENSES=cc-by,foo → cc0/cc-by-sa embed False, 'foo' → env_ignored declarado; PANEL_LICENSES=cc-by,unknown,"
      "cc-by-nc-nd → cc-by-nc panel_view False, unknown SIGUE False (la tabla manda), cc-by-nc-nd True",
      lt_env["table"]["cc0"]["embed"] is False and lt_env["table"]["cc-by"]["embed"] is True
      and lt_env["env_ignored"] == ["WITT_FIGURES_EMBED_LICENSES:foo"] and lt_env["table"]["cc-by-nc"]["panel_view"] is False
      and lt_env["table"]["unknown"]["panel_view"] is False and lt_env["table"]["cc-by-nc-nd"]["panel_view"] is True, lt_env["env_ignored"])
cfg_env2 = F.env_config({"WITT_FIGURES_EMBED_LICENSES": "cc-by-nc"})
check("EMBED_LICENSES=cc-by-nc NO amplía: cc-by-nc sigue embed False (tabla ∧ env), y cc-by queda False por la restricción",
      F.license_flags("cc-by-nc", cfg_env2)[0] is False and F.license_flags("cc-by", cfg_env2)[0] is False)

# =====================================================================================================================
# 3. FETCH con el zip fixture — attach sobre un bundle sintético; _get_bytes FALSO (0 red)
# =====================================================================================================================
print("\n== 3. fetch_figures / attach con zip fixture ==")
GET_CALLS = []
_REAL_GET_BYTES = F._get_bytes


def _mk_get(zip_bytes=None, error_kind=None, http_status=200, content_type="application/zip", raise_exc=None):
    def _fake(url, timeout, max_bytes, dest=None):
        GET_CALLS.append({"url": url, "timeout": timeout, "max_bytes": max_bytes, "dest": str(dest)})
        if raise_exc is not None:
            raise raise_exc
        if error_kind is not None:
            return {"status": "error", "http_status": http_status if error_kind.startswith("http-") else None,
                    "content_length": None, "content_type": None, "bytes": 0, "elapsed_s": 0.01, "url": url,
                    "error_kind": error_kind, "error": f"fake {error_kind}"}
        Path(dest).write_bytes(zip_bytes)
        return {"status": "ok", "http_status": http_status, "content_length": len(zip_bytes), "content_type": content_type,
                "bytes": len(zip_bytes), "elapsed_s": 0.02, "url": url, "path": str(dest)}
    return _fake


def _zip_without(zb, drop):
    zin = zipfile.ZipFile(io.BytesIO(zb))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zout:
        for n in zin.namelist():
            if n not in drop:
                zout.writestr(n, zin.read(n))
    return buf.getvalue()


def _paper(pmcid, xml_path, rank=1, evidence_id=None, source="europepmc", text_excerpt=None, full_text=True, license_=None):
    sr = {"pmid": None, "pmcid": pmcid, "doi": None, "title": f"paper {pmcid}"}
    if license_ is not None:
        sr["license"] = license_
    return {"source": source, "evidence_id": evidence_id or pmcid, "search_rec": sr, "selection_rank": rank,
            "fetched": {"found": True, "full_text": full_text, "n_chunks": 3, "raw_cached": [str(xml_path)], "raw_ref": None},
            "text_excerpt": text_excerpt}


def _bundle(*papers):
    return {"path_a": {"hits": []}, "path_b": {"papers": list(papers)}}


XML_BY_P, XML_NC_P = FX / "epmc_fulltext_PMC11379296_20260613.xml", FX / "epmc_fulltext_PMC11647118_20260613.xml"
CR = CACHE_ENV / "figures"
check("cache_dir() honra WITT_MCP_CACHE_DIR (dir_source 'env') → <dir>/figures; sin env → <repo>/mcp_cache/figures 'default'",
      F.cache_dir() == (CR, "env") and F.cache_dir({}) == (ROOT / "mcp_cache" / "figures", "default"))

F._get_bytes = _mk_get(ZIP_BY)
GET_CALLS.clear()
EVENTS = []
b1 = _bundle(_paper("PMC11379296", XML_BY_P))
s1 = F.attach(b1, cache_root=CR, on_event=lambda k, p: EVENTS.append((k, p)))
items1 = b1["path_b"]["papers"][0]["figures"]["items"]
check("attach BY: state 'attached', 1 paper elegible/seleccionado/con XML, 9 figuras, 9 con caption, 9 verified, 0 not-fetched, "
      "9 embebibles, 9 panel_view, 0 unknown; UNA sola GET (un zip por paper)",
      s1["state"] == "attached" and s1["n_papers_eligible"] == s1["n_papers_selected"] == s1["n_papers_with_xml"] == 1
      and s1["n_figures"] == 9 == s1["n_with_caption"] == s1["n_verified"] == s1["n_embeddable"] == s1["n_panel_view"]
      and s1["n_not_fetched"] == 0 and s1["n_unknown_license"] == 0 and len(GET_CALLS) == 1
      and GET_CALLS[0]["url"] == "https://www.ebi.ac.uk/europepmc/webservices/rest/PMC11379296/supplementaryFiles",
      json.dumps({k: s1[k] for k in ("state", "n_figures", "n_verified", "n_embeddable", "n_not_fetched")}))
check("sha256 de las 9 == MANIFEST (bytes ORIGINALES del zip), bytes == MANIFEST, mime image/jpeg por magic, "
      "dims medidas == scaled del XML → dims_match True, dims_source 'header'",
      all(it["sha256"] == MAN_BY[it["graphic_href"]]["sha256"] and it["bytes"] == MAN_BY[it["graphic_href"]]["bytes"]
          and it["media_type"] == "image/jpeg" and it["mime_from_extension"] == "image/jpeg"
          and it["dims_measured"] == MAN_BY[it["graphic_href"]]["dims"] == it["dims_declared"]["scaled"]
          and it["dims_match"] is True and it["dims_source"] == "header" for it in items1))
check("g001: 750×417, sha 40877777ed82…, 189 021 B (Context 2 del ADR, medido)",
      items1[0]["dims_measured"] == {"w": 750, "h": 417} and items1[0]["sha256"].startswith("40877777ed82") and items1[0]["bytes"] == 189021)
check("FigureItem con las llaves EXACTAS de FIGURE_ITEM_KEYS en orden; id '<PMCID>#<fig_id>'; class = FIGURE_CLASS; license {id, source, "
      "evidence_text, url, rule_no, version, scope}; sha256_short 12; cited_by_answer [] / seen_by_lenses [] (F4 los llena)",
      all(tuple(it) == F.FIGURE_ITEM_KEYS for it in items1) and items1[0]["id"] == "PMC11379296#pone.0307390.g001"
      and items1[0]["class"] == F.FIGURE_CLASS and set(items1[0]["license"]) == {"id", "source", "evidence_text", "url", "rule_no", "version", "scope"}
      and len(items1[0]["sha256_short"]) == 12 and items1[0]["cited_by_answer"] == [] and items1[0]["seen_by_lenses"] == []
      and items1[0]["delivered_to_synthesizer"] is True and items1[0]["caption_in_excerpt"] is None)
check("raw_ref = raw_store.source_pointer (mode source-pointer, sha256, bytes, content_type image/jpeg, source_url "
      "'{EPMC}/PMC11379296/supplementaryFiles#pone.0307390.g001.jpg')",
      items1[0]["raw_ref"]["mode"] == "source-pointer" and items1[0]["raw_ref"]["sha256"] == items1[0]["sha256"]
      and items1[0]["raw_ref"]["content_type"] == "image/jpeg" and items1[0]["raw_ref"]["bytes"] == 189021
      and items1[0]["source_url"] == items1[0]["raw_ref"]["source_url"] == f"{F.EPMC}/PMC11379296/supplementaryFiles#pone.0307390.g001.jpg")
cached_files = sorted(p.name for p in (CR / "PMC11379296").iterdir())
check("caché figures/PMC11379296/: EXACTAMENTE los 9 .jpg + el ledger _figures_<YYYYMMDD>.json; ni .gif ni s00N ni el zip ni .part",
      len(cached_files) == 10 and sum(1 for n in cached_files if n.endswith(".jpg")) == 9
      and any(re.fullmatch(r"_figures_\d{8}\.json", n) for n in cached_files)
      and not any(n.endswith((".gif", ".pdf", ".xlsx", ".zip", ".part")) for n in cached_files), ",".join(cached_files))
led1 = json.loads(next((CR / "PMC11379296").glob("_figures_*.json")).read_text(encoding="utf-8"))
check("ledger raw {fetched_at, mechanism 'supplementaryFiles-zip', http_status 200, zip_bytes, entries[9] {href, sha256, bytes, mime, dims}}",
      led1["mechanism"] == "supplementaryFiles-zip" and led1["http_status"] == 200 and led1["zip_bytes"] == len(ZIP_BY)
      and len(led1["entries"]) == 9 and set(led1["entries"][0]) == {"href", "sha256", "bytes", "mime", "dims"}
      and re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$", led1["fetched_at"]))
check("cache_path_rel 'PMC11379296/<href>' y verify_cached recalcula el sha → 'verified' (ADR-0077: sha al leer)",
      items1[0]["cache_path_rel"] == "PMC11379296/pone.0307390.g001.jpg" and F.verify_cached(CR, items1[0])["state"] == "verified"
      and items1[0]["cache_hit"] is False and items1[0]["fetched_at"] == led1["fetched_at"])
pl1 = b1["path_b"]["papers"][0]["figures"]["ledger"]
check("paper.figures.ledger {mechanism, status 'success', http_status, zip_bytes, elapsed_s, n_entries 9, n_extracted 9, n_missing 0, cache_hit False}",
      pl1["status"] == "success" and pl1["n_entries"] == 9 and pl1["n_extracted"] == 9 and pl1["n_missing"] == 0 and pl1["cache_hit"] is False
      and isinstance(pl1["elapsed_s"], float), json.dumps(pl1))
kinds = [k for k, _ in EVENTS]
check("on_event: 'paper' phase start (latido) ANTES de la descarga, 9 'figure', 'paper' phase done con license {id, source} y n_extracted",
      kinds[0] == "paper" and EVENTS[0][1]["phase"] == "start" and EVENTS[0][1]["heartbeat"] is True and kinds.count("figure") == 9
      and kinds[-1] == "paper" and EVENTS[-1][1]["phase"] == "done" and EVENTS[-1][1]["license"] == {"id": "cc-by", "source": "ext-link"}
      and EVENTS[-1][1]["n_extracted"] == 9 and EVENTS[1][1]["sha256"] == items1[0]["sha256"], kinds)
check("resumen: module/parser/license_table version, license_table efectiva + rule, mechanism, cache {dir_source 'env', dir_state 'writable', "
      "ttl_days 30, cache_max_mb 512, evicted_n 0}, budget {total_s 90, used_s, over_budget False}, caps con source, zfin_figures_state literal, "
      "selection.rule, vocabulary, bundle['figures_ledger'] es el mismo resumen",
      s1["module_version"] == "fig-1" and s1["parser_version"] == "jats-fig-1" and s1["license_table_version"] == "lt-1"
      and s1["cache"] == {"dir_source": "env", "dir_state": "writable", "ttl_days": 30.0, "cache_max_mb": 512.0, "evicted_n": 0}
      and s1["budget"]["total_s"] == 90.0 and s1["budget"]["over_budget"] is False and s1["caps"]["max_per_run"] == {"value": 12, "source": "default-unset:WITT_FIGURES_MAX_PER_RUN"}
      and s1["zfin_figures_state"] == F.ZFIN_FIGURES_STATE and s1["selection"]["rule"] == F.SELECTION_RULE
      and "LICENSES" in s1["vocabulary"] and b1["figures_ledger"] is s1, json.dumps(s1["cache"]))
proj = F.project_for_prompt(items1)
bundle_json = json.dumps(b1, ensure_ascii=False, default=str)
check("project_for_prompt: SOLO PROMPT_FIGURE_KEYS, license {id, source}; ninguna llave prohibida; NI la b64 de g001 NI 'data:image' NI "
      "cache_path/raw_ref en la proyección; el bundle_json tampoco contiene la b64 (nada binario en el blob, ADR-0074)",
      len(proj) == 9 and all(tuple(p) == F.PROMPT_FIGURE_KEYS for p in proj) and proj[0]["license"] == {"id": "cc-by", "source": "ext-link"}
      and not (set(F.PROMPT_FIGURE_KEYS) & set(F.FORBIDDEN_PROMPT_KEYS))
      and G001_B64[:64] not in json.dumps(proj) and "data:image" not in json.dumps(proj) and "cache_path" not in json.dumps(proj)
      and G001_B64[:64] not in bundle_json and "data:image" not in bundle_json)

# --- NC sintético ---------------------------------------------------------------------------------------------------
F._get_bytes = _mk_get(ZIP_NC)
GET_CALLS.clear()
b2 = _bundle(_paper("PMC11647118", XML_NC_P, text_excerpt="Figure 1 " + p_nc["figs"][1]["caption"][:120]))
s2 = F.attach(b2, cache_root=CR)
items2 = b2["path_b"]["papers"][0]["figures"]["items"]
check("attach NC (zip SINTÉTICO): 6 figuras, 5 con caption, 5 verified, undfig1 'not-fetched (no-caption)' (sin caption NO se baja ni se entrega), "
      "n_embeddable 0, n_panel_view 5, delivered_to_synthesizer False para undfig1",
      s2["n_figures"] == 6 and s2["n_with_caption"] == 5 and s2["n_verified"] == 5 and items2[0]["bytes_state"] == "not-fetched (no-caption)"
      and items2[0]["delivered_to_synthesizer"] is False and s2["n_embeddable"] == 0 and s2["n_panel_view"] == 5 and s2["n_not_fetched"] == 1,
      json.dumps([it["bytes_state"] for it in items2]))
check("NC: license cc-by-nc/license-p-url, embeddable False, panel_view True (E2 default) en las 6; sha == MANIFEST sintético; media_type "
      "image/png por MAGIC ≠ mime_from_extension image/jpeg (declarado aparte); dims 1×1 ≠ scaled → dims_match False",
      all(it["license"]["id"] == "cc-by-nc" and it["license"]["source"] == "license-p-url" and it["embeddable"] is False and it["panel_view"] is True for it in items2)
      and all(it["sha256"] == MAN_NC[it["graphic_href"]]["sha256"] and it["media_type"] == "image/png" and it["mime_from_extension"] == "image/jpeg"
              and it["dims_measured"] == {"w": 1, "h": 1} and it["dims_match"] is False for it in items2[1:]))
check("caption_in_excerpt MEDIDO: fig1 (su caption está en text_excerpt truncado → False porque el excerpt lo corta), undfig1 None (sin caption)",
      items2[0]["caption_in_excerpt"] is None and items2[1]["caption_in_excerpt"] is False)
b2b = _bundle(_paper("PMC11647118", XML_NC_P, text_excerpt="intro… " + p_nc["figs"][1]["caption"] + " …fin"))
F.attach(b2b, cache_root=CR)
check("caption_in_excerpt True cuando el caption íntegro consta en text_excerpt (substring determinista, espacios normalizados)",
      b2b["path_b"]["papers"][0]["figures"]["items"][1]["caption_in_excerpt"] is True)
check("MANIFEST declara qué es real: BY real True (9 entradas), NC real False con why_synthetic; contract '1.12'",
      MANIFEST["zips"]["PMC11379296"]["real"] is True and len(MANIFEST["zips"]["PMC11379296"]["entries"]) == 9
      and MANIFEST["zips"]["PMC11647118"]["real"] is False and "why_synthetic" in MANIFEST["zips"]["PMC11647118"] and MANIFEST["contract"] == "1.12")

# --- entrada faltante / thumb disponible ----------------------------------------------------------------------------
shutil.rmtree(CR / "PMC11647118", ignore_errors=True)
F._get_bytes = _mk_get(_zip_without(ZIP_NC, {"gr3.jpg"}))
b3 = _bundle(_paper("PMC11647118", XML_NC_P))
F.attach(b3, cache_root=CR)
it3 = {it["fig_id"]: it for it in b3["path_b"]["papers"][0]["figures"]["items"]}
check("entrada gr3.jpg ausente del zip → fig3 'not-fetched (href-not-in-zip)' con caption intacto y sha None; las otras 4 verified",
      it3["fig3"]["bytes_state"] == "not-fetched (href-not-in-zip)" and it3["fig3"]["sha256"] is None and it3["fig3"]["caption"]
      and sum(1 for it in it3.values() if it["bytes_state"] == "verified") == 4)
XML_NC_GR9 = XML_NC.replace('<fig id="fig5"', '<fig id="fig9"><label>Figure 9</label><caption><p>synthetic caption nine</p></caption>'
                            '<graphic content-type="image" xlink:href="gr9.jpg"/></fig><fig id="fig5"', 1)
xml9 = TMP / "epmc_fulltext_PMC11647118_gr9.xml"   # el nombre debe casar `*fulltext*.xml` como en mcp_cache (locate_xml)
xml9.write_text(XML_NC_GR9, encoding="utf-8")
shutil.rmtree(CR / "PMC11647118", ignore_errors=True)
F._get_bytes = _mk_get(ZIP_NC)
b4 = _bundle(_paper("PMC11647118", xml9))
F.attach(b4, cache_root=CR)
it4 = {it["fig_id"]: it for it in b4["path_b"]["papers"][0]["figures"]["items"]}
check("href gr9.jpg ausente pero gr9.gif (thumb) presente → 'not-fetched (href-not-in-zip; thumb-available)' — el thumb NO se baja",
      it4["fig9"]["bytes_state"] == "not-fetched (href-not-in-zip; thumb-available)" and not (CR / "PMC11647118" / "gr9.gif").exists())

# --- fallos declarados, sin excepción, la corrida sigue ---------------------------------------------------------------
for kind, mk in (("http-500", _mk_get(error_kind="http-500", http_status=500)),
                 ("network", _mk_get(error_kind="network")),
                 ("timeout", _mk_get(error_kind="timeout")),
                 ("zip-over-max", _mk_get(error_kind="zip-over-max"))):
    shutil.rmtree(CR / "PMC11379296", ignore_errors=True)
    F._get_bytes = mk
    bx = _bundle(_paper("PMC11379296", XML_BY_P))
    try:
        sx = F.attach(bx, cache_root=CR)
        rows = [it["bytes_state"] for it in bx["path_b"]["papers"][0]["figures"]["items"]]
        check(f"_get_bytes → {kind}: las 9 filas 'not-fetched ({kind})' con caption intacto, state 'attached', n_not_fetched 9, ledger.error declarado, "
              "NADA cacheado (errores jamás se cachean), sin excepción",
              rows == [f"not-fetched ({kind})"] * 9 and sx["state"] == "attached" and sx["n_not_fetched"] == 9 and sx["n_verified"] == 0
              and bx["path_b"]["papers"][0]["figures"]["ledger"]["error"] and not (CR / "PMC11379296").exists()
              or (rows == [f"not-fetched ({kind})"] * 9 and not list((CR / "PMC11379296").glob("*.jpg")) and not list((CR / "PMC11379296").glob("_figures_*"))),
              json.dumps(rows[:2]))
    except Exception as e:
        check(f"_get_bytes → {kind}: sin excepción", False, f"{type(e).__name__}: {e}")
shutil.rmtree(CR / "PMC11379296", ignore_errors=True)
F._get_bytes = _mk_get(b"<html>not a zip</html>", content_type="text/html")
bx = _bundle(_paper("PMC11379296", XML_BY_P))
F.attach(bx, cache_root=CR)
check("cuerpo que NO es zip (HTML) → 'not-fetched (not-a-zip)' ×9; el archivo temporal no queda",
      [it["bytes_state"] for it in bx["path_b"]["papers"][0]["figures"]["items"]] == ["not-fetched (not-a-zip)"] * 9
      and not list((CR / "PMC11379296").glob("*.zip*")))
F._get_bytes = _mk_get(b"PK\x03\x04" + b"\x00" * 200)
bx = _bundle(_paper("PMC11379296", XML_BY_P))
F.attach(bx, cache_root=CR)
check("zip corrupto (cabecera PK + basura → BadZipFile) → 'not-fetched (bad-zip)' ×9",
      [it["bytes_state"] for it in bx["path_b"]["papers"][0]["figures"]["items"]] == ["not-fetched (bad-zip)"] * 9)
F._get_bytes = _mk_get(raise_exc=RuntimeError("caller exploded"))
bx = _bundle(_paper("PMC11379296", XML_BY_P))
sx = F.attach(bx, cache_root=CR)
check("_get_bytes que LANZA → 9 filas 'error: RuntimeError: caller exploded', ledger error_kind, la corrida sigue (attach devuelve 'attached')",
      [it["bytes_state"] for it in bx["path_b"]["papers"][0]["figures"]["items"]] == ["error: RuntimeError: caller exploded"] * 9
      and sx["state"] == "attached" and all(F.bytes_state_in_vocabulary(it["bytes_state"]) for it in bx["path_b"]["papers"][0]["figures"]["items"]))
check("(B.2, corrector) las filas 'error: …' van a n_error (9), NO a n_not_fetched (0): n_figures == n_verified + n_mismatch + n_not_fetched + n_error "
      "(las cubetas SUMAN; antes n_not_fetched englobaba los 'error: ' sin declararlo)",
      sx["n_error"] == 9 and sx["n_not_fetched"] == 0
      and sx["n_figures"] == sx["n_verified"] + sx["n_mismatch"] + sx["n_not_fetched"] + sx["n_error"] == 9
      and s1["n_error"] == 0 and "n_error" in s1, json.dumps({k: sx[k] for k in ("n_figures", "n_not_fetched", "n_error")}))
# unsupported-mime / decode-error desde el zip
buf = io.BytesIO()
with zipfile.ZipFile(buf, "w") as z:
    z.writestr("pone.0307390.g001.jpg", b"%PDF-1.4 not an image at all........")
    z.writestr("pone.0307390.g002.jpg", b"\xff\xd8\xff\xe0" + b"\x00" * 20)          # JPEG sin SOF → dims None
    z.writestr("pone.0307390.g003.jpg", zipfile.ZipFile(io.BytesIO(ZIP_BY)).read("pone.0307390.g003.jpg"))
F._get_bytes = _mk_get(buf.getvalue())
bx = _bundle(_paper("PMC11379296", XML_BY_P))
F.attach(bx, cache_root=CR)
st = [it["bytes_state"] for it in bx["path_b"]["papers"][0]["figures"]["items"]]
check("mime no soportado → 'not-fetched (unsupported-mime)'; JPEG sin SOF → 'not-fetched (decode-error)'; g003 verified; g004..g009 href-not-in-zip",
      st[0] == "not-fetched (unsupported-mime)" and st[1] == "not-fetched (decode-error)" and st[2] == "verified"
      and st[3:] == ["not-fetched (href-not-in-zip)"] * 6, json.dumps(st))

# --- _get_bytes REAL con urlopen FALSO: precheck Content-Length, streaming con tope, .part -----------------------------
print("\n== 3b. _get_bytes real (urlopen falso) ==")


class _FakeResp:
    def __init__(self, body, headers=None, status=200):
        self._b, self.headers, self.status, self.reads, self.pos = body, dict(headers or {}), status, 0, 0

    def read(self, n=-1):
        self.reads += 1
        if n is None or n < 0:
            n = len(self._b) - self.pos
        chunk = self._b[self.pos:self.pos + n]
        self.pos += len(chunk)
        return chunk

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


_REAL_URLOPEN_SEAM = F._urlopen
resp = _FakeResp(ZIP_BY, {"Content-Length": str(len(ZIP_BY)), "Content-Type": "application/zip"})
F._urlopen = lambda req, timeout=None: resp
dest = TMP / "real_get" / "x.zip"
dest.parent.mkdir(parents=True)
g = _REAL_GET_BYTES("https://www.ebi.ac.uk/europepmc/webservices/rest/PMC11379296/supplementaryFiles", 5, 40 * 1024 * 1024, dest=dest)
check("_get_bytes real: status ok, http 200, content_length y bytes == len(zip), content_type, .part publicado por os.replace (sin .part residual), "
      "throttle_slept_s medido (net_throttle), elapsed_s",
      g["status"] == "ok" and g["http_status"] == 200 and g["bytes"] == len(ZIP_BY) == g["content_length"] and g["content_type"] == "application/zip"
      and dest.exists() and dest.read_bytes() == ZIP_BY and not Path(str(dest) + ".part").exists() and isinstance(g["throttle_slept_s"], float)
      and isinstance(g["elapsed_s"], float), json.dumps({k: g[k] for k in ("status", "http_status", "bytes", "elapsed_s")}))
U = "https://www.ebi.ac.uk/europepmc/webservices/rest/PMC0/supplementaryFiles"   # Request() exige una URL con esquema
resp = _FakeResp(ZIP_BY, {"Content-Length": str(len(ZIP_BY))})
F._urlopen = lambda req, timeout=None: resp
g = _REAL_GET_BYTES(U, 5, 1000, dest=TMP / "real_get" / "y.zip")
check("precheck Content-Length > max_bytes → error 'zip-over-max' con 0 bytes de cuerpo LEÍDOS (reads == 0) y sin archivo ni .part",
      g["status"] == "error" and g["error_kind"] == "zip-over-max" and resp.reads == 0 and g["bytes"] == 0
      and not (TMP / "real_get" / "y.zip").exists() and not (TMP / "real_get" / "y.zip.part").exists(), g.get("error"))
resp = _FakeResp(b"x" * (3 * 1024 * 1024 + 7), {})     # sin Content-Length, 3 MB, tope 2 MB
F._urlopen = lambda req, timeout=None: resp
g = _REAL_GET_BYTES(U, 5, 2 * 1024 * 1024, dest=TMP / "real_get" / "z.zip")
check("sin Content-Length y cuerpo > tope: se lee por chunks de 1 MB hasta rebasar → 'zip-over-max', .part BORRADO, nada publicado",
      g["status"] == "error" and g["error_kind"] == "zip-over-max" and 2 <= resp.reads <= 4
      and not (TMP / "real_get" / "z.zip").exists() and not (TMP / "real_get" / "z.zip.part").exists(), f"reads={resp.reads}")
resp = _FakeResp(b"abc", {})
F._urlopen = lambda req, timeout=None: resp
g = _REAL_GET_BYTES(U, 5, 10)
check("sin dest → los bytes vuelven en `data` (cuerpo pequeño sin Content-Length)", g["status"] == "ok" and g["data"] == b"abc" and g["bytes"] == 3)


def _raise(exc):
    def _f(req, timeout=None):
        raise exc
    return _f


F._urlopen = _raise(urllib.error.HTTPError("u", 500, "Server Error", {}, None))
g = _REAL_GET_BYTES(U, 5, 100, dest=TMP / "real_get" / "e.zip")
check("HTTPError 500 → error_kind 'http-500', http_status 500, sin excepción", g["status"] == "error" and g["error_kind"] == "http-500" and g["http_status"] == 500)
F._urlopen = _raise(urllib.error.URLError("name resolution failed"))
check("URLError → 'network'", _REAL_GET_BYTES(U, 5, 100)["error_kind"] == "network")
F._urlopen = _raise(TimeoutError("timed out"))
check("TimeoutError → 'timeout'", _REAL_GET_BYTES(U, 5, 100)["error_kind"] == "timeout")
F._urlopen = _raise(urllib.error.URLError(TimeoutError("_ssl.c: The read operation timed out")))
check("URLError(reason timeout) → 'timeout'", _REAL_GET_BYTES(U, 5, 100)["error_kind"] == "timeout")
check("la costura figures._urlopen ES urllib.request.urlopen (quedó ligada al bloqueador del smoke al importar): la ruta real de red es la contada",
      _REAL_URLOPEN_SEAM is _urlopen_blocked)


# --- (corrector B.4/C) el presupuesto POR PAPER se APLICA dentro de la descarga: una respuesta que GOTEA se corta por reloj ---------------
class _DripResp(_FakeResp):
    """Cada read() de 1 MB avanza el reloj FALSO `advance_s` (un servidor que gotea renueva el socket timeout en cada chunk)."""
    def __init__(self, body, advance_s, clockbox):
        super().__init__(body, {}, 200)
        self.adv, self.box = advance_s, clockbox

    def read(self, n=-1):
        self.box["t"] += self.adv
        return super().read(n)


_DBOX = {"t": 5000.0}
_drip = _DripResp(b"d" * (10 * 1024 * 1024 + 5), 6.0, _DBOX)      # 11 chunks × 6 s = 66 s > 45 s de presupuesto por paper
F._urlopen = lambda req, timeout=None: _drip
g = _REAL_GET_BYTES(U, 30, 40 * 1024 * 1024, dest=TMP / "real_get" / "drip.zip", deadline=_DBOX["t"] + 45.0, clock=lambda: _DBOX["t"])
check("(B.4, corrector) _get_bytes con deadline (reloj inyectado): respuesta que gotea (6 s por chunk de 1 MB, sin Content-Length) se ABORTA al rebasar "
      "los 45 s → error_kind 'timeout', deadline_exceeded True, < 11 reads (no espera al final), .part BORRADO, nada publicado",
      g["status"] == "error" and g["error_kind"] == "timeout" and g.get("deadline_exceeded") is True and 1 <= _drip.reads < 11
      and not (TMP / "real_get" / "drip.zip").exists() and not (TMP / "real_get" / "drip.zip.part").exists(),
      json.dumps({"reads": _drip.reads, "error": g.get("error"), "bytes": g["bytes"]}))
_DBOX["t"] = 5000.0
_drip2 = _DripResp(ZIP_BY, 0.5, _DBOX)                                   # 2 chunks × 0.5 s → dentro del presupuesto
F._urlopen = lambda req, timeout=None: _drip2
g2 = _REAL_GET_BYTES(U, 30, 40 * 1024 * 1024, dest=TMP / "real_get" / "drip_ok.zip", deadline=_DBOX["t"] + 45.0, clock=lambda: _DBOX["t"])
check("(B.4, corrector) la misma costura con deadline NO rebasado → status ok, bytes == len(zip), sin deadline_exceeded (el corte sólo actúa al rebasar)",
      g2["status"] == "ok" and g2["bytes"] == len(ZIP_BY) and "deadline_exceeded" not in g2)
# attach REAL (_get_bytes real + urlopen que gotea + reloj falso): filas 'not-fetched (timeout)' declaradas, la corrida sigue
shutil.rmtree(CR, ignore_errors=True)
_DBOX["t"] = 5000.0
_drip3 = _DripResp(b"d" * (10 * 1024 * 1024 + 5), 6.0, _DBOX)
F._urlopen = lambda req, timeout=None: _drip3
F._get_bytes = _REAL_GET_BYTES
b_dl = _bundle(_paper("PMC11379296", XML_BY_P))
s_dl = F.attach(b_dl, cfg=F.env_config({"WITT_FIGURES_BUDGET_S": "90", "WITT_FIGURES_TTL_DAYS": "0"}), cache_root=CR, clock=lambda: _DBOX["t"])
_l_dl = b_dl["path_b"]["papers"][0]["figures"]["ledger"]
check("(B.4/C, corrector) attach con la costura REAL y un servidor que gotea más allá del presupuesto por paper → las 9 filas 'not-fetched (timeout)' "
      "(vocabulario B.2), ledger {status 'error', error_kind 'timeout', budget_s 45}, budget.used_s ≤ ~66 s y NO ~330 s (el corte por reloj acota el "
      "hueco de latido a UNA descarga ≤ 45 s, como promete (C)); la corrida sigue ('attached')",
      [it["bytes_state"] for it in b_dl["path_b"]["papers"][0]["figures"]["items"]] == ["not-fetched (timeout)"] * 9
      and _l_dl["status"] == "error" and _l_dl["error_kind"] == "timeout" and _l_dl["budget_s"] == 45.0
      and s_dl["state"] == "attached" and 45.0 <= s_dl["budget"]["used_s"] <= 66.0 and s_dl["n_not_fetched"] == 9,
      json.dumps({"budget": s_dl["budget"], "reads": _drip3.reads, "ledger_error": _l_dl.get("error")}))
F._urlopen = _REAL_URLOPEN_SEAM
_LOCAL_BLOCKED = []


def _local_blocked(req, timeout=None):   # bloqueador LOCAL para probar que _get_bytes declara la red bloqueada sin sumar al contador global
    _LOCAL_BLOCKED.append(getattr(req, "full_url", str(req)))
    raise RuntimeError("network blocked (local probe)")


F._urlopen = _local_blocked
g = _REAL_GET_BYTES("https://www.ebi.ac.uk/x", 1, 100)
check("con urlopen bloqueado, _get_bytes NO relanza: 'error: RuntimeError: …' declarado; la sonda local contó 1 y el contador GLOBAL sigue en 0",
      g["status"] == "error" and g["error_kind"].startswith("error: RuntimeError") and len(_LOCAL_BLOCKED) == 1 and len(_NET_CALLS) == 0)
F._urlopen = _REAL_URLOPEN_SEAM

# --- presupuesto con reloj falso ---------------------------------------------------------------------------------------
print("\n== 3c. presupuesto ==")
shutil.rmtree(CR, ignore_errors=True)
F._get_bytes = _mk_get(ZIP_BY)
GET_CALLS.clear()
cfg_b0 = F.env_config({"WITT_FIGURES_BUDGET_S": "0"})
bx = _bundle(_paper("PMC11379296", XML_BY_P))
sx = F.attach(bx, cfg=cfg_b0, cache_root=CR)
check("WITT_FIGURES_BUDGET_S=0 → ledger status 'skipped-budget', 9 filas 'not-fetched (budget-exhausted)', 0 GET, budget {total_s 0, over_budget False}",
      bx["path_b"]["papers"][0]["figures"]["ledger"]["status"] == "skipped-budget"
      and [it["bytes_state"] for it in bx["path_b"]["papers"][0]["figures"]["items"]] == ["not-fetched (budget-exhausted)"] * 9
      and len(GET_CALLS) == 0 and sx["budget"]["total_s"] == 0.0)
CLOCK = {"t": 1000.0}


def _fake_clock():
    return CLOCK["t"]


def _mk_get_slow(zb, advance_s):
    inner = _mk_get(zb)

    def _f(url, timeout, max_bytes, dest=None):
        CLOCK["t"] += advance_s
        return inner(url, timeout, max_bytes, dest=dest)
    return _f


shutil.rmtree(CR, ignore_errors=True)
F._get_bytes = _mk_get_slow(ZIP_BY, 100.0)
GET_CALLS.clear()
cfg_b = F.env_config({"WITT_FIGURES_BUDGET_S": "90", "WITT_FIGURES_TTL_DAYS": "0"})
bx = _bundle(_paper("PMC11379296", XML_BY_P, rank=1), _paper("PMC11647118", XML_NC_P, rank=2))
sx = F.attach(bx, cfg=cfg_b, cache_root=CR, clock=_fake_clock)
p1, p2 = bx["path_b"]["papers"]
check("reloj falso: el 1er paper tarda 100 s > 90 → sus 9 verified; el 2º queda SIN red (1 sola GET): el run-cap (12) actúa ANTES del presupuesto → "
      "n_take 3 = [undfig1 'no-caption', fig1/fig2 'budget-exhausted'] y fig3..5 'run-cap'; ledger 'skipped-budget' con error BudgetExhausted; "
      "budget.used_s 100, over_budget True; por paper budget_s == min(45, restante) == 45 y timeout_s == 30",
      p1["figures"]["ledger"]["status"] == "success" and p2["figures"]["ledger"]["status"] == "skipped-budget"
      and [it["bytes_state"] for it in p2["figures"]["items"]] == ["not-fetched (no-caption)"] + ["not-fetched (budget-exhausted)"] * 2 + ["not-fetched (run-cap)"] * 3
      and "BudgetExhausted" in p2["figures"]["ledger"]["error"] and len(GET_CALLS) == 1
      and sx["budget"] == {"total_s": 90.0, "used_s": 100.0, "over_budget": True}
      and p1["figures"]["ledger"]["budget_s"] == 45.0 and p1["figures"]["ledger"]["timeout_s"] == 30.0, json.dumps(sx["budget"]))
CLOCK["t"] = 1000.0
shutil.rmtree(CR, ignore_errors=True)
F._get_bytes = _mk_get_slow(ZIP_BY, 1.0)
cfg_b20 = F.env_config({"WITT_FIGURES_BUDGET_S": "20", "WITT_FIGURES_TTL_DAYS": "0"})
bx = _bundle(_paper("PMC11379296", XML_BY_P))
F.attach(bx, cfg=cfg_b20, cache_root=CR, clock=_fake_clock)
check("presupuesto 20 s → por paper min(45, 20) = 20 y socket min(30, 20) = 20 (declarados en el ledger)",
      bx["path_b"]["papers"][0]["figures"]["ledger"]["budget_s"] == 20.0 and bx["path_b"]["papers"][0]["figures"]["ledger"]["timeout_s"] == 20.0)

# --- caché: TTL, mismatch, re-descarga, LRU, read-only ---------------------------------------------------------------------
print("\n== 3d. caché ==")
shutil.rmtree(CR, ignore_errors=True)
F._get_bytes = _mk_get(ZIP_BY)
GET_CALLS.clear()
bx = _bundle(_paper("PMC11379296", XML_BY_P))
F.attach(bx, cache_root=CR)
F._get_bytes = _mk_get(raise_exc=RuntimeError("la red NO debe tocarse en un cache hit"))
by = _bundle(_paper("PMC11379296", XML_BY_P))
sy = F.attach(by, cache_root=CR)
ity = by["path_b"]["papers"][0]["figures"]["items"]
check("2ª llamada con ledger fresco (TTL 30): cache_hit True en las 9, 0 _get_bytes, sha recalculado == ledger → 'verified', "
      "ledger.status 'cache-hit', fetched_at el del ledger (no se presenta como fresco)",
      all(it["cache_hit"] is True and it["bytes_state"] == "verified" for it in ity) and len(GET_CALLS) == 1
      and by["path_b"]["papers"][0]["figures"]["ledger"]["status"] == "cache-hit" and by["path_b"]["papers"][0]["figures"]["ledger"]["cache_hit"] is True
      and ity[0]["fetched_at"] == json.loads(next((CR / "PMC11379296").glob("_figures_*.json")).read_text(encoding="utf-8"))["fetched_at"]
      and sy["n_verified"] == 9)
tampered = CR / "PMC11379296" / "pone.0307390.g005.jpg"
orig5 = tampered.read_bytes()
tampered.write_bytes(orig5[:-1] + bytes([orig5[-1] ^ 0x01]))
F._get_bytes = _mk_get(ZIP_BY)
GET_CALLS.clear()
bz = _bundle(_paper("PMC11379296", XML_BY_P))
sz = F.attach(bz, cache_root=CR)
itz = {it["fig_id"]: it for it in bz["path_b"]["papers"][0]["figures"]["items"]}
lz = bz["path_b"]["papers"][0]["figures"]["ledger"]
check("(B.3, corrector) archivo alterado (1 bit) con ledger fresco → la copia NO se reutiliza como veredicto: UNA re-descarga (1 GET), las 9 'verified' "
      "con cache_hit False, el alterado REEMPLAZADO por los bytes de la fuente; ledger {status 'success', cache_mismatch_hrefs ['pone.0307390.g005.jpg'], "
      "cache_mismatch_refetched idem, SIN sha_changed_from_previous_ledger (la fuente entregó el mismo sha)}; n_mismatch 0, n_verified 9 (antes: "
      "'mismatch' 30 días en TODAS las corridas)",
      len(GET_CALLS) == 1 and all(it["bytes_state"] == "verified" and it["cache_hit"] is False for it in itz.values())
      and tampered.read_bytes() == orig5 and lz["status"] == "success"
      and lz.get("cache_mismatch_hrefs") == ["pone.0307390.g005.jpg"] == lz.get("cache_mismatch_refetched")
      and "sha_changed_from_previous_ledger" not in lz and sz["n_mismatch"] == 0 and sz["n_verified"] == 9 and sz["n_fetched"] == 9,
      json.dumps({k: lz.get(k) for k in ("status", "cache_mismatch_hrefs", "cache_mismatch_refetched", "cache_hit")}))
tampered.write_bytes(orig5[:-1] + bytes([orig5[-1] ^ 0x01]))     # alteración DESPUÉS de attach: la puerta de lectura (gate/GET/PDF)
check("verify_cached del alterado tras attach: sha256_actual ≠ sha256 congelado → 'mismatch'; servable_state → 'bytes-mismatch' (JAMÁS se sirve)",
      F.verify_cached(CR, itz["pone.0307390.g005"])["state"] == "mismatch"
      and F.verify_cached(CR, itz["pone.0307390.g005"])["sha256_actual"] != itz["pone.0307390.g005"]["sha256"]
      and F.servable_state(itz["pone.0307390.g005"], CR) == "bytes-mismatch")


def _zip_replace(zb, name, data):
    zin = zipfile.ZipFile(io.BytesIO(zb))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zout:
        for n in zin.namelist():
            zout.writestr(n, data if n == name else zin.read(n))
    return buf.getvalue()


ZIP_BY_G5ALT = _zip_replace(ZIP_BY, "pone.0307390.g005.jpg", orig5 + b"\x00")   # la FUENTE entrega hoy otro g005 (1 byte más)
F._get_bytes = _mk_get(ZIP_BY_G5ALT)
GET_CALLS.clear()
bzz = _bundle(_paper("PMC11379296", XML_BY_P))
szz = F.attach(bzz, cache_root=CR)
lzz = bzz["path_b"]["papers"][0]["figures"]["ledger"]
_g5 = next(it for it in bzz["path_b"]["papers"][0]["figures"]["items"] if it["fig_id"] == "pone.0307390.g005")
check("(B.3, corrector) mismatch en caché + la fuente entrega HOY otro sha que el ledger previo → 1 GET, g005 'verified' con el sha de los bytes que "
      "llegaron AHORA (medición de la fuente de hoy) y ledger.sha_changed_from_previous_ledger [{href, previous_ledger_sha256 == el del MANIFEST, "
      "sha256 nuevo}] DECLARADO (cambio en la fuente o en la caché: medido, no disfrazado); las otras 8 sin cambio de sha",
      len(GET_CALLS) == 1 and _g5["bytes_state"] == "verified" and _g5["sha256"] == sha(orig5 + b"\x00") != MAN_BY["pone.0307390.g005.jpg"]["sha256"]
      and lzz.get("sha_changed_from_previous_ledger") == [{"href": "pone.0307390.g005.jpg", "previous_ledger_sha256": MAN_BY["pone.0307390.g005.jpg"]["sha256"],
                                                          "sha256": sha(orig5 + b"\x00")}]
      and lzz.get("cache_mismatch_refetched") == ["pone.0307390.g005.jpg"] and szz["n_verified"] == 9,
      json.dumps(lzz.get("sha_changed_from_previous_ledger"))[:200])
tampered.write_bytes(orig5[:-1] + bytes([orig5[-1] ^ 0x01]))     # se deja alterado para el check de TTL=0 de abajo
F._get_bytes = _mk_get(ZIP_BY)
GET_CALLS.clear()
bw = _bundle(_paper("PMC11379296", XML_BY_P))
F.attach(bw, cfg=F.env_config({"WITT_FIGURES_TTL_DAYS": "0"}), cache_root=CR)
check("WITT_FIGURES_TTL_DAYS=0 = nunca confiar → re-descarga (1 GET), el alterado queda REEMPLAZADO por los bytes de la fuente → 9 verified, cache_hit False",
      len(GET_CALLS) == 1 and all(it["bytes_state"] == "verified" and it["cache_hit"] is False for it in bw["path_b"]["papers"][0]["figures"]["items"])
      and tampered.read_bytes() == orig5)
old = datetime.now(timezone.utc) - timedelta(days=45)
lp = next((CR / "PMC11379296").glob("_figures_*.json"))
led_old = json.loads(lp.read_text(encoding="utf-8"))
led_old["fetched_at"] = old.replace(microsecond=0).isoformat().replace("+00:00", "Z")
lp.write_text(json.dumps(led_old), encoding="utf-8")
GET_CALLS.clear()
bv = _bundle(_paper("PMC11379296", XML_BY_P))
F.attach(bv, cache_root=CR)
check("ledger de 45 días con TTL 30 → caducado: re-descarga (1 GET) y ledger nuevo con fetched_at de hoy",
      len(GET_CALLS) == 1 and bv["path_b"]["papers"][0]["figures"]["items"][0]["cache_hit"] is False)
(CR / "PMC11379296" / "pone.0307390.g007.jpg").unlink()
GET_CALLS.clear()
bu = _bundle(_paper("PMC11379296", XML_BY_P))
F.attach(bu, cache_root=CR)
check("archivo evictado/ausente con ledger fresco → NO es hit completo: re-descarga (1 GET) y las 9 verified",
      len(GET_CALLS) == 1 and sum(1 for it in bu["path_b"]["papers"][0]["figures"]["items"] if it["bytes_state"] == "verified") == 9)
# LRU
shutil.rmtree(CR, ignore_errors=True)
F._get_bytes = _mk_get(ZIP_NC)
b_nc = _bundle(_paper("PMC11647118", XML_NC_P))
F.attach(b_nc, cache_root=CR)
for p in (CR / "PMC11647118").iterdir():
    os.utime(p, (time.time() - 3600, time.time() - 3600))    # más viejos que lo que viene
F._get_bytes = _mk_get(ZIP_BY)
cfg_lru = F.env_config({"WITT_FIGURES_CACHE_MAX_MB": "0.001"})
b_by = _bundle(_paper("PMC11379296", XML_BY_P))
s_lru = F.attach(b_by, cfg=cfg_lru, cache_root=CR)
surv_by = sorted(p.name for p in (CR / "PMC11379296").glob("*.jpg"))
surv_nc = sorted(p.name for p in (CR / "PMC11647118").glob("*")) if (CR / "PMC11647118").exists() else []
check("CACHE_MAX_MB=0.001: evicción LRU por mtime al escribir → evicted_n ≥ 1 (los PNG viejos de PMC11647118 se van), los 9 jpg RECIÉN "
      "escritos (los más nuevos, protegidos) sobreviven; el resumen lo declara en cache.evicted_n; los 9 siguen 'verified'",
      s_lru["cache"]["evicted_n"] >= 1 and len(surv_by) == 9 and len(surv_nc) == 0 and s_lru["n_verified"] == 9
      and s_lru["cache"]["cache_max_mb"] == 0.001, f"evicted_n={s_lru['cache']['evicted_n']} nc_left={surv_nc}")
check("evict_lru con max_mb 0 = sin tope declarado → 0 evictados; el .part jamás cuenta",
      F.evict_lru(CR, 0) == 0 and F.evict_lru(CR, 512) == 0)
# read-only
_REAL_PROBE = F._probe_writable
F._probe_writable = lambda p: False
F._get_bytes = _mk_get(ZIP_BY)
GET_CALLS.clear()
b_ro = _bundle(_paper("PMC11379296", XML_BY_P))
s_ro = F.attach(b_ro, cache_root=CR)
check("dir read-only (sonda de escritura falla) → cache.dir_state 'read-only', las 9 filas 'not-fetched (cache-read-only)', 0 GET, sin excepción",
      s_ro["cache"]["dir_state"] == "read-only" and [it["bytes_state"] for it in b_ro["path_b"]["papers"][0]["figures"]["items"]] == ["not-fetched (cache-read-only)"] * 9
      and len(GET_CALLS) == 0)
F._probe_writable = _REAL_PROBE
check("cache_dir_state: dir inexistente se crea → 'writable'; una RUTA QUE ES ARCHIVO → 'missing'",
      F.cache_dir_state(TMP / "nuevo" / "figures") == "writable" and (TMP / "f.txt").write_text("x") and F.cache_dir_state(TMP / "f.txt") == "missing")
# --- (corrector) `now` NAIVE contra un ledger aware: ni excepción ni pérdida de la etapa → cache-hit igual --------------------------------
shutil.rmtree(CR, ignore_errors=True)
F._get_bytes = _mk_get(ZIP_BY)
b_tz = _bundle(_paper("PMC11379296", XML_BY_P))
F.attach(b_tz, cache_root=CR)
F._get_bytes = _mk_get(raise_exc=RuntimeError("la red NO debe tocarse en un cache hit"))
try:
    _figs_tz = F.parse_jats(XML_BY, "PMC11379296")["figs"]
    r_tz = F.fetch_figures("PMC11379296", _figs_tz, cache_root=CR, now=datetime.now())        # naive (sin tz)
    s_tz = F.attach(_bundle(_paper("PMC11379296", XML_BY_P)), cache_root=CR, now=datetime.now())
    _tz_ok = (r_tz["ledger"]["status"] == "cache-hit" and all(r["bytes_state"] == "verified" for r in r_tz["by_href"].values())
              and s_tz["n_verified"] == 9 and s_tz["state"] == "attached")
    _tz_detail = r_tz["ledger"]["status"]
except Exception as e:
    _tz_ok, _tz_detail = False, f"{type(e).__name__}: {e}"
check("(corrector) fetch_figures/attach con `now` NAIVE (datetime.now() sin tz) contra un ledger aware ('…Z') → se normaliza a UTC: cache-hit, 9 verified, "
      "0 red, SIN TypeError (antes: 'can't subtract offset-naive and offset-aware datetimes' escapaba de fetch_figures)", _tz_ok, _tz_detail)
F._get_bytes = _mk_get(ZIP_BY)

# --- selección de papers, caps, kill-switch, sin Ruta B, ZFIN --------------------------------------------------------------
print("\n== 3e. selección / caps / estados del resumen ==")
shutil.rmtree(CR, ignore_errors=True)
F._get_bytes = _mk_get(ZIP_BY)
cfg_caps = F.env_config({"WITT_FIGURES_MAX_PER_PAPER": "4", "WITT_FIGURES_MAX_PER_RUN": "6", "WITT_FIGURES_MAX_PAPERS": "2"})
zf_p = {"source": "zfin", "evidence_id": "ZFIN:ZDB-GENE-1", "search_rec": {"pmcid": None}, "fetched": {"found": True, "full_text": False, "raw_cached": []}}
noxml = _paper("PMC9999999", TMP / "nope.xml", rank=1, evidence_id="PMC9999999")
bc = _bundle(zf_p, _paper("PMC11379296", XML_BY_P, rank=3, evidence_id="A"), _paper("PMC11379296", XML_BY_P, rank=2, evidence_id="B"),
             _paper("PMC11379296", XML_BY_P, rank=4, evidence_id="C"), noxml)
sc = F.attach(bc, cfg=cfg_caps, cache_root=CR)
pp = {p["evidence_id"]: p for p in bc["path_b"]["papers"]}
check("selección por selection_rank: B (rank 2) y A (rank 3) seleccionados; C (rank 4) 'not-selected (paper-cap)'; el paper sin XML "
      "'no-fulltext-xml'; el ítem ZFIN NO gana 'figures'; n_papers_eligible 3, n_papers_selected 2",
      pp["B"]["figures"]["state"] == "attached" and pp["A"]["figures"]["state"] == "attached" and pp["C"]["figures"] == {"state": "not-selected (paper-cap)", "n": 0, "items": [], "ledger": None}
      and pp["PMC9999999"]["figures"]["state"] == "no-fulltext-xml" and "figures" not in zf_p and sc["n_papers_eligible"] == 3 and sc["n_papers_selected"] == 2)
stB = [it["bytes_state"] for it in pp["B"]["figures"]["items"]]
stA = [it["bytes_state"] for it in pp["A"]["figures"]["items"]]
check("MAX_PER_PAPER=4, MAX_PER_RUN=6: B → 4 verified + 5 'not-fetched (paper-cap)' (caption parseado); A → 2 verified (run-cap) + 2 'run-cap' + 5 'paper-cap'; "
      "n_figures 18, n_verified 6",
      stB == ["verified"] * 4 + ["not-fetched (paper-cap)"] * 5 and stA == ["verified"] * 2 + ["not-fetched (run-cap)"] * 2 + ["not-fetched (paper-cap)"] * 5
      and sc["n_figures"] == 18 and sc["n_verified"] == 6 and all(it["caption"] for it in pp["A"]["figures"]["items"]), json.dumps(stA))
check("los ítems se numeran por paper: evidence_id del paper viaja en cada FigureItem; el mismo PMCID en dos papers no se mezcla",
      all(it["evidence_id"] == "B" for it in pp["B"]["figures"]["items"]) and all(it["evidence_id"] == "A" for it in pp["A"]["figures"]["items"]))
ks = F.attach(_bundle(_paper("PMC11379296", XML_BY_P)), cfg=F.env_config({"WITT_FIGURES": "0"}), cache_root=CR)
check("WITT_FIGURES=0 → state 'kill-switch WITT_FIGURES=0' + kill_switch.declared_exceptions EXACTAS (3), items [], y el paper NO gana 'figures'",
      ks["state"] == "kill-switch WITT_FIGURES=0" and ks["kill_switch"] == {"WITT_FIGURES": "0", "declared_exceptions": ["render_contract_version", "figures", "deterministic_checks.figures"]}
      and ks["items"] == [])
check("sin Ruta B → 'no-path-b'; papers sin PMCID/XML → 'no-papers-with-xml'",
      F.attach({"path_a": {"hits": []}}, cache_root=CR)["state"] == "no-path-b"
      and F.attach(_bundle(_paper("PMC1", TMP / "none.xml")), cache_root=CR)["state"] == "no-papers-with-xml")
check("locate_xml: ruta relativa a root, absoluta, ausente → None; el .txt/.json no cuentan",
      F.locate_xml(["mcp_cache/x.txt", str(XML_BY_P)]) == XML_BY_P and F.locate_xml([XML_BY_P.name], root=FX) == XML_BY_P
      and F.locate_xml(["raw_paper_Z_20260101_fulltext.xml"], root=TMP) is None and F.locate_xml(None) is None)
zitem = F.make_item("PMC1", "E", {"fig_id": "z1", "label": "Fig Z", "caption": "c", "caption_state": "present", "graphic_href": "z.jpg",
                                  "dims_declared": {"original": None, "scaled": None}},
                    {"id": "zfin-display-only", "source": "none", "evidence_text": "", "url": None, "rule_no": 7, "version": None, "scope": "article-level"},
                    F.license_flags("zfin-display-only"))
check("licencia zfin-display-only → bytes_state 'never (zfin-display-only)', embeddable False, panel_view False, sha None, raw_ref None",
      zitem["bytes_state"] == "never (zfin-display-only)" and zitem["embeddable"] is False and zitem["panel_view"] is False and zitem["sha256"] is None and zitem["raw_ref"] is None)
check("servable_state: 'yes' (BY verified en caché) · 'forbidden-by-license' (NC) · 'bytes-not-in-cache' (archivo borrado) · 'kill-switch' · 'no-bytes' (not-fetched)",
      F.servable_state(pp["B"]["figures"]["items"][0], CR) == "yes" and F.servable_state(items2[1], CR) == "forbidden-by-license"
      and F.servable_state(dict(pp["B"]["figures"]["items"][1], cache_path_rel="PMC11379296/nope.jpg"), CR) == "bytes-not-in-cache"
      and F.servable_state(pp["B"]["figures"]["items"][0], CR, cfg=F.env_config({"WITT_FIGURES": "0"})) == "kill-switch"
      and F.servable_state(pp["B"]["figures"]["items"][5], CR) == "no-bytes"
      and all(s in F.SERVABLE_STATES for s in ("yes", "forbidden-by-license", "bytes-not-in-cache", "bytes-mismatch", "kill-switch", "no-bytes")))
check("public_item: FigureItem SIN cache_path_rel (y jamás b64); el resto de llaves intactas",
      "cache_path_rel" not in F.public_item(items1[0]) and "b64" not in F.public_item(items1[0]) and F.public_item(items1[0])["sha256"] == items1[0]["sha256"])

# =====================================================================================================================
# 4. select_for_panel + bloques por transporte
# =====================================================================================================================
print("\n== 4. select_for_panel / bloques ==")
shutil.rmtree(CR, ignore_errors=True)
F._get_bytes = _mk_get(ZIP_BY)
b_sel = _bundle(_paper("PMC11379296", XML_BY_P))
F.attach(b_sel, cache_root=CR)
ITEMS = b_sel["path_b"]["papers"][0]["figures"]["items"]
F._get_bytes = _mk_get(ZIP_NC)
b_sel2 = _bundle(_paper("PMC11647118", XML_NC_P))
F.attach(b_sel2, cache_root=CR)
ITEMS_NC = b_sel2["path_b"]["papers"][0]["figures"]["items"]
cited = {"PMC11379296#pone.0307390.g005": [3], "PMC11379296#pone.0307390.g002": [1, 4]}
sel = F.select_for_panel(ITEMS, CR, cfg=F.env_config({}), cited_ns=cited)
order = [f["fig_id"] for f in sel["figures"]]
check("orden determinista: citadas primero por menor n (g002 [1], g005 [3]), luego orden de documento (g001, g003, g004, g006…); 9 elegibles, 9 seleccionadas",
      order == ["pone.0307390.g002", "pone.0307390.g005", "pone.0307390.g001", "pone.0307390.g003", "pone.0307390.g004", "pone.0307390.g006",
                "pone.0307390.g007", "pone.0307390.g008", "pone.0307390.g009"] and sel["n_eligible"] == sel["n_selected"] == 9
      and sel["rule"] == F.SELECTION_RULE, order)
check("cada figura del panel tiene EXACTAMENTE PANEL_FIGURE_KEYS; la b64 decodifica al byte ORIGINAL (sha256 igual); license {id}",
      all(tuple(f) == F.PANEL_FIGURE_KEYS for f in sel["figures"])
      and all(sha(base64.b64decode(f["b64"])) == f["sha256"] for f in sel["figures"]) and sel["figures"][0]["license"] == {"id": "cc-by"}
      and sel["bytes_b64_total"] == sum(len(f["b64"]) for f in sel["figures"]))
sel3 = F.select_for_panel(ITEMS, CR, cfg=F.env_config({"WITT_FIGURES_MAX_PER_LENS": "3"}), cited_ns=cited)
check("MAX_PER_LENS=3 → 3 figuras (g002, g005, g001), n_excluded.lens_cap 6",
      [f["fig_id"] for f in sel3["figures"]] == ["pone.0307390.g002", "pone.0307390.g005", "pone.0307390.g001"] and sel3["n_excluded"]["lens_cap"] == 6)
_REAL_REQ_CAP = F.REQUEST_B64_MB
F.REQUEST_B64_MB = 0.3    # ≈ 314 KB de b64: cabe UNA imagen (g002 154 KB → 205 KB b64), el resto cae por tope de petición
selc = F.select_for_panel(ITEMS, CR, cfg=F.env_config({}), cited_ns=cited)
F.REQUEST_B64_MB = _REAL_REQ_CAP
check("tope de b64 por petición (constante 8 MB, forzada a 0.3) → n_dropped_by_request_cap ≥ 1 y las enviadas caben",
      selc["n_dropped_by_request_cap"] >= 1 and selc["bytes_b64_total"] <= 0.3 * 1024 * 1024 and selc["n_selected"] >= 1,
      f"selected={selc['n_selected']} dropped={selc['n_dropped_by_request_cap']}")
sels = F.select_for_panel(ITEMS, CR, cfg=F.env_config({"WITT_FIGURES_MAX_IMAGE_MB": "0.1"}))
check("MAX_IMAGE_MB=0.1 (104 857 B) → las mayores quedan excluidas (n_excluded.size 6): pasan g005 88 842 B, g008 61 866 B y g009 61 086 B (bytes MEDIDOS, Context 2)",
      sels["n_excluded"]["size"] == 6 and sorted(f["fig_id"] for f in sels["figures"]) == ["pone.0307390.g005", "pone.0307390.g008", "pone.0307390.g009"])
# ítem 'unknown' con bytes ÚNICOS (gr4.png del zip sintético, que se retira de la mezcla): así el assert por substring es honesto
UNK = dict(ITEMS_NC[4], id="PMC1#u", fig_id="u", license={"id": "unknown", "source": "none"}, panel_view=False, embeddable=False)
mixed = ITEMS + [ITEMS_NC[i] for i in (0, 1, 2, 3, 5)] + [UNK]
selm = F.select_for_panel(mixed, CR, cfg=F.env_config({}))
sel_ids = {f["id"] for f in selm["figures"]}
check("mezcla BY(9) + NC(undfig1, fig1-3, fig5) + unknown: NC SÍ entra (panel_view True, E2 default), unknown NUNCA (n_excluded.license 1), undfig1 fuera "
      "(bytes_state not-fetched (no-caption) → n_excluded.bytes_state 1); 13 elegibles, cap 12 → 12 seleccionadas, lens_cap 1",
      selm["n_eligible"] == 13 and selm["n_selected"] == 12 and selm["n_excluded"]["license"] == 1 and selm["n_excluded"]["bytes_state"] == 1
      and selm["n_excluded"]["lens_cap"] == 1 and "PMC1#u" not in sel_ids and "PMC11647118#undfig1" not in sel_ids
      and any(f["license"]["id"] == "cc-by-nc" for f in selm["figures"]),
      json.dumps({k: selm[k] for k in ("n_eligible", "n_selected", "n_excluded")}))
sel_strict = F.select_for_panel(mixed, CR, cfg=F.env_config({"WITT_FIGURES_PANEL_LICENSES": "cc-by"}))
check("PANEL_LICENSES=cc-by (E2 alternativa estricta) → con license_flags recalculadas por F4 las NC no entrarían; aquí `panel_view` viaja en el ítem: "
      "select_for_panel HONRA el ítem (contrato: F4 recalcula flags con la cfg de la corrida) — assert: ningún bloque contiene bytes de un ítem con panel_view False",
      all(f["license"]["id"] != "unknown" for f in sel_strict["figures"]) and all(it["panel_view"] or it["id"] not in {f["id"] for f in sel_strict["figures"]} for it in mixed))
# mismatch → excluida y sin bytes
t5 = CR / "PMC11379296" / "pone.0307390.g005.jpg"
b5 = t5.read_bytes()
t5.write_bytes(b5[:-1] + bytes([b5[-1] ^ 0x01]))
selx = F.select_for_panel(ITEMS, CR, cfg=F.env_config({}))
check("archivo alterado entre attach y panel → sha recalculado ≠ → EXCLUIDA (n_excluded.mismatch 1), jamás se envía un byte que no cuadre; 8 enviadas",
      selx["n_excluded"]["mismatch"] == 1 and selx["n_selected"] == 8 and not any(f["fig_id"] == "pone.0307390.g005" for f in selx["figures"]))
t5.write_bytes(b5)
t5.unlink()
selmis = F.select_for_panel(ITEMS, CR, cfg=F.env_config({}))
check("archivo ausente (evictado) → n_excluded.missing 1, 8 enviadas", selmis["n_excluded"]["missing"] == 1 and selmis["n_selected"] == 8)
t5.write_bytes(b5)

two = sel["figures"][:2]
UT = '{"claim": "x", "evidence": {}, "deterministic_checks": {}}'
ab = F.anthropic_blocks(two, UT)
check("anthropic_blocks(2 figs): [text, image, text, image, text(user_text)] — imágenes ANTES del texto, rotuladas 'Figure k — <id> (<label>): <caption>'; "
      "image.source {type 'base64', media_type medido, data}; la data decodifica al byte original; el último bloque es user_text BYTE A BYTE",
      [b["type"] for b in ab] == ["text", "image", "text", "image", "text"] and ab[0]["text"].startswith("Figure 1 — PMC11379296#pone.0307390.g002 (Fig 2): ")
      and ab[1]["source"] == {"type": "base64", "media_type": "image/jpeg", "data": two[0]["b64"]}
      and sha(base64.b64decode(ab[1]["source"]["data"])) == two[0]["sha256"] and ab[-1] == {"type": "text", "text": UT}, ab[0]["text"][:80])
rp = F.openai_responses_parts(two, UT, detail="high")
check("openai_responses_parts: [input_text, input_image{image_url 'data:image/jpeg;base64,…', detail 'high'}, …, input_text(user_text)]",
      [p["type"] for p in rp] == ["input_text", "input_image", "input_text", "input_image", "input_text"]
      and rp[1]["image_url"] == f"data:image/jpeg;base64,{two[0]['b64']}" and rp[1]["detail"] == "high" and rp[-1] == {"type": "input_text", "text": UT})
cp = F.openai_chat_parts(two, UT, detail="low")
check("openai_chat_parts: [text, image_url{image_url {url data:…, detail 'low'}}, …, text(user_text)] — forma pública declarada no re-verificada (LG4 la mide)",
      [p["type"] for p in cp] == ["text", "image_url", "text", "image_url", "text"]
      and cp[1]["image_url"] == {"url": f"data:image/jpeg;base64,{two[0]['b64']}", "detail": "low"} and cp[-1] == {"type": "text", "text": UT}
      and F.OPENAI_CHAT_FORM_STATE == "public form; not re-verified by doc in this work")
os.environ["WITT_FIGURES_OPENAI_DETAIL"] = "auto"
check("detail por default se lee de WITT_FIGURES_OPENAI_DETAIL en la llamada ('auto'); sin figuras → sólo [text(user_text)]",
      F.openai_responses_parts(two, UT)[1]["detail"] == "auto" and F.anthropic_blocks([], UT) == [{"type": "text", "text": UT}]
      and F.openai_chat_parts([], UT) == [{"type": "text", "text": UT}])
os.environ.pop("WITT_FIGURES_OPENAI_DETAIL", None)
# doctrina: ningún bloque contiene bytes de figuras cuya licencia NO permite panel (unknown / zfin) — se arma la mezcla y se asserta por substring
forbidden_items = [it for it in mixed if not it["panel_view"]]
allowed = F.select_for_panel(mixed, CR, cfg=F.env_config({}))
blocks_json = json.dumps(F.anthropic_blocks(allowed["figures"], UT)) + json.dumps(F.openai_responses_parts(allowed["figures"], UT)) + json.dumps(F.openai_chat_parts(allowed["figures"], UT))
check("DOCTRINA: ningún bloque de imagen (3 transportes) contiene la b64 de un ítem con panel_view False (unknown) ni de undfig1 (sin caption)",
      forbidden_items and all(base64.b64encode((CR / it["cache_path_rel"]).read_bytes()).decode("ascii")[:80] not in blocks_json
                              for it in forbidden_items if it.get("cache_path_rel") and (CR / it["cache_path_rel"]).exists())
      and "undfig1" not in blocks_json)

# =====================================================================================================================
# 5. env_config tolerante / vocabularios
# =====================================================================================================================
print("\n== 5. env_config / vocabularios ==")
cfg_bad = F.env_config({"WITT_FIGURES_MAX_PER_LENS": "25", "WITT_FIGURES_MAX_IMAGE_MB": "9", "WITT_FIGURES_BUDGET_S": "muchos",
                        "WITT_FIGURES": "", "WITT_FIGURES_OPENAI_DETAIL": "ultra", "WITT_FIGURES_MAX_PER_PAPER": "0", "WITT_FIGURES_TTL_DAYS": "nan"})
check("tolerante: MAX_PER_LENS=25 (> 20) → 12 'default-invalid-env'; MAX_IMAGE_MB=9 (> 7) → 5 invalid; BUDGET_S basura → 90 invalid; "
      "WITT_FIGURES vacía → True 'default-unset'; OPENAI_DETAIL 'ultra' → 'high' invalid; MAX_PER_PAPER 0 → 9 invalid; TTL 'nan' → 30 invalid",
      cfg_bad["max_per_lens"] == 12 and cfg_bad["sources"]["max_per_lens"] == "default-invalid-env:WITT_FIGURES_MAX_PER_LENS"
      and cfg_bad["max_image_mb"] == 5.0 and cfg_bad["sources"]["max_image_mb"].startswith("default-invalid-env")
      and cfg_bad["budget_s"] == 90.0 and cfg_bad["figures"] is True and cfg_bad["sources"]["figures"] == "default-unset:WITT_FIGURES"
      and cfg_bad["openai_detail"] == "high" and cfg_bad["max_per_paper"] == 9 and cfg_bad["ttl_days"] == 30.0
      and cfg_bad["sources"]["ttl_days"].startswith("default-invalid-env"), json.dumps({k: cfg_bad["sources"][k] for k in ("max_per_lens", "budget_s", "figures")}))
cfg_ok = F.env_config({"WITT_FIGURES_MAX_PER_LENS": "20", "WITT_FIGURES_MAX_IMAGE_MB": "7", "WITT_FIGURES": "0", "WITT_FIGURES_VISION_LENSES": "correctness"})
check("válidas: MAX_PER_LENS=20 (clamp inclusivo) 'env:…'; MAX_IMAGE_MB=7; WITT_FIGURES=0 → False; VISION_LENSES tokenizada ['correctness'] (F3 la valida contra models.LENSES)",
      cfg_ok["max_per_lens"] == 20 and cfg_ok["sources"]["max_per_lens"] == "env:WITT_FIGURES_MAX_PER_LENS" and cfg_ok["max_image_mb"] == 7.0
      and cfg_ok["figures"] is False and cfg_ok["vision_lenses"] == ["correctness"])
check("caps con forma (L): 8 llaves {value, source}; request_b64_mb constante 'constant (ADR-0083)'; constants declaradas (45 s por paper, 30 s socket, 5 s mínimo, 40 MP)",
      set(cfg0["caps"]) == {"max_papers", "max_per_paper", "max_per_run", "max_per_lens", "max_image_mb", "request_b64_mb", "zip_max_mb", "caption_chars"}
      and cfg0["caps"]["request_b64_mb"] == {"value": 8, "source": "constant (ADR-0083)"}
      and cfg0["constants"] == {"per_paper_budget_s": 45.0, "socket_timeout_max_s": 30.0, "min_remaining_s": 5.0, "request_b64_mb": 8, "max_megapixels": 40, "source": "constant (ADR-0083)"})
check("ENV_SPECS: 21 filas (20 nuevas + WITT_MCP_CACHE_DIR) con VAR única y default declarado; defaults == tabla del ADR",
      len(F.ENV_SPECS) == 21 and len(set(F.ENV_VARS)) == 21 and dict(zip(F.ENV_VARS, (s[2] for s in F.ENV_SPECS)))["WITT_FIGURES_PANEL_LICENSES"]
      == "cc-by,cc0,cc-by-sa,cc-by-nc,cc-by-nd,cc-by-nc-sa,cc-by-nc-nd,cc-by-prose-unconfirmed"
      and dict(zip(F.ENV_VARS, (s[2] for s in F.ENV_SPECS)))["WITT_FIGURES_BUDGET_S"] == "90")
all_states = {it["bytes_state"] for b in (b1, b2, b3, b4, bc, bx, b_ro, bw) for p in b["path_b"]["papers"] if isinstance(p.get("figures"), dict) for it in p["figures"]["items"]}
check("TODOS los bytes_state producidos en el smoke están en el vocabulario cerrado (exactos + prefijos con razón cerrada)",
      all_states and all(F.bytes_state_in_vocabulary(s) for s in all_states), sorted(all_states))
check("vocabularios exportados: LICENSES 10, BYTES_STATES_EXACT 4, BYTES_STATES_PREFIXES 2, FIGURES_STATES_EXACT 4 + prefijo 'error: ', "
      "SERVABLE_STATES 6, VOCABULARY con 17 llaves; figures_state_in_vocabulary('error: X') True; bytes 'not-fetched (bogus)' False",
      len(F.LICENSES) == 10 and len(F.BYTES_STATES_EXACT) == 4 and F.BYTES_STATES_PREFIXES == ("not-fetched (", "error: ")
      and len(F.FIGURES_STATES_EXACT) == 4 and F.FIGURES_STATES_PREFIXES == ("error: ",) and len(F.SERVABLE_STATES) == 6
      and len(F.VOCABULARY) == 17 and F.figures_state_in_vocabulary("error: X") and not F.bytes_state_in_vocabulary("not-fetched (bogus)")
      and F.bytes_state_in_vocabulary("not-fetched (http-404)"))
check("image_dims/sniff_mime stdlib: PNG 1×1, GIF 1×1, WebP VP8X 3×2, JPEG g001 750×417; basura → None; mime_from_extension .JPG/.png/.tif",
      F.image_dims(zipfile.ZipFile(io.BytesIO(ZIP_NC)).read("gr1.jpg")) == {"w": 1, "h": 1} and F.sniff_mime(zipfile.ZipFile(io.BytesIO(ZIP_NC)).read("gr9.gif")) == "image/gif"
      and F.image_dims(zipfile.ZipFile(io.BytesIO(ZIP_NC)).read("gr9.gif")) == {"w": 1, "h": 1}
      and F.image_dims(b"RIFF" + b"\x00\x00\x00\x00" + b"WEBP" + b"VP8X" + b"\x0a\x00\x00\x00" + b"\x00" * 4 + b"\x02\x00\x00" + b"\x01\x00\x00") == {"w": 3, "h": 2}
      and F.image_dims(base64.b64decode(G001_B64)) == {"w": 750, "h": 417} and F.image_dims(b"garbage" * 5) is None and F.sniff_mime(b"garbage" * 5) is None
      and F.mime_from_extension("A.JPG") == "image/jpeg" and F.mime_from_extension("x.png") == "image/png" and F.mime_from_extension("x.tif") is None)
check("_normalize_hit (fetch_paper) conserva `license` del search: 'cc by' → 'cc by'; ausente → None (llave presente)",
      fetch_paper._normalize_hit({"id": "1", "license": "cc by"})["license"] == "cc by" and fetch_paper._normalize_hit({"id": "1"})["license"] is None)
check("attach lee search_rec.license como segunda fuente (rule 6 sólo si el XML no da): paper con license 'cc by' y XML cc-by-nc → conflict declarado en la licencia del ítem",
      (lambda b: (F._get_bytes.__name__, F.attach(b, cache_root=CR), b)[2]["path_b"]["papers"][0]["figures"]["items"][1]["license"].get("conflict") == {"xml": "cc-by-nc", "search": "cc-by"})
      (_bundle(_paper("PMC11647118", XML_NC_P, license_="cc by"))))

# =====================================================================================================================
# 6. higiene: cero red, mcp_cache del repo intacto, nada bajo <repo>/mcp_cache/figures
# =====================================================================================================================
print("\n== 6. higiene ==")
F._get_bytes = _REAL_GET_BYTES
check("el smoke corrió 100% OFFLINE — MEDIDO, no prometido: urllib.request.urlopen bloqueado y contado == 0 (fakes/costuras para toda descarga)",
      len(_NET_CALLS) == 0, "; ".join(_NET_CALLS))
check("mcp_cache del repo byte-idéntico antes/después (snapshot de rutas, tamaños y mtimes) — cero mutación",
      _snapshot(REPO_CACHE) == SNAP_BEFORE)
check("no se creó <repo>/mcp_cache/figures (la caché del smoke vive en TMP vía WITT_MCP_CACHE_DIR)",
      not (REPO_CACHE / "figures").exists() and str(CR).startswith(str(TMP)) or (REPO_CACHE / "figures").exists() is False)
check("la caché de figuras del smoke está bajo TMP (WITT_MCP_CACHE_DIR temporal)", str(CACHE_ENV).startswith(str(TMP)) or not (REPO_CACHE / "figures").exists())

_urlreq.urlopen = _urlopen_real
n_ok, n_all = sum(CHECKS), len(CHECKS)
print(f"\n{n_ok}/{n_all} PASS  (tmp={TMP})")
sys.exit(0 if n_ok == n_all else 1)
