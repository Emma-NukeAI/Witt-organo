# Deploy the DATA INAMOVIBLE (Neo4j GraphRAG) on Dokploy — handoff for the server/devops dev

**Audience:** the developer who manages the server + Dokploy. **Goal:** stand up the project's shared
knowledge database ("DATA INAMOVIBLE") — a Neo4j graph + vector store the project's AI agents query.
Self-hosted, no paid services. Engine decision: Neo4j runs as a **Docker-Compose stack inside Dokploy**
(ADR-0020). You do NOT need to know the biology; this is standard Docker/Dokploy + a few Python scripts.

There are 5 stages: **A** code → Dokploy · **B** deploy Neo4j · **C** init + load data · **D** the query
API (MCP) · **E** point the agents. Do them in order; verify each before the next.

> **Already deployed once (2026-06-12) — the recipe that actually worked.** Neo4j was stood up in
> Dokploy as a **Raw Compose** service (paste the YAML below; no git needed for the DB itself), with
> `NEO4J_AUTH` set in the Dokploy **Environment** tab. Stages C–E (bootstrap, ingest, MCP) were run from
> a workstation that has the repo + can reach Bolt `7687`, using a **gitignored `.secrets/deploy.env`**
> (so no secret ever lands in git or in the MCP client config). Embeddings = **OpenAI** (`text-embedding-3-small`,
> 1536-dim). If you are re-deploying or moving this to a hosted MCP, follow the stages; if you just need to
> re-load the corpus, jump to Stage C.

---

## Prerequisites

- A Dokploy server you control (Docker + Traefik), with outbound internet.
- A private git repo the project lives in (GitHub/GitLab/Gitea). Dokploy deploys from git.
- ~6–8 GB RAM free for Neo4j; persistent disk for the graph.

---

## Stage A — Get the code into Dokploy (via git)

1. The project repo (`witt-organogenesis`) must be in a **private** git remote. (If it isn't pushed yet,
   the project owner pushes `master` to a private remote — ask them; the repo contains the compose file
   + scripts below. Nothing secret is in git: passwords are set as env vars, never committed.)
2. In Dokploy → **Create → Compose** (a Docker-Compose application). Connect it to the repo, branch
   `master`. Set the **Compose file path** to:
   ```
   rag_index/deploy/docker-compose.neo4j.yml
   ```
3. Do NOT deploy yet — set env first (Stage B).

> Alternative without git: copy the repo to the server (`scp -r`/`rsync`) and in Dokploy create the
> Compose service from the local path, or `docker compose -f rag_index/deploy/docker-compose.neo4j.yml up -d`
> directly on the host. Git is preferred (Dokploy redeploys on push).

---

## Stage B — Deploy Neo4j (the database)

1. In the Dokploy Compose service → **Environment**, set (NEVER commit this):
   ```
   NEO4J_AUTH=neo4j/<choose-a-strong-password>
   ```
2. **Ports / networking** (Neo4j exposes two):
   - `7474` — HTTP, the Neo4j Browser (web UI). Expose via a Dokploy domain (Traefik) if you want UI access.
   - `7687` — **Bolt** (the driver protocol the scripts + agents use). Bolt is **TCP, not HTTP** — expose
     it as a **TCP port** (Dokploy port mapping / Traefik TCP router), or keep it on the internal Docker
     network and run the loader (Stage C) + the MCP server (Stage D) **inside that same network**
     (recommended — see Security).
3. **Volumes:** the compose declares `neo4j_data` (persistent graph + vector index) and `neo4j_logs`
   (no Ollama volume — embeddings are the OpenAI API, not a self-hosted model). Dokploy persists named
   volumes across redeploys — confirm they're retained so the graph survives a redeploy.
4. **Deploy.** Then verify:
   - Dokploy logs for the `neo4j` service show `Started.` / `Remote interface available at http://...:7474`.
   - Open `https://<your-domain-or-host>:7474`, log in with `neo4j` / your password.
   - **Report back:** the Neo4j logs tail + that the Browser login works.

(The stack runs **only Neo4j** — no Ollama. Embeddings use the **OpenAI API** at load/query time, see Stage C.)

---

## Stage C — Initialize the schema + load the data (one-time, then on updates)

