"""
search_queries.py — constructor DETERMINISTA de queries para la Ruta B (ADR-0078, rebanada I4).

Por qué existe: answer_pipeline.build_external_query (ADR-0057) manda los símbolos ANDeados como
texto libre ('osr1 prkci pax2a' → PubMed 0 hits, Europe PMC 1 hit, medido 2026-09-13). Una query mal
construida es indistinguible de "no existe literatura" — la lección LOTE-03. Este módulo produce la
query que SÍ se manda, con sintaxis nativa de cada índice, y devuelve junto a ella TODO lo que decidió
(símbolos usados y descartados, términos anatómicos detectados, modo) para que el ledger lo registre.

Regla estructural (constitución, capa CLI): aquí no hay modelo — solo tablas declaradas y regex. Dos
llamadas con los mismos insumos producen la MISMA cadena byte a byte (gate: smoke_search_queries.py).

Tres índices, tres sintaxis:
  PubMed (E-utilities esearch `term`):
      (sym1[tiab] OR sym2[tiab]) AND (zebrafish[mh] OR zebrafish[tiab] OR "danio rerio"[tiab])
                                 AND (pronephros[tiab] OR pronephric[tiab] OR kidney[mh] OR kidney[tiab] ...)
  Europe PMC (REST /search `query`):
      (TITLE:sym1 OR ABSTRACT:sym1 OR ...) AND (MESH:"Zebrafish" OR zebrafish) AND (pronephros OR ...)
      NUNCA `ORGANISM:` — medido 0 hits (2026-09-13).
  ZFIN / Alliance (`filter.termName` del endpoint /api/gene/{curie}/phenotypes):
      OR de las RAÍCES anatómicas presentes en la pregunta, separadas con '|'.

Bloque anatómico: SOLO con los términos presentes en los textos de la pregunta. UNA política para los
TRES índices (ADR-0078 corrector, 2026-09-14): se detecta anatomía en la pregunta ORIGINAL (ES o EN, con
o sin acentos) Y en la formulación EN (`question_en`, si llega); se toma la UNIÓN en orden de tabla y se
declara de dónde salió cada término: notes.anatomy ∈ 'from-question' | 'from-question-en' | 'from-both' |
'none-in-question' + notes.anatomy_text_source (subconjunto de ['question', 'question_en']). Si ningún
texto menciona anatomía, NO hay bloque anatómico. Nunca se rellena con un default "pronephros" — eso
sería un fallback disfrazado.

Símbolos vacíos: la query se arma solo con la formulación EN (texto libre sin stopwords) + organismo +
anatomía, y se declara (notes.mode = 'question-only'). La pregunta ORIGINAL jamás se tokeniza como texto
libre: mandar español a PubMed es ~0 hits garantizados disfrazados de 'no hay literatura' (LOTE-03).
Sin símbolos NI formulación EN → query None declarada (notes.mode = 'empty', notes.reason lo dice): el
llamador registra 'not-searched', jamás manda una query vacía.

Contrato de salida de cada builder (dict, llaves fijas):
  {query, builder_version, symbols_used, anatomy_terms_used, notes}
  query               str | None (None = ausencia DECLARADA, no hay nada que buscar)
  builder_version     QUERY_BUILDER_VERSION
  symbols_used        list[str] símbolos saneados que SÍ entraron a la query (orden de entrada, sin duplicados)
  anatomy_terms_used  list[str] términos EN (subconjunto ordenado de ANATOMY_TERMS_EN) detectados en la pregunta
  notes               dict: mode, anatomy, symbols_dropped, symbols_sanitized, question_terms, ...

stdlib puro (re, unicodedata). NO importa answer_pipeline: ANATOMY_TERMS_EN se COPIA de
answer_pipeline.ZFIN_ANATOMY_TERMS (tabla ES/EN de raíces para el filtro ZFIN, 2026-08-19) y se documenta
aquí el origen; importar el orquestador desde una biblioteca de queries invertiría la dependencia.
"""
import re
import unicodedata

QUERY_BUILDER_VERSION = "1"

# Términos anatómicos EN del pronefros (vocabulario ZFIN/MeSH). ORIGEN: derivados de
# answer_pipeline.ZFIN_ANATOMY_TERMS (raíces pronephr / glomer / duct / tubul / podocyte / kidney) expandidos
# a sustantivo+adjetivo donde PubMed los indexa distinto (pronephros/pronephric, glomerulus/glomerular) y
# con `nephron`, que la tabla original no cubría. El ORDEN es contrato: anatomy_terms_used lo respeta.
ANATOMY_TERMS_EN = (
    "pronephros", "pronephric",
    "glomerulus", "glomerular",
    "podocyte",
    "nephron",
    "kidney",
    "tubule",
    "duct",
)

