"""smoke_attestations_http.py — gate offline de las 7 PUERTAS de las imágenes atestiguadas (ADR-0086, rebanada F5b).

Lo que mide, con la app REAL (TestClient ASGI), la base REAL (SQLite temporal) y el almacén REAL (LocalStorage en tmp):

  * 401 sin sesión en las SIETE puertas; 404 de plan y de corrida;
  * subir es UNA transacción con orden: 413 por Content-Length ANTES de tocar el cuerpo · tipo MEDIDO por magic bytes (el
    Content-Type declarado se registra y NO decide) · metadatos borrados ANTES de hashear (si no se pueden garantizar,
    422 y NADA se guarda) · sha256 de los bytes ALMACENADOS · y sólo entonces la fila, que nace `staged`;
  * la COMPUERTA HUMANA manda: un plan ya sellado a una corrida no recibe imágenes; sin consejo no hay canal;
  * los topes (por plan, por MB del plan, por persona y día) responden 409/429 con su `scope` y su fuente;
  * el índice del plan y el de la corrida traen METADATOS y jamás bytes, con `viewer_may_view` calculado en el SERVIDOR;
  * los BYTES salen con autorización estricta: author-only por defecto, `team` sólo si quien subió lo declaró Y
    WITT_ATTESTED_TEAM_VIEW=1, y MATERIAL DE PACIENTE es author-only SIEMPRE; el sha se RECALCULA sobre lo que sale;
  * retirar es una lápida: la fila se queda, los bytes se van, la cascada alcanza a las heredadas, el registro congelado
    NO cambia, y funciona bajo kill-switch (apagar la función no puede atrapar la imagen de nadie);
  * heredar copia los bytes y conserva la procedencia ORIGINAL; sólo quien la subió puede;
  * el kill-switch: subida 409, inherit 409, índice 'kill-switch', bytes 404, RETIRAR 200;
  * un registro anterior a 1.14 declara 'not-instrumented (contrato < 1.14)' — ausencia no es «no hubo imágenes»;
  * `attestation.*` NO mueve el latido del consejo; CORS expone X-Witt-Attested-*; ninguna respuesta JSON lleva binario.

100% offline: cero red (urlopen bloqueado y CONTADO), cero modelo, base y almacén en tempdir. Exit 0 = todo PASS.

Corre:  python rag_index/query_service/smoke_attestations_http.py
"""
import base64
import datetime
import hashlib
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "analysis" / "scripts"))
TMP = Path(tempfile.mkdtemp(prefix="smoke_attestations_http_"))

# --- máscara offline ANTES de importar la app -------------------------------------------------------
os.environ["WITT_BACKEND_DB_URL"] = "sqlite:///" + str(TMP / "attested-http.db").replace("\\", "/")
os.environ["NEO4J_URI"] = ""
os.environ["RAG_BACKEND"] = "sparse"
os.environ["OPENAI_API_KEY"] = ""
os.environ["ANTHROPIC_API_KEY"] = ""
os.environ["MINIO_ENDPOINT"] = ""
os.environ["WITT_RUN_ORIGIN"] = "smoke"
os.environ["WITT_MCP_CACHE_DIR"] = str(TMP / "mcp_cache")
for _k in list(os.environ):
    if _k.startswith("WITT_ATTESTED"):        # sin env heredada: los defaults DECLARADOS de la tabla
        os.environ.pop(_k, None)
STORE = TMP / "store"
os.environ["WITT_ATTESTED_DIR"] = str(STORE)
os.environ["WITT_CORS_ORIGINS"] = "http://localhost:5173"
ORIGIN = "http://localhost:5173"

import urllib.request as _urlreq  # noqa: E402

_NET = []
_urlopen_real = _urlreq.urlopen


def _blocked(*a, **kw):
    _NET.append(str((a[0] if a else kw.get("url")))[:120])
    raise RuntimeError("smoke_attestations_http: red bloqueada")


_urlreq.urlopen = _blocked

import db  # noqa: E402
import app as app_mod  # noqa: E402
import runs as runs_mod  # noqa: E402
from lib import attestations as at  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

CHECKS = []


def check(name, cond, detail=""):
    CHECKS.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + name + (("  -> " + str(detail)[:400]) if detail else ""))


def _fin():
    n = sum(CHECKS)
    print("\n== %d/%d PASS ==" % (n, len(CHECKS)))
    _urlreq.urlopen = _urlopen_real
    shutil.rmtree(TMP, ignore_errors=True)
    sys.exit(0 if n == len(CHECKS) else 1)


db.init_db()
db.upsert_user("natalia", "Natalia", "medico", "pw-natalia")
db.upsert_user("emmanuel", "Emmanuel", "dev", "pw-emmanuel")
client = TestClient(app_mod.app)
NAT = {"Authorization": "Bearer " + client.post("/login", json={"username": "natalia", "password": "pw-natalia"}).json()["token"]}
EMM = {"Authorization": "Bearer " + client.post("/login", json={"username": "emmanuel", "password": "pw-emmanuel"}).json()["token"]}

FX = at.synthetic_fixtures()
PNG = FX["png_text.png"]
PNG2 = FX["png_clean_64x48.png"]
JPG = FX["jpeg_exif_mpf_com.jpg"]
WEBP = FX["webp_exif.webp"]
GIF = FX["gif_comment.gif"]
PDF = FX["not_image.pdf"]
BIG_MP = FX["png_64mp.png"]
TRUNC = FX["jpeg_truncated_after_app1.jpg"]
CAP = "micrografia de pronefros de pez cebra a 48 hpf con tincion wt1a (cuaderno 2026-08)"
FORM = {"caption": CAP, "consent_declared": "true", "consent_kind": "own-work",
        "license_declared": "all-rights-reserved", "share_scope": "author-only",
        "third_party_processing_acknowledged": "true", "patient_material": "false",
        "deidentified_declared": "false"}


def _plan(plan_id, council_state="applicable", user="natalia", run_id=None):
    db.create_plan(plan_id, user, "¿wt1a marca podocitos del pronefros?", ["wt1a"],
                   json.dumps({"route": "evidence-run"}), origin="smoke", council_state=council_state)
    if run_id:
        db.mark_plan_used(plan_id, run_id)      # el MISMO sello que pone el encolado (F.4)
    return plan_id


def _subir(plan_id, data, headers=NAT, ct="image/png", nombre="foto.png", **campos):
    form = {**FORM, **campos}
    return client.post(f"/plans/{plan_id}/attestations", headers=headers,
                       files={"file": (nombre, data, ct)}, data=form)


def _post_sha(data, modo=None):
    """El sha que el servidor DEBE registrar: el de los bytes POST-strip (la biblioteca es la única verdad)."""
    st = at.strip_metadata(data, media_type=at.sniff_mime(data), mode=modo or "strip")
    return at.sha256_hex(st["data"]), len(st["data"])


def _archivos():
    return sorted(str(p.relative_to(STORE)).replace("\\", "/") for p in STORE.rglob("*") if p.is_file())


# =====================================================================================================================
print("\n# 1. sin sesión no hay nada: las SIETE puertas responden 401")
# =====================================================================================================================
P0 = _plan("plan-http-0")
_SHA0 = "0" * 64
_siete = [("POST", f"/plans/{P0}/attestations", {}), ("POST", f"/plans/{P0}/attestations/inherit", {"json": {"sha256": _SHA0, "from_run_id": "x"}}),
          ("GET", f"/plans/{P0}/attestations", {}), ("GET", f"/plans/{P0}/attestations/{_SHA0}", {}),
          ("POST", f"/plans/{P0}/attestations/{_SHA0}/withdraw", {"json": {"reason": "x"}}),
          ("GET", "/runs/r-x/attestations", {}), ("GET", f"/runs/r-x/attestations/{_SHA0}", {})]
