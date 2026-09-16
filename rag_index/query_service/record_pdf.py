"""
record_pdf.py — el PDF de servidor del registro congelado (M4 export, ADR-0073).

El tapón de la fuga que registro-congelado.md documenta: *"cualquier derivado fuera de la pantalla
sale limpio"* — impresión, copy-paste a Word/WhatsApp y correo tiran la textura/riel/cinta y
conservan la prosa y los números; el artefacto que circula fuera de la app es exactamente lo que
este producto existe para hacer imposible. Reglas del contrato (decisión del fundador 2026-08-04):

  1. **Jamás "imprimir la página"**: el PDF se genera DEL JSON CONGELADO con plantilla propia
     (una fuente, tres lectores: URL, PDF, bitácora — no pueden divergir).
  2. **La variante impresa no usa textura de fondo**: usa lo que sobrevive — LA PALABRA IMPRESA
     SIEMPRE, reglas y bordes, y las bandas dicen las palabras completas (la banda de
     NO INSTRUMENTADO no se apoya en punteados).
  3. El estado epistémico va ARRIBA de la respuesta (el orden de lectura es el orden de confianza).
  4. La identidad manda: `question_matches_run == false` ⇒ el PDF NO SE GENERA (misma regla que
     la hoja, ADR-0044).
  5. ADR-0079: dos secciones nuevas — 'EJES DEL EPISODIO' (junto al estado, arriba) e 'INVESTIGACION'
     (turno, padre, precedente en LETRAS marcado NO ADMISIBLE COMO EVIDENCIA, origen, identidad del
     padre). Tres estados por llave: registro sin la llave ⇒ 'NO INSTRUMENTADO (contrato < 1.8)';
     null-declarado con razón; valor. Nada se rellena.

Tipografía: fuentes core (latin-1) con saneo DECLARADO de caracteres fuera de latin-1 (em-dash→'-',
etc.) — la fidelidad exigida es EPISTÉMICA (el estado viaja), no tipográfica; embeber un TTF queda
como pulido futuro. Dependencia medida (ADR-0062-style): fpdf2 2.8.8 = 4 paquetes puros
(fpdf2+defusedxml+fonttools+Pillow), nada de playwright/cairo.
"""
import datetime
import json

from fpdf import FPDF

# saneo latin-1 DECLARADO: el registro usa em-dashes/flechas/comillas tipográficas que las fuentes
# core no cargan; se mapean a equivalentes imprimibles (jamás se tira contenido en silencio).
_LATIN1_MAP = {
    "—": "-", "–": "-", "‘": "'", "’": "'", "“": '"', "”": '"',
    "…": "...", "→": "->", "←": "<-", "·": "-", "•": "-",
    "≤": "<=", "≥": ">=", "≈": "~", "τ": "tau", "✖": "x", "✓": "ok",
}


def _t(s):
    if s is None:
        return "no consta"
    s = str(s)
    for k, v in _LATIN1_MAP.items():
        s = s.replace(k, v)
    return s.encode("latin-1", "replace").decode("latin-1")


_MODE_BAND = {
    "semantic": "MODO DE RECUPERACION: SELLADA LIMPIA - busqueda semantica medida",
    "degraded-dense-failed": ("MODO: DEGRADADA - la busqueda por significado FALLO; el resultado es "
                              "sparse-only y NO es semantico"),
    "reduced-by-config": "MODO: REDUCIDO POR CONFIGURACION - es configuracion, no falla",
    "not-measured": "NO INSTRUMENTADO - el modo de recuperacion no se midio (se lee como el peor caso)",
}

_STATE_GLOSS = {
    "DI_SUFFICIENT": "la DATA INAMOVIBLE alcanzo",
    "FALLBACK_FETCHED": "se recupero material externo - falta auditarlo",
    "AUDIT_APPROVED": "auditoria aprobada",
    "AUDIT_REJECTED": "ninguna evidencia paso la auditoria",
}

_SOURCE_GLOSS = {
    "stated-second-elicitation": "elicitacion dedicada post-sintesis (la medicion autoritativa, ADR-0065)",
    "stated": "declarada in-line por el modelo",
    "recovered-from-malformed-tool-call": "RECUPERADA de un tool call malformado - valor real, NO medicion limpia",
    "derived-min-of-subclaims": "derivada (min de sub-claims, peor-de-N declarado)",
}

_ABSENCE_GLOSS = {
    "not-applicable": "afirma evidencia positiva",
    "no-evidence-retrieved": "el store no sabe - NO dice nada del mundo (dispara re-ingesta, no conclusion)",
    "evidence-of-no-effect": "evidencia ACTIVA de efecto nulo - estado OPUESTO a no-encontrado",
}

# --- ADR-0079: la investigacion (T-<run_no raiz>) y los ejes del episodio, EN PALABRAS ----------------
# Tres estados por llave (ADR-0074): la llave NO EXISTE en el registro -> 'NO INSTRUMENTADO (contrato
# < 1.8)' (la corrida nacio antes del contrato; jamas se rellena); null-declarado con razon; valor.
_NOT_INSTRUMENTED = "NO INSTRUMENTADO (contrato < 1.8) - el registro nacio antes de ADR-0079; no se rellena"

_TURN_KIND_GLOSS = {
    "root": "raiz - abre la investigacion",
    "refine": "refinamiento - pregunta o entidades cambiaron respecto al padre",
    "rerun": "re-ejecucion - misma pregunta y entidades que el padre",
    "branch": "rama - el padre ya tenia otro hijo",
}

