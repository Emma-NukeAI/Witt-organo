"""
consulta_sistema.py — la CONSULTA ABIERTA del sistema (nombrada en ADR-0063, construida en ADR-0070).

El origen: Emmanuel preguntó en producción "dime qué tenemos en data inamovible" y el planner
(correctamente) ruteó la pregunta FUERA del pipeline (store-consultation) — pero nadie la RESPONDÍA:
la card solo daba links a las puertas. Este módulo es la respuesta.

Decisión de mecanismo (ADR-0070, patrón ADR-0062 — el objetivo se entrega, el mecanismo se cambia
con razón): el handoff nombraba "un agente que LEA /status + /taxonomia + manifest y responda en
lenguaje natural". La v1 es **DETERMINISTA, sin modelo**: la clase de pregunta es INVENTARIO
(conteos, versiones, estados, composición) y todas sus respuestas ya existen como datos
estructurados con procedencia — la constitución manda que lo repetible lo haga un ejecutable, y
una respuesta de modelo sin panel no puede verse homologada (la preocupación exacta del handoff).
El resumen en lenguaje natural lo compone CÓDIGO desde plantillas donde cada cifra viene del
snapshot con su fuente. `model_consulted: false` viaja declarado; si el uso real demuestra
preguntas que las plantillas no cubren, la capa de modelo será un ADR aparte (aditivo, medido).

NO-SPEND por construcción: lecturas de archivos + conteos de BD + el /status TTL-cacheado que ya
es NO-SPEND. Cero embeds, cero modelo, cero red nueva.
"""
import datetime
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "rag_index" / "corpus_manifest.json"
NICHES = ROOT / "rag_index" / "niches.json"
QUARANTINE = ROOT / "rag_index" / "curation" / "quarantine"

# ruteo por palabras clave (determinista, declarado): pregunta -> secciones del snapshot
_KEYWORDS = {
    "store": ("store", "inamovible", "identificador", "verificado", "registro", "sha"),
    "indice": ("indice", "índice", "neo4j", "embedding", "vector", "grafo", "semantic"),
    "corpus": ("corpus", "documento", "paper", "dataset", "manifest"),
    "taxonomia": ("taxonomia", "taxonomía", "nicho", "niche"),
    "corridas": ("corrida", "run", "precedente", "pregunta", "cerrad"),
    "config": ("config", "historial", "cambio", "comparab", "modelo", "generaci", "ledger", "bitácora", "bitacora"),
    "curacion": ("curacion", "curación", "cuarentena", "barrido", "sweep", "zfin", "propuesta"),
}


def _now_iso():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def _mtime_iso(path):
    try:
        return datetime.datetime.fromtimestamp(path.stat().st_mtime,
                                               datetime.timezone.utc).isoformat(timespec="seconds")
    except OSError:
        return None


def _config_efectiva():
    """ADR-0081 (I): la configuración EFECTIVA de modelos y el estado del ledger — la MISMA función que sirve
    GET /config-history.current (config_ledger.current) y la MISMA lectura de la tabla (config_ledger.listing),
    para que la consulta del sistema y M6 digan lo mismo. Import perezoso (config_ledger vive en este directorio
    y carga lib.models + db); si no se puede leer, ausencia declarada con la causa — jamás un default copiado."""
    try:
        import config_ledger
        lectura = config_ledger.listing()
        escritor = config_ledger.state_view()
        return {
            "models_effective": config_ledger.current(extra=config_ledger.default_extra()),
            "ledger": {"n_rows": lectura["n_rows"], "last_recorded_at": lectura["last_recorded_at"],
                       "state": lectura["state"] or escritor["state"]},
            "fuente_models": ("lib.models.snapshot() vía config_ledger.current — la MISMA función que "
                              "GET /config-history.current; ledger = tabla config_history (config_ledger.listing)"),
        }
    except Exception as e:
        return {"models_effective": None,
                "ledger": {"n_rows": None, "last_recorded_at": None, "state": f"error: {type(e).__name__}"},
                "fuente_models": f"unavailable: {type(e).__name__}: {str(e)[:120]}"}