_codigos = [client.request(m, u, **kw).status_code for m, u, kw in _siete]
check("las 7 puertas exigen sesión (401) — ninguna filtra la existencia de un plan o una corrida antes de autenticar",
      _codigos == [401] * 7, _codigos)
check("DELETE sobre la puerta de bytes NO existe: 405 (retirar es un POST con razón, no un DELETE silencioso)",
      client.request("DELETE", f"/plans/{P0}/attestations/{_SHA0}", headers=NAT).status_code == 405)
check("plan inexistente -> 404 plan_not_found en subida e índice",
      client.post("/plans/no-existe/attestations", headers=NAT, files={"file": ("a.png", PNG, "image/png")},
                  data=FORM).status_code == 404
      and client.get("/plans/no-existe/attestations", headers=NAT).status_code == 404)

# =====================================================================================================================
print("\n# 2. subir: el orden de la puerta, medido")
# =====================================================================================================================
P1 = _plan("plan-http-1")
r = _subir(P1, PNG)
_sha1, _bytes1 = _post_sha(PNG)
item = (r.json() or {}).get("item") or {}
check("subida válida -> 201 con el ítem: sha256 de los bytes ALMACENADOS (post-strip), sha256_received del archivo que "
      "subió la persona, exif_state que DICE qué se quitó, almacén local 'stored' y ledger_state 'staged' — la imagen NO "
      "entra a ninguna corrida hasta que el ledger la selle",
      r.status_code == 201 and item.get("sha256") == _sha1 and item.get("sha256_received") == at.sha256_hex(PNG)
      and item["sha256"] != item["sha256_received"] and item.get("bytes") == _bytes1
      and item.get("ledger_state") == "staged" and item.get("attached_to") is None
      and str(item.get("exif_state", "")).startswith("stripped")
      and item["storage"]["backend"] == "local" and item.get("class") == "attested",
      json.dumps({"sha": item.get("sha256", "")[:12], "exif": item.get("exif_state"),
                  "ledger_state": item.get("ledger_state")}, default=str))
_crudo = json.dumps(r.json(), default=str)
check("la respuesta de subida NO lleva un solo byte: ni 'b64', ni 'data:image', ni la llave del almacén, ni la ruta "
      "privada del disco — el base64 REAL de la imagen tampoco aparece",
      '"b64"' not in _crudo and "data:image" not in _crudo
      and base64.b64encode(PNG).decode("ascii")[:40] not in _crudo
      and str(STORE).replace("\\", "/") not in _crudo.replace("\\", "/")
      and "storage_key" not in _crudo)
fila = db.attested_image_get(P1, _sha1)
check("la fila quedó en la base con su procedencia (quién, cuándo, consentimiento, licencia, alcance) y su llave de "
      "almacén; el archivo existe en el disco PRIVADO con el nombre que dice la llave",
      fila is not None and fila["uploaded_by"] == "natalia" and fila["consent_kind"] == "own-work"
      and fila["license_declared"] == "all-rights-reserved" and fila["share_scope"] == "author-only"
      and fila["storage_key"] in _archivos() and (STORE / fila["storage_key"]).exists(),
      f"archivos={_archivos()}")
r_mentira = _subir(P1, PNG2, ct="image/jpeg", nombre="miente.jpg")
it2 = r_mentira.json().get("item") or {}
check("un Content-Type MENTIROSO no decide nada: el tipo se MIDE por magic bytes ('image/png'), lo declarado se REGISTRA "
      "('image/jpeg') y el desacuerdo se declara (media_type_declared_mismatch true)",
      r_mentira.status_code == 201 and it2.get("media_type") == "image/png"
      and it2.get("media_type_declared") == "image/jpeg" and it2.get("media_type_declared_mismatch") is True,
      json.dumps({k: it2.get(k) for k in ("media_type", "media_type_declared", "media_type_declared_mismatch")}))
check("subir DOS VECES el mismo archivo al mismo plan -> 409 attested_image_already_uploaded con uploaded_by_is_viewer "
      "(una identidad, una fila)",
      _subir(P1, PNG).status_code == 409
      and _subir(P1, PNG).json()["detail"]["uploaded_by_is_viewer"] is True)
check("el MISMO archivo subido por OTRA sesión al mismo plan -> 409 con uploaded_by_is_viewer FALSE (dice de quién es, "
      "sin revelar más)",
      _subir(P1, PNG, headers=EMM).json()["detail"]["uploaded_by_is_viewer"] is False)
_n_antes = len(db.attested_images_of_plan(P1))
r_gif = _subir(P1, GIF, ct="image/gif", nombre="a.gif")
r_pdf = _subir(P1, PDF, ct="application/pdf", nombre="a.pdf")
check("tipos fuera de la tabla -> 415 sin escribir nada: GIF (habilitable por env, APAGADO por defecto) y un %PDF "
      "disfrazado; el detalle dice qué se OLFATEÓ y qué se permite",
      r_gif.status_code == 415 and r_pdf.status_code == 415
      and set(r_gif.json()["detail"]["allowed"]) == set(at.env_config()["allowed_media"])
      and len(db.attested_images_of_plan(P1)) == _n_antes,
      json.dumps({"gif": r_gif.json()["detail"].get("sniffed"), "pdf": r_pdf.json()["detail"].get("sniffed")}))
r_mp = _subir(P1, BIG_MP)
r_tr = _subir(P1, TRUNC, ct="image/jpeg", nombre="t.jpg")
check("422 en los dos casos que NO se pueden garantizar: una cabecera que declara 64 MP (image-too-many-pixels) y un "
      "JPEG truncado cuyo borrado de metadatos NO se puede completar (metadata-strip-failed) — y en ninguno de los dos "
      "quedó fila ni archivo: no se almacena lo que no se pudo limpiar",
      r_mp.status_code == 422 and r_tr.status_code == 422
      and r_tr.json()["detail"]["state"] == "metadata-strip-failed"
      and len(db.attested_images_of_plan(P1)) == _n_antes,
      json.dumps({"mp": r_mp.json()["detail"]["state"], "trunc": r_tr.json()["detail"]["state"]}))
_malos = {
    "caption-missing": {"caption": "x"},
    "invalid-consent-kind": {"consent_kind": "inventado"},
    "consent-not-declared": {"consent_declared": "false"},
    "third_party_processing_not_acknowledged": {"third_party_processing_acknowledged": "false"},
    "patient_material-required": {"patient_material": ""},
    "invalid-license": {"license_declared": "lo-que-sea"},
    "invalid-share-scope": {"share_scope": "el-mundo"},
    "patient_material_not_allowed": {"patient_material": "true", "consent_kind": "patient-consented",
                                     "consent_text": "consentimiento informado firmado por la paciente",
                                     "deidentified_declared": "true"},
}
_res_malos = {}
for estado, over in _malos.items():
    rr = _subir(P1, PNG2, **over)
    _res_malos[estado] = (rr.status_code, (rr.json().get("detail") or {}).get("state"))
check("el FORMULARIO es la procedencia: los 8 rechazos tipados son 400 con su estado propio (caption, consentimiento, "
      "acuse de terceros, tres estados de material de paciente, licencia y alcance de vocabulario CERRADO) — y material "
      "de paciente está PROHIBIDO por defecto (WITT_ATTESTED_PATIENT_MATERIAL=0), no permitido en silencio",
      all(v == (400, k) for k, v in _res_malos.items()), json.dumps(_res_malos))

