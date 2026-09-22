"""smoke_attestations_db.py — gate offline de la TABLA de imágenes atestiguadas (ADR-0086, rebanada F5a: db.py).

Lo que mide, con la base REAL (SQLite temporal) y el pipeline REAL de la biblioteca:
  * la tabla nace por `create_all` (CERO ALTER) y su estado se declara ('ready' | 'table-missing');
  * la fila guarda IDENTIDAD y PROCEDENCIA y NINGÚN byte: ni b64, ni ruta absoluta del almacén;
  * subir dos veces el MISMO archivo al MISMO plan no crea dos identidades (UNIQUE plan+sha);
  * el orden de lectura es el de subida — el MISMO que verá el panel;
  * adjuntar es la compuerta humana: hasta que el ledger la sella, la imagen no está adjunta;
  * RETIRAR es una lápida: la fila permanece (identidad, procedencia y decisión), el estado lo dice, es idempotente y
    una imagen retirada ya no se adjunta;
  * la cascada encuentra las copias heredadas por otros planes;
  * el tope por persona y día se puede medir; el agregado de uso cuenta filas y bytes, jamás proyecta.

100% offline: cero red (urlopen bloqueado y contado), cero modelo, base y almacén en tempdir. Exit 0 = todo PASS.

Corre:  python rag_index/query_service/smoke_attestations_db.py
"""
import datetime
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

TMP = Path(tempfile.mkdtemp(prefix="witt-attested-db-"))
os.environ.setdefault("NEO4J_URI", "")
os.environ.setdefault("RAG_BACKEND", "sparse")
os.environ.setdefault("OPENAI_API_KEY", "")
os.environ.setdefault("ANTHROPIC_API_KEY", "")
os.environ.setdefault("MINIO_ENDPOINT", "")
os.environ.setdefault("WITT_RUN_ORIGIN", "smoke")
os.environ["WITT_BACKEND_DB_URL"] = "sqlite:///" + str(TMP / "attested.db").replace("\\", "/")
os.environ["WITT_ATTESTED_DIR"] = str(TMP / "store")

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "analysis" / "scripts"))
sys.path.insert(0, str(HERE))

import urllib.request as _urlreq  # noqa: E402

_NET_CALLS = []
_urlopen_real = _urlreq.urlopen


def _urlopen_blocked(*a, **kw):
    _NET_CALLS.append(str((a[0] if a else kw.get("url")))[:120])
    raise RuntimeError("network blocked by smoke_attestations_db (offline gate)")


_urlreq.urlopen = _urlopen_blocked

import db  # noqa: E402
from lib import attestations as at  # noqa: E402

CHECKS = []


def check(name, cond, detail=""):
    CHECKS.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + name + (("  -> " + detail) if detail else ""))


CFG = at.env_config(env={"WITT_ATTESTED_DIR": str(TMP / "store")})
STORAGE, PROBE = at.storage_backend(cfg=CFG)
FX = at.synthetic_fixtures()
FORM = {"caption": "micrografía de pronefros de pez cebra a 48 hpf", "consent_declared": "true",
        "consent_kind": "own-work", "license_declared": "all-rights-reserved", "share_scope": "author-only",
        "third_party_processing_acknowledged": "true", "patient_material": "false", "deidentified_declared": "false"}


def _fila(plan_id, fixture, quien="natalia", cuando=None, **form_over):
    """Una fila REAL: el mismo camino que la puerta de subida (validar → quitar metadatos → identidad → guardar)."""
    ok, err = at.validate_form({**FORM, **form_over}, cfg=CFG)
    assert err is None, err
    st = at.strip_metadata(fixture, media_type=at.sniff_mime(fixture), mode="strip")
    b, err_b = at.validate_bytes(st["data"], cfg=CFG)
    assert err_b is None, err_b
    ident = at.identity(st["data"], fixture)
    put = STORAGE.put(plan_id, ident["sha256"], st["data"], b["media_type"])
    at_ = cuando or datetime.datetime.now(datetime.timezone.utc).isoformat()
    return at.build_row(plan_id, ok, b, st, ident, put, uploaded_by=quien, uploaded_by_role="scientist", uploaded_at=at_)


# ====================================================================================================
print("\n# 1. la tabla nace sola y declara su estado")
# ====================================================================================================
db.init_db()
check("la tabla existe tras init_db (create_all: migración ADITIVA, CERO ALTER sobre tablas existentes)",
      db.attested_schema_state() == "ready", db.attested_schema_state())