_ORIGIN_GLOSS = {
    "production": "produccion - cuenta como precedente y para calibracion",
    "dev-offline": "desarrollo sin red - NO cuenta como precedente ni para calibracion",
    "replay": "re-ejecucion de registro - NO cuenta",
    "smoke": "prueba automatizada - NO cuenta",
    "simulation": "simulacion - NO cuenta",
    "fixture": "fixture de prueba - NO cuenta",
    None: "unknown-pre-adr-0079 - anterior a la columna origin; incluida en precedente y DECLARADA como desconocida",
}

# Tabla de mapeo de los cuatro ejes (ADR-0079 G, clase 'derived-at-freeze'): la palabra viene del enum,
# el enum viene del registro. Un literal fuera de tabla se imprime tal cual y se marca.
_AXIS_WORDS = {
    "world": {
        "effect-claimed": "MUNDO: se afirma un efecto (aprobada, evidencia positiva)",
        "null-bounded": "MUNDO: efecto nulo ACOTADO por evidencia activa (opuesto a no-encontrado)",
        "indeterminate": "MUNDO: INDETERMINADO - el store no sabe; no dice nada del mundo",
        "not-established": "MUNDO: NO ESTABLECIDO - la auditoria rechazo la respuesta",
        "not-assessed": "MUNDO: SIN EVALUAR - no hubo auditoria",
    },
    "inference": {
        "supported": "INFERENCIA: sostenida (APPROVE)",
        "minor-issues": "INFERENCIA: sostenida con observaciones menores (APPROVE_MINOR)",
        "honest-decline": "INFERENCIA: declinacion honesta (APPROVE_DECLINE) - el sistema hizo lo correcto",
        "insufficient": "INFERENCIA: insuficiente (REVISE)",
        "not-evaluated": "INFERENCIA: sin veredicto",
    },
    "technical": {
        "completed": "TECNICO: completada con recuperacion semantica",
        "degraded": "TECNICO: DEGRADADA - termino, pero la recuperacion no fue semantica",
        "failed": "TECNICO: fallo",
        "cancelled": "TECNICO: cancelada",
    },
}


# Corrector ADR-0079: por que thread_parent_matches_run es null — tres estados, cada uno con su glosa
_PARENT_MATCH_NULL_GLOSS = {
    "no-parent": "no aplica (turno raiz)",
    "no-snapshot": "no verificable: el snapshot no viajo (ver thread_context_skipped_reason)",
    "parent-without-frozen-record": "no verificable: el padre no tiene registro congelado",
}
# Corrector ADR-0079: por que precedent_citations esta vacio (la letra solo se emite con padre 'closed')
_PRECEDENT_EMPTY_GLOSS = {
    "no-parent": "sin turno previo",
    "parent-not-closed": "el padre no esta cerrado - no es precedente (ADR-0053) aunque su snapshot viaje",
    "parent-without-frozen-record": "el padre no tiene registro congelado (failed/cancelled)",
}


def _thread_label(record, thread):
    """'T-<run_no de la raiz>' leido UNICAMENTE de thread.root_run_no (costura T5: runs._root_run_no lo sella
    en todo turno); si no consta, se DECLARA — jamas se infiere del run_id, del parent_run_no ni del turn_no.
    Corrector ADR-0079: se quitaron los dos fallbacks que inferian (turn_kind 'root' -> record.run_no, llave
    que el registro no lleva en la raiz; turn_no 2 -> parent_run_no): un PDF que promete no inferir no
    tiene ramas que infieren."""
    root_no = thread.get("root_run_no")
    if root_no is not None:
        return f"T-{root_no}"
    return f"T-? (el run_no de la raiz no consta en el registro; thread_id={thread.get('thread_id')})"


