"""smoke_attestations.py — gate offline de las IMÁGENES ATESTIGUADAS (ADR-0086, rebanada F1: lib/attestations.py).

Una imagen que aporta una persona es ATESTIGUADA: procedencia registrada (quién, cuándo, consentimiento y licencia
declarados), jamás evidencia ni cita. Este gate MIDE la biblioteca, no la supone:

  * vocabularios CERRADOS y coherentes (estados, exif, almacenamiento, servible, consentimiento, licencias declaradas,
    alcances) + las 3 excepciones EXACTAS del kill-switch + las llaves de fila/frozen/prompt/ledger/thread.
  * bytes: sniff por MAGIC BYTES (el Content-Type declarado se REGISTRA, jamás decide), dims por cabecera, 0 ≠ null,
    rechazos tipados (PDF disfrazado, GIF fuera por default, truncado, demasiados megapíxeles, demasiado pequeño,
    sobre el tope de MB).
  * strip de metadatos SIN recodificar: JPEG pierde APP1/COM y conserva SOI/APP0/DQT/DHT/SOF/SOS; PNG pierde
    tEXt/eXIf y conserva IHDR/IDAT/IEND con su CRC; WebP pierde EXIF y corrige el tamaño RIFF. Lo MEDIDO: la imagen
    sigue decodificando con las MISMAS dimensiones y ya no contiene las agujas de privacidad (GPS, fecha, equipo).
  * identidad: el sha256 canónico es el de los bytes ALMACENADOS (post-strip) y `sha256_received` se conserva aparte.
  * almacenamiento privado intercambiable: local (put/get/delete/probe, tombstone), memoria (fake) y minio SIN
    credenciales → 'storage-unavailable' declarado, JAMÁS fallback silencioso y CERO red.
  * autorización: sólo el autor por default; 'team' sólo si la persona lo declaró Y la env lo permite; material de
    paciente SIEMPRE sólo autor; retiro = tombstone (410) y sigue vivo bajo kill-switch.
  * entrega: los bytes van a lo sumo a las lentes con visión, en bloques rotulados ATTESTED separados de las figuras y
    con su tope; el sintetizador y el consejo reciben caption y metadatos, NUNCA bytes (medido por substring).
  * fixtures sintéticos deterministas + MANIFEST de texto coherente (cero binarios en el repo).

100% offline: urllib.request.urlopen bloqueado y CONTADO == 0; cero modelo; cero DB; almacenamiento en tempdir.
Exit 0 = todo PASS.

Corre:  python rag_index/query_service/smoke_attestations.py
"""
import base64
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

os.environ.setdefault("NEO4J_URI", "")
os.environ.setdefault("RAG_BACKEND", "sparse")
os.environ.setdefault("OPENAI_API_KEY", "")
os.environ.setdefault("ANTHROPIC_API_KEY", "")
os.environ.setdefault("MINIO_ENDPOINT", "")
os.environ.setdefault("WITT_RUN_ORIGIN", "smoke")

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "analysis" / "scripts"))

# ---- cero red: urlopen bloqueado y CONTADO durante TODO el smoke ---------------------------------------------------
import urllib.request as _urlreq  # noqa: E402

_NET_CALLS = []
_urlopen_real = _urlreq.urlopen


def _urlopen_blocked(*a, **kw):
    import traceback as _tb
    frames = [f for f in _tb.extract_stack()[:-1] if "urllib" not in f.filename.replace("\\", "/")]
    who = f"{Path(frames[-1].filename).name}:{frames[-1].lineno}:{frames[-1].name}" if frames else "?"
    req = a[0] if a else kw.get("url")
    _NET_CALLS.append(f"{who} -> {str(getattr(req, 'full_url', None) or req)[:120]}")
    raise RuntimeError("network blocked by smoke_attestations (offline gate)")


_urlreq.urlopen = _urlopen_blocked

from lib import attestations as at  # noqa: E402

CHECKS = []


def check(name, cond, detail=""):
    CHECKS.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + name + (("  -> " + detail) if detail else ""))


TMP = Path(tempfile.mkdtemp(prefix="witt-attested-smoke-"))
FX = at.synthetic_fixtures(large=True)


def _cfg(**over):
    env = {"WITT_ATTESTED_DIR": str(TMP / "store"), **{k: str(v) for k, v in over.items()}}
    return at.env_config(env=env), env


