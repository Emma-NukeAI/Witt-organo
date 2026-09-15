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

100% offline: cero red, cero spend (caller inyectado; ANTHROPIC/OPENAI keys vacias), cero mutacion de la
DATA INAMOVIBLE ni del registro congelado. Exit 0 = todo PASS.

Corre:  python rag_index/query_service/smoke_gate_citations.py
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

npass = sum(CHECKS)
print("\n== %d/%d PASS ==" % (npass, len(CHECKS)))
sys.exit(0 if npass == len(CHECKS) else 1)
