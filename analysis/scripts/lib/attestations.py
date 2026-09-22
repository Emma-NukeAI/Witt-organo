"""
attestations.py — imágenes ATESTIGUADAS del laboratorio (ADR-0086, contrato 1.14, rebanada F1: la INTERFAZ congelada).

Una imagen que aporta una persona es ATESTIGUADA (clase atestiguada; procedencia registrada: quién, cuándo, con qué
consentimiento y licencia declarada), JAMÁS evidencia, medición ni cita (CLAUDE.md §7; ADR-0082 F; ADR-0083). Vive en
`human_attestations.images[]` (llave HERMANA de `evidence`), sus bytes viven FUERA del registro congelado (ADR-0074) en
almacenamiento PRIVADO (disco local declarado → MinIO privado), los ven a lo sumo las DOS lentes de visión del panel como
JUICIO (`attested_readings`, class model-judgment) y NUNCA el sintetizador (captions + metadatos rotulados, cero bytes);
se sirven sólo al autor por default (403), jamás en el PDF, y se retiran por tombstone (410) sin tocar el registro.

Qué hay aquí (ADR-0086 (A)):
  A.1  vocabularios CERRADOS + literales (VOCABULARY, ATTESTED_DECLARED_EXCEPTIONS, ATTESTED_READING_RULE, …)
  A.2  ENV_SPECS (18 WITT_ATTESTED_*: 15 de tabla + 3 fuera de tabla: ruta y secretos) + env_config() tolerante
  A.3  validate_form(fields, cfg)          formulario OBLIGATORIO = la procedencia; 400 tipado por campo
  A.4  validate_bytes(data, declared, cfg) magic bytes → media_type; dims por cabecera; 40 MP; mínimo; tope MB
  A.5  strip_metadata(data, media_type)    walkers stdlib JPEG / PNG / WebP / GIF SIN recodificar; fallo → MetadataStripError
  A.6  identity(stored, received)          sha256 canónico POST-strip + sha256_received; id 'attested:<sha12>'
  A.7  Storage / LocalStorage / MinioStorage / FakeMemoryStorage / storage_backend(cfg)  — JAMÁS fallback silencioso
  A.8  serve_check(storage, row, …)        relee fila viva, backend DE LA FILA, sha recalculado sobre lo que sale
  A.9  select_for_panel(items, storage, …) lo que ven las DOS lentes (b64), cap compartido con figuras, many-image guard
  A.10 attested_text_label / attested_separator_text / bloques ATTESTED por transporte (figuras → separador → [rótulo, imagen] × N)
  A.11 prompt_item / frozen_item / public_item / ledger_item / thread_item / patient_material_flag  (proyecciones SIN bytes)
  A.12 ATTESTED_READING_RULE (literal congelado en frozen.attested_images.vision.rule)
  A.13 synthetic_fixtures() + fixtures_manifest()  — bytes SINTÉTICOS generados por código; CERO binarios en git

stdlib puro (hashlib, struct, io, os, json, re, time, base64, zlib, pathlib). Importa de figures SÓLO sniff_mime /
image_dims / MEDIA_TYPES / MAX_MEGAPIXELS / REQUEST_B64_MB / CHUNK_BYTES. `from minio import Minio` es PEREZOSO (patrón
raw_store._client) y sólo ocurre con MINIO_* configurado. Nada aquí toca la DATA INAMOVIBLE ni `mcp_cache/` (caché ≠
almacenamiento: la raíz local por default es <repo>/attested_private, en .gitignore).
"""
import base64
import hashlib
import io
import json
import os
import re
import stat as _stat
import struct
import sys
import time
import zlib
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2].parent
sys.path.insert(0, str(ROOT / "analysis" / "scripts"))
from lib import figures as _figures  # noqa: E402  (sniff_mime / image_dims / MEDIA_TYPES / MAX_MEGAPIXELS / REQUEST_B64_MB)

sniff_mime = _figures.sniff_mime
image_dims = _figures.image_dims
MEDIA_TYPES = _figures.MEDIA_TYPES
MAX_MEGAPIXELS = _figures.MAX_MEGAPIXELS
REQUEST_B64_MB = _figures.REQUEST_B64_MB
CHUNK_BYTES = _figures.CHUNK_BYTES

# ---------------------------------------------------------------------------------------------------------
# A.1 Versiones, clase, literales
# ---------------------------------------------------------------------------------------------------------
MODULE_VERSION = "att-1"
ATTESTED_CLASS = ("attested (human-provided; provenance recorded: uploader, time, consent, declared license; "
                  "never evidence, never cited, never embedded)")
ATTESTED_ID_PREFIX = "attested:"
SHA_SHORT = 12
CONSTANT_SOURCE = "constant (ADR-0086)"

# Constantes declaradas (viajan en `caps`/`constants` con source CONSTANT_SOURCE)
FORM_OVERHEAD_BYTES = 64 * 1024        # C.2: max_body_bytes = max_image_mb·2^20 + FORM_OVERHEAD
FROZEN_CAPTION_CHARS = 600             # caption ≤ 600 en el frozen (caption_truncated)
THREAD_CAPTION_CHARS = 200             # ≤ 200 en thread_context.parent_attested_images[]
CAPTION_MIN_CHARS = 10
CONSENT_TEXT_CHARS = 600
FROZEN_CONSENT_TEXT_CHARS = 300
CONSENT_TEXT_MIN_CHARS = 20
DATE_TAKEN_CHARS = 32
METHOD_CHARS = 300
MANY_IMAGE_LIMIT = 20                  # Context 9: > 20 imágenes por petición ⇒ cada una ≤ 2000 px (régimen many-image)
MIN_DIM_PX = 16
MAX_IMAGE_MB_CLAMP = (0.1, 7.0)        # 7 MB ≈ 9.3 MB b64 < 10 MB/imagen de la API

# (L) `frozen.attested_images.rule` y `delivery` — literales
FROZEN_RULE = ("human-provided images are ATTESTED prior art: never evidence, never cited, never embedded, never "
               "redistributed; bytes only to <= 2 vision lenses (judgment); synthesizer and council see captions only")
DELIVERY = {"synthesizer": "captions-only (human_attestations.images[])", "bytes_to_synthesizer": False,
            "council_rounds": "captions-only", "panel": "bytes to <= 2 vision lenses", "pdf": "never"}
AGENT_DESCRIPTION = ("attestations (lib/attestations.py — human-provided images: magic bytes + sha256 + metadata strip + "
                     "private storage; bytes to ≤2 vision lenses only)")
HUMAN_ATTESTATIONS_IMAGES_RULE = ("human-provided images are described ONLY by their human captions; the synthesizer "
                                  "never receives them")
SELECTION_RULE = ("attached ∧ not withdrawn ∧ stored ∧ sha256 recomputed ok ∧ bytes <= max_image_mb; upload order; "
                  "figures first in the shared 8 MB b64 request cap; figures + attested <= 20 (many-image guard)")
SERVABLE_RULE = ("bytes are served only to the uploader by default (share_scope 'team' honoured only when declared by the "
                 "uploader and WITT_ATTESTED_TEAM_VIEW=1; patient material is always author-only); sha256 recomputed on "
                 "the bytes that leave; withdrawn = 410 tombstone; never in the PDF; never presigned")
# (C.4) aviso literal que el formulario muestra y `third_party_processing_acknowledged` acusa
THIRD_PARTY_NOTICE_ES = (
    "Esta imagen NO es evidencia: el modelo que redacta recibe SÓLO tu caption y metadatos; sus BYTES los verán a lo sumo "
    "dos lentes del panel y para ello SALEN a los proveedores de esas lentes (Anthropic — procesamiento efímero, sin "
    "entrenamiento, según su documentación; OpenAI con `WITT_OPENAI_STORE=0`); el CAPTION NO es privado: lo lee toda "
    "sesión del equipo, el sintetizador y los miembros del consejo; la imagen jamás sale en el PDF ni se redistribuye; "
    "puedes retirar los bytes cuando quieras (queda constancia: sha y metadatos).")
# (E.2) nota de durabilidad cuando backend local y dir_source 'default'
DURABILITY_NOTE_LOCAL_DEFAULT = (
    "el directorio por default vive DENTRO del contenedor: sin volumen montado los bytes se pierden en el siguiente "
    "redeploy (el registro sha/metadatos permanece); monta un volumen o fija WITT_ATTESTED_DIR")
# (H.2) nota del tombstone cuando el panel ya la vio
WITHDRAWN_NOTE_TEMPLATE = "bytes already shown to {lenses} in run {run_id}; irreversible"
WITHDRAWN_NOTE_UNSEEN = "bytes never shown to any lens"
# (A.12) LA REGLA, literal: va al system de las lentes que reciben imágenes atestiguadas y congelada en
# frozen.attested_images.vision.rule (F3 la importa; F4 la congela).
ATTESTED_READING_RULE = (
    "You may be shown images labelled ATTESTED IMAGE: they were provided by a person as PRIOR ART and are NOT evidence. "
    "Use them ONLY to judge whether the claim is consistent with what the person says they show. NEVER derive, read off "
    "or estimate numbers, counts, sizes or statistics from an attested image; never treat one as support for any "
    "citation; never cite one. Report anything you conclude from an attested image ONLY in `attested_readings` — it is "
    "model judgment, never a measurement; never in `caught`, `reasons` or `correction_applied`. You are not a diagnostic "
    "tool: never interpret patient material clinically.")
# (A.10) rótulo y separador de bloques
ATTESTED_SEPARATOR_TEXT = ("HUMAN-ATTESTED IMAGES follow — prior art provided by a person, never evidence; judge them ONLY "
                           "per the attested-image rule.")
attested_separator_text = ATTESTED_SEPARATOR_TEXT

# ---------------------------------------------------------------------------------------------------------
# A.1 Vocabularios CERRADOS (exportados para el gate de paridad; viajan en frozen.attested_images.vocabulary)
# ---------------------------------------------------------------------------------------------------------
ATTESTED_STATES_EXACT = ("attached", "no-attested-images",
                         # (corrector revisor 3, A3) había filas ADJUNTAS en la base que el ledger VIGENTE no selló —
                         # porque se aprobó y luego se saltó el consejo, o porque el sello se escribió y el ledger no.
                         # No entran a la corrida, y el registro lo DICE: «nadie aportó» y «lo que aportaron no lo
                         # gobierna este ledger» son dos cosas distintas.
                         "no-attested-images (attached rows not sealed by this ledger)",
                         "not-applicable (no-ledger)", "kill-switch WITT_ATTESTED_IMAGES=0")
ATTESTED_STATES_PREFIXES = ("error: ", "tool-unavailable (")
STORAGE_BACKENDS = ("local", "minio")
STORAGE_STATES = ("stored", "bytes-missing", "withdrawn (tombstone)", "mismatch", "backend-not-configured-now",
                  "storage-unavailable", "not-probed")
STORAGE_STATES_PREFIXES = ("storage-unavailable (", "withdrawn (tombstone; delete-pending: ", "error: ")
DIR_STATES = ("writable", "read-only", "missing", "permissions-not-applied (win32)")
DIR_SOURCES = ("env", "default", "injected")
EXIF_STATES_EXACT = ("none-found", "declared-not-stripped", "strip-failed")
EXIF_STATES_PREFIXES = ("stripped (",)
EXIF_MODES = ("strip", "declare")
CONSENT_KINDS = ("own-work", "lab-internal", "third-party-permission", "patient-consented", "public-domain")
CONSENT_TEXT_REQUIRED_KINDS = ("third-party-permission", "patient-consented")
SHARE_SCOPES = ("author-only", "team")
# Vocabulario PROPIO (no figures.LICENSES: zfin-display-only/unknown/cc-by-prose-unconfirmed no aplican a una foto humana)
LICENSES_DECLARED = ("private-team-only", "cc-by", "cc0", "cc-by-sa", "cc-by-nc", "cc-by-nd", "cc-by-nc-sa", "cc-by-nc-nd",
                     "all-rights-reserved", "other-declared")
LEDGER_IMAGE_STATES = ("staged", "attached", "withdrawn-before-approve", "withdrawn-before-run", "inherited")
SERVABLE_STATES = ("yes", "forbidden (author-only)", "withdrawn", "bytes-missing", "bytes-mismatch",
                   "backend-not-configured-now", "storage-unavailable", "kill-switch")
SAW_ATTESTED_DETAILS = ("sent", "lens-not-in-vision-lenses", "kill-switch WITT_ATTESTED_VISION=0",
                        "kill-switch WITT_FIGURES_VISION=0", "no-eligible-images", "model-vision-unknown",
                        "api-form-not-verified")
VIEW_RULES = ("author-only", "team", "author-only (patient-material)")
WITHDRAW_POLICIES = ("uploader", "team")          # valores de WITT_ATTESTED_WITHDRAW (quién puede retirar)
ATTACHED_TO_KNOWLEDGE_NOW = "knowledge_now"
ATTACHED_TO_REQUIREMENT_PREFIX = "requirement:"
ATTESTED_EVENT_TYPES = ("stage.attestations.plan", "stage.attestations.image", "stage.attestations.summary",
                        "stage.attestations.panel")
PLAN_EVENT_TYPES = ("attestation.uploaded", "attestation.inherited", "attestation.withdrawn", "attestation.bytes_served")
PLAN_EVENT_AGENT = "attestations"
FLAG_EMITTED_BY = "attestations (human-upload)"
FLAG_SOURCE = "human-upload"
# (corrector R1) por qué la bandera no lleva el caption: viaja al PDF y al prompt del turno siguiente
CAPTION_OMITTED_REASON = ("el caption no viaja en la bandera: ésta llega al PDF del servidor y al contexto del turno "
                          "siguiente; para leerlo hay que pedir el ítem por su puerta, con su autorización (ADR-0086 I.iii, "
                          "corregido 2026-09-21)")
