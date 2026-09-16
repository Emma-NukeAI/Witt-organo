"""smoke_gate_citations.py — gate determinista de la rebanada C6 de ADR-0080 (gate y panel).

Cubre (E):
  - predicado DURO verify_output.positive_claim_requires_citations: una AFIRMACION POSITIVA
    (absence_kind 'not-applicable') con 0 citas validas es INADMISIBLE via admissible(extra_predicates);
    una DECLINACION puede no citar; absence_kind AUSENTE no dispara y lo declara; la evaluacion viaja en
    `pred.evaluation` (para congelarla en deterministic_checks sin recalcular).
  - escalera de soporte por cita verify_output.support_state_for: unresolved -> resolved ->
    passage_delivered -> supported | unsupported; `pertinent` = 'not-available (ADR-0082)'; los campos
    NUNCA se funden; un veredicto del juez solo eleva una cita con pasaje entregado; support_summary.
  - composite_auditor.VERDICT_TOOL gana `citation_support` OPCIONAL (no en required); solo la charge de la
    lente evidence-grounding lo pide; parse_citation_support descarta y CUENTA lo fuera de forma;
    citation_support_from_panel entrega la lista del juez de esa lente (None si erro / no emitio).
  - reintento por juez (WITT_JUDGE_RETRIES, default 1) con caller INYECTADO: juez que falla una vez y luego
    responde -> fila con verdict + retries_judge 1 + attempts[2]; juez que falla dos veces -> errored con
    attempts[2]; retries 0 -> un solo intento; usage solo de intentos exitosos; `member.attempt` llega al
    caller; salida ilegible (verdict fuera del vocabulario) cuenta como intento errado; el bloque
    out.judge_retries declara valor + procedencia.
  - ADR-0083 (E)/(F), rebanada F2 — figuras como evidencia OBSERVADA: `_bundle_evidence_index` indexa cada
    `papers[].figures.items[]` como item propio ('<PMCID>#<fig_id>', delivered = caption 'present'; sin caption NO
    se indexa); la escalera de soporte acepta citas kind 'figure' sin peldaños nuevos; `figure_predicates` devuelve el
    fragmento `deterministic_checks.figures` con los CINCO predicados (3 DUROS: figure_id_resolves, figure_sha_matches
    solo en mismatch, figure_only_not_asserted; 2 INFORMATIVOS gating False: figure_numerals_grounded con
    n_marker_absent medido, figure_license_known) + FIGURE_RULES congeladas; sin citas figura -> 'no-figure-citations'
    y ningun predicado entra; kill-switch WITT_FIGURES=0 -> fragmento EXACTAMENTE {state}. Bytes desde los zips
    fixture (figures._get_bytes FALSEADA), sha recalculado al gatear, cache en TMP.

100% offline: cero red (urlopen BLOQUEADO Y CONTADO == 0), cero spend (caller inyectado; ANTHROPIC/OPENAI keys
vacias), cero mutacion de la DATA INAMOVIBLE, del mcp_cache del repo ni del registro congelado. Exit 0 = todo PASS.

Corre (mascara):  WITT_BACKEND_DB_URL=sqlite:///<tmp>.db NEO4J_URI="" RAG_BACKEND=sparse OPENAI_API_KEY="" ANTHROPIC_API_KEY=""
                  WITT_RUN_ORIGIN=smoke [WITT_MCP_CACHE_DIR=<tmp>] python rag_index/query_service/smoke_gate_citations.py
"""
import os
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "analysis" / "scripts"))
os.environ["ANTHROPIC_API_KEY"] = ""
os.environ["OPENAI_API_KEY"] = ""
os.environ.pop("WITT_JUDGE_RETRIES", None)

from lib import composite_auditor as ca  # noqa: E402
from lib import verify_output as vo  # noqa: E402

CHECKS = []


def check(name, cond, detail=""):
    CHECKS.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + name + (("  -> " + detail) if detail else ""))


# ---------------------------------------------------------------------------------------------------
# 1) Predicado DURO: afirmacion positiva sin citas -> inadmisible; declinacion sin citas -> admisible
# ---------------------------------------------------------------------------------------------------
ANSWER_TXT = {"direct_answer": "wt1a is required for podocyte specification in the zebrafish pronephros."}

pred_pos_0 = vo.positive_claim_requires_citations({"absence_kind": "not-applicable"}, 0)
adm, reasons = vo.admissible(ANSWER_TXT, extra_predicates=[pred_pos_0])
check("positive claim + 0 citations -> INADMISSIBLE via admissible(extra_predicates)",
      adm is False and any("positive_claim_requires_citations" in r for r in reasons), str(reasons))
check("evaluation declares reason/rule/decided_by and n_citations_valid 0",
      pred_pos_0.evaluation["ok"] is False and pred_pos_0.evaluation["positive_claim"] is True
      and pred_pos_0.evaluation["n_citations_valid"] == 0 and pred_pos_0.evaluation["decided_by"] == "code"
      and "ADR-0080" in pred_pos_0.evaluation["rule"], str(pred_pos_0.evaluation))

cits_one = [{"n": 1, "kind": "pmid", "id": "PMID:37844491", "note": ""}]
pred_pos_1 = vo.positive_claim_requires_citations({"absence_kind": "not-applicable"}, cits_one)
adm, reasons = vo.admissible(ANSWER_TXT, extra_predicates=[pred_pos_1])
check("positive claim + 1 valid citation (list counted) -> admissible",
      adm is True and pred_pos_1.evaluation["n_citations_valid"] == 1
      and pred_pos_1.evaluation["citations_state"] == "counted", str(reasons))

pred_decl = vo.positive_claim_requires_citations({"absence_kind": "no-evidence-retrieved"}, 0)
adm, reasons = vo.admissible({"direct_answer": "No evidence retrieved; cannot answer."}, extra_predicates=[pred_decl])
check("declination (no-evidence-retrieved) + 0 citations -> admissible",
      adm is True and pred_decl.evaluation["positive_claim"] is False, str(reasons))

pred_empty_ids = vo.positive_claim_requires_citations({"absence_kind": "not-applicable"},
                                                      [{"n": 1, "kind": "other", "id": "", "note": ""}])
adm, _ = vo.admissible(ANSWER_TXT, extra_predicates=[pred_empty_ids])
check("positive claim + citations with EMPTY ids -> 0 valid -> INADMISSIBLE (n_valid rule of ADR-0078)",
      adm is False and pred_empty_ids.evaluation["n_citations_valid"] == 0)

pred_absent = vo.positive_claim_requires_citations({"direct_answer": "x"}, None)
check("absence_kind ABSENT -> treated as POSITIVE claim (conservative default, ADR-0080 corrector): ok False with 0 citations, "
      "absence_kind_state 'absent -> treated-as-positive…', citations 'absent' (0 declared), resolved_identifiers_state "
      "'checked' (direct_answer measured, none resolved)",
      pred_absent.evaluation["ok"] is False and pred_absent.evaluation["positive_claim"] is True
      and pred_absent.evaluation["absence_kind_state"].startswith("absent -> treated-as-positive")
      and pred_absent.evaluation["citations_state"] == "absent" and "conservative" in pred_absent.evaluation["reason"]
      and pred_absent.evaluation["resolved_identifiers"] == [] and pred_absent.evaluation["resolved_identifiers_state"] == "checked")
pred_absent_cited = vo.positive_claim_requires_citations({"direct_answer": "x"}, 1)
check("absence_kind ABSENT + 1 valid citation -> admissible (the conservative default only demands evidence)",
      pred_absent_cited.evaluation["ok"] is True and pred_absent_cited.evaluation["positive_claim"] is True)
_rep_ids = {"verified_raw": ["ENSDARG00000031420"], "verified_derived": [], "unresolved": []}
pred_decl_ids = vo.positive_claim_requires_citations({"absence_kind": "no-evidence-retrieved",
                                                      "direct_answer": "wt1a (ENSDARG00000031420) marks the pronephros."},
                                                     0, identifier_report=_rep_ids)
pred_decl_ids_cited = vo.positive_claim_requires_citations({"absence_kind": "no-evidence-retrieved"}, 1, identifier_report=_rep_ids)
pred_decl_norep = vo.positive_claim_requires_citations({"absence_kind": "no-evidence-retrieved"}, 0)
check("declination that names RESOLVED identifiers (identifier_report from the same gate) with 0 citations -> INADMISSIBLE "
      "(reason 'declination with resolved identifiers […] and 0 citations'); same with 1 citation -> admissible; without a "
      "report and without direct_answer -> 'not-provided' and the plain declination rule applies",
      pred_decl_ids.evaluation["ok"] is False and pred_decl_ids.evaluation["positive_claim"] is False
      and pred_decl_ids.evaluation["resolved_identifiers"] == ["ENSDARG00000031420"]
      and pred_decl_ids.evaluation["reason"].startswith("declination with resolved identifiers")
      and pred_decl_ids_cited.evaluation["ok"] is True
      and pred_decl_norep.evaluation["ok"] is True and pred_decl_norep.evaluation["resolved_identifiers_state"] == "not-provided"
      and "ADR-0080" in pred_decl_ids.evaluation["rule"])
pred_decl_norep_ans = vo.positive_claim_requires_citations({"absence_kind": "no-evidence-retrieved",
                                                            "direct_answer": "No evidence retrieved; cannot answer."}, 0)