check("el nombre de la tabla y su índice por plan están declarados en el módulo",
      db.ATTESTED_IMAGES_TABLE == "plan_attested_images" and hasattr(db, "plan_attested_images"))

# ====================================================================================================
print("\n# 2. la fila guarda identidad y procedencia — ningún byte")
# ====================================================================================================
R1 = _fila("plan-a", FX["png_text.png"])
check("insert de una imagen nueva", db.attested_image_insert(R1) is True)
leida = db.attested_image_get("plan-a", R1["sha256"])
check("la fila leída trae identidad (los dos sha y los dos tamaños), procedencia (quién, cuándo, consentimiento, "
      "licencia, alcance) y el estado de sus metadatos",
      leida and leida["sha256"] == R1["sha256"] and leida["sha256_received"] == R1["sha256_received"]
      and leida["uploaded_by"] == "natalia" and leida["consent_kind"] == "own-work"
      and leida["license_declared"] == "all-rights-reserved" and leida["share_scope"] == "author-only"
      and isinstance(leida["exif_state"], str) and leida["bytes"] > 0)
crudo = json.dumps(leida, ensure_ascii=False, default=str)
check("NINGÚN byte de imagen en la fila: ni b64, ni data:image, ni la ruta absoluta del almacén",
      "data:image" not in crudo and str(TMP).replace("\\", "/") not in crudo.replace("\\", "/")
      and "b64" not in leida)
check("los booleanos son booleanos y las fechas viajan en ISO (la webapp no adivina tipos)",
      leida["patient_material"] is False and leida["consent_declared"] is True
      and isinstance(leida["uploaded_at"], str) and leida["uploaded_at"].count("-") >= 2)
check("subir DOS VECES el mismo archivo al mismo plan no crea dos identidades (UNIQUE plan+sha)",
      db.attested_image_insert(R1) is False and len(db.attested_images_of_plan("plan-a")) == 1)

R2 = _fila("plan-a", FX["jpeg_exif_mpf_com.jpg"],
           cuando=(datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=30)).isoformat())
db.attested_image_insert(R2)
check("dos imágenes distintas conviven y se leen EN ORDEN DE SUBIDA (el mismo que verá el panel)",
      [r["sha256"] for r in db.attested_images_of_plan("plan-a")] == [R1["sha256"], R2["sha256"]])
check("las de otro plan no se mezclan", db.attested_images_of_plan("plan-b") == [])

# ====================================================================================================
print("\n# 3. adjuntar es la compuerta humana")
# ====================================================================================================
check("recién subida NO está adjunta: hasta que el ledger la sella, no entra a ninguna corrida",
      db.attested_images_of_plan("plan-a", attached_only=True) == []
      and db.attested_image_get("plan-a", R1["sha256"])["ledger_state"] == "staged")
check("adjuntar sella el destino, quién y cuándo",
      db.attested_image_attach("plan-a", R1["sha256"], "knowledge_now", by="natalia") is True)
a1 = db.attested_image_get("plan-a", R1["sha256"])
check("la fila adjunta lo declara: attached_to, attached_by, attached_at y ledger_state",
      a1["attached_to"] == "knowledge_now" and a1["attached_by"] == "natalia"
      and isinstance(a1["attached_at"], str) and a1["ledger_state"] == "attached"
      and len(db.attested_images_of_plan("plan-a", attached_only=True)) == 1)
check("adjuntar a un requisito del consejo guarda su identificador",
      db.attested_image_attach("plan-a", R2["sha256"], "requirement", requirement_id="req-fff", by="natalia")
      and db.attested_image_get("plan-a", R2["sha256"])["requirement_id"] == "req-fff")

# ====================================================================================================
print("\n# 4. retirar es una LÁPIDA, no un borrado")
# ====================================================================================================
check("retirar marca la fila y devuelve True", db.attested_image_withdraw("plan-a", R2["sha256"], "natalia",
                                                                          "subí la imagen equivocada") is True)