# Tabla de detección: (raíz ZFIN para filter.termName, términos EN que activa, regex de agujas ES/EN).
# Las agujas se evalúan sobre la pregunta NORMALIZADA (minúsculas, sin acentos: riñón→rinon, túbulo→tubulo,
# glomérulo→glomerulo, pronéfrico→pronefrico). Se exige borde de palabra al inicio (\b) para que 'reduction'
# no active 'duct' ni 'product' active 'duct' — el sustring crudo de ZFIN_ANATOMY_TERMS sí lo hacía.
ANATOMY_GROUPS = (
    ("pronephr", ("pronephros", "pronephric"), r"\bpronephr\w*|\bpronefr\w*"),
    ("glomer",   ("glomerulus", "glomerular"), r"\bglomer\w*"),
    ("podocyte", ("podocyte",),                r"\bpodoc\w*"),
    ("nephron",  ("nephron",),                 r"\bnephron\w*|\bnefron\w*"),
    ("kidney",   ("kidney",),                  r"\bkidney\w*|\brinon\w*|\brenal\w*"),
    ("tubul",    ("tubule",),                  r"\btubul\w*"),
    ("duct",     ("duct",),                    r"\bduct\w*|\bconductos?\b"),
)

# Campos PubMed por término anatómico. `kidney` es descriptor MeSH (Kidney); el resto va por título/abstract.
# Declarado aquí — no se infiere.
ANATOMY_PUBMED_FIELDS = {
    "pronephros": ("tiab",),
    "pronephric": ("tiab",),
    "glomerulus": ("tiab",),
    "glomerular": ("tiab",),
    "podocyte":   ("tiab",),
    "nephron":    ("tiab",),
    "kidney":     ("mh", "tiab"),
    "tubule":     ("tiab",),
    "duct":       ("tiab",),
}

PUBMED_ORGANISM_BLOCK = '(zebrafish[mh] OR zebrafish[tiab] OR "danio rerio"[tiab])'
EPMC_ORGANISM_BLOCK = '(MESH:"Zebrafish" OR zebrafish)'
ZFIN_FILTER_SEPARATOR = "|"

# Símbolo de gen: letras, dígitos y . _ : - (cubre wt1a, pax2a, si:ch211-250g4.3, LOC100005). Un símbolo es UN
# token: si la entrada trae espacios ('wt1a; DROP TABLE') se conserva solo el primer token — nunca se pegan
# tokens. Todo carácter fuera del conjunto (comillas, paréntesis, corchetes, punto y coma) se ELIMINA. Ambas
# cosas se declaran en notes.symbols_sanitized (original → limpio).
_SYMBOL_ALLOWED = re.compile(r"[^A-Za-z0-9._:-]")
_SYMBOL_NEEDS_QUOTES = re.compile(r"[^A-Za-z0-9]")
_SYMBOL_MIN_LEN = 2

# Stopwords para el modo question-only (texto libre). Incluye el organismo porque ya va en su bloque.
QUESTION_STOPWORDS_EN = frozenset("""
a an and are as at be by can could did do does for from has have how in is it its of on or
required requires that the this to was were what when where which while who why will with
zebrafish danio rerio
""".split())


def _normalize(text):
    """minúsculas + sin diacríticos (NFD, se quitan las marcas combinantes). '' si text es None."""
    if not text:
        return ""
    nfd = unicodedata.normalize("NFD", str(text))
    stripped = "".join(ch for ch in nfd if not unicodedata.combining(ch))
    return stripped.lower()


def detect_anatomy(question):
    """(anatomy_terms_en, zfin_stems) presentes en la pregunta, ambos en orden de tabla y sin duplicados.
    Determinista: regex sobre la pregunta normalizada. ([], []) = la pregunta no menciona anatomía."""
    q = _normalize(question)
    if not q:
        return [], []
    terms, stems = [], []
    for stem, en_terms, pattern in ANATOMY_GROUPS:
        if re.search(pattern, q):
            stems.append(stem)
            for t in en_terms:
                if t not in terms:
                    terms.append(t)
    # Orden contractual = ANATOMY_TERMS_EN (los grupos ya lo siguen; se reordena por si la tabla cambia).
    terms.sort(key=ANATOMY_TERMS_EN.index)
    return terms, stems


