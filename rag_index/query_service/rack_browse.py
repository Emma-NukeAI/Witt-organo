"""
rack_browse.py — la operación BROWSE del grafo (Rack fase 2, ADR-0071).

La puerta que faltaba en todas partes ("aparece en el documento de arquitectura, no es tool MCP ni
subcomando del CLI" — faltantes §3): recorrer la DATA INAMOVIBLE como grafo — nicho → documentos →
entidades → nichos de vuelta — y con ella la promesa de LOTE-01·A7: los ejes de taxonomía POR
ENTIDAD derivan del grafo (Document-MENTIONS-Entity + Document-IN_NICHE), nunca de /resolve.

Dos backends, un contrato, marcador in-band (la disciplina ADR-0043):

  - **graph** (producción, NEO4J_URI): Cypher parametrizado ($id — jamás interpolado), acotado
    (EDGE_LIMIT por dirección, truncamiento DECLARADO), NO-SPEND (cero embeds — lookups por
    índice/label). El `embedding` del nodo JAMÁS se serializa.
  - **files-fallback** (dev/offline o grafo caído): derivado de LOS MISMOS archivos fuente que
    alimentan ingest.py (niches.json, databases.json, corpus_manifest.json) con el MISMO gate
    estructural (rag_backend.is_approved — un registro no aprobado no existe para el browse,
    igual que no existe para el grafo). Paridad por construcción, no por imitación.

`browse_mode` viaja SIEMPRE; un grafo configurado-pero-caído cae al fallback con `browse_error`
declarado (§6 no-hang) — nunca un 500, nunca un fallback disfrazado de grafo.

Resolución del id (orden declarado, primer match gana):
  documento (doc_id exacto, datasets y chunks) → entidad (symbol exacto, luego ENSDARG) →
  nicho (id) → base (id). NOT_FOUND = resultado positivo (found: false), como /resolve.
"""
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAG = ROOT / "rag_index"

EDGE_LIMIT = 100   # por dirección; el truncamiento se declara, jamás se esconde

_RESOLUTION_ORDER = "document -> entity(symbol, luego ensdarg) -> niche -> database"


# --------------------------------------------------------------------------- backend: grafo
def _graph_session():
    from neo4j import GraphDatabase
    drv = GraphDatabase.driver(os.environ["NEO4J_URI"],
                               auth=(os.environ.get("NEO4J_USER", "neo4j"),
                                     os.environ["NEO4J_PASSWORD"]),
                               connection_timeout=8, connection_acquisition_timeout=10,
                               max_transaction_retry_time=8)
    return drv


def _node_props(node):
    """Propiedades del nodo SIN el embedding (un vector de 1536 floats no es contenido de browse)
    y con `meta` normalizado a la forma sparse (reutiliza ADR-0069)."""
    props = {k: v for k, v in dict(node).items() if k != "embedding"}
    if "meta" in props:
        import sys as _sys
        _sys.path.insert(0, str(ROOT / "analysis" / "scripts"))
        from lib.rag_backend import _parse_node_meta
        parsed = _parse_node_meta(props.pop("meta"), [])
        parsed.pop("related", None)
        props["meta_parsed"] = parsed
    return props