check("declination with direct_answer but no report -> the predicate measures verify_identifiers itself: no ids -> admissible, "
      "resolved_identifiers [] 'checked'",
      pred_decl_norep_ans.evaluation["ok"] is True and pred_decl_norep_ans.evaluation["resolved_identifiers"] == []
      and pred_decl_norep_ans.evaluation["resolved_identifiers_state"] == "checked")

check("count_valid_citations: int given / None absent / raw ids counted",
      vo.count_valid_citations(3) == (3, "given") and vo.count_valid_citations(None) == (0, "absent")
      and vo.count_valid_citations(["PMID:1", "", None]) == (1, "counted"))

# ---------------------------------------------------------------------------------------------------
# 2) Escalera de soporte por cita (support_state_for) sobre un bundle sintetico con las tres fuentes
# ---------------------------------------------------------------------------------------------------
BUNDLE = {
    "path_a": {"hits": [{"doc_id": "CORPUS:schoels2021:chunk-12", "text": "wt1a expression in the glomerulus..."},
                        {"doc_id": "CORPUS:empty-hit", "text": ""}]},
    "path_b": {"papers": [
        {"source": "europepmc", "evidence_id": "PMID:37844491",
         "search_rec": {"pmid": "37844491", "pmcid": "PMC10000001", "doi": "10.1242/dev.02071"},
         "abstract": "The Wilms tumor suppressor wt1a ...", "text_excerpt": None},
        {"source": "pubmed", "evidence_id": "PMID:11111111",
         "search_rec": {"pmid": "11111111", "pmcid": None, "doi": None},
         "abstract": None, "text_excerpt": None},                       # resolvio pero SIN pasaje
        {"source": "zfin", "evidence_id": "ZFIN:ZDB-GENE-980526-558",
         "search_rec": {"pmid": None, "pmcid": None, "doi": None},
         "zfin": {"phenotypes": [{"statement": "pronephros glomerulus malformed", "references": ["PMID:1"]}]}},
        {"source": "zfin", "evidence_id": "ZFIN:unresolved:foo",
         "search_rec": {"pmid": None}, "zfin": {"phenotypes": []}},   # zfin sin statements
    ]},
}
CITS = [
    {"n": 1, "kind": "pmid", "id": "PMID:37844491", "note": ""},          # paper con abstract
    {"n": 2, "kind": "pmid", "id": "11111111", "note": ""},               # numerico sin prefijo -> resuelve, sin pasaje
    {"n": 3, "kind": "other", "id": "PMID:99999999", "note": ""},         # no esta en el bundle
    {"n": 4, "kind": "zfin", "id": "ZFIN:ZDB-GENE-980526-558", "note": ""},  # zfin con statement
    {"n": 5, "kind": "corpus", "id": "CORPUS:schoels2021:chunk-12", "note": ""},  # path_a con texto
    {"n": 6, "kind": "corpus", "id": "CORPUS:empty-hit", "note": ""},     # path_a sin texto
    {"n": 7, "kind": "doi", "id": "https://doi.org/10.1242/dev.02071", "note": ""},  # DOI -> mismo paper
    {"n": 8, "kind": "zfin", "id": "ZFIN:unresolved:foo", "note": ""},    # zfin sin statements
]

rows = vo.support_state_for(CITS, BUNDLE)
by_n = {r["n"]: r for r in rows}
check("ladder without grounding: paper w/ abstract -> passage_delivered, supported 'not-evaluated'",
      by_n[1]["resolved"] and by_n[1]["passage_delivered"] and by_n[1]["support_state"] == "passage_delivered"
      and by_n[1]["supported"] == "not-evaluated", str(by_n[1]))
check("ladder: numeric pmid without prefix resolves; no abstract/excerpt -> 'resolved' (passage_delivered False)",
      by_n[2]["resolved"] and by_n[2]["passage_delivered"] is False and by_n[2]["support_state"] == "resolved"
      and by_n[2]["resolved_to"] == "PMID:11111111", str(by_n[2]))
check("ladder: citation absent from bundle -> 'unresolved', resolved_to None",
      by_n[3]["resolved"] is False and by_n[3]["support_state"] == "unresolved" and by_n[3]["resolved_to"] is None)
check("ladder: zfin with >=1 statement -> passage_delivered; zfin with 0 statements -> resolved",
      by_n[4]["support_state"] == "passage_delivered" and by_n[8]["support_state"] == "resolved", f"{by_n[4]['support_state']} / {by_n[8]['support_state']}")
check("ladder: path_a hit with text -> passage_delivered; empty-text hit -> resolved",
      by_n[5]["support_state"] == "passage_delivered" and by_n[6]["support_state"] == "resolved")
check("ladder: https://doi.org/<doi> resolves to the paper's evidence_id (deterministic key variants)",
      by_n[7]["resolved"] and by_n[7]["resolved_to"] == "PMID:37844491")
check("pertinent is the declared literal 'not-available (ADR-0082)' on every row (never fused)",
      all(r["pertinent"] == vo.PERTINENT_NOT_AVAILABLE for r in rows) and all("ladder_rule" in r for r in rows))

# --- ADR-0082 (G.4): `pertinent` deja de ser gris cuando el consejo juzgó — mapa {evidence_id: [requirement_id]} de votos VÁLIDOS ---
PERT = {"PMID:37844491": ["req-a"], "CORPUS:schoels2021:chunk-12": ["req-b", "req-c"]}
rows_p = vo.support_state_for(CITS, BUNDLE, council_pertinence=PERT, council_source="council.r2 (covered|partial votes)")
p = {r["n"]: r for r in rows_p}
check("ADR-0082 (G.4) con council_pertinence: la cita [1] PMID:37844491 -> pertinent True + pertinent_to ['req-a'] + pertinent_source; "
      "la [7] (DOI que RESUELVE al mismo paper) -> True por resolved_to; la [5] (chunk citado por dos requisitos) -> ['req-b', 'req-c'] "
      "ordenados; la escalera (support_state) NO cambia",
      p[1]["pertinent"] is True and p[1]["pertinent_to"] == ["req-a"] and p[1]["pertinent_source"] == "council.r2 (covered|partial votes)"
      and p[7]["pertinent"] is True and p[7]["pertinent_to"] == ["req-a"]
      and p[5]["pertinent"] is True and p[5]["pertinent_to"] == ["req-b", "req-c"]
      and [r["support_state"] for r in rows_p] == [r["support_state"] for r in rows], str({n: (p[n]["pertinent"], p[n].get("pertinent_to")) for n in (1, 5, 7)}))
check("ADR-0082 (G.4) una cita resuelta que NINGÚN voto nombró ([2]) y una no resuelta ([3]) -> 'not-named-by-council (valid round; no "
      "vote cites this id)' — JAMÁS false (un miembro sólo juzga SUS requisitos: ausencia ≠ negación), pertinent_to []",
      p[2]["pertinent"] == vo.PERTINENT_NOT_NAMED and p[2]["pertinent_to"] == []
      and p[3]["pertinent"] == vo.PERTINENT_NOT_NAMED and p[3]["pertinent_to"] == []
      and all(r["pertinent"] is not False for r in rows_p), str(p[2]["pertinent"]))
rows_pm = vo.support_state_for(CITS[:2], BUNDLE, council_pertinence={"37844491": ["req-z"]})
rows_ns = vo.support_state_for(CITS[:1], BUNDLE, council_state="incomplete")
check("ADR-0082 (G.4) variantes deterministas de llave: un mapa con el PMID SIN prefijo ('37844491') casa con la cita 'PMID:37844491' "
      "(y con la que resuelve a ella); sin mapa pero con council_state -> 'not-available (council incomplete)' (la razón viaja; sin "
      "council_state el literal viejo 'not-available (ADR-0082)' sigue); pertinent_source sólo cuando hubo mapa",
      rows_pm[0]["pertinent"] is True and rows_pm[0]["pertinent_to"] == ["req-z"] and rows_pm[1]["pertinent"] == vo.PERTINENT_NOT_NAMED
      and rows_ns[0]["pertinent"] == "not-available (council incomplete)" and "pertinent_source" not in rows_ns[0]
      and rows[0]["pertinent"] == vo.PERTINENT_NOT_AVAILABLE, str((rows_pm[0]["pertinent"], rows_ns[0]["pertinent"])))
summ_p = vo.support_summary(rows_p)
summ_ns = vo.support_summary(rows_ns)
check("ADR-0082 (G.4) support_summary.pertinent pasa de literal a {state, n_true, n_not_named, n_not_available, literal, rule}: con mapa "
      "state 'checked' n_true 3 n_not_named 5; sin ronda válida state = el literal not-available de las filas; el literal viejo "
      "sigue DENTRO (`literal` == PERTINENT_NOT_AVAILABLE) en ambos",
      summ_p["pertinent"]["state"] == "checked" and summ_p["pertinent"]["n_true"] == 3 and summ_p["pertinent"]["n_not_named"] == 5
      and summ_p["pertinent"]["n_not_available"] == 0 and summ_p["pertinent"]["literal"] == vo.PERTINENT_NOT_AVAILABLE
      and summ_ns["pertinent"]["state"] == "not-available (council incomplete)" and summ_ns["pertinent"]["n_not_available"] == 1
      and summ_ns["pertinent"]["literal"] == vo.PERTINENT_NOT_AVAILABLE and summ_p["pertinent"]["rule"] == vo.PERTINENT_RULE,
      str(summ_p["pertinent"]))