def _section_investigacion(pdf, record):
    """ADR-0079: la investigacion a la que pertenece la corrida + precedente en LETRAS + origen."""
    _h(pdf, "INVESTIGACION (ADR-0079) - turnos encadenados; el turno previo es PRECEDENTE, jamas evidencia")
    if "thread" not in record:
        _p(pdf, f"[?] {_NOT_INSTRUMENTED}", style="I", size=8)
    else:
        thread = record.get("thread") or {}
        if not thread:
            _p(pdf, "thread: null declarado - la corrida no pertenece a ninguna investigacion", style="I", size=8)
        else:
            kind = thread.get("turn_kind")
            _p(pdf, f"investigacion {_thread_label(record, thread)}   |   turno {thread.get('turn_no')} - "
                    f"{_TURN_KIND_GLOSS.get(kind, f'clase fuera de tabla: {kind}')}", style="B", size=9)
            if thread.get("parent_run_id"):
                _p(pdf, f"padre: corrida #{thread.get('parent_run_no')} ({thread.get('parent_run_id')}) en estado "
                        f"{thread.get('parent_state')}", size=8)
            else:
                _p(pdf, "padre: ninguno (turno raiz)", size=8)
            if thread.get("root_question_id"):
                _p(pdf, f"pregunta raiz (apunte): {thread.get('root_question_id')}", size=8)
        # el snapshot que el modelo vio: se declara si viajo o por que no (nunca se imprime entero)
        if "thread_context" in record:
            tc = record.get("thread_context")
            skipped = ((tc or {}).get("skipped_reason") or thread.get("thread_context_skipped_reason")
                       or thread.get("skipped_reason") or record.get("thread_context_skipped_reason"))
            if tc is None:
                _p(pdf, f"thread_context: null declarado - razon: {skipped or 'no consta'}", size=8)
            else:
                ks = tc.get("kill_switch") or {}
                hc = tc.get("human_comments")
                # T5 (integrador, ADR-0079 C): runs.py persiste human_comments como SOBRE {items, n_total,
                # n_included, truncated, class 'atestiguada'}; una lista cruda se tolera (lectura ADR-0074);
                # cualquier otra forma = 'no consta' (jamas se cuenta lo que no se sabe contar).
                if isinstance(hc, dict):
                    n_hc = f"{hc.get('n_included', '?')} de {hc.get('n_total', '?')}"
                    hc_trunc = bool(hc.get("truncated"))
                elif isinstance(hc, list):
                    n_hc, hc_trunc = str(len(hc)), bool(tc.get("truncated"))
                else:
                    n_hc, hc_trunc = "no consta", False
                _p(pdf, f"thread_context: viajo al modelo ({tc.get('bytes', '?')} bytes, snapshot {tc.get('snapshot_at')})"
                        f" - comentarios humanos: {n_hc}"
                        f"{' (TRUNCADOS al tope)' if hc_trunc else ''}"
                        f" - kill_switch WITT_THREAD_CONTEXT={ks.get('WITT_THREAD_CONTEXT', 'no consta')}"
                        + (f" - {skipped}" if skipped else "")
                        + (" - PADRE PRE-ADR-0079 (raiz virtual)" if tc.get("parent_pre_adr_0079") else ""),
                   size=8)
                _p(pdf, "excluido del snapshot por regla: valores y notas de calificacion (enmascarados por "
                        "solicitante, jamas promediados)", size=7)
        if "thread_parent_matches_run" in record:
            m = record.get("thread_parent_matches_run")
            if m is None:
                # corrector ADR-0079: null NO es 'turno raiz' — el estado dice por que es null (un hijo con
                # kill-switch o con padre failed tambien trae null); estado ausente = no consta
                st = record.get("thread_parent_matches_run_state")
                glosa = _PARENT_MATCH_NULL_GLOSS.get(st, f"estado fuera de tabla: {st}" if st else "estado no consta")
                _p(pdf, f"identidad del padre: {glosa} - null declarado", size=8)
            else:
                _p(pdf, "identidad del padre: " + ("COINCIDE - el snapshot que vio el modelo es el registro "
                                                    "congelado del padre (sha256 sobre el blob sin frozen_at/closed_by)"
                                                    if m else
                                                    "NO COINCIDE - el snapshot NO corresponde al registro del padre"),
                   style="B" if m is False else "", size=8)
    # precedente en LETRAS: la serie que no puede producir numeros
    if "precedent_citations" not in record:
        _p(pdf, f"precedente citado: [?] {_NOT_INSTRUMENTED}", style="I", size=8)
    else:
        pcs = record.get("precedent_citations") or []
        if not pcs:
            pst = record.get("precedent_citations_state")
            razon = _PRECEDENT_EMPTY_GLOSS.get(pst, f"estado fuera de tabla: {pst}" if pst else "razon no consta")
            _p(pdf, f"precedente citado: ninguno (lista vacia declarada - {razon})", size=8)
        for c in pcs:
            who = f"turno {c.get('turn_no')} - " if c.get("turn_no") is not None else ""
            no = f"corrida #{c.get('run_no')}" if c.get("run_no") is not None else c.get("run_id")
            _p(pdf, f"  [{c.get('l')}] {c.get('kind') or 'precedente'}: {who}{no} - {c.get('question')}"
                    f"  -  NO ADMISIBLE COMO EVIDENCIA", size=8)
    # origen
    if "origin" not in record:
        _p(pdf, f"origen: [?] {_NOT_INSTRUMENTED}", style="I", size=8)
    else:
        og = record.get("origin") or {}
        val = og.get("value") if isinstance(og, dict) else og
        src = og.get("source") if isinstance(og, dict) else "no consta"
        gloss = _ORIGIN_GLOSS.get(val, f"fuera del enum ({val}) - declarado, la corrida se creo igual")
        _p(pdf, f"origen: {val if val is not None else 'null'} - {gloss}   |   fuente (al encolar): {src}", size=8)
        sae = og.get("source_at_execution") if isinstance(og, dict) else None
        if isinstance(sae, dict) and sae.get("same_value_as_column") is False:
            # corrector ADR-0079: el entorno al ejecutar derivaba OTRO valor — se declara, no se funde en `source`
            _p(pdf, f"  al ejecutar el entorno derivaba {sae.get('value')!r} ({sae.get('source')}) - "
                    "distinto de la columna; la columna manda", size=7)
    _rule(pdf)