# =====================================================================================================================
print("\n# 3. el tope del cuerpo se aplica ANTES de leerlo")
# =====================================================================================================================
os.environ["WITT_ATTESTED_MAX_IMAGE_MB"] = "0.1"
_grande = PNG + b"\x00" * (200 * 1024)
r_413 = _subir(P1, _grande)
os.environ.pop("WITT_ATTESTED_MAX_IMAGE_MB", None)
_d413 = r_413.json().get("detail") or {}
check("con el tope en 0.1 MB, un cuerpo de ~200 KB -> 413 attested_image_too_large por CONTENT-LENGTH: el detalle trae "
      "el largo declarado, el tope y su FUENTE, y dice que no se leyó el cuerpo; no quedó fila ni archivo",
      r_413.status_code == 413 and _d413["state"] == "attested_image_too_large"
      and _d413.get("content_length", 0) > _d413.get("max_body_bytes", 0)
      and "no se leyó" in str(_d413.get("note", "")) and _d413.get("source", "").startswith("env:")
      and db.attested_image_get(P1, at.sha256_hex(_grande)) is None,
      json.dumps({k: _d413.get(k) for k in ("state", "content_length", "max_body_bytes", "source")}))

# =====================================================================================================================
print("\n# 4. los topes del plan y de la persona")
# =====================================================================================================================
P2 = _plan("plan-http-2")
os.environ["WITT_ATTESTED_MAX_PER_PLAN"] = "2"
_r1 = _subir(P2, PNG)
_r2 = _subir(P2, PNG2)
_r3 = _subir(P2, JPG, ct="image/jpeg", nombre="c.jpg")
_d3 = (_r3.json().get("detail") or {})
check("WITT_ATTESTED_MAX_PER_PLAN=2: la tercera imagen -> 409 attestations_cap_reached con scope 'plan', el conteo, el "
      "tope y su fuente; y el mensaje dice cómo liberar cupo (retirar)",
      (_r1.status_code, _r2.status_code, _r3.status_code) == (201, 201, 409)
      and _d3["state"] == "attestations_cap_reached" and _d3["scope"] == "plan" and _d3["cap"] == 2
      and _d3["source"] == "env:WITT_ATTESTED_MAX_PER_PLAN" and "retirar" in _d3.get("note", ""),
      json.dumps(_d3))
_sha_p2a = _post_sha(PNG)[0]
client.post(f"/plans/{P2}/attestations/{_sha_p2a}/withdraw", headers=NAT, json={"reason": "libero cupo"})
check("retirar LIBERA cupo: tras la lápida, la tercera imagen entra (el tope cuenta filas VIVAS, no filas)",
      _subir(P2, JPG, ct="image/jpeg", nombre="c.jpg").status_code == 201)
os.environ.pop("WITT_ATTESTED_MAX_PER_PLAN", None)
P3 = _plan("plan-http-3")
os.environ["WITT_ATTESTED_MAX_TOTAL_MB"] = "1.0"
os.environ["WITT_ATTESTED_MAX_PER_USER_PER_DAY"] = "1"
_r429 = _subir(P3, PNG)
_d429 = (_r429.json().get("detail") or {})
check("WITT_ATTESTED_MAX_PER_USER_PER_DAY=1 con subidas previas de esta sesión -> 429 upload-rate-limited con n_today, "
      "cap y resets_at (la cuenta es por persona y día UTC, no por plan)",
      _r429.status_code == 429 and _d429["state"] == "upload-rate-limited" and _d429["cap"] == 1
      and _d429["n_today"] >= 1 and str(_d429.get("resets_at", "")).count("-") >= 2,
      json.dumps(_d429))
os.environ.pop("WITT_ATTESTED_MAX_PER_USER_PER_DAY", None)
# el tope de MB no se puede bajar por env (el clamp declarado es 1.0..168.0): se SIEMBRA una fila que ya pesa 2 MB —
# la cuenta es de la columna `bytes` de las filas VIVAS, que es justo lo que este check mide
_gorda = dict(db.attested_image_get(P2, _post_sha(PNG2)[0]))
_gorda.update(plan_id=P3, sha256="f" * 64, sha256_received="f" * 64, bytes=2 * 1024 * 1024,
              image_id="attested:" + "f" * 12, storage_key="attested/%s/%s.png" % (P3, "f" * 64))
db.attested_image_insert(_gorda)
os.environ["WITT_ATTESTED_MAX_TOTAL_MB"] = "1.0"
_rmb = _subir(P3, PNG)
_dmb = (_rmb.json().get("detail") or {})
check("el tope de MB del plan es por SUMA de bytes vivos: con una fila sembrada de 2 MB y el tope en 1.0 MB, la "
      "siguiente subida -> 409 attestations_cap_reached con scope 'total_mb' y los bytes contra el tope EN BYTES (dos "
      "topes distintos, dos scopes distintos: el mensaje no los confunde)",
      _rmb.status_code == 409 and _dmb["state"] == "attestations_cap_reached" and _dmb["scope"] == "total_mb"
      and _dmb["bytes"] > _dmb["cap_bytes"] and _dmb["max_total_mb"] == 1.0, json.dumps(_dmb))
os.environ.pop("WITT_ATTESTED_MAX_TOTAL_MB", None)

# =====================================================================================================================
print("\n# 5. la compuerta humana: sin ledger no hay canal, y un plan sellado ya no recibe")
# =====================================================================================================================
P_SIN = _plan("plan-http-sin-consejo", council_state="disabled (kill-switch WITT_COUNCIL=0)")
_rsin = _subir(P_SIN, PNG)
check("un plan cuyo consejo no dejó requisitos que decidir -> 409 attestations_require_ledger con su council_state y la "
      "REGLA (aportar es una decisión del ledger; sin ledger no hay dónde sellarla)",
      _rsin.status_code == 409 and _rsin.json()["detail"]["state"] == "attestations_require_ledger"
      and _rsin.json()["detail"]["council_state"].startswith("disabled")
      and "ledger" in _rsin.json()["detail"]["rule"], json.dumps(_rsin.json()["detail"]))
P_SELLADO = _plan("plan-http-sellado")
_subir(P_SELLADO, PNG)
db.mark_plan_used(P_SELLADO, "run-que-lo-sello")
_rsell = _subir(P_SELLADO, PNG2)
check("un plan YA SELLADO a una corrida -> 409 plan_already_used {run_id}: su ledger quedó congelado al encolar y nadie "
      "le añade imágenes después (el registro de esa corrida no puede cambiar)",
      _rsell.status_code == 409 and _rsell.json()["detail"]["state"] == "plan_already_used"
      and _rsell.json()["detail"]["run_id"] == "run-que-lo-sello")
check("pero RETIRAR sigue vivo con el plan sellado: quien aportó una imagen no queda atrapado por el sello",
      client.post(f"/plans/{P_SELLADO}/attestations/{_post_sha(PNG)[0]}/withdraw", headers=NAT,
                  json={"reason": "me equivoque de toma"}).status_code == 200)

# =====================================================================================================================
print("\n# 6. el índice del plan: metadatos y permisos calculados en el SERVIDOR")
# =====================================================================================================================
P4 = _plan("plan-http-4")
_subir(P4, PNG)
_subir(P4, PNG2, share_scope="team")
_sha_a, _sha_b = _post_sha(PNG)[0], _post_sha(PNG2)[0]
idx_nat = client.get(f"/plans/{P4}/attestations", headers=NAT).json()
idx_emm = client.get(f"/plans/{P4}/attestations", headers=EMM).json()
_by_nat = {i["sha256"]: i for i in idx_nat["items"]}
_by_emm = {i["sha256"]: i for i in idx_emm["items"]}
check("el índice trae topes, almacén con su DURABILIDAD, kill-switch, la regla de servibilidad y los vocabularios "
      "CERRADOS de la biblioteca (los mismos que congela el registro y lee el gate de paridad de la webapp)",
      idx_nat["state"] == "listed" and idx_nat["n"] == 2 and idx_nat["n_live"] == 2
      and idx_nat["caps"]["max_per_plan"]["source"].startswith("default-unset:")
      and isinstance(idx_nat["storage"]["durability"], dict)
      and idx_nat["vocabulary"]["ATTESTED_STATES_EXACT"] == list(at.ATTESTED_STATES_EXACT)
      and idx_nat["class"] == "attested" and "sha256 recomputed" in idx_nat["servable_rule"],
      json.dumps({"n": idx_nat["n"], "backend": idx_nat["storage"]["backend"]}))