grounding = [{"n": 1, "verdict": "supported"}, {"n": 4, "verdict": "unsupported"},
             {"n": 5, "verdict": "not-assessable"}, {"n": 3, "verdict": "supported"},   # 3 es unresolved
             {"n": 2, "verdict": "supported"},                                            # 2 sin pasaje
             {"n": 6, "verdict": "bogus"}, {"n": "x", "verdict": "supported"}]           # fuera de forma
rows_g = vo.support_state_for(CITS, BUNDLE, grounding=grounding)
g = {r["n"]: r for r in rows_g}
check("ladder with grounding: supported -> 'supported'; unsupported -> 'unsupported'; not-assessable stays passage_delivered",
      g[1]["support_state"] == "supported" and g[4]["support_state"] == "unsupported"
      and g[5]["support_state"] == "passage_delivered" and g[5]["supported"] == "not-assessable",
      f"{g[1]['support_state']} / {g[4]['support_state']} / {g[5]['support_state']}")
check("ladder does NOT skip rungs: judge 'supported' on an unresolved citation keeps state 'unresolved' (word kept in `supported`)",
      g[3]["support_state"] == "unresolved" and g[3]["supported"] == "supported")
check("ladder does NOT skip rungs: judge 'supported' on a resolved-without-passage citation keeps 'resolved'",
      g[2]["support_state"] == "resolved" and g[2]["supported"] == "supported")
check("off-vocabulary / non-integer grounding entries are dropped -> 'not-evaluated' (never corrected in silence)",
      g[6]["supported"] == "not-evaluated" and vo._grounding_by_n(grounding)[1] == 2)
check("grounding accepted as dict {n: verdict} too",
      vo.support_state_for(CITS[:1], BUNDLE, grounding={1: "unsupported"})[0]["support_state"] == "unsupported")

summ = vo.support_summary(rows_g)
check("support_summary: n == len(citations), by_state carries ALL rungs and sums to n",
      summ["n"] == 8 and set(summ["by_state"]) == set(vo.SUPPORT_LADDER) and sum(summ["by_state"].values()) == 8
      and summ["by_state"] == {"unresolved": 1, "resolved": 3, "passage_delivered": 2, "supported": 1, "unsupported": 1},
      str(summ["by_state"]))
check("support_summary on no citations: n 0 and every rung 0 (measured zero, not absent)",
      vo.support_summary([])["n"] == 0 and all(v == 0 for v in vo.support_summary([])["by_state"].values()))

# ---------------------------------------------------------------------------------------------------
# 3) Panel: VERDICT_TOOL.citation_support OPCIONAL; solo la charge de evidence-grounding lo pide
# ---------------------------------------------------------------------------------------------------
props = ca.VERDICT_TOOL["input_schema"]["properties"]
check("VERDICT_TOOL has citation_support (array of {n, verdict}) and it is NOT required",
      "citation_support" in props and props["citation_support"]["type"] == "array"
      and set(props["citation_support"]["items"]["properties"]["verdict"]["enum"]) == set(vo.SUPPORT_VERDICTS)
      and "citation_support" not in ca.VERDICT_TOOL["input_schema"]["required"]
      and ca.VERDICT_TOOL["input_schema"]["required"] == ["verdict", "confidence"])
check("only the evidence-grounding charge asks for citation_support (other lenses ignore it)",
      "citation_support" in ca._LENS_CHARGES["evidence-grounding"]
      and not any("citation_support" in ca._LENS_CHARGES[k] for k in ca._LENS_CHARGES if k != "evidence-grounding"))
check("vocabularies agree across modules (composite_auditor duplicates verify_output's literal)",
      tuple(ca.CITATION_SUPPORT_VERDICTS) == tuple(vo.SUPPORT_VERDICTS))

parsed, dropped = ca.parse_citation_support(
    [{"n": 1, "verdict": "supported"}, {"n": 2, "verdict": "maybe"}, {"n": 0, "verdict": "supported"},
     {"n": 1, "verdict": "unsupported"}, "junk", {"n": 3.0, "verdict": "not-assessable"}, {"n": True, "verdict": "supported"}])
check("parse_citation_support: keeps valid {n>=1, verdict in vocab}, first per n wins, drops+counts the rest",
      parsed == [{"n": 1, "verdict": "supported"}, {"n": 3, "verdict": "not-assessable"}] and dropped == 5,
      f"{parsed} dropped={dropped}")
check("parse_citation_support on non-list -> ([], 0) (caller decides 'not emitted')",
      ca.parse_citation_support(None) == ([], 0) and ca.parse_citation_support("x") == ([], 0))

# ---------------------------------------------------------------------------------------------------
# 4) Reintento por juez (WITT_JUDGE_RETRIES) con caller inyectado — declarado, jamas fabricado
# ---------------------------------------------------------------------------------------------------
PANEL = [
    {"reviewer": "j-correctness", "family": "anthropic", "lens": "correctness"},
    {"reviewer": "j-overclaim", "family": "anthropic", "lens": "overclaim"},
    {"reviewer": "j-grounding", "family": "anthropic", "lens": "evidence-grounding"},
    {"reviewer": "j-repro", "family": "openai", "lens": "reproducibility"},
]
CLAIM = {"direct_answer": "wt1a is required [1][2].", "stated_confidence": 0.7}


def make_caller(fail_plan, grounding_out=None, illegible=()):
    """fail_plan: {reviewer: n_fallos_antes_de_responder}. illegible: reviewers que responden con un
    verdict fuera del vocabulario (ilegible) en el primer intento."""
    calls, seen_attempts = {}, {}

    def caller(member, system, user_text):
        r = member["reviewer"]
        calls[r] = calls.get(r, 0) + 1
        seen_attempts.setdefault(r, []).append(member.get("attempt"))
        if calls[r] <= fail_plan.get(r, 0):
            raise RuntimeError(f"simulated network failure #{calls[r]}")
        if r in illegible and calls[r] == 1:
            return {"verdict": "MAYBE", "confidence": 0.5}, {"input_tokens": 5, "output_tokens": 1}
        out = {"verdict": "APPROVE", "confidence": 0.9, "reasons": ["ok"]}
        if member["lens"] == "evidence-grounding" and grounding_out is not None:
            out["citation_support"] = grounding_out
        return out, {"input_tokens": 100, "output_tokens": 10}

    caller.calls, caller.seen_attempts = calls, seen_attempts
    return caller


# 4a) default retries (env unset -> 1): j-correctness falla 1 vez y responde; j-overclaim falla 2 veces
c1 = make_caller({"j-correctness": 1, "j-overclaim": 2},
                 grounding_out=[{"n": 1, "verdict": "supported"}, {"n": 2, "verdict": "bogus"}, {"n": 2, "verdict": "unsupported"}])
res = ca.audit(CLAIM, {"path_b": []}, deterministic_checks={"admissible": True}, panel=PANEL, caller=c1)
rows_by = {r["reviewer"]: r for r in res["panel"]}
check("judge that fails once then answers -> row WITH verdict, retries_judge 1, attempts [errored, ok]",
      rows_by["j-correctness"].get("verdict") == "APPROVE" and rows_by["j-correctness"]["retries_judge"] == 1
      and [a["status"] for a in rows_by["j-correctness"]["attempts"]] == ["errored", "ok"]
      and "error" in rows_by["j-correctness"]["attempts"][0], str(rows_by["j-correctness"].get("attempts")))
check("judge that fails twice (retries 1) -> status errored, retries_judge 1, attempts 2, last error kept, no verdict",
      rows_by["j-overclaim"].get("status") == "errored" and "verdict" not in rows_by["j-overclaim"]
      and rows_by["j-overclaim"]["retries_judge"] == 1 and len(rows_by["j-overclaim"]["attempts"]) == 2
      and "#2" in rows_by["j-overclaim"]["error"], str(rows_by["j-overclaim"]))
check("judge that answers first time -> retries_judge 0, attempts [ok]",
      rows_by["j-repro"]["retries_judge"] == 0 and [a["status"] for a in rows_by["j-repro"]["attempts"]] == ["ok"])
check("out.judge_retries declares value 1 + source default-unset:WITT_JUDGE_RETRIES",
      res["judge_retries"] == {"value": 1, "source": "default-unset:WITT_JUDGE_RETRIES",
                               "scope": "judge-call (additional attempts before exclusion)"}, str(res["judge_retries"]))
check("member.attempt reaches the injected caller (1 then 2 for the retried judge)",
      c1.seen_attempts["j-correctness"] == [1, 2] and c1.seen_attempts["j-overclaim"] == [1, 2]
      and c1.seen_attempts["j-repro"] == [1], str(c1.seen_attempts))
check("usage_total counts ONLY successful attempts (3 valid judges x 100 in / 10 out)",
      res["usage"] == {"input_tokens": 300, "output_tokens": 30}, str(res["usage"]))
check("citation_support parsed onto the evidence-grounding row; dropped counted; absent on other rows",
      rows_by["j-grounding"].get("citation_support") == [{"n": 1, "verdict": "supported"}, {"n": 2, "verdict": "unsupported"}]
      and rows_by["j-grounding"]["citation_support_dropped"] == 1
      and "citation_support" not in rows_by["j-repro"] and "citation_support" not in rows_by["j-correctness"])
check("citation_support_from_panel returns the grounding judge's list",
      ca.citation_support_from_panel(res["panel"]) == [{"n": 1, "verdict": "supported"}, {"n": 2, "verdict": "unsupported"}])
