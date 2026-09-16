"""
smoke_live_web.py — ADR-0084 § Gates EN VIVO: el instrumento de LG1 (fixture REAL de Brave, 1 GET), LG2 (localizador de punta a
punta en dev: 1 GET Brave + <= WITT_WEB_MAX_MATERIALIZE GET a Europe PMC), LG3 (rate limit real: cabeceras X-RateLimit-*) y LG5 (alterno
Anthropic web_search, 1 llamada). Lo corre Emmanuel; GASTA lo que dice; jamás toca la BD (db_imported false medido en cada salida).

Ningún smoke del CI gasta modelo ni red (ADR-0084 (M.2)): todo lo que aquí llama a la red lo hace con la llave del entorno del proceso
de Emmanuel. Este script NO replica nada: usa el código REAL — `.tooluniverse/tools/brave_web_search.py` (W1: prepare/locate, la ÚNICA
costura `_get`), `lib.web_locator` (W2: provider_state, env_config, locate, resolve_urls, build_anthropic_body) y
`lib.fetch_paper._resolve_one` (materialización por Europe PMC, UNA GET, sin escribir caché).

  --provider brave|anthropic   (default brave; anthropic fija WITT_WEB_LOCATOR=anthropic SÓLO en este proceso — es EXPLÍCITO)
  --query "<q>"                 (default 'wt1a zebrafish pronephros podocyte' — la del fixture LG1)
  --count N                     (count de Brave; default el de WITT_WEB_MAX_RESULTS)
  --materialize                 LG2: por cada located pmid|pmcid|doi, fetch_paper._resolve_one(epmc_ident) → found True/False
  --dry-run                     construye TODO sin red ni llave: la petición Brave (url_sent SIN token, params_sent ⊆ documentados,
                                ninguno de PARAMS_NEVER_SENT), el cuerpo Anthropic (SIN tool_choice, allowed_domains == la lista,
                                tipo/max_uses de la env), provider_state declarado y el resolutor sobre el fixture SINTÉTICO de W1
                                (0 red) — con `urlopen` BLOQUEADO y contado (== 0). Es el ÚNICO modo que corre el CI (exit 0).

Salida: filas por consola y, en los modos EN VIVO, `analysis/outputs/live_web_<fecha>.json` (append por invocación) pasado por un
cinturón anti-secreto (nunca headers, env ni llaves — sólo su PRESENCIA). Las URLs SÍ se imprimen aquí (instrumento humano: es el
ledger que frozen.web_locator congela); `description`/`extra_snippets` jamás (el tool las corta en la salida, W1 A.3). Sin llave para
el proveedor pedido rehúsa con `no-api-key` (exit 2) ANTES de tocar red. Cuota: las sondas CLI NO pasan por la BD (QUOTA_RULE) —
`quota.state 'not-enforced (no quota callable)'` declarado.

Uso (venv de los gates: dev/.venvs/witt-query-service):
  python analysis/scripts/smoke_live_web.py --dry-run
  python analysis/scripts/smoke_live_web.py --provider brave --query "wt1a zebrafish pronephros podocyte"              # LG1/LG3
  python analysis/scripts/smoke_live_web.py --provider brave --query "wt1a pronephros review" --materialize          # LG2
  WITT_WEB_LOCATOR=anthropic python analysis/scripts/smoke_live_web.py --provider anthropic --query "wt1a review"    # LG5
"""
import argparse
import datetime as _dt
import json
import os
import re
import sys
import tempfile
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))

from lib import web_locator as wl  # noqa: E402

