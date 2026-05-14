# SKILL.md Templates & Writing Rules

> **When to read this file:** When generating SKILL.md files in Phase 4. Contains the frontmatter template, sub-skill template, orchestrator template, bilingual trigger writing rules, and the 1024-char description checklist. Read this *before* writing your first SKILL.md, not after.

---

## The Hard Rules (Non-Negotiable)

These come from the Claude Skills platform itself. Violating any of them produces a skill that won't upload, won't trigger, or will be rejected at audit.

1. **Filename:** Exactly `SKILL.md` (case-sensitive). No variations.
2. **Folder name:** kebab-case, no spaces, no capitals, no underscores. Must match the `name` field.
3. **Frontmatter delimiters:** Three dashes `---` on their own lines, top and bottom of the frontmatter block.
4. **Required fields:** `name` and `description`. Both are mandatory.
5. **Description length:** Under 1024 characters. **Hard platform limit.** Always count.
6. **No XML angle brackets** (`<` `>`) anywhere in frontmatter. They break the parser.
7. **No `claude` or `anthropic` in the skill name.** Reserved.
8. **No `README.md` inside the skill folder.** All docs go in `SKILL.md` or `references/`.
9. **SKILL.md body target:** Under 500 lines. If you'd exceed it, push detail into `references/`.

---

## Frontmatter Template (Copy + Edit)

```yaml
---
name: kebab-case-skill-name
description: "What the agent does (1-2 sentences). Use when someone says: trigger phrase 1, trigger phrase 2, trigger phrase 3 (English), frase activadora 1, frase activadora 2 (Spanish). Also activates on: domain-specific terms, partner names, project terms. Bilingüe: inglés o español según el usuario."
---
```

**Optional metadata** (use when relevant):

```yaml
metadata:
  author: Emmanuel / Project Organogenesis
  version: 1.0.0
  category: simulation | wet-lab | omics | knowledge | operations
  stage: phase-1 | phase-2 | phase-3 | all
```

---

## Description Writing Rules

The description is the single most important field. It's loaded into Claude's system prompt at all times and decides whether your skill triggers. Get this right or the skill is dead on arrival.

### Required components

A working description has **all three** of these:

1. **WHAT it does** — One concrete sentence. Not "helps with biology" — say "Designs wet-lab protocols translating pruned intervention recipes into zebrafish kidney experiments."
2. **WHEN to trigger** — Explicit phrases users would actually say, in *both* languages.
3. **Domain anchors** — Project-specific terms (causal pruning, chaperone tissue, BWH, SeqMatic, pronephros) that signal "this skill knows the project."

### Bilingual trigger structure

Use this template:

> "[WHAT in user's primary language]. Use when someone says: [English trigger 1], [English trigger 2], [English trigger 3], [Spanish trigger 1], [Spanish trigger 2], [Spanish trigger 3]. Also activates on: [domain term 1], [domain term 2], [partner name 1]. Bilingüe: inglés o español según el usuario."

Or interleave them more naturally:

> "[WHAT in Spanish]. Use when: [trigger phrases mixing languages]. Also: [domain anchors]. Bilingüe."

Both work. The interleaved version usually fits more triggers per character.

### What good triggers look like

✅ Specific, action-y phrases users actually type:
- "design an experiment", "draft a protocol", "translate intervention to wet lab"
- "diseñar experimento", "redactar protocolo", "traducir intervención a wet lab"

❌ Generic, vague phrases that overlap with everything:
- "help me", "do biology", "ayúdame"

✅ Project nouns that anchor the skill:
- "pronephros induction", "chaperone tissue patch", "BWH embryo batch", "Runpod sim sweep"

❌ Generic nouns:
- "research", "experiment", "data"

### The 1024-char budget

Every char counts. To pack triggers efficiently:

- Drop articles (`the`, `a`, `los`, `las`) where readable.
- Use slashes for alternatives: `simulation/pruning/lab`.
- Move weak triggers out — keep the top 6-10 in each language.
- Always count before delivering. Use this Python one-liner mentally:
  > `len("...your description here...")`

### Avoid these description anti-patterns