check("n_valid 3 of 4 -> verdict still computed (min_valid 3), tally counts only valid rows",
      res["n_valid"] == 3 and res["verdict"] == "APPROVE" and not res.get("panel_incomplete"))

# 4b) escalera end-to-end: support_state_for consume lo que el panel emitio
e2e = vo.support_state_for(CITS[:2], BUNDLE, grounding=ca.citation_support_from_panel(res["panel"]))
check("end-to-end: panel citation_support -> support_state ('supported' for [1]; [2] has no passage -> stays 'resolved')",
      e2e[0]["support_state"] == "supported" and e2e[1]["support_state"] == "resolved" and e2e[1]["supported"] == "unsupported")

# 4c) retries=0 via caller: a single failure -> errored with ONE attempt; grounding judge errored -> None
c2 = make_caller({"j-correctness": 1, "j-grounding": 1})
res0 = ca.audit(CLAIM, {}, panel=PANEL, caller=c2, judge_retries=0)
r0 = {r["reviewer"]: r for r in res0["panel"]}
check("judge_retries=0 (caller): one failure -> errored, retries_judge 0, attempts 1; source 'caller'",
      r0["j-correctness"].get("status") == "errored" and r0["j-correctness"]["retries_judge"] == 0
      and len(r0["j-correctness"]["attempts"]) == 1 and res0["judge_retries"]["source"] == "caller"
      and res0["judge_retries"]["value"] == 0)
check("grounding judge errored -> citation_support_from_panel None (declared 'not-evaluated' downstream, never filled)",
      ca.citation_support_from_panel(res0["panel"]) is None
      and all(r["supported"] == "not-evaluated" for r in vo.support_state_for(CITS[:2], BUNDLE, grounding=None)))
check("thin panel (2 valid < min_valid 3) can never approve -> REVISE + panel_incomplete",
      res0["n_valid"] == 2 and res0["verdict"] == "REVISE" and res0.get("panel_incomplete") is True)

# 4d) salida ILEGIBLE (verdict fuera del vocabulario) cuenta como intento errado y se reintenta
c3 = make_caller({}, illegible=("j-repro",))
res3 = ca.audit(CLAIM, {}, panel=PANEL, caller=c3)
r3 = {r["reviewer"]: r for r in res3["panel"]}
check("illegible judge output (verdict off-vocabulary) -> attempt errored 'unparseable', retried, then valid",
      r3["j-repro"].get("verdict") == "APPROVE" and r3["j-repro"]["retries_judge"] == 1
      and "unparseable" in r3["j-repro"]["attempts"][0]["error"], str(r3["j-repro"]["attempts"]))
check("MEASURED usage of the illegible attempt IS kept: attempts[0].usage declared, row.usage sums attempts, usage_total 405/41",
      r3["j-repro"]["attempts"][0].get("usage") == {"input_tokens": 5, "output_tokens": 1}
      and r3["j-repro"]["usage"] == {"input_tokens": 105, "output_tokens": 11}
      and res3["usage"] == {"input_tokens": 405, "output_tokens": 41}, str(res3["usage"]))
check("errored attempts carry no usage (the caller raised: nothing was measured) -> usage_total from successful attempts only",
      "usage" not in rows_by["j-overclaim"] and all("usage" not in a for a in rows_by["j-overclaim"]["attempts"])
      and res["usage"] == {"input_tokens": 300, "output_tokens": 30})

# 4e) env parsing: garbage / empty / negative -> default declared; valid int -> env
check("resolve_judge_retries: unset/empty/garbage/negative -> 1 declared; '2' -> (2, env:)",
      ca.resolve_judge_retries({}) == (1, "default-unset:WITT_JUDGE_RETRIES")
      and ca.resolve_judge_retries({"WITT_JUDGE_RETRIES": ""}) == (1, "default-unset:WITT_JUDGE_RETRIES")
      and ca.resolve_judge_retries({"WITT_JUDGE_RETRIES": "abc"}) == (1, "default-invalid-env:WITT_JUDGE_RETRIES")
      and ca.resolve_judge_retries({"WITT_JUDGE_RETRIES": "-3"}) == (1, "default-invalid-env:WITT_JUDGE_RETRIES")
      and ca.resolve_judge_retries({"WITT_JUDGE_RETRIES": "2"}) == (2, "env:WITT_JUDGE_RETRIES"))
os.environ["WITT_JUDGE_RETRIES"] = "2"
c4 = make_caller({"j-correctness": 2})
res4 = ca.audit(CLAIM, {}, panel=PANEL, caller=c4)
os.environ.pop("WITT_JUDGE_RETRIES", None)
r4 = {r["reviewer"]: r for r in res4["panel"]}
check("WITT_JUDGE_RETRIES=2 read at audit() time: judge failing twice then answering -> verdict, retries_judge 2",
      r4["j-correctness"].get("verdict") == "APPROVE" and r4["j-correctness"]["retries_judge"] == 2
      and res4["judge_retries"] == {"value": 2, "source": "env:WITT_JUDGE_RETRIES",
                                    "scope": "judge-call (additional attempts before exclusion)"})

# ---------------------------------------------------------------------------------------------------
# 5) Regresion: la base de verify_output no cambio (fabricacion wt1a sigue cayendo; ok sigue pasando)
# ---------------------------------------------------------------------------------------------------
adm_bad, _ = vo.admissible("wt1a is ENSDARG00000054611", extra_predicates=[pred_decl])
adm_good, _ = vo.admissible("wt1a is ENSDARG00000031420", extra_predicates=[pred_pos_1])
check("regression: fabricated ENSDARG still inadmissible even with a passing extra predicate; verified id + cited positive claim admissible",
      adm_bad is False and adm_good is True)

# ---------------------------------------------------------------------------------------------------
# 6) ADR-0083 (E)/(F) — figuras como evidencia OBSERVADA: índice, escalera y los CINCO predicados (rebanada F2)
#    Bytes desde los zips fixture (figures._get_bytes FALSEADA con la MISMA firma), caché en TMP, urlopen bloqueado
#    y CONTADO, sha256 RECALCULADO al gatear (ADR-0077). Ningún píxel se lee: sólo bundle, caché y TEXTO.
# ---------------------------------------------------------------------------------------------------
import copy  # noqa: E402
import json  # noqa: E402
import tempfile  # noqa: E402
import urllib.request as _urlreq  # noqa: E402

_NET_CALLS = []


def _urlopen_blocked(*a, **kw):
    req = a[0] if a else kw.get("url")
    _NET_CALLS.append(getattr(req, "full_url", None) or str(req))
    raise AssertionError("red bloqueada en el smoke (ADR-0083 M.5)")


_urlreq.urlopen = _urlopen_blocked
from lib import figures as F  # noqa: E402
F._urlopen = _urlopen_blocked          # la costura de figures también
sys.path.insert(0, str(HERE))
import precedent  # noqa: E402  (sólo lectura: validate_disjoint acepta kind figure con `n` entero)

for _k in list(os.environ):            # sin env de figuras heredada: la config viaja INYECTADA (cfg=CFG)
    if _k.startswith("WITT_FIGURES"):
        os.environ.pop(_k, None)
TMP = Path(tempfile.mkdtemp(prefix="smoke_gate_fig_"))
_cache_env = (os.environ.get("WITT_MCP_CACHE_DIR") or "").strip()
_cache_parent = (Path(_cache_env) if _cache_env else TMP / "mcp_cache") / "figures"
_cache_parent.mkdir(parents=True, exist_ok=True)
# raíz de caché FRESCA por corrida (mkdtemp dentro de WITT_MCP_CACHE_DIR o TMP): una corrida anterior dejaría un ledger
# TTL-fresco y F1 serviría cache_hit con 0 descargas — el smoke debe medir la descarga falsa, no el residuo de otra corrida
CR = Path(tempfile.mkdtemp(prefix="gate_citations_", dir=str(_cache_parent)))
FX = HERE / "fixtures" / "figures"
XML_BY, XML_NC = FX / "epmc_fulltext_PMC11379296_20260613.xml", FX / "epmc_fulltext_PMC11647118_20260613.xml"
ZIP_BY = (FX / "PMC11379296-figures.zip").read_bytes()
ZIP_NC = (FX / "PMC11647118-figures-SYNTHETIC.zip").read_bytes()
MANIFEST = json.loads((FX / "MANIFEST.json").read_text(encoding="utf-8"))
REPO_FIG_CACHE = ROOT / "mcp_cache" / "figures"
_repo_fig_cache_before = REPO_FIG_CACHE.exists()
GET_CALLS = []


def _fake_get(url, timeout, max_bytes, dest=None):
    """MISMA firma que figures._get_bytes (F1): escribe el zip fixture en `dest`; cero red."""
    zb = ZIP_BY if "PMC11379296" in url else ZIP_NC
    GET_CALLS.append(url)
    Path(dest).write_bytes(zb)
    return {"status": "ok", "http_status": 200, "content_length": len(zb), "content_type": "application/zip",
            "bytes": len(zb), "elapsed_s": 0.01, "url": url, "path": str(dest)}


F._get_bytes = _fake_get
CFG = F.env_config({})                 # defaults declarados (WITT_FIGURES=1, E2/E3 por default), sin heredar env