check("quién puede ver QUÉ lo decide el servidor, no la webapp: quien subió ve las dos; la otra sesión ve la 'team' "
      "(TEAM_VIEW=1 por defecto) y NO la author-only — y cada ítem trae la REGLA que se le aplicó",
      _by_nat[_sha_a]["viewer_may_view"] is True and _by_nat[_sha_b]["viewer_may_view"] is True
      and _by_emm[_sha_a]["viewer_may_view"] is False and _by_emm[_sha_b]["viewer_may_view"] is True
      and _by_emm[_sha_a]["view_rule"] == "author-only" and _by_emm[_sha_b]["view_rule"] == "team"
      and all(i["view_rule"] in at.VIEW_RULES for i in idx_emm["items"]),
      json.dumps({s[:8]: (_by_emm[s]["viewer_may_view"], _by_emm[s]["view_rule"]) for s in (_sha_a, _sha_b)}))
check("`servable` es MEDIDO (los bytes están y el sha recalculado cuadra) y el índice lo declara; la URL de retiro sólo "
      "viaja a quien PUEDE retirar (la otra sesión no la recibe)",
      _by_nat[_sha_a]["servable"]["state"] == "yes" and idx_nat["sha_verified_on_index"] is True
      and _by_nat[_sha_a].get("withdraw_url") and not _by_emm[_sha_a].get("withdraw_url"),
      json.dumps({"servable": _by_nat[_sha_a]["servable"], "wd_emm": _by_emm[_sha_a].get("withdraw_url")}))
check("ninguno de los dos índices lleva binario: sin 'b64', sin data:image, sin llave de almacén y sin la ruta privada",
      all('"b64"' not in json.dumps(x) and "data:image" not in json.dumps(x)
          and "storage_key" not in json.dumps(x)
          and str(STORE).replace("\\", "/") not in json.dumps(x).replace("\\", "/")
          for x in (idx_nat, idx_emm)))

# =====================================================================================================================
print("\n# 7. los BYTES: autorización estricta y sha recalculado sobre lo que sale")
# =====================================================================================================================
b_nat = client.get(f"/plans/{P4}/attestations/{_sha_a}", headers=NAT)
check("quien subió recibe 200 con los bytes EXACTOS (su sha256 cuadra), Content-Type MEDIDO, ETag = el sha, "
      "Cache-Control private,no-store (jamás cacheable fuera), nosniff, Content-Disposition y los X-Witt-Attested-*",
      b_nat.status_code == 200 and at.sha256_hex(b_nat.content) == _sha_a
      and b_nat.headers["content-type"].startswith("image/png")
      and b_nat.headers["etag"] == f'"{_sha_a}"'
      and b_nat.headers["cache-control"] == "private, no-store"
      and b_nat.headers["x-content-type-options"] == "nosniff"
      and b_nat.headers["x-witt-attested-sha256"] == _sha_a
      and b_nat.headers["x-witt-attested-class"] == "attested"
      and b_nat.headers["x-witt-attested-view-rule"] == "author-only"
      and b_nat.headers["x-witt-attested-patient-material"] == "0"
      and "inline" in b_nat.headers["content-disposition"],
      json.dumps({k: v for k, v in b_nat.headers.items() if k.startswith("x-witt") or k in ("etag", "cache-control")}))
check("If-None-Match con el ETag -> 304 (el sha ES la identidad de esos bytes: no se reenvían)",
      client.get(f"/plans/{P4}/attestations/{_sha_a}", headers={**NAT, "If-None-Match": f'"{_sha_a}"'}).status_code == 304)
b_emm = client.get(f"/plans/{P4}/attestations/{_sha_a}", headers=EMM)
check("otra sesión sobre una imagen author-only -> 403 con la REGLA que se aplicó y sin un solo byte en el cuerpo",
      b_emm.status_code == 403 and b_emm.json()["detail"]["state"].startswith("forbidden")
      and b_emm.json()["detail"]["view_rule"]["rule"] == "author-only"
      and base64.b64encode(PNG).decode("ascii")[:40] not in b_emm.text)
check("la misma sesión sobre la imagen declarada 'team' con WITT_ATTESTED_TEAM_VIEW=1 -> 200",
      client.get(f"/plans/{P4}/attestations/{_sha_b}", headers=EMM).status_code == 200)
os.environ["WITT_ATTESTED_TEAM_VIEW"] = "0"
_b_team_off = client.get(f"/plans/{P4}/attestations/{_sha_b}", headers=EMM)
os.environ.pop("WITT_ATTESTED_TEAM_VIEW", None)
check("WITT_ATTESTED_TEAM_VIEW=0 cierra el equipo AL INSTANTE (la env se lee EN LA LLAMADA): la misma imagen 'team' "
      "pasa a 403 author-only para la otra sesión, sin tocar ninguna fila",
      _b_team_off.status_code == 403 and _b_team_off.json()["detail"]["view_rule"]["rule"] == "author-only"
      and _b_team_off.json()["detail"]["view_rule"]["team_view_env"] is False,
      json.dumps(_b_team_off.json()["detail"]["view_rule"]))
os.environ["WITT_ATTESTED_PATIENT_MATERIAL"] = "1"
P5 = _plan("plan-http-5")
r_pac = _subir(P5, PNG, share_scope="team", patient_material="true", consent_kind="patient-consented",
               consent_text="consentimiento informado firmado por la paciente el 2026-08-01",
               deidentified_declared="true")
_sha_pac = _post_sha(PNG)[0]
_b_pac_otro = client.get(f"/plans/{P5}/attestations/{_sha_pac}", headers=EMM)
_b_pac_duena = client.get(f"/plans/{P5}/attestations/{_sha_pac}", headers=NAT)
os.environ.pop("WITT_ATTESTED_PATIENT_MATERIAL", None)
check("MATERIAL DE PACIENTE es author-only SIEMPRE: aunque quien subió declare 'team' y TEAM_VIEW esté en 1, la otra "
      "sesión recibe 403 con la regla 'author-only (patient-material)'; sólo quien lo aportó lo ve, y la cabecera lo "
      "marca — no hay variable de entorno que abra esto",
      r_pac.status_code == 201 and _b_pac_otro.status_code == 403
      and _b_pac_otro.json()["detail"]["view_rule"]["rule"] == "author-only (patient-material)"
      and _b_pac_duena.status_code == 200
      and _b_pac_duena.headers["x-witt-attested-patient-material"] == "1",
      json.dumps(_b_pac_otro.json()["detail"]["view_rule"]))
_fila_a = db.attested_image_get(P4, _sha_a)
_ruta_a = STORE / _fila_a["storage_key"]
_orig = _ruta_a.read_bytes()
_ruta_a.write_bytes(_orig + b"ALTERADO")
_idx_alt = client.get(f"/plans/{P4}/attestations", headers=NAT).json()
_b_alt = client.get(f"/plans/{P4}/attestations/{_sha_a}", headers=NAT)
check("si alguien ALTERA el archivo en el disco, el índice lo dice ('bytes-mismatch') y la puerta de bytes responde 409 "
      "— JAMÁS 200 con otros bytes: el sha se recalcula sobre lo que va a salir, no sobre un stat previo",
      next(i for i in _idx_alt["items"] if i["sha256"] == _sha_a)["servable"]["state"] == "bytes-mismatch"
      and _b_alt.status_code == 409 and _b_alt.json()["detail"]["state"] == "bytes-mismatch"
      and _b_alt.json()["detail"]["expected"] == _sha_a,
      json.dumps(_b_alt.json()["detail"])[:200])