def _section_ejes(pdf, record):
    """ADR-0079 G: los cuatro ejes del episodio en palabras (clase derived-at-freeze, tabla de mapeo)."""
    _h(pdf, "EJES DEL EPISODIO (ADR-0079) - derivados al congelar, cuatro ejes, jamas un enum unico")
    if "episode_axes" not in record:
        _p(pdf, f"[?] {_NOT_INSTRUMENTED}", style="I", size=8)
        _rule(pdf)
        return
    axes = record.get("episode_axes")
    if not axes:
        _p(pdf, "episode_axes: null declarado - los ejes no se derivaron", style="I", size=8)
        _rule(pdf)
        return
    for axis in ("world", "inference", "technical"):
        v = axes.get(axis)
        words = _AXIS_WORDS[axis].get(v)
        if words is None:
            words = (f"{axis.upper()}: {'null declarado' if v is None else f'LITERAL FUERA DE TABLA: {v}'}")
        _p(pdf, "  - " + words, size=8)
    prov = axes.get("provenance") or {}
    gates = prov.get("human_gates") or {}
    turn = prov.get("turn") or {}
    _p(pdf, f"  - PROCEDENCIA: origen {prov.get('origin') if prov.get('origin') is not None else 'null'}   |   "
            f"plan declarado: {'SI' if gates.get('plan_declared') else 'NO'}   |   "
            f"cerrada por humano: {'SI' if gates.get('closed') else 'NO'}   |   "
            f"turno {turn.get('turn_no')} ({turn.get('turn_kind')}) de {turn.get('thread_id')}", size=8)
    _p(pdf, "clase: derived-at-freeze - cada eje sale de una tabla de mapeo declarada (decision_state x "
            "absence_kind x veredicto x estado x modo de recuperacion); no es medicion nueva", size=7)
    _rule(pdf)


# --- ADR-0082: CONSEJO DE CRITERIO — tres estados por llave (registro < 1.11 -> NO INSTRUMENTADO; state declarado; valor) ---
_NOT_INSTRUMENTED_1_11 = "NO INSTRUMENTADO (contrato < 1.11) - el registro nacio antes de ADR-0082; no se rellena"
_COUNCIL_STATE_GLOSS = {
    "applicable": "el consejo JUZGO la cobertura (ronda valida, cuorum alcanzado)",
    "incomplete": "ronda INCOMPLETA (k/N < cuorum) - la compuerta la cuenta como NO competente, se declara",
    "skipped-by-human": "el humano SALTO el consejo con razon - ledger vacio declarado",
    "not-applicable (no-ledger)": "sin ledger del consejo (corrida sin plan o plan sin ronda 1 aprobada)",
    "disabled (kill-switch WITT_COUNCIL=0)": "APAGADO por kill-switch - camino sin consejo, componente informativo",
    "pre-adr-0082": "plan anterior al ADR - sin consejo, declarado",
}
_COVERAGE_GLOSS = {
    "covered": "cubierto", "partial": "PARCIAL (cuenta como sin cubrir)", "uncovered": "SIN CUBRIR",
    "not-judged": "SIN JUZGAR (cuenta como sin cubrir)", "covered-by-attestation": "cubierto por ATESTIGUACION humana (no evidencia)",
    "discarded": "descartado por el humano",
}
_AFTER_SEARCH_GLOSS = {
    "retrieved-for": "se RECUPERO evidencia para su directiva (medicion estructural, no juicio)",
    "still-uncovered": "directiva compilada, nada admitido", "not-searched": "sin directiva (no se busco)",
    "covered-pre": "ya cubierto antes de buscar",
}


def _council_state_gloss(state):
    if state in _COUNCIL_STATE_GLOSS:
        return _COUNCIL_STATE_GLOSS[state]
    if isinstance(state, str) and state.startswith("errored ("):
        return "la ronda del consejo FALLO - declarado, la corrida siguio sin cobertura"
    if isinstance(state, str) and state.startswith("not-requested ("):
        return "la ronda 1 NO se pidio para este plan (compuerta de gasto declarada)"
    return f"estado fuera de tabla: {state}"