# (N.1) las EXACTAMENTE 3 excepciones del kill-switch — el literal vive aquí y `runs` lo importa
ATTESTED_DECLARED_EXCEPTIONS = ("render_contract_version", "attested_images", "deterministic_checks.attested_images")
# Forma EXACTA de las proyecciones (el orden de llaves es contrato para F2–F8 y la webapp)
ATTESTED_FROZEN_KEYS = (
    "id", "sha256", "sha256_short", "sha256_received", "bytes", "bytes_received", "media_type", "media_type_declared",
    "media_type_declared_mismatch", "dims", "dims_source", "caption", "caption_truncated", "caption_chars", "requirement_id",
    "attached_to", "attached_by", "attached_by_is_uploader", "date_taken", "method", "consent", "third_party_ack",
    "patient_material", "deidentified_declared", "license_declared", "share_scope", "exif_state", "exif_removed",
    "uploaded_by", "uploaded_by_role", "uploaded_at", "plan_id", "ledger_state", "inherited_from", "storage", "withdrawn",
    "seen_by_lenses", "n_readings", "delivered_to_synthesizer", "class")
ATTESTED_ITEM_KEYS = ATTESTED_FROZEN_KEYS + ("viewer_may_view", "view_rule", "servable", "url", "withdraw_url")
ATTESTED_LEDGER_ITEM_KEYS = (
    "id", "sha256", "sha256_short", "attached_to", "requirement_id", "caption", "caption_truncated", "media_type", "dims",
    "bytes", "consent", "patient_material", "deidentified_declared", "license_declared", "share_scope", "exif_state",
    "uploaded_by", "uploaded_at", "attached_by_is_uploader", "ledger_state", "class")
THREAD_ITEM_KEYS = ("id", "sha256_short", "caption", "caption_truncated", "by", "at", "consent_kind", "patient_material",
                    "seen_by_lenses", "class")
# (G.2 / K.4) lo que viaja al `member` de una lente con visión — `uploaded_by`/`uploaded_at` porque el rótulo los lleva
PANEL_ATTESTED_KEYS = ("id", "sha256", "sha256_short", "caption", "media_type", "b64", "dims", "consent_kind",
                       "uploaded_by", "uploaded_at", "class")
# (K.2) lo ÚNICO que ve el sintetizador y el consejo por imagen
PROMPT_ATTESTED_KEYS = ("id", "sha256_short", "caption", "media_type", "dims", "requirement_id", "attached_to", "consent",
                        "patient_material", "license_declared", "uploaded_by", "uploaded_at", "class", "bytes_delivered")
FORBIDDEN_ATTESTED_PROMPT_KEYS = ("b64", "data", "bytes_b64", "storage_key", "path", "cache_path")
assert not set(PROMPT_ATTESTED_KEYS) & set(FORBIDDEN_ATTESTED_PROMPT_KEYS)
assert not set(ATTESTED_FROZEN_KEYS) & set(FORBIDDEN_ATTESTED_PROMPT_KEYS)
# Fila de `plan_attested_images` como dict (F.1) — la forma que consumen frozen_item/public_item/prompt_item
ROW_KEYS = (
    "image_id", "plan_id", "sha256", "sha256_received", "bytes", "bytes_received", "media_type", "media_type_declared",
    "dims_w", "dims_h", "caption", "caption_chars", "consent_kind", "consent_declared", "consent_text", "third_party_ack",
    "patient_material", "deidentified_declared", "license_declared", "share_scope", "requirement_id", "date_taken", "method",
    "exif_state", "exif_removed_json", "storage_backend", "storage_key", "storage_state", "uploaded_by", "uploaded_by_role",
    "uploaded_at", "attached_to", "attached_at", "attached_by", "inherited_from_plan_id", "inherited_from_run_id",
    "withdrawn_by", "withdrawn_at", "withdraw_reason", "withdraw_cascade_n")
# (C.4) 400 tipados por campo del formulario — vocabulario CERRADO
FORM_ERROR_STATES = (
    "caption-missing", "caption-too-long", "invalid-consent-kind", "consent-not-declared", "consent_text-required",
    "consent_text-too-long", "third_party_processing_not_acknowledged", "patient_material-required",
    "patient_material_not_allowed", "patient_material_without_consent", "patient_material_not_deidentified",
    "invalid-license", "invalid-share-scope", "unknown_requirement_id", "invalid-date_taken", "method-too-long")
BYTES_ERROR_STATES = ("unsupported-media-type", "undecodable-header", "image-too-many-pixels", "image-too-small",
                      "attested_image_too_large", "metadata-strip-failed")
# `detail.state` de las 7 rutas (L.HTTP) — para el gate de paridad (W5) y las glosas de la webapp
HTTP_DETAIL_STATES = {
    400: FORM_ERROR_STATES + ("bad-sha256", "withdraw_without_reason", "attested_image_not_inheritable",
                              "unknown_attested_image", "attested_image_withdrawn", "duplicated_attested_image",
                              "images_without_aporto", "too_many_attested_images", "attested_images_disabled",
                              "patient_material_unacknowledged"),
    403: ("forbidden (author-only)", "inherit-not-uploader", "withdraw-not-uploader"),
    404: ("plan_not_found", "bytes-missing", "backend-not-configured-now", "kill-switch WITT_ATTESTED_IMAGES=0"),
    409: ("plan_already_used", "attestations_require_ledger", "attested_images_disabled", "attested_image_already_uploaded",
          "attestations_cap_reached", "attested-bytes-mismatch", "already-withdrawn"),
    410: ("withdrawn",),
    413: ("attested_image_too_large",),
    415: ("unsupported-media-type",),
    422: ("undecodable-header", "image-too-many-pixels", "image-too-small", "metadata-strip-failed"),
    429: ("upload-rate-limited",),
    503: ("attested-storage-unavailable", "attested-db-unavailable"),
}
EXT_BY_MEDIA = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp", "image/gif": "gif"}
DEFAULT_ALLOWED_MEDIA = "image/jpeg,image/png,image/webp"     # GIF fuera por default (Context 9: ambigüedad de frame)

VOCABULARY = {
    "ATTESTED_STATES_EXACT": ATTESTED_STATES_EXACT, "ATTESTED_STATES_PREFIXES": ATTESTED_STATES_PREFIXES,
    "STORAGE_BACKENDS": STORAGE_BACKENDS, "STORAGE_STATES": STORAGE_STATES, "DIR_STATES": DIR_STATES,
    "EXIF_STATES_EXACT": EXIF_STATES_EXACT, "EXIF_STATES_PREFIXES": EXIF_STATES_PREFIXES, "CONSENT_KINDS": CONSENT_KINDS,
    "SHARE_SCOPES": SHARE_SCOPES, "LICENSES_DECLARED": LICENSES_DECLARED, "LEDGER_IMAGE_STATES": LEDGER_IMAGE_STATES,
    "SERVABLE_STATES": SERVABLE_STATES, "SAW_ATTESTED_DETAILS": SAW_ATTESTED_DETAILS,
    # +3 aditivas sobre las 13 de (L) (pedido del orquestador: view_rule, política de retiro, modo EXIF)
    "VIEW_RULES": VIEW_RULES, "WITHDRAW_POLICIES": WITHDRAW_POLICIES, "EXIF_MODES": EXIF_MODES,
}
FROZEN_VOCABULARY_KEYS = tuple(VOCABULARY.keys())
for _k, _v in VOCABULARY.items():
    assert isinstance(_v, tuple) and len(set(_v)) == len(_v), _k
assert len(ATTESTED_DECLARED_EXCEPTIONS) == 3 and len(LICENSES_DECLARED) == 10


def attested_state_in_vocabulary(s):
    return s in ATTESTED_STATES_EXACT or (isinstance(s, str) and s.startswith(ATTESTED_STATES_PREFIXES))


def exif_state_in_vocabulary(s):
    return s in EXIF_STATES_EXACT or (isinstance(s, str) and s.startswith(EXIF_STATES_PREFIXES) and s.endswith(")"))


def storage_state_in_vocabulary(s):
    return s in STORAGE_STATES or (isinstance(s, str) and s.startswith(STORAGE_STATES_PREFIXES))


def servable_state_in_vocabulary(s):
    return s in SERVABLE_STATES


# ---------------------------------------------------------------------------------------------------------
# Errores tipados (la app los traduce a HTTP; los smokes los miden) — y el sobre {status, state, detail}
# ---------------------------------------------------------------------------------------------------------
def error(status, state, **detail):
    """Sobre de error de la lib: {status, state, detail{…}} — la app hace HTTPException(status, {state, **detail})."""
    return {"status": int(status), "state": state, "detail": dict(detail)}


class AttestationError(Exception):
    status = 500
    state = "error"

    def __init__(self, detail=None, **extra):
        self.detail = detail
        self.extra = extra
        super().__init__(f"{self.state}: {detail}")

    def to_error(self):
        return error(self.status, self.state, detail=self.detail, **self.extra)


class MetadataStripError(AttestationError):
    """(A.5) el walker no puede GARANTIZAR el resultado → 422 metadata-strip-failed {media_type, detail}; nada se guarda."""
    status = 422
    state = "metadata-strip-failed"

    def __init__(self, media_type, detail):
        self.media_type = media_type
        super().__init__(detail, media_type=media_type)


class StorageUnavailable(AttestationError):
    """(A.7/E.1) backend no configurado o inalcanzable → 503 attested-storage-unavailable {backend, state, detail}; JAMÁS
    fallback a otro backend."""
    status = 503
    state = "attested-storage-unavailable"

    def __init__(self, backend, detail, storage_state=None):
        self.backend = backend
        self.storage_state = storage_state or f"storage-unavailable ({detail})"
        # corrector (F5b): el extra se llamaba `state` y `to_error()` lo pasaba a `error(status, state, **extra)` →
        # TypeError SIEMPRE. Es decir: el 503 declarado del almacén no existía, reventaba. El estado del ALMACÉN viaja
        # como `storage_state` (el `state` del sobre es el de la clase de error: son dos cosas distintas).
        super().__init__(detail, backend=backend, storage_state=self.storage_state)


