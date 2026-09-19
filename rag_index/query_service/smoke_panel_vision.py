"""smoke_panel_vision.py — gate determinista de la rebanada F3 de ADR-0083 (G — panel con visión) en
composite_auditor.py + models.py: las DOS lentes que ven figuras, los TRES transportes con `user_content`, la fila
`saw_figures` MEDIDA, `figure_readings` como JUICIO etiquetado, `audit.vision`, el kill-switch byte a byte y la proyección
pública de tokens de visión — todo con jueces FAKEADOS, bytes REALES del fixture CC BY (zip reducido de PMC11379296) y cero red.

Qué MIDE (100% offline; caller inyectado; `urllib.request.urlopen` bloqueado y contado = 0):
  - fixture: los 9 JPG del zip CC BY decodifican a los sha256 / dims / bytes del MANIFEST (medición, no supuesto); el PNG 1×1
    del zip NC SINTÉTICO da media_type 'image/png' por magic (≠ extensión .jpg).
  - literales congelados: VISION_LENSES == el default de figures.ENV_SPECS; SAW_FIGURES_DETAILS / VISION_STATES cerrados;
    FIGURE_READING_RULE literal (G.3); VERDICT_TOOL gana `figure_readings` OPCIONAL y, sin esa propiedad, es BYTE A BYTE el de
    contract-1.11-frozen (sha16 golden @ ca9a03d); _LENS_CHARGES intacto (sha16 golden).
  - vision_lenses(env): unset → default declarado; token fuera de models.LENSES o CSV vacío → default 'default-invalid-env';
    CSV válido → tokens distintos en orden con 'env:'.
  - transportes SIN user_content = 1.11 byte a byte: cuerpo REAL de _anthropic_tool_call (urlopen fake) con "content": user_text;
    _responses_kwargs "input" == user_text (y == con user_content=None explícito); _openai_chat_call content == user_text.
  - con 2 imágenes: Anthropic [text, image(base64, media_type medido, data == bytes originales), text, image, text(user_text)];
    Responses input [{role user, content [input_text, input_image(data URL, detail), …, input_text]}]; Chat messages[1].content
    [text, image_url{url data:, detail}, …, text]; detail de WITT_FIGURES_OPENAI_DETAIL (default high; env low).
  - _default_caller: arma los bloques por `member['api']` y SOLO cuando el member trae `figures`; sin figuras NO pasa el kwarg
    (un fake con la firma vieja sigue aceptado).
  - audit() con el panel g2 de la tabla y 9 figuras: el fake recibe member['figures'] SOLO en evidence-grounding y
    reproducibility (assert exacto por lente), su system contiene FIGURE_READING_RULE y los otros dos NO (byte a byte el de
    1.11); saw_figures.n 9/9/0/0 con detail 'sent' | 'lens-not-in-vision-lenses'; sha256s == los 9 del MANIFEST;
    bytes_b64_total == Σ len(b64); visual_tokens_projected 5037 (tier estándar, Σ⌈w/28⌉×⌈h/28⌉) y 5525 (tiles: 9×85+28×170)
    con fórmula/tier de models.vision_tokens; api_form_state 'verified by doc' vs la forma chat 'not re-verified';
    audit.vision {state 'sent', lenses, lenses_source, rule, n_images_by_lens, bytes_b64_sent_total, tokens…};
    NINGUNA b64 ni 'data:image' en json.dumps(audit); panel_signature IDÉNTICO con y sin figuras.
  - vision_lenses=('correctness',) → sólo correctness ve (lenses_source 'caller'); lista inválida → default declarado.
  - figures=None → filas con el keyset de 1.11 + saw_figures (detail 'no-eligible-figures' | 'lens-not-in-vision-lenses');
    vision.state 'no-eligible-figures'.
  - figure_readings: lista → parseadas + class 'model-judgment' + dropped; string → [] + dropped 1; id no entregado, duplicado,
    consistent_with_caption fuera de vocabulario → dropped; fig_id pelón único resuelve; > 400 chars → truncado declarado;
    numerals_present MEDIDO; no emitir ≠ emitir []; una lente sin imágenes que emite → todo dropped.
  - juez errored conserva saw_figures y attempts[].usage; 2 intentos con imágenes → attempts_with_images 2 y el reenvío se
    MIDE en vision.bytes_b64_sent_total (×2).
  - WITT_FIGURES_MAX_PER_LENS=3 → 3 bloques + n_dropped.lens_cap 6; =0 → 'no-eligible-figures'; tope de petición
    (figures.REQUEST_B64_MB parcheado) → n_dropped.request_cap; figura sin b64/media inválido → n_dropped.invalid.
  - vision_tier 'unknown' (id fuera de tabla) o 'none' (fila embed) → 0 bloques + 'model-vision-unknown'; familia desconocida
    → 'api-form-not-verified'.
  - WITT_FIGURES_VISION=0 → 0 imágenes en todas, detail kill-switch, vision.state kill-switch, enabled False, system sin regla.
  - WITT_FIGURES=0 (M.1) → NINGUNA llave nueva (ni saw_figures ni vision), member sin figures, system byte a byte.
  - WITT_FIGURES_COUNT_TOKENS=1 → tokens_measured = input_tokens − count_tokens (fake) SOLO en la lente Anthropic con imágenes;
    OpenAI → 'not-available'; conteo que falla → 'error: <kind>'; =0 → 'not-requested'.
  - figure_readings_from_panel; apply_to_bundle copia `vision` (answer_pipeline REAL); firmas del contrato F3.

Ningún id de modelo se escribe aquí como literal: todos salen de models.py (gate estático M.4 de smoke_models).

Corre (máscara offline):
  WITT_BACKEND_DB_URL="sqlite:///C:/Users/Emmanuel/AppData/Local/Temp/claude/witt-smokes/adr83-panel-vision.db"
  NEO4J_URI="" RAG_BACKEND=sparse OPENAI_API_KEY="" ANTHROPIC_API_KEY="" WITT_RUN_ORIGIN=smoke
  python rag_index/query_service/smoke_panel_vision.py
"""
import base64
import hashlib
import inspect
import json
import os
import sys
import urllib.request
import zipfile
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
FIX = HERE / "fixtures" / "figures"
sys.path.insert(0, str(ROOT / "analysis" / "scripts"))
os.environ["ANTHROPIC_API_KEY"] = ""
os.environ["OPENAI_API_KEY"] = ""
# El gate mide con DEFAULTS declarados: ninguna env de modelos/panel/figuras se hereda del proceso
for _k in list(os.environ):
    if (_k.startswith("WITT_FIGURES") or _k.startswith("WITT_MODEL") or _k.startswith("WITT_JUDGE") or _k.startswith("WITT_PANEL")
            or _k.startswith("WITT_OPENAI") or _k.startswith("WITT_ANTHROPIC") or _k.startswith("WITT_COUNCIL")
            or _k in ("OPENAI_JUDGE_MODEL", "WITT_CG_COUNCIL_COMPONENT")):
        os.environ.pop(_k, None)

_NET_CALLS = []


def _blocked_urlopen(*a, **k):
    _NET_CALLS.append(getattr(a[0], "full_url", repr(a[0])) if a else repr(k))
    raise AssertionError("smoke: urllib.request.urlopen bloqueado (cero red)")


urllib.request.urlopen = _blocked_urlopen

from lib import composite_auditor as ca  # noqa: E402
from lib import figures as F  # noqa: E402
from lib import models  # noqa: E402

CHECKS = []


def check(name, cond, detail=""):
    CHECKS.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + name + (("  -> " + detail) if detail else ""))


def _raises(fn):
    try:
        fn()
    except Exception as e:  # noqa: BLE001
        return e
    return None


def dumps(o):
    return json.dumps(o, sort_keys=True, ensure_ascii=True, separators=(",", ":"))


def sha16(o):
    return hashlib.sha256(dumps(o).encode("utf-8")).hexdigest()[:16]


ca._backoff = lambda seconds: None
G2 = models.GENERATIONS["g2-2026-09"]["defaults"]
HAIKU = G2["judge.evidence-grounding"]          # vision_tier standard-1568
OPUS = G2["synthesizer"]                         # high-res-2576
GPT_BRIDGE = G2["judge.reproducibility"]         # tile-512 · openai-chat-completions
ASTRA = next(m for m, r in models.MODELS.items() if r["status"] == "candidate")   # patch-32 · openai-responses
EMBED = next(m for m, r in models.MODELS.items() if r["status"] == "embed")       # vision_tier none
FAKE_KEY = "smoke-fake-anthropic-key-not-a-secret"
VOK = {"verdict": "APPROVE", "caught": "", "correction_applied": "", "confidence": 0.9, "reasons": []}
CLAIM = {"direct_answer": "wt1a marks the pronephros [1].", "stated_confidence": 0.7}
EVID = {"path_a": [{"id": "CORPUS-2026-0001", "text": "wt1a"}]}
DET = {"admissible": True}
PMCID = "PMC11379296"

# =====================================================================================================================
# 0. Fixture: los 9 JPG REALES del zip CC BY → PANEL_FIGURE_KEYS; medidos contra el MANIFEST (no supuestos)
# =====================================================================================================================
MANIFEST = json.loads((FIX / "MANIFEST.json").read_text(encoding="utf-8"))
_entries = {e["href"]: e for e in MANIFEST["zips"][PMCID]["entries"]}
_z = zipfile.ZipFile(FIX / MANIFEST["zips"][PMCID]["file"])
FIGS = []
for _name in sorted(n for n in _z.namelist() if n.lower().endswith(".jpg")):
    _b = _z.read(_name)
    _fid = Path(_name).stem
    FIGS.append({"id": f"{PMCID}#{_fid}", "fig_id": _fid, "label": f"Fig {len(FIGS) + 1}", "caption": f"caption of {_fid}",
                 "license": {"id": "cc-by"}, "sha256": F.sha256_bytes(_b), "media_type": F.sniff_mime(_b),
                 "b64": base64.b64encode(_b).decode("ascii"), "dims_measured": F.image_dims(_b), "_bytes": len(_b),
                 "_href": Path(_name).name})
check("fixture CC BY: 9 JPG en el zip reducido; sha256 / dims / bytes de cada uno == MANIFEST.zips.PMC11379296.entries (medido al "
      "leer); media_type 'image/jpeg' por magic; hrefs pone.0307390.g001..g009",
      len(FIGS) == 9 and all(_entries[f["_href"]]["sha256"] == f["sha256"] and _entries[f["_href"]]["dims"] == f["dims_measured"]
                             and _entries[f["_href"]]["bytes"] == f["_bytes"] and f["media_type"] == "image/jpeg" for f in FIGS)
      and [f["fig_id"] for f in FIGS] == [f"pone.0307390.g00{i}" for i in range(1, 10)],
      f"dims={[ (f['dims_measured']['w'], f['dims_measured']['h']) for f in FIGS ]}")
