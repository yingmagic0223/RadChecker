import numpy as np
from scipy import stats
from sqlalchemy.orm import Session
from models import Plan, AIMemory
from schemas import MetricFlag, EvaluationResult, PlanCreate


METRIC_LABELS = {
    "mu_efficiency": "MU Efficiency (MU/Gy)",
    "mus_per_fraction": "MUs per Fraction",
    "total_beams": "Total Beams",
    "total_segments": "Total Segments",
    "segments_per_beam": "Segments per Beam",
    "mus_per_segment": "MUs per Segment",
}

# z-score thresholds for flagging
CAUTION_Z = 1.8
FLAG_Z = 2.5


def _status_from_z(z: float) -> str:
    if abs(z) <= CAUTION_Z:
        return "NORMAL"
    if abs(z) <= FLAG_Z:
        return "CAUTION"
    return "FLAG"


def _overall_status(metric_flags: dict[str, MetricFlag]) -> str:
    statuses = [m.status for m in metric_flags.values()]
    if "FLAG" in statuses:
        return "FLAG"
    if "CAUTION" in statuses:
        return "REVIEW_RECOMMENDED"
    return "ACCEPTABLE"


def build_memory_for_group(db: Session, disease_site: str, technique: str) -> AIMemory | None:
    plans = (
        db.query(Plan)
        .filter(Plan.disease_site == disease_site, Plan.technique == technique, Plan.is_approved == True)
        .all()
    )
    if len(plans) < 3:
        return None

    def arr(attr):
        return np.array([getattr(p, attr) for p in plans], dtype=float)

    def build_stats(values):
        return {
            "mean": float(np.mean(values)),
            "std": float(np.std(values, ddof=1)),
            "p5": float(np.percentile(values, 5)),
            "p25": float(np.percentile(values, 25)),
            "p75": float(np.percentile(values, 75)),
            "p95": float(np.percentile(values, 95)),
            "min": float(np.min(values)),
            "max": float(np.max(values)),
        }

    mue = arr("mu_efficiency")
    mpf = arr("mus_per_fraction")
    tb = arr("total_beams")
    ts = arr("total_segments")
    spb = arr("segments_per_beam")
    mps = arr("mus_per_segment")

    s_mue = build_stats(mue)
    s_mpf = build_stats(mpf)
    s_tb = build_stats(tb)
    s_ts = build_stats(ts)
    s_spb = build_stats(spb)
    s_mps = build_stats(mps)

    mem = db.query(AIMemory).filter(
        AIMemory.disease_site == disease_site, AIMemory.technique == technique
    ).first()
    if mem is None:
        mem = AIMemory(disease_site=disease_site, technique=technique)
        db.add(mem)

    mem.plan_count = len(plans)
    mem.mu_efficiency_mean = s_mue["mean"]
    mem.mu_efficiency_std = s_mue["std"]
    mem.mu_efficiency_p5 = s_mue["p5"]
    mem.mu_efficiency_p25 = s_mue["p25"]
    mem.mu_efficiency_p75 = s_mue["p75"]
    mem.mu_efficiency_p95 = s_mue["p95"]

    mem.mus_per_fraction_mean = s_mpf["mean"]
    mem.mus_per_fraction_std = s_mpf["std"]
    mem.mus_per_fraction_p5 = s_mpf["p5"]
    mem.mus_per_fraction_p95 = s_mpf["p95"]

    mem.total_beams_mean = s_tb["mean"]
    mem.total_beams_std = s_tb["std"]
    mem.total_beams_min = s_tb["min"]
    mem.total_beams_max = s_tb["max"]

    mem.total_segments_mean = s_ts["mean"]
    mem.total_segments_std = s_ts["std"]
    mem.total_segments_p5 = s_ts["p5"]
    mem.total_segments_p95 = s_ts["p95"]

    mem.segments_per_beam_mean = s_spb["mean"]
    mem.segments_per_beam_std = s_spb["std"]

    mem.mus_per_segment_mean = s_mps["mean"]
    mem.mus_per_segment_std = s_mps["std"]

    db.commit()
    db.refresh(mem)
    return mem