# ---------------------------------------------------------------------------------------------------------
# A.2 Env: 18 variables WITT_ATTESTED_* con default declarado; lector TOLERANTE en tiempo de llamada.
# 15 entran a models.ENV_TABLE (F3); WITT_ATTESTED_DIR (ruta) y los dos *_MINIO_*_KEY (secretos) quedan FUERA: sólo su
# PRESENCIA viaja. kind ∈ bool | int | float | csv | choice | str | path | secret.
# ---------------------------------------------------------------------------------------------------------
ENV_SPECS = (
    ("enabled",          "WITT_ATTESTED_IMAGES",               "1", "bool", None, "app · runs · audit()",
     "kill-switch maestro (N.1): 0 = frozen 1.13 byte a byte salvo ATTESTED_DECLARED_EXCEPTIONS (3); subida/inherit 409, "
     "ledger con images[] 400, GET índices 'kill-switch', bytes 404; withdraw SIGUE vivo"),
    ("vision",           "WITT_ATTESTED_VISION",               "1", "bool", None, "audit()",
     "0 = ninguna lente recibe bytes atestiguados; captions al sintetizador y al consejo siguen (N.2)"),
    ("backend",          "WITT_ATTESTED_BACKEND",              "local", "choice", STORAGE_BACKENDS, "attestations.storage_backend",
     "local | minio; fuera de vocabulario → local con source 'default-invalid-env:…'; minio sin MINIO_* → 503, JAMÁS cae a local"),
    ("dir",              "WITT_ATTESTED_DIR",                  "", "path", None, "attestations.LocalStorage",
     "raíz PRIVADA del backend local (vacía = <repo>/attested_private; 0o700/0o600; win32 declarado); FUERA de ENV_TABLE"),
    ("minio_bucket",     "WITT_ATTESTED_MINIO_BUCKET",         "witt-attested-private", "str", None, "attestations.MinioStorage",
     "bucket PRIVADO dedicado (≠ data-inamovible-raw); bucket_exists/make_bucket en probe(); versioning OFF; jamás presigned"),
    ("minio_access_key", "WITT_ATTESTED_MINIO_ACCESS_KEY",     "", "secret", None, "attestations.MinioStorage",
     "credencial de un usuario MinIO DEDICADO (unset ⇒ MINIO_ACCESS_KEY); FUERA de ENV_TABLE; sólo su presencia viaja"),
    ("minio_secret_key", "WITT_ATTESTED_MINIO_SECRET_KEY",     "", "secret", None, "attestations.MinioStorage",
     "credencial de un usuario MinIO DEDICADO (unset ⇒ MINIO_SECRET_KEY); FUERA de ENV_TABLE; sólo su presencia viaja"),
    ("max_image_mb",     "WITT_ATTESTED_MAX_IMAGE_MB",         "5", "float", MAX_IMAGE_MB_CLAMP, "app (C.2) · validate_bytes · select_for_panel",
     "bytes CRUDOS por imagen; 413 por Content-Length sin leer y por stream con tope (clamp 0.1..7)"),
    ("max_per_plan",     "WITT_ATTESTED_MAX_PER_PLAN",         "8", "int", (1, 24), "app · ledger",
     "filas VIVAS (no retiradas) por plan → 409 attestations_cap_reached {scope 'plan'}; al aprobar 400 too_many_attested_images"),
    ("max_total_mb",     "WITT_ATTESTED_MAX_TOTAL_MB",         "24", "float", (1.0, 168.0), "app",
     "suma de bytes vivos por plan → 409 attestations_cap_reached {scope 'total_mb'}"),
    ("max_per_lens",     "WITT_ATTESTED_MAX_PER_LENS",         "4", "int", (0, 8), "attestations.select_for_panel",
     "imágenes atestiguadas por petición de lente, APARTE de WITT_FIGURES_MAX_PER_LENS; figures + attested ≤ 20"),
    ("max_per_user_per_day", "WITT_ATTESTED_MAX_PER_USER_PER_DAY", "30", "int", (1, 500), "app (db.count_attested_uploads_today)",
     "rate limit de subida por cuenta (UTC) → 429 upload-rate-limited {n_today, cap, resets_at}"),
    ("caption_chars",    "WITT_ATTESTED_CAPTION_CHARS",        "1000", "int", (100, 4000), "attestations.validate_form",
     "tope del caption OBLIGATORIO (≥ 10; 400 caption-too-long); ≤ 600 en el frozen; ≤ 200 en parent_attested_images"),
    ("allowed_media",    "WITT_ATTESTED_ALLOWED_MEDIA",        DEFAULT_ALLOWED_MEDIA, "csv", None, "attestations.validate_bytes",
     "CSV acotado a figures.MEDIA_TYPES (GIF habilitable; fuera de tabla se ignora → allowed_media_env_ignored[]); PDF/TIFF/HEIC/SVG/DICOM → 415"),
    ("exif",             "WITT_ATTESTED_EXIF",                 "strip", "choice", EXIF_MODES, "attestations.strip_metadata",
     "strip = quitar metadatos ANTES de hashear/almacenar (fallo → 422, nada se guarda); declare = tal cual con exif_present medido"),
    ("team_view",        "WITT_ATTESTED_TEAM_VIEW",            "1", "bool", None, "app.view_rule",
     "1 = honrar share_scope 'team' declarado por quien sube; 0 = author-only para todos; material de paciente author-only SIEMPRE"),
    ("withdraw",         "WITT_ATTESTED_WITHDRAW",             "uploader", "choice", WITHDRAW_POLICIES, "app withdraw",
     "quién retira: uploader | team (403 withdraw-not-uploader con la regla)"),
    ("patient_material", "WITT_ATTESTED_PATIENT_MATERIAL",     "0", "bool", None, "attestations.validate_form",
     "1 = material de paciente permitido con consentimiento + desidentificación + acuse al aprobar; 0 = 400 patient_material_not_allowed (OE4)"),
)
ENV_VARS = tuple(s[1] for s in ENV_SPECS)
ENV_TABLE_VARS = tuple(s[1] for s in ENV_SPECS if s[3] not in ("path", "secret"))     # → models.ENV_TABLE (F3)
ENV_OUT_OF_TABLE_VARS = tuple(s[1] for s in ENV_SPECS if s[3] in ("path", "secret"))  # ruta + secretos: sólo presencia
ENV_DEFAULTS = {s[1]: s[2] for s in ENV_SPECS}
ENV_SOURCE_PREFIXES = ("env:", "default-unset:", "default-empty-env:", "default-invalid-env:")
assert len(ENV_SPECS) == 18 and len(set(ENV_VARS)) == 18 and len(ENV_TABLE_VARS) == 15 and len(ENV_OUT_OF_TABLE_VARS) == 3
assert all(v.startswith("WITT_ATTESTED_") for v in ENV_VARS)
_BUCKET_RE = re.compile(r"^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$")


def _parse_env_value(kind, raw, default, clamp):
    """(value, ok). ok False = inválida → el llamador toma el default y declara 'default-invalid-env'."""
    s = (raw or "").strip()
    if kind == "bool":
        if s in ("0", "1"):
            return s == "1", True
        low = s.lower()
        if low in ("true", "yes", "on"):
            return True, True
        if low in ("false", "no", "off"):
            return False, True
        return default == "1", False
    if kind == "int":
        try:
            v = int(float(s))
        except (TypeError, ValueError):
            return int(default), False
        if clamp and not (clamp[0] <= v <= clamp[1]):
            return int(default), False
        return v, True
    if kind == "float":
        try:
            v = float(s)
        except (TypeError, ValueError):
            return float(default), False
        if v != v or v in (float("inf"), float("-inf")):
            return float(default), False
        if clamp and not (clamp[0] <= v <= clamp[1]):
            return float(default), False
        return v, True
    if kind == "csv":
        toks = [t.strip().lower() for t in s.split(",") if t.strip()]
        return (toks, True) if toks else ([t for t in default.split(",")], False)
    if kind == "choice":
        low = s.lower()
        return (low, True) if low in clamp else (default, False)
    if kind == "str":
        if s and _BUCKET_RE.match(s):
            return s, True
        return default, False
    if kind == "path":
        return (s or None), True
    if kind == "secret":
        return bool(s), True
    raise ValueError(kind)


def env_config(env=None):
    """Lee las 18 WITT_ATTESTED_* del entorno EN LA LLAMADA, tolerante (vacía/basura → default con source). Devuelve
    {<name>: valor efectivo (los `secret` como PRESENCIA bool, jamás el valor), 'sources': {<name>: 'env:<VAR>' |
    'default-unset:<VAR>' | 'default-empty-env:<VAR>' (presente y vacía: tres estados) | 'default-invalid-env:<VAR>'},
    'allowed_media_env_ignored': [...], 'caps': {...forma (L)...}, 'constants': {...}, 'exif_mode': {value, source},
    'view_rule_default': {value, source}, 'team_view': {value, source}}."""
    env = os.environ if env is None else env
    out, sources, ignored = {}, {}, []
    for name, var, default, kind, clamp, _reader, _effect in ENV_SPECS:
        raw = env.get(var)
        if raw is None:
            v, _ = _parse_env_value(kind, default, default, clamp)
            sources[name] = f"default-unset:{var}"
        elif not str(raw).strip():
            v, _ = _parse_env_value(kind, default, default, clamp)
            sources[name] = f"default-empty-env:{var}"
        else:
            v, ok = _parse_env_value(kind, str(raw), default, clamp)
            sources[name] = f"env:{var}" if ok else f"default-invalid-env:{var}"
        if kind == "csv":   # acotado a figures.MEDIA_TYPES: la env sólo puede ELEGIR dentro de la tabla, jamás ampliarla
            kept = tuple(t for t in v if t in MEDIA_TYPES)
            ignored.extend(f"{var}:{t}" for t in v if t not in MEDIA_TYPES)
            if not kept:
                kept = tuple(default.split(","))
                sources[name] = f"default-invalid-env:{var}"
            v = kept
        out[name] = v
    out["sources"] = sources
    out["allowed_media_env_ignored"] = ignored
    out["caps"] = {
        "max_image_mb": {"value": out["max_image_mb"], "source": sources["max_image_mb"]},
        "max_per_plan": {"value": out["max_per_plan"], "source": sources["max_per_plan"]},
        "max_total_mb": {"value": out["max_total_mb"], "source": sources["max_total_mb"]},
        "max_per_lens": {"value": out["max_per_lens"], "source": sources["max_per_lens"]},
        "request_b64_mb": {"value": REQUEST_B64_MB, "source": _figures.CONSTANT_SOURCE},
        "caption_chars": {"value": out["caption_chars"], "source": sources["caption_chars"]},
        "allowed_media": {"value": list(out["allowed_media"]), "source": sources["allowed_media"]},
        "many_image_limit": {"value": MANY_IMAGE_LIMIT, "source": CONSTANT_SOURCE},
        "max_per_user_per_day": {"value": out["max_per_user_per_day"], "source": sources["max_per_user_per_day"]},
    }
    out["constants"] = {"form_overhead_bytes": FORM_OVERHEAD_BYTES, "sha_short": SHA_SHORT,
                        "frozen_caption_chars": FROZEN_CAPTION_CHARS, "thread_caption_chars": THREAD_CAPTION_CHARS,
                        "caption_min_chars": CAPTION_MIN_CHARS, "consent_text_chars": CONSENT_TEXT_CHARS,
                        "frozen_consent_text_chars": FROZEN_CONSENT_TEXT_CHARS, "consent_text_min_chars": CONSENT_TEXT_MIN_CHARS,
                        "many_image_limit": MANY_IMAGE_LIMIT, "min_dim_px": MIN_DIM_PX, "max_megapixels": MAX_MEGAPIXELS,
                        "request_b64_mb": REQUEST_B64_MB, "source": CONSTANT_SOURCE}
    out["exif_mode"] = {"value": out["exif"], "source": sources["exif"]}
    # el default de vista es SIEMPRE author-only (share_scope default); 'team' sólo por declaración + TEAM_VIEW=1 (G.1)
    out["view_rule_default"] = {"value": "author-only", "source": CONSTANT_SOURCE}
    out["team_view"] = {"value": out["team_view"], "source": sources["team_view"]}
    out["max_body_bytes"] = int(float(out["max_image_mb"]) * 1024 * 1024) + FORM_OVERHEAD_BYTES
    return out


def local_root(cfg=None, env=None):
    """(Path, dir_source ∈ 'env' | 'default'): WITT_ATTESTED_DIR o <repo>/attested_private — JAMÁS bajo mcp_cache."""
    cfg = cfg or env_config(env)
    v = cfg.get("dir")
    if v:
        return Path(v), "env"
    return ROOT / "attested_private", "default"


# ---------------------------------------------------------------------------------------------------------
# A.3 validate_form(fields, cfg) → (ok_fields, None) | (None, error {status 400, state, detail})
# ---------------------------------------------------------------------------------------------------------
def _parse_bool(v):
    if isinstance(v, bool):
        return v
    if v is None:
        return None
    if isinstance(v, (int, float)) and v in (0, 1):
        return bool(v)
    s = str(v).strip().lower()
    if s in ("1", "true", "yes", "on"):
        return True
    if s in ("0", "false", "no", "off"):
        return False
    return None


def _str_or_none(v):
    if v is None:
        return None
    s = str(v).strip()
    return s or None


_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}([T ].*)?$")


def validate_form(fields, cfg=None, known_requirement_ids=None):
    """El formulario ES la procedencia (C.4): campos OBLIGATORIOS con 400 tipado por campo. `fields` = dict de strings/bools
    (multipart); `known_requirement_ids` opcional (lista) activa `unknown_requirement_id`. Devuelve
    (ok_fields normalizados, None) | (None, error). Reglas de paciente (I): patient_material → consent_kind
    'patient-consented' ∧ deidentified_declared ∧ consent_text ≥ 20; con WITT_ATTESTED_PATIENT_MATERIAL=0 → 400
    patient_material_not_allowed (OE4, default 0)."""
    cfg = cfg or env_config()
    f = fields or {}
    caption = _str_or_none(f.get("caption"))
    if caption is None or len(caption) < CAPTION_MIN_CHARS:
        return None, error(400, "caption-missing", min_chars=CAPTION_MIN_CHARS, chars=len(caption or ""))
    if len(caption) > int(cfg["caption_chars"]):
        return None, error(400, "caption-too-long", max_chars=int(cfg["caption_chars"]), chars=len(caption))
    kind = _str_or_none(f.get("consent_kind"))
    if kind not in CONSENT_KINDS:
        return None, error(400, "invalid-consent-kind", allowed=list(CONSENT_KINDS), given=kind)
    if _parse_bool(f.get("consent_declared")) is not True:
        return None, error(400, "consent-not-declared")
    consent_text = _str_or_none(f.get("consent_text"))
    if kind in CONSENT_TEXT_REQUIRED_KINDS and (consent_text is None or len(consent_text) < CONSENT_TEXT_MIN_CHARS):
        return None, error(400, "consent_text-required", kind=kind, min_chars=CONSENT_TEXT_MIN_CHARS)
    if consent_text is not None and len(consent_text) > CONSENT_TEXT_CHARS:
        return None, error(400, "consent_text-too-long", max_chars=CONSENT_TEXT_CHARS, chars=len(consent_text))
    if _parse_bool(f.get("third_party_processing_acknowledged")) is not True:
        return None, error(400, "third_party_processing_not_acknowledged", notice=THIRD_PARTY_NOTICE_ES)
    pm = _parse_bool(f.get("patient_material"))
    if pm is None:                                   # SIN default: ausente ≠ false (tres estados)
        return None, error(400, "patient_material-required")
    deid = _parse_bool(f.get("deidentified_declared"))
    deid = bool(deid) if deid is not None else False
    if pm:
        if not cfg["patient_material"]:
            return None, error(400, "patient_material_not_allowed", env="WITT_ATTESTED_PATIENT_MATERIAL",
                               source=cfg["sources"]["patient_material"])
        if kind != "patient-consented" or consent_text is None or len(consent_text) < CONSENT_TEXT_MIN_CHARS:
            return None, error(400, "patient_material_without_consent", required_consent_kind="patient-consented",
                               consent_text_min_chars=CONSENT_TEXT_MIN_CHARS)
        if not deid:
            return None, error(400, "patient_material_not_deidentified")
    lic = _str_or_none(f.get("license_declared")) or "private-team-only"
    if lic not in LICENSES_DECLARED:
        return None, error(400, "invalid-license", allowed=list(LICENSES_DECLARED), given=lic)
    scope = _str_or_none(f.get("share_scope")) or "author-only"
    if scope not in SHARE_SCOPES:
        return None, error(400, "invalid-share-scope", allowed=list(SHARE_SCOPES), given=scope)
    req = _str_or_none(f.get("requirement_id"))
    if req is not None and known_requirement_ids is not None and req not in list(known_requirement_ids):
        return None, error(400, "unknown_requirement_id", requirement_id=req, known=list(known_requirement_ids))
    date_taken = _str_or_none(f.get("date_taken"))
    if date_taken is not None and (len(date_taken) > DATE_TAKEN_CHARS or not _DATE_RE.match(date_taken)):
        return None, error(400, "invalid-date_taken", max_chars=DATE_TAKEN_CHARS, format="ISO 8601 (YYYY-MM-DD[Thh:mm…])")
    method = _str_or_none(f.get("method"))
    if method is not None and len(method) > METHOD_CHARS:
        return None, error(400, "method-too-long", max_chars=METHOD_CHARS, chars=len(method))
    return {"caption": caption, "caption_chars": len(caption), "consent_kind": kind, "consent_declared": True,
            "consent_text": consent_text, "third_party_ack": True, "patient_material": bool(pm),
            "deidentified_declared": deid, "license_declared": lic, "share_scope": scope, "requirement_id": req,
            "date_taken": date_taken, "method": method}, None