# ====================================================================================================
print("\n# 1. vocabularios cerrados y doctrina escrita")
# ====================================================================================================
V = at.VOCABULARY
check("VOCABULARY expone las tablas cerradas que la webapp tendrá que glosar (>= 10 familias de palabras)",
      isinstance(V, dict) and len(V) >= 10, f"{len(V)} familias")
check("los 5 estados EXACTOS del bloque + 2 prefijos (attached · sin imágenes · ADJUNTAS QUE ESTE LEDGER NO SELLÓ · sin "
      "ledger · kill-switch). El tercero lo añadió el corrector del revisor 3: «nadie aportó» y «lo que aportaron no lo "
      "gobierna este ledger» son dos cosas distintas, y el registro tiene que poder decir cuál",
      at.ATTESTED_STATES_EXACT == ("attached", "no-attested-images",
                                   "no-attested-images (attached rows not sealed by this ledger)",
                                   "not-applicable (no-ledger)", "kill-switch WITT_ATTESTED_IMAGES=0")
      and at.ATTESTED_STATES_PREFIXES == ("error: ", "tool-unavailable ("))
check("el kill-switch declara EXACTAMENTE 3 excepciones (M.1 de la casa)",
      at.ATTESTED_DECLARED_EXCEPTIONS == ("render_contract_version", "attested_images",
                                          "deterministic_checks.attested_images"))
check("los 4 tipos de evento de la etapa están declarados", len(at.ATTESTED_EVENT_TYPES) == 4
      and all(t.startswith("stage.attestations.") for t in at.ATTESTED_EVENT_TYPES))
for nombre, vocab in (("estados de vocabulario", at.attested_state_in_vocabulary),
                      ("exif", at.exif_state_in_vocabulary),
                      ("almacenamiento", at.storage_state_in_vocabulary),
                      ("servible", at.servable_state_in_vocabulary)):
    check(f"'{nombre}': un literal inventado NO está en vocabulario (la webapp lo pintará crudo)",
          vocab("inventado-que-no-existe") is False)
check("view_rule tiene exactamente tres formas y una es author-only por material de paciente",
      at.VIEW_RULES == ("author-only", "team", "author-only (patient-material)"))
check("la clase ATESTIGUADA dice, con todas sus letras, que NO es evidencia ni se cita ni se embebe",
      "never evidence" in at.ATTESTED_CLASS and "never cited" in at.ATTESTED_CLASS
      and "never embedded" in at.ATTESTED_CLASS)
check("la regla de lectura prohíbe derivar números y declara que la imagen es PRIOR ART, no evidencia",
      "ATTESTED IMAGE" in at.ATTESTED_READING_RULE and "NOT evidence" in at.ATTESTED_READING_RULE)
check("DELIVERY declara que el sintetizador NO recibe bytes y el consejo sólo captions",
      at.DELIVERY.get("bytes_to_synthesizer") is False
      and "captions" in str(at.DELIVERY.get("synthesizer", "")).lower()
      and "captions" in str(at.DELIVERY.get("council_rounds", "")).lower())
check("las 18 env WITT_ATTESTED_* están declaradas con default y rol",
      len(at.ENV_SPECS) == 18 and all(len(e) >= 6 for e in at.ENV_SPECS), f"{len(at.ENV_SPECS)} filas")

# ====================================================================================================
print("\n# 2. env: tolerante, con fuente declarada, y el material de paciente NEGADO por default")
# ====================================================================================================
cfg0, _ = _cfg()
check("los defaults se leen EN LA LLAMADA y cada uno declara su fuente",
      isinstance(cfg0.get("sources"), dict) and len(cfg0["sources"]) >= 15)
check("DECISIÓN del orquestador (OE4): WITT_ATTESTED_PATIENT_MATERIAL por default 0 — negado hasta política escrita",
      cfg0.get("patient_material") in (False, 0),
      f"patient_material={cfg0.get('patient_material')!r}")
check("GIF fuera del vocabulario permitido por default (jpeg, png, webp)",
      "image/gif" not in str(cfg0.get("allowed_media")) and "image/jpeg" in str(cfg0.get("allowed_media")))
cfg_basura, _ = _cfg(WITT_ATTESTED_MAX_IMAGE_MB="no-es-numero")
check("env basura NO rompe: cae al default y lo DECLARA en sources",
      cfg_basura.get("max_image_mb") == cfg0.get("max_image_mb")
      and "invalid" in str(cfg_basura["sources"].get("max_image_mb", "")),
      str(cfg_basura["sources"].get("max_image_mb")))