def _section_consejo(pdf, record):
    """ADR-0082 (K.m): la seccion 'CONSEJO DE CRITERIO' nace con el bloque frozen.council. Tres estados: llave ausente
    (registro < 1.11) -> NO INSTRUMENTADO; `state` declarado sin rondas (kill-switch, no-ledger, not-requested, skip,
    errored); valor (membresia, ledger con decisiones, cobertura pre/post, rondas n/N, catalog_sha, costo r1/r2/r3).
    El consejo NUNCA escribe la respuesta: aqui solo se imprimen sus requisitos, decisiones humanas y coberturas."""
    _h(pdf, "CONSEJO DE CRITERIO (ADR-0082) - requisitos de informacion y cobertura; JAMAS escribe la respuesta")
    if "council" not in record:
        _p(pdf, f"[?] {_NOT_INSTRUMENTED_1_11}", style="I", size=8)
        _rule(pdf)
        return
    c = record.get("council")
    if not isinstance(c, dict):
        _p(pdf, "council: null declarado - la corrida no congelo consejo", style="I", size=8)
        _rule(pdf)
        return
    state = c.get("state")
    _p(pdf, f"estado: {state} - {_council_state_gloss(state)}"
            + (f"   |   razon: {c.get('state_reason')}" if c.get("state_reason") else ""), style="B", size=9)
    ledger = c.get("ledger") if isinstance(c.get("ledger"), dict) else None
    rounds = [r for r in (c.get("rounds") or []) if isinstance(r, dict)]
    if ledger is None and not rounds:
        # estado declarado SIN rondas: nada mas que imprimir salvo la version y la membresia
        _p(pdf, f"membresia {c.get('membership_version')} - {c.get('n_members')} miembros"
                f"{' (full-council)' if c.get('full_council') else ''}   |   catalog_sha "
                f"{str(c.get('catalog_sha') or 'no consta')[:16]}...   |   kill_switch WITT_COUNCIL="
                f"{((c.get('kill_switch') or {}).get('WITT_COUNCIL') or 'unset')}", size=8)
        _rule(pdf)
        return
    model = c.get("model") or {}
    _p(pdf, f"membresia {c.get('membership_version')} ({c.get('membership_source')}) - {c.get('n_members')} miembros"
            f"{' (full-council)' if c.get('full_council') else ''} - cuorum {c.get('quorum_required')}   |   modelo "
            f"{model.get('requested')} ({model.get('source')}; effort {model.get('effort') or 'no enviado'})", size=8)
    pcm = c.get("plan_catalog_matches_run")
    _p(pdf, f"catalog_sha (al ejecutar) {str(c.get('catalog_sha') or 'no consta')[:16]}...   |   fichas del plan "
            + ("COINCIDEN" if pcm is True else "NO COINCIDEN - las fichas cambiaron entre plan y corrida" if pcm is False
               else "no verificable (plan sin catalog_sha)"), size=8)
    # ledger: decisiones humanas
    if ledger is not None:
        kn = ledger.get("knowledge_now") or {}
        _p(pdf, f"LEDGER {ledger.get('state')} - {ledger.get('n_requirements')} requisitos: {ledger.get('n_kept')} keep, "
                f"{ledger.get('n_discarded')} discard, {ledger.get('n_attested')} aportados, {ledger.get('n_pending')} pendientes, "
                f"{ledger.get('n_hard_rule')} hard-rule (causal-pruner)   |   aprobado por {ledger.get('approved_by') or 'nadie'}"
                f"{' (autor del plan)' if ledger.get('approved_by_is_author') else ''}"
                + (f"   |   saltado por {ledger.get('skipped_by')}: {ledger.get('skip_reason')}" if ledger.get("skipped_by") else ""),
           style="B", size=8)
        if kn.get("present"):
            _p(pdf, f"QUE SABES AHORA (ATESTIGUADO por {kn.get('by')}, {kn.get('chars')} chars"
                    f"{', RECORTADO a 600 en el registro' if kn.get('truncated') else ''}; NO es evidencia): {kn.get('text')}",
               style="I", size=8)
        cov = c.get("coverage") or {}
        pre = cov.get("pre_search") if isinstance(cov.get("pre_search"), dict) else {}
        post = cov.get("post_search") if isinstance(cov.get("post_search"), dict) else {}
        after = cov.get("after_search") if isinstance(cov.get("after_search"), dict) else {}
        pre_by = {b["requirement_id"]: b for b in (pre.get("by_requirement") or []) if isinstance(b, dict)}
        post_by = {b["requirement_id"]: b for b in (post.get("by_requirement") or []) if isinstance(b, dict)}
        after_by = {b["requirement_id"]: b for b in (after.get("by_requirement") or []) if isinstance(b, dict)}
        for r in ledger.get("requirements") or []:
            rid = r.get("requirement_id")
            head = (f"  [{r.get('priority')}] {rid}: {r.get('gap')}   -   {r.get('source_family')}/{r.get('evidence_kind')}"
                    f"   -   pedido por {r.get('n_requested_by')} de {r.get('n_members')}   -   decision {r.get('decision')}"
                    f" ({r.get('decided_by') or 'sin decidir'})")
            if r.get("hard_rule_gate"):
                head += "   -   HARD-RULE §7.1 (decision humana explicita)"
            if r.get("priority_downgraded_from"):
                head += f"   -   degradado de {r['priority_downgraded_from']} (exploratorio)"
            if r.get("harness_state") and r.get("harness_state") != "satisfiable":
                head += f"   -   {r['harness_state']} (no gatea, contado)"
            _p(pdf, head, size=7)
            if r.get("decision_reason"):
                _p(pdf, f"      razon del humano: {r['decision_reason']}", size=7)
            if r.get("attested_text"):
                _p(pdf, f"      ATESTIGUADO ({r.get('attested_chars')} chars{', recortado a 600' if r.get('attested_text_truncated') else ''}; "
                        f"no es evidencia): {r['attested_text']}", style="I", size=7)
            pb, qb, ab = pre_by.get(rid), post_by.get(rid), after_by.get(rid)
            if pb or qb or ab:
                partes = []
                if pb:
                    partes.append(f"pre-busqueda {pb.get('coverage_final')} ({_COVERAGE_GLOSS.get(pb.get('coverage_final'), '?')}; "
                                  f"{pb.get('n_valid_votes')} votos validos, {pb.get('n_annulled_votes')} anulados)")
                if ab and ab.get("state"):
                    partes.append(f"tras buscar: {ab['state']} ({_AFTER_SEARCH_GLOSS.get(ab['state'], '?')}"
                                  + (f", {ab.get('n_items_retrieved')} items" if ab.get("n_items_retrieved") else "") + ")")
                if qb:
                    partes.append(f"post-busqueda {qb.get('coverage_final')} ({qb.get('n_valid_votes')} votos validos)")
                _p(pdf, "      cobertura: " + "   |   ".join(partes), size=7)
                for v in (pb or {}).get("votes") or []:
                    if v.get("annulled"):
                        _p(pdf, f"      voto ANULADO de {v.get('agent')}: {v.get('annul_reason')} "
                                f"{v.get('hallucinated_evidence_ids') or ''}", style="B", size=7)
        for f in ledger.get("flags") or []:
            _p(pdf, f"  BANDERA §7 (gate humano) {f.get('kind')}: {f.get('statement')}   -   emitida por "
                    f"{', '.join(f.get('emitted_by') or [])}", style="B", size=7)
        if pre:
            _p(pdf, f"must: total {pre.get('must_total')} | SIN CUBRIR {pre.get('must_uncovered')} (uncovered {pre.get('must_uncovered_strict')}"
                    f" + partial {pre.get('must_partial')} + sin juzgar {pre.get('must_not_judged')}) | atestiguados {pre.get('must_attested')}"
                    f" | descartados {pre.get('must_discarded')} | no satisfacibles por el harness {pre.get('must_unsatisfiable')} (no gatean, E1)"
                    f" | votos alucinados {pre.get('n_hallucinated_votes')}   -   clase: {pre.get('class')}", size=7)
        elif isinstance(cov.get("pre_search"), dict):
            _p(pdf, f"cobertura pre-busqueda: {cov['pre_search'].get('state')}", size=7)
        if post and post.get("state") == "judged":
            _p(pdf, f"post-busqueda (r3 sobre {len((post.get('r3') or {}).get('members') or [])} duenos): must SIN CUBRIR "
                    f"{post.get('must_uncovered')}   -   INFORMATIVA (jamas re-gatea)", size=7)
        elif isinstance(cov.get("post_search"), dict):
            _p(pdf, f"post-busqueda: {cov['post_search'].get('state')}", size=7)
        d = c.get("directives") or []
        _p(pdf, f"directivas de busqueda compiladas por CODIGO: {len(d)} ({c.get('directives_state')})"
                + (f" -> familias {sorted({x.get('family') for x in d})}" if d else "")
                + (f"   |   excluidas {len(c.get('directives_excluded') or [])}" if c.get("directives_excluded") else ""), size=7)
    # rondas n/N y costo
    for r in rounds:
        u = r.get("usage") or {}
        cache = f" | cache creation {u.get('cache_creation')} / read {u.get('cache_read')}" if isinstance(u, dict) and ("cache_creation" in u or "cache_read" in u) else ""
        tag = " (COPIADA del plan: gastada ANTES de encolar)" if r.get("copied_from_plan_id") else ""
        _p(pdf, f"ronda {r.get('round')} ({r.get('kind')}, fase {r.get('phase')}){tag}: {r.get('n_valid')}/{r.get('n_members')} validos"
                f" - estado {r.get('state')} - invocados {r.get('n_invoked')} - errored {r.get('n_errored')} - timeout {r.get('n_timeout')}"
                f" - {r.get('elapsed_s')} s - tokens in {u.get('in') if isinstance(u, dict) else '?'} / out "
                f"{u.get('out') if isinstance(u, dict) else '?'}{cache} [MEDICION]", size=7)
    for s in c.get("rounds_skipped") or []:
        _p(pdf, f"ronda {s.get('round')} NO corrio: {s.get('reason')}", size=7)
    cache = c.get("cache") or {}
    if cache:
        _p(pdf, f"cache de prompt: {'activa' if cache.get('enabled') else 'apagada'} (ttl {cache.get('ttl')}) - hit_ratio_r2 "
                f"{cache.get('hit_ratio_r2') if cache.get('hit_ratio_r2') is not None else 'no medido'} [MEDICION]", size=7)
    _rule(pdf)