# ---------------------------------------------------------------------------------------------------------
# A.4 validate_bytes(data, declared_ct, cfg) → (fields, None) | (None, error {status 413|415|422, state, detail})
# ---------------------------------------------------------------------------------------------------------
def _normalize_ct(ct):
    if ct is None:
        return None
    s = str(ct).split(";")[0].strip().lower()
    if s == "image/jpg":
        s = "image/jpeg"
    return s or None


def validate_bytes(data, declared_ct=None, cfg=None):
    """Orden (D): sniff_mime → allowed_media → image_dims → 40 MP → mínimo 16 px → tope MB. El Content-Type declarado se
    REGISTRA (media_type_declared / media_type_declared_mismatch: bool|null), jamás decide (D). dims 0 se mide (0 ≠ null):
    cae a image-too-small con w/h medidos."""
    cfg = cfg or env_config()
    data = bytes(data or b"")
    declared = _normalize_ct(declared_ct)
    sniffed = sniff_mime(data)
    allowed = list(cfg["allowed_media"])
    if sniffed is None or sniffed not in allowed:
        return None, error(415, "unsupported-media-type", sniffed=sniffed, declared=declared, allowed=allowed)
    dims = image_dims(data)
    if dims is None:
        return None, error(422, "undecodable-header", media_type=sniffed)
    w, h = int(dims["w"]), int(dims["h"])
    if w * h > MAX_MEGAPIXELS * 1_000_000:
        return None, error(422, "image-too-many-pixels", w=w, h=h, max_mp=MAX_MEGAPIXELS)
    if min(w, h) < MIN_DIM_PX:
        return None, error(422, "image-too-small", w=w, h=h, min_px=MIN_DIM_PX)
    max_mb = float(cfg["max_image_mb"])
    if len(data) > int(max_mb * 1024 * 1024):
        return None, error(413, "attested_image_too_large", bytes=len(data), max_mb=max_mb,
                           max_mb_source=cfg["sources"]["max_image_mb"])
    return {"media_type": sniffed, "media_type_declared": declared,
            "media_type_declared_mismatch": (None if declared is None else declared != sniffed),
            "dims": {"w": w, "h": h}, "dims_source": "header", "bytes_received": len(data),
            "megapixels": round(w * h / 1_000_000, 3)}, None


# ---------------------------------------------------------------------------------------------------------
# A.5 strip_metadata(data, media_type, mode) → {data, exif_state, removed[], exif_present, detail}
#     walkers stdlib SIN recodificar: los píxeles quedan byte-idénticos (image_dims antes == después, medido)
# ---------------------------------------------------------------------------------------------------------
_JPEG_STANDALONE = {0xD8, 0x01} | set(range(0xD0, 0xD8))
_PNG_SIG = b"\x89PNG\r\n\x1a\n"
_PNG_STRIP = {b"tEXt", b"zTXt", b"iTXt", b"eXIf", b"tIME"}
_WEBP_STRIP = {b"EXIF", b"XMP "}
_WEBP_FLAG = {b"EXIF": 0x08, b"XMP ": 0x04}


def _jpeg_walk(data):
    """(segments_out: list[bytes], removed: list[str]). Lanza ValueError si no puede garantizar el resultado."""
    n = len(data)
    if n < 4 or data[:2] != b"\xff\xd8":
        raise ValueError("no SOI")
    out, removed = [b"\xff\xd8"], []
    i = 2
    while True:
        if i + 2 > n:
            raise ValueError("segment table ends before SOS")
        if data[i] != 0xFF:
            raise ValueError(f"marker expected at {i}")
        marker = data[i + 1]
        if marker == 0xFF:               # fill byte
            out.append(b"\xff")
            i += 1
            continue
        if marker in _JPEG_STANDALONE:
            out.append(data[i:i + 2])
            i += 2
            continue
        if marker == 0xD9:
            raise ValueError("EOI before SOS")
        if i + 4 > n:
            raise ValueError("truncated segment length")
        seg_len = struct.unpack(">H", data[i + 2:i + 4])[0]
        if seg_len < 2 or i + 2 + seg_len > n:
            raise ValueError(f"segment 0x{marker:02X} truncated (declared {seg_len}, available {n - i - 2})")
        seg = data[i:i + 2 + seg_len]
        payload = seg[4:]
        if marker == 0xDA:               # SOS: desde aquí TODO se conserva verbatim (scan(s), DHT/DQT entre scans, EOI)
            out.append(data[i:])
            return out, removed
        if marker == 0xE1:
            removed.append("APP1")
        elif marker == 0xE2:
            if payload.startswith(b"ICC_PROFILE\x00"):
                out.append(seg)
            else:
                removed.append("APP2:MPF" if payload.startswith(b"MPF\x00") else "APP2")
        elif 0xE3 <= marker <= 0xED:
            removed.append(f"APP{marker - 0xE0}")
        elif marker == 0xFE:
            removed.append("COM")
        else:                            # APP0 (JFIF), APP14 (Adobe), APP15, DQT, DHT, SOF*, DRI, …: intactos
            out.append(seg)
        i += 2 + seg_len
    # unreachable


def _png_walk(data):
    n = len(data)
    if data[:8] != _PNG_SIG:
        raise ValueError("no PNG signature")
    out, removed = [_PNG_SIG], []
    i = 8
    saw_iend = False
    while i < n:
        if i + 8 > n:
            raise ValueError("truncated chunk header")
        length = struct.unpack(">I", data[i:i + 4])[0]
        ctype = data[i + 4:i + 8]
        end = i + 12 + length
        if end > n:
            raise ValueError(f"chunk {ctype!r} truncated")
        chunk = data[i:end]
        if ctype in _PNG_STRIP:
            removed.append(ctype.decode("latin-1"))
        else:
            out.append(chunk)            # CRC del chunk conservado: intacto (no se recalcula)
        i = end
        if ctype == b"IEND":
            saw_iend = True
            break
    if not saw_iend:
        raise ValueError("no IEND")
    if i != n:
        raise ValueError("bytes after IEND")
    return out, removed


def _webp_walk(data):
    n = len(data)
    if n < 12 or data[:4] != b"RIFF" or data[8:12] != b"WEBP":
        raise ValueError("no RIFF/WEBP")
    riff_size = struct.unpack("<I", data[4:8])[0]
    if riff_size + 8 != n:
        raise ValueError(f"RIFF size inconsistent (declared {riff_size + 8}, actual {n})")
    chunks, removed = [], []
    i = 12
    while i < n:
        if i + 8 > n:
            raise ValueError("truncated chunk header")
        fourcc = data[i:i + 4]
        size = struct.unpack("<I", data[i + 4:i + 8])[0]
        padded = size + (size & 1)
        end = i + 8 + padded
        if end > n:
            raise ValueError(f"chunk {fourcc!r} truncated")
        chunks.append((fourcc, bytearray(data[i:end])))
        i = end
    flags_clear = 0
    kept = []
    for fourcc, raw in chunks:
        if fourcc in _WEBP_STRIP:
            removed.append(fourcc.decode("latin-1").strip())
            flags_clear |= _WEBP_FLAG[fourcc]
        else:
            kept.append((fourcc, raw))
    if flags_clear:
        for fourcc, raw in kept:
            if fourcc == b"VP8X" and len(raw) >= 9:
                raw[8] &= (~flags_clear) & 0xFF       # bajar los bits E (EXIF) / X (XMP) del VP8X
    body = b"".join(bytes(r) for _f, r in kept)
    out = [b"RIFF", struct.pack("<I", len(body) + 4), b"WEBP", body]
    return out, removed


def _gif_subblocks_end(data, i):
    """Devuelve el índice tras el terminador 0x00 de una secuencia de sub-bloques que empieza en i."""
    n = len(data)
    while True:
        if i >= n:
            raise ValueError("truncated sub-blocks")
        size = data[i]
        if size == 0:
            return i + 1
        i += 1 + size
        if i > n:
            raise ValueError("truncated sub-block")


def _gif_walk(data):
    n = len(data)
    if n < 13 or data[:6] not in (b"GIF87a", b"GIF89a"):
        raise ValueError("no GIF header")
    out, removed = [], []
    packed = data[10]
    i = 13
    if packed & 0x80:
        i += 3 * (2 << (packed & 0x07))
    if i > n:
        raise ValueError("truncated global color table")
    out.append(data[:i])
    while True:
        if i >= n:
            raise ValueError("no trailer")
        b = data[i]
        if b == 0x3B:
            out.append(data[i:i + 1])
            i += 1
            break
        if b == 0x2C:                    # image descriptor + LCT? + LZW min code + sub-blocks
            if i + 10 > n:
                raise ValueError("truncated image descriptor")
            p = data[i + 9]
            j = i + 10
            if p & 0x80:
                j += 3 * (2 << (p & 0x07))
            j += 1                       # LZW minimum code size
            if j > n:
                raise ValueError("truncated image data")
            j = _gif_subblocks_end(data, j)
            out.append(data[i:j])
            i = j
            continue
        if b == 0x21:
            if i + 2 > n:
                raise ValueError("truncated extension")
            label = data[i + 1]
            j = _gif_subblocks_end(data, i + 2)
            block = data[i:j]
            if label == 0xFE:
                removed.append("Comment")
            elif label == 0xFF and len(block) >= 14 and block[3:14] == b"XMP DataXMP":
                removed.append("XMP")
            else:
                out.append(block)
            i = j
            continue
        raise ValueError(f"unknown block 0x{b:02X} at {i}")
    if i != n:
        raise ValueError("bytes after trailer")
    return out, removed


_WALKERS = {"image/jpeg": _jpeg_walk, "image/png": _png_walk, "image/webp": _webp_walk, "image/gif": _gif_walk}


def strip_metadata(data, media_type=None, mode="strip"):
    """SIN recodificar. mode 'strip' (default): JPEG quita APP1 (Exif/XMP), APP2≠ICC (MPF), APP3–APP13, COM; conserva APP0,
    APP2 ICC, APP14, DQT/DHT/SOF*/DRI/SOS…EOI · PNG quita tEXt/zTXt/iTXt/eXIf/tIME (CRC de los conservados intacto) · WebP
    quita EXIF/XMP, corrige el tamaño RIFF y baja los bits del VP8X · GIF quita Comment y Application 'XMP DataXMP'.
    Devuelve {data, exif_state ∈ 'none-found' | 'stripped (<segmentos>)' | 'declared-not-stripped', removed[], exif_present,
    detail}. Un walker que no puede GARANTIZAR el resultado (truncado, longitud inconsistente, dims/mime cambiarían) →
    MetadataStripError (422 metadata-strip-failed; el llamador NO guarda nada). mode 'declare': tal cual, exif_present
    MEDIDO (None si el walker no pudo medir) y exif_state 'declared-not-stripped'."""
    data = bytes(data or b"")
    media_type = media_type or sniff_mime(data)
    walker = _WALKERS.get(media_type)
    if walker is None:
        raise MetadataStripError(media_type, f"unsupported media_type {media_type!r}")
    if mode not in EXIF_MODES:
        raise MetadataStripError(media_type, f"unknown mode {mode!r}")
    try:
        segments, removed = walker(data)
    except (ValueError, struct.error, IndexError) as e:
        if mode == "declare":
            return {"data": data, "exif_state": "declared-not-stripped", "removed": [], "exif_present": None,
                    "detail": f"walker could not measure: {e}"}
        raise MetadataStripError(media_type, str(e))
    if mode == "declare":
        return {"data": data, "exif_state": "declared-not-stripped", "removed": [], "exif_present": bool(removed),
                "detail": ("metadata present: " + ", ".join(removed)) if removed else "no metadata segments found"}
    if not removed:
        return {"data": data, "exif_state": "none-found", "removed": [], "exif_present": False, "detail": None}
    out = b"".join(segments)
    if sniff_mime(out) != media_type or image_dims(out) != image_dims(data):
        raise MetadataStripError(media_type, "post-strip header differs (mime/dims) — result not guaranteed")
    return {"data": out, "exif_state": f"stripped ({', '.join(removed)})", "removed": list(removed), "exif_present": True,
            "detail": None}


# ---------------------------------------------------------------------------------------------------------
# A.6 identidad: sha256 de los bytes ALMACENADOS (post-strip) + sha256 de los recibidos; id 'attested:<sha12>'
# ---------------------------------------------------------------------------------------------------------
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
_PLAN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")


def sha256_hex(data):
    return hashlib.sha256(data).hexdigest()


def short_of(sha256):
    return str(sha256)[:SHA_SHORT]


def id_of(sha256):
    return ATTESTED_ID_PREFIX + short_of(sha256)