def detect_anatomy_both(question, question_en):
    """ADR-0078 corrector — la política ÚNICA de anatomía para los tres índices: unión de lo detectado en
    la pregunta original y en la formulación EN, en orden de tabla, con la procedencia declarada.
    Devuelve (terms, stems, sources) donde sources ⊆ ['question', 'question_en'] nombra los textos que
    aportaron al menos una raíz."""
    t_q, s_q = detect_anatomy(question)
    t_en, s_en = detect_anatomy(question_en)
    terms = [t for t in ANATOMY_TERMS_EN if t in t_q or t in t_en]
    stems = [g[0] for g in ANATOMY_GROUPS if g[0] in s_q or g[0] in s_en]
    sources = ([] if not s_q else ["question"]) + ([] if not s_en else ["question_en"])
    return terms, stems, sources


def _anatomy_literal(sources):
    if sources == ["question"]:
        return "from-question"
    if sources == ["question_en"]:
        return "from-question-en"
    if sources == ["question", "question_en"]:
        return "from-both"
    return "none-in-question"


def sanitize_symbols(symbols):
    """(used, dropped, sanitized): saneo declarado de símbolos.
    used      — símbolos limpios (minúsculas, orden de entrada, sin duplicados)
    dropped   — entradas que quedaron vacías o < 2 caracteres tras el saneo (se reporta el original)
    sanitized — {original: limpio} solo para los que CAMBIARON (auditoría de lo que se mandó vs lo pedido)."""
    used, dropped, sanitized = [], [], {}
    for raw in (symbols or []):
        if raw is None:
            continue
        original = str(raw)
        tokens = original.split()
        first = tokens[0] if tokens else ""
        clean = _SYMBOL_ALLOWED.sub("", first).lower()
        if len(clean) < _SYMBOL_MIN_LEN:
            dropped.append(original)
            continue
        if clean != original:
            sanitized[original] = clean
        if clean not in used:
            used.append(clean)
    return used, dropped, sanitized


def question_terms(question_en):
    """Tokens de texto libre para el modo question-only: palabras (\\w+) de la pregunta normalizada, sin
    stopwords, sin tokens de 1 carácter, sin duplicados, en orden de aparición."""
    out = []
    for tok in re.findall(r"\w+", _normalize(question_en)):
        if len(tok) < 2 or tok in QUESTION_STOPWORDS_EN or tok in out:
            continue
        out.append(tok)
    return out


def _pubmed_symbol(sym):
    return (f'"{sym}"' if _SYMBOL_NEEDS_QUOTES.search(sym) else sym) + "[tiab]"


def _epmc_symbol(sym):
    quoted = f'"{sym}"' if _SYMBOL_NEEDS_QUOTES.search(sym) else sym
    return f"TITLE:{quoted} OR ABSTRACT:{quoted}"


def _result(query, symbols_used, anatomy_terms_used, notes):
    return {
        "query": query,
        "builder_version": QUERY_BUILDER_VERSION,
        "symbols_used": list(symbols_used),
        "anatomy_terms_used": list(anatomy_terms_used),
        "notes": notes,
    }


_EMPTY_REASON = ("no symbols and no English formulation: nothing to search (the original-language "
                 "question is never tokenized as free text — ADR-0078 corrector)")


def _base_notes(index, used, dropped, sanitized, anatomy_sources, qterms):
    if used:
        mode = "symbols"
    elif qterms:
        mode = "question-only"
    else:
        mode = "empty"
    return {
        "index": index,
        "mode": mode,
        "anatomy": _anatomy_literal(anatomy_sources),
        "anatomy_text_source": list(anatomy_sources),
        "symbols_dropped": list(dropped),
        "symbols_sanitized": dict(sanitized),
        "question_terms": list(qterms) if mode == "question-only" else [],
        "question_terms_source": "question_en" if mode == "question-only" else None,
        "organism_block": True,
    }