for f in FIGS:
    f.pop("_bytes"), f.pop("_href")
B64_TOTAL = sum(len(f["b64"]) for f in FIGS)
SHAS = [f["sha256"] for f in FIGS]
_zn = zipfile.ZipFile(FIX / MANIFEST["zips"]["PMC11647118"]["file"])
_png = _zn.read("fx1.jpg")
PNG_FIG = {"id": "PMC11647118#undfig1", "fig_id": "undfig1", "label": None, "caption": "graphical abstract",
           "license": {"id": "cc-by-nc"}, "sha256": F.sha256_bytes(_png), "media_type": F.sniff_mime(_png),
           "b64": base64.b64encode(_png).decode("ascii"), "dims_measured": F.image_dims(_png)}
check("fixture NC SINTÉTICO: fx1.jpg es un PNG 1×1 → media_type 'image/png' por magic (≠ mime_from_extension 'image/jpeg'): "
      "el transporte manda el media_type MEDIDO, no el de la extensión",
      PNG_FIG["media_type"] == "image/png" and PNG_FIG["dims_measured"] == {"w": 1, "h": 1}
      and F.mime_from_extension("fx1.jpg") == "image/jpeg")

# =====================================================================================================================
# 1. Literales congelados y goldens @ contract-1.11-frozen (ca9a03d)
# =====================================================================================================================
_default_lenses = next(s[2] for s in F.ENV_SPECS if s[1] == "WITT_FIGURES_VISION_LENSES")
check("(G.1) VISION_LENSES == ('evidence-grounding', 'reproducibility') == el default de figures.ENV_SPECS (una verdad, dos sedes); "
      "ambas ∈ models.LENSES",
      ca.VISION_LENSES == ("evidence-grounding", "reproducibility") == tuple(_default_lenses.split(","))
      and all(l in models.LENSES for l in ca.VISION_LENSES))
check("(G.6) vocabularios CERRADOS: SAW_FIGURES_DETAILS (6) y VISION_STATES (3) exactos; TOKENS_MEASURED_STATES (5) + prefijo 'error: '",
      ca.SAW_FIGURES_DETAILS == ("sent", "lens-not-in-vision-lenses", "kill-switch WITT_FIGURES_VISION=0", "no-eligible-figures",
                                 "model-vision-unknown", "api-form-not-verified")
      and ca.VISION_STATES == ("sent", "kill-switch WITT_FIGURES_VISION=0", "no-eligible-figures")
      and len(ca.TOKENS_MEASURED_STATES) == 5 and ca.TOKENS_MEASURED_PREFIXES == ("error: ",))
check("(G.3) FIGURE_READING_RULE literal del ADR: 'Use them ONLY to judge whether the claim misrepresents', 'NEVER derive, read off "
      "or estimate numbers', 'numbers must come from text', 'ONLY in `figure_readings`', 'model judgment, never a measurement'; "
      "FIGURE_READING_RULE_SHORT 'never derive numbers from the image' vive en la description del tool",
      all(s in ca.FIGURE_READING_RULE for s in ("Use them ONLY to judge whether the claim misrepresents what the figure shows",
                                                 "NEVER derive, read off or estimate numbers", "numbers must come from text",
                                                 "ONLY in `figure_readings`", "model judgment, never a measurement"))
      and ca.FIGURE_READING_RULE_SHORT == "never derive numbers from the image"
      and ca.FIGURE_READING_RULE_SHORT in ca.VERDICT_TOOL["input_schema"]["properties"]["figure_readings"]["description"]
      and "never numbers read off the image" in ca.VERDICT_TOOL["input_schema"]["properties"]["figure_readings"]["description"])
_props = ca.VERDICT_TOOL["input_schema"]["properties"]
_fr = _props.get("figure_readings")
_tool_1_11 = json.loads(json.dumps(ca.VERDICT_TOOL))
_tool_1_11["input_schema"]["properties"].pop("figure_readings")
VERDICT_TOOL_GOLDEN_CA9A03D = "807b254ee9ee7cce"     # sha16(json sort_keys) de composite_auditor.VERDICT_TOOL @ ca9a03d (medido 2026-09-16)
LENS_CHARGES_GOLDEN_CA9A03D = "9295020260aa3100"     # sha16 de _LENS_CHARGES @ ca9a03d — la regla NO se mete en las charges
check("(G.5) VERDICT_TOOL.figure_readings OPCIONAL: array de {fig_id str, reading str maxLength 400, consistent_with_caption bool|null} "
      "con required [fig_id, reading]; NO en `required` del tool; description 'vision lenses ONLY'",
      isinstance(_fr, dict) and _fr["type"] == "array" and _fr["items"]["required"] == ["fig_id", "reading"]
      and _fr["items"]["properties"]["reading"]["maxLength"] == 400 == ca.FIGURE_READING_MAX_CHARS
      and _fr["items"]["properties"]["consistent_with_caption"]["type"] == ["boolean", "null"]
      and "figure_readings" not in ca.VERDICT_TOOL["input_schema"]["required"]
      and _fr["description"].startswith("vision lenses ONLY"))
check("GOLDEN @ ca9a03d: VERDICT_TOOL sin `figure_readings` es BYTE A BYTE el de contract-1.11-frozen (sha16 807b254ee9ee7cce) y "
      "_LENS_CHARGES no cambió (sha16 9295020260aa3100): la regla entra al system, no a las charges",
      sha16(_tool_1_11) == VERDICT_TOOL_GOLDEN_CA9A03D and sha16(ca._LENS_CHARGES) == LENS_CHARGES_GOLDEN_CA9A03D,
      f"tool={sha16(_tool_1_11)} charges={sha16(ca._LENS_CHARGES)}")

# =====================================================================================================================
# 2. vision_lenses(env)
# =====================================================================================================================
check("(G.1) vision_lenses: unset → (VISION_LENSES, 'default-unset:WITT_FIGURES_VISION_LENSES'); token fuera de models.LENSES → "
      "default 'default-invalid-env:…'; CSV vacío → 'default-invalid-env'; CSV válido con espacios y duplicado → tokens DISTINTOS "
      "en orden con 'env:…'",
      ca.vision_lenses({}) == (ca.VISION_LENSES, "default-unset:WITT_FIGURES_VISION_LENSES")
      and ca.vision_lenses({"WITT_FIGURES_VISION_LENSES": "correctness,foo"}) == (ca.VISION_LENSES, "default-invalid-env:WITT_FIGURES_VISION_LENSES")
      and ca.vision_lenses({"WITT_FIGURES_VISION_LENSES": " , "}) == (ca.VISION_LENSES, "default-invalid-env:WITT_FIGURES_VISION_LENSES")
      and ca.vision_lenses({"WITT_FIGURES_VISION_LENSES": "correctness, overclaim ,correctness"}) == (("correctness", "overclaim"), "env:WITT_FIGURES_VISION_LENSES"))
check("(G.1, corrector) «at most two panel lenses» (CLAUDE.md §7 / N.h) la HACE CUMPLIR el código: VISION_LENSES_MAX == 2; un CSV con 3 o 4 lentes "
      "válidas → default VISION_LENSES DECLARADO 'default-invalid-env:WITT_FIGURES_VISION_LENSES (>2 lenses)'; 2 lentes distintas al default → 'env:…'",
      ca.VISION_LENSES_MAX == 2 and len(ca.VISION_LENSES) <= ca.VISION_LENSES_MAX
      and ca.vision_lenses({"WITT_FIGURES_VISION_LENSES": "correctness,overclaim,evidence-grounding,reproducibility"})
      == (ca.VISION_LENSES, "default-invalid-env:WITT_FIGURES_VISION_LENSES (>2 lenses)")
      and ca.vision_lenses({"WITT_FIGURES_VISION_LENSES": "correctness,overclaim,reproducibility"})
      == (ca.VISION_LENSES, "default-invalid-env:WITT_FIGURES_VISION_LENSES (>2 lenses)")
      and ca.vision_lenses({"WITT_FIGURES_VISION_LENSES": "correctness,overclaim"}) == (("correctness", "overclaim"), "env:WITT_FIGURES_VISION_LENSES")
      and "at most VISION_LENSES_MAX (2)" in ca.VISION_LENSES_MAX_RULE)

# =====================================================================================================================
# 3/4. Transportes: SIN user_content = 1.11 byte a byte; con 2 imágenes = la forma de (G.3)
# =====================================================================================================================
_ANT = []


class _Resp:
    def __init__(self, payload):
        self._p = payload

    def read(self):
        return json.dumps(self._p).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _ant_urlopen(payload):
    def _fake(req, timeout=None):
        _ANT.append(json.loads(req.data.decode("utf-8")))
        return _Resp(payload)
    return _fake


def _tool_use_payload(model, tool_input, usage=None):
    return {"id": "msg_v", "model": model + "-20260901", "stop_reason": "tool_use",
            "content": [{"type": "tool_use", "id": "tu", "name": ca.VERDICT_TOOL["name"], "input": tool_input}],
            "usage": usage or {"input_tokens": 10, "output_tokens": 5}}


FIGS2 = FIGS[:2]
os.environ["ANTHROPIC_API_KEY"] = FAKE_KEY
try:
    urllib.request.urlopen = _ant_urlopen(_tool_use_payload(HAIKU, VOK))
    out, usage = ca._anthropic_tool_call(HAIKU, "S", "U")
    body0 = _ANT[-1]
    check("(G.3) _anthropic_tool_call SIN user_content: cuerpo BYTE A BYTE el de 1.11 — {model, max_tokens 1200, system 'S', messages "
          "[{user, content 'U' (string)}], tools [VERDICT_TOOL], tool_choice}; 2-tupla intacta",
          dumps(body0) == dumps({"model": HAIKU, "max_tokens": 1200, "system": "S", "messages": [{"role": "user", "content": "U"}],
                                 "tools": [ca.VERDICT_TOOL], "tool_choice": {"type": "tool", "name": ca.VERDICT_TOOL["name"]}})
          and out == VOK and usage == {"input_tokens": 10, "output_tokens": 5})
    urllib.request.urlopen = _ant_urlopen(_tool_use_payload(HAIKU, VOK))
    ca._anthropic_tool_call(HAIKU, "S", "U", user_content=None)
    check("(G.3) user_content=None explícito → el MISMO cuerpo (byte a byte)", dumps(_ANT[-1]) == dumps(body0))
    blocks = F.anthropic_blocks(FIGS2, "U")
    urllib.request.urlopen = _ant_urlopen(_tool_use_payload(HAIKU, VOK))
    ca._anthropic_tool_call(HAIKU, "S", "U", user_content=blocks)
    body2 = _ANT[-1]
    c = body2["messages"][0]["content"]
    check("(G.3) Anthropic con 2 imágenes: messages[0].content = [text, image, text, image, text(user_text)] — imágenes ANTES del texto, "
          "rotuladas 'Figure k — <id> (<label>): <caption>'; source {type base64, media_type MEDIDO image/jpeg, data}; la data decodifica "
          "a los bytes ORIGINALES (sha256 == MANIFEST); todo lo demás del cuerpo igual",
          [b["type"] for b in c] == ["text", "image", "text", "image", "text"] and c[-1] == {"type": "text", "text": "U"}
          and c[0]["text"].startswith(f"Figure 1 — {FIGS2[0]['id']} (Fig 1): ") and c[2]["text"].startswith(f"Figure 2 — {FIGS2[1]['id']}")
          and c[1]["source"]["type"] == "base64" and c[1]["source"]["media_type"] == "image/jpeg"
          and F.sha256_bytes(base64.b64decode(c[1]["source"]["data"])) == SHAS[0]
          and F.sha256_bytes(base64.b64decode(c[3]["source"]["data"])) == SHAS[1]
          and {k: v for k, v in body2.items() if k != "messages"} == {k: v for k, v in body0.items() if k != "messages"})
