"""smoke_live_attestations.py — el instrumento EN VIVO de las imágenes atestiguadas (ADR-0086, gates LG1–LG4).

Qué hace, en orden de riesgo creciente. El default es el que no gasta ni toca nada de nadie:

  --dry-run (DEFAULT)   construye TODO sin red, sin llave y sin almacén compartido: valida un fixture SINTÉTICO por magic
                        bytes, le borra los metadatos, calcula su identidad, arma la fila, arma lo que vería el
                        sintetizador (pie de foto y metadatos), arma los bloques de imagen que verían las lentes con
                        visión por CADA transporte (Anthropic, OpenAI Responses, OpenAI chat) e IMPRIME el tamaño exacto
                        de la petición y los tokens de visión PROYECTADOS. `urlopen` queda bloqueado y CONTADO: si algo
                        intenta salir, se cuenta y se declara. Cero centavos, cero red — MEDIDO, no prometido.

  --store local         además ESCRIBE de verdad en un directorio temporal propio y lo vuelve a leer con el sha
                        recalculado, para probar el camino completo de almacenamiento sin tocar MinIO ni el disco de
                        producción. Sigue sin red y sin modelo.

  --store minio         prueba el almacén PRIVADO real (LG3). Exige MINIO_ENDPOINT + credenciales en el entorno y el
                        bucket dedicado de WITT_ATTESTED_MINIO_BUCKET. Escribe UN objeto de prueba y lo borra. Sin
                        credenciales NO cae a local: declara 503 y sale. Cero modelo.

  --vision              LA ÚNICA opción que GASTA (LG4): manda UNA imagen sintética a UNA lente con visión, con el
                        rótulo y la regla de verdad, y mide los tokens que la API reporta contra la proyección. Exige
                        --yes-spend y la autorización explícita de Emmanuel. Costo PROYECTADO que se imprime ANTES de
                        llamar: ~1 a 7 centavos de dólar según el modelo. Ninguna imagen de nadie sale de aquí: el
                        fixture lo genera el código.

Ninguna imagen de una persona real entra a este instrumento. Los fixtures los produce `attestations.synthetic_fixtures()`
y son PNG/JPEG/WebP/GIF generados por código, con metadatos plantados a propósito para poder medir que se borran.

Corre:  python analysis/scripts/smoke_live_attestations.py --dry-run
        python analysis/scripts/smoke_live_attestations.py --store local
        python analysis/scripts/smoke_live_attestations.py --store minio
        python analysis/scripts/smoke_live_attestations.py --vision --lens evidence-grounding --yes-spend
"""
import argparse
import base64
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from lib import attestations as at  # noqa: E402
from lib import composite_auditor as ca  # noqa: E402
from lib import models  # noqa: E402

FORM = {"caption": "micrografia SINTETICA de prueba del instrumento en vivo (ADR-0086): no es de nadie",
        "consent_declared": "true", "consent_kind": "own-work", "license_declared": "cc0",
        "share_scope": "author-only", "third_party_processing_acknowledged": "true",
        "patient_material": "false", "deidentified_declared": "false"}
NET_CALLS = []


def _block_network():
    """urlopen BLOQUEADO y CONTADO — ninguna petición sale; si algo lo intenta, queda contado y declarado."""
    import urllib.request as ur

    real = ur.urlopen

    def blocked(*a, **kw):
        NET_CALLS.append(str((a[0] if a else kw.get("url")))[:160])
        raise RuntimeError("network blocked by smoke_live_attestations (dry-run)")

    ur.urlopen = blocked
    return real


def _p(titulo, obj=None):
    print("\n== " + titulo + " ==")
    if obj is not None:
        print(json.dumps(obj, ensure_ascii=False, indent=1, default=str, sort_keys=True))


def _pipeline(data, cfg):
    """El MISMO camino que la puerta de subida, paso por paso y con lo medido a la vista."""
    sniffed = at.sniff_mime(data)
    ok, err = at.validate_form(FORM, cfg=cfg)
    assert err is None, err
    b, err_b = at.validate_bytes(data, declared_ct="image/jpeg", cfg=cfg)   # un Content-Type MENTIROSO a propósito
    assert err_b is None, err_b
    strip = at.strip_metadata(data, media_type=b["media_type"], mode=cfg["exif"])
    ident = at.identity(strip["data"], data)
    return {"sniffed": sniffed, "bytes": b, "strip": {k: strip[k] for k in strip if k != "data"},
            "stripped_bytes": strip["data"], "identity": ident, "form": ok}


