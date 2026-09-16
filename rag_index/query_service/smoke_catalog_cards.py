"""
smoke_catalog_cards.py — gate NO-SPEND de las FICHAS COMO CÓDIGO (ADR-0082 (A) y (C.1); rebanada C1).

Mide, no supone:
  · 31 fichas golden (`CARDS_COUNT_GOLDEN`), las 17 de la membresía ∈ CARDS, `category` ∈ 6.
  · cada `sha` == sha256 del SUBSTRING EXACTO del .md (bytes del archivo, sin normalizar).
  · `CATALOG_SHA` estable en dos parseos; un byte cambiado en `causal-pruner` (copia en tmp Y edición en
    memoria) mueve SÓLO su sha + el global — las otras 30 no se mueven.
  · headers con sufijo normalizados (3), `header_raw` conservado.
  · obligatorios 31/31; opcionales AUSENTES = llave ausente (jamás ''), con los conteos medidos
    (substrate_evidence 10 · framework 2 · method 1 · upstream/downstream 4 · draft_description 4).
  · errores de parseo (obligatorio faltante, ficha fuera de categoría, nombre duplicado, categoría fuera de
    vocabulario) LANZAN — nunca un default.
  · las 3 filas sin ficha de la matriz ∉ CARDS y cada ficha del catálogo tiene fila (cards_without_row 0).
  · COUNCIL_RULES: 10 ítems, cada uno substring LITERAL de la sección §7 de CLAUDE.md; RULES_SHA cuadra.
  · build_system: bloque A IDÉNTICO para los 17 (un solo sha), bloque B == text_verbatim (sha == CARDS[x].sha),
    cache_control ×2 con CACHE=1 y string con CACHE=0; TTL 1h en AMBOS bloques (regla de la API: 1h antes de
    5m — el A no puede quedarse en 5m delante de un B 1h); basura → default declarado; función PURA.
  · el bloque A no nombra ningún campo prohibido (direct_answer, verdict, confidence, ranking, score); los
    verbos answer / rank / dispatch aparecen SÓLO negados ("do NOT …"); sin fechas ni ids.
  · `urllib.request.urlopen` bloqueado y contado = 0. Sin BD, sin modelo.

Uso (máscara offline de siempre):  python rag_index/query_service/smoke_catalog_cards.py
"""
import hashlib
import json
import re
import shutil
import sys
import tempfile
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "analysis" / "scripts"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# ── red BLOQUEADA y contada (NO-SPEND) ──────────────────────────────────────────────────────────────
N_URLOPEN = [0]


def _blocked_urlopen(*a, **k):
    N_URLOPEN[0] += 1
    raise AssertionError("network blocked: NO-SPEND smoke")


urllib.request.urlopen = _blocked_urlopen

from lib import agent_matrix, catalog_cards as cc  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
CHECKS = []


def check(name, cond, detail=""):
    CHECKS.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + name + (f"  -> {detail}" if detail else ""))


def _raises(fn, exc):
    try:
        fn()
    except exc:
        return True
    except Exception:
        return False
    return False


