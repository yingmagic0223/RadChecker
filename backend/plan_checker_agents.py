"""
RT Plan Checker V8 compatibility backend.

This module preserves the Flask API used by the V6 web shell while delegating
actual auditing to the newer UnityExtractor plan_checker.py engine. The engine
loads site-specific V8 audit rules from ./audit_rules and memory from ./Memory.
"""

from __future__ import annotations

import copy
import datetime as _dt
import json
import os
import re
from collections import OrderedDict
from pathlib import Path
from typing import Any, Dict, List, Optional

from openai import AzureOpenAI

import plan_checker as engine

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "reports"
UPLOAD_DIR = BASE_DIR / "uploads"
AUDIT_RULES_DIR = BASE_DIR / "audit_rules"
MEMORY_DIR = BASE_DIR / "Memory"
PROMPTS_DIR = BASE_DIR / "prompts"

for _path in (OUTPUT_DIR, UPLOAD_DIR, AUDIT_RULES_DIR, MEMORY_DIR, PROMPTS_DIR):
    _path.mkdir(parents=True, exist_ok=True)

# Point the UnityExtractor engine at the bundled V8 rule files.
engine.AUDIT_RULES_DIR = AUDIT_RULES_DIR
try:
    engine._AUDIT_RULES_CACHE.clear()
except Exception:
    pass

AZURE_ENDPOINT = engine.AZURE_SETTINGS.get("azure_endpoint", "https://ying-zhang-utsw-eastus.openai.azure.com/")
AZURE_DEPLOYMENT = engine.AZURE_SETTINGS.get("azure_deployment", "gpt-5.4")
AZURE_API_VERSION = engine.AZURE_SETTINGS.get("openai_api_version", "2024-12-01-preview")
MODEL = AZURE_DEPLOYMENT

_client: Optional[AzureOpenAI] = None


def _api_key() -> str:
    return os.getenv("AZURE_OPENAI_API_KEY", "") or engine.AZURE_SETTINGS.get("api_key", "")


def _get_client() -> AzureOpenAI:
    global _client
    if _client is None:
        key = _api_key()
        if not key:
            raise RuntimeError("AZURE_OPENAI_API_KEY is not set. Start with start_server.ps1 or set the environment variable.")
        _client = AzureOpenAI(
            azure_endpoint=AZURE_ENDPOINT,
            azure_deployment=AZURE_DEPLOYMENT,
            api_version=AZURE_API_VERSION,
            api_key=key,
        )
    return _client


CHAT_PROMPT_FILE = PROMPTS_DIR / "chat_system.txt"
MEMORY_PROMPT_FILE = PROMPTS_DIR / "memory_system.txt"

_PROMPT_SPECS = OrderedDict([
    ("pancreas_rules", {
        "label": "Pancreas Audit Rules",
        "group_name": "Pancreas",
        "path": AUDIT_RULES_DIR / "Pancreas.md",
        "note": "V8 site rule file used for Pancreas contour, plan-parameter, and optimization agents.",
    }),
    ("prostate_rules", {
        "label": "Prostate Audit Rules",
        "group_name": "Prostate",
        "path": AUDIT_RULES_DIR / "Prostate.md",
        "note": "V8 site rule file used for Prostate contour, plan-parameter, and optimization agents.",
    }),
    ("pancreas_memory", {
        "label": "Pancreas Memory Summary",
        "group_name": "Pancreas Memory",
        "path": MEMORY_DIR / "pancreas_plan_memory_summary.v4.json",
        "note": "Complete bundled cohort memory. V8 loads the full file without application-side character truncation.",
    }),
    ("prostate_memory", {
        "label": "Prostate Memory Summary",
        "group_name": "Prostate Memory",
        "path": MEMORY_DIR / "prostate_plan_memory_summary.v4.json",
        "note": "Complete bundled cohort memory. V8 loads the full file without application-side character truncation.",
    }),
    ("chat", {
        "label": "Physicist Chat",
        "group_name": "Chat",
        "path": CHAT_PROMPT_FILE,
        "note": "System prompt for the post-audit chat assistant.",
    }),
    ("memory", {
        "label": "Memory Agent",
        "group_name": "Memory Q&A",
        "path": MEMORY_PROMPT_FILE,
        "note": "System prompt for direct memory: queries.",
    }),
])
PROMPT_KEYS = list(_PROMPT_SPECS.keys())