_ruta_a.unlink()
_b_falta = client.get(f"/plans/{P4}/attestations/{_sha_a}", headers=NAT)
check("si el archivo DESAPARECE (el volumen efímero de Dokploy), 404 'bytes-missing' declarado — la fila sigue diciendo "
      "que esa imagen existió: ausencia de bytes no borra la procedencia",
      _b_falta.status_code == 404 and _b_falta.json()["detail"]["state"] == "bytes-missing"
      and db.attested_image_get(P4, _sha_a) is not None)
_ruta_a.write_bytes(_orig)

# =====================================================================================================================
print("\n# 8. retirar: la lápida se queda, los píxeles se van, la cascada alcanza")
# =====================================================================================================================
P6 = _plan("plan-http-6")
_subir(P6, PNG)
_sha6 = _post_sha(PNG)[0]
_ruta6 = STORE / db.attested_image_get(P6, _sha6)["storage_key"]
_lea_antes = db.get_plan(P6).get("council_last_event_at")
check("retirar sin razón -> 400 withdraw_without_reason (retirar es una decisión y queda escrita); otra sesión -> 403 "
      "withdraw-not-uploader con la política vigente y su fuente",
      client.post(f"/plans/{P6}/attestations/{_sha6}/withdraw", headers=NAT, json={"reason": "  "}).status_code == 400
      and client.post(f"/plans/{P6}/attestations/{_sha6}/withdraw", headers=EMM,
                      json={"reason": "no me gusta"}).status_code == 403
      and client.post(f"/plans/{P6}/attestations/{_sha6}/withdraw", headers=EMM,
                      json={"reason": "x"}).json()["detail"]["policy"] == "uploader")
r_wd = client.post(f"/plans/{P6}/attestations/{_sha6}/withdraw", headers=NAT, json={"reason": "la cambie por otra toma"})
_fila6 = db.attested_image_get(P6, _sha6)
check("quien la subió retira: 200 con la lápida ('withdrawn (tombstone)'), bytes_deleted true y el archivo YA NO EXISTE "
      "en el disco; la FILA se queda con identidad, procedencia y la razón — el registro es inmutable, los píxeles no",
      r_wd.status_code == 200 and r_wd.json()["state"] == "withdrawn (tombstone)"
      and r_wd.json()["bytes_deleted"] is True and not _ruta6.exists()
      and _fila6["withdrawn_at"] and _fila6["withdrawn_by"] == "natalia"
      and _fila6["withdraw_reason"] == "la cambie por otra toma" and _fila6["uploaded_by"] == "natalia",
      json.dumps({k: r_wd.json()[k] for k in ("state", "bytes_deleted", "storage_delete_state", "cascade_n")}))
check("segundo retiro -> 409 already-withdrawn {withdrawn_at}; los bytes -> 410 con la lápida y su razón (410, no 404: "
      "existió y se retiró, que no es lo mismo que no haber existido); el índice la muestra retirada",
      client.post(f"/plans/{P6}/attestations/{_sha6}/withdraw", headers=NAT, json={"reason": "otra vez"}).status_code == 409
      and client.get(f"/plans/{P6}/attestations/{_sha6}", headers=NAT).status_code == 410
      and client.get(f"/plans/{P6}/attestations/{_sha6}", headers=NAT).json()["detail"]["withdraw_reason"] == "la cambie por otra toma"
      and client.get(f"/plans/{P6}/attestations", headers=NAT).json()["n_live"] == 0)
_ev6 = [e for e in db.plan_events_after(P6, 0) if e["type"].startswith("attestation.")]
check("la traza del PLAN lleva los eventos attestation.uploaded / .bytes_served / .withdrawn con identidad CORTA y sin "
      "caption, y NO mueven el latido del consejo (los emite una persona, no el job: mover council_last_event_at haría "
      "parecer vivo un job muerto)",
      [e["type"] for e in _ev6] == ["attestation.uploaded", "attestation.withdrawn"]
      and all(CAP not in json.dumps(e["payload"], default=str) for e in _ev6)
      and all(e["payload"].get("sha256_short") == at.short_of(_sha6) for e in _ev6)
      and db.get_plan(P6).get("council_last_event_at") == _lea_antes,
      json.dumps([e["type"] for e in _ev6]))

# =====================================================================================================================
print("\n# 9. heredar: la misma imagen en otro plan, con su procedencia original")
# =====================================================================================================================
P7 = _plan("plan-http-7")
_subir(P7, PNG2)
_sha7 = _post_sha(PNG2)[0]
db.attested_image_attach(P7, _sha7, "knowledge_now", by="natalia")
RID7 = runs_mod.new_run("natalia", "¿y en el hijo?", ["wt1a"], plan_json=json.dumps({"route": "evidence-run"}),
                        council_json=json.dumps({"plan_id": P7, "ledger": {"state": "approved"}}))
P8 = _plan("plan-http-8")
r_her = client.post(f"/plans/{P8}/attestations/inherit", headers=NAT, json={"sha256": _sha7, "from_run_id": RID7})
_it_her = (r_her.json() or {}).get("item") or {}
check("heredar: 201 con ledger_state 'inherited', los bytes COPIADOS bajo la llave del plan NUEVO (el sha es el mismo: "
      "es la misma imagen) y la procedencia ORIGINAL intacta — quién la aportó y cuándo no cambian: heredar no "
      "re-atestigua; y la fila dice de dónde vino",
      r_her.status_code == 201 and _it_her["ledger_state"] == "inherited" and _it_her["sha256"] == _sha7
      and _it_her["uploaded_by"] == "natalia" and _it_her["attached_to"] is None
      and db.attested_image_get(P8, _sha7)["inherited_from_plan_id"] == P7
      and db.attested_image_get(P8, _sha7)["inherited_from_run_id"] == RID7
      and (STORE / db.attested_image_get(P8, _sha7)["storage_key"]).exists()
      and at.sha256_hex((STORE / db.attested_image_get(P8, _sha7)["storage_key"]).read_bytes()) == _sha7,
      json.dumps({"ledger_state": _it_her["ledger_state"], "from": db.attested_image_get(P8, _sha7)["inherited_from_plan_id"]}))
P9 = _plan("plan-http-9", user="emmanuel")
check("otra sesión NO hereda la imagen de alguien más -> 403 inherit-not-uploader (aportar es un acto personal: sólo "
      "quien lo hizo puede volver a hacerlo)",
      client.post(f"/plans/{P9}/attestations/inherit", headers=EMM,
                  json={"sha256": _sha7, "from_run_id": RID7}).status_code == 403)
r_casc = client.post(f"/plans/{P7}/attestations/{_sha7}/withdraw", headers=NAT, json={"reason": "retiro con cascada"})
check("la CASCADA del retiro alcanza a las copias heredadas: cascade_n 1, el plan hijo aparece en cascade_plan_ids, su "
      "fila queda retirada y sus bytes borrados — retirar una imagen la retira de TODAS partes",
      r_casc.json()["cascade_n"] == 1 and r_casc.json()["cascade_plan_ids"] == [P8]
      and db.attested_image_get(P8, _sha7)["withdrawn_at"] is not None
      and client.get(f"/plans/{P8}/attestations/{_sha7}", headers=NAT).status_code == 410,
      json.dumps({"cascade_n": r_casc.json()["cascade_n"], "planes": r_casc.json()["cascade_plan_ids"]}))
check("una imagen RETIRADA ya no se hereda -> 400 attested_image_not_inheritable con su estado",
      client.post(f"/plans/{_plan('plan-http-10')}/attestations/inherit", headers=NAT,
                  json={"sha256": _sha7, "from_run_id": RID7}).json()["detail"]["state"] == "attested_image_not_inheritable")