def _sha(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


MEMBERS = list(agent_matrix.MEMBERS)
RAW_BYTES = cc.CATALOG_PATH_ABS.read_bytes()
RAW = RAW_BYTES.decode("utf-8")

# ── 1 · el catálogo se localiza donde el ADR dice y parsea: 31 golden ───────────────────────────────
check("CATALOG_PATH es hermano de agent_matrix.MATRIX_PATH (ADR-0082 (A))",
      cc.CATALOG_PATH == "skills/custom/organogenesis-agent-architect/references/agent-catalog.md"
      and cc.CATALOG_PATH.rsplit("/", 1)[0] == agent_matrix.MATRIX_PATH.rsplit("/", 1)[0]
      and cc.CATALOG_PATH_ABS.exists(), cc.CATALOG_PATH)
check("CATALOG_STATE 'parsed' (el import no lanza; el estado se DECLARA)", cc.CATALOG_STATE == "parsed",
      cc.CATALOG_STATE)
check("CARDS_COUNT == 31 golden", cc.CARDS_COUNT == cc.CARDS_COUNT_GOLDEN == 31, f"n={cc.CARDS_COUNT}")
check("CATALOG_SHA es un sha256 (64 hex) y no None", isinstance(cc.CATALOG_SHA, str)
      and re.fullmatch(r"[0-9a-f]{64}", cc.CATALOG_SHA) is not None, (cc.CATALOG_SHA or "")[:16])
check("los 17 miembros de la membresía ∈ CARDS", all(m in cc.CARDS for m in MEMBERS) and len(MEMBERS) == 17,
      f"faltan={[m for m in MEMBERS if m not in cc.CARDS]}")
check("card(name) devuelve la ficha; card('nadie') es None (sin ficha ≠ ficha vacía)",
      cc.card("causal-pruner") is cc.CARDS["causal-pruner"] and cc.card("nadie") is None)

# ── 2 · bytes exactos: sha == sha256 del substring del .md; offsets/líneas golden ──────────────────
exact = all(RAW[c["offset_start"]:c["offset_end"]] == c["text_verbatim"]
            and _sha(RAW[c["offset_start"]:c["offset_end"]]) == c["sha"] for c in cc.CARDS.values())
check("cada sha == sha256 del SUBSTRING EXACTO del .md (offsets medidos, sin normalizar)", exact)
check("text_verbatim empieza en '### <header_raw>' y termina donde empieza el siguiente ### / ##",
      all(c["text_verbatim"].startswith("### " + c["header_raw"]) for c in cc.CARDS.values())
      and all(not re.search(r"^#{2,3} ", c["text_verbatim"][4:], re.M) for c in cc.CARDS.values()))
check("los bloques son DISJUNTOS y cubren de la primera ficha (:41) a la última (:638) — golden ADR Context 1",
      min(c["line_start"] for c in cc.CARDS.values()) == 41
      and max(c["line_start"] for c in cc.CARDS.values()) == 638
      and sorted(c["offset_start"] for c in cc.CARDS.values())
      == [c["offset_start"] for c in sorted(cc.CARDS.values(), key=lambda c: c["offset_start"])]
      and all(a["offset_end"] <= b["offset_start"] for a, b in
              zip(sorted(cc.CARDS.values(), key=lambda c: c["offset_start"]),
                  sorted(cc.CARDS.values(), key=lambda c: c["offset_start"])[1:])))
check("causal-pruner vive en :61-84 (golden ADR-0082 Context 3)",
      cc.CARDS["causal-pruner"]["line_start"] == 61 and cc.CARDS["causal-pruner"]["line_end"] == 84,
      f"{cc.CARDS['causal-pruner']['line_start']}-{cc.CARDS['causal-pruner']['line_end']}")
check("CATALOG_SHA sigue la fórmula del ADR: sha256('\\n'.join(name:sha ordenados))",
      cc.CATALOG_SHA == _sha("\n".join(f"{n}:{cc.CARDS[n]['sha']}" for n in sorted(cc.CARDS))))
sum_members = sum(cc.CARDS[m]["chars"] for m in MEMBERS)
mx = max(MEMBERS, key=lambda m: cc.CARDS[m]["chars"])
mn = min(MEMBERS, key=lambda m: cc.CARDS[m]["chars"])
check("tamaño MEDIDO de las 17 fichas: máx squidiff-in-silico-gate, mín histology-reviewer (ADR Context 2)",
      mx == "squidiff-in-silico-gate" and mn == "histology-reviewer",
      f"total={sum_members} chars (~{sum_members // 4} tok a 4 chars/tok) media={sum_members // 17} "
      f"max={cc.CARDS[mx]['chars']} min={cc.CARDS[mn]['chars']}")

# ── 3 · determinismo: dos parseos idénticos; un byte en causal-pruner mueve SÓLO su sha + el global ──
again = cc.parse(cc.CATALOG_PATH_ABS)
check("CATALOG_SHA estable en dos parseos del mismo archivo",
      cc.catalog_sha(again) == cc.CATALOG_SHA and {n: c["sha"] for n, c in again.items()}
      == {n: c["sha"] for n, c in cc.CARDS.items()})
cp = cc.CARDS["causal-pruner"]
pos = RAW.index("Train and query", cp["offset_start"], cp["offset_end"])
MUTATED = RAW[:pos] + "t" + RAW[pos + 1:]          # UN byte: 'T' -> 't' dentro del Purpose de causal-pruner
assert len(MUTATED.encode("utf-8")) == len(RAW_BYTES)
TMP = Path(tempfile.mkdtemp(prefix="smoke_catalog_cards_"))
tmp_md = TMP / "agent-catalog.md"
shutil.copy(cc.CATALOG_PATH_ABS, tmp_md)
tmp_md.write_bytes(MUTATED.encode("utf-8"))
mut_file = cc.parse(tmp_md)
mut_mem = cc.parse(text=MUTATED)
moved_file = sorted(n for n in cc.CARDS if mut_file[n]["sha"] != cc.CARDS[n]["sha"])
moved_mem = sorted(n for n in cc.CARDS if mut_mem[n]["sha"] != cc.CARDS[n]["sha"])
check("copia en tmp con UN byte cambiado en causal-pruner → cambia SÓLO su sha (30 intactas) + CATALOG_SHA",
      moved_file == ["causal-pruner"] and cc.catalog_sha(mut_file) != cc.CATALOG_SHA
      and len(mut_file) == 31, f"moved={moved_file}")
check("la misma edición EN MEMORIA (parse(text=)) da el mismo resultado que el archivo",
      moved_mem == ["causal-pruner"] and cc.catalog_sha(mut_mem) == cc.catalog_sha(mut_file)
      and mut_mem["causal-pruner"]["sha"] == mut_file["causal-pruner"]["sha"])
check("el sha mutado es el sha256 del bloque mutado (no un contador ni un timestamp)",
      mut_mem["causal-pruner"]["sha"] == _sha(mut_mem["causal-pruner"]["text_verbatim"])
      and mut_mem["causal-pruner"]["text_verbatim"] != cp["text_verbatim"])
shutil.rmtree(TMP, ignore_errors=True)

# ── 4 · headers normalizados; category por sección; campos obligatorios / opcionales ────────────────
suffixed = {n: c["header_suffix"] for n, c in cc.CARDS.items() if c["header_suffix"]}
check("3 headers con sufijo normalizados (hypothesis-generator, composite-auditor, retrospector); header_raw conservado",
      set(suffixed) == {"hypothesis-generator", "composite-auditor", "retrospector"}
      and cc.CARDS["hypothesis-generator"]["header_raw"] == "hypothesis-generator (NEW v1.1, PR-01)"
      and cc.CARDS["composite-auditor"]["header_raw"] == "composite-auditor (NEW v2.2)"
      and cc.CARDS["retrospector"]["header_raw"].startswith("retrospector (NEW v1.1, ADR-0009")
      and all("(" not in n for n in cc.CARDS), f"{suffixed}")
cats = {}
for c in cc.CARDS.values():
    cats[c["category"]] = cats.get(c["category"], 0) + 1
check("category ∈ vocabulario cerrado de 6 en las 31; conteos medidos 5/5/4/5/4/8",
      all(c["category"] in cc.CATEGORY_VOCABULARY for c in cc.CARDS.values())
      and cats == {"compute-simulation": 5, "wet-lab-experiment": 5, "data-omics": 4,
                   "knowledge-strategy": 5, "operations-reporting": 4, "substrate-instrumentation": 8},
      f"{cats}")
check("category_raw verbatim del '## Category N:' vigente",
      cc.CARDS["causal-pruner"]["category_raw"] == "Category 1: Compute & Simulation"
      and cc.CARDS["retrospector"]["category_raw"] == "Category 6: Substrate Instrumentation (NEW v2.0)")
check("obligatorios 31/31 no vacíos: purpose, owns, does_not_own, inputs, outputs",
      all(all(c.get(f) for f in cc.REQUIRED_FIELDS) for c in cc.CARDS.values()))
cnt = {f: sum(1 for c in cc.CARDS.values() if f in c) for f in cc.OPTIONAL_FIELDS}
check("opcionales con los conteos MEDIDOS (ADR Context 2): substrate_evidence 10 · framework 2 · method 1 · "
      "upstream 4 · downstream 4 · draft_description 4",
      cnt == {"substrate_evidence": 10, "framework": 2, "method": 1, "upstream": 4, "downstream": 4,
              "draft_description": 4}, f"{cnt}")
check("opcional AUSENTE = llave ausente, jamás '' (tres estados) — p. ej. histology-reviewer sin framework",
      "framework" not in cc.CARDS["histology-reviewer"]
      and all(c.get(f) != "" for c in cc.CARDS.values() for f in cc.OPTIONAL_FIELDS)
      and "framework" in cc.CARDS["hypothesis-generator"]["fields_present"]
      and "framework" in cc.CARDS["histology-reviewer"]["fields_absent"])
check("un campo multilínea se conserva completo (hypothesis-generator.purpose envuelto a 100 cols)",
      "obligatory" in cc.CARDS["hypothesis-generator"]["purpose"]
      and cc.CARDS["hypothesis-generator"]["purpose"].startswith("Generate calibrated"))
check("una etiqueta sin línea en blanco antes de la siguiente termina el campo (Upstream / Downstream)",
      cc.CARDS["sim-orchestrator"]["upstream"] == "`benchmark-designer`, computational lead."
      and cc.CARDS["sim-orchestrator"]["downstream"] == "`causal-pruner`, `sim-result-analyst`.")
check("las etiquetas NO mapeadas quedan visibles en labels_raw, no se inventan campos",
      "Quality gates" in cc.CARDS["squidiff-in-silico-gate"]["labels_raw"]
      and "quality_gates" not in cc.CARDS["squidiff-in-silico-gate"])

# ── 5 · errores de parseo LANZAN (un faltante es error, no default) ─────────────────────────────────
sin_inputs = RAW.replace("**Inputs:** Causal benchmark library", "**Entradas:** Causal benchmark library", 1)
check("obligatorio faltante (Inputs de causal-pruner) → CatalogParseError",
      _raises(lambda: cc.parse(text=sin_inputs), cc.CatalogParseError))
fuera = RAW.replace("## Category 1: Compute & Simulation", "## Compute & Simulation", 1)
check("una ficha fuera de '## Category N:' → CatalogParseError",
      _raises(lambda: cc.parse(text=fuera), cc.CatalogParseError))
dup = RAW.replace("### fitness-curator", "### sim-orchestrator", 1)
check("nombre duplicado → CatalogParseError", _raises(lambda: cc.parse(text=dup), cc.CatalogParseError))
cat7 = RAW.replace("## Category 6:", "## Category 7:", 1)
check("categoría fuera de vocabulario (Category 7) → CatalogParseError",
      _raises(lambda: cc.parse(text=cat7), cc.CatalogParseError))
check("un archivo inexistente lanza en parse() (OSError) — el import lo habría DECLARADO, no rellenado",
      _raises(lambda: cc.parse(ROOT / "no-existe.md"), OSError))

# ── 6 · la matriz y el catálogo se cruzan: 3 filas sin ficha, 0 fichas sin fila ─────────────────────
rows_without_card = sorted(n for n, r in agent_matrix.AGENTS.items() if r["card"] == "no-card-in-catalog")
check("las 3 filas sin ficha (html-report-emitter, identifier-verification-gate, type-c-viz-emitter) ∉ CARDS "
      "y declaradas 'no-card-in-catalog'",
      rows_without_card == ["html-report-emitter", "identifier-verification-gate", "type-c-viz-emitter"]
      and not any(n in cc.CARDS for n in rows_without_card))
check("cada ficha del catálogo tiene fila en la matriz v1.3 (cards_without_row == []) y cada 'present' ∈ CARDS",
      [n for n in cc.CARDS if n not in agent_matrix.AGENTS] == []
      and all(n in cc.CARDS for n, r in agent_matrix.AGENTS.items() if r["card"] == "present"))
summ = cc.cards_summary()
check("cards_summary(): vista sin text_verbatim con sha/category/chars por ficha y el catalog_sha",
      summ["catalog_sha"] == cc.CATALOG_SHA and summ["n_cards"] == 31
      and all("text_verbatim" not in v and v["sha"] == cc.CARDS[n]["sha"] for n, v in summ["cards"].items()))

# ── 7 · COUNCIL_RULES: texto LITERAL de CLAUDE.md §7 ────────────────────────────────────────────────
claude_md = (ROOT / "CLAUDE.md").read_bytes().decode("utf-8").replace("\r\n", "\n")
sec_start = claude_md.index("## 7. Hard rules")
sec_end = claude_md.index("\n## ", sec_start + 5)
SECTION7 = claude_md[sec_start:sec_end]
check("COUNCIL_RULES_ITEMS: 10 reglas, cada una substring LITERAL de la sección §7 de CLAUDE.md (CRLF normalizado)",
      len(cc.COUNCIL_RULES_ITEMS) == 10
      and all(("- " + r + "\n") in SECTION7 for r in cc.COUNCIL_RULES_ITEMS)
      and not any("\r" in r for r in cc.COUNCIL_RULES_ITEMS),
      f"faltan={[r[:40] for r in cc.COUNCIL_RULES_ITEMS if ('- ' + r + chr(10)) not in SECTION7]}")
check("las reglas citadas por el ADR están: causal-pruner (:146), cross-field (:147), Test 5 (:148), "
      "compliance/budget (:149), identificadores (:154), anti-fabricación (:155), self-audit (:157), invocación (:158)",
      cc.COUNCIL_RULES_ITEMS[0].startswith("**`causal-pruner` outputs always require a human gate")
      and cc.COUNCIL_RULES_ITEMS[1].startswith("**`cross-field-bridge-agent` operates Method 2 only")
      and cc.COUNCIL_RULES_ITEMS[2].startswith("**Test 5 is exploratory in Phase I")
      and cc.COUNCIL_RULES_ITEMS[3].startswith("**Compliance and budget decisions never go through automatic")
      and any(r.startswith("**External identifiers are never used from internal memory") for r in cc.COUNCIL_RULES_ITEMS)
      and any(r.startswith("**Anti-fabrication verification gate") for r in cc.COUNCIL_RULES_ITEMS)
      and any(r.startswith("**Self-audit by the same agent") for r in cc.COUNCIL_RULES_ITEMS)
      and any(r.startswith("**Catalog-agent invocation discipline") for r in cc.COUNCIL_RULES_ITEMS))
check("RULES_SHA == sha256(COUNCIL_RULES) y COUNCIL_RULES = header + '- ' por regla",
      cc.RULES_SHA == _sha(cc.COUNCIL_RULES)
      and cc.COUNCIL_RULES == cc.COUNCIL_RULES_HEADER + "\n" + "\n".join("- " + r for r in cc.COUNCIL_RULES_ITEMS))

# ── 8 · COUNCIL_FIXED_BLOCK: doctrina literal, sin campos prohibidos, sin fechas, sin sustitución ────
A = cc.COUNCIL_FIXED_BLOCK
check("el bloque fijo dice la doctrina: NO answer / NO rank / NO audit / NO dispatch · ONLY the tool · PRIOR ART",
      all(p in A for p in ("do NOT answer", "do NOT rank", "do NOT audit", "do NOT dispatch",
                           "Emit ONLY the tool", "PRIOR ART, never evidence", "never assert identifiers as facts")))
prohibited_fields = [t for t in ("direct_answer", "verdict", "confidence", "ranking", "score")
                     if re.search(rf"\b{t}\b", A, re.I)]
check("ningún nombre de campo prohibido en el bloque fijo (direct_answer, verdict, confidence, ranking, score)",
      prohibited_fields == [], f"{prohibited_fields}")
verbs = [(m.group(0), A[max(0, m.start() - 4):m.start()]) for m in re.finditer(r"\b(answer|rank|dispatch)\b", A)]
check("los verbos answer / rank / dispatch aparecen SÓLO negados ('NOT ' inmediatamente antes) — la doctrina, no una orden",
      verbs and all(prev == "NOT " for _, prev in verbs), f"{verbs}")
check("sin fechas ni ids en el bloque fijo (caché: prefijo estable) y sin sustitución por miembro ('<agent>' literal)",
      re.search(r"\b20\d\d\b", A) is None and re.search(r"\b\d{4,}\b", A) is None and "<agent>" in A
      and "<pendiente" not in A)
check("PROHIBITED_OUTPUT_FIELDS exportado para el test estático de los tools (C2 (C.2))",
      set(cc.PROHIBITED_OUTPUT_FIELDS) >= {"direct_answer", "answer", "verdict", "confidence", "ranking",
                                          "rank", "score", "dispatch"})
check("SHARED_BLOCK_TEXT = A + '\\n\\n' + reglas; su tamaño solo ya supera el mínimo cacheable (512 tok ≈ 2048 chars)",
      cc.SHARED_BLOCK_TEXT == A + "\n\n" + cc.COUNCIL_RULES and cc.SHARED_BLOCK_SHA == _sha(cc.SHARED_BLOCK_TEXT)
      and len(cc.SHARED_BLOCK_TEXT) >= 4 * cc.MIN_CACHEABLE_TOKENS,
      f"chars={len(cc.SHARED_BLOCK_TEXT)} (~{len(cc.SHARED_BLOCK_TEXT) // 4} tok a 4 chars/tok; LG1 mide count_tokens)")

# ── 9 · build_system: [A idéntico ×17, ficha VERBATIM] con cache_control; string con CACHE=0 ────────
ENV_ON = {"WITT_COUNCIL_CACHE": "1"}
systems = {m: cc.build_system(m, ENV_ON) for m in MEMBERS}
check("build_system(env cache=1) → lista de 2 bloques {type:'text', text, cache_control} para los 17",
      all(isinstance(s, list) and len(s) == 2 and all(b["type"] == "text" and "cache_control" in b for b in s)
          for s in systems.values()))
check("bloque A IDÉNTICO byte a byte para los 17 (un solo sha: el prefijo compartido que la caché lee 16×)",
      len({_sha(s[0]["text"]) for s in systems.values()}) == 1
      and next(iter(systems.values()))[0]["text"] == cc.SHARED_BLOCK_TEXT)
check("bloque B == text_verbatim de la ficha y sha256(bloque B) == CARDS[agent].sha ×17",
      all(s[1]["text"] == cc.CARDS[m]["text_verbatim"] and _sha(s[1]["text"]) == cc.CARDS[m]["sha"]
          for m, s in systems.items()))
check("build_system acepta la ficha (dict) o el nombre (str) y da los mismos bytes",
      cc.build_system(cc.CARDS["literature-monitor"], ENV_ON) == systems["literature-monitor"])
check("cache_control por defecto (TTL 5m) = {type:'ephemeral'} sin `ttl` explícito, en AMBOS bloques",
      all(b["cache_control"] == {"type": "ephemeral"} for b in systems["causal-pruner"]))
s1h = cc.build_system("causal-pruner", {"WITT_COUNCIL_CACHE": "1", "WITT_COUNCIL_CACHE_TTL": "1h"})
check("TTL 1h: AMBOS bloques ttl '1h' — el A hereda 1h porque una entrada 1h debe ir ANTES que las de 5m "
      "(regla de la API; el ADR decía 'A siempre 5m': DECLARADO como desvío)",
      all(b["cache_control"] == {"type": "ephemeral", "ttl": "1h"} for b in s1h))
ttls = [b["cache_control"].get("ttl", "5m") for b in s1h]
check("orden de TTLs válido: ninguna entrada 5m precede a una 1h",
      not any(ttls[i] == "5m" and "1h" in ttls[i + 1:] for i in range(len(ttls))), f"{ttls}")
soff = cc.build_system("causal-pruner", {"WITT_COUNCIL_CACHE": "0"})
check("CACHE=0 → `system` es el STRING A + '\\n\\n' + ficha (A/B medible en usage.cache_*)",
      isinstance(soff, str) and soff == cc.SHARED_BLOCK_TEXT + "\n\n" + cc.CARDS["causal-pruner"]["text_verbatim"])
cfg_bad = cc.cache_config({"WITT_COUNCIL_CACHE": "quizás", "WITT_COUNCIL_CACHE_TTL": "2d"})
check("env basura → defaults DECLARADOS con fuente (cache on, ttl 5m; 'unparseable' en la fuente)",
      cfg_bad["enabled"] is True and cfg_bad["ttl_card"] == "5m" and cfg_bad["ttl_shared"] == "5m"
      and "unparseable" in cfg_bad["enabled_source"] and "unparseable" in cfg_bad["ttl_source"])
cfg_def = cc.cache_config({})
check("env vacío → cache on (default 1) y ttl 5m con fuente 'default (… unset)'; min_cacheable 512 con fuente",
      cfg_def["enabled"] and cfg_def["ttl_card"] == "5m" and "unset" in cfg_def["enabled_source"]
      and cfg_def["min_cacheable_tokens"] == 512 and "claude-api" in cfg_def["min_cacheable_source"])
check("cache_config acepta 'true/yes/on' y 'false/no/off' (tolerante)",
      cc.cache_config({"WITT_COUNCIL_CACHE": "off"})["enabled"] is False
      and cc.cache_config({"WITT_COUNCIL_CACHE": "yes"})["enabled"] is True)
check("build_system es PURA: dos llamadas → mismos bytes y mismo system_sha; system_sha distingue miembros",
      cc.build_system("causal-pruner", ENV_ON) == systems["causal-pruner"]
      and cc.system_sha(cc.build_system("causal-pruner", ENV_ON)) == cc.system_sha(systems["causal-pruner"])
      and len({cc.system_sha(s) for s in systems.values()}) == 17
      and cc.system_sha(soff) == _sha(soff))
check("system_sha de la lista es el sha del JSON canónico (sort_keys, sin espacios, ensure_ascii False)",
      cc.system_sha(s1h) == _sha(json.dumps(s1h, sort_keys=True, ensure_ascii=False, separators=(",", ":"))))
check("sin ficha → ValueError('no-card-in-catalog: …') — C2 la vuelve fila errored, no un prompt vacío",
      _raises(lambda: cc.build_system("html-report-emitter", ENV_ON), ValueError)
      and _raises(lambda: cc.build_system("nadie", ENV_ON), ValueError))

# ── 10 · NO-SPEND ───────────────────────────────────────────────────────────────────────────────────
check("urlopen bloqueado y contado = 0 (sin red, sin modelo, sin BD)", N_URLOPEN[0] == 0, f"n={N_URLOPEN[0]}")

n_pass = sum(CHECKS)
print(f"\n{n_pass}/{len(CHECKS)} PASS")
sys.exit(0 if n_pass == len(CHECKS) else 1)