Run these from a machine that has the repo + Python 3.10+ and can reach the Neo4j **Bolt** endpoint
(ideally inside the Dokploy network, or via the exposed `7687`). This creates the vector index and loads
the curated corpus into Neo4j.

```bash
cd witt-organogenesis
python -m venv .venv && . .venv/bin/activate
pip install -r rag_index/graphrag/requirements.txt

# Point at the Neo4j you just deployed (use the internal host if running inside the Dokploy network):
export NEO4J_URI=bolt://<neo4j-host>:7687
export NEO4J_USER=neo4j
export NEO4J_PASSWORD='<the password from Stage B>'
export EMBED_MODEL=openai                       # OpenAI embeddings (no Ollama); 1536-dim
export OPENAI_API_KEY='<your OpenAI key>'        # secret — env only, never commit
# export OPENAI_EMBED_MODEL=text-embedding-3-large   # optional: 3072-dim, higher quality

python rag_index/graphrag/bootstrap.py     # creates constraints + the vector index (dim auto-matches the model)
python rag_index/graphrag/ingest.py        # loads the corpus (Documents+embeddings, Niches, Databases, Entities)
```

**Verify** (in the Neo4j Browser, or it prints node counts):
```cypher
MATCH (d:Document) RETURN count(d);          // expect ~25 to start (grows as the corpus grows)
SHOW INDEXES;                                 // 'doc_embeddings' VECTOR index ONLINE
```
**Report back:** the `[ingest] ... nodes: {...}` line + the `count(d)`.

> This step is the only WRITER. It's idempotent (safe to re-run when the corpus grows). The project's
> people approve new content before it's loaded (human gate) — re-run `ingest.py` after approvals.

---

## Stage D — The query API the agents use (MCP server)

The agents query the DATA INAMOVIBLE through a small **MCP server** (one process). Run it where the
project's agents/clients can reach it, pointing at Neo4j:

```bash
pip install mcp                  # the MCP SDK (in the same venv)
export RAG_BACKEND=neo4j NEO4J_URI=bolt://<neo4j-host>:7687 NEO4J_USER=neo4j NEO4J_PASSWORD='<secret>'
python rag_index/mcp_server/server.py
```

You can run this as **another Dokploy service** (a small Python app from the same repo, command
`python rag_index/mcp_server/server.py`, same NEO4J_* + RAG_BACKEND env). Quick sanity test without the
SDK: `python rag_index/mcp_server/server.py` runs a smoke test and prints query/resolve results.

---

## Stage E — Point the project's agents at it

In each project instance's MCP client config, register the server. For **Claude Code**, the one-liner
(the server auto-loads `.secrets/deploy.env`, so the config carries NO secrets):

```bash
claude mcp add data-inamovible --scope local -- \
  "<repo>/.venv/Scripts/python.exe" "<repo>/rag_index/mcp_server/server.py"     # Windows
# (Linux/macOS: use <repo>/.venv/bin/python). Verify: `claude mcp get data-inamovible` -> Status: Connected.
# Restart the client once so it spawns the server process and the tools appear.
```

The repo's `CLAUDE.md §8` already instructs agents to consult the DATA INAMOVIBLE via the
`data-inamovible` MCP tools. Once registered, agents call `query_data_inamovible` (semantic) +
`resolve_identifier` (deterministic). For **shared/hosted** access by everyone (not just this
workstation), run the same server as an HTTP/SSE service behind Dokploy/Traefik with auth + TLS — a
follow-up; the local stdio registration above is per-workstation.

---

## Security (please don't skip)

- **`NEO4J_AUTH` / `NEO4J_PASSWORD` are secrets** — set them only as Dokploy env vars; never commit.
- **Do not expose Bolt (7687) to the public internet** without TLS + a strong password. Prefer keeping
  Neo4j + the loader + the MCP server on the **same internal Dokploy network** and exposing only what's
  needed (and behind Traefik/auth if remote access is required).
- Change the default password immediately; Neo4j forces a change on first login.
- Snapshot the `neo4j_data` volume per corpus version (versioned + retraíble — the project's discipline).

---

## What to report back (so we continue together)

After each stage paste: **B** Neo4j logs tail + Browser login OK · **C** the ingest node counts +
`SHOW INDEXES` · **D** the MCP smoke-test output. If anything errors, paste the full error — we debug it.
