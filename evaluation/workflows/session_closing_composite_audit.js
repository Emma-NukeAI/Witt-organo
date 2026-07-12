export const meta = {
  name: 'session-closing-composite-audit',
  description: 'Closing composite-auditor (Mode 1, multi-family) over the 2026-07-11 session claims: each claim gets 3 adversarial auditors from DISTINCT families (Opus/Sonnet/Haiku) prompted to REFUTE it given its evidence + honest caveats; returns a per-claim verdict (CONFIRMED/REVISE/REJECT) with the strongest objection. This is the §7 audit gate that the producing agent cannot self-substitute.',
  phases: [{ title: 'Audit', detail: '3 adversarial family-auditors per claim' }],
}

const CLAIMS = Array.isArray(args) ? args : JSON.parse(args)
const AUDITORS = ['claude-opus-4-8', 'claude-sonnet-5', 'claude-haiku-4-5-20251001']

const VERDICT = {
  type: 'object',
  properties: {
    verdict: { type: 'string', enum: ['CONFIRMED', 'REVISE', 'REJECT'],
               description: 'CONFIRMED only if you cannot find a material flaw; REVISE if over-claimed or a material caveat is missing/underweighted; REJECT if unsupported by the evidence.' },
    is_overclaim: { type: 'boolean', description: 'Does the claim assert more than the evidence (esp. small n / not-ground-truth) supports?' },
    strongest_objection: { type: 'string', description: 'The single strongest refutation you can mount.' },
    suggested_revision: { type: 'string', description: 'If REVISE/REJECT, the honest re-statement you would accept.' },
    confidence: { type: 'number', description: 'Your confidence in this verdict, [0,1].' },
  },
  required: ['verdict', 'is_overclaim', 'strongest_objection', 'confidence'],
}

function auditPrompt(c) {
  return [
    'You are an ADVERSARIAL auditor in a composite-audit panel (CLAUDE.md §7). Your job is to REFUTE the claim',
    'below, not to be agreeable. Default to finding its weakest point. Judge it ONLY against the stated evidence.',
    'Penalize: generalizing from small n; treating LLM-as-judge quality as ground truth; correlated reviewers;',
    'comparisons that are not apples-to-apples; confidence lift that could be OVER-confidence rather than accuracy.',
    'Return CONFIRMED only if, after a genuine refutation attempt, the claim stands AS STATED (including its hedges).',
    '',
    'CLAIM (' + c.id + '): ' + c.claim,
    '',
    'EVIDENCE: ' + c.evidence,
    'SAMPLE SIZE / SCOPE: ' + (c.n || 'n/a'),
    'CAVEATS THE OPERATOR ALREADY STATED: ' + (c.caveats || 'none'),
    '',
    'Is this claim CONFIRMED, or does it need REVISE / REJECT? Give your strongest objection regardless.',
  ].join('\n')
}

log('Closing composite-audit over ' + CLAIMS.length + ' session claims × 3 family auditors')

const results = await pipeline(
  CLAIMS,
  async (c) => {
    const verdicts = await parallel(AUDITORS.map((m) => () =>
      agent(auditPrompt(c), { label: 'audit:' + c.id + ':' + m.split('-')[1], phase: 'Audit', model: m, schema: VERDICT })
        .then((v) => (v ? { model: m, ...v } : null))
    ))
    const vs = verdicts.filter(Boolean)
    const labels = vs.map((v) => v.verdict)
    const tally = { CONFIRMED: 0, REVISE: 0, REJECT: 0 }
    labels.forEach((l) => { if (tally[l] != null) tally[l]++ })
    // majority; ties or any REJECT-leaning fall to the more conservative verdict
    let majority = 'REVISE'
    if (tally.CONFIRMED > tally.REVISE + tally.REJECT) majority = 'CONFIRMED'
    else if (tally.REJECT >= tally.CONFIRMED && tally.REJECT >= tally.REVISE) majority = (tally.REJECT >= 2 ? 'REJECT' : 'REVISE')
    const overclaim_votes = vs.filter((v) => v.is_overclaim).length
    return {
      claim_id: c.id, tally, majority_verdict: majority, overclaim_votes,
      objections: vs.map((v) => ({ model: v.model, verdict: v.verdict, objection: v.strongest_objection, revision: v.suggested_revision || null })),
    }
  }
)

return results.filter(Boolean)