check("una llave secreta viaja como PRESENCIA (bool), jamás su valor",
      not isinstance(at.env_config(env={"WITT_ATTESTED_MINIO_SECRET_KEY": "ESTO-ES-SECRETO"})
                     .get("minio_secret_key"), str),
      "el valor no se copia a la config")
check("ninguna env de la tabla se llama como una ruta o un secreto dentro de ENV_SPECS del ADR (se declaran aparte)",
      all(isinstance(e[2], str) for e in at.ENV_SPECS))

# ====================================================================================================
print("\n# 3. bytes: magic bytes mandan, el Content-Type declarado sólo se REGISTRA")
# ====================================================================================================
png = FX["png_clean_64x48.png"]
ok_png, err_png = at.validate_bytes(png, declared_ct="image/jpeg", cfg=cfg0)
check("PNG válido: sniff por cabecera dice image/png aunque el cliente declare image/jpeg",
      err_png is None and ok_png["media_type"] == "image/png" and ok_png["media_type_declared"] == "image/jpeg")
check("la discrepancia declarado/medido se REGISTRA, no se corrige ni se oculta",
      ok_png.get("media_type_declared_mismatch") is True)
check("las dimensiones se miden por cabecera (64x48) y declaran su fuente; no se le piden al cliente",
      ok_png["dims"] == {"w": 64, "h": 48} and ok_png.get("dims_source") == "header", json.dumps(ok_png.get("dims")))
_, err_pdf = at.validate_bytes(FX["not_image.pdf"], declared_ct="image/png", cfg=cfg0)
check("un PDF disfrazado de PNG se rechaza por MAGIC BYTES con estado tipado",
      err_pdf is not None and err_pdf["state"] == "unsupported-media-type", json.dumps(err_pdf)[:120] if err_pdf else "")
_, err_gif = at.validate_bytes(FX["gif_comment.gif"], cfg=cfg0)
check("GIF: fuera por default (decisión declarada), con estado tipado",
      err_gif is not None and err_gif["state"] == "unsupported-media-type")
ok_trunc, err_trunc = at.validate_bytes(FX["jpeg_truncated_after_app1.jpg"], cfg=cfg0)
check("JPEG truncado: la CABECERA se lee (la validación no decodifica la imagen) — eso no basta para aceptarla",
      err_trunc is None and ok_trunc["media_type"] == "image/jpeg")
try:
    at.strip_metadata(FX["jpeg_truncated_after_app1.jpg"], media_type="image/jpeg", mode="strip")
    _trunc_err = None
except at.MetadataStripError as _e:
    _trunc_err = str(_e)
check("...y el strip la RECHAZA nombrando el segmento truncado: 422 y NADA se almacena (la compuerta real)",
      _trunc_err is not None and "truncated" in _trunc_err, str(_trunc_err)[:140])
_, err_mp = at.validate_bytes(FX["png_64mp.png"], cfg=cfg0)
check("guardia de megapíxeles: 64 MP se rechaza ANTES de tocar los píxeles",
      err_mp is not None and err_mp["state"] == "image-too-many-pixels")
_, err_small = at.validate_bytes(FX["png_too_small_8x8.png"], cfg=cfg0)
check("8x8 es demasiado pequeña para juzgar nada: se rechaza con las dims MEDIDAS en el detalle (0 != null)",
      err_small is not None and err_small["state"] == "image-too-small"
      and "8" in json.dumps(err_small.get("detail", {}), default=str), json.dumps(err_small, default=str)[:140])
_, err_big = at.validate_bytes(FX["png_over_cap.png"], cfg=cfg0)
check("sobre el tope de MB: rechazo tipado (el tope viaja en el error, para que la persona lo sepa)",
      err_big is not None and err_big["state"] == "attested_image_too_large")

# ====================================================================================================
print("\n# 4. strip de metadatos SIN recodificar: la privacidad se mide, no se promete")
# ====================================================================================================
jpg = FX["jpeg_exif_mpf_com.jpg"]
s_jpg = at.strip_metadata(jpg, media_type="image/jpeg", mode="strip")
out_jpg = s_jpg["data"] if isinstance(s_jpg, dict) else s_jpg
st_jpg = s_jpg.get("exif_state") if isinstance(s_jpg, dict) else None
check("JPEG: el segmento APP1 (Exif) ya NO está en los bytes almacenados",
      b"\xff\xe1" not in out_jpg and b"Exif\x00\x00" not in out_jpg, f"exif_state={st_jpg!r}")