def _paper(pmcid, xml_path, rank):
    return {"source": "europepmc", "evidence_id": pmcid, "search_rec": {"pmid": None, "pmcid": pmcid, "doi": None},
            "selection_rank": rank, "text_excerpt": None,
            "fetched": {"found": True, "full_text": True, "raw_cached": [str(xml_path)]}}


FIG_BUNDLE = {
    "path_a": {"hits": [{"doc_id": "CORPUS:schoels2021:chunk-12", "text": "wt1a expression in the glomerulus..."}]},
    "path_b": {"papers": [
        {"source": "europepmc", "evidence_id": "PMID:37844491", "search_rec": {"pmid": "37844491", "pmcid": None, "doi": None},
         "abstract": "The Wilms tumor suppressor wt1a is required in 42 % of embryos (n = 12).", "text_excerpt": None,
         "fetched": {"found": True, "full_text": False, "raw_cached": []}},
        _paper("PMC11379296", XML_BY, 1),      # CC BY real: 9 figuras, 9 jpg en el zip
        _paper("PMC11647118", XML_NC, 2),      # CC BY-NC sintético: undfig1 SIN caption; con max_per_run 12 sólo caben 3
    ]},
}
S = F.attach(FIG_BUNDLE, cfg=CFG, cache_root=CR)
IT = {it["id"]: it for it in S["items"]}
G1, G9 = "PMC11379296#pone.0307390.g001", "PMC11379296#pone.0307390.g009"
UND, NC3 = "PMC11647118#undfig1", "PMC11647118#fig3"
check("ADR-0083 precondición (F1 en el árbol): attach con zips fixture → 'attached', 15 figuras (9 BY + 6 NC), 11 verified "
      "(9 + 2: max_per_run 12), 9 embebibles, undfig1 caption 'absent' + 'not-fetched (no-caption)', fig3 'not-fetched (run-cap)', "
      "sha de g001 == MANIFEST, 2 GET falsas (un zip por paper), 0 urlopen",
      S["state"] == "attached" and S["n_figures"] == 15 and S["n_verified"] == 11 and S["n_embeddable"] == 9
      and IT[UND]["caption_state"] == "absent" and IT[UND]["bytes_state"] == "not-fetched (no-caption)"
      and IT[NC3]["bytes_state"] == "not-fetched (run-cap)" and IT[G1]["bytes_state"] == "verified"
      and IT[G1]["sha256"] == MANIFEST["zips"]["PMC11379296"]["entries"][0]["sha256"] and len(GET_CALLS) == 2 and not _NET_CALLS,
      json.dumps({k: S[k] for k in ("state", "n_figures", "n_verified", "n_embeddable", "n_not_fetched")}))

# 6a) índice de evidencia: la figura es ítem PROPIO; sin caption NO se indexa
idx = vo._bundle_evidence_index(FIG_BUNDLE)
check("(E) _bundle_evidence_index indexa '<PMCID>#<fig_id>' (y su MAYÚSCULA) como ítem propio con delivered True (caption present); "
      "fig3 not-fetched (run-cap) SÍ se indexa (su caption se entregó); undfig1 (caption 'absent') NO se indexa; las llaves de "
      "papers/path_a siguen (PMID:37844491, CORPUS:…)",
      idx.get(G1) == (G1, True) and idx.get(G1.upper()) == (G1, True) and idx.get(NC3) == (NC3, True)
      and UND not in idx and UND.upper() not in idx and "PMID:37844491" in idx and "CORPUS:schoels2021:chunk-12" in idx,
      str({k: idx.get(k) for k in (G1, NC3, UND)}))
FCITS = [{"n": 1, "kind": "figure", "id": G1, "note": ""}, {"n": 2, "kind": "figure", "id": UND, "note": ""},
         {"n": 3, "kind": "pmid", "id": "PMID:37844491", "note": ""}]
frows = vo.support_state_for(FCITS, FIG_BUNDLE)
fr = {r["n"]: r for r in frows}
frows_g = vo.support_state_for(FCITS, FIG_BUNDLE, grounding={1: "supported", 2: "supported"})
check("(E) escalera SIN peldaños nuevos: cita figure g001 → resolved, resolved_to == el id de la figura, passage_delivered (caption), "
      "support_state 'passage_delivered', supported 'not-evaluated'; con grounding 'supported' → 'supported'; undfig1 → 'unresolved' "
      "(y el juez no la eleva); la cita paper conserva EXACTAMENTE la forma de hoy (mismas llaves que una fila de la sección 2)",
      fr[1]["resolved"] is True and fr[1]["resolved_to"] == G1 and fr[1]["passage_delivered"] is True
      and fr[1]["support_state"] == "passage_delivered" and fr[1]["supported"] == "not-evaluated"
      and frows_g[0]["support_state"] == "supported" and fr[2]["support_state"] == "unresolved" and frows_g[1]["support_state"] == "unresolved"
      and fr[3]["support_state"] == "passage_delivered" and set(fr[3]) == set(rows[0]) and set(fr[1]) == set(rows[0]),
      str({n: (fr[n]["support_state"], fr[n]["resolved_to"]) for n in (1, 2, 3)}))
check("(E) _figure_items cae a bundle.figures_ledger.items cuando los papers no traen `figures` (F4 puede pop('papers')): g001 indexada",
      vo._bundle_evidence_index({"path_b": {"papers": [{"evidence_id": "x"}]}, "figures_ledger": {"items": S["items"]}}).get(G1) == (G1, True))

# 6b) figure_predicates — todo verde
ANS_POS = {"direct_answer": "wt1a is required for podocyte specification [1][2].", "absence_kind": "not-applicable"}
C_OK = [{"n": 1, "kind": "figure", "id": G1, "note": ""}, {"n": 2, "kind": "pmid", "id": "PMID:37844491", "note": ""}]


def _adm(text_or_ans, cits, preds):
    ans = text_or_ans if isinstance(text_or_ans, dict) else {"direct_answer": text_or_ans}
    return vo.admissible({"direct_answer": ans.get("direct_answer"), "evidence_cited": cits, "absence_kind": ans.get("absence_kind")},
                         extra_predicates=preds or None)


frag, preds = vo.figure_predicates(C_OK, FIG_BUNDLE, CR, ANS_POS, cfg=CFG)
adm, reasons = _adm(ANS_POS, C_OK, preds)
check("(F) figure_predicates todo verde: state 'checked', n_figure_citations 1, los 5 bloques con ok/gating/reason/rule, los 3 DUROS "
      "(y SOLO ellos) como extra_predicates con .evaluation y __name__, id_resolves ok n_checked 1, sha_matches ok n_checked 1 "
      "(sha RECALCULADO en caché), only_not_asserted ok (1 paper al lado), license_known ok, admissible True sin reasons",
      frag["state"] == "checked" and frag["n_figure_citations"] == 1 and frag["n_figures_in_bundle"] == 15 and frag["n_figures_delivered"] == 14
      and all(set(("ok", "gating", "reason", "rule")) <= set(frag[p]) for p in vo.FIGURE_PREDICATES)
      and [p.__name__ for p in preds] == ["figure_id_resolves", "figure_sha_matches", "figure_only_not_asserted"]
      and all(isinstance(p.evaluation, dict) for p in preds)
      and frag["figure_id_resolves"]["ok"] is True and frag["figure_id_resolves"]["n_checked"] == 1
      and frag["figure_sha_matches"]["ok"] is True and frag["figure_sha_matches"]["n_checked"] == 1 and frag["figure_sha_matches"]["mismatches"] == []
      and frag["figure_sha_matches"]["cache_dir_state"] == "provided"
      and frag["figure_only_not_asserted"]["ok"] is True and frag["figure_only_not_asserted"]["n_non_figure_citations"] == 1
      and frag["figure_license_known"]["ok"] is True and frag["figure_license_known"]["n_checked"] == 1
      and adm is True and reasons == [], str(reasons) + " " + json.dumps({p: frag[p]["ok"] for p in vo.FIGURE_PREDICATES}))
check("(F) FIGURE_RULES congeladas (5 literales, uno por predicado, cada uno cita ADR-0083), gating declarado (3 DUROS / 2 informativos), "
      "decided_by 'code', predicates_version; el gating del bloque == FIGURE_GATING; vocabulario de state cerrado",
      set(frag["rules"]) == set(vo.FIGURE_PREDICATES) == set(vo.FIGURE_GATING) and all("ADR-0083" in r for r in frag["rules"].values())
      and frag["gating"] == {"figure_id_resolves": True, "figure_sha_matches": True, "figure_only_not_asserted": True,
                             "figure_numerals_grounded": False, "figure_license_known": False}
      and all(frag[p]["gating"] == vo.FIGURE_GATING[p] for p in vo.FIGURE_PREDICATES)
      and frag["decided_by"] == "code" and frag["predicates_version"] == vo.FIGURE_PREDICATES_VERSION
      and all(vo.figure_check_state_in_vocabulary(s) for s in ("checked", "no-figure-citations", "kill-switch WITT_FIGURES=0",
                                                              "tool-unavailable (x)", "error: y"))
      and not vo.figure_check_state_in_vocabulary("bogus"))

