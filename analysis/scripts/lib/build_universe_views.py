"""
build_universe_views.py — Generate the 3 "project universe" visualizations (GWT v1.1, Cycle 4 viz).

NO-SPEND, stdlib only. Reads REAL repo data (no fabrication) and emits 3 self-contained HTML files
under reports/:
  (a) universe-graph-niches-dbs-entities.html  — Cytoscape.js graph: niches <-> databases <-> entities
  (b) project-universe-view0.html              — static index: agents + ADRs + claim records + reports
  (c) crosswalk-heatmap-9x13.html              — heatmap of the 9 DBs x 13 niches crosswalk

Cytoscape.js loads from CDN (same convention as the project's Three.js TYPE C reports); the data is
embedded inline so the file is otherwise self-contained. (b) and (c) use pure HTML/CSS (no external lib).

Regenerable as the repo grows. Usage:  python analysis/scripts/lib/build_universe_views.py
"""
from pathlib import Path
import json
import re

ROOT = Path(__file__).resolve().parents[3]
RAG = ROOT / "rag_index"
REPORTS = ROOT / "reports"
CATALOG = ROOT / "skills/custom/organogenesis-agent-architect/references/agent-catalog.md"
ADR_INDEX = ROOT / "docs/decisions/README.md"
RECORDS = ROOT / "substrate_calibration/records"

CSS = """body{margin:0;background:#0f172a;color:#e2e8f0;font:14px/1.5 -apple-system,Segoe UI,Roboto,Arial,sans-serif;padding:22px}
h1{font-size:22px;margin:0 0 4px}h2{font-size:16px;color:#38bdf8;border-bottom:1px solid #334155;padding-bottom:6px;margin:22px 0 10px}
.sub{color:#94a3b8;margin:0 0 16px}.card{background:#172033;border:1px solid #334155;border-radius:10px;padding:12px 14px;margin:8px 0}
a{color:#7dd3fc;text-decoration:none}a:hover{text-decoration:underline}
table{border-collapse:collapse;width:100%;font-size:12.5px}th,td{border:1px solid #334155;padding:5px 8px;text-align:left}th{background:#1e293b}
.badge{display:inline-block;padding:1px 7px;border-radius:999px;font-size:11px;margin:1px 2px}
.good{background:rgba(22,163,74,.15);color:#4ade80}.warn{background:rgba(245,158,11,.15);color:#fbbf24}.acc{background:rgba(56,189,248,.13);color:#7dd3fc}.mut{color:#94a3b8}"""