def load_text(path: Path) -> str:
    return Path(path).read_text(encoding="utf-8")


def _read_spec_text(key: str) -> str:
    spec = _PROMPT_SPECS[key]
    path = Path(spec["path"])
    return path.read_text(encoding="utf-8") if path.exists() else ""


_DEFAULT_PROMPT_TEXTS = {key: _read_spec_text(key) for key in PROMPT_KEYS}


def _combined_memory_text() -> str:
    """Return both complete site memories without application-side clipping."""
    chunks = []
    for key, label in (("pancreas_memory", "PANCREAS"), ("prostate_memory", "PROSTATE")):
        text = _read_spec_text(key)
        chunks.append(f"## {label} MEMORY\n{text}")
    return "\n\n".join(chunks)


SYSTEM_PROMPT = "RT Plan Checker V8 uses site-specific audit_rules/*.md loaded dynamically per plan."
MEMORY_TEXT = _combined_memory_text()


def _build_prompt_store() -> Dict[str, Dict[str, Any]]:
    store: Dict[str, Dict[str, Any]] = {}
    for key, spec in _PROMPT_SPECS.items():
        text = _read_spec_text(key)
        store[key] = {
            "label": spec["label"],
            "group_name": spec.get("group_name", ""),
            "system": text,
            "modified": text != _DEFAULT_PROMPT_TEXTS.get(key, ""),
            "note": spec.get("note", ""),
        }
    return store


_PROMPTS: Dict[str, Dict[str, Any]] = {}


def _refresh_prompt_store() -> None:
    global MEMORY_TEXT
    fresh = _build_prompt_store()
    _PROMPTS.clear()
    _PROMPTS.update(fresh)
    MEMORY_TEXT = _combined_memory_text()


_refresh_prompt_store()


def get_prompts() -> Dict[str, Dict[str, Any]]:
    _refresh_prompt_store()
    return copy.deepcopy(_PROMPTS)


def _after_prompt_write(key: str) -> None:
    if key.endswith("_rules"):
        try:
            engine._AUDIT_RULES_CACHE.clear()
        except Exception:
            pass
    _refresh_prompt_store()


def update_prompt(key: str, field: str, new_text: str) -> None:
    if key not in _PROMPT_SPECS:
        raise KeyError(key)
    if field != "system":
        raise KeyError(field)
    Path(_PROMPT_SPECS[key]["path"]).write_text(new_text, encoding="utf-8")
    _after_prompt_write(key)


def reset_prompt(key: str) -> None:
    if key not in _PROMPT_SPECS:
        raise KeyError(key)
    Path(_PROMPT_SPECS[key]["path"]).write_text(_DEFAULT_PROMPT_TEXTS.get(key, ""), encoding="utf-8")
    _after_prompt_write(key)


def reset_all_prompts() -> None:
    for key in PROMPT_KEYS:
        reset_prompt(key)


def _clinical_focaldata(plan: Dict[str, Any]) -> Dict[str, Any]:
    focal = plan.get("clinical_focaldata")
    return focal if isinstance(focal, dict) else plan


def load_all_plans(path: str | Path) -> List[Dict[str, Any]]:
    return engine.load_all_plans(Path(path))


def _first_present(*values: Any, default: Any = "-") -> Any:
    for value in values:
        if value not in (None, "", [], {}):
            return value
    return default


def plan_summary(plan: Dict[str, Any]) -> Dict[str, Any]:
    focal = _clinical_focaldata(plan)
    basic = focal.get("basic_info", {}) if isinstance(focal.get("basic_info"), dict) else {}
    rx = focal.get("prescription_normalization", {}) if isinstance(focal.get("prescription_normalization"), dict) else {}
    site = engine.infer_treatment_site(Path("uploaded_plan.json"), plan)
    return {
        "plan_name": _first_present(basic.get("plan_name"), plan.get("Plan"), plan.get("Name"), default="-"),
        "site": site,
        "machine": _first_present(basic.get("machine"), default="-"),
        "total_dose": _first_present(basic.get("total_dose"), default="-"),
        "total_fx": _first_present(basic.get("total_fx"), default="-"),
        "rx_name": _first_present(basic.get("rx_name"), default="-"),
        "ptv": _first_present(basic.get("ptv"), basic.get("ptv_name"), default="-"),
        "date": _first_present(basic.get("image_taken_date"), plan.get("Last Modified"), default="-"),
        "approved": plan.get("Approved", None),
        "signed_by": plan.get("Signed By", ""),
        "cover_pct": _first_present(rx.get("to_cover_percent"), default="-"),
    }