def build_snapshot(status, run_tally):
    """El snapshot del sistema: cada sección con su fuente declarada. `status` = el StoreStatus
    NO-SPEND (TTL) de app._store_status; `run_tally` = db.run_state_tally() (conteo, gratis)."""
    snap = {"read_at": _now_iso(), "secciones": {}}

    snap["secciones"]["store"] = {
        "store_version": status.get("store_version"),
        "record_count": status.get("record_count"),
        "sha": status.get("sha"),
        "integrity": status.get("integrity"),
        "fuente": "verified_identifiers.json vía /status (NO-SPEND, TTL)",
    }
    snap["secciones"]["indice"] = {
        "index_state": status.get("index_state"),
        "doc_count": status.get("doc_count"),
        "entity_count": status.get("entity_count"),
        "embed_model": status.get("embed_model"),
        "embed_dim": status.get("embed_dim"),
        "index_version": status.get("index_version"),
        "fuente": "Neo4j (:Meta) + manifest del índice vía /status — OFFLINE = conteos null, jamás inventados",
    }
    try:
        man = json.loads(MANIFEST.read_text(encoding="utf-8"))
        recs = man.get("records", [])
        por_nicho = {}
        for r in recs:
            n = ((r.get("axis_data_niche") or {}).get("primary")) or "sin-nicho"
            por_nicho[n] = por_nicho.get(n, 0) + 1
        # El denominador honesto (ADR-0075). `por_nicho` se venía pintando como si fuera EL reparto del
        # acervo, cuando es el reparto de los registros CATALOGADOS en el manifest — que hoy son una
        # fracción de los documentos indexados. Sin el denominador, un lector concluye "el corpus es
        # 2/3 genómica" de una muestra que no sabe que es muestra. Los dos números ya viven en este
        # mismo snapshot (sección `indice`), así que el arreglo es de lectura, no de datos.
        doc_count = status.get("doc_count")
        cobertura = (f"{len(recs)} de {doc_count}" if isinstance(doc_count, int) and doc_count
                     else f"{len(recs)} (documentos indexados: no consta — índice OFFLINE)")
        snap["secciones"]["corpus"] = {
            "n_records": len(recs),
            "n_docs_indexados": doc_count,
            "cobertura_del_reparto": cobertura,
            "por_nicho": dict(sorted(por_nicho.items(), key=lambda kv: -kv[1])),
            "ultimo_id": recs[-1].get("corpus_record_id") if recs else None,
            "caveat": ("`por_nicho` reparte SÓLO los registros catalogados en el manifest, no todo lo "
                       "indexado: los documentos sin ficha no tienen eje y no aparecen en ninguna barra. "
                       "Léelo como el reparto de lo CATALOGADO, jamás como el reparto del acervo. Y los "
                       "nichos en cero pueden serlo por fase del proyecto (PROJECT_SCOPE) y no por "
                       "descuido — un cero aquí no es, por sí solo, evidencia de hueco"),
            "fuente": {"path": "rag_index/corpus_manifest.json", "mtime": _mtime_iso(MANIFEST)},
        }
    except Exception as e:
        snap["secciones"]["corpus"] = {"state": "unavailable",
                                       "error": f"{type(e).__name__}: {str(e)[:120]}"}
    try:
        niches = json.loads(NICHES.read_text(encoding="utf-8"))
        items = niches.get("niches", niches) if isinstance(niches, dict) else niches
        snap["secciones"]["taxonomia"] = {
            "n_niches": len(items),
            "niches": [n.get("id") for n in items] if isinstance(items, list) else list(items),
            "fuente": {"path": "rag_index/niches.json", "mtime": _mtime_iso(NICHES)},
        }
    except Exception as e:
        snap["secciones"]["taxonomia"] = {"state": "unavailable",
                                          "error": f"{type(e).__name__}: {str(e)[:120]}"}
    snap["secciones"]["corridas"] = {
        "por_estado": run_tally,
        "total": sum(run_tally.values()),
        "cerradas_precedente": run_tally.get("closed", 0),
        "fuente": "tabla runs del backend (conteo por estado — el precedente = cerradas, ADR-0053)",
    }
    hist = ROOT / "rag_index" / "config_history.json"
    try:
        entries = json.loads(hist.read_text(encoding="utf-8")).get("entries", [])
        snap["secciones"]["config"] = {
            "n_cambios": len(entries),
            "ultimo": entries[-1] if entries else None,
            "fuente": {"path": "rag_index/config_history.json", "mtime": _mtime_iso(hist)},
        }
    except Exception as e:
        snap["secciones"]["config"] = {"state": "unavailable",
                                       "error": f"{type(e).__name__}: {str(e)[:120]}"}
    # ADR-0081 (I): el archivo es la clase ATESTIGUADA; la configuración EFECTIVA (models_effective) y la
    # bitácora en BD (ledger) son MEDICIÓN — las tres viajan en la misma sección sin mezclar formas.
    snap["secciones"]["config"].update(_config_efectiva())
    sweeps = sorted(QUARANTINE.glob("*/dataset.json")) if QUARANTINE.exists() else []
    cur = {"n_propuestas_en_cuarentena": len(sweeps), "ultima": None,
           "fuente": "rag_index/curation/quarantine/ (propuestas gateadas, ADR-0068 — NO son la DI)"}
    if sweeps:
        try:
            ult = json.loads(sweeps[-1].read_text(encoding="utf-8"))
            cur["ultima"] = {"sweep_id": ult.get("sweep_id"),
                             "counts": ult.get("counts", {}).get("status_tally"),
                             "n_statements": ult.get("counts", {}).get("n_statements_total")}
        except Exception:
            cur["ultima"] = {"state": "unreadable"}
    snap["secciones"]["curacion"] = cur
    return snap