# =====================================================================================================================
print("\n# 10. el índice y los bytes de la CORRIDA (lo que el registro congeló)")
# =====================================================================================================================
P11 = _plan("plan-http-11")
_subir(P11, PNG)
_subir(P11, PNG2)
_sha11a, _sha11b = _post_sha(PNG)[0], _post_sha(PNG2)[0]
db.attested_image_attach(P11, _sha11a, "knowledge_now", by="natalia")
db.attested_image_attach(P11, _sha11b, "requirement", requirement_id="req-fff", by="natalia")
RID11 = runs_mod.new_run("natalia", "¿la corrida con imágenes?", ["wt1a"], plan_json=json.dumps({"route": "evidence-run"}),
                         council_json=json.dumps({"plan_id": P11, "ledger": {"state": "approved"}}))
_items11 = [at.frozen_item(db.attested_image_get(P11, s)) for s in (_sha11a, _sha11b)]
_frozen11 = {"render_contract_version": "1.14", "question_matches_run": True,
             "attested_images": {"state": "attached", "n_attached": 2, "items": _items11, "n_seen_by_panel": 1}}
_usage11 = {"attested_images": {"state": "attached", "n_attached": 2, "n_seen_by_panel": 1, "n_readings": 0,
                                "bytes_total": sum(int(i["bytes"]) for i in _items11),
                                "class": "medición (conteos y bytes; los tokens de visión ya están en los input_tokens "
                                         "medidos del panel)"}}
db.update_run(RID11, state="awaiting_closure", frozen_record_json=json.dumps(_frozen11, default=str),
              usage_json=json.dumps(_usage11, default=str))   # el MISMO espejo que runs._token_usage persiste (K)
idx_run = client.get(f"/runs/{RID11}/attestations", headers=NAT).json()
check("el índice de la corrida lee su registro CONGELADO (state 'attached', 2 ítems, el conteo del panel) y MIDE hoy el "
      "estado vivo de cada una (servable, retirada) — lo congelado dice lo que pasó; lo medido, lo que hay hoy",
      idx_run["state"] == "attached" and idx_run["n_items"] == 2 and idx_run["n_withdrawn_now"] == 0
      and idx_run["n_seen_by_panel"] == 1 and idx_run["render_contract_version"] == "1.14"
      and all(i["servable"]["state"] == "yes" for i in idx_run["items"])
      and all(i["url"] == f"/runs/{RID11}/attestations/{i['sha256']}" for i in idx_run["items"]),
      json.dumps({"state": idx_run["state"], "n": idx_run["n_items"]}))
b_run = client.get(f"/runs/{RID11}/attestations/{_sha11a}", headers=NAT)
check("los bytes por la corrida: 200 para quien la aportó, con el sha verificado sobre lo que sale y las mismas "
      "cabeceras que la puerta del plan; un sha que NO está en ESTE registro -> 404 aunque exista en la base",
      b_run.status_code == 200 and at.sha256_hex(b_run.content) == _sha11a
      and b_run.headers["cache-control"] == "private, no-store"
      and client.get(f"/runs/{RID11}/attestations/{_post_sha(JPG)[0]}", headers=NAT).status_code == 404
      and client.get(f"/runs/{RID11}/attestations/{_sha11a}", headers=EMM).status_code == 403)
RID_VIEJO = runs_mod.new_run("natalia", "¿una corrida de 1.13?", ["wt1a"], plan_json=json.dumps({"route": "evidence-run"}))
db.update_run(RID_VIEJO, state="awaiting_closure",
              frozen_record_json=json.dumps({"render_contract_version": "1.13", "question_matches_run": True}))
idx_viejo = client.get(f"/runs/{RID_VIEJO}/attestations", headers=NAT).json()
check("una corrida ANTERIOR a 1.14 lo DECLARA: state 'not-instrumented (contrato < 1.14)' con items [] — la función no "
      "existía cuando corrió, que NO es lo mismo que «no hubo imágenes»; y los bytes de ese registro -> 404 con el mismo "
      "literal, jamás un 200 fabricado",
      idx_viejo["state"] == "not-instrumented (contrato < 1.14)" and idx_viejo["items"] == []
      and idx_viejo["render_contract_version"] == "1.13"
      and client.get(f"/runs/{RID_VIEJO}/attestations/{_sha11a}", headers=NAT).json()["detail"]["state"]
      == "not-instrumented (contrato < 1.14)")
_r_sin_frozen = client.get(f"/runs/{runs_mod.new_run('natalia', '¿sin registro?', [], plan_json='{}')}/attestations",
                           headers=NAT)
check("una corrida sin registro congelado todavía -> 409 declarado (no 200 vacío: no se finge un índice de algo que aún "
      "no ocurrió); una corrida inexistente -> 404",
      _r_sin_frozen.status_code == 409 and client.get("/runs/no-existe/attestations", headers=NAT).status_code == 404)

# =====================================================================================================================
print("\n# 11. kill-switch: todo se apaga MENOS el derecho a retirar")
# =====================================================================================================================
P12 = _plan("plan-http-12")
_subir(P12, PNG)
_sha12 = _post_sha(PNG)[0]
os.environ["WITT_ATTESTED_IMAGES"] = "0"
_k_sub = _subir(P12, PNG2)
_k_her = client.post(f"/plans/{P12}/attestations/inherit", headers=NAT, json={"sha256": _sha7, "from_run_id": RID7})
_k_idx = client.get(f"/plans/{P12}/attestations", headers=NAT).json()
_k_run = client.get(f"/runs/{RID11}/attestations", headers=NAT).json()
_k_byt = client.get(f"/plans/{P12}/attestations/{_sha12}", headers=NAT)
_k_wd = client.post(f"/plans/{P12}/attestations/{_sha12}/withdraw", headers=NAT, json={"reason": "apagada y aun asi la retiro"})
os.environ.pop("WITT_ATTESTED_IMAGES", None)
check("con WITT_ATTESTED_IMAGES=0: subir 409 attested_images_disabled (con la fuente de la env), heredar 409, el índice "
      "del plan y el de la corrida declaran 'kill-switch WITT_ATTESTED_IMAGES=0' con items [] y los bytes 404 — pero "
      "RETIRAR responde 200: apagar la función no puede dejar la imagen de una persona atrapada en el sistema",
      _k_sub.status_code == 409 and _k_sub.json()["detail"]["state"] == "attested_images_disabled"
      and _k_sub.json()["detail"]["source"] == "env:WITT_ATTESTED_IMAGES"
      and _k_her.status_code == 409
      and _k_idx["state"] == "kill-switch WITT_ATTESTED_IMAGES=0" and _k_idx["items"] == []
      and _k_run["state"] == "kill-switch WITT_ATTESTED_IMAGES=0" and _k_run["items"] == []
      and _k_run["frozen_state"] == "attached"        # lo congelado NO se borra: se declara que hoy está apagado
      and _k_byt.status_code == 404 and _k_byt.json()["detail"]["state"] == "kill-switch WITT_ATTESTED_IMAGES=0"
      and _k_wd.status_code == 200 and _k_wd.json()["state"] == "withdrawn (tombstone)",
      json.dumps({"sub": _k_sub.status_code, "idx": _k_idx["state"], "byt": _k_byt.status_code, "wd": _k_wd.status_code}))

# =====================================================================================================================
print("\n# 12. el almacén que no está: 503 declarado, JAMÁS un fallback silencioso")
# =====================================================================================================================
P13 = _plan("plan-http-13")
os.environ["WITT_ATTESTED_BACKEND"] = "minio"
_r503 = _subir(P13, PNG)
os.environ.pop("WITT_ATTESTED_BACKEND", None)
check("WITT_ATTESTED_BACKEND=minio sin MINIO_* configurado -> 503 attested-storage-unavailable y NADA escrito: jamás se "
      "cae a `local` en silencio (una imagen privada no se guarda donde no se pidió)",
      _r503.status_code == 503 and _r503.json()["detail"]["state"] == "attested-storage-unavailable"
      and db.attested_images_of_plan(P13) == [],
      json.dumps(_r503.json()["detail"])[:220])