def image_id_of(plan_id, sha256):
    """PK de plan_attested_images (String 64): determinista por (plan_id, sha256) — el `id` público 'attested:<sha12>'
    no es único entre planes."""
    return hashlib.sha256(f"{plan_id}/{sha256}".encode("utf-8")).hexdigest()[:32]


def identity(stored, received=None):
    """{sha256 (ALMACENADO = lo que se sirve y se recalcula), sha256_received, sha256_short, id, bytes, bytes_received}."""
    received = stored if received is None else received
    sha = sha256_hex(stored)
    return {"sha256": sha, "sha256_received": sha256_hex(received), "sha256_short": short_of(sha), "id": id_of(sha),
            "bytes": len(stored), "bytes_received": len(received)}


def valid_sha256(s):
    return isinstance(s, str) and _SHA_RE.match(s) is not None


# ---------------------------------------------------------------------------------------------------------
# A.7 Storage: backend INTERCAMBIABLE, PRIVADO, fuera del blob — lo que pasa sin dir o sin MinIO se DECLARA, jamás fallback
# ---------------------------------------------------------------------------------------------------------
def storage_key(plan_id, sha256, media_type):
    """Layout <plan_id>/<sha256>.<ext> (un plan, sus bytes: sin refcount ni clave compartida — (P)(k))."""
    if not _PLAN_ID_RE.match(str(plan_id or "")):
        raise ValueError(f"bad plan_id {plan_id!r}")
    if not valid_sha256(sha256):
        raise ValueError("bad sha256")
    ext = EXT_BY_MEDIA.get(media_type)
    if ext is None:
        raise ValueError(f"no extension for media_type {media_type!r}")
    return f"{plan_id}/{sha256}.{ext}"


class Storage:
    """Interfaz congelada. put/get/stat/delete LANZAN StorageUnavailable cuando el backend no está o no responde (la app
    responde 503, nada se escribe); probe() jamás lanza: DECLARA."""
    backend = None

    def put(self, plan_id, sha256, data, media_type):
        raise NotImplementedError

    def get(self, key):
        raise NotImplementedError

    def stat(self, key):
        raise NotImplementedError

    def delete(self, key):
        raise NotImplementedError

    def probe(self):
        raise NotImplementedError

    def presign(self, *a, **kw):
        raise NotImplementedError("presigned URLs are FORBIDDEN for attested images (ADR-0086 G.3): a presign is a shareable "
                                  "URL = redistribution")


def _probe_writable(path):
    probe = Path(path) / f".probe_{os.getpid()}_{int(time.time() * 1000)}"
    try:
        fd = os.open(str(probe), os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), 0o600)
        os.close(fd)
        probe.unlink()
        return True
    except OSError:
        return False


IS_WIN32 = sys.platform == "win32"


def _apply_dir_mode(path):
    """0o700 en POSIX (medido); en win32 no aplica y se DECLARA."""
    if IS_WIN32:
        return "permissions-not-applied (win32)"
    try:
        os.chmod(str(path), 0o700)
        mode = _stat.S_IMODE(os.stat(str(path)).st_mode)
        return "writable" if mode == 0o700 else "read-only"
    except OSError:
        return "read-only"


class LocalStorage(Storage):
    """Disco local PRIVADO bajo WITT_ATTESTED_DIR (vacía → <repo>/attested_private; JAMÁS bajo mcp_cache). mkdir 0o700,
    archivos 0o600 vía os.open (win32 → dir_state 'permissions-not-applied (win32)' declarado), escritura ATÓMICA .part +
    os.replace, `already_present` cuando el sha ya está (409 en la app sin bytes a medias)."""
    backend = "local"

    def __init__(self, root=None, cfg=None, env=None):
        if root is not None:
            self.root, self.dir_source = Path(root), "injected"
        else:
            self.root, self.dir_source = local_root(cfg, env)
        self.root = Path(self.root)
        rp = str(self.root.resolve()).replace("\\", "/").lower()
        assert "/mcp_cache/" not in rp + "/" and not rp.endswith("/mcp_cache"), "attested root must never live under mcp_cache"

    def dir_state(self, create=True):
        p = self.root
        if not p.exists():
            if not create:
                return "missing"
            try:
                p.mkdir(parents=True, exist_ok=True)
            except OSError:
                return "missing"
        if not p.is_dir():
            return "missing"
        if not _probe_writable(p):
            return "read-only"
        return _apply_dir_mode(p)

    def probe(self, create=True):
        ds = self.dir_state(create=create)
        ok = ds in ("writable", "permissions-not-applied (win32)")
        return {"backend": self.backend, "state": "stored" if ok else f"storage-unavailable (dir {ds})", "detail": str(self.root),
                "dir_state": ds, "dir_source": self.dir_source, "root_present": self.root.exists(), "sdk_version": None,
                "bucket": None, "credentials_source": None}

    def _path(self, key):
        p = (self.root / key)
        if ".." in Path(key).parts:
            raise ValueError("bad key")
        return p

    def put(self, plan_id, sha256, data, media_type):
        key = storage_key(plan_id, sha256, media_type)
        final = self._path(key)
        try:
            ds = self.dir_state(create=True)
            if ds not in ("writable", "permissions-not-applied (win32)"):
                raise StorageUnavailable(self.backend, f"dir {ds}: {self.root}")
            if final.exists():
                return {"key": key, "state": "stored", "already_present": True, "bytes": final.stat().st_size, "dir_state": ds}
            plan_dir = final.parent
            if not plan_dir.exists():
                os.mkdir(str(plan_dir), 0o700)
                _apply_dir_mode(plan_dir)
            part = plan_dir / f"{final.name}.part.{os.getpid()}"
            fd = os.open(str(part), os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), 0o600)
            try:
                with os.fdopen(fd, "wb") as fh:
                    fh.write(data)
                    fh.flush()
                    os.fsync(fh.fileno())
                os.replace(str(part), str(final))
            finally:
                if part.exists():
                    try:
                        part.unlink()
                    except OSError:
                        pass
            return {"key": key, "state": "stored", "already_present": False, "bytes": len(data), "dir_state": ds}
        except StorageUnavailable:
            raise
        except OSError as e:
            raise StorageUnavailable(self.backend, f"{type(e).__name__}: {e}")

    def get(self, key):
        p = self._path(key)
        try:
            if not p.is_file():
                return None
            return p.read_bytes()
        except OSError as e:
            raise StorageUnavailable(self.backend, f"{type(e).__name__}: {e}")

    def stat(self, key):
        p = self._path(key)
        try:
            if not p.is_file():
                return {"exists": False, "bytes": None}
            return {"exists": True, "bytes": p.stat().st_size}
        except OSError as e:
            raise StorageUnavailable(self.backend, f"{type(e).__name__}: {e}")

    def delete(self, key):
        p = self._path(key)
        try:
            if not p.is_file():
                return False
            p.unlink()
            return True
        except OSError as e:
            raise StorageUnavailable(self.backend, f"{type(e).__name__}: {e}")


MINIO_REQUIRED_ENV = ("MINIO_ENDPOINT", "MINIO_ACCESS_KEY", "MINIO_SECRET_KEY")


class MinioStorage(Storage):
    """MinIO PRIVADO con el SDK ya instalado (pin minio>=7.2,<8): firma 7.2 POSICIONAL `put_object(bucket, key, BytesIO,
    length, content_type=, metadata=)`. Credenciales: WITT_ATTESTED_MINIO_*_KEY si están (usuario DEDICADO), si no MINIO_*
    (`credentials_source` declarado); endpoint MINIO_ENDPOINT / MINIO_SECURE. Sin endpoint/credenciales → probe().state
    'storage-unavailable (missing env: …)' SIN importar minio, y put/get/stat/delete lanzan StorageUnavailable (503) —
    JAMÁS cae a local. `client_factory` / set_client_factory(fn) inyectan un FakeMinio en los smokes. presign PROHIBIDO."""
    backend = "minio"

    def __init__(self, client_factory=None, cfg=None, env=None):
        self._env = os.environ if env is None else env
        self.cfg = cfg or env_config(self._env)
        self.bucket = self.cfg["minio_bucket"]
        self._factory = client_factory
        self._client = None
        self.sdk_version = None

    def set_client_factory(self, fn):
        self._factory = fn
        self._client = None

    def credentials(self):
        """({endpoint, access_key, secret_key, secure} | None, credentials_source, missing[]) — los valores NO salen de aquí."""
        env = self._env
        ak, sk = (env.get("WITT_ATTESTED_MINIO_ACCESS_KEY") or "").strip(), (env.get("WITT_ATTESTED_MINIO_SECRET_KEY") or "").strip()
        source = "WITT_ATTESTED_MINIO_*" if (ak and sk) else "MINIO_*"
        if not (ak and sk):
            ak, sk = (env.get("MINIO_ACCESS_KEY") or "").strip(), (env.get("MINIO_SECRET_KEY") or "").strip()
        endpoint = (env.get("MINIO_ENDPOINT") or "").strip()
        missing = [v for v, present in (("MINIO_ENDPOINT", endpoint), ("MINIO_ACCESS_KEY", ak), ("MINIO_SECRET_KEY", sk)) if not present]
        if missing:
            return None, None, missing
        secure = (env.get("MINIO_SECURE") or "true").strip().lower() == "true"
        return {"endpoint": endpoint, "access_key": ak, "secret_key": sk, "secure": secure}, source, []

    def client(self):
        if self._client is not None:
            return self._client
        creds, _source, missing = self.credentials()
        if missing:
            raise StorageUnavailable(self.backend, "missing env: " + ", ".join(missing))
        try:
            if self._factory is not None:
                self._client = self._factory(creds)
            else:
                import minio as _minio               # PEREZOSO (patrón raw_store._client) — sólo con env configurada
                from minio import Minio
                self.sdk_version = getattr(_minio, "__version__", None)
                self._client = Minio(creds["endpoint"], access_key=creds["access_key"], secret_key=creds["secret_key"],
                                     secure=creds["secure"])
        except StorageUnavailable:
            raise
        except Exception as e:
            raise StorageUnavailable(self.backend, f"client: {type(e).__name__}: {e}")
        if self.sdk_version is None:
            self.sdk_version = getattr(self._client, "sdk_version", None)
            if self.sdk_version is None:
                try:
                    import minio as _minio
                    self.sdk_version = getattr(_minio, "__version__", None)
                except Exception:
                    self.sdk_version = None
        return self._client

    def probe(self):
        creds, source, missing = self.credentials()
        base = {"backend": self.backend, "detail": None, "dir_state": None, "dir_source": None, "root_present": None,
                "sdk_version": None, "bucket": self.bucket, "credentials_source": source}
        if missing:
            base["state"] = "storage-unavailable (missing env: " + ", ".join(missing) + ")"
            base["detail"] = "not configured; minio not imported"
            return base
        try:
            c = self.client()
            base["sdk_version"] = self.sdk_version
            if not c.bucket_exists(self.bucket):
                c.make_bucket(self.bucket)
                base["detail"] = "bucket created"
            else:
                base["detail"] = "bucket exists"
            base["state"] = "stored"
        except StorageUnavailable as e:
            base["state"], base["detail"] = e.storage_state, e.detail
        except Exception as e:
            base["state"], base["detail"] = f"storage-unavailable ({type(e).__name__})", f"{type(e).__name__}: {e}"
        return base

    @staticmethod
    def _is_no_such_key(e):
        code = getattr(e, "code", None)
        return code in ("NoSuchKey", "NoSuchObject") or "NoSuchKey" in str(e)

    def put(self, plan_id, sha256, data, media_type):
        key = storage_key(plan_id, sha256, media_type)
        c = self.client()
        try:
            st = self.stat(key)
            if st["exists"]:
                return {"key": key, "state": "stored", "already_present": True, "bytes": st["bytes"], "dir_state": None}
            c.put_object(self.bucket, key, io.BytesIO(data), len(data), content_type=media_type, metadata={"sha256": sha256})
        except StorageUnavailable:
            raise
        except Exception as e:
            raise StorageUnavailable(self.backend, f"put_object: {type(e).__name__}: {e}")
        return {"key": key, "state": "stored", "already_present": False, "bytes": len(data), "dir_state": None}

    def get(self, key):
        c = self.client()
        resp = None
        try:
            resp = c.get_object(self.bucket, key)
            return resp.read()
        except Exception as e:
            if self._is_no_such_key(e):
                return None
            raise StorageUnavailable(self.backend, f"get_object: {type(e).__name__}: {e}")
        finally:
            if resp is not None:
                for m in ("close", "release_conn"):
                    try:
                        getattr(resp, m)()
                    except Exception:
                        pass

    def stat(self, key):
        c = self.client()
        try:
            obj = c.stat_object(self.bucket, key)
            return {"exists": True, "bytes": getattr(obj, "size", None)}
        except Exception as e:
            if self._is_no_such_key(e):
                return {"exists": False, "bytes": None}
            raise StorageUnavailable(self.backend, f"stat_object: {type(e).__name__}: {e}")

    def delete(self, key):
        c = self.client()
        try:
            if not self.stat(key)["exists"]:
                return False
            c.remove_object(self.bucket, key)
            return True
        except StorageUnavailable:
            raise
        except Exception as e:
            raise StorageUnavailable(self.backend, f"remove_object: {type(e).__name__}: {e}")