def _fmt(v):
    return "no consta" if v is None else str(v)


def resumen(snap):
    """El lenguaje natural lo compone CÓDIGO: cada cifra sale del snapshot (lecturas en vivo,
    autofechadas por read_at) — jamás un número sin fuente."""
    s = snap["secciones"]
    st, ix, co, tx, ru, cu, cf = (s.get(k, {}) for k in
                                  ("store", "indice", "corpus", "taxonomia", "corridas", "curacion", "config"))
    partes = [
        f"La DATA INAMOVIBLE tiene {_fmt(st.get('record_count'))} identificadores verificados "
        f"(store_version {_fmt(st.get('store_version'))}).",
        (f"El índice semántico está {_fmt(ix.get('index_state'))}"
         + (f" con {_fmt(ix.get('doc_count'))} documentos y {_fmt(ix.get('entity_count'))} "
            f"entidades en el grafo (embeddings {_fmt(ix.get('embed_model'))}"
            f"/{_fmt(ix.get('embed_dim'))}d)." if ix.get("index_state") == "ONLINE"
            else " — los conteos del grafo no constan (jamás se inventan).")),
        (f"El corpus manifiesta {_fmt(co.get('n_records'))} registros"
         + (f", el más reciente {co['ultimo_id']}" if co.get("ultimo_id") else "")
         + (f", repartidos en {len(co.get('por_nicho', {}))} nichos con datos "
            f"(de {_fmt(tx.get('n_niches'))} en la taxonomía)." if co.get("por_nicho") else ".")),
        (f"Corridas: {_fmt(ru.get('total'))} en total; {_fmt(ru.get('cerradas_precedente'))} "
         f"cerradas (el corpus de precedente)."),
        (f"Curación en cuarentena: {_fmt(cu.get('n_propuestas_en_cuarentena'))} propuesta(s) "
         f"esperando el gate humano." if cu.get("n_propuestas_en_cuarentena") else
         "Curación en cuarentena: ninguna propuesta pendiente."),
    ]
    # ADR-0081: la generación de modelos EFECTIVA y sus avisos medidos (retiro, env inválida) — cifras del
    # mismo snapshot (models_effective), nunca una constante; sin snapshot, se declara que no consta.
    me = cf.get("models_effective") if isinstance(cf, dict) else None
    if isinstance(me, dict):
        n_av = len(me.get("warnings") or [])
        partes.append(f"Modelos: generación {_fmt(me.get('generation'))} (firma del panel "
                      f"{_fmt(me.get('panel_signature'))}); "
                      + (f"{n_av} aviso(s) de configuración." if n_av else "sin avisos de configuración.")
                      + f" Bitácora de configuración: {_fmt((cf.get('ledger') or {}).get('state'))}.")
    else:
        partes.append("Modelos: la configuración efectiva no consta (config_ledger no disponible).")
    return " ".join(partes)


def answer(q, status, run_tally):
    """La respuesta de la consulta abierta: snapshot (filtrado por ruteo de palabras clave cuando
    q trae señal; completo cuando no — y el no-match se DECLARA) + resumen compuesto por código +
    la declaración estructural de que el modelo NO se consultó."""
    snap = build_snapshot(status, run_tally)
    q_norm = (q or "").lower()
    matched = sorted({sec for sec, kws in _KEYWORDS.items()
                      if any(kw in q_norm for kw in kws)}) if q_norm.strip() else []
    out = {
        "q": q or None,
        "q_matched_sections": matched or None,
        "answer_class": "deterministic-inventory",
        "model_consulted": False,
        "resumen": resumen(snap),
        "snapshot": (snap if not matched else
                     {"read_at": snap["read_at"],
                      "secciones": {k: v for k, v in snap["secciones"].items() if k in matched}}),
        "note": ("v1 determinista (ADR-0070): la clase de pregunta es INVENTARIO y sus respuestas "
                 "existen como datos con procedencia — el modelo NO se consulta (una respuesta de "
                 "modelo sin panel no puede verse homologada). Pregunta sin match de sección = "
                 "snapshot completo con q_matched_sections null, declarado."),
    }
    return out
