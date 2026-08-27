"""
Standalone demo: shows what structured_report_from_state produces for two
realistic clinical cases without requiring the full plan_checker engine.
Run from the backend/ directory:  python demo_report.py
"""
from __future__ import annotations
import sys
import types

# ── Minimal engine mock so plan_checker_agents imports cleanly ────────────────

_engine = types.ModuleType("plan_checker")

def _mock_normalize_site(site: str) -> str:
    return site.strip().title()

def _mock_online_edit_contour_groups(state):
    return state.get("_mock_contour_groups", {})

def _mock_coerce_findings(raw):
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        return raw.get("findings", [])
    return []

def _mock_filter_fp(state, findings):
    return findings

_engine.normalize_site = _mock_normalize_site
_engine.infer_treatment_site = lambda path, plan: plan.get("_site", "Unknown")
_engine.build_plan_setup = lambda plan: plan.get("plan_setup", {})
_engine.build_contour_data = lambda plan: plan.get("contour_data", {})
_engine.build_imrt_data = lambda plan: plan.get("imrt_data", {})
_engine._online_edit_contour_groups = _mock_online_edit_contour_groups
_engine._coerce_findings = _mock_coerce_findings
_engine._filter_known_false_positive_findings = _mock_filter_fp
_engine.AZURE_SETTINGS = {}
_engine.AUDIT_RULES_DIR = "."
_engine._AUDIT_RULES_CACHE = {}
_engine.load_all_plans = lambda p: []

sys.modules["plan_checker"] = _engine

# Patch directory creation so the module loads without real folders
from unittest.mock import patch, MagicMock
import pathlib
_real_mkdir = pathlib.Path.mkdir

def _safe_mkdir(self, *a, **kw):
    kw.setdefault("exist_ok", True)
    try:
        _real_mkdir(self, *a, **kw)
    except Exception:
        pass

pathlib.Path.mkdir = _safe_mkdir

# ── Now import the actual agent module ───────────────────────────────────────
import importlib, os
os.chdir(os.path.dirname(__file__))

with patch("builtins.open", MagicMock(side_effect=FileNotFoundError)):
    pass  # suppress missing prompt-file warnings during import

import plan_checker_agents as agents


# ── Demo state builder ────────────────────────────────────────────────────────

def make_finding(severity, item, observed, expected, evidence=None, action=None):
    return {
        "severity": severity,
        "item": item,
        "observed": observed,
        "expected": expected,
        "evidence": evidence or item,
        "action": action or "",
    }


# ─────────────────────────────────────────────────────────────────────────────
# CASE 1 — Prostate VMAT, Unity CMM
# ─────────────────────────────────────────────────────────────────────────────

PROSTATE_STATE = {
    "treatment_site": "Prostate",
    "case_id": "Prostate_MR_20250812",

    "plan_setup": {
        "plan_name": "Prostate_MR_20250812",
        "machine": "Unity MR-Linac",
        "total_dose": 7800,           # cGy → will be converted to 78 Gy
        "total_fx": 39,
        "rx_name": "78 Gy / 39 fx — 2.00 Gy/fx VMAT SIB",
        "image_taken_date": "2025-08-12",
        "compression": "No compression — supine, knee support",
        "adaptation_mode": "CMM",
        "source_target": "CTV_Prostate",
    },

    "case_summary": (
        "72-year-old male with intermediate-risk prostate adenocarcinoma (Gleason 3+4, "
        "PSA 8.2). Referred for definitive radiotherapy. No prior pelvic surgery. "
        "Moderate rectal gas on simulation CT; MR-guidance selected for daily online "
        "adaptation."
    ),

    "contour_data": {
        "structures": [
            {"name": "CTV_Prostate",  "volume": 42.1},
            {"name": "CTV_SV",        "volume": 18.6},
            {"name": "PTV_High",      "volume": 68.3,  "formula": "CTV_Prostate + CTV_SV expanded 5 mm (3 mm posterior)"},
            {"name": "PTV_Elective",  "volume": 312.5, "formula": "Pelvic nodal CTV expanded 7 mm isotropically"},
        ]
    },

    "oar_analysis": {
        "within_artring_3cm":    ["Rectum", "Bladder", "BowelBag"],
        "overlap_75_isl":        ["Rectum", "Bladder"],
        "active_optimization":   ["Rectum", "Bladder", "BowelBag", "FemoralHead_L", "FemoralHead_R"],
    },

    "coverage_summary": (
        "Reference plan: PTV_High V95% = 97.3%, PTV_Elective V95% = 95.8%. "
        "Rectal V70Gy = 14.2% (constraint ≤ 20%)."
    ),
    "overlap_summary": (
        "Rectum overlaps PTV_High by 4.1 cc (posterior wall contact). "
        "Bladder overlaps PTV_High by 7.8 cc (trigone region)."
    ),
    "optimization_challenges": (
        "Posterior PTV_High coverage vs. rectal anterior wall constraint; "
        "seminal vesicle tip coverage limited by rectal proximity; "
        "daily bladder filling variation managed via CMM online adaptation"
    ),

    "critic_results": {
        "findings": [
            make_finding(
                "WARNING",
                "Rectal V70Gy near constraint limit",
                "V70Gy = 18.9%",
                "≤ 20%",
                evidence="Rectum DVH",
            ),
        ]
    },

    "summary_notes": [],
    "_mock_contour_groups": {"target": ["CTV_Prostate", "CTV_SV"], "ed": ["Rectum", "Bladder"], "other": []},
}