def plan_to_text(plan: Dict[str, Any]) -> str:
    return json.dumps(plan, indent=2, ensure_ascii=False)


def plan_chat_context(plan: Dict[str, Any]) -> str:
    sections = {
        "plan_setup": engine.build_plan_setup(plan),
        "contour_data": engine.build_contour_data(plan),
        "imrt_data": engine.build_imrt_data(plan),
    }
    return json.dumps(sections, indent=2, ensure_ascii=False)


def _safe_filename(*parts: Any) -> str:
    raw = "_".join(str(part) for part in parts if part is not None and str(part).strip())
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", raw).strip("._")
    return (cleaned or "plan_check_report")[:160]


def _format_dose_gy(value: Any) -> str:
    try:
        dose = float(str(value).replace("cGy", "").replace("Gy", "").strip())
        if dose > 100:
            dose = dose / 100.0
        return f"{dose:g}"
    except Exception:
        return str(value or "?")


def _find_setup_value(setup: Dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in setup and setup[key] not in (None, ""):
            return setup[key]
    for value in setup.values():
        if isinstance(value, dict):
            nested = _find_setup_value(value, *keys)
            if nested not in (None, ""):
                return nested
    return ""


def _collect_findings(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    findings = []
    try:
        findings = engine._coerce_findings(state.get("critic_results", {}))
    except Exception:
        findings = []
    if not findings:
        for key in ("audit_results", "param_audit_results", "imrt_audit_results"):
            try:
                findings.extend(engine._coerce_findings(state.get(key, {})))
            except Exception:
                pass
    try:
        findings = engine._filter_known_false_positive_findings(state, findings)
    except Exception:
        pass
    return findings


def _clean(value: Any, fallback: str = "-") -> str:
    text = str(value if value not in (None, "") else fallback)
    return " ".join(text.replace("|", "/").split())


def _issue_line(prefix: str, index: int, finding: Dict[str, Any], severity: str) -> str:
    title = _clean(finding.get("item"), "Finding")
    location = _clean(finding.get("evidence") or finding.get("item"), "Plan")
    found = _clean(finding.get("observed"), "See detail")
    expected = _clean(finding.get("expected") or finding.get("memory_check"), "See V8 memory/rules")
    base = f"{prefix}{index} | {title} | {location} | Found: {found} | Expected: {expected}"
    if severity == "CRITICAL":
        impact = _clean(finding.get("action"), "")
        if impact:
            return f"{base} | Impact: {impact}"
    return base


def _online_contour_groups(state: Dict[str, Any]) -> Dict[str, List[str]]:
    try:
        groups = engine._online_edit_contour_groups(state)
    except Exception:
        groups = {}
    return {
        "target": list(groups.get("target", []) or []),
        "ed": list(groups.get("ed", []) or []),
        "other": list(groups.get("other", []) or []),
    }


def _inline_contour_name(name: Any) -> str:
    return _clean(name).replace("`", "'")


def _format_contour_group_lines(label: str, names: List[str], chunk_size: int = 4) -> List[str]:
    cleaned = [_inline_contour_name(name) for name in names if _inline_contour_name(name)]
    if not cleaned:
        return []
    lines = [f"- **{label} ({len(cleaned)}):**"]
    for start in range(0, len(cleaned), chunk_size):
        chunk = cleaned[start:start + chunk_size]
        lines.append("  - " + ", ".join(f"`{name}`" for name in chunk))
    return lines


def _format_plan_notes_section(state: Dict[str, Any], site: str) -> str:
    """Legacy helper retained for callers outside structured_report_from_state."""
    notes = [str(n).strip() for n in state.get("summary_notes", []) if str(n).strip()]
    if not notes:
        notes = [f"{site} plan audited with site-specific V8 rules and bundled memory."]
    return "\n".join(f"- {_clean(note)}" for note in notes)


def _format_online_contours_section(state: Dict[str, Any]) -> str:
    """Legacy helper retained for callers outside structured_report_from_state."""
    groups = _online_contour_groups(state)
    lines: List[str] = []
    if any(groups.values()):
        lines.extend(_format_contour_group_lines("Target", groups["target"]))
        lines.extend(_format_contour_group_lines("ED related", groups["ed"]))
        lines.extend(_format_contour_group_lines("Other", groups["other"]))
    else:
        lines.append("- None identified.")
    return "\n".join(lines)


# ── Section helpers for structured_report_from_state ─────────────────────────

def _sec_case_summary(state: Dict[str, Any], setup: Dict[str, Any], site: str) -> List[str]:
    """Section 1 — Case Summary (LLM-based narrative + plan identity)."""
    plan_name = _clean(
        state.get("case_id") or _find_setup_value(setup, "plan_name", "Plan", "Name"), "Plan"
    )
    machine = _clean(_find_setup_value(setup, "machine", "treatment_unit", "linac"), "-")
    total_dose = _format_dose_gy(
        _find_setup_value(setup, "total_dose", "prescription_dose", "rx_dose")
    )
    total_fx = _clean(_find_setup_value(setup, "total_fx", "fractions", "number_of_fractions"), "?")
    rx_name = _clean(_find_setup_value(setup, "rx_name", "prescription_name"), "")
    date = _clean(_find_setup_value(setup, "image_taken_date", "date", "Last Modified"), "-")

    try:
        dpf = f"{float(total_dose) / int(total_fx):.2f} Gy/fx"
    except Exception:
        dpf = ""

    lines = ["## 1. Case Summary"]
    lines.append(f"- **Plan**: {plan_name}  |  **Machine**: {machine}  |  **Site**: {site}")

    rx_line = f"- **Prescription**: {total_dose} Gy / {total_fx} fractions"
    if dpf:
        rx_line += f"  ({dpf})"
    if rx_name and rx_name not in ("-", ""):
        rx_line += f"  —  {rx_name}"
    lines.append(rx_line)

    if date and date not in ("-", ""):
        lines.append(f"- **Date**: {date}")

    # AI-generated case summary: prefer dedicated field, fall back to first summary note
    ai_text = _clean(
        state.get("case_summary") or state.get("ai_case_summary") or "", ""
    )
    if not ai_text:
        notes = [str(n).strip() for n in (state.get("summary_notes") or []) if str(n).strip()]
        ai_text = notes[0] if notes else ""
    if ai_text:
        lines.append(f"- **Clinical Summary**: {ai_text}")

    return lines


def _sec_setup_motion(state: Dict[str, Any], setup: Dict[str, Any]) -> List[str]:
    """Section 2 — Setup / Motion Considerations (compression; Unity MM vs CMM)."""
    lines = ["## 2. Setup / Motion Considerations"]

    # Compression
    compression = _clean(
        _find_setup_value(
            setup, "compression", "compression_device", "belly_board", "immobilization"
        ) or state.get("compression", ""),
        "",
    )
    if compression and compression not in ("-", ""):
        lines.append(f"- **Compression**: {compression}")
    else:
        lines.append("- **Compression**: Not documented")

    # Unity adaptation mode (MM = monitor only; CMM = continuous monitoring + adaptation)
    adapt_mode = _clean(
        _find_setup_value(
            setup, "adaptation_mode", "unity_mode", "plan_mode", "art_mode", "adapt_mode"
        ) or state.get("adaptation_mode", ""),
        "",
    )
    if adapt_mode and adapt_mode not in ("-", ""):
        mode_upper = adapt_mode.upper()
        lines.append(f"- **Unity Adaptation**: {mode_upper}")
        if any(tok in mode_upper for tok in ("CMM", "CONTINUOUS", "ADAPT_TO_SHAPE", "ATS", "ONLINE")):
            src = _clean(
                _find_setup_value(
                    setup, "source_target", "cmm_source", "reference_target",
                    "cmm_target", "base_structure",
                ) or state.get("cmm_source_target", ""),
                "",
            )
            if src and src not in ("-", ""):
                lines.append(f"  - **CMM Source Target**: `{src}`")
    else:
        lines.append("- **Unity Adaptation Mode**: Not specified")

    return lines


def _sec_targets(state: Dict[str, Any], setup: Dict[str, Any]) -> List[str]:
    """Section 3 — Targets: CTV/ITV (Unity-type) and PTVs with expansion formulas."""
    lines = ["## 3. Targets"]

    contour_data = state.get("contour_data") or {}
    all_structures: List[Dict[str, Any]] = (
        contour_data.get("structures")
        or contour_data.get("structure_list")
        or []
    )

    ctv_tags = ("CTV", "ITV", "GTV")
    ctvs = [s for s in all_structures if any(t in str(s.get("name", "")).upper() for t in ctv_tags)]
    ptvs = [s for s in all_structures if "PTV" in str(s.get("name", "")).upper()]

    # ── CTV / ITV ────────────────────────────────────────────────────────────
    lines.append("- **CTV / ITV** (Unity-type targets):")
    if ctvs:
        for s in ctvs:
            name = _clean(s.get("name", ""))
            vol = s.get("volume")
            vol_str = f"  —  {vol:.1f} cc" if vol is not None else ""
            lines.append(f"  - `{name}`{vol_str}")
    else:
        primary_ctv = _clean(_find_setup_value(setup, "ctv", "ctv_name", "target_ctv"), "")
        if primary_ctv and primary_ctv not in ("-", ""):
            lines.append(f"  - `{primary_ctv}`")
        else:
            lines.append("  - Not specified")

    # ── PTVs ─────────────────────────────────────────────────────────────────
    lines.append("- **PTVs** (expansion formulas in natural language):")
    if ptvs:
        for s in ptvs:
            name = _clean(s.get("name", ""))
            formula = _clean(
                s.get("formula") or s.get("description") or s.get("margin_description") or "", ""
            )
            margin = s.get("margin") or s.get("expansion_mm")
            if formula and formula not in ("-", ""):
                lines.append(f"  - `{name}`: {formula}")
            elif margin is not None:
                try:
                    lines.append(f"  - `{name}`: {float(margin):.0f} mm isotropic expansion from CTV/ITV")
                except Exception:
                    lines.append(f"  - `{name}`: {margin} expansion from CTV/ITV")
            else:
                vol = s.get("volume")
                vol_str = f"  ({vol:.1f} cc)" if vol is not None else ""
                lines.append(f"  - `{name}`{vol_str}")
    else:
        primary_ptv = _clean(_find_setup_value(setup, "ptv", "ptv_name", "target_ptv"), "")
        if primary_ptv and primary_ptv not in ("-", ""):
            lines.append(f"  - `{primary_ptv}`")
        else:
            lines.append("  - Not specified")

    return lines


def _sec_oars(state: Dict[str, Any]) -> List[str]:
    """
    Section 4 — OARs selected by three clinical criteria:
      a) within 3 cm ARTring
      b) overlap with 75% ISL
      c) actively used in optimization (source structures, not margin structures)
    """
    lines = ["## 4. OARs"]

    oar_analysis: Dict[str, Any] = (
        state.get("oar_analysis") or state.get("oar_categories") or {}
    )

    artring_oars: List[str] = list(
        oar_analysis.get("within_artring_3cm") or oar_analysis.get("artring_3cm") or []
    )
    isl_oars: List[str] = list(
        oar_analysis.get("overlap_75_isl") or oar_analysis.get("isl_75pct") or []
    )
    opt_oars: List[str] = list(
        oar_analysis.get("active_optimization") or oar_analysis.get("optimization_structures") or []
    )

    # Fallback: use online-edit contour groups when engine OAR analysis is absent
    if not any([artring_oars, isl_oars, opt_oars]):
        try:
            groups = engine._online_edit_contour_groups(state)
            ed_oars = list(groups.get("ed", []) or [])
            other_oars = list(groups.get("other", []) or [])
            opt_oars = ed_oars + other_oars
        except Exception:
            pass

    lines.append("- **Within 3 cm ARTring**:")
    if artring_oars:
        for oar in artring_oars:
            lines.append(f"  - `{_inline_contour_name(oar)}`")
    else:
        lines.append("  - Not available (requires engine OAR spatial analysis)")

    lines.append("- **Overlapping with 75% ISL**:")
    if isl_oars:
        for oar in isl_oars:
            lines.append(f"  - `{_inline_contour_name(oar)}`")
    else:
        lines.append("  - Not available")

    lines.append("- **Active in Optimization** (source structures, excluding margin structures):")
    if opt_oars:
        for oar in opt_oars:
            lines.append(f"  - `{_inline_contour_name(oar)}`")
    else:
        lines.append("  - Not specified")

    return lines


def _sec_planning_goals(state: Dict[str, Any]) -> List[str]:
    """
    Section 5 — Planning Goals / Challenges (AI-based reference plan summary):
      1) Coverage of reference plan
      2) OAR / PTV overlap situation
      3) Optimization challenges
    """
    lines = ["## 5. Planning Goals / Challenges"]

    # Prefer dedicated engine fields; fall back to summary_notes (skip note[0] used in section 1)
    coverage = _clean(
        state.get("coverage_summary") or state.get("plan_coverage_summary") or "", ""
    )
    overlap = _clean(
        state.get("overlap_summary") or state.get("oar_ptv_overlap_summary") or "", ""
    )
    challenges = _clean(
        state.get("optimization_challenges") or state.get("planning_challenges") or "", ""
    )

    notes = [str(n).strip() for n in (state.get("summary_notes") or []) if str(n).strip()]
    remaining = list(notes[1:])  # notes[0] already consumed in section 1

    lines.append("- **Coverage of Reference Plan**:")
    if coverage:
        lines.append(f"  - {coverage}")
    elif remaining:
        lines.append(f"  - {remaining.pop(0)}")
    else:
        lines.append("  - See audit findings for coverage assessment")

    lines.append("- **OAR / PTV Overlap Situation**:")
    if overlap:
        lines.append(f"  - {overlap}")
    elif remaining:
        lines.append(f"  - {remaining.pop(0)}")
    else:
        lines.append("  - Refer to OARs section above for relevant structures")

    lines.append("- **Optimization Challenges**:")
    if challenges:
        for item in (p.strip() for p in challenges.split(";") if p.strip()):
            lines.append(f"  - {item}")
    elif remaining:
        for note in remaining:
            lines.append(f"  - {note}")
    else:
        lines.append("  - See critical and warning findings below")

    return lines


# ── Main structured report ────────────────────────────────────────────────────

def structured_report_from_state(state: Dict[str, Any]) -> str:
    setup = state.get("plan_setup", {}) or {}
    site = engine.normalize_site(state.get("treatment_site", ""))
    plan_name = _clean(
        state.get("case_id") or _find_setup_value(setup, "plan_name", "Plan", "Name"), "Plan"
    )
    machine = _clean(_find_setup_value(setup, "machine", "treatment_unit"), "-")
    total_dose = _format_dose_gy(
        _find_setup_value(setup, "total_dose", "prescription_dose", "rx_dose")
    )
    total_fx = _clean(_find_setup_value(setup, "total_fx", "fractions", "fx"), "?")
    date = _clean(_find_setup_value(setup, "image_taken_date", "date", "Last Modified"), "-")

    findings = _collect_findings(state)
    critical = [f for f in findings if str(f.get("severity", "")).upper() == "CRITICAL"]
    warnings  = [f for f in findings if str(f.get("severity", "")).upper() == "WARNING"]

    if critical:
        verdict   = "FAIL"
        rationale = f"V8 {site} audit found {len(critical)} critical finding(s) requiring correction before approval."
    elif warnings:
        verdict   = "PASS WITH MANUAL REVIEW"
        rationale = f"V8 {site} audit found {len(warnings)} warning(s) needing physicist review."
    else:
        verdict   = "PASS"
        rationale = f"V8 {site} audit found no critical or warning findings."

    lines: List[str] = [
        f"PLAN: {plan_name} | {machine} | {total_dose} Gy / {total_fx} fx | {date}",
        f"VERDICT: {verdict}",
        f"RATIONALE: {rationale}",
        "",
    ]

    # ── Sections 1 – 5 ───────────────────────────────────────────────────────
    for section_lines in (
        _sec_case_summary(state, setup, site),
        _sec_setup_motion(state, setup),
        _sec_targets(state, setup),
        _sec_oars(state),
        _sec_planning_goals(state),
    ):
        lines.extend(section_lines)
        lines.append("")

    # ── Audit findings ────────────────────────────────────────────────────────
    lines.append("## Audit Findings")
    lines.append("")
    lines.append("CRITICAL:")
    if critical:
        lines.extend(
            _issue_line("C", i, finding, "CRITICAL")
            for i, finding in enumerate(critical, 1)
        )
    else:
        lines.append("None")

    lines += ["", "WARNINGS:"]
    if warnings:
        lines.extend(
            _issue_line("W", i, finding, "WARNING")
            for i, finding in enumerate(warnings, 1)
        )
    else:
        lines.append("None")

    passed = (
        "Checks without listed critical/warning findings are omitted from the concise V8 summary; "
        "see the detail report for INFO items and plan notes."
    )
    lines += ["", f"PASSED: {passed}"]
    return "\n".join(lines)


def _state_debug_json(state: Dict[str, Any]) -> str:
    keep = {
        "treatment_site": state.get("treatment_site"),
        "case_id": state.get("case_id"),
        "site_memory_path": state.get("site_memory_path"),
        "audit_results": state.get("audit_results"),
        "param_audit_results": state.get("param_audit_results"),
        "imrt_audit_results": state.get("imrt_audit_results"),
        "critic_results": state.get("critic_results"),
        "summary_notes": state.get("summary_notes"),
        "online_contour_groups": _online_contour_groups(state),
    }
    return json.dumps(keep, indent=2, ensure_ascii=False)


def run_audit(
    plan: Dict[str, Any],
    file_stem: str = "plan",
    verbose: bool = True,
    fast_mode: bool = False,
    site_override: Optional[str] = None,
    feedback_memory: str = "",
) -> Dict[str, Any]:
    source_path = Path(f"{file_stem}.json")
    state = engine.build_plan_state(
        plan=plan,
        source_path=source_path,
        plan_index=0,
        site_override=site_override,
        memory_dir=MEMORY_DIR,
    )
    state["user_feedback_memory"] = feedback_memory or ""
    state["fast_mode"] = bool(fast_mode)

    if verbose:
        print(f"[V8] Running {state['treatment_site']} audit for {state['case_id']}", flush=True)
    app = engine.create_mrl_graph(skip_critic=bool(fast_mode))
    result_state = app.invoke(state)

    site = engine.normalize_site(result_state.get("treatment_site", state.get("treatment_site", "")))
    plan_name = str(result_state.get("case_id") or file_stem)
    native_report = result_state.get("summary_report", "")
    concise = structured_report_from_state(result_state)
    online_contour_groups = _online_contour_groups(result_state)
    online_contours_text = _format_online_contours_section(result_state)
    detail = (
        f"# Native V8 Markdown Report\n\n{native_report}\n\n"
        f"---\n\n# V8 Structured UI Summary\n\n{concise}\n"
    )
    critic_log = _state_debug_json(result_state)
    memory_text = str(result_state.get("site_memory", "") or "")
    memory_path = str(result_state.get("site_memory_path", "") or "")

    ts = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    stem = OUTPUT_DIR / _safe_filename(site, file_stem, plan_name, ts)
    concise_path = Path(str(stem) + "_REPORT.txt")
    detail_path  = Path(str(stem) + "_DETAIL.md")
    critic_path  = Path(str(stem) + "_CRITIC.json")
    concise_path.write_text(concise, encoding="utf-8")
    detail_path.write_text(detail, encoding="utf-8")
    critic_path.write_text(critic_log, encoding="utf-8")

    return {
        "concise": concise,
        "detail": detail,
        "native_report": native_report,
        "critic_notes": critic_log,
        "online_contour_groups": online_contour_groups,
        "online_contours_text": online_contours_text,
        "concise_path": str(concise_path),
        "detail_path": str(detail_path),
        "critic_path": str(critic_path),
        "plan_name": plan_name,
        "site": site,
        "plan_text": plan_to_text(plan),
        "chat_context": plan_chat_context(plan),
        "memory_text": memory_text,
        "memory_path": memory_path,
        "memory_characters_loaded": len(memory_text),
        "memory_bytes_loaded": len(memory_text.encode("utf-8")),
        "basic_info": _clinical_focaldata(plan).get("basic_info", {}),
        "v8_state": result_state,
        "fast_mode": fast_mode,
        "feedback_memory": feedback_memory or "",
    }


def query_memory(question: str) -> str:
    prompts = get_prompts()
    memory_prompt = prompts.get("memory", {}).get("system", "Answer from the supplied site memory.")
    memory = _combined_memory_text()
    response = _get_client().chat.completions.create(
        model=MODEL,
        temperature=0.1,
        max_completion_tokens=700,
        messages=[
            {"role": "system", "content": memory_prompt},
            {"role": "user", "content": f"COMPLETE SITE MEMORY:\n{memory}\n\nQUESTION:\n{question}"},
        ],
    )
    return response.choices[0].message.content.strip()
