"""
niche_catalog.py — los nichos de una corrida LEÍDOS del catálogo (2026-09-05, decisión del fundador).

Esto NO juzga: LEE. Cada registro del corpus trae sus dos ejes ya catalogados y aprobados por
gate humano (`approval_chain`: gate `categorization`, approved_by Emmanuel, 2026-06-11):

    axis_data_niche        RN1–RN13 · qué TIPO DE DATO es      (transcriptómica, bioeléctrica, …)
    axis_scientific_domain N1–N6    · a qué CAMPO pertenece    (embriología, señalización, …)

Los dos ejes son ORTOGONALES por decisión ratificada (ADR-0018): uno no se deriva del otro, y el
crosswalk mapea bases→RN*, nunca RN*→N*. Por eso este módulo cuenta cada eje por separado y jamás
infiere uno del otro.

POR QUÉ ESTO ANTES QUE UN JUICIO: pedirle a un modelo que clasifique lo que la ficha ya declara
sustituye una medición por una opinión. Donde el catálogo alcanza, ésta es la respuesta más fuerte
disponible — sale de fichas que un humano aprobó, no de un juez que infiere.

LA COBERTURA VIAJA SIEMPRE. La evidencia de una corrida real es mezcla: registros y chunks del
corpus (CON ficha), PMIDs de literatura y resoluciones de identidad (SIN ficha). En la corrida
9b3140ab sólo 1 de 7 ítems estaba catalogado. Un reparto de nichos sobre 1 de 7 leído sin su
denominador se entiende como el reparto de la corrida entera — que es exactamente el defecto que
ADR-0075 corrigió en `por_nicho` de Consultas del sustrato. Aquí el denominador es primera clase.

PRIMARIO Y SECUNDARIO NO SE SUMAN: la ficha distingue el eje principal de los que el documento
"además toca". Fundirlos inflaría el conteo y borraría la distinción que el catalogador hizo.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "rag_index" / "corpus_manifest.json"

_CACHE = {"mtime": None, "por_id": None}


def _catalogo():
    """El manifest indexado por corpus_record_id, recacheado por mtime. Si no se puede leer, se
    devuelve vacío y el llamador lo DECLARA como cobertura 0 — jamás como 'sin nichos'."""
    try:
        mtime = MANIFEST.stat().st_mtime
    except OSError:
        return {}
    if _CACHE["mtime"] != mtime:
        try:
            man = json.loads(MANIFEST.read_text(encoding="utf-8"))
            _CACHE["por_id"] = {r["corpus_record_id"]: r
                                for r in man.get("records", []) if r.get("corpus_record_id")}
            _CACHE["mtime"] = mtime
        except Exception:
            return {}
    return _CACHE["por_id"] or {}


def _id_de_registro(evidencia_id: str) -> str:
    """`CORPUS-2026-0003#c012` -> `CORPUS-2026-0003`: el chunk hereda la ficha de su registro."""
    return str(evidencia_id or "").split("#", 1)[0].strip()


def _sumar(destino: dict, eje: dict | None):
    """Cuenta un eje de UNA ficha, conservando la distinción primario/secundario."""
    if not isinstance(eje, dict):
        return
    principal = eje.get("primary")
    if principal:
        destino["primary"][principal] = destino["primary"].get(principal, 0) + 1
    for s in eje.get("secondary") or []:
        if s:
            destino["secondary"][s] = destino["secondary"].get(s, 0) + 1


def niches_of_evidence(evidence) -> dict:
    """Ítems de evidencia citados -> los nichos MEDIDOS de los que sí tienen ficha.

    `evidence` es la lista del registro congelado: cada ítem con al menos `id` (y `kind`).
    Devuelve conteos por eje + la cobertura, y la lista de ítems SIN ficha con su tipo, para que
    la ausencia sea legible y no un hueco mudo.
    """
    cat = _catalogo()
    items = [e for e in (evidence or []) if isinstance(e, dict)]
    data = {"primary": {}, "secondary": {}}
    dominio = {"primary": {}, "secondary": {}}
    catalogados, sin_ficha = [], []

    for e in items:
        rid = _id_de_registro(e.get("id"))
        ficha = cat.get(rid)
        if ficha is None:
            sin_ficha.append({"id": e.get("id"), "kind": e.get("kind")})
            continue
        catalogados.append(rid)
        _sumar(data, ficha.get("axis_data_niche"))
        _sumar(dominio, ficha.get("axis_scientific_domain"))

    n = len(items)
    n_cat = len(catalogados)
    return {
        "source": "rag_index/corpus_manifest.json — fichas con gate humano de categorización",
        "class": "medicion",          # se LEE del catálogo; no es juicio de modelo
        "n_evidence": n,
        "n_catalogued": n_cat,
        "coverage": f"{n_cat} de {n}" if n else "0 de 0",
        "catalogued_ids": sorted(set(catalogados)),
        "uncatalogued": sin_ficha,
        "data_niches": data,          # RN1–RN13 · tipo de dato
        "domain_niches": dominio,     # N1–N6 · campo científico
        "note": ("reparto sobre los ítems CATALOGADOS, no sobre toda la evidencia: los PMIDs y las "
                 "resoluciones de identidad no traen ejes y no se les inventa uno. Primario y "
                 "secundario se cuentan aparte — fundirlos borraría la distinción de la ficha."),
    }