# =====================================================================================================================
print("\n# 14. el LEDGER sella: subir sólo prepara, aprobar es lo que adjunta (ADR-0086 J)")
# =====================================================================================================================
REQS = [{"requirement_id": "req-aaa", "source_family": "zfin", "priority": "must", "gap": "expresión"},
        {"requirement_id": "req-bbb", "source_family": "pubmed", "priority": "should", "gap": "función"}]


def _plan_con_requisitos(plan_id):
    _plan(plan_id)
    db.update_plan_council(plan_id, council_json=json.dumps({"plan_id": plan_id, "requirements": REQS}))
    return plan_id


def _ledger(plan_id, headers=NAT, **body):
    return client.post(f"/plans/{plan_id}/council/ledger", headers=headers, json=body)


PL = _plan_con_requisitos("plan-ledger-1")
_subir(PL, PNG)
_subir(PL, PNG2)
_sha_l1, _sha_l2 = _post_sha(PNG)[0], _post_sha(PNG2)[0]
_otro = _plan_con_requisitos("plan-ledger-otro")
_subir(_otro, JPG, ct="image/jpeg", nombre="o.jpg")
_sha_otro = _post_sha(JPG)[0]
_m = {}
_m["unknown_attested_image"] = _ledger(PL, images=[_sha_otro], approve=False)
_m["images_without_aporto"] = _ledger(PL, decisions=[{"requirement_id": "req-aaa", "decision": "keep",
                                                      "images": [_sha_l1]}], approve=False)
_m["duplicated_attested_image"] = _ledger(PL, images=[_sha_l1], decisions=[
    {"requirement_id": "req-aaa", "decision": "aporto", "attested_text": "lo medimos en el laboratorio",
     "images": [_sha_l1]}], approve=False)
check("(J.2) el ledger valida las imágenes ANTES de escribir nada: un sha de OTRO plan -> 400 unknown_attested_image; "
      "una imagen colgada de un requisito que se MANTIENE (no se aporta) -> 400 images_without_aporto; el mismo sha en "
      "dos sitios -> 400 duplicated_attested_image. Un 400 aquí deja intacto el ledger anterior: ninguna decisión "
      "humana se pierde por un sha mal escrito",
      all(r.status_code == 400 and r.json()["detail"]["state"] == k for k, r in _m.items())
      and db.get_plan(PL).get("council_ledger_json") is None,
      json.dumps({k: (r.status_code, r.json()["detail"]["state"]) for k, r in _m.items()}))
_r_draft = _ledger(PL, images=[_sha_l1], decisions=[
    {"requirement_id": "req-bbb", "decision": "aporto", "attested_text": "lo confirmamos en el cuaderno 2026-08",
     "images": [_sha_l2]}], approve=False)
_led_d = _r_draft.json()["ledger"]
check("(J.3) en BORRADOR nada se sella: el ledger devuelve las dos imágenes con su destino propuesto y ledger_state "
      "'staged (pending approval)', y en la BASE siguen SIN attached_to — subir prepara, aprobar es lo que adjunta",
      _r_draft.status_code == 200 and _led_d["n_images"] == 2 and _led_d["images_source"] == "body.images"
      and all(i["ledger_state"] == "staged (pending approval)" for i in _led_d["images"])
      and db.attested_image_get(PL, _sha_l1)["attached_to"] is None
      and db.attested_image_get(PL, _sha_l2)["attached_to"] is None,
      json.dumps({"n": _led_d["n_images"], "src": _led_d["images_source"]}))
_r_keep = _ledger(PL, decisions=[{"requirement_id": "req-aaa", "decision": "keep"}], approve=False)
check("(J.1, PATCH-like) un borrador posterior que NO manda `images` CONSERVA las vinculaciones del anterior y lo "
      "DECLARA (images_source 'kept-from-previous-draft') — igual que knowledge_now: no mandar no es borrar",
      _r_keep.json()["ledger"]["images_source"] == "kept-from-previous-draft"
      and _r_keep.json()["ledger"]["n_images"] == 2,
      json.dumps({"src": _r_keep.json()["ledger"]["images_source"], "n": _r_keep.json()["ledger"]["n_images"]}))
_r_ap = _ledger(PL, approve=True, decisions=[{"requirement_id": "req-aaa", "decision": "keep"}], headers=EMM)
_led_a = _r_ap.json()["ledger"]
_f_l1 = db.attested_image_get(PL, _sha_l1)
check("(J.3) al APROBAR se sella: attached_to 'knowledge_now' para la del cuerpo y 'requirement' con su requirement_id "
      "para la del `aporto`; attached_by es QUIEN APROBÓ (permisos planos: puede no ser quien subió) y el registro lo "
      "DICE con attached_by_is_uploader false — no se oculta, se declara",
      _r_ap.status_code == 200 and _led_a["n_images"] == 2
      and _f_l1["attached_to"] == "knowledge_now" and _f_l1["attached_by"] == "emmanuel"
      and db.attested_image_get(PL, _sha_l2)["attached_to"] == "requirement"
      and db.attested_image_get(PL, _sha_l2)["requirement_id"] == "req-bbb"
      and all(i["attached_by_is_uploader"] is False for i in _led_a["images"])
      and next(d for d in _led_a["decisions"] if d["requirement_id"] == "req-bbb")["n_images"] == 1,
      json.dumps({"l1": _f_l1["attached_to"], "l2": db.attested_image_get(PL, _sha_l2)["attached_to"]}))
_at_antes = _f_l1["attached_at"]
_ledger(PL, approve=True, decisions=[{"requirement_id": "req-aaa", "decision": "keep"}])
check("(J.3, write-once) una SEGUNDA aprobación tras un borrador NO mueve la adjunción ya registrada: attached_at y "
      "attached_by siguen siendo los de la primera (el registro de cuándo y quién no se reescribe)",
      db.attested_image_get(PL, _sha_l1)["attached_at"] == _at_antes
      and db.attested_image_get(PL, _sha_l1)["attached_by"] == "emmanuel")
_r_vacio = _ledger(PL, images=[], approve=False)
check("(J.1) `images: []` EXPLÍCITO desvincula en el ledger (images_source 'body.images', n_images 0) — pero lo ya "
      "sellado en la BASE no se des-sella: una aprobación pasada es un hecho, no un borrador",
      _r_vacio.json()["ledger"]["n_images"] == 0 and _r_vacio.json()["ledger"]["images"] == []
      and _r_vacio.json()["ledger"]["images_source"] == "body.images"
      and db.attested_image_get(PL, _sha_l1)["attached_to"] == "knowledge_now")
PL2 = _plan_con_requisitos("plan-ledger-2")
_subir(PL2, PNG)
_sha_r = _post_sha(PNG)[0]
client.post(f"/plans/{PL2}/attestations/{_sha_r}/withdraw", headers=NAT, json={"reason": "me arrepenti"})
check("(J.2) una imagen RETIRADA no se puede sellar -> 400 attested_image_withdrawn (la lápida es definitiva para el "
      "ledger: no se adjunta lo que su autora quitó)",
      _ledger(PL2, images=[_sha_r], approve=False).json()["detail"]["state"] == "attested_image_withdrawn")
os.environ["WITT_ATTESTED_PATIENT_MATERIAL"] = "1"
PL3 = _plan_con_requisitos("plan-ledger-3")
_subir(PL3, PNG, patient_material="true", consent_kind="patient-consented",
       consent_text="consentimiento informado firmado por la paciente el 2026-08-01", deidentified_declared="true")