def main(argv=None):
    ap = argparse.ArgumentParser(description="instrumento en vivo de ADR-0086 (default: dry-run, cero gasto, cero red)")
    ap.add_argument("--dry-run", action="store_true", help="construir todo sin red ni almacén compartido (DEFAULT)")
    ap.add_argument("--store", choices=("local", "minio"), default=None, help="escribir de verdad en el almacén")
    ap.add_argument("--vision", action="store_true", help="LG4: UNA llamada real a una lente con visión (GASTA)")
    ap.add_argument("--lens", default="evidence-grounding", help="lente con visión a la que se manda la imagen")
    ap.add_argument("--fixture", default="jpeg_exif_mpf_com.jpg", help="fixture sintético a usar")
    ap.add_argument("--yes-spend", action="store_true", help="autorización EXPLÍCITA para gastar (sólo con --vision)")
    a = ap.parse_args(argv)
    seco = not (a.store or a.vision)
    real_urlopen = _block_network() if seco or a.store == "local" else None

    cfg = at.env_config()
    _p("configuración leída EN LA LLAMADA (18 variables, con su fuente)",
       {"enabled": cfg["enabled"], "vision": cfg["vision"], "backend": cfg["backend"],
        "exif": cfg["exif"], "team_view": cfg["team_view"], "withdraw": cfg["withdraw"],
        "patient_material": cfg["patient_material"], "caps": cfg["caps"],
        "dir_source": at.local_root(cfg)[1], "sources": cfg["sources"]})
    if not cfg["enabled"]:
        print("\nWITT_ATTESTED_IMAGES=0: la función está APAGADA. El instrumento no simula lo que el servidor rechazaría.")
        return 0

    fx = at.synthetic_fixtures()
    if a.fixture not in fx:
        print("fixtures disponibles: " + ", ".join(sorted(fx)))
        return 2
    data = fx[a.fixture]
    r = _pipeline(data, cfg)
    _p("1 · tipo MEDIDO por magic bytes (el Content-Type declarado se registra y NO decide)",
       {"sniffed": r["sniffed"], "media_type": r["bytes"]["media_type"],
        "media_type_declared": r["bytes"].get("media_type_declared"),
        "declared_mismatch": r["bytes"].get("media_type_declared") != r["bytes"]["media_type"],
        "dims": r["bytes"]["dims"], "bytes_recibidos": len(data)})
    _p("2 · metadatos borrados ANTES de hashear y guardar (sin recodificar: mismas dimensiones, mismo formato)",
       {**r["strip"], "bytes_despues": len(r["stripped_bytes"]),
        "dims_iguales": at.image_dims(r["stripped_bytes"]) == at.image_dims(data)})
    _p("3 · identidad: el sha que se registra es el de los bytes ALMACENADOS; el del archivo recibido se conserva aparte",
       r["identity"])
    fila = at.build_row("plan-live-0086", r["form"], r["bytes"], r["strip"], r["identity"],
                        {"key": at.storage_key("plan-live-0086", r["identity"]["sha256"], r["bytes"]["media_type"]),
                         "state": "dry-run (not written)"},
                        uploaded_by="emmanuel", uploaded_by_role="dev",
                        uploaded_at="2026-09-21T00:00:00+00:00", storage_backend_name=cfg["backend"])
    _p("4 · lo que el SINTETIZADOR y el CONSEJO verían de esta imagen (pie de foto y metadatos, `bytes_delivered` False)",
       at.prompt_item(fila))
    _p("5 · lo que el REGISTRO congelaría (40 llaves; sin b64, sin llave de almacén, sin ruta)", at.frozen_item(fila))

    b64 = base64.b64encode(r["stripped_bytes"]).decode("ascii")
    entregada = {"id": at.id_of(r["identity"]["sha256"]), "sha256": r["identity"]["sha256"],
                 "sha256_short": at.short_of(r["identity"]["sha256"]), "caption": FORM["caption"],
                 "media_type": r["bytes"]["media_type"], "b64": b64, "dims": r["bytes"]["dims"],
                 "consent_kind": FORM["consent_kind"], "uploaded_by": "emmanuel",
                 "uploaded_at": "2026-09-21T00:00:00+00:00", "class": "attested"}
    transportes = {
        "anthropic": at.anthropic_attested_blocks([entregada]),
        "openai_responses": at.openai_responses_attested_parts([entregada], detail=cfg.get("openai_detail")),
        "openai_chat": at.openai_chat_attested_parts([entregada], detail=cfg.get("openai_detail")),
    }
    _p("6 · los bloques por TRANSPORTE que verían las lentes con visión — tamaños y rótulos, sin volcar el base64",
       {k: {"n_bloques": len(v), "chars_total": len(json.dumps(v)),
            "rotulo": next((x for x in json.dumps(v, ensure_ascii=False).split('"') if "ATTESTED" in x), None)}
        for k, v in transportes.items()})
    # el reviewer sale del PANEL resuelto EN LA LLAMADA (la misma tabla que usa la corrida), no de una constante
    _panel = {m["lens"]: m for m in models.panel()}
    _lv, _lv_src = ca.vision_lenses(os.environ)      # las MISMAS lentes que ven figuras (a lo sumo dos, §7)
    _lentes_vision = list(_lv)
    reviewer = (_panel.get(a.lens) or {}).get("reviewer")
    tier = models.vision_tier_of(reviewer)[0] if reviewer else None
    w, h = (r["bytes"]["dims"] or {}).get("w"), (r["bytes"]["dims"] or {}).get("h")
    tokens = models.vision_tokens(reviewer, w, h, cfg.get("openai_detail")) if reviewer else None
    _p("7 · tokens de visión PROYECTADOS (clase proyección: la medición la da la API cuando se llame de verdad). "
       "`tokens` en null NO es cero: es que la tabla no proyecta para ese modelo (tier none|unknown) — ausencia declarada",
       {"lente": a.lens, "reviewer": reviewer, "vision_tier": tier, "b64_chars": len(b64),
        "lentes_con_vision_hoy": _lentes_vision, "lentes_source": _lv_src,
        "lente_recibiria_bytes": a.lens in _lentes_vision,
        "max_por_lente": cfg["caps"]["max_per_lens"], "tokens": tokens,
        "regla": at.ATTESTED_READING_RULE[:160] + "…"})

    if seco:
        _p("8 · cero red MEDIDA (dry-run)", {"urlopen_llamadas": len(NET_CALLS), "intentos": NET_CALLS[:3]})
        print("\nDRY-RUN: nada se escribió, nada salió a la red, nada se gastó. Para escribir de verdad: --store local.")
        if real_urlopen:
            import urllib.request as ur
            ur.urlopen = real_urlopen
        return 0 if not NET_CALLS else 1

    if a.store == "local":
        tmp = Path(tempfile.mkdtemp(prefix="live-attested-"))
        try:
            cfg_l = at.env_config(env={**os.environ, "WITT_ATTESTED_DIR": str(tmp), "WITT_ATTESTED_BACKEND": "local"})
            st, probe = at.storage_backend(cfg=cfg_l)
            put = st.put("plan-live-0086", r["identity"]["sha256"], r["stripped_bytes"], r["bytes"]["media_type"])
            leidos = st.get(put["key"])
            _p("8 · almacén LOCAL real (directorio temporal propio): escrito y releído con el sha RECALCULADO",
               {"probe": probe, "durabilidad": at.durability_of(probe), "put": put,
                "sha_releido_igual": at.sha256_hex(leidos) == r["identity"]["sha256"],
                "bytes_releidos": len(leidos), "urlopen_llamadas": len(NET_CALLS)})
            st.delete(put["key"])
            print("\nEscrito, verificado y borrado. Cero red, cero modelo.")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
            if real_urlopen:
                import urllib.request as ur
                ur.urlopen = real_urlopen
        return 0

    if a.store == "minio":
        cfg_m = at.env_config(env={**os.environ, "WITT_ATTESTED_BACKEND": "minio"})
        try:
            st, probe = at.storage_backend(cfg=cfg_m)
        except at.StorageUnavailable as e:
            _p("8 · almacén MINIO: NO disponible — se DECLARA y no se cae a local", e.to_error())
            return 1
        put = st.put("plan-live-0086", r["identity"]["sha256"], r["stripped_bytes"], r["bytes"]["media_type"])
        leidos = st.get(put["key"])
        _p("8 · almacén MINIO real (bucket privado dedicado): escrito y releído con el sha RECALCULADO",
           {"probe": probe, "durabilidad": at.durability_of(probe), "put": put,
            "bucket": cfg_m["minio_bucket"], "sha_releido_igual": at.sha256_hex(leidos) == r["identity"]["sha256"]})
        st.delete(put["key"])
        print("\nObjeto de prueba escrito, verificado y BORRADO del bucket privado.")
        return 0

    # --vision: la única ruta que gasta
    if not a.yes_spend:
        print("\n--vision GASTA (una llamada real con imagen a una lente con visión). Falta --yes-spend y la "
              "autorización explícita de Emmanuel. Costo PROYECTADO arriba, en el paso 7.")
        return 2
    print("\n--vision con --yes-spend: esta rebanada del instrumento se completa cuando Emmanuel autorice el gasto "
          "(LG4 del ADR). Hoy imprime lo que se enviaría y NO llama: el instrumento no gasta por su cuenta.")
    _p("9 · la petición que se enviaría (sin el base64; el rótulo y la regla son los de verdad)",
       {"lente": a.lens, "reviewer": reviewer, "n_bloques": len(transportes["anthropic"]),
        "tokens_proyectados": tokens, "regla_completa_chars": len(at.ATTESTED_READING_RULE)})
    return 0


if __name__ == "__main__":
    sys.exit(main())