def _graph_browse(node_id):
    q = node_id
    drv = _graph_session()
    try:
        with drv.session() as s:
            # 1) documento
            row = s.run("MATCH (d:Document {doc_id:$id}) RETURN d", id=q).single()
            if row:
                out = s.run(
                    "MATCH (d:Document {doc_id:$id})-[r]->(x) "
                    "RETURN type(r) AS rel, labels(x) AS labels, properties(r) AS rprops, "
                    "coalesce(x.doc_id, x.symbol, x.id) AS tid, coalesce(x.name, '') AS name "
                    "LIMIT $lim", id=q, lim=EDGE_LIMIT + 1).data()
                inn = s.run(
                    "MATCH (x)-[r]->(d:Document {doc_id:$id}) "
                    "RETURN type(r) AS rel, labels(x) AS labels, properties(r) AS rprops, "
                    "coalesce(x.doc_id, x.symbol, x.id) AS tid, coalesce(x.name, '') AS name "
                    "LIMIT $lim", id=q, lim=EDGE_LIMIT + 1).data()
                return _shape("document", q, _node_props(row["d"]), out, inn)
            # 2) entidad (symbol exacto, luego ensdarg)
            row = s.run("MATCH (e:Entity {symbol:$id}) RETURN e", id=q).single() \
                or s.run("MATCH (e:Entity {ensdarg:$id}) RETURN e", id=q).single()
            if row:
                sym = row["e"].get("symbol")
                inn = s.run(
                    "MATCH (d:Document)-[r:MENTIONS]->(e:Entity {symbol:$s}) "
                    "RETURN 'MENTIONS' AS rel, labels(d) AS labels, properties(r) AS rprops, "
                    "d.doc_id AS tid, '' AS name LIMIT $lim", s=sym, lim=EDGE_LIMIT + 1).data()
                axes = s.run(
                    "MATCH (d:Document)-[:MENTIONS]->(e:Entity {symbol:$s}) "
                    "OPTIONAL MATCH (d)-[:IN_NICHE]->(n:Niche) "
                    "RETURN n.id AS niche, count(d) AS n_documents ORDER BY n_documents DESC",
                    s=sym).data()
                derived = {"data_niches": [a for a in axes if a["niche"]],
                           "note": ("ejes POR ENTIDAD derivados del grafo "
                                    "(Document-MENTIONS-Entity + Document-IN_NICHE) — la puerta "
                                    "que /resolve declara nunca servir (LOTE-01·A7)")}
                return _shape("entity", q, _node_props(row["e"]), [], inn, derived)
            # 3) nicho
            row = s.run("MATCH (n:Niche {id:$id}) RETURN n", id=q).single()
            if row:
                inn = s.run(
                    "MATCH (x)-[r]->(n:Niche {id:$id}) "
                    "RETURN type(r) AS rel, labels(x) AS labels, properties(r) AS rprops, "
                    "coalesce(x.doc_id, x.id) AS tid, coalesce(x.name, '') AS name "
                    "LIMIT $lim", id=q, lim=EDGE_LIMIT + 1).data()
                return _shape("niche", q, _node_props(row["n"]), [], inn)
            # 4) base de datos
            row = s.run("MATCH (b:Database {id:$id}) RETURN b", id=q).single()
            if row:
                out = s.run(
                    "MATCH (b:Database {id:$id})-[r]->(x) "
                    "RETURN type(r) AS rel, labels(x) AS labels, properties(r) AS rprops, "
                    "coalesce(x.id, x.doc_id) AS tid, coalesce(x.name, '') AS name "
                    "LIMIT $lim", id=q, lim=EDGE_LIMIT + 1).data()
                inn = s.run(
                    "MATCH (x)-[r]->(b:Database {id:$id}) "
                    "RETURN type(r) AS rel, labels(x) AS labels, properties(r) AS rprops, "
                    "coalesce(x.doc_id, x.id) AS tid, coalesce(x.name, '') AS name "
                    "LIMIT $lim", id=q, lim=EDGE_LIMIT + 1).data()
                return _shape("database", q, _node_props(row["b"]), out, inn)
        return {"found": False, "id": q, "resolution_order": _RESOLUTION_ORDER}
    finally:
        drv.close()


def _shape(kind, node_id, props, out_rows, in_rows, derived=None):
    def _edges(rows):
        edges = []
        for r in rows[:EDGE_LIMIT]:
            if "tid" in r or "labels" in r:   # fila cruda del grafo -> normalizar
                e = {"rel": r["rel"], "kind": (r.get("labels") or ["?"])[0].lower(),
                     "id": r.get("tid")}
                if r.get("name"):
                    e["name"] = r["name"]
                rprops = r.get("rprops") or {}
                if rprops:
                    e["edge_props"] = rprops   # p. ej. verified_tier_weight del MENTIONS (ADR-0041)
            else:                              # fila YA normalizada (backend de archivos)
                e = {k: v for k, v in r.items() if not k.startswith("_")}
            edges.append(e)
        return edges, len(rows) > EDGE_LIMIT

    out_e, out_trunc = _edges(out_rows)
    in_e, in_trunc = _edges(in_rows)
    res = {"found": True, "id": node_id, "kind": kind, "node": props,
           "edges": {"out": out_e, "in": in_e}}
    if out_trunc or in_trunc:
        res["truncated"] = {"out": out_trunc, "in": in_trunc, "edge_limit": EDGE_LIMIT,
                            "note": "hay más aristas que el límite — declarado, no escondido"}
    if derived:
        res["derived"] = derived
    return res


# --------------------------------------------------------------------------- backend: archivos
def _load_sources():
    """Las MISMAS fuentes que alimentan ingest.py, con el MISMO gate estructural."""
    import sys as _sys
    _sys.path.insert(0, str(ROOT / "analysis" / "scripts"))
    from lib.rag_backend import is_approved
    niches = json.loads((RAG / "niches.json").read_text(encoding="utf-8"))["niches"]
    dbs = json.loads((RAG / "databases.json").read_text(encoding="utf-8"))["databases"]
    man = json.loads((RAG / "corpus_manifest.json").read_text(encoding="utf-8"))
    records = [r for r in man.get("records", []) if is_approved(r)]
    return niches, dbs, records