# 6c) figure_id_resolves (DURO)
C_BAD = [{"n": 1, "kind": "figure", "id": "PMC11379296#pone.0307390.g042", "note": ""}, C_OK[1]]
frag_b, preds_b = vo.figure_predicates(C_BAD, FIG_BUNDLE, CR, ANS_POS, cfg=CFG)
adm_b, reasons_b = _adm(ANS_POS, C_BAD, preds_b)
check("(F.1) id de figura INVENTADO → figure_id_resolves ok False, unresolved_ids [id], detail 'not-in-bundle', admissible False con "
      "'hard predicate failed: figure_id_resolves' (misma disciplina que un ENSDARG no resuelto)",
      frag_b["figure_id_resolves"]["ok"] is False and frag_b["figure_id_resolves"]["unresolved_ids"] == ["PMC11379296#pone.0307390.g042"]
      and frag_b["figure_id_resolves"]["unresolved_detail"][0]["reason"] == "not-in-bundle"
      and adm_b is False and "hard predicate failed: figure_id_resolves" in reasons_b, str(reasons_b))
C_UND = [{"n": 1, "kind": "figure", "id": UND, "note": ""}, C_OK[1]]
frag_u, preds_u = vo.figure_predicates(C_UND, FIG_BUNDLE, CR, ANS_POS, cfg=CFG)
check("(F.1) citar undfig1 (caption 'absent': jamás entregada al sintetizador) → NO resuelve, detail 'caption-absent (never delivered)', "
      "inadmisible",
      frag_u["figure_id_resolves"]["ok"] is False and frag_u["figure_id_resolves"]["unresolved_detail"][0]["reason"].startswith("caption-absent")
      and _adm(ANS_POS, C_UND, preds_u)[0] is False)
C_MISLABEL = [{"n": 1, "kind": "paper", "id": "PMC11379296#pone.0307390.g042", "note": ""}, {"n": 2, "kind": "paper", "id": G1, "note": ""}]
frag_m, _ = vo.figure_predicates(C_MISLABEL, FIG_BUNDLE, CR, ANS_POS, cfg=CFG)
check("(F.1) superset conservador: una cita kind 'paper' con id con FORMA de figura cuenta como cita figura (la etiqueta del modelo no "
      "rescata) → g042 no resuelve (ok False); g001 con kind 'paper' resuelve; n_figure_citations 2, kind_figure 0",
      frag_m["n_figure_citations"] == 2 and frag_m["figure_only_not_asserted"]["n_figure_citations_kind_figure"] == 0
      and frag_m["figure_id_resolves"]["ok"] is False and frag_m["figure_id_resolves"]["unresolved_ids"] == ["PMC11379296#pone.0307390.g042"])

# 6d) figure_sha_matches (DURO sólo en MISMATCH; ausencia ≠ alteración)
g1_path = CR / IT[G1]["cache_path_rel"]
orig = g1_path.read_bytes()
g1_path.write_bytes(orig[:-1] + bytes([orig[-1] ^ 0x01]))     # UN byte alterado en la caché
frag_s, preds_s = vo.figure_predicates(C_OK, FIG_BUNDLE, CR, ANS_POS, cfg=CFG)
adm_s, reasons_s = _adm(ANS_POS, C_OK, preds_s)
g1_path.write_bytes(orig)                                        # restaurado
frag_r, _ = vo.figure_predicates(C_OK, FIG_BUNDLE, CR, ANS_POS, cfg=CFG)
check("(F.2) 1 byte alterado en la caché → sha RECALCULADO ≠ bundle: ok False, mismatches [{id, expected == sha del bundle, actual ≠}], "
      "admissible False 'hard predicate failed: figure_sha_matches'; bytes restaurados → ok True de nuevo (el gate lee, no recuerda)",
      frag_s["figure_sha_matches"]["ok"] is False and len(frag_s["figure_sha_matches"]["mismatches"]) == 1
      and frag_s["figure_sha_matches"]["mismatches"][0]["id"] == G1
      and frag_s["figure_sha_matches"]["mismatches"][0]["expected"] == IT[G1]["sha256"]
      and frag_s["figure_sha_matches"]["mismatches"][0]["actual"] not in (None, IT[G1]["sha256"])
      and adm_s is False and "hard predicate failed: figure_sha_matches" in reasons_s
      and frag_r["figure_sha_matches"]["ok"] is True and frag_r["figure_sha_matches"]["n_checked"] == 1, str(reasons_s))
C_NF = [{"n": 1, "kind": "figure", "id": NC3, "note": ""}, C_OK[1]]
frag_nf, preds_nf = vo.figure_predicates(C_NF, FIG_BUNDLE, CR, ANS_POS, cfg=CFG)
frag_nc, preds_nc = vo.figure_predicates(C_OK, FIG_BUNDLE, None, ANS_POS, cfg=CFG)
frag_mi, preds_mi = vo.figure_predicates(C_OK, FIG_BUNDLE, TMP / "empty_cache", ANS_POS, cfg=CFG)
check("(F.2) ausencia ≠ alteración: figura 'not-fetched (run-cap)' citada → n_not_verifiable 1 con razón 'bytes-state: …', ok null, "
      "NO falla; cache_dir None → 'no-cache-dir' + cache_dir_state 'not-provided'; archivo ausente de la caché → 'file-missing'; "
      "los tres admisibles (la cita sostiene sólo su caption)",
      frag_nf["figure_sha_matches"]["ok"] is None and frag_nf["figure_sha_matches"]["n_not_verifiable"] == 1
      and frag_nf["figure_sha_matches"]["not_verifiable"][0]["reason"] == "bytes-state: not-fetched (run-cap)"
      and frag_nc["figure_sha_matches"]["not_verifiable"][0]["reason"] == "no-cache-dir" and frag_nc["figure_sha_matches"]["cache_dir_state"] == "not-provided"
      and frag_mi["figure_sha_matches"]["not_verifiable"][0]["reason"] == "file-missing" and frag_mi["figure_sha_matches"]["ok"] is None
      and _adm(ANS_POS, C_NF, preds_nf)[0] is True and _adm(ANS_POS, C_OK, preds_nc)[0] is True and _adm(ANS_POS, C_OK, preds_mi)[0] is True,
      json.dumps([frag_nf["figure_sha_matches"]["not_verifiable"], frag_nc["figure_sha_matches"]["not_verifiable"], frag_mi["figure_sha_matches"]["not_verifiable"]]))
C_DUP = [{"n": 1, "kind": "figure", "id": G1, "note": ""}, {"n": 2, "kind": "figure", "id": G1.lower(), "note": ""}, C_OK[1]]
frag_d, _ = vo.figure_predicates(C_DUP, FIG_BUNDLE, CR, ANS_POS, cfg=CFG)
check("(F.2) dos citas a la MISMA figura (una en minúsculas) → ambas resuelven, el sha se recalcula UNA vez (n_checked 1), n_figure_citations 2",
      frag_d["figure_id_resolves"]["ok"] is True and frag_d["n_figure_citations"] == 2 and frag_d["figure_sha_matches"]["n_checked"] == 1)

# 6e) figure_only_not_asserted (DURO, por kinds — §7 «figure-only NOT asserted»)
C_FIGS = [{"n": 1, "kind": "figure", "id": G1, "note": ""}, {"n": 2, "kind": "figure", "id": G9, "note": ""}]
frag_fo, preds_fo = vo.figure_predicates(C_FIGS, FIG_BUNDLE, CR, ANS_POS, cfg=CFG)
adm_fo, reasons_fo = _adm(ANS_POS, C_FIGS, preds_fo)
C_MIX = C_FIGS + [C_OK[1]]
frag_mx, preds_mx = vo.figure_predicates(C_MIX, FIG_BUNDLE, CR, ANS_POS, cfg=CFG)
ANS_DECL = {"direct_answer": "No evidence retrieved; the figures only show morphology [1][2].", "absence_kind": "no-evidence-retrieved"}
frag_de, preds_de = vo.figure_predicates(C_FIGS, FIG_BUNDLE, CR, ANS_DECL, cfg=CFG)
check("(F.3) afirmación POSITIVA sostenida SOLO por citas figure → ok False, admissible False 'hard predicate failed: figure_only_not_asserted' "
      "(n_figure 2, n_non_figure 0); 1 paper + 2 figure → ok; declinación (absence_kind declarado) sólo con figuras → ok, positive_claim False",
      frag_fo["figure_only_not_asserted"]["ok"] is False and frag_fo["figure_only_not_asserted"]["n_figure_citations"] == 2
      and frag_fo["figure_only_not_asserted"]["n_non_figure_citations"] == 0 and adm_fo is False
      and "hard predicate failed: figure_only_not_asserted" in reasons_fo
      and frag_mx["figure_only_not_asserted"]["ok"] is True and _adm(ANS_POS, C_MIX, preds_mx)[0] is True
      and frag_de["figure_only_not_asserted"]["ok"] is True and frag_de["figure_only_not_asserted"]["positive_claim"] is False
      and _adm(ANS_DECL, C_FIGS, preds_de)[0] is True, str(reasons_fo))