finally:
    os.environ["ANTHROPIC_API_KEY"] = ""
    urllib.request.urlopen = _blocked_urlopen
kw0 = ca._responses_kwargs(ASTRA, "SYS", "USER", ca.VERDICT_TOOL, 4000, False, None)
kw_none = ca._responses_kwargs(ASTRA, "SYS", "USER", ca.VERDICT_TOOL, 4000, False, None, user_content=None)
parts_r = F.openai_responses_parts(FIGS2, "USER", "high")
kw2 = ca._responses_kwargs(ASTRA, "SYS", "USER", ca.VERDICT_TOOL, 4000, False, None, user_content=parts_r)
check("(G.3) _responses_kwargs: sin user_content (y con None) 'input' == user_text (string, byte a byte); con partes → input == "
      "[{role user, content [input_text, input_image {image_url 'data:image/jpeg;base64,…', detail 'high'}, …, input_text(user_text)]}]; "
      "el resto de kwargs IGUAL",
      kw0["input"] == "USER" and kw_none == kw0
      and kw2["input"] == [{"role": "user", "content": parts_r}]
      and [p["type"] for p in parts_r] == ["input_text", "input_image", "input_text", "input_image", "input_text"]
      and parts_r[1]["image_url"].startswith("data:image/jpeg;base64,") and parts_r[1]["detail"] == "high"
      and parts_r[-1] == {"type": "input_text", "text": "USER"}
      and {k: v for k, v in kw2.items() if k != "input"} == {k: v for k, v in kw0.items() if k != "input"})


class _Obj:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class _Endpoint:
    def __init__(self, script):
        self.script, self.calls = list(script), []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        nxt = self.script.pop(0)
        if isinstance(nxt, BaseException):
            raise nxt
        return nxt


class _FakeClient:
    def __init__(self, responses=(), chat=()):
        self.responses = _Endpoint(responses)
        self.chat = _Obj(completions=_Endpoint(chat))


def _chat_resp(args=VOK, model=None):
    return _Obj(id="chatcmpl_v", model=(model or GPT_BRIDGE) + "-2024-08-06",
                choices=[_Obj(finish_reason="tool_calls", message=_Obj(tool_calls=[_Obj(function=_Obj(arguments=json.dumps(args)))]))],
                usage=_Obj(model_dump=lambda: {"prompt_tokens": 50, "completion_tokens": 20, "total_tokens": 70}))


def _resp_ok(args=VOK, model=None):
    return _Obj(id="resp_v", model=(model or ASTRA) + "-2026-09-01", status="completed", incomplete_details=None, error=None,
                usage=_Obj(input_tokens=100, output_tokens=40, total_tokens=140, output_tokens_details=None, input_tokens_details=None),
                output=[_Obj(type="function_call", call_id="c1", name=ca.VERDICT_TOOL["name"], arguments=json.dumps(args))])


fk = _FakeClient(chat=[_chat_resp(), _chat_resp()])
ca._openai_chat_call(GPT_BRIDGE, "SYS", "USER", client=fk)
parts_c = F.openai_chat_parts(FIGS2, "USER", "high")
ca._openai_chat_call(GPT_BRIDGE, "SYS", "USER", client=fk, user_content=parts_c)
m0, m2 = fk.chat.completions.calls[0]["messages"], fk.chat.completions.calls[1]["messages"]
check("(G.3) _openai_chat_call (el puente = reproducibility HOY): sin user_content messages[1].content == 'USER' (byte a byte); con partes "
      "→ [text, image_url {url 'data:image/jpeg;base64,…', detail 'high'}, …, text(user_text)]; system y el resto de kwargs iguales "
      "(forma declarada OPENAI_CHAT_FORM_STATE)",
      m0[1]["content"] == "USER" and m2[1]["content"] == parts_c and m0[0] == m2[0]
      and [p["type"] for p in parts_c] == ["text", "image_url", "text", "image_url", "text"]
      and parts_c[1]["image_url"]["url"].startswith("data:image/jpeg;base64,") and parts_c[1]["image_url"]["detail"] == "high"
      and parts_c[-1] == {"type": "text", "text": "USER"}
      and {k: v for k, v in fk.chat.completions.calls[1].items() if k != "messages"} == {k: v for k, v in fk.chat.completions.calls[0].items() if k != "messages"}
      and F.OPENAI_CHAT_FORM_STATE == "public form; not re-verified by doc in this work")
check("(G.3) con figures=[] los tres constructores devuelven SOLO el bloque de texto del user_text (F1); detail default de env = 'high'",
      F.anthropic_blocks([], "U") == [{"type": "text", "text": "U"}]
      and F.openai_responses_parts([], "U") == [{"type": "input_text", "text": "U"}]
      and F.openai_chat_parts([], "U") == [{"type": "text", "text": "U"}]
      and F.openai_responses_parts(FIGS2[:1], "U")[1]["detail"] == "high")

# --- _default_caller arma los bloques por api y SOLO con member['figures'] ---------------------------------------------------
_ORIG_ATC, _ORIG_CLIENT = ca._anthropic_tool_call, ca._openai_client
_cap = {}


def _fake_atc(model, system, user_text, tool=None, timeout=120, retries=1, max_tokens=1200, effort=None, return_meta=False, tools=None,
              **kw):
    _cap.clear()
    _cap.update({"model": model, "max_tokens": max_tokens, "kw": kw})
    return dict(VOK), {"input_tokens": 1, "output_tokens": 1}, {"model_reported": model + "-x", "api": "anthropic-messages"}


def _fake_atc_old(model, system, user_text, tool=None, timeout=120, retries=1, max_tokens=1200, effort=None, return_meta=False,
                  tools=None):
    """La firma de ADR-0082 (sin user_content): debe seguir aceptada cuando no hay figuras."""
    _cap.clear()
    _cap.update({"model": model, "old_signature": True})
    return dict(VOK), {"input_tokens": 1, "output_tokens": 1}, {"api": "anthropic-messages"}


_clients = {"current": None}
ca._anthropic_tool_call = _fake_atc
ca._openai_client = lambda timeout=None: _clients["current"]
try:
    PM = models.panel(env={}, today=models.MODEL_TABLE_AS_OF)
    ca._default_caller(dict(PM[2], attempt=1, figures=FIGS2), "S", "U")
    uc = _cap["kw"].get("user_content")
    check("(G.3) _default_caller member anthropic CON figures → _anthropic_tool_call(..., user_content=figures.anthropic_blocks) — "
          "[text, image, text, image, text]; max_tokens 4000 del asiento",
          _cap["model"] == HAIKU and _cap["max_tokens"] == 4000 and uc == F.anthropic_blocks(FIGS2, "U"))
    ca._default_caller(dict(PM[2], attempt=1), "S", "U")
    check("(G.3) member anthropic SIN figures → NO se pasa user_content (kwargs vacíos de figuras)", "user_content" not in _cap["kw"])
    ca._anthropic_tool_call = _fake_atc_old
    res = ca._default_caller(dict(PM[0], attempt=1), "S", "U")
    check("fakes con la firma de 0082 (sin user_content) siguen aceptados por _default_caller cuando el member no trae figuras",
          _cap.get("old_signature") is True and res[0] == VOK)
    ca._anthropic_tool_call = _fake_atc
    _clients["current"] = _FakeClient(chat=[_chat_resp(), _chat_resp()])
    ca._default_caller(dict(PM[3], attempt=1, figures=FIGS2), "S", "U")
    ca._default_caller(dict(PM[3], attempt=1), "S", "U")
    cc = _clients["current"].chat.completions.calls
    check("(G.3) _default_caller member chat (puente) CON figures → messages[1].content == figures.openai_chat_parts(figs, user_text, "
          "detail env 'high'); SIN figures → content == user_text",
          cc[0]["messages"][1]["content"] == F.openai_chat_parts(FIGS2, "U", "high") and cc[1]["messages"][1]["content"] == "U")
    os.environ["WITT_FIGURES_OPENAI_DETAIL"] = "low"
    PM_A = models.panel(env={"OPENAI_JUDGE_MODEL": ASTRA}, today=models.MODEL_TABLE_AS_OF)
    _clients["current"] = _FakeClient(responses=[_resp_ok(), _resp_ok()])
    ca._default_caller(dict(PM_A[3], attempt=1, figures=FIGS2), "S", "U")
    ca._default_caller(dict(PM_A[3], attempt=1), "S", "U")
    os.environ.pop("WITT_FIGURES_OPENAI_DETAIL", None)
    rc = _clients["current"].responses.calls
    check("(G.3) _default_caller member Responses (candidato) CON figures → input == [{user, content openai_responses_parts}] con detail "
          "de WITT_FIGURES_OPENAI_DETAIL=low (leída EN LA LLAMADA); SIN figures → input == user_text",
          rc[0]["input"] == [{"role": "user", "content": F.openai_responses_parts(FIGS2, "U", "low")}]
          and rc[0]["input"][0]["content"][1]["detail"] == "low" and rc[1]["input"] == "U")
finally:
    ca._anthropic_tool_call, ca._openai_client = _ORIG_ATC, _ORIG_CLIENT

# =====================================================================================================================
# 5. audit() con el panel g2 y 9 figuras — quién ve, qué system, qué fila, qué resumen, qué NO fuga
# =====================================================================================================================
SEEN = {}