def load_json(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def parse_agents():
    """### agent headings grouped under ## Category headings in agent-catalog.md."""
    cat, agents = None, []
    for line in CATALOG.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^## (Category [^\n]+)", line) or re.match(r"^## (.+)", line)
        if line.startswith("## "):
            cat = line[3:].strip()
        elif line.startswith("### "):
            name = line[4:].strip()
            # skip pure operational sub-notes that aren't agents
            if cat and ("Category" in cat or "Substrate" in cat):
                agents.append((name, cat))
    return agents


def parse_adrs():
    rows = []
    for line in ADR_INDEX.read_text(encoding="utf-8").splitlines():
        m = re.match(r"\|\s*\[(\d{4})\]\(([^)]+)\)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|", line)
        if m:
            rows.append({"id": m.group(1), "file": m.group(2), "date": m.group(3),
                         "title": m.group(4), "status": m.group(5)})
    return rows


def parse_claims():
    out = []
    for f in sorted(RECORDS.glob("*.json")):
        d = load_json(f)
        out.append({"id": d.get("claim_id"), "conf": d.get("stated_confidence"),
                    "outcome": d.get("observed_outcome"), "cat": d.get("claim_category"),
                    "tests": d.get("test_mapping", [])})
    return out


def list_reports():
    return sorted(p.name for p in REPORTS.glob("*.html"))


# ---------- (a) Cytoscape graph ----------
def build_graph():
    niches = load_json(RAG / "niches.json")["niches"]
    dbs = load_json(RAG / "databases.json")["databases"]
    cross = load_json(RAG / "niche_database_crosswalk.json")["crosswalk"]
    store = load_json(RAG / ".." / "analysis/outputs/verified_identifiers.json") if (ROOT / "analysis/outputs/verified_identifiers.json").exists() else {"records": []}
    anchors = [r["symbol"] for r in store.get("records", []) if str(r.get("raw_cache_ref", "")).startswith("RAW:")][:7]

    els = []
    for n in niches:
        els.append({"data": {"id": n["id"], "label": n["id"], "ttype": "niche", "full": n["name"]}})
    for d in dbs:
        els.append({"data": {"id": d["id"], "label": d["name"], "ttype": "db", "full": d.get("utility", "")}})
    for a in anchors:
        els.append({"data": {"id": "g_" + a, "label": a, "ttype": "entity", "full": "verified gene (RAW tier)"}})
        els.append({"data": {"source": "g_" + a, "target": "RN1", "etype": "entity"}})
    for db, info in cross.items():
        for nid in info.get("declared", []):
            els.append({"data": {"source": db, "target": nid, "etype": "declared", "prov": info.get("provenance")}})
        for nid in info.get("proposed", []):
            els.append({"data": {"source": db, "target": nid, "etype": "proposed", "prov": info.get("provenance")}})

    return f"""<!DOCTYPE html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Universe graph — niches ↔ databases ↔ entities</title><style>{CSS}
#cy{{width:100%;height:72vh;background:#0b1220;border:1px solid #334155;border-radius:10px}}</style>
<script src="https://cdn.jsdelivr.net/npm/cytoscape@3.30.2/dist/cytoscape.min.js"></script></head><body>
<h1>Universe graph — niches ↔ databases ↔ entities</h1>
<p class="sub">GWT v1.1 · self-contained (Cytoscape from CDN, data embedded) · drag/zoom · <span class="badge acc">niche RN</span> <span class="badge good">database</span> <span class="badge warn">verified entity</span> · solid=declared feed, dashed=proposed (human-gate)</p>
<div id="cy"></div>
<script>
const ELS={json.dumps(els)};
const cy=cytoscape({{container:document.getElementById('cy'),elements:ELS,
 style:[
  {{selector:'node[ttype="niche"]',style:{{'background-color':'#38bdf8','label':'data(label)','color':'#0b1220','font-size':11,'text-valign':'center','width':34,'height':34}}}},
  {{selector:'node[ttype="db"]',style:{{'background-color':'#16a34a','label':'data(label)','color':'#e2e8f0','font-size':10,'shape':'round-rectangle','width':'label','padding':'6px'}}}},
  {{selector:'node[ttype="entity"]',style:{{'background-color':'#f59e0b','label':'data(label)','color':'#0b1220','font-size':9,'shape':'diamond','width':22,'height':22}}}},
  {{selector:'edge[etype="declared"]',style:{{'width':2,'line-color':'#475569','curve-style':'bezier'}}}},
  {{selector:'edge[etype="proposed"]',style:{{'width':1.5,'line-color':'#7c2d12','line-style':'dashed'}}}},
  {{selector:'edge[etype="entity"]',style:{{'width':1,'line-color':'#92400e','line-style':'dotted'}}}}
 ],
 layout:{{name:'cose',animate:false,padding:30,nodeRepulsion:9000,idealEdgeLength:90}}}});
cy.on('tap','node',e=>alert(e.target.data('label')+' — '+(e.target.data('full')||'')));
</script></body></html>"""


# ---------- (b) View 0 static index ----------
def build_view0():
    agents = parse_agents()
    adrs = parse_adrs()
    claims = parse_claims()
    reports = list_reports()
    by_cat = {}
    for name, cat in agents:
        by_cat.setdefault(cat, []).append(name)
    agent_html = ""
    for cat, names in by_cat.items():
        agent_html += f"<div class='card'><b>{cat}</b><br>" + " ".join(f"<span class='badge acc'>{n}</span>" for n in names) + "</div>"
    adr_html = "<table><tr><th>ADR</th><th>Title</th><th>Status</th></tr>" + "".join(
        f"<tr><td><a href='../docs/decisions/{a['file']}'>{a['id']}</a></td><td>{a['title']}</td>"
        f"<td><span class='badge {'good' if 'ccept' in a['status'] else 'warn'}'>{a['status']}</span></td></tr>" for a in adrs) + "</table>"
    claim_html = "<table><tr><th>Claim</th><th>Cat</th><th>Conf</th><th>Outcome</th><th>Tests</th></tr>" + "".join(
        f"<tr><td>{c['id']}</td><td>{c['cat']}</td><td>{c['conf']}</td>"
        f"<td><span class='badge {'good' if c['outcome'] in ('positive','h1') else 'mut'}'>{c['outcome'] or 'pending'}</span></td>"
        f"<td class='mut'>{', '.join(c['tests'])}</td></tr>" for c in claims) + "</table>"
    rep_html = "".join(f"<div class='card'><a href='{r}'>{r}</a></div>" for r in reports)
    return f"""<!DOCTYPE html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Project universe — View 0</title><style>{CSS}</style></head><body>
<h1>Project universe — View 0 (static index)</h1>
<p class="sub">GWT v1.1 · regenerable (build_universe_views.py) · agents + ADRs + claim records + reports</p>
<div class="card"><b>Stats:</b> <span class="badge acc">{len(agents)} agent entries</span>
 <span class="badge good">{len(adrs)} ADRs</span> <span class="badge warn">{len(claims)} claim records</span>
 <span class="badge acc">{len(reports)} reports</span></div>
<h2>Agents (catalog)</h2>{agent_html}
<h2>Architecture Decision Records</h2><div class="card">{adr_html}</div>
<h2>Substrate calibration — claim records</h2><div class="card">{claim_html}</div>
<h2>Reports (outputs / theses — kept separate)</h2>{rep_html}
</body></html>"""


# ---------- (c) Crosswalk heatmap ----------
def build_heatmap():
    niches = [n["id"] for n in load_json(RAG / "niches.json")["niches"]]
    dbs = load_json(RAG / "databases.json")["databases"]
    cross = load_json(RAG / "niche_database_crosswalk.json")["crosswalk"]
    header = "<tr><th>DB \\ niche</th>" + "".join(f"<th>{n}</th>" for n in niches) + "</tr>"
    rows = ""
    for d in dbs:
        info = cross.get(d["id"], {})
        decl, prop = set(info.get("declared", [])), set(info.get("proposed", []))
        cells = ""
        for n in niches:
            if n in decl:
                cells += f"<td style='background:#16a34a;color:#06210f;text-align:center'>P</td>"
            elif n in prop:
                cells += f"<td style='background:#7c2d12;color:#fde68a;text-align:center'>+</td>"
            else:
                cells += "<td style='background:#0b1220'></td>"
        rows += f"<tr><td><b>{d['name']}</b><br><span class='mut' style='font-size:10px'>{info.get('provenance','')}</span></td>{cells}</tr>"
    return f"""<!DOCTYPE html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Crosswalk heatmap — 9 DBs × 13 niches</title><style>{CSS}
td,th{{font-size:11px;padding:4px 6px}}</style></head><body>
<h1>Crosswalk heatmap — 9 databases × 13 RAG data-niches</h1>
<p class="sub">GWT v1.1 · <span class="badge good">P = declared feed (databases.json)</span> <span class="badge warn">+ = proposed (human-gate)</span> · provenance per row</p>
<div class="card" style="overflow-x:auto"><table>{header}{rows}</table></div>
<p class="mut" style="font-size:12px">Edge-provenance rule: IntAct(physical) &gt; BioGRID(genetic) &gt; STRING(predicted). A STRING-only edge is tagged predicted + carries a gap_flag. Source: rag_index/niche_database_crosswalk.json</p>
</body></html>"""


def main():
    REPORTS.mkdir(exist_ok=True)
    (REPORTS / "universe-graph-niches-dbs-entities.html").write_text(build_graph(), encoding="utf-8")
    (REPORTS / "project-universe-view0.html").write_text(build_view0(), encoding="utf-8")
    (REPORTS / "crosswalk-heatmap-9x13.html").write_text(build_heatmap(), encoding="utf-8")
    print("[universe] wrote 3 reports: universe-graph-niches-dbs-entities.html, "
          "project-universe-view0.html, crosswalk-heatmap-9x13.html")


if __name__ == "__main__":
    main()
