"""
reasoning_catalog.py — the machine-readable face of `references/reasoning-frameworks-catalog.md` v1.2
(tapón 2 / ADR-0060).

WHY THIS EXISTS. CLAUDE.md §4 requires that `framework_applied` travel with a citation of the SPECIFIC
catalog section plus a quoted criterion, and it records the anti-pattern it exists to prevent: two real
sessions (2026-05-09 and 2026-05-14) tagged outputs "Tier 2" without ever consulting the catalog, and
citing the tier header instead of the framework section is itself a §4 audit failure.

A model asked to supply the section number can get it wrong. So it does NOT supply it: the model picks a
NAME from a closed enum and quotes the criterion it matched; this table maps name -> (section, tier)
DETERMINISTICALLY. The anti-pattern §4 was written against becomes structurally impossible rather than
merely forbidden.

The criteria below are the Tier-list one-liners of the catalog (§"Tier 1/2/3" sections), verbatim enough
to be matched against what the model quotes — see criterion_matches_catalog(). A mismatch is NOT an
error: it is a declared fact about the citation, recorded as such.

`framework_applied` stays SELF-REPORT by §5's own critical note ("LLMs do not reliably introspect their
own reasoning" — Anthropic, April 2025; treat as a prompt-time tag, never as a verified claim). This
module never upgrades it. What it does is make the *citation* checkable and the *tier* trustworthy.
"""

CATALOG_VERSION = "v1.2"
CATALOG_PATH = "skills/custom/organogenesis-agent-architect/references/reasoning-frameworks-catalog.md"

# name -> (section, tier, applicability criterion as the catalog states it)
FRAMEWORKS = {
    "Chain-of-Thought": (
        "§1", 2,
        "useful as prompting structure, but the chain produced is not a reliable window into the "
        "model's actual reasoning; use for output structure, not for auditability"),
    "Tree-of-Thought": (
        "§2", 2,
        "promising for exploratory problems, but the multi-branch structure exposes the model to "
        "disjunctive reasoning failures"),
    "Self-Discover": (
        "§3", 2,
        "maintain for novel problem types but monitor; limited 2025+ literature"),
    "Self-Consistency": (
        "§4", 1,
        "for any task where multiple runs can be majority-voted; agreement rate doubles as "
        "confidence signal"),
    "Logic-LM": (
        "§5", 1,
        "for any task whose criteria are formalizable; produces results perfectly calibrated by "
        "construction because the verification step is symbolic, not neural"),
    "Inversion": (
        "§6", 3,
        "risk-assessment heuristic; no 2025+ LLM-specific studies"),
    "First-Principles Reasoning": (
        "§7", 3,
        "assumption-stripping heuristic; no 2025+ LLM-specific studies"),
    "Chain-of-Verification": (
        "§8", 2,
        "favored for high-stakes outputs, but excessive verification degrades performance on simple "
        "problems; context-dependent"),
}

# CLAUDE.md §4: "If no Tier 2 framework matches either, Tier 3 is acceptable but the agent MUST declare
# in the output that no rigorous-evidence framework matched." This literal IS that declaration.
NONE_MATCHED = "NONE-MATCHED"

ENUM = sorted(FRAMEWORKS) + [NONE_MATCHED]


def digest():
    """The compact catalog handed to the synthesizer. A criterion cannot be quoted from a file the model
    never saw — without this, demanding a citation manufactures fabricated section numbers, which is
    worse than demanding nothing."""
    lines = [f"Reasoning-frameworks catalog {CATALOG_VERSION} (tier 1 = preferred when applicable):"]
    for name in sorted(FRAMEWORKS, key=lambda n: FRAMEWORKS[n][1]):
        sec, tier, crit = FRAMEWORKS[name]
        lines.append(f'  - {name} (Tier {tier}): "{crit}"')
    lines.append(f'  - {NONE_MATCHED}: no framework above matches; say so instead of forcing one.')
    return "\n".join(lines)


def _norm(s):
    return " ".join((s or "").lower().replace("-", " ").split())


def criterion_matches_catalog(name, quoted, min_overlap=0.5):
    """Did the quoted criterion actually come from this framework's catalog entry? Token-overlap rather
    than exact substring, because a paraphrase is a weaker citation but not a fabricated one. Returns
    (matches, overlap) — recorded, never used to reject."""
    entry = FRAMEWORKS.get(name)
    if not entry or not (quoted or "").strip():
        return False, 0.0
    want = set(_norm(entry[2]).split())
    got = set(_norm(quoted).split())
    if not got:
        return False, 0.0
    overlap = len(want & got) / max(1, len(got))
    return overlap >= min_overlap, round(overlap, 3)


def resolve(name, quoted_criterion, reason=""):
    """Build the record's `framework_applied` block. The section and the tier come from the TABLE; only
    the name and the quote come from the model. `class` is stamped on every path: this field is a
    prompt-time tag (§5 critical note) and a consumer must never paint it as a measurement."""
    base = {
        "class": "self-report",
        "class_note": ("etiqueta de prompt-time, NO introspección fiel (§5, nota crítica v2.2; "
                       "Anthropic abril 2025). Jamás se renderiza como medición."),
        "catalog": f"{CATALOG_PATH} {CATALOG_VERSION}",
    }
    if name == NONE_MATCHED:
        return dict(base, name=NONE_MATCHED, catalog_section=None, tier=None,
                    quoted_criterion=None, criterion_matches_catalog=None,
                    declared_no_rigorous_framework=True, reason=reason or "no declarado")
    if name not in FRAMEWORKS:
        # fuera del vocabulario: se registra el literal crudo, no se corrige ni se descarta
        return dict(base, name=name or None, catalog_section=None, tier=None,
                    quoted_criterion=quoted_criterion or None, criterion_matches_catalog=False,
                    off_catalog=True, reason=reason or "")
    sec, tier, _crit = FRAMEWORKS[name]
    matches, overlap = criterion_matches_catalog(name, quoted_criterion)
    return dict(base, name=name, catalog_section=sec, tier=tier,
                quoted_criterion=(quoted_criterion or "").strip() or None,
                criterion_matches_catalog=matches, criterion_overlap=overlap,
                reason=reason or "")


# --- what the PIPELINE applies, regardless of what the model tags -------------------------------------
# Derived from code, not self-reported. This is the honest counterweight to `framework_applied`: the
# run's real guarantees live here.
def structural_frameworks():
    return [
        {"mechanism": "Logic-LM (verificación simbólica determinista)",
         "catalog_section": "§5", "tier": 1, "component": "lib/verify_output.py",
         "class": "derived-from-code",
         "note": "no es un LLM: un identificador que no resuelve contra el store verificado es falla de gate"},
        {"mechanism": "panel adversarial composite-auditor Mode 1 (4 lentes, 2 proveedores), "
                      "agregación worst-of-N",
         "catalog_section": None, "tier": None, "component": "lib/composite_auditor.py",
         "class": "derived-from-code",
         "note": "NO es Self-Consistency (§4): no hay voto por mayoría — cualquier catch real domina. "
                 "Se nombra aparte para no disfrazar worst-of-N de framework de Tier 1"},
        {"mechanism": "dos pasadas con gate de confianza (τ) sobre evidencia DI-only vs aumentada",
         "catalog_section": None, "tier": None, "component": "query_service/runs.py",
         "class": "derived-from-code",
         "note": "ADR-0051: el delta pass1→pass2 es la medición de '¿mi store alcanza?'"},
    ]