w = db.attested_image_get("plan-a", R2["sha256"])
check("la fila SIGUE existiendo: identidad, procedencia, decisión y razón del retiro se conservan — el registro es "
      "inmutable; lo que se va son los bytes",
      w is not None and w["sha256"] == R2["sha256"] and w["uploaded_by"] == "natalia"
      and w["withdrawn_by"] == "natalia" and w["withdraw_reason"] == "subí la imagen equivocada"
      and isinstance(w["withdrawn_at"], str) and w["storage_state"] == "withdrawn (tombstone)")
check("retirar dos veces no re-escribe la lápida (idempotente)",
      db.attested_image_withdraw("plan-a", R2["sha256"], "otra", "otra razón") is False
      and db.attested_image_get("plan-a", R2["sha256"])["withdraw_reason"] == "subí la imagen equivocada")
check("una imagen retirada ya NO se puede adjuntar",
      db.attested_image_attach("plan-a", R2["sha256"], "knowledge_now", by="natalia") is False)
check("las vivas se pueden pedir aparte de las retiradas (0 ≠ ausente: las dos listas se miden)",
      len(db.attested_images_of_plan("plan-a")) == 2
      and len(db.attested_images_of_plan("plan-a", include_withdrawn=False)) == 1)

# --- cascada: lo que otro plan heredó -------------------------------------------------------------
R3 = _fila("plan-hijo", FX["png_text.png"])
R3 = {**R3, "inherited_from_plan_id": "plan-a", "inherited_from_run_id": "run-1", "ledger_state": "inherited"}
db.attested_image_insert(R3)
check("la copia heredada por otro plan se encuentra por su origen (la cascada del retiro la alcanza)",
      [r["plan_id"] for r in db.attested_images_inherited_from("plan-a", R1["sha256"])] == ["plan-hijo"])
db.attested_image_withdraw("plan-hijo", R1["sha256"], "natalia", "cascada desde plan-a", cascade_n=1)
check("tras retirar la heredada, la cascada ya no la lista y su conteo queda declarado",
      db.attested_images_inherited_from("plan-a", R1["sha256"]) == []
      and db.attested_image_get("plan-hijo", R1["sha256"])["withdraw_cascade_n"] == 1)

# ====================================================================================================
print("\n# 5. topes y uso: conteos MEDIDOS, jamás proyecciones")
# ====================================================================================================
ayer = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=1)
manana = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=1)
check("el tope por persona y día se puede medir (cuántas subió desde un instante dado)",
      db.attested_images_uploaded_today("natalia", ayer) == 3
      and db.attested_images_uploaded_today("natalia", manana) == 0
      and db.attested_images_uploaded_today("otra-persona", ayer) == 0)
u = db.attested_images_usage()
check("el agregado de uso cuenta filas, bytes, retiradas, adjuntas y material de paciente — todo MEDIDO. Una imagen "
      "retirada CONSERVA su adjunción: el registro dice lo que pasó, no lo que quedó (por eso adjuntas = 2 con una retirada)",
      u["n_images"] == 3 and u["bytes_stored_total"] > 0 and u["n_withdrawn"] == 2 and u["n_attached"] == 2
      # (corrector A9) «vivas» y «todas» son dos mediciones distintas y ahora cada una tiene su nombre: antes el bloque
      # decía «sobre las filas vivas» y contaba también las retiradas, con bytes de archivos que ya no existen
      and u["n_live"] == u["n_images"] - u["n_withdrawn"] and u["bytes_live_total"] < u["bytes_stored_total"]
      and "n_live y bytes_live_total" in u["class"]
      and u["n_patient_material"] == 0 and "medición" in u["class"], json.dumps(u, ensure_ascii=False))
check("el agregado se puede acotar a unos planes (el reporte por ventana no inventa filas de otros)",
      db.attested_images_usage(plan_ids=["plan-hijo"])["n_images"] == 1
      and db.attested_images_usage(plan_ids=["plan-inexistente"])["n_images"] == 0)

# ====================================================================================================
print("\n# cierre")
# ====================================================================================================
check("el gate corrió 100% OFFLINE — MEDIDO: urlopen bloqueado y contado == 0", _NET_CALLS == [], str(_NET_CALLS[:3]))
_urlreq.urlopen = _urlopen_real
try:
    db.engine().dispose()
except Exception:
    pass
shutil.rmtree(TMP, ignore_errors=True)

npass = sum(CHECKS)
print("\n== %d/%d PASS ==" % (npass, len(CHECKS)))
sys.exit(0 if npass == len(CHECKS) else 1)