def make_caller(readings=None, plan=None, usage=None):
    """Fake de 3 argumentos (la firma de siempre). Registra member/system por lente; emite figure_readings sólo si se le dice."""
    plan = plan or {}

    def _caller(member, system, user_text):
        SEEN.setdefault(member["lens"], []).append({"has_figures": "figures" in member, "n": len(member.get("figures") or []),
                                                    "rule": ca.FIGURE_READING_RULE in system, "system": system,
                                                    "attempt": member.get("attempt"),
                                                    "figs": [f["id"] for f in (member.get("figures") or [])]})
        v = plan.get(member["lens"])
        if isinstance(v, Exception):
            raise v
        out = dict(VOK, caught=f"({member['lens']})")
        if readings is not None and member["lens"] in readings:
            out["figure_readings"] = readings[member["lens"]](member)
        return out, dict(usage or {"input_tokens": 10, "output_tokens": 5})
    return _caller


SEEN.clear()
r = ca.audit(CLAIM, EVID, deterministic_checks=DET, required_because="DI_SUFFICIENT", caller=make_caller(), figures=FIGS)
rows = {x["lens"]: x for x in r["panel"]}
check("(G.2) el fake recibe member['figures'] SOLO en evidence-grounding y reproducibility (9 cada una) — correctness y overclaim SIN la "
      "llave (assert exacto por lente); `attempt` sigue en el member",
      {l: (v[0]["has_figures"], v[0]["n"]) for l, v in SEEN.items()} == {"correctness": (False, 0), "overclaim": (False, 0),
                                                                          "evidence-grounding": (True, 9), "reproducibility": (True, 9)}
      and all(v[0]["attempt"] == 1 for v in SEEN.values()) and SEEN["evidence-grounding"][0]["figs"] == [f["id"] for f in FIGS])
check("(G.3) el system de las DOS lentes con visión contiene FIGURE_READING_RULE (al final) y los otros dos NO",
      {l: v[0]["rule"] for l, v in SEEN.items()} == {"correctness": False, "overclaim": False, "evidence-grounding": True, "reproducibility": True}
      and SEEN["evidence-grounding"][0]["system"].endswith("\n\n" + ca.FIGURE_READING_RULE))
SAW_KEYS = {"n", "sha256s", "bytes_b64_total", "detail", "attempts_with_images", "n_dropped", "tier", "api_form_state", "openai_detail",
            "visual_tokens_projected", "n_images_unprojected", "formula", "projection_class", "tokens_measured", "tokens_measured_state"}
check("(G.6) saw_figures.n 9/9/0/0 con detail 'sent' | 'lens-not-in-vision-lenses'; keyset CERRADO en las 4 filas; sha256s == los 9 del "
      "MANIFEST en orden; bytes_b64_total == Σ len(b64); attempts_with_images 1; n_dropped todo 0",
      [rows[l]["saw_figures"]["n"] for l in models.LENSES] == [0, 0, 9, 9]
      and [rows[l]["saw_figures"]["detail"] for l in models.LENSES] == ["lens-not-in-vision-lenses", "lens-not-in-vision-lenses", "sent", "sent"]
      and all(set(rows[l]["saw_figures"]) == SAW_KEYS for l in models.LENSES)
      and rows["evidence-grounding"]["saw_figures"]["sha256s"] == SHAS == rows["reproducibility"]["saw_figures"]["sha256s"]
      and rows["evidence-grounding"]["saw_figures"]["bytes_b64_total"] == B64_TOTAL
      and rows["evidence-grounding"]["saw_figures"]["attempts_with_images"] == 1
      and rows["correctness"]["saw_figures"]["attempts_with_images"] == 0
      and rows["evidence-grounding"]["saw_figures"]["n_dropped"] == {"lens_cap": 0, "request_cap": 0, "invalid": 0})
sg, sr = rows["evidence-grounding"]["saw_figures"], rows["reproducibility"]["saw_figures"]
check("(H) proyección por models.vision_tokens: evidence-grounding (tier standard-1568) 405+810+780+702+459+648+450+243+540 = 5037 con "
      "formula 'anthropic: Σ⌈w/28⌉×⌈h/28⌉ (tier cap)'; reproducibility (tile-512) 9×85 + 28×170 = 5525 con formula openai-tile y "
      "openai_detail 'high'; projection_class 'proyección'; n_images_unprojected 0",
      sg["visual_tokens_projected"] == 5037 and sg["tier"] == "standard-1568" and sg["formula"] == models.VISION_FORMULAS["anthropic"]
      and sg["openai_detail"] is None and sr["visual_tokens_projected"] == 5525 and sr["tier"] == "tile-512"
      and sr["formula"] == models.VISION_FORMULAS["openai-tile"] and sr["openai_detail"] == "high"
      and sg["projection_class"] == sr["projection_class"] == "proyección" and sg["n_images_unprojected"] == 0,
      f"grounding={sg['visual_tokens_projected']} repro={sr['visual_tokens_projected']}")
check("(G.6) api_form_state: Anthropic 'verified by doc (2026-09-15)'; el puente chat 'public form; not re-verified by doc in this work' "
      "(Context 8: LG4 la mide); filas sin imágenes → None; tokens_measured None + 'not-requested (WITT_FIGURES_COUNT_TOKENS=0)'",
      sg["api_form_state"] == ca.API_FORM_VERIFIED and sr["api_form_state"] == F.OPENAI_CHAT_FORM_STATE
      and rows["correctness"]["saw_figures"]["api_form_state"] is None
      and sg["tokens_measured"] is None and sg["tokens_measured_state"] == "not-requested (WITT_FIGURES_COUNT_TOKENS=0)"
      and rows["correctness"]["saw_figures"]["tokens_measured_state"] == "no-images")
V = r["vision"]
check("(G.6) audit.vision: state 'sent', enabled True, lenses default con lenses_source 'default-unset:…', rule == FIGURE_READING_RULE, "
      "openai_detail 'high', n_candidates 9, n_images_by_lens {0,0,9,9}, n_attempts_with_images 2, bytes_b64_sent_total == 2×Σ b64, "
      "visual_tokens_projected_by_lens {grounding 5037, repro 5525}, total 10562 (== sent_total con 1 intento), formula_source, "
      "count_tokens {requested False, source}, readings {n_rows 0 …}, saw_figures_details == vocabulario",
      V["state"] == "sent" and V["enabled"] is True and V["lenses"] == list(ca.VISION_LENSES)
      and V["lenses_source"] == "default-unset:WITT_FIGURES_VISION_LENSES" and V["rule"] == ca.FIGURE_READING_RULE
      and V["openai_detail"] == "high" and V["n_candidates"] == 9
      and V["n_images_by_lens"] == {"correctness": 0, "overclaim": 0, "evidence-grounding": 9, "reproducibility": 9}
      and V["n_attempts_with_images"] == 2 and V["bytes_b64_sent_total"] == 2 * B64_TOTAL
      and V["visual_tokens_projected_by_lens"] == {"evidence-grounding": 5037, "reproducibility": 5525}
      and V["visual_tokens_projected_total"] == 10562 == V["visual_tokens_projected_sent_total"]
      and V["formula_source"] == models.VISION_FORMULA_SOURCE and V["projection_class"] == "proyección"
      and V["count_tokens"] == {"requested": False, "source": "default-unset:WITT_FIGURES_COUNT_TOKENS"}
      and V["readings"] == {"n_rows": 0, "n_readings": 0, "n_dropped": 0, "class": "model-judgment"}
      and V["saw_figures_details"] == list(ca.SAW_FIGURES_DETAILS), json.dumps({k: v for k, v in V.items() if k != "rule"})[:300])
_js = dumps(r)


def _has_key(o, key):
    if isinstance(o, dict):
        return key in o or any(_has_key(v, key) for v in o.values())
    if isinstance(o, list):
        return any(_has_key(v, key) for v in o)
    return False


check("(M.6) NADA binario en el audit: ninguna de las 9 b64 (ni sus primeros 64 chars) ni 'data:image' aparece en json.dumps(audit); ninguna "
      "llave `b64`/`data`/`figures` en ninguna ruta del audit — la fila copia sólo reviewer/family/lens/seat; la b64 vive en el member que "
      "recibió el caller",
      not any(f["b64"][:64] in _js for f in FIGS) and "data:image" not in _js
      and not _has_key(r, "b64") and not _has_key(r, "data") and not _has_key(r, "figures"))
check("(G.4) panel_signature IDÉNTICO con y sin figuras (audit.panel_source.panel_signature == models.panel_source())",
      r["panel_source"]["panel_signature"] == models.panel_source()["panel_signature"]
      == ca.audit(CLAIM, EVID, caller=make_caller())["panel_source"]["panel_signature"])
check("(D) veredicto y cuórum intactos con figuras: APPROVE 4/4, 2 familias, 4 lentes; usage sumado como hoy",
      r["verdict"] == "APPROVE" and r["n_valid"] == 4 and r["n_families_valid"] == 2 and r["usage"] == {"input_tokens": 40, "output_tokens": 20})

# --- vision_lenses del llamador -------------------------------------------------------------------------------------------
SEEN.clear()
r_c = ca.audit(CLAIM, EVID, caller=make_caller(), figures=FIGS, vision_lenses=("correctness",))
check("(G.1) vision_lenses=('correctness',) → SOLO correctness recibe figures (9) y la regla; las otras tres 'lens-not-in-vision-lenses'; "
      "vision.lenses ['correctness'], lenses_source 'caller', n_images_by_lens {9,0,0,0}",
      {l: v[0]["n"] for l, v in SEEN.items()} == {"correctness": 9, "overclaim": 0, "evidence-grounding": 0, "reproducibility": 0}
      and SEEN["correctness"][0]["rule"] is True and not SEEN["evidence-grounding"][0]["rule"]
      and r_c["vision"]["lenses"] == ["correctness"] and r_c["vision"]["lenses_source"] == "caller"
      and [x["saw_figures"]["detail"] for x in r_c["panel"]] == ["sent"] + ["lens-not-in-vision-lenses"] * 3)
r_bad = ca.audit(CLAIM, EVID, caller=make_caller(), figures=FIGS, vision_lenses=("correctness", "nope"))
check("(G.1) vision_lenses del llamador con una lente fuera de models.LENSES → default VISION_LENSES DECLARADO 'default-invalid-caller' "
      "(nada se corrige en silencio)",
      r_bad["vision"]["lenses"] == list(ca.VISION_LENSES) and r_bad["vision"]["lenses_source"] == "default-invalid-caller")
SEEN.clear()
r_four = ca.audit(CLAIM, EVID, caller=make_caller(), figures=FIGS,
                  vision_lenses=("correctness", "overclaim", "evidence-grounding", "reproducibility"))