frag_ab, preds_ab = vo.figure_predicates(C_FIGS, FIG_BUNDLE, CR, "wt1a is required [1][2].", cfg=CFG)      # str: sin absence_kind
frag_om, _ = vo.figure_predicates(C_FIGS, FIG_BUNDLE, CR, {"direct_answer": "wt1a is required [1][2]."}, cfg=CFG)  # dict SIN el campo
frag_kw, _ = vo.figure_predicates(C_FIGS, FIG_BUNDLE, CR, "no evidence [1][2].", absence_kind="no-evidence-retrieved", cfg=CFG)
check("(F.3) tres estados de absence_kind, ninguno disfrazado: (a) answer_text str SIN kwarg → el llamador no lo pasó → POSITIVA conservadora "
      "con absence_kind_state 'not-provided by caller (…)' e inadmisible sólo-figuras; (b) dict del sintetizador SIN el campo → 'absent -> "
      "treated-as-positive (…)' (omisión del modelo) e inadmisible; (c) kwarg explícito 'no-evidence-retrieved' → 'declared', declinación → ok",
      frag_ab["figure_only_not_asserted"]["ok"] is False and frag_ab["figure_only_not_asserted"]["absence_kind_state"] == vo.ABSENCE_KIND_NOT_PROVIDED_STATE
      and frag_ab["figure_only_not_asserted"]["absence_kind_state"].startswith("not-provided by caller")
      and _adm("wt1a is required [1][2].", C_FIGS, preds_ab)[0] is False
      and frag_om["figure_only_not_asserted"]["ok"] is False and frag_om["figure_only_not_asserted"]["absence_kind_state"].startswith("absent -> treated-as-positive")
      and frag_kw["figure_only_not_asserted"]["ok"] is True and frag_kw["figure_only_not_asserted"]["absence_kind_state"] == "declared",
      str((frag_ab["figure_only_not_asserted"]["absence_kind_state"], frag_om["figure_only_not_asserted"]["absence_kind_state"])))

# 6e-bis) corrector (F.3): una cita de TEXTO que NO resuelve (id inventado) o RESUELVE sin pasaje entregado NO rescata la afirmación figure-only
C_HALLU = C_FIGS + [{"n": 3, "kind": "paper", "id": "PMID:99999999", "note": ""}]
frag_hl, preds_hl = vo.figure_predicates(C_HALLU, FIG_BUNDLE, CR, ANS_POS, cfg=CFG)
adm_hl, reasons_hl = _adm(ANS_POS, C_HALLU, preds_hl)
_fo_hl, _fo_mx = frag_hl["figure_only_not_asserted"], frag_mx["figure_only_not_asserted"]
check("(F.3, corrector) afirmación POSITIVA con 2 citas figure + 1 cita paper ALUCINADA (PMID:99999999 no resuelve al bundle) → figure-only: ok False, "
      "INADMISIBLE 'hard predicate failed: figure_only_not_asserted', reason nombra el id no resuelto; n_non_figure_citations 1, _resolved 0, "
      "_delivered 0, _unresolved 1; la mezcla REAL (paper que resuelve CON pasaje) sigue ok con _delivered 1 y figure_citations_same_paper medido "
      "[{id, same_paper_text_citation}] ×2 (D.2, informativo)",
      _fo_hl["ok"] is False and adm_hl is False and "hard predicate failed: figure_only_not_asserted" in reasons_hl
      and "do NOT resolve to a delivered passage" in _fo_hl["reason"]
      and (_fo_hl["n_non_figure_citations"], _fo_hl["n_non_figure_citations_resolved"], _fo_hl["n_non_figure_citations_delivered"],
           _fo_hl["n_non_figure_citations_unresolved"]) == (1, 0, 0, 1)
      and _fo_mx["ok"] is True and _fo_mx["n_non_figure_citations_delivered"] == 1 and _fo_mx["n_non_figure_citations_unresolved"] == 0
      and isinstance(_fo_mx["figure_citations_same_paper"], list) and len(_fo_mx["figure_citations_same_paper"]) == 2
      and all(set(x) == {"id", "same_paper_text_citation"} and isinstance(x["same_paper_text_citation"], bool) for x in _fo_mx["figure_citations_same_paper"])
      and isinstance(_fo_mx["n_figure_citations_without_same_paper_text"], int),
      json.dumps({k: _fo_hl.get(k) for k in ("ok", "reason", "n_non_figure_citations_unresolved")}))
B_ND = copy.deepcopy(FIG_BUNDLE)
B_ND["path_b"]["papers"].append({"source": "europepmc", "evidence_id": "PMID:55555555", "search_rec": {"pmid": "55555555", "pmcid": None},
                                 "fetched": {"found": True, "full_text": False, "raw_cached": []}})
C_ND = C_FIGS + [{"n": 3, "kind": "paper", "id": "PMID:55555555", "note": ""}]
frag_nd, preds_nd = vo.figure_predicates(C_ND, B_ND, CR, ANS_POS, cfg=CFG)
_fo_nd = frag_nd["figure_only_not_asserted"]
check("(F.3, corrector) cita paper que RESUELVE al bundle pero SIN pasaje entregado (sin abstract/text_excerpt) → tampoco rescata: ok False, "
      "_resolved 1, _delivered 0, _unresolved 0; inadmisible (el texto que porta la evidencia tiene que haberse ENTREGADO)",
      _fo_nd["ok"] is False and (_fo_nd["n_non_figure_citations_resolved"], _fo_nd["n_non_figure_citations_delivered"],
                                _fo_nd["n_non_figure_citations_unresolved"]) == (1, 0, 0)
      and _adm(ANS_POS, C_ND, preds_nd)[0] is False, json.dumps(_fo_nd["reason"]))
check("(F.3, corrector) FIGURE_RULES[F.3] declara el límite NUEVO ('hallucinated or unresolved text id beside the figure does NOT rescue') y el "
      "medido D.2 (same_paper_text_citation); el literal viaja congelado en el fragmento (rules)",
      "does NOT rescue the claim" in vo.FIGURE_RULES[vo.PREDICATE_FIGURE_ONLY_NOT_ASSERTED]
      and "same_paper_text_citation" in vo.FIGURE_RULES[vo.PREDICATE_FIGURE_ONLY_NOT_ASSERTED]
      and frag_hl["rules"][vo.PREDICATE_FIGURE_ONLY_NOT_ASSERTED] == vo.FIGURE_RULES[vo.PREDICATE_FIGURE_ONLY_NOT_ASSERTED])

# 6f) figure_numerals_grounded (INFORMATIVO, gating False): se mide, jamás gatea
C_G1 = [{"n": 1, "kind": "figure", "id": G1, "note": ""}]
frag_n1, preds_n1 = vo.figure_predicates(C_G1, FIG_BUNDLE, CR, {"direct_answer": "Podocyte number fell by 42 % [1].", "absence_kind": "not-applicable"}, cfg=CFG)
ev1 = frag_n1["figure_numerals_grounded"]["evaluations"]
check("(F.4) '42 % [1]' sin respaldo en el caption de g001 → ok False, evaluations[{n 1, id, state 'marker-sentence', numerals ['42%'], "
      "numerals_unsupported ['42%'], supporting_sources []}], state 'checked', n_marker_absent 0; admissible() sigue True y NINGÚN predicado "
      "'figure_numerals_grounded' entra a la conjunción (gating False)",
      frag_n1["figure_numerals_grounded"]["ok"] is False and frag_n1["figure_numerals_grounded"]["state"] == "checked"
      and frag_n1["figure_numerals_grounded"]["n_marker_absent"] == 0 and len(ev1) == 1 and ev1[0]["n"] == 1 and ev1[0]["id"] == G1
      and ev1[0]["state"] == "marker-sentence" and ev1[0]["numerals"] == ["42%"] and ev1[0]["numerals_unsupported"] == ["42%"]
      and ev1[0]["supporting_sources"] == [] and "figure_numerals_grounded" not in [p.__name__ for p in preds_n1]
      and _adm({"direct_answer": "Podocyte number fell by 42 % [1].", "absence_kind": "not-applicable"}, C_G1, preds_n1)[0] is False
      and _adm({"direct_answer": "Podocyte number fell by 42 % [1].", "absence_kind": "not-applicable"}, C_G1, preds_n1)[1] == ["hard predicate failed: figure_only_not_asserted"],
      json.dumps(ev1))
C_G9 = [{"n": 1, "kind": "figure", "id": G9, "note": ""}, C_OK[1]]
frag_n2, _ = vo.figure_predicates(C_G9, FIG_BUNDLE, CR, {"direct_answer": "Significance at 95% with p < 0.05 [1].", "absence_kind": "not-applicable"}, cfg=CFG)
ev2 = frag_n2["figure_numerals_grounded"]["evaluations"]
check("(F.4) numerales que CONSTAN en el caption de la figura citada (g009: '95%', '0.05') → ok True, supporting_sources ['caption:<id>'], "
      "numerals ['95%', '0.05']",
      frag_n2["figure_numerals_grounded"]["ok"] is True and ev2[0]["numerals"] == ["95%", "0.05"] and ev2[0]["numerals_unsupported"] == []
      and ev2[0]["supporting_sources"] == [f"caption:{G9}"], json.dumps(ev2))
frag_n3, _ = vo.figure_predicates(C_OK, FIG_BUNDLE, CR, {"direct_answer": "Podocyte number fell by 42 % [1][2].", "absence_kind": "not-applicable"}, cfg=CFG)
ev3 = frag_n3["figure_numerals_grounded"]["evaluations"]
frag_n3b, _ = vo.figure_predicates(C_OK, FIG_BUNDLE, CR, {"direct_answer": "Podocyte number fell by 42 %. [1][2]", "absence_kind": "not-applicable"}, cfg=CFG)
check("(F.4) '[1][2]' en la misma oración: el pasaje ENTREGADO de la cita paper [2] (abstract con '42 %') respalda el numeral → ok True, "
      "supporting_sources ['passage:PMID:37844491']; un fragmento SOLO de marcadores tras el punto ('…42 %. [1][2]') se funde con la oración "
      "anterior (sigue 'marker-sentence', mismo respaldo)",
      frag_n3["figure_numerals_grounded"]["ok"] is True and ev3[0]["supporting_sources"] == ["passage:PMID:37844491"] and ev3[0]["numerals"] == ["42%"]
      and frag_n3b["figure_numerals_grounded"]["evaluations"][0]["state"] == "marker-sentence"
      and frag_n3b["figure_numerals_grounded"]["evaluations"][0]["supporting_sources"] == ["passage:PMID:37844491"], json.dumps(ev3))
