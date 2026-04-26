from sqlalchemy import Column, Integer, Float, String, Boolean, DateTime, JSON, Text
from sqlalchemy.sql import func
from database import Base


class Plan(Base):
    __tablename__ = "plans"

    id = Column(Integer, primary_key=True, index=True)
    plan_name = Column(String, nullable=False)
    disease_site = Column(String, nullable=False, index=True)
    technique = Column(String, nullable=False, index=True)

    # Prescription
    total_dose_gy = Column(Float, nullable=False)
    fractions = Column(Integer, nullable=False)
    dose_per_fraction_gy = Column(Float, nullable=False)

    # PTVs: list of {name, volume_cc, prescribed_dose_gy}
    ptvs = Column(JSON, nullable=False, default=list)

    # OARs: list of {name, volume_cc, overlaps: {ptv_name: overlap_cc}}
    oars = Column(JSON, nullable=False, default=list)

    # Delivery
    total_beams = Column(Integer, nullable=False)
    total_segments = Column(Integer, nullable=False)
    total_mus = Column(Float, nullable=False)
    mus_per_fraction = Column(Float, nullable=False)
    mu_efficiency = Column(Float, nullable=False)  # MU / Gy
    segments_per_beam = Column(Float, nullable=False)
    mus_per_segment = Column(Float, nullable=False)

    # Beam details: list of {name, gantry_angle, couch_angle, collimator_angle, energy_mv, mu, segments}
    beam_details = Column(JSON, nullable=False, default=list)

    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    is_approved = Column(Boolean, default=True)


class AIMemory(Base):
    __tablename__ = "ai_memory"

    id = Column(Integer, primary_key=True, index=True)
    disease_site = Column(String, nullable=False, index=True)
    technique = Column(String, nullable=False, index=True)
    plan_count = Column(Integer, default=0)

    # MU efficiency stats
    mu_efficiency_mean = Column(Float)
    mu_efficiency_std = Column(Float)
    mu_efficiency_p5 = Column(Float)
    mu_efficiency_p25 = Column(Float)
    mu_efficiency_p75 = Column(Float)
    mu_efficiency_p95 = Column(Float)

    # MUs per fraction stats
    mus_per_fraction_mean = Column(Float)
    mus_per_fraction_std = Column(Float)
    mus_per_fraction_p5 = Column(Float)
    mus_per_fraction_p95 = Column(Float)

    # Beam count stats
    total_beams_mean = Column(Float)
    total_beams_std = Column(Float)
    total_beams_min = Column(Float)
    total_beams_max = Column(Float)

    # Segment stats
    total_segments_mean = Column(Float)
    total_segments_std = Column(Float)
    total_segments_p5 = Column(Float)
    total_segments_p95 = Column(Float)

    segments_per_beam_mean = Column(Float)
    segments_per_beam_std = Column(Float)

    mus_per_segment_mean = Column(Float)
    mus_per_segment_std = Column(Float)

    # AI narrative insights
    ai_insights = Column(Text)

    last_updated = Column(DateTime(timezone=True), server_default=func.now())


class EvaluationLog(Base):
    __tablename__ = "evaluation_logs"

    id = Column(Integer, primary_key=True, index=True)
    plan_name = Column(String)
    disease_site = Column(String)
    technique = Column(String)
    overall_status = Column(String)  # ACCEPTABLE / REVIEW_RECOMMENDED / FLAG
    plan_data = Column(JSON)
    evaluation_result = Column(JSON)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