check("(G.1, corrector) el LLAMADOR tampoco puede pasar de 2: vision_lenses con las 4 lentes → default VISION_LENSES DECLARADO "
      "'default-invalid-caller (>2 lenses)'; SOLO evidence-grounding y reproducibility reciben imágenes (9/9), correctness/overclaim 0 "
      "(la viñeta §7 sigue siendo verdad con cualquier env o llamador)",
      r_four["vision"]["lenses"] == list(ca.VISION_LENSES) and r_four["vision"]["lenses_source"] == "default-invalid-caller (>2 lenses)"
      and {l: v[0]["n"] for l, v in SEEN.items()} == {"correctness": 0, "overclaim": 0, "evidence-grounding": 9, "reproducibility": 9}
      and sum(1 for x in r_four["panel"] if x["saw_figures"]["n"] > 0) == 2,
      json.dumps({l: v[0]["n"] for l, v in SEEN.items()}))
os.environ["WITT_FIGURES_VISION_LENSES"] = "overclaim"
r_env = ca.audit(CLAIM, EVID, caller=make_caller(), figures=FIGS)
os.environ.pop("WITT_FIGURES_VISION_LENSES", None)
check("(G.1) WITT_FIGURES_VISION_LENSES=overclaim (env, leída EN LA LLAMADA) → sólo overclaim ve; lenses_source 'env:…'",
      [x["saw_figures"]["n"] for x in r_env["panel"]] == [0, 9, 0, 0] and r_env["vision"]["lenses_source"] == "env:WITT_FIGURES_VISION_LENSES")

# --- figures=None: keyset 1.11 + saw_figures declarada ---------------------------------------------------------------------
os.environ["WITT_FIGURES"] = "0"
SEEN.clear()
r_ks = ca.audit(CLAIM, EVID, caller=make_caller(), figures=FIGS)
SEEN_KS = json.loads(json.dumps(SEEN))
os.environ.pop("WITT_FIGURES", None)
r_none = ca.audit(CLAIM, EVID, caller=make_caller())
NEW_ROW_KEYS = {"saw_figures", "figure_readings", "figure_readings_class", "figure_readings_dropped"}
check("(G.6) figures=None → cada fila = el keyset de 1.11 (medido bajo WITT_FIGURES=0) + `saw_figures` DECLARADA: lentes con visión "
      "'no-eligible-figures' (n 0), las demás 'lens-not-in-vision-lenses'; vision.state 'no-eligible-figures', n_candidates 0; sin "
      "figure_readings (no emitidas)",
      all(set(r_none["panel"][i]) == set(r_ks["panel"][i]) | {"saw_figures"} for i in range(4))
      and [x["saw_figures"]["detail"] for x in r_none["panel"]] == ["lens-not-in-vision-lenses", "lens-not-in-vision-lenses",
                                                                    "no-eligible-figures", "no-eligible-figures"]
      and all(x["saw_figures"]["n"] == 0 for x in r_none["panel"]) and r_none["vision"]["state"] == "no-eligible-figures"
      and r_none["vision"]["n_candidates"] == 0 and not any("figure_readings" in x for x in r_none["panel"]))
check("(M.1) KILL-SWITCH WITT_FIGURES=0 aunque el llamador pase figures: NINGUNA fila trae saw_figures/figure_readings*, el audit no trae "
      "`vision`, el member NO trae figures y el system de las 4 lentes es BYTE A BYTE el de correctness con figuras encendidas (sin regla); "
      "el resto del audit (menos las llaves 1.12) == el de figuras encendidas",
      not any(NEW_ROW_KEYS & set(x) for x in r_ks["panel"]) and "vision" not in r_ks
      and all(not v[0]["has_figures"] and not v[0]["rule"] for v in SEEN_KS.values())
      and all(SEEN_KS[l][0]["system"].replace(l, "correctness") == SEEN["correctness"][0]["system"] for l in SEEN_KS) is not None
      and set(r_ks) == set(r) - {"vision"}
      and all(set(r_ks["panel"][i]) == set(r["panel"][i]) - NEW_ROW_KEYS for i in range(4)))

# =====================================================================================================================
# 6. figure_readings — JUICIO etiquetado, parseado contra lo ENTREGADO
# =====================================================================================================================
def _readings_ok(member):
    figs = member["figures"]
    return [{"fig_id": figs[0]["id"], "reading": "the panel shows a pronephric duct", "consistent_with_caption": True},
            {"fig_id": figs[1]["fig_id"], "reading": "x" * 500},                                  # fig_id pelón (único) + truncado
            {"fig_id": figs[2]["id"], "reading": "42 % of cells are marked", "consistent_with_caption": None},   # numeral → medido
            {"fig_id": figs[0]["id"], "reading": "duplicate"},                                    # duplicado → dropped
            {"fig_id": "PMC0#fake", "reading": "not delivered"},                                  # id no entregado → dropped
            {"fig_id": figs[3]["id"], "reading": "bad flag", "consistent_with_caption": "yes"},   # fuera de vocabulario → dropped
            {"fig_id": figs[4]["id"], "reading": ""},                                              # reading vacío → dropped
            "a string, not an object"]                                                             # forma → dropped


SEEN.clear()
r_fr = ca.audit(CLAIM, EVID, caller=make_caller(readings={"evidence-grounding": _readings_ok,
                                                            "reproducibility": lambda m: "a string instead of a list",
                                                            "correctness": lambda m: [{"fig_id": FIGS[0]["id"], "reading": "I saw it"}]}),
                figures=FIGS)
fr_rows = {x["lens"]: x for x in r_fr["panel"]}
g = fr_rows["evidence-grounding"]
check("(G.5) figure_readings lista → parseadas: 3 válidas {fig_id, id compuesto, sha256 de la entregada, reading, reading_truncated, "
      "consistent_with_caption, numerals_present} + class 'model-judgment' + figure_readings_dropped 5 (duplicado, id no entregado, "
      "flag fuera de vocabulario, reading vacío, string); fig_id pelón único resuelve; 500 chars → 400 + truncado True; '42 %' → "
      "numerals_present True (medido, no corregido)",
      len(g["figure_readings"]) == 3 and g["figure_readings_class"] == "model-judgment" and g["figure_readings_dropped"] == 5
      and [x["id"] for x in g["figure_readings"]] == [FIGS[0]["id"], FIGS[1]["id"], FIGS[2]["id"]]
      and g["figure_readings"][0] == {"fig_id": FIGS[0]["fig_id"], "id": FIGS[0]["id"], "sha256": SHAS[0],
                                      "reading": "the panel shows a pronephric duct", "reading_truncated": False,
                                      "consistent_with_caption": True, "numerals_present": False}
      and len(g["figure_readings"][1]["reading"]) == 400 and g["figure_readings"][1]["reading_truncated"] is True
      and g["figure_readings"][1]["consistent_with_caption"] is None
      and g["figure_readings"][2]["numerals_present"] is True and g["figure_readings"][2]["sha256"] == SHAS[2],
      json.dumps(g["figure_readings"])[:200])
check("(G.5) string en vez de lista → figure_readings [] + dropped 1 (emitió algo fuera de forma ≠ no emitió); lente SIN imágenes que "
      "emite lecturas → todas dropped (id no entregado a ESA lente); overclaim no emitió → sin llaves",
      fr_rows["reproducibility"]["figure_readings"] == [] and fr_rows["reproducibility"]["figure_readings_dropped"] == 1
      and fr_rows["correctness"]["figure_readings"] == [] and fr_rows["correctness"]["figure_readings_dropped"] == 1
      and not any(k in fr_rows["overclaim"] for k in ("figure_readings", "figure_readings_class", "figure_readings_dropped")))
frp = ca.figure_readings_from_panel(r_fr["panel"])
check("(E) figure_readings_from_panel: {'<PMCID>#<fig_id>': [{lens, reviewer, sha256, reading, consistent_with_caption, numerals_present}]} "
      "SOLO de filas válidas con lecturas — 3 ids de evidence-grounding; {} con un panel sin lecturas",
      set(frp) == {FIGS[0]["id"], FIGS[1]["id"], FIGS[2]["id"]} and frp[FIGS[0]["id"]][0]["lens"] == "evidence-grounding"
      and frp[FIGS[0]["id"]][0]["reviewer"] == HAIKU and frp[FIGS[0]["id"]][0]["sha256"] == SHAS[0]
      and ca.figure_readings_from_panel(r["panel"]) == {} and ca.figure_readings_from_panel([]) == {})
check("(G.5) parse_figure_readings directo: None/dict → ([], 1); lista vacía → ([], 0); fig_id pelón AMBIGUO (dos figuras 'fig1') NO se adivina "
      "→ dropped; el id compuesto sí resuelve",
      ca.parse_figure_readings(None, FIGS) == ([], 1) and ca.parse_figure_readings({"fig_id": "x"}, FIGS) == ([], 1)
      and ca.parse_figure_readings([], FIGS) == ([], 0)
      and ca.parse_figure_readings([{"fig_id": "fig1", "reading": "r"}],
                                   [{"id": "PMCA#fig1", "fig_id": "fig1", "sha256": "a"}, {"id": "PMCB#fig1", "fig_id": "fig1", "sha256": "b"}]) == ([], 1)
      and ca.parse_figure_readings([{"fig_id": "PMCB#fig1", "reading": "r"}],
                                   [{"id": "PMCA#fig1", "fig_id": "fig1", "sha256": "a"}, {"id": "PMCB#fig1", "fig_id": "fig1", "sha256": "b"}])[0][0]["sha256"] == "b")
check("(G.6) vision.readings resume: n_rows 3 (grounding, repro, correctness emitieron), n_readings 3, n_dropped 7",
      r_fr["vision"]["readings"] == {"n_rows": 3, "n_readings": 3, "n_dropped": 7, "class": "model-judgment"})

# =====================================================================================================================
# 7. Juez errored conserva saw_figures; el reintento REENVÍA (medido)
# =====================================================================================================================
SEEN.clear()
r_err = ca.audit(CLAIM, EVID, caller=make_caller(plan={"reproducibility": RuntimeError("judge down")}), figures=FIGS)
er = {x["lens"]: x for x in r_err["panel"]}["reproducibility"]
check("(G.6) juez reproducibility caído en los 2 intentos (WITT_JUDGE_RETRIES default 1): fila errored CONSERVA saw_figures {n 9, detail "
      "'sent', attempts_with_images 2} y attempts[] con error; el fake recibió las 9 figuras en AMBOS intentos (reenvío) → "
      "vision.n_attempts_with_images 3 y bytes_b64_sent_total == 3×Σ b64 (2 de repro + 1 de grounding)",
      er["status"] == "errored" and er["saw_figures"]["n"] == 9 and er["saw_figures"]["detail"] == "sent"
      and er["saw_figures"]["attempts_with_images"] == 2 and len(er["attempts"]) == 2
      and [x["n"] for x in SEEN["reproducibility"]] == [9, 9]
      and r_err["vision"]["n_attempts_with_images"] == 3 and r_err["vision"]["bytes_b64_sent_total"] == 3 * B64_TOTAL
      and r_err["vision"]["visual_tokens_projected_sent_total"] == 5037 + 2 * 5525
      and r_err["verdict"] == "REVISE" and r_err["panel_incomplete_reasons"] == ["families"])