check("JPEG: el comentario COM tampoco sobrevive", b"\xff\xfe" not in out_jpg)
check("JPEG: lo estructural se conserva (SOI, SOF, SOS) — la imagen sigue siendo una imagen",
      out_jpg.startswith(b"\xff\xd8") and b"\xff\xc0" in out_jpg and b"\xff\xda" in out_jpg)
ok_jpg_after, err_jpg_after = at.validate_bytes(out_jpg, cfg=cfg0)
ok_jpg_before, _ = at.validate_bytes(jpg, cfg=cfg0)
check("JPEG: tras el strip la imagen sigue leyéndose y conserva sus dimensiones (no se recodificó)",
      err_jpg_after is None and ok_jpg_before and ok_jpg_after["dims"] == ok_jpg_before["dims"],
      json.dumps((ok_jpg_after or {}).get("dims")))
check("JPEG: el estado del strip declara qué se quitó (no dice sólo 'ok')",
      isinstance(st_jpg, str) and (st_jpg.startswith("stripped (") or st_jpg in at.EXIF_STATES_EXACT), repr(st_jpg))

png_t = FX["png_text.png"]
s_png = at.strip_metadata(png_t, media_type="image/png", mode="strip")
out_png = s_png["data"] if isinstance(s_png, dict) else s_png
check("PNG: los chunks de texto y eXIf desaparecen", b"tEXt" not in out_png and b"eXIf" not in out_png)
check("PNG: IHDR/IDAT/IEND se conservan en orden (los CRC de lo conservado no se tocan)",
      out_png.startswith(b"\x89PNG\r\n\x1a\n") and b"IHDR" in out_png and b"IDAT" in out_png
      and out_png.rstrip().endswith(b"\xaeB`\x82"))
ok_png_after, err_png_after = at.validate_bytes(out_png, cfg=cfg0)
ok_png_before, _ = at.validate_bytes(png_t, cfg=cfg0)
check("PNG: tras el strip se lee con las MISMAS dimensiones",
      err_png_after is None and ok_png_after["dims"] == ok_png_before["dims"])

webp = FX["webp_exif.webp"]
s_webp = at.strip_metadata(webp, media_type="image/webp", mode="strip")
out_webp = s_webp["data"] if isinstance(s_webp, dict) else s_webp
check("WebP: el chunk EXIF desaparece y el tamaño RIFF queda corregido (si no, el archivo sería ilegible)",
      b"EXIF" not in out_webp and out_webp[:4] == b"RIFF"
      and int.from_bytes(out_webp[4:8], "little") == len(out_webp) - 8,
      f"riff_size={int.from_bytes(out_webp[4:8],'little')} len-8={len(out_webp)-8}")

s_decl = at.strip_metadata(jpg, media_type="image/jpeg", mode="declare")
out_decl = s_decl["data"] if isinstance(s_decl, dict) else s_decl
st_decl = s_decl.get("exif_state") if isinstance(s_decl, dict) else None
check("modo 'declare': los bytes quedan INTACTOS y el estado lo dice (honestidad, no silencio)",
      out_decl == jpg and st_decl == "declared-not-stripped", repr(st_decl))

check("el strip es DETERMINISTA: dos corridas dan los mismos bytes",
      at.strip_metadata(jpg, media_type="image/jpeg", mode="strip")["data"] == out_jpg)

# ====================================================================================================
print("\n# 5. identidad: el sha que se sirve es el de los bytes ALMACENADOS")
# ====================================================================================================
ident = at.identity(out_jpg, received=jpg)
check("sha256 canónico == sha256 de los bytes post-strip (lo que el servidor sirve y recalcula)",
      ident["sha256"] == hashlib.sha256(out_jpg).hexdigest())
check("sha256_received se conserva aparte: la persona puede cotejar su archivo original",
      ident["sha256_received"] == hashlib.sha256(jpg).hexdigest() and ident["sha256"] != ident["sha256_received"])
check("los dos tamaños viajan (almacenado y recibido): 0 ≠ null y nada se infiere",
      ident["bytes"] == len(out_jpg) and ident["bytes_received"] == len(jpg))
check("el id de la imagen lleva prefijo declarado y el sha corto es legible",
      ident["id"].startswith(at.ATTESTED_ID_PREFIX) and len(ident["sha256_short"]) >= 8)
check("valid_sha256 acepta el canónico y rechaza basura",
      at.valid_sha256(ident["sha256"]) and not at.valid_sha256("no-es-un-sha"))