class _Doc(FPDF):
    def header(self):
        self.set_font("Helvetica", "B", 9)
        self.cell(0, 5, "WITT x ORGANOGENESIS - REGISTRO CONGELADO (exportacion de servidor)",
                  new_x="LMARGIN", new_y="NEXT", align="C")
        self.ln(1)

    def footer(self):
        self.set_y(-12)
        self.set_font("Helvetica", "I", 7)
        self.cell(0, 4, f"pagina {self.page_no()}/{{nb}}", align="C")


def _rule(pdf):
    pdf.ln(1)
    pdf.set_draw_color(0)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
    pdf.ln(2)


def _h(pdf, text):
    pdf.set_font("Helvetica", "B", 10)
    pdf.multi_cell(0, 5, _t(text), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)


def _p(pdf, text, style="", size=9):
    pdf.set_font("Helvetica", style, size)
    pdf.multi_cell(0, 4.6, _t(text), new_x="LMARGIN", new_y="NEXT")


def _band(pdf, text, double=False):
    """Banda con BORDE y palabras completas (regla 2: nada de textura; la palabra impresa siempre)."""
    pdf.set_font("Helvetica", "B", 9.5)
    pdf.multi_cell(0, 6, _t(text), border=1, new_x="LMARGIN", new_y="NEXT", align="C")
    if double:
        y = pdf.get_y() + 0.6
        pdf.line(pdf.l_margin, y, pdf.w - pdf.r_margin, y)
        pdf.ln(1.4)
    pdf.ln(1.2)
    pdf.set_font("Helvetica", "", 9)