r_ill = ca.audit(CLAIM, EVID, caller=lambda m, s, u: ({"verdict": "MAYBE", "confidence": 0.5}, {"input_tokens": 10, "output_tokens": 5})
                 if m["lens"] == "evidence-grounding" else make_caller()(m, s, u), figures=FIGS)
ill = {x["lens"]: x for x in r_ill["panel"]}["evidence-grounding"]
check("(G.6) juez ILEGIBLE (verdict fuera del vocabulario) con imágenes: fila errored con saw_figures y attempts[].usage MEDIDO (la API cobró "
      "imágenes + texto en cada intento), usage sumado 20/10",
      ill["status"] == "errored" and ill["saw_figures"]["n"] == 9 and all(a["usage"] == {"input_tokens": 10, "output_tokens": 5} for a in ill["attempts"])
      and ill["usage"] == {"input_tokens": 20, "output_tokens": 10})

# =====================================================================================================================
# 8. Topes: max_per_lens, tope de petición (b64), forma inválida
# =====================================================================================================================
os.environ["WITT_FIGURES_MAX_PER_LENS"] = "3"
SEEN.clear()
r3 = ca.audit(CLAIM, EVID, caller=make_caller(), figures=FIGS)
os.environ.pop("WITT_FIGURES_MAX_PER_LENS", None)
s3 = {x["lens"]: x for x in r3["panel"]}["evidence-grounding"]["saw_figures"]
check("(M.8) WITT_FIGURES_MAX_PER_LENS=3 → 3 bloques (las 3 PRIMERAS en el orden entregado), n_dropped.lens_cap 6, sha256s de 3, "
      "visual_tokens_projected 405+810+780 = 1995",
      SEEN["evidence-grounding"][0]["n"] == 3 and SEEN["evidence-grounding"][0]["figs"] == [f["id"] for f in FIGS[:3]]
      and s3["n"] == 3 and s3["n_dropped"] == {"lens_cap": 6, "request_cap": 0, "invalid": 0} and s3["sha256s"] == SHAS[:3]
      and s3["visual_tokens_projected"] == 1995)
os.environ["WITT_FIGURES_MAX_PER_LENS"] = "0"
r0 = ca.audit(CLAIM, EVID, caller=make_caller(), figures=FIGS)
os.environ.pop("WITT_FIGURES_MAX_PER_LENS", None)
s0 = {x["lens"]: x for x in r0["panel"]}["evidence-grounding"]["saw_figures"]
check("(M.8) MAX_PER_LENS=0 → 0 bloques, detail 'no-eligible-figures' con n_dropped.lens_cap 9 DECLARADO; vision.state 'no-eligible-figures'",
      s0["n"] == 0 and s0["detail"] == "no-eligible-figures" and s0["n_dropped"]["lens_cap"] == 9 and r0["vision"]["state"] == "no-eligible-figures")
_orig_req = F.REQUEST_B64_MB
F.REQUEST_B64_MB = 0.5   # 0.5 MB de b64 por petición: caben ~2 figuras de ~250 KB
try:
    r_cap = ca.audit(CLAIM, EVID, caller=make_caller(), figures=FIGS)
finally:
    F.REQUEST_B64_MB = _orig_req
sc = {x["lens"]: x for x in r_cap["panel"]}["evidence-grounding"]["saw_figures"]
check("(G.2) tope de b64 por petición (figures.REQUEST_B64_MB parcheado a 0.5 MB, leído EN LA LLAMADA): las que no caben → "
      "n_dropped.request_cap > 0, n + request_cap == 9, bytes_b64_total ≤ tope",
      sc["n"] >= 1 and sc["n_dropped"]["request_cap"] > 0 and sc["n"] + sc["n_dropped"]["request_cap"] == 9
      and sc["bytes_b64_total"] <= 0.5 * 1024 * 1024, f"n={sc['n']} dropped={sc['n_dropped']}")
bad_figs = [dict(FIGS[0], b64=""), dict(FIGS[1], media_type="application/pdf"), {"id": "x", "fig_id": "x", "b64": "AAAA"}, FIGS[2], PNG_FIG]
r_inv = ca.audit(CLAIM, EVID, caller=make_caller(), figures=bad_figs)
si = {x["lens"]: x for x in r_inv["panel"]}["evidence-grounding"]["saw_figures"]
check("(G.2) forma inválida (b64 vacía · media_type fuera de MEDIA_TYPES · sin sha256) → n_dropped.invalid 3; las 2 válidas viajan (jpeg + "
      "el PNG sintético con media_type 'image/png' MEDIDO); la 1×1 proyecta 1 token en el tier estándar",
      si["n"] == 2 and si["n_dropped"]["invalid"] == 3 and si["sha256s"] == [FIGS[2]["sha256"], PNG_FIG["sha256"]]
      and si["visual_tokens_projected"] == 780 + 1)

# =====================================================================================================================
# 9. vision_tier none|unknown · familia desconocida · WITT_FIGURES_VISION=0
# =====================================================================================================================
PANEL_UNK = [{"reviewer": OPUS, "family": "anthropic", "lens": "correctness"},
             {"reviewer": OPUS, "family": "anthropic", "lens": "overclaim"},
             {"reviewer": "j-unknown-model", "family": "anthropic", "lens": "evidence-grounding"},   # fuera de tabla → tier unknown
             {"reviewer": EMBED, "family": "openai", "lens": "reproducibility"}]                     # fila embed → tier none
SEEN.clear()
r_unk = ca.audit(CLAIM, EVID, caller=make_caller(), panel=PANEL_UNK, figures=FIGS)
u = {x["lens"]: x for x in r_unk["panel"]}
check("(G.4) vision_tier 'unknown' (id fuera de tabla) y 'none' (fila embed) → 0 bloques al caller, detail 'model-vision-unknown', tier "
      "declarado; system SIN regla; vision.state 'no-eligible-figures'",
      SEEN["evidence-grounding"][0]["n"] == 0 and SEEN["reproducibility"][0]["n"] == 0
      and u["evidence-grounding"]["saw_figures"]["detail"] == "model-vision-unknown" and u["evidence-grounding"]["saw_figures"]["tier"] == "unknown"
      and u["reproducibility"]["saw_figures"]["detail"] == "model-vision-unknown" and u["reproducibility"]["saw_figures"]["tier"] == "none"
      and not SEEN["evidence-grounding"][0]["rule"] and r_unk["vision"]["state"] == "no-eligible-figures")
PANEL_FAM = PANEL_UNK[:2] + [{"reviewer": HAIKU, "family": "anthropic", "api": "anthropic-batch", "lens": "evidence-grounding"},
                             {"reviewer": "llama-9", "family": "unknown", "lens": "reproducibility"}]
SEEN.clear()
r_fam = ca.audit(CLAIM, EVID, caller=make_caller(), panel=PANEL_FAM, figures=FIGS)
_fam = {x["lens"]: x for x in r_fam["panel"]}
check("(G.6) member con `api` explícita SIN forma de bloques conocida (fuera de models.TOOL_CALL_APIS) y tier con visión → detail "
      "'api-form-not-verified', 0 bloques; familia desconocida (id fuera de tabla, api None) → 'model-vision-unknown' (el tier decide antes "
      "que el transporte, G.4)",
      _fam["evidence-grounding"]["saw_figures"]["detail"] == "api-form-not-verified" and SEEN["evidence-grounding"][0]["n"] == 0
      and _fam["reproducibility"]["saw_figures"]["detail"] == "model-vision-unknown" and SEEN["reproducibility"][0]["n"] == 0)
os.environ["WITT_FIGURES_VISION"] = "0"
SEEN.clear()
r_v0 = ca.audit(CLAIM, EVID, caller=make_caller(), figures=FIGS)
os.environ.pop("WITT_FIGURES_VISION", None)
check("(M.2) WITT_FIGURES_VISION=0: NINGUNA lente recibe imágenes (0/0/0/0), detail 'kill-switch WITT_FIGURES_VISION=0' en las 4, system "
      "sin regla, vision {state kill-switch, enabled False}; el resto de saw_figures/vision sigue DECLARADO (las figuras observadas siguen)",
      all(v[0]["n"] == 0 and not v[0]["has_figures"] and not v[0]["rule"] for v in SEEN.values())
      and all(x["saw_figures"]["detail"] == "kill-switch WITT_FIGURES_VISION=0" for x in r_v0["panel"])
      and r_v0["vision"]["state"] == "kill-switch WITT_FIGURES_VISION=0" and r_v0["vision"]["enabled"] is False
      and r_v0["vision"]["n_candidates"] == 9)

# =====================================================================================================================
# 10. (H) WITT_FIGURES_COUNT_TOKENS=1 — tokens_measured = input_tokens − count_tokens (fake), sólo Anthropic con imágenes
# =====================================================================================================================
_orig_count = ca._anthropic_count_tokens
_COUNT_CALLS = []


def _fake_count(model, system, user_text, tool=None, tools=None, timeout=60, user_content=None):
    _COUNT_CALLS.append({"model": model, "rule_in_system": ca.FIGURE_READING_RULE in system, "user_text": user_text,
                         "user_content": user_content})
    return 1000


ca._anthropic_count_tokens = _fake_count
os.environ["WITT_FIGURES_COUNT_TOKENS"] = "1"
try:
    r_ct = ca.audit(CLAIM, EVID, caller=make_caller(usage={"input_tokens": 6037, "output_tokens": 5}), figures=FIGS)
    ca._anthropic_count_tokens = lambda *a, **k: (_ for _ in ()).throw(ca.CallerError("http-400", "count failed"))
    r_ct_err = ca.audit(CLAIM, EVID, caller=make_caller(usage={"input_tokens": 6037, "output_tokens": 5}), figures=FIGS)
finally:
    os.environ.pop("WITT_FIGURES_COUNT_TOKENS", None)
    ca._anthropic_count_tokens = _orig_count