class FakeMemoryStorage(Storage):
    """Misma interfaz, en memoria (smokes). `backend` se declara 'local' para que las filas queden en vocabulario;
    `unavailable=True` simula un backend caído (todo lanza StorageUnavailable); `objects[key]` se puede alterar para medir
    'bytes-mismatch'."""
    backend = "local"
    fake = True

    def __init__(self, backend="local"):
        self.backend = backend
        self.objects = {}
        self.unavailable = False
        self.calls = []

    def _guard(self, op):
        self.calls.append(op)
        if self.unavailable:
            raise StorageUnavailable(self.backend, f"fake backend unavailable ({op})")

    def put(self, plan_id, sha256, data, media_type):
        key = storage_key(plan_id, sha256, media_type)
        self._guard("put")
        if key in self.objects:
            return {"key": key, "state": "stored", "already_present": True, "bytes": len(self.objects[key]), "dir_state": None}
        self.objects[key] = bytes(data)
        return {"key": key, "state": "stored", "already_present": False, "bytes": len(data), "dir_state": None}

    def get(self, key):
        self._guard("get")
        return self.objects.get(key)

    def stat(self, key):
        self._guard("stat")
        d = self.objects.get(key)
        return {"exists": d is not None, "bytes": (len(d) if d is not None else None)}

    def delete(self, key):
        self._guard("delete")
        return self.objects.pop(key, None) is not None

    def probe(self):
        state = "storage-unavailable (fake backend unavailable)" if self.unavailable else "stored"
        return {"backend": self.backend, "state": state, "detail": "FakeMemoryStorage", "dir_state": None,
                "dir_source": "injected", "root_present": None, "sdk_version": None, "bucket": None, "credentials_source": None}


def storage_backend(cfg=None, env=None, client_factory=None, local_root_override=None):
    """(storage, probe) según WITT_ATTESTED_BACKEND (ya tolerante en env_config: fuera de vocabulario → local con source
    'default-invalid-env:…'). `probe` lleva backend_source. JAMÁS fallback: minio sin env → storage con probe 'storage-
    unavailable (missing env: …)' y la app responde 503."""
    cfg = cfg or env_config(env)
    backend = cfg["backend"]
    if backend == "minio":
        st = MinioStorage(client_factory=client_factory, cfg=cfg, env=env)
    else:
        st = LocalStorage(root=local_root_override, cfg=cfg, env=env)
    pr = st.probe()
    pr["backend_source"] = cfg["sources"]["backend"]
    return st, pr


def durability_of(probe):
    """(E.2) `durability {backend, dir_source, dir_state, note}` para el 201 y la Hoja."""
    note = None
    if probe.get("backend") == "local" and probe.get("dir_source") == "default":
        note = DURABILITY_NOTE_LOCAL_DEFAULT
    return {"backend": probe.get("backend"), "dir_source": probe.get("dir_source"), "dir_state": probe.get("dir_state"),
            "note": note}


# ---------------------------------------------------------------------------------------------------------
# G.1 view_rule(row, viewer, cfg) — sólo el autor por default; el alcance lo declara quien sube; paciente SIEMPRE autor
# ---------------------------------------------------------------------------------------------------------
def view_rule(row, viewer, cfg=None):
    """{rule ∈ VIEW_RULES, allowed, uploaded_by_is_viewer, share_scope, team_view_env, patient_material}. viewer None →
    allowed False (la app ya respondió 401)."""
    cfg = cfg or env_config()
    uploader = row.get("uploaded_by")
    is_viewer = viewer is not None and uploader == viewer
    scope = row.get("share_scope") or "author-only"
    # (corrector F1) `env_config` entrega team_view ENVUELTO {value, source} (docstring de env_config): leer el
    # envoltorio como booleano hacía que WITT_ATTESTED_TEAM_VIEW=0 NUNCA cerrara el equipo (un dict no vacío es True).
    _tv = cfg["team_view"]
    team_env = bool(_tv.get("value")) if isinstance(_tv, dict) else bool(_tv)
    if row.get("patient_material"):
        rule, allowed = "author-only (patient-material)", is_viewer
    elif scope == "team" and team_env:
        rule, allowed = "team", viewer is not None
    else:
        rule, allowed = "author-only", is_viewer
    return {"rule": rule, "allowed": bool(allowed), "uploaded_by_is_viewer": bool(is_viewer), "share_scope": scope,
            "team_view_env": team_env, "patient_material": bool(row.get("patient_material"))}


def may_withdraw(row, viewer, cfg=None):
    cfg = cfg or env_config()
    if viewer is None:
        return False
    if row.get("uploaded_by") == viewer:
        return True
    return cfg["withdraw"] == "team"


# ---------------------------------------------------------------------------------------------------------
# A.8 serve_check(storage, row, …) — relee la fila viva, backend DE LA FILA, sha recalculado sobre lo que sale
# ---------------------------------------------------------------------------------------------------------
def serve_check(storage, row, viewer=None, cfg=None, verify_sha=True, enforce_view=None):
    """{state ∈ SERVABLE_STATES, data | None, sha256_actual, bytes, detail, sha_verified}. Orden (G.2): kill-switch →
    view_rule (sólo si enforce_view o viewer dado) → tombstone 'withdrawn' → backend de la FILA ≠ backend del storage de
    hoy → 'backend-not-configured-now' → get (None → 'bytes-missing'; StorageUnavailable → 'storage-unavailable') → sha
    recalculado (≠ → 'bytes-mismatch', data None: JAMÁS se sirve). verify_sha=False (índice minio): sólo stat, sha_verified
    False, data None."""
    cfg = cfg or env_config()
    out = {"state": None, "data": None, "sha256_actual": None, "bytes": None, "detail": None, "sha_verified": False}
    if not cfg["enabled"]:
        out["state"], out["detail"] = "kill-switch", "kill-switch WITT_ATTESTED_IMAGES=0"
        return out
    if enforce_view is None:
        enforce_view = viewer is not None
    if enforce_view:
        vr = view_rule(row, viewer, cfg)
        if not vr["allowed"]:
            out["state"], out["detail"] = "forbidden (author-only)", vr["rule"]
            return out
    if row.get("withdrawn_at"):
        out["state"], out["detail"] = "withdrawn", str(row.get("withdrawn_at"))
        return out
    if storage is None or row.get("storage_backend") != getattr(storage, "backend", None):
        out["state"] = "backend-not-configured-now"
        out["detail"] = f"row backend {row.get('storage_backend')!r}; configured {getattr(storage, 'backend', None)!r}"
        return out
    key = row.get("storage_key")
    try:
        if not verify_sha:
            st = storage.stat(key)
            if not st["exists"]:
                out["state"] = "bytes-missing"
                return out
            out["state"], out["bytes"], out["detail"] = "yes", st["bytes"], "stat only; sha not verified on index"
            return out
        data = storage.get(key)
    except StorageUnavailable as e:
        out["state"], out["detail"] = "storage-unavailable", e.detail
        return out
    if data is None:
        out["state"] = "bytes-missing"
        return out
    actual = sha256_hex(data)
    out["sha256_actual"], out["bytes"], out["sha_verified"] = actual, len(data), True
    if actual != row.get("sha256"):
        out["state"], out["detail"] = "bytes-mismatch", f"expected {row.get('sha256')}, actual {actual}"
        return out
    out["state"], out["data"] = "yes", data
    return out


# ---------------------------------------------------------------------------------------------------------
# A.9 select_for_panel(items, storage, cfg, figures_n, figures_b64_total) — lo que ven las DOS lentes
# ---------------------------------------------------------------------------------------------------------
def _iso(v):
    if v is None:
        return None
    if isinstance(v, datetime):
        if v.tzinfo is None:
            v = v.replace(tzinfo=timezone.utc)
        return v.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return str(v)


def is_attached(row):
    """Adjunta = `attached_to` sellado por el ledger al aprobar (staged e inherited por igual)."""
    return bool(row.get("attached_to"))


def select_for_panel(items, storage, cfg=None, figures_n=0, figures_b64_total=0):
    """Elegibles = attached ∧ ¬withdrawn ∧ bytes leídos del backend con sha recalculado ok ∧ bytes ≤ max_image_mb; orden de
    subida (uploaded_at, sha256); tope max_per_lens; cap b64 8 MB por petición COMPARTIDO con las figuras (figuras PRIMERO:
    `figures_b64_total` ya consumido); invariante many-image `figures_n + n ≤ 20` → recorte declarado 'many_image_guard'.
    Devuelve {attested [PANEL_ATTESTED_KEYS], n_eligible, n_delivered, n_dropped {withdrawn, missing, mismatch, size,
    lens_cap, request_cap, many_image_guard}, n_not_attached, storage_errors[], bytes_b64_total, rule}."""
    cfg = cfg or env_config()
    dropped = {"withdrawn": 0, "missing": 0, "mismatch": 0, "size": 0, "lens_cap": 0, "request_cap": 0, "many_image_guard": 0}
    errors, out, b64_total, not_attached = [], [], 0, 0
    cands = []
    for row in items or []:
        if not is_attached(row):
            not_attached += 1
            continue
        if row.get("withdrawn_at"):
            dropped["withdrawn"] += 1
            continue
        cands.append(row)
    cands.sort(key=lambda r: (_iso(r.get("uploaded_at")) or "", r.get("sha256") or ""))
    max_raw = int(float(cfg["max_image_mb"]) * 1024 * 1024)
    req_cap = REQUEST_B64_MB * 1024 * 1024
    lens_cap = int(cfg["max_per_lens"])
    many_cap = max(0, MANY_IMAGE_LIMIT - int(figures_n or 0))
    n_eligible = 0
    for row in cands:
        if (row.get("bytes") or 0) > max_raw:
            dropped["size"] += 1
            continue
        chk = serve_check(storage, row, cfg=cfg, enforce_view=False)
        if chk["state"] == "bytes-missing":
            dropped["missing"] += 1
            continue
        if chk["state"] == "storage-unavailable":
            dropped["missing"] += 1
            errors.append(f"{row.get('sha256', '')[:SHA_SHORT]}: storage-unavailable ({chk['detail']})")
            continue
        if chk["state"] == "backend-not-configured-now":
            dropped["missing"] += 1
            errors.append(f"{row.get('sha256', '')[:SHA_SHORT]}: backend-not-configured-now")
            continue
        if chk["state"] == "bytes-mismatch":
            dropped["mismatch"] += 1
            continue
        if chk["state"] != "yes":
            dropped["missing"] += 1
            errors.append(f"{row.get('sha256', '')[:SHA_SHORT]}: {chk['state']}")
            continue
        data = chk["data"]
        if len(data) > max_raw:
            dropped["size"] += 1
            continue
        n_eligible += 1
        if len(out) >= lens_cap:
            dropped["lens_cap"] += 1
            continue
        if len(out) >= many_cap:
            dropped["many_image_guard"] += 1
            continue
        b64 = base64.b64encode(data).decode("ascii")
        if int(figures_b64_total or 0) + b64_total + len(b64) > req_cap:
            dropped["request_cap"] += 1
            continue
        b64_total += len(b64)
        out.append({"id": id_of(row["sha256"]), "sha256": row["sha256"], "sha256_short": short_of(row["sha256"]),
                    "caption": row.get("caption") or "", "media_type": row.get("media_type"), "b64": b64,
                    "dims": _dims_of(row), "consent_kind": row.get("consent_kind"), "uploaded_by": row.get("uploaded_by"),
                    "uploaded_at": _iso(row.get("uploaded_at")), "class": "attested"})
    return {"attested": out, "n_eligible": n_eligible, "n_delivered": len(out), "n_dropped": dropped,
            "n_not_attached": not_attached, "storage_errors": errors, "bytes_b64_total": b64_total, "rule": SELECTION_RULE}


# ---------------------------------------------------------------------------------------------------------
# A.10 rótulo, separador y bloques ATTESTED por transporte (F3 los concatena: figuras → separador → [rótulo, imagen] × N → texto)
# ---------------------------------------------------------------------------------------------------------
def attested_text_label(k, img):
    date = (_iso(img.get("uploaded_at")) or "unknown date")[:10]
    return (f"ATTESTED IMAGE {k} — {img['id']} (human-provided PRIOR ART, NOT evidence; consent: {img.get('consent_kind')}; "
            f"uploaded by {img.get('uploaded_by') or 'unknown'} on {date}): {img.get('caption') or ''}")


def anthropic_attested_blocks(attested):
    """Bloques Anthropic Messages para las atestiguadas: [] con None/vacío; si no → [{text: separador}] + [{text: rótulo_k},
    {image_k}] × N (SIN el texto del usuario: lo añade el builder de figures)."""
    if not attested:
        return []
    blocks = [{"type": "text", "text": ATTESTED_SEPARATOR_TEXT}]
    for k, a in enumerate(attested, start=1):
        blocks.append({"type": "text", "text": attested_text_label(k, a)})
        blocks.append({"type": "image", "source": {"type": "base64", "media_type": a["media_type"], "data": a["b64"]}})
    return blocks


def openai_responses_attested_parts(attested, detail=None):
    if not attested:
        return []
    detail = detail or _figures.env_config()["openai_detail"]
    parts = [{"type": "input_text", "text": ATTESTED_SEPARATOR_TEXT}]
    for k, a in enumerate(attested, start=1):
        parts.append({"type": "input_text", "text": attested_text_label(k, a)})
        parts.append({"type": "input_image", "image_url": f"data:{a['media_type']};base64,{a['b64']}", "detail": detail})
    return parts


def openai_chat_attested_parts(attested, detail=None):
    if not attested:
        return []
    detail = detail or _figures.env_config()["openai_detail"]
    parts = [{"type": "text", "text": ATTESTED_SEPARATOR_TEXT}]
    for k, a in enumerate(attested, start=1):
        parts.append({"type": "text", "text": attested_text_label(k, a)})
        parts.append({"type": "image_url", "image_url": {"url": f"data:{a['media_type']};base64,{a['b64']}", "detail": detail}})
    return parts