SECRET_ENV = ("BRAVE_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "NCBI_API_KEY", "OPENALEX_API_KEY")
DEFAULT_QUERY = "wt1a zebrafish pronephros podocyte"
FIXTURE_SYNTHETIC = ROOT / "rag_index" / "query_service" / "fixtures" / "brave_web_search_SYNTHETIC_wt1a_20260916.json"
OUT_DIR = ROOT / "analysis" / "outputs"


def _redact(obj, secrets):
    """Cinturón anti-secreto: ningún valor de llave del entorno sale en la salida (sólo su presencia)."""
    s = json.dumps(obj, ensure_ascii=False, default=str)
    for v in secrets:
        if v and len(v) >= 6:
            s = s.replace(v, "<redacted-secret>")
    return json.loads(s)


def _secrets():
    return [os.environ.get(k) or "" for k in SECRET_ENV]


def _key_presence():
    return {k: bool((os.environ.get(k) or "").strip()) for k in ("BRAVE_API_KEY", "ANTHROPIC_API_KEY")}


def _print(row):
    print(json.dumps(row, ensure_ascii=False, indent=2, default=str))


class _NetBlock:
    """urlopen BLOQUEADO y CONTADO (--dry-run): ninguna petición sale; si algo lo intenta, se cuenta y se declara."""

    def __init__(self):
        self.calls = []
        self._real = urllib.request.urlopen

    def __enter__(self):
        def _blocked(*a, **kw):
            req = a[0] if a else kw.get("url")
            self.calls.append(str(getattr(req, "full_url", None) or req)[:120])
            raise RuntimeError("network blocked by smoke_live_web --dry-run")
        urllib.request.urlopen = _blocked
        return self

    def __exit__(self, *exc):
        urllib.request.urlopen = self._real
        return False


def dry_run(args):
    """Construye la petición Brave y el cuerpo Anthropic SIN red ni llave; corre el resolutor sobre el fixture sintético (0 red)."""
    ok = True
    rows = {"mode": "dry-run", "db_imported": "db" in sys.modules or "rag_index.query_service.db" in sys.modules}
    tmp = tempfile.mkdtemp(prefix="witt-live-web-dry-")
    with _NetBlock() as net:
        # (1) Brave: prepare() es puro — url_sent sin token, params_sent ⊆ DOCUMENTED_PARAMS, ninguno de PARAMS_NEVER_SENT
        mod, fn, detail = wl._load_brave_tool()
        if mod is None:
            rows["brave"] = {"state": f"tool-unavailable ({detail})"}
            ok = False
        else:
            prep = mod.prepare(args.query, count=args.count, env={**os.environ, "BRAVE_API_KEY": ""})
            probe = mod.cache_probe(args.query, count=args.count, cache_dir=tmp)
            url = prep["url_sent"]
            never = [p for p in mod.PARAMS_NEVER_SENT if f"{p}=" in url]
            documented = all(p in mod.DOCUMENTED_PARAMS for p in prep["params_sent"])
            rows["brave"] = {"tool_version": mod.TOOL_VERSION, "url_sent": url, "params_sent": prep["params_sent"],
                             "params_documented_only": documented, "params_never_sent_present": never,
                             "query_sent": prep["query_sent"], "query_truncated": prep["query_truncated"],
                             "count_sent": prep["count_sent"], "count_source": prep["count_source"],
                             "cache_probe": probe, "token_in_url": "X-Subscription-Token" in url,
                             "params_verified_as_of": mod.PARAMS_VERIFIED_AS_OF}
            ok = ok and documented and not never and url.startswith(mod.BASE) and probe["cache_hit"] is False
        # (2) Anthropic: build_anthropic_body() es puro — SIN tool_choice, allowed_domains == la lista, tipo/max_uses de la env
        cfg = wl.env_config()
        model, model_src = wl.anthropic_model(cfg)
        body = wl.build_anthropic_body(args.query, cfg, model)
        tools = body.get("tools") or []
        tool = tools[0] if tools else {}
        allowed = wl.anthropic_allowed_domains(cfg)
        rows["anthropic"] = {"model": model, "model_source": model_src, "has_tool_choice": "tool_choice" in body,
                             "n_tools": len(tools), "tool_type": tool.get("type"), "tool_name": tool.get("name"),
                             "max_uses": tool.get("max_uses"), "allowed_domains": tool.get("allowed_domains"),
                             "allowed_domains_equal_list": tool.get("allowed_domains") == allowed,
                             "has_blocked_domains": "blocked_domains" in tool, "has_allowed_callers": "allowed_callers" in tool,
                             "max_tokens": body.get("max_tokens"), "system_is_dispatcher": body.get("system") == wl.ANTHROPIC_SYSTEM,
                             "provider_property": wl.ANTHROPIC_READS_WEB_TEXT}
        ok = ok and "tool_choice" not in body and len(tools) == 1 and tool.get("name") == wl.ANTHROPIC_TOOL_NAME \
            and tool.get("allowed_domains") == allowed and "blocked_domains" not in tool \
            and tool.get("type") == cfg.get("anthropic_tool_type") and tool.get("max_uses") == cfg.get("anthropic_max_uses")
        # (3) disponibilidad declarada (sin llave en el CI: off derivado) y el resolutor sobre el fixture SINTÉTICO (0 red)
        ps = wl.provider_state()
        rows["provider_state"] = {**ps, "key_present": _key_presence()}
        if FIXTURE_SYNTHETIC.exists():
            fx = json.loads(FIXTURE_SYNTHETIC.read_text(encoding="utf-8"))
            results = ((fx.get("response") or {}).get("web") or {}).get("results") or []
            res = wl.resolve_urls([{"url": r.get("url"), "title": r.get("title")} for r in results],
                                  allowed_hosts=cfg.get("allowed_hosts"), generic_doi=cfg.get("generic_doi", True))
            rows["resolver_on_synthetic_fixture"] = {
                "fixture": str(FIXTURE_SYNTHETIC.relative_to(ROOT)), "synthetic": bool((fx.get("_fixture") or {}).get("synthetic")),
                "n_results": res["n_results"], "n_located": res["n_located"], "n_unresolved": res["n_unresolved"],
                "located": [{"id": l["id"], "kind": l["kind"], "rule": l["resolver_rule"], "host": l["host"]} for l in res["located"]],
                "unresolved": [{"host": u["host"], "reason": u["reason"]} for u in res["unresolved"]],
                "resolver_version": res["resolver_version"]}
            ok = ok and res["n_results"] == len(results) and res["n_located"] + res["n_unresolved"] >= res["n_results"] - res["n_located"]
        else:
            rows["resolver_on_synthetic_fixture"] = {"state": "fixture-missing (declared)"}
    rows["urlopen_calls"] = len(net.calls)
    rows["ok"] = bool(ok and not net.calls and not rows["db_imported"])
    _print(_redact(rows, _secrets()))
    return 0 if rows["ok"] else 1


def live(args):
    """UNA consulta REAL por el código de producción (web_locator.locate sin quota_fn: las sondas CLI no cuentan) y, con
    --materialize, la verificación de existencia en Europe PMC por located de literatura (fetch_paper._resolve_one)."""
    if args.provider == "anthropic":
        os.environ["WITT_WEB_LOCATOR"] = "anthropic"
    elif not (os.environ.get("WITT_WEB_LOCATOR") or "").strip():
        os.environ["WITT_WEB_LOCATOR"] = "brave"
    ps = wl.provider_state()
    if not ps.get("available"):
        _print({"mode": "live", "provider": args.provider, "state": "no-api-key", "provider_state": ps,
                "key_present": _key_presence(), "note": "set the key in the process environment (never git/vault/memory)"})
        return 2
    cfg = wl.env_config()
    if args.count is not None:
        cfg["max_results"] = max(1, min(int(args.count), 20))
        cfg["sources"]["max_results"] = "argument:--count"
    t0 = _dt.datetime.now(_dt.timezone.utc)
    row = wl.locate(args.query, cfg, quota_fn=None, requirement_ids=["cli"], round_no=0, query_source="operator-cli:smoke_live_web")
    out = {"mode": "live", "provider": ps["provider"], "provider_source": ps["provider_source"], "query": args.query,
           "started_at": t0.isoformat(timespec="seconds"), "key_present": _key_presence(),
           "db_imported": "db" in sys.modules, "row": row}
    if args.materialize:
        from lib import fetch_paper  # noqa: E402  (import perezoso: sólo con --materialize)
        mats = []
        cap = int(cfg.get("max_materialize") or 0)
        for loc in (row.get("located") or []):
            ident = wl.epmc_ident(loc)
            if ident is None or loc.get("dedup") is not None:
                continue
            if len(mats) >= cap:
                mats.append({"id": loc["id"], "state": "not-materialized (feed cap)"})
                continue
            if not wl.EPMC_IDENT_RE.match(ident):
                mats.append({"id": loc["id"], "state": "error: ident not in EPMC form (never sent)"})
                continue
            try:
                rec, ledger = fetch_paper._resolve_one(ident)
                mats.append({"id": loc["id"], "epmc_ident": ident, "found": rec is not None,
                             "title_epmc": (rec or {}).get("title"), "pmid": (rec or {}).get("pmid"), "pmcid": (rec or {}).get("pmcid"),
                             "doi": (rec or {}).get("doi"), "ledger_status": (ledger or {}).get("status")})
            except Exception as e:
                mats.append({"id": loc["id"], "epmc_ident": ident, "state": f"error: {type(e).__name__}: {str(e)[:120]}"})
        out["materialized"] = mats
        out["n_materialized_found"] = sum(1 for m in mats if m.get("found") is True)
    # medición LG3: cabeceras X-RateLimit-* si la fila-proveedor las trae (brave_web_search.locate las normaliza)
    out["rate_limit_headers"] = (row.get("cache_probe") or {}).get("rate_limit_headers") or row.get("rate_limit_headers")
    red = _redact(out, _secrets())
    _print(red)
    try:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        path = OUT_DIR / f"live_web_{t0.strftime('%Y%m%d')}.json"
        prev = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
        prev.append(red)
        path.write_text(json.dumps(prev, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        print(f"\nwritten: {path.relative_to(ROOT)} (append; secrets redacted by presence-only belt)")
    except Exception as e:   # la escritura no invalida la medición
        print(f"\noutput not written: {type(e).__name__}: {e}")
    st = row.get("provider_status")
    return 0 if st in ("success", "no-match") else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    ap.add_argument("--provider", choices=("brave", "anthropic"), default="brave")
    ap.add_argument("--query", default=DEFAULT_QUERY)
    ap.add_argument("--count", type=int, default=None)
    ap.add_argument("--materialize", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    if not re.search(r"\S", args.query or ""):
        print("empty query"); return 2
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    return dry_run(args) if args.dry_run else live(args)


if __name__ == "__main__":
    sys.exit(main())