def rebuild_all_memory(db: Session) -> list[AIMemory]:
    groups = db.query(Plan.disease_site, Plan.technique).distinct().all()
    results = []
    for disease_site, technique in groups:
        mem = build_memory_for_group(db, disease_site, technique)
        if mem:
            results.append(mem)
    return results


def _z_score(value: float, mean: float, std: float) -> float:
    if std == 0:
        return 0.0
    return (value - mean) / std


def _percentile_rank(value: float, values: list[float]) -> float:
    arr = np.array(values, dtype=float)
    return float(stats.percentileofscore(arr, value, kind="rank"))


def evaluate_plan(plan: PlanCreate, db: Session) -> EvaluationResult:
    mem = db.query(AIMemory).filter(
        AIMemory.disease_site == plan.disease_site,
        AIMemory.technique == plan.technique,
    ).first()

    if mem is None or mem.plan_count < 3:
        # Try rebuilding memory first
        mem = build_memory_for_group(db, plan.disease_site, plan.technique)

    if mem is None:
        return EvaluationResult(
            disease_site=plan.disease_site,
            technique=plan.technique,
            historical_plan_count=0,
            overall_status="INSUFFICIENT_DATA",
            metrics={},
            ai_analysis=(
                f"No historical data available for {plan.disease_site} / {plan.technique}. "
                "Please add more approved clinical plans to enable statistical comparison."
            ),
        )

    historical_plans = (
        db.query(Plan)
        .filter(Plan.disease_site == plan.disease_site, Plan.technique == plan.technique, Plan.is_approved == True)
        .order_by(Plan.id.desc())
        .limit(5)
        .all()
    )

    def metric_flag(value: float, mean: float, std: float, p5: float = None, p95: float = None) -> MetricFlag:
        z = _z_score(value, mean, std)
        return MetricFlag(
            value=round(value, 2),
            mean=round(mean, 2),
            std=round(std, 2),
            z_score=round(z, 2),
            percentile_rank=None,
            status=_status_from_z(z),
            p5=round(p5, 2) if p5 is not None else None,
            p95=round(p95, 2) if p95 is not None else None,
        )

    metrics: dict[str, MetricFlag] = {}

    if mem.mu_efficiency_mean is not None:
        metrics["mu_efficiency"] = metric_flag(
            plan.mu_efficiency, mem.mu_efficiency_mean, mem.mu_efficiency_std,
            mem.mu_efficiency_p5, mem.mu_efficiency_p95
        )

    if mem.mus_per_fraction_mean is not None:
        metrics["mus_per_fraction"] = metric_flag(
            plan.mus_per_fraction, mem.mus_per_fraction_mean, mem.mus_per_fraction_std,
            mem.mus_per_fraction_p5, mem.mus_per_fraction_p95
        )

    if mem.total_beams_mean is not None:
        metrics["total_beams"] = metric_flag(
            plan.total_beams, mem.total_beams_mean, mem.total_beams_std
        )

    if mem.total_segments_mean is not None:
        metrics["total_segments"] = metric_flag(
            plan.total_segments, mem.total_segments_mean, mem.total_segments_std,
            mem.total_segments_p5, mem.total_segments_p95
        )

    if mem.segments_per_beam_mean is not None:
        metrics["segments_per_beam"] = metric_flag(
            plan.segments_per_beam, mem.segments_per_beam_mean, mem.segments_per_beam_std
        )

    if mem.mus_per_segment_mean is not None:
        metrics["mus_per_segment"] = metric_flag(
            plan.mus_per_segment, mem.mus_per_segment_mean, mem.mus_per_segment_std
        )

    overall = _overall_status(metrics)

    similar = [
        {
            "id": p.id,
            "plan_name": p.plan_name,
            "total_dose_gy": p.total_dose_gy,
            "fractions": p.fractions,
            "total_beams": p.total_beams,
            "total_segments": p.total_segments,
            "total_mus": p.total_mus,
            "mu_efficiency": p.mu_efficiency,
        }
        for p in historical_plans
    ]

    return EvaluationResult(
        disease_site=plan.disease_site,
        technique=plan.technique,
        historical_plan_count=mem.plan_count,
        overall_status=overall,
        metrics=metrics,
        ai_analysis="",  # populated by ai_agent
        similar_plans=similar,
    )