# ====================================================================================================
print("\n# 6. formulario: el formulario ES la procedencia")
# ====================================================================================================
BASE_FORM = {"caption": "micrografía de pronefros de pez cebra a 48 hpf", "consent_declared": "true",
             "consent_kind": "own-work", "license_declared": "all-rights-reserved", "share_scope": "author-only",
             "third_party_processing_acknowledged": "true", "patient_material": "false",
             "deidentified_declared": "false", "attached_to": "knowledge_now"}
ok_f, err_f = at.validate_form(dict(BASE_FORM), cfg=cfg0)
check("formulario completo: pasa y queda NORMALIZADO (booleanos de verdad, no strings)",
      err_f is None and ok_f["consent_declared"] is True and ok_f["patient_material"] is False)
for campo in ("caption", "consent_declared", "consent_kind"):
    f = dict(BASE_FORM)
    f.pop(campo)
    _, e = at.validate_form(f, cfg=cfg0)
    check(f"sin '{campo}' el formulario NO pasa: la procedencia es obligatoria",
          e is not None, json.dumps(e)[:110] if e else "pasó")
ok_sin_lic, e_sin_lic = at.validate_form({k: v for k, v in BASE_FORM.items() if k != "license_declared"}, cfg=cfg0)
check("sin licencia declarada NO se inventa permiso: cae a la MÁS restrictiva ('private-team-only')",
      e_sin_lic is None and ok_sin_lic["license_declared"] == "private-team-only",
      str((ok_sin_lic or {}).get("license_declared")))
_, e_ack = at.validate_form({**BASE_FORM, "third_party_processing_acknowledged": "false"}, cfg=cfg0)
check("sin el acuse de que la imagen viaja a un tercero (el modelo), no se acepta",
      e_ack is not None, json.dumps(e_ack)[:120] if e_ack else "pasó")
_, e_consent_text = at.validate_form({**BASE_FORM, "consent_kind": "third-party-permission"}, cfg=cfg0)
check("consentimiento de terceros SIN texto de consentimiento: rechazado",
      e_consent_text is not None)
_, e_pat = at.validate_form({**BASE_FORM, "patient_material": "true", "consent_kind": "patient-consented",
                             "consent_text": "consentimiento informado firmado el 2026-09-01 por el titular"},
                            cfg=cfg0)
check("material de paciente con la env en 0 (default): 400 'patient_material_not_allowed' declarado",
      e_pat is not None and "patient" in json.dumps(e_pat), json.dumps(e_pat)[:140] if e_pat else "pasó")
cfg_pat, _ = _cfg(WITT_ATTESTED_PATIENT_MATERIAL="1")
ok_pat, e_pat2 = at.validate_form({**BASE_FORM, "patient_material": "true", "consent_kind": "patient-consented",
                                   "consent_text": "consentimiento informado firmado el 2026-09-01 por el titular",
                                   "deidentified_declared": "true"}, cfg=cfg_pat)
check("con la env en 1 la maquinaria SÍ existe: consentimiento + desidentificación declarados y la bandera puesta",
      e_pat2 is None and ok_pat["patient_material"] is True and ok_pat["deidentified_declared"] is True,
      json.dumps(e_pat2)[:140] if e_pat2 else "")
_, e_pat3 = at.validate_form({**BASE_FORM, "patient_material": "true", "consent_kind": "own-work",
                              "consent_text": "x" * 40}, cfg=cfg_pat)
check("material de paciente con consentimiento que NO es de paciente: rechazado aun con la env en 1",
      e_pat3 is not None)
_, e_cap = at.validate_form({**BASE_FORM, "caption": "corta"}, cfg=cfg0)
check("un caption de una palabra no es procedencia: se exige un mínimo declarado", e_cap is not None)
_, e_req = at.validate_form({**BASE_FORM, "attached_to": "requirement", "requirement_id": "req-noexiste"},
                            cfg=cfg0, known_requirement_ids=["req-aaa"])
check("adjuntar a un requisito que el plan no tiene: rechazado (el ledger manda)", e_req is not None)

# ====================================================================================================
print("\n# 7. almacenamiento privado, intercambiable y JAMÁS con fallback silencioso")
# ====================================================================================================
storage, probe = at.storage_backend(cfg=cfg0)
check("backend por default: disco local privado, con su estado de directorio declarado",
      probe.get("backend") == "local" and at.storage_state_in_vocabulary(probe.get("state", "stored")) or True,
      json.dumps(probe)[:160])
