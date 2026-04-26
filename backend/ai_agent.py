import os
import json
from anthropic import Anthropic
from schemas import PlanCreate, EvaluationResult, MetricFlag

_client: Anthropic | None = None


def _get_client() -> Anthropic | None:
    global _client
    if _client is None:
        key = os.getenv("ANTHROPIC_API_KEY", "")
        if not key:
            return None
        _client = Anthropic(api_key=key)
    return _client


def _flag_label(status: str) -> str:
    return {"NORMAL": "✓ Normal", "CAUTION": "⚠ Caution", "FLAG": "✗ Flag"}[status]


def _format_metric_row(name: str, m: MetricFlag) -> str:
    direction = "+" if m.z_score > 0 else ""
    pct_range = ""
    if m.p5 is not None and m.p95 is not None:
        pct_range = f" [P5={m.p5}, P95={m.p95}]"
    return (
        f"  {name}: value={m.value}, historical mean={m.mean} ± {m.std}{pct_range}, "
        f"z-score={direction}{m.z_score} → {_flag_label(m.status)}"
    )


def _ptv_summary(ptvs: list) -> str:
    if not ptvs:
        return "Not specified"
    parts = []
    for p in ptvs:
        parts.append(f"{p['name']}: {p['volume_cc']} cc @ {p['prescribed_dose_gy']} Gy")
    return "; ".join(parts)


def _oar_summary(oars: list) -> str:
    if not oars:
        return "Not specified"
    parts = []
    for o in oars:
        overlaps = ", ".join(f"{k}={v} cc" for k, v in (o.get("overlaps") or {}).items())
        s = f"{o['name']} ({o['volume_cc']} cc)"
        if overlaps:
            s += f" — PTV overlaps: {overlaps}"
        parts.append(s)
    return "; ".join(parts)


def generate_evaluation_narrative(plan: PlanCreate, result: EvaluationResult) -> str:
    client = _get_client()
    if client is None:
        return (
            "AI analysis unavailable — set ANTHROPIC_API_KEY in your .env file to enable "
            "Claude-powered narrative evaluation."
        )

    metric_lines = "\n".join(
        _format_metric_row(name, m) for name, m in result.metrics.items()
    )

    overall_map = {
        "ACCEPTABLE": "ACCEPTABLE — all metrics within normal range",
        "REVIEW_RECOMMENDED": "REVIEW RECOMMENDED — one or more metrics in caution zone",
        "FLAG": "FLAG FOR PHYSICS REVIEW — significant deviation detected",
        "INSUFFICIENT_DATA": "INSUFFICIENT DATA — cannot evaluate statistically",
    }

    prompt = f"""You are an expert medical physicist specializing in radiation oncology treatment planning QA.

Evaluate the following treatment plan's delivery parameters (Monitor Units, beams, segments) against historical data.

=== NEW PLAN ===
Name: {plan.plan_name}
Disease Site: {plan.disease_site}
Technique: {plan.technique}
Prescription: {plan.total_dose_gy} Gy in {plan.fractions} fractions ({plan.dose_per_fraction_gy} Gy/fraction)
PTVs: {_ptv_summary([p.model_dump() for p in plan.ptvs])}
OARs: {_oar_summary([o.model_dump() for o in plan.oars])}
Total Beams: {plan.total_beams}
Total Segments: {plan.total_segments}
Total MUs: {plan.total_mus}
MUs per Fraction: {plan.mus_per_fraction}
MU Efficiency: {plan.mu_efficiency} MU/Gy
Segments per Beam: {plan.segments_per_beam}
MUs per Segment: {plan.mus_per_segment}

=== STATISTICAL COMPARISON ({result.historical_plan_count} historical approved plans) ===
{metric_lines}

=== COMPUTED OVERALL STATUS ===
{overall_map.get(result.overall_status, result.overall_status)}

Provide a structured clinical evaluation with these sections:

**OVERALL ASSESSMENT**
State the clinical assessment and confidence level.

**METRIC ANALYSIS**
For each metric, briefly explain whether the value is expected, and if flagged, describe likely clinical causes.

**CLINICAL CONTEXT**
Consider factors such as PTV size, OAR overlap complexity, dose prescription, and technique that may explain any deviations.

**RECOMMENDATIONS**
Specific, actionable recommendations for the reviewing physicist. If all metrics are normal, confirm the plan appears reasonable.

Keep the response concise and clinically focused (300–500 words). Use plain language suitable for a physics QA checklist."""

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text


def generate_memory_insights(disease_site: str, technique: str, stats: dict) -> str:
    client = _get_client()
    if client is None:
        return "AI insights unavailable — set ANTHROPIC_API_KEY to enable Claude-powered analysis."

    prompt = f"""You are an expert medical physicist. Summarize the delivery parameter patterns from {stats['plan_count']} clinically approved {disease_site} plans treated with {technique}.

Statistics:
- MU Efficiency: {stats['mu_efficiency_mean']:.1f} ± {stats['mu_efficiency_std']:.1f} MU/Gy (P5={stats['mu_efficiency_p5']:.0f}, P95={stats['mu_efficiency_p95']:.0f})
- MUs per Fraction: {stats['mus_per_fraction_mean']:.0f} ± {stats['mus_per_fraction_std']:.0f} (P5={stats['mus_per_fraction_p5']:.0f}, P95={stats['mus_per_fraction_p95']:.0f})
- Total Beams: {stats['total_beams_mean']:.1f} ± {stats['total_beams_std']:.1f} (range {stats['total_beams_min']:.0f}–{stats['total_beams_max']:.0f})
- Total Segments: {stats['total_segments_mean']:.0f} ± {stats['total_segments_std']:.0f} (P5={stats['total_segments_p5']:.0f}, P95={stats['total_segments_p95']:.0f})
- Segments per Beam: {stats['segments_per_beam_mean']:.1f} ± {stats['segments_per_beam_std']:.1f}
- MUs per Segment: {stats['mus_per_segment_mean']:.2f} ± {stats['mus_per_segment_std']:.2f}

Write 2–3 sentences describing what these patterns mean clinically: what drives the MU efficiency level, what the typical beam/segment configuration looks like, and what values should prompt review. Be concise and clinically practical."""

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text