frag_n4, _ = vo.figure_predicates(C_OK, FIG_BUNDLE, CR, {"direct_answer": "Podocyte number fell by 42 % in mutants.", "absence_kind": "not-applicable"}, cfg=CFG)
ev4 = frag_n4["figure_numerals_grounded"]["evaluations"]
frag_n5, _ = vo.figure_predicates(C_OK, FIG_BUNDLE, CR, {"direct_answer": "Podocyte number fell by 17 % in mutants.", "absence_kind": "not-applicable"}, cfg=CFG)
check("(F.4) SIN marcadores → state 'no-markers: whole-answer fallback', n_marker_absent 1 (límite MEDIDO, jamás ok silencioso), la evaluación "
      "'no-marker: whole-answer fallback' compara los numerales de TODA la respuesta con la unión caption + pasajes no-figure ('42%' respaldado "
      "por el abstract → ok True; '17%' sin respaldo → ok False, numerals_unsupported ['17%'])",
      frag_n4["figure_numerals_grounded"]["state"] == "no-markers: whole-answer fallback" and frag_n4["figure_numerals_grounded"]["n_marker_absent"] == 1
      and ev4[0]["state"] == "no-marker: whole-answer fallback" and ev4[0]["numerals"] == ["42%"] and frag_n4["figure_numerals_grounded"]["ok"] is True
      and "passage:PMID:37844491" in ev4[0]["supporting_sources"]
      and frag_n5["figure_numerals_grounded"]["ok"] is False and frag_n5["figure_numerals_grounded"]["evaluations"][0]["numerals_unsupported"] == ["17%"],
      json.dumps(ev4))
frag_n6, _ = vo.figure_predicates(C_G1, FIG_BUNDLE, CR, {"direct_answer": "The ratio was 0,5 with n = 12 at 24 hpf [1].", "absence_kind": "not-applicable"}, cfg=CFG)
ev6 = frag_n6["figure_numerals_grounded"]["evaluations"]
check("(F.4) '0,5' y 'n = 12' se CUENTAN como numerales (regex del ADR); '12' y '24' constan en el caption de g001, '0,5' no → "
      "numerals ['0,5', '12', '24'], numerals_unsupported ['0,5'] (separador NO normalizado: límite declarado en la regla); el marcador [1] "
      "NO se cuenta como cifra",
      ev6[0]["numerals"] == ["0,5", "12", "24"] and ev6[0]["numerals_unsupported"] == ["0,5"] and ev6[0]["supporting_sources"] == [f"caption:{G1}"],
      json.dumps(ev6))
check("(F.4) _numeral_in: '12' NO casa incrustado en '2012' ni en '12.5'; '42%' casa en '42 %'; '0.05' casa en 'p < 0.05'",
      vo._numeral_in("12", "in 2012 we") is False and vo._numeral_in("12", "x 12.5 y") is False and vo._numeral_in("12", "n = 12.") is True
      and vo._numeral_in("42%", "fell by 42 % overall") is True and vo._numeral_in("0.05", "p < 0.05)") is True)

# 6g) figure_license_known (INFORMATIVO)
B_UNK = copy.deepcopy(FIG_BUNDLE)
for _p in B_UNK["path_b"]["papers"]:
    for _it in ((_p.get("figures") or {}).get("items") or []):
        if _it["id"] == G1:
            _it["license"] = dict(_it["license"], id="unknown", source="none", rule_no=7)
frag_lk, preds_lk = vo.figure_predicates(C_OK, B_UNK, CR, ANS_POS, cfg=CFG)
check("(F.5) figura citada con license 'unknown' → figure_license_known ok False, unknown [id]; admissible() sigue True (gating False: la "
      "licencia gatea EMBEBER, no la verdad de la cita)",
      frag_lk["figure_license_known"]["ok"] is False and frag_lk["figure_license_known"]["unknown"] == [G1]
      and _adm(ANS_POS, C_OK, preds_lk) == (True, []), str(frag_lk["figure_license_known"]))

# 6h) sin citas figura → 'no-figure-citations' y NINGÚN predicado entra (admisibilidad de hoy)
C_TXT = [{"n": 1, "kind": "pmid", "id": "PMID:37844491", "note": ""}, {"n": 2, "kind": "corpus", "id": "CORPUS:schoels2021:chunk-12", "note": ""}]
frag_0, preds_0 = vo.figure_predicates(C_TXT, FIG_BUNDLE, CR, ANS_POS, cfg=CFG)
check("(F) sin citas figura (el bundle SÍ trae 15 figuras) → state 'no-figure-citations', extra_predicates [], los 5 bloques presentes con "
      "ceros MEDIDOS (id_resolves n_checked 0 ok True; sha ok null; only ok True; numerals state 'no-figure-citations' ok null; license ok null); "
      "admissible == la conjunción de hoy",
      frag_0["state"] == "no-figure-citations" and preds_0 == [] and frag_0["n_figure_citations"] == 0 and frag_0["n_figures_in_bundle"] == 15
      and frag_0["figure_id_resolves"] == dict(frag_0["figure_id_resolves"], ok=True, n_checked=0)
      and frag_0["figure_sha_matches"]["ok"] is None and frag_0["figure_only_not_asserted"]["ok"] is True
      and frag_0["figure_numerals_grounded"]["state"] == "no-figure-citations" and frag_0["figure_numerals_grounded"]["ok"] is None
      and frag_0["figure_license_known"]["ok"] is None
      and _adm(ANS_POS, C_TXT, preds_0) == vo.admissible({"direct_answer": ANS_POS["direct_answer"], "evidence_cited": C_TXT, "absence_kind": "not-applicable"}))

# 6i) kill-switch WITT_FIGURES=0 → fragmento EXACTAMENTE {state} y sin gating (M.1: una de las 3 excepciones declaradas)
frag_ks, preds_ks = vo.figure_predicates(C_OK, FIG_BUNDLE, CR, ANS_POS, cfg=F.env_config({"WITT_FIGURES": "0"}))
frag_kl, preds_kl = vo.figure_predicates(C_OK, {"figures_ledger": {"state": "kill-switch WITT_FIGURES=0"}}, CR, ANS_POS, cfg=CFG)
os.environ["WITT_FIGURES"] = "0"
frag_ke, preds_ke = vo.figure_predicates(C_OK, FIG_BUNDLE, CR, ANS_POS)          # cfg leído del env EN LA LLAMADA (M.4)
os.environ.pop("WITT_FIGURES", None)
check("(M.1) kill-switch: cfg WITT_FIGURES=0 | bundle.figures_ledger.state kill-switch | env WITT_FIGURES=0 leída en la llamada → fragmento "
      "EXACTAMENTE {'state': 'kill-switch WITT_FIGURES=0'} (ninguna otra llave: la excepción declarada del frozen 1.11) y extra_predicates []",
      frag_ks == {"state": "kill-switch WITT_FIGURES=0"} and preds_ks == [] and frag_kl == {"state": "kill-switch WITT_FIGURES=0"} and preds_kl == []
      and frag_ke == {"state": "kill-switch WITT_FIGURES=0"} and preds_ke == [], json.dumps([frag_ks, frag_kl, frag_ke]))

# 6j) precedent.validate_disjoint (SIN tocar): kind 'figure' con `n` entero pasa; con `l` (serie de precedente) cae
check("precedent.validate_disjoint (no se toca, verificado): evidencia kind 'figure' con `n` entero → True; con `l` o sin `n` entero → False",
      precedent.validate_disjoint({"evidence": [{"n": 1, "kind": "figure", "id": G1}], "precedent": []}) is True
      and precedent.validate_disjoint({"evidence": [{"n": 1, "l": "A", "kind": "figure", "id": G1}], "precedent": []}) is False
      and precedent.validate_disjoint({"evidence": [{"n": "1", "kind": "figure", "id": G1}], "precedent": []}) is False)

# 6k) cero red, cero mutación fuera de TMP
check("ADR-0083 M.5: urlopen (urllib y la costura figures._urlopen) = 0 llamadas en toda la sección; _get_bytes falsa = 2 (un zip por paper); "
      "el mcp_cache/figures del REPO no cambió de existencia (la caché del smoke vive en TMP / WITT_MCP_CACHE_DIR)",
      _NET_CALLS == [] and len(GET_CALLS) == 2 and REPO_FIG_CACHE.exists() == _repo_fig_cache_before,
      f"net={_NET_CALLS} gets={len(GET_CALLS)} cache={CR}")
import shutil  # noqa: E402
shutil.rmtree(CR, ignore_errors=True)      # la caché del smoke es efímera: nada queda en WITT_MCP_CACHE_DIR
shutil.rmtree(TMP, ignore_errors=True)

npass = sum(CHECKS)
print("\n== %d/%d PASS ==" % (npass, len(CHECKS)))
sys.exit(0 if npass == len(CHECKS) else 1)