def build_pubmed_term(symbols, question_en=None, question=None):
    """Término `term` para esearch (db=pubmed). Ver docstring del módulo para la forma exacta.
    Anatomía: unión de `question` (original) y `question_en` (ADR-0078 corrector, una política).
    symbols vacíos → modo question-only (texto libre de question_en sin stopwords; la pregunta original
    NUNCA se tokeniza). Nada que buscar → query None declarada (notes.mode='empty')."""
    used, dropped, sanitized = sanitize_symbols(symbols)
    anatomy_terms, _stems, a_src = detect_anatomy_both(question, question_en)
    qterms = question_terms(question_en) if not used else []
    notes = _base_notes("pubmed", used, dropped, sanitized, a_src, qterms)

    if used:
        head = "(" + " OR ".join(_pubmed_symbol(s) for s in used) + ")"
    elif qterms:
        head = "(" + " ".join(qterms) + ")"
    else:
        notes["organism_block"] = False
        notes["reason"] = _EMPTY_REASON
        return _result(None, [], anatomy_terms, notes)

    blocks = [head, PUBMED_ORGANISM_BLOCK]
    if anatomy_terms:
        clauses = []
        for t in anatomy_terms:
            for field in ANATOMY_PUBMED_FIELDS[t]:
                clauses.append(f"{t}[{field}]")
        blocks.append("(" + " OR ".join(clauses) + ")")
    return _result(" AND ".join(blocks), used, anatomy_terms, notes)


def build_epmc_query(symbols, question_en=None, question=None):
    """`query` para Europe PMC REST /search. Campos TITLE:/ABSTRACT: por símbolo; organismo por
    MESH:"Zebrafish" OR zebrafish (NUNCA ORGANISM:, medido 0 hits). Misma política de modos y de
    anatomía que PubMed."""
    used, dropped, sanitized = sanitize_symbols(symbols)
    anatomy_terms, _stems, a_src = detect_anatomy_both(question, question_en)
    qterms = question_terms(question_en) if not used else []
    notes = _base_notes("europepmc", used, dropped, sanitized, a_src, qterms)
    notes["organism_field"] = "MESH"   # declarado: ORGANISM: descartado por medición

    if used:
        head = "(" + " OR ".join(_epmc_symbol(s) for s in used) + ")"
    elif qterms:
        head = "(" + " ".join(qterms) + ")"
    else:
        notes["organism_block"] = False
        notes["reason"] = _EMPTY_REASON
        return _result(None, [], anatomy_terms, notes)

    blocks = [head, EPMC_ORGANISM_BLOCK]
    if anatomy_terms:
        blocks.append("(" + " OR ".join(anatomy_terms) + ")")
    return _result(" AND ".join(blocks), used, anatomy_terms, notes)


def build_zfin_filter(question, question_en=None):
    """Raíces anatómicas para el tool ZFIN: la misma política de anatomía que PubMed/EPMC (unión de
    `question` y `question_en`, ADR-0078 corrector). `query` es la lista de raíces unida con '|' SOLO
    como representación legible en el ledger — el tool recibe `notes.stems` y hace UNA petición por raíz
    (Alliance responde HTTP 400 a `filter.termName=a|b`, medido 2026-09-14) o filtra en el cliente por
    prefijo de palabra. Sin anatomía → query None: el llamador busca SIN filtro (búsqueda MÁS AMPLIA, no
    fallida) y lo registra. No usa símbolos."""
    anatomy_terms, stems, a_src = detect_anatomy_both(question, question_en)
    notes = {
        "index": "zfin",
        "mode": "anatomy-filter" if stems else "no-filter",
        "anatomy": _anatomy_literal(a_src),
        "anatomy_text_source": list(a_src),
        "separator": ZFIN_FILTER_SEPARATOR,
        "semantics": ("ledger representation only: the tool sends ONE filter.termName GET per stem "
                      "(server) and matches word-prefix \\b<stem> (client backstop)"),
        "stems": list(stems),
    }
    query = ZFIN_FILTER_SEPARATOR.join(stems) if stems else None
    return _result(query, [], anatomy_terms, notes)


def build_all(symbols, question_en=None, question=None):
    """Conveniencia: los tres builders de una vez con UNA política (ADR-0078 corrector): `question`
    (original, ES o EN) y `question_en` (formulación EN del sintetizador/llamador) alimentan AMBOS la
    detección anatómica de los tres índices; solo `question_en` alimenta los términos de texto libre."""
    return {
        "builder_version": QUERY_BUILDER_VERSION,
        "pubmed": build_pubmed_term(symbols, question_en=question_en, question=question),
        "europepmc": build_epmc_query(symbols, question_en=question_en, question=question),
        "zfin": build_zfin_filter(question, question_en=question_en),
    }