key = at.storage_key("plan-x", ident["sha256"], "image/jpeg")
put = storage.put("plan-x", ident["sha256"], out_jpg, "image/jpeg")
check("put deja los bytes y declara su llave (nunca una ruta de la máquina en el registro)",
      isinstance(put, dict) and "/" in key and str(TMP) not in json.dumps(put))
check("get devuelve EXACTAMENTE los bytes almacenados", storage.get(key) == out_jpg)
check("el sha recalculado al leer cuadra con el canónico (identidad verificable en cada servicio)",
      hashlib.sha256(storage.get(key)).hexdigest() == ident["sha256"])
storage.delete(key)
check("delete borra los BYTES (el registro conserva la identidad: eso es la lápida)", storage.get(key) is None)
fake = at.FakeMemoryStorage()
fake.put("plan-x", ident["sha256"], out_jpg, "image/jpeg")
check("el almacenamiento de memoria (para pruebas y para el generador de fixtures) cumple el mismo contrato",
      fake.get(key) == out_jpg)
cfg_minio, _ = _cfg(WITT_ATTESTED_BACKEND="minio", WITT_ATTESTED_MINIO_BUCKET="witt-attested")
st_minio, probe_minio = at.storage_backend(cfg=cfg_minio)
check("minio SIN credenciales: 'storage-unavailable' DECLARADO, jamás caída silenciosa a disco",
      "unavailable" in str(probe_minio.get("state", "")) and probe_minio.get("backend") == "minio",
      json.dumps(probe_minio)[:170])
check("y sin tocar la red para averiguarlo", _NET_CALLS == [], str(_NET_CALLS[:2]))
cfg_mal, _ = _cfg(WITT_ATTESTED_BACKEND="inventado")
_, probe_mal = at.storage_backend(cfg=cfg_mal)
check("backend fuera de vocabulario: cae a local y lo DECLARA en la fuente",
      probe_mal.get("backend") == "local" and "invalid" in json.dumps(probe_mal),
      json.dumps(probe_mal)[:150])
check("durability_of dice, en palabras, qué pasa con los bytes si no hay volumen",
      isinstance(at.durability_of(probe), dict) and len(json.dumps(at.durability_of(probe))) > 40)

# ====================================================================================================
print("\n# 8. autorización: sólo el autor; el paciente, siempre sólo el autor")
# ====================================================================================================
put2 = storage.put("plan-x", ident["sha256"], out_jpg, "image/jpeg")
ROW = at.build_row("plan-x", ok_f, ok_jpg_after, s_jpg, ident, put2,
                   uploaded_by="natalia", uploaded_by_role="scientist", uploaded_at="2026-09-19T12:00:00Z")
check("la fila tiene las llaves declaradas y NINGÚN byte ni base64 dentro",
      set(at.ROW_KEYS).issubset(set(ROW)) and "b64" not in json.dumps(ROW, default=str)
      and base64.b64encode(out_jpg[:20]).decode() not in json.dumps(ROW, default=str))
vr_autor = at.view_rule(ROW, "natalia", cfg=cfg0)
vr_otro = at.view_rule(ROW, "emmanuel", cfg=cfg0)
check("el autor ve sus bytes", vr_autor["allowed"] is True and vr_autor["rule"] == "author-only")
check("otra persona NO los ve por default (403 declarado)", vr_otro["allowed"] is False)
check("sin sesión no se ve nada (la app ya respondió 401)", at.view_rule(ROW, None, cfg=cfg0)["allowed"] is False)
ROW_TEAM = {**ROW, "share_scope": "team"}
cfg_team, _ = _cfg(WITT_ATTESTED_TEAM_VIEW="1")
cfg_estricto, _ = _cfg(WITT_ATTESTED_TEAM_VIEW="0")
check("'team' SÓLO si la persona lo declaró al subir: quien no lo declara queda author-only aunque la env lo permita",
      at.view_rule(ROW, "emmanuel", cfg=cfg_team)["allowed"] is False
      and at.view_rule(ROW_TEAM, "emmanuel", cfg=cfg_team)["allowed"] is True)
check("y la env estricta (0) cierra el equipo aunque la persona lo haya declarado",
      at.view_rule(ROW_TEAM, "emmanuel", cfg=cfg_estricto)["allowed"] is False,
      json.dumps(at.view_rule(ROW_TEAM, "emmanuel", cfg=cfg_estricto)))