def _files_browse(node_id):
    niches, dbs, records = _load_sources()
    q = node_id

    # 1) documento: dataset (corpus_record_id) o chunk (chunk_id)
    for r in records:
        if r["corpus_record_id"] == q:
            sd = r.get("source_document", {})
            dn = (r.get("axis_data_niche") or {}).get("primary")
            sdb = sd.get("source_db")
            out = []
            if dn and any(n["id"] == dn for n in niches):
                out.append({"rel": "IN_NICHE", "kind": "niche", "id": dn})
            if sdb and any(d["id"] == sdb for d in dbs):
                out.append({"rel": "FROM_DB", "kind": "database", "id": sdb})
            for e in r.get("entities_extracted", []):
                if e.get("entity"):
                    out.append({"rel": "MENTIONS", "kind": "entity", "id": e["entity"],
                                "edge_props": {"verification_tier": e.get("verification_tier")}})
            inn = [{"rel": "HAS_CHUNK", "kind": "document", "id": ch["chunk_id"]}
                   for ch in r.get("chunks", [])][:EDGE_LIMIT]
            props = {"doc_id": q, "type": "dataset", "name": sd.get("name"),
                     "accession": sd.get("accession"), "source_db": sdb, "data_niche": dn}
            return _shape("document", q, props, out, inn)
        for ch in r.get("chunks", []):
            if ch.get("chunk_id") == q:
                props = {"doc_id": q, "type": "chunk", "section": ch.get("section"),
                         "parent": r["corpus_record_id"], "raw_ref": ch.get("raw_ref")}
                out = [{"rel": "PART_OF", "kind": "document", "id": r["corpus_record_id"]}]
                return _shape("document", q, props, out, [])
    # 2) entidad (symbol exacto, luego ensdarg) — derivada del manifest, mismo insumo que el grafo
    menciones, ent_props = [], None
    for r in records:
        for e in r.get("entities_extracted", []):
            sym = e.get("entity")
            g = e.get("store_ensdarg") or (e.get("external_ids_verified") or {}).get("ENSDARG")
            if sym == q or (g and g == q):
                ent_props = ent_props or {"symbol": sym, "ensdarg": g,
                                          "tier": e.get("verification_tier")}
                menciones.append({"rel": "MENTIONS", "kind": "document",
                                  "id": r["corpus_record_id"],
                                  "edge_props": {"verification_tier": e.get("verification_tier")},
                                  "_niche": (r.get("axis_data_niche") or {}).get("primary")})
    if ent_props:
        tally = {}
        for m in menciones:
            n = m.pop("_niche", None)
            if n:
                tally[n] = tally.get(n, 0) + 1
        derived = {"data_niches": [{"niche": n, "n_documents": c}
                                   for n, c in sorted(tally.items(), key=lambda kv: -kv[1])],
                   "note": ("ejes POR ENTIDAD derivados de los MISMOS archivos que alimentan el "
                            "grafo (manifest entities_extracted + axis_data_niche) — la puerta que "
                            "/resolve declara nunca servir (LOTE-01·A7)")}
        return _shape("entity", q, ent_props, [], menciones, derived)
    # 3) nicho
    for n in niches:
        if n["id"] == q:
            docs_in = [{"rel": "IN_NICHE", "kind": "document", "id": r["corpus_record_id"]}
                       for r in records if (r.get("axis_data_niche") or {}).get("primary") == q]
            feeds = [{"rel": "FEEDS", "kind": "database", "id": d["id"], "name": d.get("name", "")}
                     for d in dbs if q in (d.get("feeds_niches") or [])]
            return _shape("niche", q, {"id": q, "name": n.get("name")}, [], docs_in + feeds)
    # 4) base de datos
    for d in dbs:
        if d["id"] == q:
            out = [{"rel": "FEEDS", "kind": "niche", "id": nid}
                   for nid in (d.get("feeds_niches") or [])]
            inn = [{"rel": "FROM_DB", "kind": "document", "id": r["corpus_record_id"]}
                   for r in records
                   if (r.get("source_document") or {}).get("source_db") == q]
            return _shape("database", q, {"id": q, "name": d.get("name"),
                                          "link": d.get("link")}, out, inn)
    return {"found": False, "id": q, "resolution_order": _RESOLUTION_ORDER}


# --------------------------------------------------------------------------- la puerta
def browse_node(node_id):
    """El browse con su marcador in-band: grafo cuando hay NEO4J_URI; caído o ausente -> el
    fallback por archivos, DECLARADO (jamás un 500, jamás un fallback disfrazado de grafo)."""
    node_id = (node_id or "").strip()
    if not node_id:
        return {"found": False, "id": node_id, "browse_mode": "none",
                "browse_error": "id vacío"}
    if os.environ.get("NEO4J_URI"):
        try:
            res = _graph_browse(node_id)
            res.update(browse_mode="graph", browse_error=None)
            return res
        except Exception as e:
            err = f"{type(e).__name__}: {str(e)[:160]}"
            res = _files_browse(node_id)
            res.update(browse_mode="files-fallback", browse_error=err,
                       mode_note=("el grafo está configurado pero FALLÓ — respuesta derivada de "
                                  "los archivos fuente (paridad por construcción); las aristas "
                                  "MENTIONS/tier vienen del manifest, no del grafo vivo"))
            return res
    res = _files_browse(node_id)
    res.update(browse_mode="files-fallback", browse_error=None,
               mode_note=("sin NEO4J_URI (dev/offline): derivado de los MISMOS archivos fuente "
                          "que alimentan el grafo, con el mismo gate estructural (is_approved)"))
    return res
