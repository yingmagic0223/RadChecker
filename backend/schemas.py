from pydantic import BaseModel, field_validator, model_validator
from typing import Optional
from datetime import datetime


class PTVEntry(BaseModel):
    name: str
    volume_cc: float
    prescribed_dose_gy: float


class OAREntry(BaseModel):
    name: str
    volume_cc: float
    # key = PTV name, value = overlap volume in cc
    overlaps: dict[str, float] = {}


class BeamDetail(BaseModel):
    name: str
    gantry_angle: float
    couch_angle: float = 0.0
    collimator_angle: float = 0.0
    energy_mv: str = "6"
    mu: float
    segments: int


class PlanCreate(BaseModel):
    plan_name: str
    disease_site: str
    technique: str

    total_dose_gy: float
    fractions: int
    dose_per_fraction_gy: Optional[float] = None

    ptvs: list[PTVEntry] = []
    oars: list[OAREntry] = []

    total_beams: int
    total_segments: int
    total_mus: float
    mus_per_fraction: Optional[float] = None
    mu_efficiency: Optional[float] = None
    segments_per_beam: Optional[float] = None
    mus_per_segment: Optional[float] = None

    beam_details: list[BeamDetail] = []
    notes: Optional[str] = None
    is_approved: bool = True

    @model_validator(mode="after")
    def compute_derived(self):
        if self.dose_per_fraction_gy is None:
            self.dose_per_fraction_gy = round(self.total_dose_gy / self.fractions, 4)
        if self.mus_per_fraction is None:
            self.mus_per_fraction = round(self.total_mus / self.fractions, 2)
        if self.mu_efficiency is None:
            self.mu_efficiency = round(self.total_mus / self.total_dose_gy, 2)
        if self.segments_per_beam is None:
            self.segments_per_beam = round(self.total_segments / self.total_beams, 2) if self.total_beams else 0
        if self.mus_per_segment is None:
            self.mus_per_segment = round(self.total_mus / self.total_segments, 2) if self.total_segments else 0
        return self


class PlanOut(PlanCreate):
    id: int
    created_at: datetime

    model_config = {"from_attributes": True}


class AIMemoryOut(BaseModel):
    id: int
    disease_site: str
    technique: str
    plan_count: int

    mu_efficiency_mean: Optional[float]
    mu_efficiency_std: Optional[float]
    mu_efficiency_p5: Optional[float]
    mu_efficiency_p25: Optional[float]
    mu_efficiency_p75: Optional[float]
    mu_efficiency_p95: Optional[float]

    mus_per_fraction_mean: Optional[float]
    mus_per_fraction_std: Optional[float]
    mus_per_fraction_p5: Optional[float]
    mus_per_fraction_p95: Optional[float]

    total_beams_mean: Optional[float]
    total_beams_std: Optional[float]
    total_beams_min: Optional[float]
    total_beams_max: Optional[float]

    total_segments_mean: Optional[float]
    total_segments_std: Optional[float]
    total_segments_p5: Optional[float]
    total_segments_p95: Optional[float]

    segments_per_beam_mean: Optional[float]
    segments_per_beam_std: Optional[float]

    mus_per_segment_mean: Optional[float]
    mus_per_segment_std: Optional[float]

    ai_insights: Optional[str]
    last_updated: datetime

    model_config = {"from_attributes": True}


class MetricFlag(BaseModel):
    value: float
    mean: float
    std: float
    z_score: float
    percentile_rank: Optional[float]
    status: str  # NORMAL / CAUTION / FLAG
    p5: Optional[float] = None
    p95: Optional[float] = None


class EvaluationResult(BaseModel):
    disease_site: str
    technique: str
    historical_plan_count: int
    overall_status: str  # ACCEPTABLE / REVIEW_RECOMMENDED / FLAG
    metrics: dict[str, MetricFlag]
    ai_analysis: str
    similar_plans: list[dict] = []