# ─────────────────────────────────────────────────────────────────────────────
# CASE 2 — Pancreas SBRT, Unity MM (monitoring only, no online adaptation)
# ─────────────────────────────────────────────────────────────────────────────

PANCREAS_STATE = {
    "treatment_site": "Pancreas",
    "case_id": "Pancreas_SBRT_20250814",

    "plan_setup": {
        "plan_name": "Pancreas_SBRT_20250814",
        "machine": "Unity MR-Linac",
        "total_dose": 4000,           # cGy → 40 Gy
        "total_fx": 5,
        "rx_name": "40 Gy / 5 fx — 8.00 Gy/fx SBRT",
        "image_taken_date": "2025-08-14",
        "compression": "Abdominal compression (15 mmHg) — respiratory motion < 5 mm",
        "adaptation_mode": "MM",
    },

    "case_summary": (
        "67-year-old female with unresectable pancreatic head adenocarcinoma, post "
        "4 cycles FOLFIRINOX. CA19-9 trending down. SBRT planned for local consolidation. "
        "Duodenal proximity is the primary dose-limiting constraint."
    ),

    "contour_data": {
        "structures": [
            {"name": "GTV_Pancreas",  "volume": 18.4},
            {"name": "ITV_Pancreas",  "volume": 24.7},
            {"name": "PTV_SBRT",      "volume": 41.2,  "formula": "ITV_Pancreas expanded 3 mm isotropically"},
        ]
    },

    "oar_analysis": {
        "within_artring_3cm":  ["Duodenum", "Stomach", "SmallBowel"],
        "overlap_75_isl":      ["Duodenum"],
        "active_optimization": ["Duodenum", "Stomach", "SmallBowel", "SpinalCord", "Liver", "Kidney_R"],
    },

    "coverage_summary": (
        "Reference plan: PTV_SBRT D95% = 38.6 Gy (96.5% of 40 Gy). "
        "Duodenum D0.03cc = 31.2 Gy (constraint ≤ 33 Gy)."
    ),
    "overlap_summary": (
        "Duodenum abuts PTV_SBRT over a 1.8 cm interface — zero geometric gap. "
        "Stomach posterior wall within 4 mm of PTV superior margin."
    ),
    "optimization_challenges": (
        "Duodenum constraint limits achievable PTV_SBRT coverage to ~96%; "
        "gradient falloff toward stomach competes with superior PTV coverage; "
        "abdominal compression reduces but does not eliminate residual respiratory motion"
    ),

    "critic_results": {
        "findings": [
            make_finding(
                "CRITICAL",
                "PTV_SBRT coverage below 95% threshold",
                "D95% = 38.6 Gy (96.5%) — borderline",
                "D95% ≥ 95% of prescription (38.0 Gy)",
                evidence="PTV_SBRT DVH",
                action="Verify clinical acceptability with treating physician before approval",
            ),
            make_finding(
                "WARNING",
                "Duodenum D0.03cc approaching limit",
                "31.2 Gy",
                "≤ 33 Gy (AAPM TG-101)",
                evidence="Duodenum DVH",
            ),
        ]
    },

    "summary_notes": [],
    "_mock_contour_groups": {},
}


# ── Render and print ──────────────────────────────────────────────────────────

SEPARATOR = "\n" + "═" * 72 + "\n"

print(SEPARATOR)
print("  DEMO OUTPUT — RT Plan Checker V8 Structured Report")
print(SEPARATOR)

for label, state in [
    ("CASE 1 — Prostate VMAT / Unity CMM", PROSTATE_STATE),
    ("CASE 2 — Pancreas SBRT / Unity MM",  PANCREAS_STATE),
]:
    print(f"\n{'─' * 72}")
    print(f"  {label}")
    print(f"{'─' * 72}\n")
    print(agents.structured_report_from_state(state))
    print()

print(SEPARATOR)
print("  End of demo")
print(SEPARATOR)