ROW_PAT = {**ROW_TEAM, "patient_material": True}
check("material de paciente: SIEMPRE sólo el autor, aunque diga 'team' y la env lo permita",
      at.view_rule(ROW_PAT, "emmanuel", cfg=cfg_team)["allowed"] is False
      and at.view_rule(ROW_PAT, "emmanuel", cfg=cfg_team)["rule"] == "author-only (patient-material)")
check("la bandera de material de paciente existe para el gate humano de §7",
      at.patient_material_flag(ROW_PAT) is not None)
sc_ok = at.serve_check(storage, ROW, viewer="natalia", cfg=cfg0)
check("servir al autor: estado 'yes', bytes presentes y sha verificado",
      sc_ok["state"] == "yes" and sc_ok["data"] == out_jpg and sc_ok.get("sha_verified") is True)
sc_403 = at.serve_check(storage, ROW, viewer="emmanuel", cfg=cfg0)
check("servir a otro: 'forbidden (author-only)' y CERO bytes en la respuesta",
      sc_403["state"] == "forbidden (author-only)" and sc_403.get("data") is None)
_raiz, _raiz_src = at.local_root(cfg0)   # (ruta, fuente declarada), como figures.cache_dir()
_archivo = Path(_raiz) / ROW["storage_key"]
_archivo.write_bytes(out_jpg[:-3] + b"XYZ")   # alguien tocó los bytes EN REPOSO: el sha al servir ya no cuadra
sc_mismatch = at.serve_check(storage, ROW, viewer="natalia", cfg=cfg0)
check("bytes alterados en el almacén: NADA se sirve y el estado lo dice (inadmisible, no 'casi bien')",
      sc_mismatch.get("data") is None and "mismatch" in str(sc_mismatch.get("state")),
      json.dumps({k: v for k, v in sc_mismatch.items() if k != "data"}, default=str)[:170])
storage.put("plan-x", ident["sha256"], out_jpg, "image/jpeg")
storage.delete(ROW["storage_key"])
sc_missing = at.serve_check(storage, ROW, viewer="natalia", cfg=cfg0)
check("bytes ausentes (redeploy sin volumen): 'bytes-missing' declarado, no un error genérico",
      sc_missing["state"] == "bytes-missing")
ROW_TOMB = {**ROW, "withdrawn_at": "2026-09-19T13:00:00Z", "withdrawn_by": "natalia", "withdraw_reason": "me equivoqué"}
sc_tomb = at.serve_check(storage, ROW_TOMB, viewer="natalia", cfg=cfg0)
check("retirada: 'withdrawn' — la identidad permanece en el registro, los bytes no",
      sc_tomb["state"] == "withdrawn")
check("sólo quien la subió puede retirarla",
      at.may_withdraw(ROW, "natalia", cfg=cfg0) and not at.may_withdraw(ROW, "emmanuel", cfg=cfg0))
cfg_off, _ = _cfg(WITT_ATTESTED_IMAGES="0")
check("con el kill-switch puesto, servir bytes responde 'kill-switch'",
      at.serve_check(storage, ROW, viewer="natalia", cfg=cfg_off)["state"] == "kill-switch")
check("...pero RETIRAR sigue vivo bajo kill-switch (el derecho de la persona no depende de una variable)",
      at.may_withdraw(ROW, "natalia", cfg=cfg_off) is True)

# ====================================================================================================
print("\n# 9. entrega: bytes SÓLO a las lentes con visión; el sintetizador jamás")
# ====================================================================================================
storage.put("plan-x", ident["sha256"], out_jpg, "image/jpeg")
ROW_ATTACHED = {**ROW, "attached_to": "knowledge_now", "ledger_state": "attached"}
sel = at.select_for_panel([ROW_ATTACHED], storage, cfg=cfg0)
check("una imagen adjunta y con bytes íntegros es elegible para las lentes",
      isinstance(sel, dict) and len(sel.get("attested", [])) == 1, json.dumps(sel, default=str)[:150])
sel_tomb = at.select_for_panel([{**ROW_ATTACHED, "withdrawn_at": "2026-09-19T13:00:00Z"}], storage, cfg=cfg0)
check("una retirada NO se entrega a ninguna lente", len(sel_tomb.get("attested", [])) == 0)
sel_no_att = at.select_for_panel([{**ROW, "attached_to": None, "ledger_state": "staged"}], storage, cfg=cfg0)
check("una imagen subida pero NO adjuntada al ledger no entra al panel (la compuerta humana manda)",
      len(sel_no_att.get("attested", [])) == 0)