# ---------------------------------------------------------------------------------------------------------
# A.11 proyecciones SIN bytes: prompt_item / frozen_item / public_item / ledger_item / thread_item / patient_material_flag
# ---------------------------------------------------------------------------------------------------------
def _dims_of(row):
    if isinstance(row.get("dims"), dict):
        return {"w": row["dims"].get("w"), "h": row["dims"].get("h")}
    return {"w": row.get("dims_w"), "h": row.get("dims_h")}


def _truncate(text, cap):
    text = "" if text is None else str(text)
    if len(text) <= cap:
        return text, False
    return text[:cap], True


def _exif_removed_of(row):
    v = row.get("exif_removed")
    if v is None:
        v = row.get("exif_removed_json")
    if isinstance(v, str):
        try:
            v = json.loads(v)
        except ValueError:
            v = [v]
    return list(v or [])


def _inherited_of(row):
    if row.get("inherited_from_plan_id") or row.get("inherited_from_run_id"):
        return {"plan_id": row.get("inherited_from_plan_id"), "run_id": row.get("inherited_from_run_id")}
    return None


def _withdrawn_of(row, seen_by_lenses=None, run_id=None):
    if not row.get("withdrawn_at"):
        return None
    seen = list(seen_by_lenses or [])
    note = WITHDRAWN_NOTE_TEMPLATE.format(lenses=", ".join(seen), run_id=run_id or "?") if seen else WITHDRAWN_NOTE_UNSEEN
    return {"at": _iso(row.get("withdrawn_at")), "by_present": bool(row.get("withdrawn_by")),
            "reason_present": bool(row.get("withdraw_reason")), "note": note}


def prompt_item(row):
    """(K.2) lo ÚNICO que ve el sintetizador y el consejo por imagen — PROMPT_ATTESTED_KEYS, bytes_delivered False."""
    it = {"id": id_of(row["sha256"]), "sha256_short": short_of(row["sha256"]), "caption": row.get("caption") or "",
          "media_type": row.get("media_type"), "dims": _dims_of(row), "requirement_id": row.get("requirement_id"),
          "attached_to": row.get("attached_to"),
          "consent": {"kind": row.get("consent_kind"), "declared": bool(row.get("consent_declared"))},
          "patient_material": bool(row.get("patient_material")), "license_declared": row.get("license_declared"),
          "uploaded_by": row.get("uploaded_by"), "uploaded_at": _iso(row.get("uploaded_at")), "class": "attested",
          "bytes_delivered": False}
    assert tuple(it.keys()) == PROMPT_ATTESTED_KEYS and not set(it) & set(FORBIDDEN_ATTESTED_PROMPT_KEYS)
    return it


def frozen_item(row, cap=FROZEN_CAPTION_CHARS, state_at_run=None, seen_by_lenses=None, n_readings=0, run_id=None):
    """AttestedImageFrozen (L): forma EXACTA ATTESTED_FROZEN_KEYS — SIN b64, SIN storage_key, SIN ruta."""
    caption, trunc = _truncate(row.get("caption"), cap)
    ctext, ctrunc = _truncate(row.get("consent_text"), FROZEN_CONSENT_TEXT_CHARS)
    declared = row.get("media_type_declared")
    seen = list(seen_by_lenses if seen_by_lenses is not None else (row.get("seen_by_lenses") or []))
    it = {
        "id": id_of(row["sha256"]), "sha256": row["sha256"], "sha256_short": short_of(row["sha256"]),
        "sha256_received": row.get("sha256_received"), "bytes": row.get("bytes"), "bytes_received": row.get("bytes_received"),
        "media_type": row.get("media_type"), "media_type_declared": declared,
        "media_type_declared_mismatch": (None if declared is None else declared != row.get("media_type")),
        "dims": _dims_of(row), "dims_source": "header", "caption": caption, "caption_truncated": trunc,
        "caption_chars": row.get("caption_chars") if row.get("caption_chars") is not None else len(row.get("caption") or ""),
        "requirement_id": row.get("requirement_id"), "attached_to": row.get("attached_to"), "attached_by": row.get("attached_by"),
        "attached_by_is_uploader": (None if not row.get("attached_by") else row.get("attached_by") == row.get("uploaded_by")),
        "date_taken": row.get("date_taken"), "method": row.get("method"),
        "consent": {"kind": row.get("consent_kind"), "declared": bool(row.get("consent_declared")),
                    "text": (ctext if row.get("consent_text") else None), "text_present": bool(row.get("consent_text")),
                    "text_truncated": ctrunc},
        "third_party_ack": bool(row.get("third_party_ack")), "patient_material": bool(row.get("patient_material")),
        "deidentified_declared": bool(row.get("deidentified_declared")), "license_declared": row.get("license_declared"),
        "share_scope": row.get("share_scope"), "exif_state": row.get("exif_state"), "exif_removed": _exif_removed_of(row),
        "uploaded_by": row.get("uploaded_by"), "uploaded_by_role": row.get("uploaded_by_role"),
        "uploaded_at": _iso(row.get("uploaded_at")), "plan_id": row.get("plan_id"), "ledger_state": row.get("ledger_state"),
        "inherited_from": _inherited_of(row),
        "storage": {"backend": row.get("storage_backend"), "key_present": bool(row.get("storage_key")),
                    "state_at_run": state_at_run if state_at_run is not None else row.get("storage_state")},
        "withdrawn": _withdrawn_of(row, seen, run_id), "seen_by_lenses": seen, "n_readings": int(n_readings or 0),
        "delivered_to_synthesizer": "captions-only", "class": "attested",
    }
    assert tuple(it.keys()) == ATTESTED_FROZEN_KEYS
    return it


def public_item(row, viewer=None, cfg=None, servable=None, url=None, withdraw_url=None, storage_state_live=None,
                state_at_run=None, seen_by_lenses=None, n_readings=0, run_id=None):
    """AttestedImageItem (índices HTTP): frozen_item + viewer_may_view (calculado en el SERVIDOR) + view_rule + servable
    {state, reason?} MEDIDO por el llamador (None → declarado no medido) + url + withdraw_url (sólo a quien puede retirar)
    + storage.state VIVO. Ensamblaje puro: sin I/O."""
    cfg = cfg or env_config()
    it = frozen_item(row, state_at_run=state_at_run, seen_by_lenses=seen_by_lenses, n_readings=n_readings, run_id=run_id)
    vr = view_rule(row, viewer, cfg)
    it["storage"]["state"] = storage_state_live if storage_state_live is not None else row.get("storage_state")
    it["viewer_may_view"] = bool(vr["allowed"]) if cfg["enabled"] else False
    it["view_rule"] = vr["rule"]
    if servable is None:
        it["servable"] = {"state": None, "reason": "not-measured"}
    elif isinstance(servable, dict):
        it["servable"] = {"state": servable.get("state"), **({"reason": servable["detail"]} if servable.get("detail") else {})}
    else:
        it["servable"] = {"state": str(servable)}
    it["url"] = url
    it["withdraw_url"] = withdraw_url if (withdraw_url and may_withdraw(row, viewer, cfg)) else None
    assert tuple(it.keys()) == ATTESTED_ITEM_KEYS
    return it


def ledger_item(row, cap=FROZEN_CAPTION_CHARS):
    """AttestedImageLedgerItem (J.4) — lo que el ledger devuelve y `_frozen_ledger_view` copia."""
    caption, trunc = _truncate(row.get("caption"), cap)
    it = {"id": id_of(row["sha256"]), "sha256": row["sha256"], "sha256_short": short_of(row["sha256"]),
          "attached_to": row.get("attached_to"), "requirement_id": row.get("requirement_id"), "caption": caption,
          "caption_truncated": trunc, "media_type": row.get("media_type"), "dims": _dims_of(row), "bytes": row.get("bytes"),
          "consent": {"kind": row.get("consent_kind"), "declared": bool(row.get("consent_declared")),
                      "text_present": bool(row.get("consent_text"))},
          "patient_material": bool(row.get("patient_material")), "deidentified_declared": bool(row.get("deidentified_declared")),
          "license_declared": row.get("license_declared"), "share_scope": row.get("share_scope"),
          "exif_state": row.get("exif_state"), "uploaded_by": row.get("uploaded_by"), "uploaded_at": _iso(row.get("uploaded_at")),
          "attached_by_is_uploader": (None if not row.get("attached_by") else row.get("attached_by") == row.get("uploaded_by")),
          "ledger_state": row.get("ledger_state"), "class": "attested"}
    assert tuple(it.keys()) == ATTESTED_LEDGER_ITEM_KEYS
    return it


def thread_item(row, cap=THREAD_CAPTION_CHARS, seen_by_lenses=None):
    """(B.6.i) thread_context.parent_attested_images[] — METADATOS, caption ≤ 200, sin bytes."""
    caption, trunc = _truncate(row.get("caption"), cap)
    it = {"id": id_of(row["sha256"]), "sha256_short": short_of(row["sha256"]), "caption": caption, "caption_truncated": trunc,
          "by": row.get("uploaded_by"), "at": _iso(row.get("uploaded_at")), "consent_kind": row.get("consent_kind"),
          "patient_material": bool(row.get("patient_material")),
          "seen_by_lenses": list(seen_by_lenses if seen_by_lenses is not None else (row.get("seen_by_lenses") or [])),
          "class": "attested"}
    assert tuple(it.keys()) == THREAD_ITEM_KEYS
    return it


def patient_material_flag(row):
    """(I.iii) bandera LISTA con gate humano, forma council.py:1569 (+ sha256_short, source): la webapp hace emitted_by.join.

    CORRECTOR (revisor 1, 2026-09-21): el `statement` llevaba los primeros 120 caracteres del CAPTION. Esa bandera viaja a
    `frozen.council.ledger.flags[]`, y de ahí (a) el PDF del servidor la imprime verbatim en la sección del consejo —
    1.100 líneas debajo de la sección 54, que suprime el caption del paciente y lo dice en voz alta — y (b)
    `council.summary_for_thread` la copia al `thread_context` del turno siguiente, que alimenta al planner y a la ronda 1
    de los 17 miembros. O sea: el caption de una biopsia salía en un PDF que circula fuera de la app y en prompts que van
    a proveedores externos, por el único camino que nadie estaba mirando.

    La bandera identifica la imagen por su sha corto y por quién la aportó; para saber QUÉ dice hay que pedir el ítem por
    su puerta, con su autorización. Una bandera es un aviso, no un canal de contenido.
    """
    return {"kind": "patient-material",
            "statement": (f"imagen atestiguada {short_of(row['sha256'])} declarada material de paciente por "
                          f"{row.get('uploaded_by')} — requiere acuse humano al aprobar el ledger"),
            "gate": "human", "emitted_by": [FLAG_EMITTED_BY], "sha256_short": short_of(row["sha256"]),
            "source": FLAG_SOURCE, "caption_omitted": CAPTION_OMITTED_REASON}


def build_row(plan_id, form, bfields, strip, ident, put, uploaded_by, uploaded_by_role, uploaded_at, ledger_state="staged",
              storage_backend_name="local", inherited_from=None):
    """Fila de plan_attested_images (ROW_KEYS) desde los productos de validate_form / validate_bytes / strip_metadata /
    identity / storage.put — el servidor pone uploaded_by/role/at (ADR-0056)."""
    row = {
        "image_id": image_id_of(plan_id, ident["sha256"]), "plan_id": plan_id, "sha256": ident["sha256"],
        "sha256_received": ident["sha256_received"], "bytes": ident["bytes"], "bytes_received": ident["bytes_received"],
        "media_type": bfields["media_type"], "media_type_declared": bfields.get("media_type_declared"),
        "dims_w": bfields["dims"]["w"], "dims_h": bfields["dims"]["h"], "caption": form["caption"],
        "caption_chars": form["caption_chars"], "consent_kind": form["consent_kind"], "consent_declared": True,
        "consent_text": form.get("consent_text"), "third_party_ack": True, "patient_material": bool(form["patient_material"]),
        "deidentified_declared": bool(form["deidentified_declared"]), "license_declared": form["license_declared"],
        "share_scope": form["share_scope"], "requirement_id": form.get("requirement_id"), "date_taken": form.get("date_taken"),
        "method": form.get("method"), "exif_state": strip["exif_state"], "exif_removed_json": json.dumps(strip["removed"]),
        "storage_backend": storage_backend_name, "storage_key": put["key"], "storage_state": put["state"],
        "uploaded_by": uploaded_by, "uploaded_by_role": uploaded_by_role, "uploaded_at": _iso(uploaded_at),
        "attached_to": None, "attached_at": None, "attached_by": None,
        "inherited_from_plan_id": (inherited_from or {}).get("plan_id"), "inherited_from_run_id": (inherited_from or {}).get("run_id"),
        "withdrawn_by": None, "withdrawn_at": None, "withdraw_reason": None, "withdraw_cascade_n": None,
    }
    row["ledger_state"] = ledger_state
    assert set(ROW_KEYS) <= set(row)
    return row


def plan_bytes_url(plan_id, sha256):
    return f"/plans/{plan_id}/attestations/{sha256}"


def run_bytes_url(run_id, sha256):
    return f"/runs/{run_id}/attestations/{sha256}"


def withdraw_url_of(plan_id, sha256):
    return f"/plans/{plan_id}/attestations/{sha256}/withdraw"


