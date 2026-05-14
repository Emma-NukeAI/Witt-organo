#!/usr/bin/env python3
"""
morpheus_emit_json.py — Emit morpheus.json files for cross-verdict pairing.

Reads scenario data (embedded for the pronephros contractility cascade,
matching SCENARIOS in reports/visualizacion-cascada-pronefro-v2.html) and
emits morpheus.json files in SIMULATION_OUTPUTS_DB/<hypothesis_id>/ per the
schema in skills/custom/squidiff-in-silico-gate/references/morpheus-pairing.md.

This is the J.1 patch (2026-05-14): the morpheus-4d-viz skill currently produces
HTML only; this helper bridges existing v2 visualizations to Squidiff Mode 3
cross-verdict without modifying prior session outputs (ADR-0002 preservation).

Usage:
    python scripts/morpheus_emit_json.py
    python scripts/morpheus_emit_json.py --topic pronephros_contractility --root SIMULATION_OUTPUTS_DB/

Future invocation pattern: when morpheus-4d-viz itself emits JSON natively
(planned patch), this script can be deprecated. Until then it is the operational
contract for cross-verdict pairing.
"""
from __future__ import annotations
import argparse
import json
import os
import sys
from pathlib import Path
from typing import Dict, List


# Scenario data — derived from reports/visualizacion-cascada-pronefro-v2.html SCENARIOS
# Phenotype class mapping consistent with v2.0.1 13-scenario re-analysis.
SCENARIOS: List[Dict] = [
    {"id": "control",  "label": "Control (WT)",            "etapa": 0,
     "decouple": "na",   "confidence": 1.00,
     "pheno_class": "normal",     "pheno": "Pronefro bilateral simetrico"},
    {"id": "1A-hipo",  "label": "1A - stage-specific - hipo", "etapa": 1,
     "decouple": "pass", "confidence": 0.78,
     "pheno_class": "dislocated", "pheno": "Dislocacion - longitud normal"},
    {"id": "1A-KO",    "label": "1A - stage-specific - KO",   "etapa": 1,
     "decouple": "pass", "confidence": 0.74,
     "pheno_class": "asymmetric", "pheno": "Asimetria - truncamiento"},
    {"id": "1B-hipo",  "label": "1B - persistente - hipo",    "etapa": 1,
     "decouple": "partial", "confidence": 0.62,
     "pheno_class": "dislocated", "pheno": "Dislocado + malformado"},
    {"id": "1B-KO",    "label": "1B - persistente - KO",      "etapa": 1,
     "decouple": "fail", "confidence": 0.55,
     "pheno_class": "catastrophic", "pheno": "Catastrofico - sin pronefro"},
    {"id": "2A-hipo",  "label": "2A - stage-specific - hipo", "etapa": 2,
     "decouple": "pass", "confidence": 0.80,
     "pheno_class": "compressed", "pheno": "Comprimido - lumen formado"},
    {"id": "2A-KO",    "label": "2A - stage-specific - KO",   "etapa": 2,
     "decouple": "pass", "confidence": 0.75,
     "pheno_class": "cyst_amorphous", "pheno": "Quiste compacto - cluster"},
    {"id": "2B-hipo",  "label": "2B - persistente - hipo",    "etapa": 2,
     "decouple": "partial", "confidence": 0.66,
     "pheno_class": "dislocated", "pheno": "Comprimido + falla polaridad"},
    {"id": "2B-KO",    "label": "2B - persistente - KO",      "etapa": 2,
     "decouple": "pass-paradigm", "confidence": 0.58,
     "pheno_class": "preserved_foci", "pheno": "Sin tubulo - foci wt1a+"},
    {"id": "3A-hipo",  "label": "3A - stage-specific - hipo", "etapa": 3,
     "decouple": "pass", "confidence": 0.82,
     "pheno_class": "normal", "pheno": "Pared bumpy - longitud OK"},
    {"id": "3A-KO",    "label": "3A - stage-specific - KO",   "etapa": 3,
     "decouple": "pass", "confidence": 0.78,
     "pheno_class": "swiss_cheese", "pheno": "Swiss cheese - identidad bulk OK"},
    {"id": "3B-hipo",  "label": "3B - persistente - hipo",    "etapa": 3,
     "decouple": "partial", "confidence": 0.65,
     "pheno_class": "normal", "pheno": "Pared mal polarizada"},
    {"id": "3B-KO",    "label": "3B - persistente - KO",      "etapa": 3,
     "decouple": "pass", "confidence": 0.62,
     "pheno_class": "masa_sin_arquitectura", "pheno": "Masa sin arquitectura"},
]


def assess_severity(scenario: Dict) -> str:
    """Map scenario etapa+dose to severity."""
    if scenario["id"] == "control":
        return "baseline"
    if "-KO" in scenario["id"] and "B-" in scenario["id"]:
        return "extreme"
    if "-KO" in scenario["id"]:
        return "extreme" if scenario["pheno_class"] in ("swiss_cheese", "catastrophic", "masa_sin_arquitectura") else "moderate"
    return "moderate"


def scenario_to_morpheus_json(scenario: Dict, topic: str) -> Dict:
    """Translate a scenario dict to a morpheus.json structure."""
    return {
        "hypothesis_id": f"{topic}_{scenario['id']}",
        "scenario_label": scenario["id"],
        "phenotype_severity": assess_severity(scenario),
        "phenotype_class": scenario["pheno_class"],
        "morphology_decouple": scenario["decouple"],
        "confidence": scenario["confidence"],
        "notes": scenario["pheno"],
        "morpheus_version": "manual-1.0"
    }


def main():
    parser = argparse.ArgumentParser(description="Emit morpheus.json files for cross-verdict pairing.")
    parser.add_argument("--topic", default="pronephros_contractility",
                        help="Topic slug for hypothesis_id (default: pronephros_contractility)")
    parser.add_argument("--root", default="SIMULATION_OUTPUTS_DB",
                        help="Root directory for SIMULATION_OUTPUTS_DB (default: SIMULATION_OUTPUTS_DB)")
    args = parser.parse_args()

    root = Path(args.root)
    written = []
    for sc in SCENARIOS:
        hypothesis_id = f"{args.topic}_{sc['id']}"
        out_dir = root / hypothesis_id
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "morpheus.json"
        payload = scenario_to_morpheus_json(sc, args.topic)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        written.append(str(out_path))

    print(f"Wrote {len(written)} morpheus.json files under {root}/")
    for p in written:
        print(f"  {p}")


if __name__ == "__main__":
    main()