1. **English-only descriptions.** The user code-switches. So must the skill.
2. **All-trigger no-WHAT.** Triggers without describing what the skill does means Claude triggers it but doesn't know what to do.
3. **All-WHAT no-triggers.** Beautiful prose explanation, zero trigger phrases — the skill never fires.
4. **Repeating the name as the WHAT.** "Kidney protocol designer designs kidney protocols." Useless.
5. **Forbidden chars.** No `<` or `>` in frontmatter. None.

---

## Specialist Skill Template (Sub-skill)

For an agent that owns a single workflow slice and has no sub-agents of its own.

```markdown
---
name: <agent-name>
description: "<bilingual description with WHAT + WHEN + anchors, under 1024 chars>"
---

# <Agent Display Name>

You are <one-line role statement — what kind of expert this agent is>.

Your job is to <one-paragraph description of the workflow slice this agent owns>. You produce <output type>. You do not <explicit non-responsibilities>.

You are bilingual. Match the user's language.

---

## When to Use This Skill

Use when:
- <Trigger condition 1>
- <Trigger condition 2>
- <Trigger condition 3>

Skip this skill when:
- <Boundary case 1 — what skill should be used instead>
- <Boundary case 2>

---

## Inputs You Need

To do your job, you need:
1. **<Input 1>** — <format, source, why>
2. **<Input 2>** — <format, source, why>

If any are missing, ask before proceeding. Don't fabricate.

---

## Workflow

### Step 1 — <name>
<concrete instructions, in imperative voice>

### Step 2 — <name>
<concrete instructions>

### Step 3 — <name>
<concrete instructions>

---

## Output Format

<Template for the output, in a code block, with placeholders>

---

## Quality Gates

Before delivering, verify:
- [ ] <Gate 1 — specific, testable>
- [ ] <Gate 2>
- [ ] <Gate 3>

---

## Failure Modes & Fallbacks

**If <X happens>:** <what to do>
**If <Y happens>:** <what to do>

---

## Hands Off To

After delivering, the natural next agent is **<downstream-agent-name>**. Mention this to the user so they know where to take the output next.
```

---

## Orchestrator Skill Template

For an agent that routes to or coordinates sub-agents. Smaller body — most logic is "when to call which sub-skill."

```markdown
---
name: <orchestrator-name>
description: "<bilingual description making clear this is an orchestrator, with triggers like 'plan the X workflow', 'coordinate Y', 'orchestrate Z' in both languages>"
---

# <Orchestrator Display Name>

You are the orchestrator for <workflow domain>. You don't do the work yourself — you decide which sub-skill to invoke, in what order, with what context, and you synthesize the results.

You are bilingual. Match the user's language.

---

## Sub-skills You Coordinate

| Sub-skill | When to invoke |
|-----------|----------------|
| `<sub-skill-1>` | <Specific trigger condition> |
| `<sub-skill-2>` | <Specific trigger condition> |
| `<sub-skill-3>` | <Specific trigger condition> |

---

## Orchestration Logic

<Describe the pattern: pipeline, supervisor, parallel+aggregator, etc. Reference the pattern by name. Then describe the actual sequence/branching for THIS workflow>

### The default flow

1. <Step 1: invoke sub-skill X with inputs Y>
2. <Step 2: review output Z>
3. <Step 3: invoke sub-skill A or B based on conditional>
4. <Step 4: synthesize and present to user>

### Decision points

**If <condition 1>:** invoke `<sub-skill>`.
**If <condition 2>:** invoke `<sub-skill>` instead.
**If results conflict:** <fallback or escalation>.

---

## Human-in-the-Loop Gates

This orchestrator pauses and asks for explicit approval at:
- <Gate 1>
- <Gate 2>

Never proceed past a gate without an explicit "yes" from the user.

---

## Output Format

<Synthesis template — what the orchestrator returns to the user after coordinating sub-skills>

---

## What This Orchestrator Does NOT Do

- It does NOT do the work of sub-skills inline. If you find yourself rewriting what a sub-skill produces, stop and re-invoke the sub-skill.
- It does NOT skip sub-skills to "save time." If a sub-skill is in the workflow, it runs.
- It does NOT modify sub-skill outputs without disclosure to the user.
```

---

## Bilingual Trigger Writing Tips

The user (Emmanuel) code-switches Spanish/English mid-conversation. Every skill needs both. Here's how to do it efficiently:

### Strategy 1 — Mirrored phrases

For each English trigger, include the Spanish equivalent:
- "design an experiment" / "diseñar experimento"
- "review my agent system" / "revisar mi sistema de agentes"
- "what agents do I need" / "qué agentes necesito"

### Strategy 2 — Domain terms stay English

Most technical terms (causal pruning, scRNA-seq, chaperone tissue, BWH, Runpod, Morizane) are in English even in Spanish conversations. List them once.

### Strategy 3 — Pack imperatives

Imperative verbs are short and trigger well. Stack them:
- English: "design, draft, plan, propose, generate, audit, review"
- Spanish: "diseña, redacta, planea, propón, genera, audita, revisa"

### Strategy 4 — Avoid translation traps

Some phrases don't translate cleanly:
- "Ship it" → no good Spanish equivalent. Use "lanzar" or "entregar".
- "Sprint" → both languages use it.
- "Roadmap" → both languages use it.

When in doubt, include both. The 1024-char budget is tight but rarely *that* tight.

---

## The 1024-Char Description Checklist

Before delivering any SKILL.md, verify:

- [ ] Description starts with WHAT the skill does (one sentence, concrete).
- [ ] Includes "Use when someone says:" or "Use when:" followed by ≥6 trigger phrases.
- [ ] Trigger phrases are split between English and Spanish (≥3 each).
- [ ] At least 2 domain anchors (causal pruning, BWH, Runpod, etc.).
- [ ] Ends with bilingual marker: "Bilingüe: inglés o español según el usuario." or equivalent.
- [ ] **Counts under 1024 chars** (count the value between the quotes, not the `description: "..."` wrapper).
- [ ] No `<` or `>` characters anywhere.
- [ ] No skill name starts with `claude-` or `anthropic-`.

If any box is unchecked, fix before delivering.

---

## Folder Structure for a Multi-Skill System

When proposing a multi-agent system, deliver this structure:

```
<system-name>/
├── README.md                       # OPTIONAL: human-facing only, NOT inside skill folders
├── <orchestrator-skill-name>/
│   ├── SKILL.md
│   └── references/
│       ├── orchestration-logic.md
│       └── sub-skill-registry.md
└── sub-skills/
    ├── <agent-1-name>/
    │   ├── SKILL.md
    │   └── references/
    │       └── domain-knowledge.md
    ├── <agent-2-name>/
    │   ├── SKILL.md
    │   └── references/
    └── <agent-3-name>/
        └── SKILL.md
```

**Important:** A `README.md` is fine *at the system root* (for humans browsing the repo), but **never** inside an individual skill folder. The skill folder must contain only `SKILL.md`, `references/`, `scripts/`, and/or `assets/`.

Each individual skill folder gets its own zip when uploading to Claude.ai. The user uploads them one at a time (or whatever the platform allows at the time you're delivering — check current docs).

---

## When to Use Reference Files vs. Inline Content

**Inline in SKILL.md:**
- Core workflow (always loaded when skill triggers)
- Quality gates and decision logic
- Output format templates
- Anti-patterns and failure modes

**In references/ (loaded on demand):**
- Detailed domain knowledge (catalogs, glossaries, partner info)
- Long lookup tables
- Multiple worked examples
- Pattern libraries
- Anything that won't be needed every time the skill triggers

**Rule of thumb:** If the SKILL.md body is approaching 500 lines, move the longest section into a reference file and add a "Read `references/<file>.md` when..." pointer.

---

## Common Mistakes When Generating SKILL.md Files

1. **Forgetting bilingual triggers.** Re-check every description.
2. **Going over 1024 chars.** Count. Always count.
3. **Forgetting the "Does NOT own" line in specialist skills.** Without it, agents overlap.
4. **Inlining what should be a reference file.** Bloated SKILL.md = poor performance.
5. **Vague trigger phrases.** "Help with stuff" doesn't trigger; "design wet-lab protocol" does.
6. **Missing the imperative voice.** "You should consider..." is weaker than "Consider...".
7. **No quality gates.** Without explicit gates, the skill ships whatever it generates.
8. **Inventing partners or facts.** Use only what the user has shared or what's in `references/organogenesis-domain.md`.