ct = {x["lens"]: x["saw_figures"] for x in r_ct["panel"]}
cte = {x["lens"]: x["saw_figures"] for x in r_ct_err["panel"]}
check("(H) COUNT_TOKENS=1: evidence-grounding (Anthropic, 9 imágenes) → tokens_measured 6037 − 1000 = 5037 (clase medición derivada), "
      "tokens_measured_text_only 1000, state 'measured (…last attempt)'; el conteo se pidió con el MISMO system (con la regla) y el MISMO "
      "user_text, UNA vez; reproducibility (OpenAI) → 'not-available (provider does not separate image tokens)'; correctness (sin "
      "imágenes) → 'no-images'; vision.count_tokens.requested True",
      ct["evidence-grounding"]["tokens_measured"] == 5037 and ct["evidence-grounding"]["tokens_measured_text_only"] == 1000
      and ct["evidence-grounding"]["tokens_measured_state"] == ca.TOKENS_MEASURED_STATES[0]
      and len(_COUNT_CALLS) == 1 and _COUNT_CALLS[0]["model"] == HAIKU and _COUNT_CALLS[0]["rule_in_system"] is True
      and ct["reproducibility"]["tokens_measured"] is None
      and ct["reproducibility"]["tokens_measured_state"] == "not-available (provider does not separate image tokens)"
      and ct["correctness"]["tokens_measured_state"] == "no-images" and r_ct["vision"]["count_tokens"]["requested"] is True)
_cc0 = _COUNT_CALLS[0]["user_content"] if _COUNT_CALLS else None
check("(H, corrector) el conteo se pide con la MISMA petición del juez MENOS las imágenes: user_content = lista de 10 bloques `text` (9 rótulos "
      "'Figure k — <id> (<label>): <caption>' + el user_text al final), CERO bloques `image`; saw_figures.tokens_measured_counted_blocks 10 — los "
      "rótulos de caption cuentan como TEXTO, no como visión (antes se atribuían a visión: sesgo al alza por construcción)",
      isinstance(_cc0, list) and len(_cc0) == 10 and all(b.get("type") == "text" for b in _cc0)
      and _cc0[-1]["text"] == _COUNT_CALLS[0]["user_text"] and _cc0[0]["text"].startswith("Figure 1 — ")
      and all(f["caption"] in b["text"] for f, b in zip(FIGS, _cc0[:-1]))
      and ct["evidence-grounding"]["tokens_measured_counted_blocks"] == 10,
      json.dumps({"n_blocks": len(_cc0) if isinstance(_cc0, list) else None, "types": sorted({b.get("type") for b in (_cc0 or [])})}))
_body_ct = None
try:
    _orig_urlopen_ct = urllib.request.urlopen
    def _cap_ct(req, timeout=None):
        global _body_ct
        _body_ct = json.loads(req.data.decode("utf-8"))
        raise RuntimeError("captured")
    urllib.request.urlopen = _cap_ct
    os.environ["ANTHROPIC_API_KEY"] = "sk-smoke-fake"
    try:
        ca._anthropic_count_tokens(HAIKU, "S", "U", user_content=[{"type": "text", "text": "L1"}, {"type": "text", "text": "U"}])
    except Exception:
        pass
finally:
    os.environ["ANTHROPIC_API_KEY"] = ""
    urllib.request.urlopen = _orig_urlopen_ct
check("(H, corrector) _anthropic_count_tokens(user_content=[bloques]) manda messages[0].content = la LISTA de bloques (no el string); sin user_content "
      "el cuerpo sigue siendo el de 1.12-F3 (content == user_text) — cuerpo capturado con urlopen falso, llave falsa, nada llamado",
      isinstance(_body_ct, dict) and _body_ct["messages"][0]["content"] == [{"type": "text", "text": "L1"}, {"type": "text", "text": "U"}]
      and _body_ct["model"] == HAIKU and _body_ct["tool_choice"]["name"] == ca.VERDICT_TOOL["name"],
      json.dumps(_body_ct)[:200] if _body_ct else "sin cuerpo")
check("(H) conteo que FALLA (CallerError http-400) → tokens_measured None + state 'error: http-400' DECLARADO; el panel no se cae",
      cte["evidence-grounding"]["tokens_measured"] is None and cte["evidence-grounding"]["tokens_measured_state"] == "error: http-400"
      and r_ct_err["verdict"] == "APPROVE")
check("(H) _anthropic_count_tokens sin ANTHROPIC_API_KEY → CallerError('no-api-key') con CERO llamadas (cero red)",
      isinstance(_raises(lambda: ca._anthropic_count_tokens(HAIKU, "S", "U")), ca.CallerError)
      and _raises(lambda: ca._anthropic_count_tokens(HAIKU, "S", "U")).kind == "no-api-key" and _NET_CALLS == [])

# =====================================================================================================================
# 11. apply_to_bundle copia `vision`; firmas del contrato F3; cierre
# =====================================================================================================================
try:
    from lib import answer_pipeline as _ap  # noqa: E402
    b = ca.apply_to_bundle({"run_id": "smoke-vision", "question": "q"}, r, ["CORPUS-2026-0001"], answer_pipeline_module=_ap)
    b0 = ca.apply_to_bundle({"run_id": "smoke-vision-ks", "question": "q"}, r_ks, ["CORPUS-2026-0001"], answer_pipeline_module=_ap)
    check("apply_to_bundle (answer_pipeline REAL): bundle['audit'].vision == audit.vision y las filas del panel llevan saw_figures; con el "
          "resultado del kill-switch NO gana `vision` (ausente ≠ null); identidad re-sellada",
          b["audit"]["vision"] == r["vision"] and all("saw_figures" in x for x in b["audit"]["panel"])
          and "vision" not in b0["audit"] and b["bundle_identity"]["sha256"] != b0["bundle_identity"]["sha256"])
except Exception as e:  # pragma: no cover
    check(f"apply_to_bundle: answer_pipeline importable ({type(e).__name__}: {str(e)[:80]})", False)
check("contrato F3 (firmas, +ADR-0086 attested=None aditivo al final): audit(..., directives=None, figures=None, "
      "vision_lenses=None, attested=None); _anthropic_tool_call(..., tools=None, "
      "user_content=None); _responses_kwargs(..., reasoning_effort=None, user_content=None); _openai_responses_call(..., user_content=None); "
      "_openai_chat_call(model, system, user_text, timeout=None, tool=None, client=None, user_content=None); _default_caller SIN cambio; "
      "parse_figure_readings(raw, delivered); figure_readings_from_panel(rows); vision_lenses(env=None)",
      list(inspect.signature(ca.audit).parameters)[-4:] == ["directives", "figures", "vision_lenses", "attested"]
      and inspect.signature(ca.audit).parameters["figures"].default is None
      and inspect.signature(ca.audit).parameters["attested"].default is None
      and list(inspect.signature(ca._anthropic_tool_call).parameters)[-2:] == ["tools", "user_content"]
      and list(inspect.signature(ca._responses_kwargs).parameters)[-2:] == ["reasoning_effort", "user_content"]
      and list(inspect.signature(ca._openai_responses_call).parameters)[-1] == "user_content"
      and list(inspect.signature(ca._openai_chat_call).parameters) == ["model", "system", "user_text", "timeout", "tool", "client", "user_content"]
      and list(inspect.signature(ca._default_caller).parameters) == ["member", "system", "user_text", "tool"]
      and list(inspect.signature(ca.parse_figure_readings).parameters) == ["raw", "delivered"]
      and list(inspect.signature(ca.figure_readings_from_panel).parameters) == ["rows"]
      and list(inspect.signature(ca.vision_lenses).parameters) == ["env"])
check("(G.4) models: vision_tier_of por tabla — grounding g2 standard-1568 · sintetizador high-res-2576 · puente tile-512 · candidato "
      "patch-32 ×1.2 · embed none · id desconocido ('unknown', 'unknown-to-table'); vision_verified False en TODAS las filas (nada medido "
      "en vivo aún)",
      models.vision_tier_of(HAIKU)[0] == "standard-1568" and models.vision_tier_of(OPUS)[0] == "high-res-2576"
      and models.vision_tier_of(GPT_BRIDGE)[0] == "tile-512" and models.vision_tier_of(ASTRA)[:2] == ("patch-32", 1.2)
      and models.vision_tier_of(EMBED)[0] == "none" and models.vision_tier_of("j-unknown") == ("unknown", None, False, "unknown-to-table")
      and not any(r_["vision_verified"] for r_ in models.MODELS.values()))
def _caller_cs(member, system, user_text):
    out = dict(VOK, caught=f"({member['lens']})")
    if member["lens"] == "evidence-grounding":
        out["citation_support"] = [{"n": 1, "verdict": "supported"}]
    return out, {"input_tokens": 10, "output_tokens": 5}


_r_cs = ca.audit(CLAIM, EVID, caller=_caller_cs, figures=FIGS)
_eg_cs = next(x for x in _r_cs["panel"] if x["lens"] == "evidence-grounding")
check("(E/G, corrector — límite declarado) la fila de evidence-grounding con citation_support gana `citation_support_vision_informed` == (saw_figures.n > 0): "
      "el veredicto de soporte de una cita figure pudo estar informado por píxeles y el registro lo DECLARA; FIGURE_READING_RULE "
      "(system, sólo cuando viajan imágenes) pide juzgar SOLO el CAPTION ('the image never decides support') — la description de citation_support NO "
      "cambia (VERDICT_TOOL sin figure_readings sigue byte a byte el de 1.11, golden de arriba); una fila sin citation_support no gana la llave",
      _eg_cs.get("citation_support") == [{"n": 1, "verdict": "supported"}] and _eg_cs["citation_support_vision_informed"] is True
      and _eg_cs["saw_figures"]["n"] == 9
      and all("citation_support_vision_informed" not in x for x in _r_cs["panel"] if x["lens"] != "evidence-grounding")
      and "the image never decides support" in ca.FIGURE_READING_RULE
      and "the image never decides support" not in ca.VERDICT_TOOL["input_schema"]["properties"]["citation_support"]["description"]
      and "judge the CAPTION" in ca.FIGURE_READING_RULE,
      json.dumps({k: _eg_cs.get(k) for k in ("citation_support", "citation_support_vision_informed")}))
check("docstring: el módulo declara ADR-0083 (G), user_content, saw_figures, FIGURE_READING_RULE y el kill-switch M.1",
      all(s in ca.__doc__ for s in ("ADR-0083", "user_content", "saw_figures", "FIGURE_READING_RULE", "WITT_FIGURES=0")))
check("(M.5) urllib.request.urlopen REAL bloqueado y contado: 0 llamadas en todo el gate; 'openai' jamás importado aquí",
      _NET_CALLS == [] and "openai" not in sys.modules, str(_NET_CALLS[:3]))

# =====================================================================================================================
# ADR-0086 (F3) · IMÁGENES ATESTIGUADAS AL PANEL — bytes sólo a las lentes con visión, rotulados y aparte de las figuras
# =====================================================================================================================
from lib import attestations as AT  # noqa: E402

