# ADR-0033 — Security hardening of the hosted store is an integrity control, not a backlog item

- **Status:** **Proposed — DEFERRED, no action now.** Founder direction (2026-07-05): *"la 0033 de data inamovible: por el momento, no le hagamos ningún cambio."* Recorded as a **parked finding** to revisit later. This ADR changes nothing: no reclassification is enforced, no deployment is touched, no reporting behavior is mandated, and the DATA INAMOVIBLE / its hosted surfaces are left exactly as they are. From the external review (Fable 5, 2026-07-05, rec 3).
- **Relates:** ADR-0020/0021 (hosted GraphRAG + MinIO on Dokploy), CLAUDE.md §7 (DI is human-gated + "inamovible").
- **Affects:** the Dokploy deployment (infrastructure; executed by a human with Dokploy access — not by an agent).

## Context

The external auditor: *"an externally reachable, mutable canonical store nullifies the entire human-gate
guarantee. This is an integrity control, not a backlog item."* Correct. The whole "inamovible" property
(all mutations human-gated) is void if the Neo4j/MinIO/ingest surfaces can be reached and mutated outside
the gate. This had been tracked as a low-priority deploy to-do; it is re-classified here as an **integrity
control** on par with the human gate itself.

Currently exposed on the Dokploy host (per deployment notes): Neo4j `7474`/`7687`, MinIO `9100`/`9101`,
ingest service `8077`.

## Decision

**Deferred — take no action now** (founder direction). This section records, for whoever revisits this, the
hardening checklist that *would* apply. It is a proposal, not an adopted requirement, until un-deferred.
Checklist (human-executed on Dokploy when revisited):

1. **Close public ports.** Put Neo4j (7474/7687), MinIO (9100/9101), and the ingest service (8077) behind
   the Dokploy internal network; expose nothing publicly that can mutate the store.
2. **TLS** on any surface that must remain reachable.
3. **Strong, rotated credentials** for Neo4j/MinIO; the ingest service `INGEST_ADMIN_TOKEN` treated as the
   gate key (least-privilege; rotate).
4. **Verify the gate cannot be bypassed:** confirm there is no write path to Neo4j/MinIO that skips
   `ingest.py` / the `/approve` human gate.
5. **Access logging** on the ingest service so approvals/mutations are auditable after the fact.

## Consequences

- **No change now.** The security posture, the hosted surfaces, and the current reporting language are left
  untouched per founder direction. This ADR sits as a deferred, revisitable record.
- Factual note for whoever un-defers this (not a mandated behavior change today): while these surfaces remain
  publicly reachable, the human-gate guarantee is technically conditional; treat that honestly when the time
  comes to act.
- When un-deferred: it becomes a human-executed task on Dokploy (an agent cannot/should not perform it); this
  ADR is the spec + checklist. Re-verify item 4 after hardening.
