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
# CASE 1 — Prostate SBRT SIB 45 Gy / 40 Gy in 5 fx, Unity CMM
# ─────────────────────────────────────────────────────────────────────────────

PROSTATE_STATE = {
    "treatment_site": "Prostate",
    "case_id": "Prostate_SBRT_SIB_20250820",

    "plan_setup": {
        "plan_name": "Prostate_SBRT_SIB_20250820",
        "machine": "Unity MR-Linac",
        "total_dose": 4500,           # cGy → 45 Gy (high-dose PTV level)
        "total_fx": 5,
        "rx_name": "45 Gy (PTV_High) / 40 Gy (PTV_SV) in 5 fx — SBRT SIB (9.0 / 8.0 Gy/fx)",
        "image_taken_date": "2025-08-20",
        "compression": "No compression — supine, EndoRectal balloon not used",
        "adaptation_mode": "CMM",
        "source_target": "CTV_Prostate",
    },

    "case_summary": (
        "68-year-old male with high-risk prostate adenocarcinoma (Gleason 4+4, PSA 14.6, "
        "cT2c). Referred for definitive MR-guided SBRT with simultaneous integrated boost. "
        "No prior pelvic irradiation. Full bladder / empty rectum protocol. Daily online "
        "adaptation planned via CMM to account for interfraction rectal filling variation."
    ),

    "contour_data": {
        "structures": [
            {"name": "CTV_Prostate",  "volume": 38.5},
            {"name": "CTV_SV",        "volume": 14.2},
            {"name": "PTV_High",
             "volume": 58.7,
             "formula": "CTV_Prostate expanded 3 mm (2 mm posterior) — prescribed 45 Gy / 5 fx"},
            {"name": "PTV_SV",
             "volume": 36.4,
             "formula": "CTV_SV expanded 4 mm isotropically — prescribed 40 Gy / 5 fx"},
        ]
    },

    "oar_analysis": {
        "within_artring_3cm":  ["Rectum", "Bladder", "Urethra"],
        "overlap_75_isl":      ["Rectum", "Bladder"],
        "active_optimization": ["Rectum", "Bladder", "Urethra", "FemoralHead_L", "FemoralHead_R", "PenileBulb"],
    },

    "coverage_summary": (
        "Reference plan: PTV_High D95% = 44.6 Gy (99.1%), PTV_SV D95% = 39.4 Gy (98.5%). "
        "Rectal D0.03cc = 43.8 Gy (constraint < 45 Gy); Bladder D0.03cc = 44.1 Gy."
    ),
    "overlap_summary": (
        "Rectum overlaps PTV_High by 1.8 cc (anterior rectal wall, posterior prostate). "
        "Bladder overlaps PTV_High by 5.2 cc at bladder neck / trigone. "
        "Urethra passes through PTV_High over 3.2 cm — urethral D0.1cc = 42.3 Gy."
    ),
    "optimization_challenges": (
        "Rectal max dose (D0.03cc) within 1.2 Gy of constraint at 45 Gy high-dose level; "
        "urethral dose must be balanced against posterior PTV_High coverage; "
        "SV tip coverage conflicts with rectal anterior wall sparing; "
        "CMM online adaptation critical to maintain rectal constraint on treatment days"
    ),

    "critic_results": {
        "findings": [
            make_finding(
                "WARNING",
                "Rectal D0.03cc near constraint ceiling",
                "43.8 Gy",
                "< 45 Gy",
                evidence="Rectum DVH",
            ),
            make_finding(
                "WARNING",
                "Urethral D0.1cc above institutional guideline",
                "42.3 Gy",
                "≤ 42 Gy (institutional)",
                evidence="Urethra DVH",
            ),
        ]
    },

    "summary_notes": [],
    "_mock_contour_groups": {
        "target": ["CTV_Prostate", "CTV_SV"],
        "ed": ["Rectum", "Bladder", "Urethra"],
        "other": [],
    },
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


# ─────────────────────────────────────────────────────────────────────────────
# CASE 3 — Pancreas body SBRT 50 Gy / 5 fx, Unity CMM (borderline resectable)
# ─────────────────────────────────────────────────────────────────────────────

PANCREAS2_STATE = {
    "treatment_site": "Pancreas",
    "case_id": "Pancreas_Body_SBRT_20250818",

    "plan_setup": {
        "plan_name": "Pancreas_Body_SBRT_20250818",
        "machine": "Unity MR-Linac",
        "total_dose": 5000,           # cGy → 50 Gy
        "total_fx": 5,
        "rx_name": "50 Gy / 5 fx — 10.0 Gy/fx SBRT (dose-painted SIB)",
        "image_taken_date": "2025-08-18",
        "compression": "Abdominal compression belt (20 mmHg) — residual motion ≤ 3 mm SI",
        "adaptation_mode": "CMM",
        "source_target": "GTV_Pancreas",
    },

    "case_summary": (
        "58-year-old male with borderline-resectable pancreatic body adenocarcinoma "
        "(abutting SMA < 90°). Post 6 cycles FOLFIRINOX with partial response; CA19-9 "
        "normalised. SBRT at 50 Gy / 5 fx planned as conversion therapy prior to surgical "
        "reassessment. Celiac axis and superior mesenteric artery proximity are principal "
        "dose-limiting constraints alongside stomach and colon."
    ),

    "contour_data": {
        "structures": [
            {"name": "GTV_Pancreas",  "volume": 12.8},
            {"name": "ITV_Pancreas",  "volume": 17.3},
            {"name": "PTV_High",
             "volume": 28.9,
             "formula": "ITV_Pancreas expanded 3 mm isotropically — prescribed 50 Gy / 5 fx"},
            {"name": "PTV_Low",
             "volume": 52.4,
             "formula": "ITV_Pancreas expanded 5 mm isotropically — prescribed 40 Gy / 5 fx (elective margin)"},
        ]
    },

    "oar_analysis": {
        "within_artring_3cm":  ["Stomach", "Duodenum", "SmallBowel", "Colon"],
        "overlap_75_isl":      ["Stomach", "Duodenum"],
        "active_optimization": [
            "Stomach", "Duodenum", "SmallBowel", "Colon",
            "SpinalCord", "Liver", "Kidney_L", "Kidney_R",
        ],
    },

    "coverage_summary": (
        "Reference plan: PTV_High D95% = 49.2 Gy (98.4%), PTV_Low D95% = 39.5 Gy (98.8%). "
        "Stomach D0.03cc = 32.8 Gy (constraint ≤ 35 Gy); Duodenum D0.03cc = 31.5 Gy (≤ 33 Gy). "
        "Combined liver mean = 6.4 Gy (well within tolerance)."
    ),
    "overlap_summary": (
        "Stomach posterior wall directly contacts PTV_High over a 2.4 cm² surface — "
        "minimum geometric gap of 0 mm at superior pole. "
        "Duodenum sweeps within 3 mm of PTV_High at the pancreatic neck. "
        "Left colon flexure within PTV_Low at inferior margin."
    ),
    "optimization_challenges": (
        "Stomach max dose limits PTV_High superior coverage — D95% achievable only via "
        "steep gradient (≥ 10 Gy/cm falloff required); "
        "simultaneous duodenum and stomach constraints compete at overlapping dose levels; "
        "CMM online adaptation used to re-evaluate stomach position daily before delivery; "
        "colon flexure position variable — backup plan without colon in field prepared"
    ),

    "critic_results": {
        "findings": [
            make_finding(
                "CRITICAL",
                "Stomach D0.03cc exceeds institutional limit on reference plan",
                "32.8 Gy",
                "≤ 32 Gy (institutional; AAPM TG-101 ≤ 35 Gy)",
                evidence="Stomach DVH",
                action=(
                    "Dose-paint or reduce superior PTV_High coverage; "
                    "re-optimise with tighter stomach objective before approval"
                ),
            ),
            make_finding(
                "WARNING",
                "Duodenum D0.03cc within 5% of constraint",
                "31.5 Gy",
                "≤ 33 Gy (AAPM TG-101)",
                evidence="Duodenum DVH",
            ),
            make_finding(
                "WARNING",
                "Colon D0.03cc not evaluated — structure absent on reference CT",
                "Not contoured",
                "Contour and constrain if within PTV_Low",
                evidence="Colon — structure set",
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
    ("CASE 1 — Prostate SBRT SIB 45/40 Gy / 5 fx  /  Unity CMM", PROSTATE_STATE),
    ("CASE 2 — Pancreas Head SBRT 40 Gy / 5 fx     /  Unity MM",  PANCREAS_STATE),
    ("CASE 3 — Pancreas Body SBRT 50 Gy / 5 fx     /  Unity CMM", PANCREAS2_STATE),
]:
    print(f"\n{'─' * 72}")
    print(f"  {label}")
    print(f"{'─' * 72}\n")
    print(agents.structured_report_from_state(state))
    print()

print(SEPARATOR)
print("  End of demo")
print(SEPARATOR)