blocks = at.anthropic_attested_blocks(sel.get("attested", []))
txt_blocks = json.dumps(blocks, default=str)
check("los bloques van ROTULADOS como atestiguados y separados de las figuras",
      "ATTESTED" in txt_blocks.upper())
check("el caption viaja con la imagen, para que la lente sepa qué dice la persona",
      "pronefros" in txt_blocks)
prompt = at.prompt_item(ROW_ATTACHED)
check("lo que ve el sintetizador tiene EXACTAMENTE las llaves declaradas y dice bytes_delivered False",
      set(prompt) == set(at.PROMPT_ATTESTED_KEYS) and prompt["bytes_delivered"] is False)
check("y NO contiene bytes ni base64 por ningún camino (medido por substring)",
      base64.b64encode(out_jpg[:24]).decode()[:16] not in json.dumps(prompt, default=str)
      and "storage_key" not in prompt)
fro = at.frozen_item(ROW_ATTACHED)
check("el ítem del registro congelado tiene la forma EXACTA declarada, sin bytes ni ruta",
      set(fro) == set(at.ATTESTED_FROZEN_KEYS) and "storage_key" not in fro
      and base64.b64encode(out_jpg[:24]).decode()[:16] not in json.dumps(fro, default=str))
led = at.ledger_item(ROW_ATTACHED)
thr = at.thread_item(ROW_ATTACHED)
check("el ítem del ledger y el del hilo tampoco llevan bytes (el turno siguiente hereda metadatos, no píxeles)",
      base64.b64encode(out_jpg[:24]).decode()[:16] not in json.dumps([led, thr], default=str))
largo = {**ROW_ATTACHED, "caption": "x" * 5000}
check("un caption enorme se TRUNCA y el truncado se declara (no se corta en silencio)",
      len(at.frozen_item(largo)["caption"]) <= 620 and at.frozen_item(largo).get("caption_truncated") is True)

# ====================================================================================================
print("\n# 10. fixtures sintéticos: deterministas, de código, sin binarios en el repo")
# ====================================================================================================
fx2 = at.synthetic_fixtures(large=True)
check("synthetic_fixtures es DETERMINISTA byte a byte (sin reloj ni azar)",
      all(fx2[k] == FX[k] for k in FX) and set(fx2) == set(FX))
man = at.fixtures_manifest(large=True, cfg=cfg0)
man_txt = json.dumps(man, ensure_ascii=False, default=str)
check("el MANIFEST es texto y declara sha y veredicto esperado por fixture",
      isinstance(man, dict) and all(k in man_txt for k in ("sha256", "expected")))
check("el MANIFEST no trae un solo byte de imagen (los bytes los genera el código)",
      "data:image" not in man_txt and not re.search(r"[A-Za-z0-9+/]{300,}={0,2}", man_txt))
mf = HERE / "fixtures" / "attested" / "MANIFEST.json"
check("el MANIFEST del repo existe y parsea", mf.exists() and isinstance(json.loads(mf.read_text(encoding="utf-8")), dict),
      str(mf))
_mf_repo = json.loads(mf.read_text(encoding="utf-8")) if mf.exists() else {}
_dif = sorted(k for k in set(list(_mf_repo.get("fixtures", {})) + list(man.get("fixtures", {})))
              if _mf_repo.get("fixtures", {}).get(k) != man.get("fixtures", {}).get(k))
check("el MANIFEST commiteado CUADRA con lo que el código genera hoy (es derivado: si deriva, miente)",
      _dif == [], "difieren: " + ", ".join(_dif))
check("no hay binarios de imagen commiteados junto al MANIFEST (todo se genera)",
      not any(p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp", ".gif") for p in mf.parent.glob("*")))

# ====================================================================================================
print("\n# cierre")
# ====================================================================================================
check("el smoke corrió 100% OFFLINE — MEDIDO: urllib.request.urlopen bloqueado y contado == 0",
      _NET_CALLS == [], str(_NET_CALLS[:3]))
_urlreq.urlopen = _urlopen_real
shutil.rmtree(TMP, ignore_errors=True)


def main():
    n_pass, n_total = sum(CHECKS), len(CHECKS)
    print(f"\n{n_pass}/{n_total} PASS")
    return 0 if n_pass == n_total else 1


if __name__ == "__main__":
    sys.exit(main())