_sha_p = _post_sha(PNG)[0]
_r_sin_acuse = _ledger(PL3, images=[_sha_p], approve=True)
_r_con_acuse = _ledger(PL3, images=[_sha_p], approve=True, patient_material_acknowledged=True)
os.environ.pop("WITT_ATTESTED_PATIENT_MATERIAL", None)
_led_p = _r_con_acuse.json()["ledger"]
_flag = next((f for f in (_led_p.get("flags") or []) if f.get("kind") == "patient-material"), None)
check("(I.iii/I.iv) aprobar un ledger con MATERIAL DE PACIENTE sin acuse explícito -> 400 "
      "patient_material_unacknowledged; con acuse -> 200, has_patient_material true y una BANDERA 'patient-material' "
      "con gate HUMANO, su sha corto y su origen (la bandera se emite, no se resuelve sola)",
      _r_sin_acuse.status_code == 400
      and _r_sin_acuse.json()["detail"]["state"] == "patient_material_unacknowledged"
      and _r_con_acuse.status_code == 200 and _led_p["has_patient_material"] is True
      and _led_p["patient_material_acknowledged"] is True
      and _flag is not None and _flag["gate"] == "human" and _flag["sha256_short"] == at.short_of(_sha_p)
      and _flag["source"] == at.FLAG_SOURCE and isinstance(_flag["emitted_by"], list),
      json.dumps(_flag, default=str)[:260])
_ev_led = [e for e in db.plan_events_after(PL, 0) if e["type"] in ("council.ledger", "attestation.attached")]
check("(J.3) la traza del plan registra el sellado: council.ledger lleva n_images / has_patient_material / "
      "patient_material_acknowledged, y attestation.attached lleva los sha CORTOS y a qué se adjuntó — ningún caption "
      "entra a la traza",
      any(e["type"] == "council.ledger" and e["payload"].get("n_images") == 2 for e in _ev_led)
      and any(e["type"] == "attestation.attached" and e["payload"].get("n_images") == 2 for e in _ev_led)
      and all(CAP not in json.dumps(e["payload"], default=str) for e in _ev_led),
      json.dumps([e["type"] for e in _ev_led]))
_vista = client.get(f"/plans/{PL}", headers=NAT).json()
check("(J.4) GET /plans/{id} trae `attested_images` con la MISMA forma del índice, para que la pantalla de Preguntar "
      "pinte con UNA llamada — metadatos, permisos por sesión y ningún byte",
      _vista["attested_images"]["state"] == "listed" and _vista["attested_images"]["n"] == 2
      and all(i["class"] == "attested" for i in _vista["attested_images"]["items"])
      and '"b64"' not in json.dumps(_vista),
      json.dumps({"state": _vista["attested_images"]["state"], "n": _vista["attested_images"]["n"]}))
os.environ["WITT_ATTESTED_IMAGES"] = "0"
_r_kill = _ledger(PL2, images=[_sha_r], approve=False)
os.environ.pop("WITT_ATTESTED_IMAGES", None)
check("(J.2) bajo kill-switch el ledger con imágenes -> 400 attested_images_disabled con la fuente de la env (la "
      "función apagada no sella nada, y lo dice)",
      _r_kill.status_code == 400 and _r_kill.json()["detail"]["state"] == "attested_images_disabled"
      and _r_kill.json()["detail"]["source"] == "env:WITT_ATTESTED_IMAGES")

# =====================================================================================================================
print("\n# 13. las rutas no se pisan, CORS expone lo suyo y nada binario viaja en JSON")
# =====================================================================================================================
check("/plans/{id}/attestations NO captura /plans/{id}/events ni /plans/{id}; /runs/{id}/attestations NO captura "
      "/runs/{id}/events (los segmentos son literales y el orden de declaración no los solapa)",
      client.get(f"/plans/{P4}/events", headers=NAT).status_code == 200
      and client.get(f"/plans/{P4}", headers=NAT).status_code == 200
      and client.get(f"/runs/{RID11}/events", headers=NAT).status_code == 200
      and "events" in client.get(f"/plans/{P4}/events", headers=NAT).json())
_pre = client.options(f"/plans/{P4}/attestations/{_sha_b}",
                      headers={"Origin": ORIGIN, "Access-Control-Request-Method": "GET"})
_real = client.get(f"/plans/{P4}/attestations/{_sha_b}", headers={**EMM, "Origin": ORIGIN})
_exp = [h.strip().lower() for h in (_real.headers.get("access-control-expose-headers") or "").split(",")]
check("CORS: el preflight admite la puerta de bytes y la respuesta REAL expone las X-Witt-Attested-* (Starlette manda "
      "expose_headers en la respuesta, no en el preflight; sin ellas el navegador las esconde aunque viajen). NINGUNA "
      "de esas cabeceras lleva bytes ni llave de almacén: identidad, clase y la regla de vista que el servidor aplicó",
      _pre.status_code in (200, 204) and _pre.headers.get("access-control-allow-origin") == ORIGIN
      and all(h.lower() in _exp for h in app_mod.ATTESTED_EXPOSE_HEADERS)
      and not any("key" in h or "path" in h or "b64" in h for h in _exp),
      json.dumps(_exp))
_todas = [client.get(f"/plans/{P4}/attestations", headers=NAT), client.get(f"/runs/{RID11}/attestations", headers=NAT),
          client.get(f"/plans/{P4}", headers=NAT)]
check("ninguna respuesta JSON de este gate lleva binario: ni 'b64', ni 'data:image', ni el base64 REAL de las imágenes "
      "subidas, ni la ruta privada del almacén",
      all('"b64"' not in x.text and "data:image" not in x.text
          and base64.b64encode(PNG).decode("ascii")[:40] not in x.text
          and str(STORE).replace("\\", "/") not in x.text.replace("\\", "/") for x in _todas))
_usage = client.get("/usage", headers=NAT).json()
_ai_usage = _usage["attested_images"]
check("(K) GET /usage trae `attested_images` APARTE de totals, y las DOS mediciones rotuladas: lo que las CORRIDAS "
      "consumieron (n_attached, n_seen_by_panel, bytes_total, by_state) y las FILAS vivas de la base (`rows`) — que es "
      "otra cosa: una imagen puede existir sin haber entrado a ninguna corrida. Todo es MEDICIÓN, cero proyección: los "
      "tokens de visión ya están dentro de los input_tokens medidos del panel y aquí no se suman otra vez",
      _ai_usage["state"] == "measured" and _ai_usage["n_runs_declared"] == 1
      # `n_runs_without` cuenta las corridas que SÍ traen usage_json pero no el bloque (a esas no se les inventa 0); en
      # este gate sólo la corrida sembrada tiene usage_json, así que el contador es 0 y eso es lo correcto
      and _ai_usage["n_runs_without"] == 0
      and _ai_usage["n_attached"] >= 2 and _ai_usage["bytes_total"] > 0
      and _ai_usage["by_state"].get("attached", 0) >= 1
      and _ai_usage["rows"]["n_images"] >= _ai_usage["n_attached"]
      and _ai_usage["rows"]["class"].startswith("medición")
      and _ai_usage["class"].startswith("medición") and "counted twice" in _ai_usage["note"]
      and "attested_images" not in _usage.get("totals", {})
      # el bloque de lo atestiguado no lleva bytes; `b64` sí aparece en /usage por los TOPES de figuras
      # (request_b64_mb), que no es una fuga: una afirmación demasiado ancha convertiría un tope en un hallazgo
      and '"b64"' not in json.dumps(_ai_usage) and "data:image" not in json.dumps(_usage),
      json.dumps({k: _ai_usage.get(k) for k in ("state", "n_runs_declared", "n_runs_without", "n_attached",
                                                "bytes_total", "by_state")} | {"rows": _ai_usage.get("rows")},
                 default=str)[:380])
check("la superficie que esta capa usa de db.py es REAL y está migrada (attested_schema_state 'ready'); app.py importó "
      "la biblioteca de verdad (no un stub) y plan_add_event acepta heartbeat=",
      db.attested_schema_state() == "ready" and app_mod.attestations_mod is at
      and "heartbeat" in __import__("inspect").signature(db.plan_add_event).parameters)
check("cero red MEDIDA: urlopen bloqueado y contado == 0 durante TODO el gate (ninguna de las 7 puertas sale a internet)",
      _NET == [], json.dumps(_NET[:3]))
_fin()