# ---------------------------------------------------------------------------------------------------------
# A.13 fixtures SINTÉTICOS generados por código (struct/zlib): PNG / JPEG / WebP / GIF mínimos con metadatos sintéticos,
#      un PDF disfrazado, un JPEG truncado, uno > tope. CERO binarios en git, CERO material real.
# ---------------------------------------------------------------------------------------------------------
def _png_chunk(ctype, payload):
    return struct.pack(">I", len(payload)) + ctype + payload + struct.pack(">I", zlib.crc32(ctype + payload) & 0xFFFFFFFF)


def _png(w, h, chunks_before_idat=(), chunks_after_idat=(), color_type=0, idat=None, rows=None):
    ihdr = struct.pack(">IIBBBBB", w, h, 8, color_type, 0, 0, 0)
    if idat is None:
        bpp = {0: 1, 2: 3, 6: 4}[color_type]
        if rows is None:
            rows = b"".join(b"\x00" + bytes((x * 7 + y * 13) & 0xFF for x in range(w * bpp)) for y in range(h))
        idat = zlib.compress(rows, 9)
    out = _PNG_SIG + _png_chunk(b"IHDR", ihdr)
    for c in chunks_before_idat:
        out += c
    out += _png_chunk(b"IDAT", idat)
    for c in chunks_after_idat:
        out += c
    return out + _png_chunk(b"IEND", b"")


def _tiff_synthetic(with_gps=True):
    """TIFF little-endian sintético: IFD0 {DateTime, (GPSInfo → GPS IFD con lat/lon FICTICIOS)} — jamás datos reales."""
    dt = b"2026:01:01 00:00:00\x00"
    ifd0_entries = 2 if with_gps else 1
    ifd0_off = 8
    ifd0_len = 2 + 12 * ifd0_entries + 4
    dt_off = ifd0_off + ifd0_len
    gps_ifd_off = dt_off + len(dt)
    ifd0 = struct.pack("<H", ifd0_entries)
    ifd0 += struct.pack("<HHII", 0x0132, 2, len(dt), dt_off)
    if with_gps:
        ifd0 += struct.pack("<HHII", 0x8825, 4, 1, gps_ifd_off)
    ifd0 += struct.pack("<I", 0)
    out = b"II*\x00" + struct.pack("<I", ifd0_off) + ifd0 + dt
    if with_gps:
        gps_len = 2 + 12 * 2 + 4
        rat_off = gps_ifd_off + gps_len
        gps = struct.pack("<H", 2)
        gps += struct.pack("<HHII", 0x0002, 5, 3, rat_off)
        gps += struct.pack("<HHII", 0x0004, 5, 3, rat_off + 24)
        gps += struct.pack("<I", 0)
        rats = struct.pack("<IIIIII", 12, 1, 34, 1, 56, 1) + struct.pack("<IIIIII", 98, 1, 76, 1, 54, 1)
        out += gps + rats
    return out


def _jpeg_segment(marker, payload):
    return b"\xff" + bytes([marker]) + struct.pack(">H", len(payload) + 2) + payload


def _jpeg(w, h, extra_segments=(), scan_blocks=None):
    """JPEG baseline gris mínimo: SOI, APP0 JFIF, [extra], DQT, SOF0, DHT×2 (un código de 1 bit), SOS, scan de ceros, EOI."""
    app0 = _jpeg_segment(0xE0, b"JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00")
    dqt = _jpeg_segment(0xDB, b"\x00" + b"\x01" * 64)
    sof0 = _jpeg_segment(0xC0, struct.pack(">BHHB", 8, h, w, 1) + b"\x01\x11\x00")
    dht_dc = _jpeg_segment(0xC4, b"\x00" + b"\x01" + b"\x00" * 15 + b"\x00")
    dht_ac = _jpeg_segment(0xC4, b"\x10" + b"\x01" + b"\x00" * 15 + b"\x00")
    sos = _jpeg_segment(0xDA, b"\x01\x01\x00\x00\x3f\x00")
    blocks = scan_blocks if scan_blocks is not None else ((w + 7) // 8) * ((h + 7) // 8)
    scan = b"\x00" * ((blocks * 2 + 7) // 8)
    return b"\xff\xd8" + app0 + b"".join(extra_segments) + dqt + sof0 + dht_dc + dht_ac + sos + scan + b"\xff\xd9"


class _BitWriter:
    def __init__(self):
        self.bits = []

    def put(self, value, n):
        for i in range(n):
            self.bits.append((value >> i) & 1)

    def bytes(self):
        out = bytearray()
        for i in range(0, len(self.bits), 8):
            b = 0
            for j, bit in enumerate(self.bits[i:i + 8]):
                b |= bit << j
            out.append(b)
        return bytes(out)


def _vp8l(w, h):
    """VP8L sin transformaciones ni caché de color, 5 códigos prefijo simples de 1 símbolo (imagen negra opaca):
    cabecera válida; los píxeles no consumen bits."""
    header = b"\x2f" + struct.pack("<I", (w - 1) | ((h - 1) << 14) | (0 << 28) | (0 << 29))
    bw = _BitWriter()
    bw.put(0, 1)            # transform_present
    bw.put(0, 1)            # color_cache
    bw.put(0, 1)            # meta prefix codes
    for sym, wide in ((0, False), (0, False), (0, False), (255, True), (0, False)):   # G, R, B, A, dist
        bw.put(1, 1)        # simple code
        bw.put(0, 1)        # num_symbols - 1 = 0
        if wide:
            bw.put(1, 1)
            bw.put(sym, 8)
        else:
            bw.put(0, 1)
            bw.put(sym, 1)
    return header + bw.bytes()


def _webp_chunk(fourcc, payload):
    return fourcc + struct.pack("<I", len(payload)) + payload + (b"\x00" if len(payload) & 1 else b"")


def _webp(chunks):
    body = b"".join(chunks)
    return b"RIFF" + struct.pack("<I", len(body) + 4) + b"WEBP" + body


def _gif_subblocks(payload):
    out = b""
    for i in range(0, len(payload), 255):
        part = payload[i:i + 255]
        out += bytes([len(part)]) + part
    return out + b"\x00"


def synthetic_fixtures(large=False):
    """{name: bytes} DETERMINISTA (cero azar, cero reloj). `large=True` añade `png_over_cap.png` (> 5 MiB) para el 413."""
    fx = {}
    # PNG 32×24 con tEXt + eXIf + tIME (tres chunks a quitar; pasa validate_bytes → sirve para el 201 con strip medido)
    text = _png_chunk(b"tEXt", b"Comment\x00synthetic ADR-0086 fixture (no real metadata)")
    exif = _png_chunk(b"eXIf", _tiff_synthetic(with_gps=True))
    tim = _png_chunk(b"tIME", struct.pack(">HBBBBB", 2026, 1, 1, 0, 0, 0))
    fx["png_text.png"] = _png(32, 24, chunks_before_idat=(text, exif), chunks_after_idat=(tim,))
    # PNG 64×48 limpio (RGB)
    fx["png_clean_64x48.png"] = _png(64, 48, color_type=2)
    # JPEG 80×60 con APP1 Exif (GPS/fecha FICTICIOS) + APP2 ICC (se conserva) + APP2 MPF + APP14 Adobe (se conserva) + COM
    app1 = _jpeg_segment(0xE1, b"Exif\x00\x00" + _tiff_synthetic(with_gps=True))
    app2_icc = _jpeg_segment(0xE2, b"ICC_PROFILE\x00\x01\x01" + b"\x00\x00\x00\x80" + b"SYNT" + b"\x02\x10\x00\x00" + b"mntr" + b"GRAY" + b"XYZ ")
    app2_mpf = _jpeg_segment(0xE2, b"MPF\x00" + b"II*\x00" + struct.pack("<I", 8) + struct.pack("<H", 0) + struct.pack("<I", 0))
    app14 = _jpeg_segment(0xEE, b"Adobe\x00\x64\x00\x00\x00\x00\x00")
    com = _jpeg_segment(0xFE, b"synthetic comment - ADR-0086 fixture; no real content")
    fx["jpeg_exif_mpf_com.jpg"] = _jpeg(80, 60, extra_segments=(app1, app2_icc, app2_mpf, app14, com))
    # WebP VP8X 32×32 con bandera EXIF + VP8L + chunk EXIF
    vp8x = _webp_chunk(b"VP8X", bytes([0x08, 0, 0, 0]) + struct.pack("<I", 31)[:3] + struct.pack("<I", 31)[:3])
    vp8l = _webp_chunk(b"VP8L", _vp8l(32, 32))
    exif_chunk = _webp_chunk(b"EXIF", _tiff_synthetic(with_gps=False))
    fx["webp_exif.webp"] = _webp((vp8x, vp8l, exif_chunk))
    # GIF89a 1×1 con Comment (se quita) + NETSCAPE2.0 (se conserva)
    gif = b"GIF89a" + struct.pack("<HHBBB", 1, 1, 0x80, 0, 0) + b"\x00\x00\x00\xff\xff\xff"
    gif += b"\x21\xfe" + _gif_subblocks(b"synthetic ADR-0086 comment")
    gif += b"\x21\xff" + b"\x0bNETSCAPE2.0" + b"\x03\x01\x00\x00" + b"\x00"
    gif += b"\x2c" + struct.pack("<HHHHB", 0, 0, 1, 1, 0) + b"\x02" + b"\x02\x44\x01" + b"\x00" + b"\x3b"
    fx["gif_comment.gif"] = gif
    # no imagen
    fx["not_image.pdf"] = b"%PDF-1.4\n1 0 obj << /Type /Catalog >> endobj\n%%EOF\n"
    # IHDR 8000×8000 (64 MP > 40) con IDAT diminuto: se rechaza SIN decodificar
    fx["png_64mp.png"] = _png(8000, 8000, idat=zlib.compress(b"\x00" * 16, 9))
    # PNG 8×8 (too-small)
    fx["png_too_small_8x8.png"] = _png(8, 8)
    # JPEG con SOF0 válido (dims 80×60 → pasa validate_bytes) y un APP1 TRUNCADO después (longitud declarada 200, quedan
    # 22 bytes) → el walker no puede garantizar el resultado → strip-failed (422 metadata-strip-failed, nada se guarda)
    trunc = b"\xff\xd8" + _jpeg_segment(0xE0, b"JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00")
    trunc += _jpeg_segment(0xDB, b"\x00" + b"\x01" * 64) + _jpeg_segment(0xC0, struct.pack(">BHHB", 8, 60, 80, 1) + b"\x01\x11\x00")
    trunc += b"\xff\xe1" + struct.pack(">H", 200) + b"Exif\x00\x00" + b"II*\x00" + b"\x08\x00\x00\x00" + b"\x00" * 6
    fx["jpeg_truncated_after_app1.jpg"] = trunc
    if large:
        payload = bytes(range(256)) * (((5 * 1024 * 1024 + 1) // 256) + 1)
        fx["png_over_cap.png"] = _png(64, 48, idat=zlib.compress(payload[:5 * 1024 * 1024 + 1], 0))
    return fx


FIXTURE_EXPECTED = {
    # name: (validate_bytes status|None(=ok), state|None, exif_state esperado tras strip | 'strip-failed' | None)
    "png_text.png": (None, None, "stripped (tEXt, eXIf, tIME)"),
    "png_clean_64x48.png": (None, None, "none-found"),
    "jpeg_exif_mpf_com.jpg": (None, None, "stripped (APP1, APP2:MPF, COM)"),
    "webp_exif.webp": (None, None, "stripped (EXIF)"),
    "gif_comment.gif": (415, "unsupported-media-type", "stripped (Comment)"),
    "not_image.pdf": (415, "unsupported-media-type", None),
    "png_64mp.png": (422, "image-too-many-pixels", "none-found"),
    "png_too_small_8x8.png": (422, "image-too-small", "none-found"),
    "jpeg_truncated_after_app1.jpg": (None, None, "strip-failed"),
    "png_over_cap.png": (413, "attested_image_too_large", "none-found"),
}


def fixtures_manifest(large=True, cfg=None):
    """MANIFEST (texto) determinista: por fixture sniff/dims/bytes/sha256_received y, tras strip, exif_state/removed/sha256/
    bytes (o {state 'strip-failed', detail}); `expected` = veredicto de validate_bytes con la cfg por default."""
    cfg = cfg or env_config({})
    out = {"contract": "1.14", "adr": "ADR-0086", "slice": "F1", "generated_by": "attestations.synthetic_fixtures()",
           "module_version": MODULE_VERSION,
           "note": ("Fixtures 100% SINTÉTICOS generados por código (struct/zlib) — cero binarios en git, cero material real; "
                    "los metadatos (Exif/GPS/fecha/comentarios) son FICTICIOS. sha256_received = bytes generados; strip.sha256 = "
                    "bytes ALMACENADOS (post-strip), la identidad canónica."),
           "fixtures": {}}
    for name, data in sorted(synthetic_fixtures(large=large).items()):
        mime = sniff_mime(data)
        rec = {"synthetic": True, "bytes": len(data), "sha256_received": sha256_hex(data), "media_type_sniffed": mime,
               "dims": image_dims(data), "strip": None, "expected": None}
        exp = FIXTURE_EXPECTED.get(name)
        if exp:
            rec["expected"] = {"validate_bytes_status": exp[0], "validate_bytes_state": exp[1], "exif_state": exp[2]}
        if mime in _WALKERS:
            try:
                s = strip_metadata(data, mime, "strip")
                rec["strip"] = {"exif_state": s["exif_state"], "removed": s["removed"], "sha256": sha256_hex(s["data"]),
                                "bytes": len(s["data"]), "sha_changed": sha256_hex(s["data"]) != rec["sha256_received"]}
            except MetadataStripError as e:
                rec["strip"] = {"state": "strip-failed", "detail": e.detail}
        out["fixtures"][name] = rec
    return out