_B64_A = base64.b64encode(b"imagen-atestiguada-A" * 8).decode()
_B64_B = base64.b64encode(b"imagen-atestiguada-B" * 8).decode()
ATT_A = {"id": "attested:" + "a" * 12, "sha256": "a" * 64, "media_type": "image/png", "b64": _B64_A,
         "caption": "micrografía de pronefros aportada por natalia", "dims": {"w": 64, "h": 48}}
ATT_B = {"id": "attested:" + "b" * 12, "sha256": "b" * 64, "media_type": "image/png", "b64": _B64_B,
         "caption": "corte histológico aportado por natalia", "dims": {"w": 64, "h": 48}}
PANEL_4 = [{"reviewer": OPUS, "family": "anthropic", "lens": l}   # OPUS sale de la tabla: cero literales de modelo aquí
           for l in ("correctness", "overclaim", "evidence-grounding", "reproducibility")]


def _mk_caller_att(registro):
    """Caller falso que APUNTA lo que recibió cada asiento (member y system) y devuelve un veredicto válido."""
    def _c(member, system, user_text):
        registro[member["lens"]] = {
            "n_attested": len(member.get("attested") or []),
            "n_figures": len(member.get("figures") or []),
            "regla_attested": AT.ATTESTED_READING_RULE in system,
            "regla_figuras": ca.FIGURE_READING_RULE in system,
        }
        return ({"verdict": "approve", "caught": "", "correction_applied": "", "reasons": [], "citation_support": []},
                {"input_tokens": 10, "output_tokens": 2}, {})
    return _c


_reg = {}
_a_att = ca.audit("claim", "evidence", panel=PANEL_4, caller=_mk_caller_att(_reg), min_valid=1, attested=[ATT_A])
check("(0086 F3) sólo las DOS lentes con visión reciben bytes atestiguados; las otras no reciben ninguno y su fila lo "
      "declara con el vocabulario cerrado",
      _reg["evidence-grounding"]["n_attested"] == 1 and _reg["reproducibility"]["n_attested"] == 1
      and _reg["correctness"]["n_attested"] == 0 and _reg["overclaim"]["n_attested"] == 0
      and {r["lens"]: r["saw_attested"]["detail"] for r in _a_att["panel"]} == {
          "evidence-grounding": "sent", "reproducibility": "sent",
          "correctness": "lens-not-in-vision-lenses", "overclaim": "lens-not-in-vision-lenses"}
      and all(r["saw_attested"]["detail"] in ca.SAW_ATTESTED_DETAILS for r in _a_att["panel"]),
      json.dumps({r["lens"]: r["saw_attested"]["detail"] for r in _a_att["panel"]}))
check("(0086 F3) la regla de lo atestiguado entra al system SÓLO de quien recibe imágenes aportadas; el resto ve el "
      "system de siempre",
      _reg["evidence-grounding"]["regla_attested"] and _reg["reproducibility"]["regla_attested"]
      and not _reg["correctness"]["regla_attested"] and not _reg["overclaim"]["regla_attested"])
check("(0086 F3) la fila declara lo entregado (n y shas) y su CLASE: lo que una lente diga de una imagen aportada es "
      "JUICIO, jamás medición",
      [r for r in _a_att["panel"] if r["lens"] == "evidence-grounding"][0]["saw_attested"]["sha256s"] == ["a" * 64]
      and [r for r in _a_att["panel"] if r["lens"] == "evidence-grounding"][0]["saw_attested"]["class"] == "model-judgment"
      and ca.ATTESTED_READINGS_CLASS == "model-judgment")
_res_att = (_a_att.get("vision") or {}).get("attested") or _a_att.get("attested_vision")
check("(0086 F3) el resumen dice el estado, las lentes, cuántas vio cada una, la regla literal y su clase — sin un solo "
      "byte ni caption",
      _res_att["state"] == "sent" and _res_att["enabled"] is True
      and _res_att["n_images_by_lens"]["evidence-grounding"] == 1 and _res_att["n_candidates"] == 1
      and _res_att["rule"] == AT.ATTESTED_READING_RULE and _res_att["readings"]["class"] == "model-judgment"
      and _B64_A not in json.dumps(_res_att) and "micrografía" not in json.dumps(_res_att, ensure_ascii=False))
check("(0086 F3) NINGÚN byte atestiguado entra al objeto audit (los b64 viven en el member, que la fila no copia)",
      _B64_A not in json.dumps(_a_att, default=str) and "micrografía" not in json.dumps(_a_att, ensure_ascii=False, default=str))

_reg0 = {}
_a_sin = ca.audit("claim", "evidence", panel=PANEL_4, caller=_mk_caller_att(_reg0), min_valid=1)
check("(0086 M.1) una corrida SIN imágenes aportadas es byte a byte la de 1.13: ninguna fila trae saw_attested, el audit "
      "no trae el resumen y el member no trae `attested`",
      not any("saw_attested" in r for r in _a_sin["panel"])
      and "attested" not in json.dumps(_a_sin.get("vision") or {}) and "attested_vision" not in _a_sin
      and all(v["n_attested"] == 0 and not v["regla_attested"] for v in _reg0.values()))

_reg_ks = {}
os.environ["WITT_ATTESTED_IMAGES"] = "0"
_a_ks = ca.audit("claim", "evidence", panel=PANEL_4, caller=_mk_caller_att(_reg_ks), min_valid=1, attested=[ATT_A])
os.environ.pop("WITT_ATTESTED_IMAGES", None)
check("(0086 M.1) KILL-SWITCH WITT_ATTESTED_IMAGES=0 aunque el llamador pase imágenes: ninguna fila trae saw_attested, "
      "el audit no trae resumen, el member no recibe nada y la regla no entra al system",
      not any("saw_attested" in r for r in _a_ks["panel"])
      and "attested" not in json.dumps(_a_ks.get("vision") or {}) and "attested_vision" not in _a_ks
      and all(v["n_attested"] == 0 and not v["regla_attested"] for v in _reg_ks.values()))

_reg_v0 = {}
os.environ["WITT_ATTESTED_VISION"] = "0"
_a_v0 = ca.audit("claim", "evidence", panel=PANEL_4, caller=_mk_caller_att(_reg_v0), min_valid=1, attested=[ATT_A])
os.environ.pop("WITT_ATTESTED_VISION", None)
check("(0086 N.2) VISIÓN APAGADA (WITT_ATTESTED_VISION=0): ninguna lente recibe bytes, pero el registro lo DECLARA con "
      "su estado — apagar no es 'no había imágenes'",
      all(v["n_attested"] == 0 for v in _reg_v0.values())
      and all(r["saw_attested"]["detail"] == "kill-switch WITT_ATTESTED_VISION=0" for r in _a_v0["panel"])
      and ((_a_v0.get("vision") or {}).get("attested") or {}).get("state") == "kill-switch WITT_ATTESTED_VISION=0",
      json.dumps([r.get("saw_attested", {}).get("detail") for r in _a_v0["panel"]]))

_reg_cap = {}
os.environ["WITT_ATTESTED_MAX_PER_LENS"] = "1"
_a_cap = ca.audit("claim", "evidence", panel=PANEL_4, caller=_mk_caller_att(_reg_cap), min_valid=1, attested=[ATT_A, ATT_B])
os.environ.pop("WITT_ATTESTED_MAX_PER_LENS", None)
_eg_cap = [r for r in _a_cap["panel"] if r["lens"] == "evidence-grounding"][0]["saw_attested"]
check("(0086 F3) el tope por lente se respeta y lo que se quedó fuera se CUENTA (no desaparece en silencio)",
      _reg_cap["evidence-grounding"]["n_attested"] == 1 and _eg_cap["n"] == 1
      and _eg_cap["n_dropped"]["lens_cap"] == 1, json.dumps(_eg_cap["n_dropped"]))

_mala = {"id": "attested:mala", "sha256": "c" * 64, "media_type": "application/pdf", "b64": _B64_A}
_a_mala = ca.audit("claim", "evidence", panel=PANEL_4, caller=_mk_caller_att({}), min_valid=1, attested=[_mala])
_eg_mala = [r for r in _a_mala["panel"] if r["lens"] == "evidence-grounding"][0]["saw_attested"]
check("(0086 F3) una imagen con forma inválida (tipo fuera de vocabulario) no se entrega y se cuenta como descartada",
      _eg_mala["detail"] == "no-eligible-attested" and _eg_mala["n_dropped"]["invalid"] == 1)

# --- la FORMA del contenido: figuras primero, lo atestiguado detrás de su separador, el texto al final ---------------
_blocks = F.anthropic_blocks([FIGS[0]] if FIGS else [], "TEXTO-DEL-USUARIO",
                             attested_blocks=AT.anthropic_attested_blocks([ATT_A]))
_tipos = [b.get("type") for b in _blocks]
check("(0086 F3) Anthropic: [figuras…] + [separador ATESTIGUADO + rótulo + imagen] + [texto] — las imágenes aportadas "
      "van DESPUÉS de las figuras y ANTES del texto, nunca mezcladas",
      _tipos[-1] == "text" and _blocks[-1]["text"] == "TEXTO-DEL-USUARIO"
      and AT.ATTESTED_SEPARATOR_TEXT in json.dumps(_blocks, ensure_ascii=False)
      and _tipos.index("image") < len(_tipos) - 1,
      json.dumps(_tipos))
check("(0086 F3) el separador dice, con todas sus letras, que lo que sigue es PRIOR ART de una persona y NUNCA evidencia",
      "prior art" in AT.ATTESTED_SEPARATOR_TEXT.lower() and "never evidence" in AT.ATTESTED_SEPARATOR_TEXT.lower())
check("(0086 F3) sin bloques atestiguados el contenido es BYTE A BYTE el de 1.12 (el parámetro es aditivo)",
      F.anthropic_blocks([FIGS[0]] if FIGS else [], "T") == F.anthropic_blocks([FIGS[0]] if FIGS else [], "T", attested_blocks=None)
      and F.openai_responses_parts([], "T") == F.openai_responses_parts([], "T", attested_parts=None)
      and F.openai_chat_parts([], "T") == F.openai_chat_parts([], "T", attested_parts=None))
check("(0086 F3) el módulo declara en su docstring la entrega de lo atestiguado y su vocabulario",
      "ADR-0086" in ca.__doc__ or "attested" in ca.__doc__.lower()
      or all(hasattr(ca, n) for n in ("SAW_ATTESTED_DETAILS", "ATTESTED_READINGS_CLASS", "_attested_for_member")))


npass = sum(CHECKS)
print("\n== %d/%d PASS ==" % (npass, len(CHECKS)))
sys.exit(0 if npass == len(CHECKS) else 1)