def build_pdf(record, compress=True):
    """El PDF (bytes) desde el registro congelado — jamás desde la página. Identidad primero."""
    if record.get("question_matches_run") is False:
        raise ValueError("identidad rota: el registro no corresponde a la pregunta de la corrida "
                         "(question_matches_run=false) - la hoja no se dibuja y el PDF tampoco (ADR-0044)")

    pdf = _Doc(format="A4")
    pdf.set_compression(compress)
    pdf.alias_nb_pages()
    pdf.set_auto_page_break(auto=True, margin=16)
    pdf.add_page()

    # --- identidad de la corrida -----------------------------------------------------------------
    _p(pdf, f"run_id: {record.get('run_id')}   -   contrato de render: "
            f"{record.get('render_contract_version')}", size=8)
    _p(pdf, f"PREGUNTA: {record.get('question')}", style="B", size=11)
    frozen_at = record.get("frozen_at")
    if frozen_at:
        _p(pdf, f"CERRADA por {record.get('closed_by')} el {frozen_at} - es precedente consultable", size=8)
    else:
        _p(pdf, "SIN CERRAR - esperando cierre: NO es precedente todavia", size=8)
    _rule(pdf)

    # --- 1. el estado epistemico ARRIBA ----------------------------------------------------------
    rs = record.get("retrieval_summary")
    if rs is None:
        _band(pdf, _MODE_BAND["not-measured"])
    else:
        mode = rs.get("mode")
        texto = _MODE_BAND.get(mode, f"LITERAL DESCONOCIDO: {mode} - se trata como DEGRADADO por regla")
        extra = f" ({rs.get('retrievals')} recuperaciones, agregacion {rs.get('aggregation')})"
        _band(pdf, texto + extra)

    ds = record.get("decision_state") or {}
    st = ds.get("state")
    _p(pdf, f"decision_state: {st} - {_STATE_GLOSS.get(st, 'estado fuera del vocabulario conocido')}"
            f"   |   may_answer_now: {'SI' if ds.get('may_answer_now') else 'NO'}"
            f"   |   may_propose_now: {'SI' if ds.get('may_propose_now') else 'NO'}")
    _rule(pdf)

    # --- 1b. los ejes del episodio (ADR-0079 G) van con el estado, ARRIBA de la respuesta -----------
    _section_ejes(pdf, record)

    # --- 2. auditoria adversarial (siempre; el estado sano tambien se declara) --------------------
    audit = record.get("audit") or {}
    verdict = audit.get("verdict")
    _h(pdf, "REVISION ADVERSARIAL - obligatoria en el 100% de las corridas")
    if audit:
        objetada = verdict == "REVISE"
        _band(pdf, (f"OBJETADA - {audit.get('tally', {}).get('REVISE', '?')} REVISE de "
                    f"{audit.get('n_valid')} validos - hallazgo negativo de primera clase") if objetada
              else f"APROBADA ({verdict}) - {audit.get('n_valid')} jueces validos",
              double=objetada)
        _p(pdf, f"vocabulario: {audit.get('source_vocabulary')}", size=8)
        for row in audit.get("panel", []):
            if row.get("status") == "errored":
                _p(pdf, f"  - {row.get('reviewer')} ({row.get('lens')}): ERRORED - excluido, "
                        f"jamas fabricado", size=8)
            else:
                caught = f" | atrapo: {row.get('caught')}" if row.get("caught") else ""
                _p(pdf, f"  - {row.get('reviewer')} ({row.get('lens')}): {row.get('verdict')}{caught}",
                   size=8)
    else:
        _band(pdf, "REQUERIDA Y PENDIENTE - sin veredicto registrado")

    # --- 2b. ciclo de revision (ADR-0067): nada se borra ------------------------------------------
    rev = record.get("revision") or {}
    if rev.get("performed"):
        _p(pdf, f"HUBO CICLO DE REVISION ({rev.get('cap')} de max {rev.get('cap')}, ADR-0067): "
                f"veredicto inicial {rev.get('initial_verdict')} -> final {rev.get('final_verdict')}. "
                f"La tabla de arriba es la ronda 1 (post-revision); la ronda 0 persiste abajo - "
                f"NADA SE BORRA.", style="B")
        ai = record.get("answer_initial") or {}
        _p(pdf, f"RONDA 0 - respuesta inicial (SUPERADA, no borrada): {ai.get('direct_answer')}",
           style="I", size=8)
        auditi = record.get("audit_initial") or {}
        for row in auditi.get("panel", []):
            if "verdict" in row:
                _p(pdf, f"  - [ronda 0] {row.get('reviewer')} ({row.get('lens')}): {row.get('verdict')}",
                   size=8)
    elif rev.get("skipped_reason"):
        _p(pdf, f"[?] REVISE sin ciclo de revision - {rev['skipped_reason']}", size=8)
    _rule(pdf)

    # --- 3. la respuesta (despues del estado - el orden de lectura es el orden de confianza) ------
    _h(pdf, "RESPUESTA")
    ans = record.get("answer") or {}
    if verdict == "REVISE" or (ans.get("gap_flags") or []):
        _band(pdf, "RESPONDE CON HUECO DECLARADO - leer los huecos junto con la respuesta")
    _p(pdf, ans.get("direct_answer") or "(sin respuesta registrada)", size=10)
    ak = ans.get("absence_kind")
    if ak and ak != "not-applicable":
        _p(pdf, f"absence_kind: {ak} - {_ABSENCE_GLOSS.get(ak, ak)}", style="B", size=8)
    _rule(pdf)

    # --- 4. confianza con su procedencia -----------------------------------------------------------
    _h(pdf, "CONFIANZA DECLARADA - autoreporte del modelo, NO medicion")
    conf = record.get("confidence")
    if conf:
        if conf.get("state") == "value" and conf.get("final") is not None:
            _p(pdf, f"final: {conf['final']}   |   procedencia: "
                    f"{_SOURCE_GLOSS.get(conf.get('source'), conf.get('source') or 'no consta')}")
        else:
            _p(pdf, "SIN MEDIR - absent-not-calibratable: el modelo la omitio (declarado, "
                    "no un null silencioso)", style="B")
        partes = [f"pass1: {conf.get('pass1')}"]
        if conf.get("pass2") is not None:
            partes += [f"pass2: {conf.get('pass2')}", f"delta: {conf.get('delta')}"]
        if conf.get("revision") is not None:
            partes.append(f"revision: {conf.get('revision')}")
        if conf.get("pass1_inline") is not None:
            partes.append(f"cross-check in-line: {conf.get('pass1_inline')} (el instrumento previo "
                          f"persiste, ADR-0065)")
        _p(pdf, "   |   ".join(partes), size=8)
        subs = conf.get("by_subclaim") or {}
        for k, v in subs.items():
            _p(pdf, f"  - {k}: {v}", size=8)
        if subs:
            _p(pdf, "el agregado NO sustituye el perfil - no se imprime promedio (SS5)", size=7)
    else:
        _p(pdf, "[?] el bloque confidence no viaja en este registro (contrato pre-1.1)", style="I")
    fb = record.get("fallback") or {}
    if fb:
        _p(pdf, f"fallback.trigger: {fb.get('trigger')}"
                + (f" (tau={((fb.get('fb_meta') or {}).get('tau'))})" if fb.get("fb_meta") else ""), size=8)
        # ADR-0080 (corrector): QUIEN decidio el trigger — la compuerta (codigo), lo estructural o la regla legada por
        # confianza (kill-switch) — y el veredicto de la compuerta; ausente = registro anterior al contrato 1.9
        fbm = fb.get("fb_meta") or {}
        comp_meta = fbm.get("competence") if isinstance(fbm.get("competence"), dict) else None
        if comp_meta is not None or "trigger_decided_by" in fbm:
            _p(pdf, f"  decidido por: {fbm.get('trigger_decided_by') or 'NO DECLARADO'}"
                    + (f" | competence: {comp_meta.get('competent')} ({comp_meta.get('decision_source')})"
                       if comp_meta else ""), size=7)
        else:
            _p(pdf, "  [?] compuerta de competencia NO INSTRUMENTADA (contrato < 1.9)", style="I", size=7)
    sl = record.get("search_ledger")
    if isinstance(sl, dict):
        _p(pdf, f"search_ledger: state {sl.get('state')} | rondas {sl.get('n_rounds')} / cap {sl.get('cap')}"
                + (f" | stop {sl.get('stop_reason')}" if sl.get("stop_reason") else "")
                + (f" | familias {(sl.get('plan') or {}).get('families_source')}"
                   if isinstance(sl.get("plan"), dict) and sl["plan"].get("families_source") else ""), size=7)
    _rule(pdf)

    # --- 4b. el consejo de criterio (ADR-0082) — NACE con el bloque (regla del brief §18) --------------
    _section_consejo(pdf, record)

    # --- 5. evidencia, huecos, alternativas --------------------------------------------------------
    _h(pdf, "EVIDENCIA CITADA (numeros = evidencia; letras reservadas a precedente)")
    cits = record.get("citations") or []
    if cits:
        for c in cits:
            # ADR-0080 (corrector): el peldano de soporte alcanzado por la cita cuando el registro lo trae (>= 1.9)
            support = (f"  [soporte: {c.get('support_state')}]" if "support_state" in c
                       else "  [soporte: NO INSTRUMENTADO (contrato < 1.9)]")
            _p(pdf, f"  [{c.get('n')}] {c.get('kind')}: {c.get('id')}"
                    + (f" - {c.get('note')}" if c.get("note") else "") + support, size=8)
    else:
        _p(pdf, "[?] citas tipadas no constan (contrato pre-1.1) - no se rellena", style="I", size=8)
    gaps = ans.get("gap_flags") or []
    if gaps:
        _h(pdf, "HUECOS DECLARADOS")
        for g in gaps:
            _p(pdf, f"  ! {g}", size=8)
    alts = record.get("alternatives_considered")
    _h(pdf, "ALTERNATIVAS CONSIDERADAS")
    if alts is None:
        _p(pdf, "[?] AUSENTE - hueco del sistema (distinto de 'no habia alternativas')", style="I", size=8)
    elif not alts:
        _p(pdf, "se consideraron y NO hubo alternativas viables (lista vacia declarada)", size=8)
    else:
        for a in alts:
            _p(pdf, f"  - {a}", size=8)
    _rule(pdf)

    # --- 5b. la investigacion (ADR-0079): turnos, precedente en LETRAS, origen ----------------------
    _section_investigacion(pdf, record)

    # --- 6. costo + consenso + pie ------------------------------------------------------------------
    tu = record.get("token_usage")
    if tu:
        _p(pdf, f"COSTO: {tu.get('input_tokens'):,} entrada / {tu.get('output_tokens'):,} salida "
                f"[MEDICION] - USD {tu.get('estimated_cost_usd')} [PROYECCION: los tokens son medicion, "
                f"los dolares no]", size=8)
    cons = record.get("consensus")
    if cons:
        _p(pdf, f"CONSENSO DE CALIFICACION: {cons.get('received')} de {cons.get('invited')} - "
                f"{'ABIERTO' if cons.get('open') else 'completo'} (conteo, jamas promedio - los "
                f"valores individuales viven en la app)", size=8)
    _rule(pdf)
    ident = record.get("bundle_identity") or {}
    _p(pdf, f"Exportado del registro congelado el "
            f"{datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds')} - "
            f"identidad sha256: {str(ident.get('sha256', 'no consta'))[:16]}...  -  "
            f"Esta exportacion de servidor es EL UNICO canal autorizado para sacar una respuesta de "
            f"la app: copiar y pegar desde la pantalla pierde el estado epistemico. Texto normalizado "
            f"a latin-1 para el PDF (saneo declarado).", style="I", size=7)

    out = pdf.output()
    return bytes(out)


def build_pdf_from_json(path, compress=True):
    return build_pdf(json.loads(open(path, encoding="utf-8").read()), compress=compress)
