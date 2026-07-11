export const meta = {
  name: 'level2-tooluniverse-fallback',
  description: 'Level-2 agentic Tool Universe fallback: each agent uses STRUCTURED Tool Universe tools (ensembl/zfin/reactome/EuropePMC via MCP) to answer a zebrafish intent question when the DATA INAMOVIBLE is thin, returns the §5 contract; a multi-family judge panel (Opus/Sonnet/Haiku) then scores each answer against expected evidence.',
  phases: [
    { title: 'Synthesize', detail: 'agentic Tool Universe tool-use → §5 contract (Opus)' },
    { title: 'Verify', detail: 'multi-family judge panel scores vs expected evidence' },
  ],
}

const QS = Array.isArray(args) ? args : (typeof args === 'string' ? JSON.parse(args) : (args ? [args] : []))
const JUDGES = ['claude-opus-4-8', 'claude-sonnet-5', 'claude-haiku-4-5-20251001']

const CONTRACT = {
  type: 'object',
  properties: {
    direct_answer: { type: 'string' },
    confidence: { type: 'number', description: 'calibrated probability answer is correct, [0,1]' },
    evidence_cited: { type: 'array', items: { type: 'string' } },
    identifier_bindings: { type: 'array', items: { type: 'object', properties: { symbol: { type: 'string' }, ensdarg: { type: 'string' } }, required: ['symbol'] } },
    alternatives_considered: { type: 'array', items: { type: 'string' } },
    gap_flags: { type: 'array', items: { type: 'string' } },
    framework_applied: { type: 'string' },
    tu_tools_called: { type: 'array', items: { type: 'string' }, description: 'Tool Universe tools you actually EXECUTED (empty if DI sufficed)' },
  },
  required: ['direct_answer', 'confidence', 'evidence_cited', 'identifier_bindings', 'alternatives_considered', 'gap_flags', 'framework_applied', 'tu_tools_called'],
}

const VERDICT = {
  type: 'object',
  properties: {
    overall_score: { type: 'number', description: 'overall answer quality vs expected evidence, [0,1]' },
    verdict: { type: 'string', enum: ['correct', 'partial', 'incorrect', 'abstain'] },
    justification: { type: 'string' },
  },
  required: ['overall_score', 'verdict', 'justification'],
}

function synthPrompt(q) {
  return [
    'You answer a zebrafish developmental-biology question under the Witt §5 output contract.',
    '',
    'QUESTION (' + q.type + '):', q.q,
    '',
    'DATA INAMOVIBLE retrieval (Path A — this is THIN by design):', q.di || '(none)',
    'DI-resolved entities: ' + (JSON.stringify(q.ents) || '[]'),
    '',
    'The DI is insufficient to answer this well. USE TOOL UNIVERSE (Level-2 structured fallback):',
    '1. Load the MCP tools: call ToolSearch with query "select:mcp__tooluniverse__find_tools,mcp__tooluniverse__get_tool_info,mcp__tooluniverse__execute_tool".',
    '2. Gather STRUCTURED evidence (not just literature): e.g. execute_tool ensembl_lookup_gene (verify gene->ENSDARG, species=danio_rerio); reactome / omnipath tools for pathways/signaling; zfin tools for zebrafish phenotypes; EuropePMC_search_articles only as a literature complement. Use find_tools to locate the right tool when unsure.',
    '3. Ground EVERY claim in what you retrieve. NEVER assert a gene ENSDARG from memory — only IDs you verified via a tool go in identifier_bindings (symbol + ensdarg). List EXACTLY the tools you executed in tu_tools_called.',
    '',
    'Keep confidence calibrated: raise it only to the extent the retrieved evidence actually answers the question; stay low if gaps remain. Return the contract.',
  ].join('\n')
}

function judgePrompt(q, c) {
  return [
    'You are an adversarial expert reviewer. Score the candidate answer against the expected evidence and a rubric.',
    'Reward correctness + verified identifiers + honest uncertainty; penalize overclaiming and fabricated specifics.',
    'You MUST return all fields: numeric overall_score in [0,1], a verdict, and a justification. Use abstain only if truly unjudgeable.',
    '',
    'QUESTION:', q.q,
    '', 'EXPECTED EVIDENCE (what a good answer contains):', q.ee || '(unspecified)',
    '', 'CANDIDATE ANSWER:', (c && c.direct_answer) || '(none)',
    'Candidate confidence: ' + ((c && c.confidence) != null ? c.confidence : 'n/a'),
    'Candidate cited: ' + JSON.stringify((c && c.evidence_cited) || []),
    'Candidate identifier_bindings: ' + JSON.stringify((c && c.identifier_bindings) || []),
    'Candidate Tool Universe tools executed: ' + JSON.stringify((c && c.tu_tools_called) || []),
  ].join('\n')
}

log('Level-2 agentic Tool Universe fallback over ' + QS.length + ' questions')

const results = await pipeline(
  QS,
  async (q) => {
    const c = await agent(synthPrompt(q), { label: 'synth:' + q.id, phase: 'Synthesize', schema: CONTRACT })
    return { q, contract: c }
  },
  async (prev) => {
    if (!prev || !prev.contract) return null
    const q = prev.q, contract = prev.contract
    const verdicts = await parallel(JUDGES.map((m) => () =>
      agent(judgePrompt(q, contract), { label: 'judge:' + q.id + ':' + m.split('-')[1], phase: 'Verify', model: m, schema: VERDICT })
        .then((v) => (v ? { model: m, ...v } : null))
    ))
    return { q_id: q.id, type: q.type, contract, verdicts: verdicts.filter(Boolean) }
  }
)

return results.filter(Boolean)