import os
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from sqlalchemy import func

import database, models, schemas, evaluator, ai_agent
from seed_data import get_all_seed_plans

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    models.Base.metadata.create_all(bind=database.engine)
    yield


app = FastAPI(title="RadChecker — Oncology MU Evaluator", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve frontend static files
frontend_dir = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.isdir(frontend_dir):
    app.mount("/static", StaticFiles(directory=frontend_dir), name="static")


@app.get("/")
def root():
    index = os.path.join(frontend_dir, "index.html")
    if os.path.isfile(index):
        return FileResponse(index)
    return {"status": "RadChecker API running", "docs": "/docs"}


# ─── Plans ────────────────────────────────────────────────────────────────────

@app.get("/api/plans", response_model=list[schemas.PlanOut])
def list_plans(
    disease_site: str = None,
    technique: str = None,
    db: Session = Depends(database.get_db),
):
    q = db.query(models.Plan)
    if disease_site:
        q = q.filter(models.Plan.disease_site == disease_site)
    if technique:
        q = q.filter(models.Plan.technique == technique)
    return q.order_by(models.Plan.id.desc()).all()


@app.post("/api/plans", response_model=schemas.PlanOut, status_code=201)
def create_plan(plan: schemas.PlanCreate, db: Session = Depends(database.get_db)):
    db_plan = models.Plan(
        plan_name=plan.plan_name,
        disease_site=plan.disease_site,
        technique=plan.technique,
        total_dose_gy=plan.total_dose_gy,
        fractions=plan.fractions,
        dose_per_fraction_gy=plan.dose_per_fraction_gy,
        ptvs=[p.model_dump() for p in plan.ptvs],
        oars=[o.model_dump() for o in plan.oars],
        total_beams=plan.total_beams,
        total_segments=plan.total_segments,
        total_mus=plan.total_mus,
        mus_per_fraction=plan.mus_per_fraction,
        mu_efficiency=plan.mu_efficiency,
        segments_per_beam=plan.segments_per_beam,
        mus_per_segment=plan.mus_per_segment,
        beam_details=[b.model_dump() for b in plan.beam_details],
        notes=plan.notes,
        is_approved=plan.is_approved,
    )
    db.add(db_plan)
    db.commit()
    db.refresh(db_plan)
    return db_plan


@app.get("/api/plans/{plan_id}", response_model=schemas.PlanOut)
def get_plan(plan_id: int, db: Session = Depends(database.get_db)):
    plan = db.query(models.Plan).filter(models.Plan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    return plan


@app.delete("/api/plans/{plan_id}", status_code=204)
def delete_plan(plan_id: int, db: Session = Depends(database.get_db)):
    plan = db.query(models.Plan).filter(models.Plan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    db.delete(plan)
    db.commit()


# ─── AI Memory ───────────────────────────────────────────────────────────────

@app.get("/api/memory", response_model=list[schemas.AIMemoryOut])
def get_memory(db: Session = Depends(database.get_db)):
    return db.query(models.AIMemory).order_by(models.AIMemory.disease_site, models.AIMemory.technique).all()


@app.post("/api/memory/generate")
def generate_memory(db: Session = Depends(database.get_db)):
    memories = evaluator.rebuild_all_memory(db)
    # Generate AI insights for each memory group
    for mem in memories:
        stats = {
            "plan_count": mem.plan_count,
            "mu_efficiency_mean": mem.mu_efficiency_mean,
            "mu_efficiency_std": mem.mu_efficiency_std,
            "mu_efficiency_p5": mem.mu_efficiency_p5,
            "mu_efficiency_p95": mem.mu_efficiency_p95,
            "mus_per_fraction_mean": mem.mus_per_fraction_mean,
            "mus_per_fraction_std": mem.mus_per_fraction_std,
            "mus_per_fraction_p5": mem.mus_per_fraction_p5,
            "mus_per_fraction_p95": mem.mus_per_fraction_p95,
            "total_beams_mean": mem.total_beams_mean,
            "total_beams_std": mem.total_beams_std,
            "total_beams_min": mem.total_beams_min,
            "total_beams_max": mem.total_beams_max,
            "total_segments_mean": mem.total_segments_mean,
            "total_segments_std": mem.total_segments_std,
            "total_segments_p5": mem.total_segments_p5,
            "total_segments_p95": mem.total_segments_p95,
            "segments_per_beam_mean": mem.segments_per_beam_mean,
            "segments_per_beam_std": mem.segments_per_beam_std,
            "mus_per_segment_mean": mem.mus_per_segment_mean,
            "mus_per_segment_std": mem.mus_per_segment_std,
        }
        insight = ai_agent.generate_memory_insights(mem.disease_site, mem.technique, stats)
        mem.ai_insights = insight
    db.commit()
    return {"generated": len(memories), "groups": [f"{m.disease_site}/{m.technique}" for m in memories]}


# ─── Evaluate ────────────────────────────────────────────────────────────────

@app.post("/api/evaluate", response_model=schemas.EvaluationResult)
def evaluate_plan(plan: schemas.PlanCreate, db: Session = Depends(database.get_db)):
    result = evaluator.evaluate_plan(plan, db)
    narrative = ai_agent.generate_evaluation_narrative(plan, result)
    result.ai_analysis = narrative

    # Log the evaluation
    log = models.EvaluationLog(
        plan_name=plan.plan_name,
        disease_site=plan.disease_site,
        technique=plan.technique,
        overall_status=result.overall_status,
        plan_data=plan.model_dump(),
        evaluation_result=result.model_dump(),
    )
    db.add(log)
    db.commit()

    return result


# ─── Dashboard Stats ─────────────────────────────────────────────────────────

@app.get("/api/stats")
def get_stats(db: Session = Depends(database.get_db)):
    total_plans = db.query(func.count(models.Plan.id)).scalar()
    total_evals = db.query(func.count(models.EvaluationLog.id)).scalar()
    total_memory = db.query(func.count(models.AIMemory.id)).scalar()

    by_site = (
        db.query(models.Plan.disease_site, func.count(models.Plan.id))
        .group_by(models.Plan.disease_site)
        .all()
    )
    by_technique = (
        db.query(models.Plan.technique, func.count(models.Plan.id))
        .group_by(models.Plan.technique)
        .all()
    )
    eval_by_status = (
        db.query(models.EvaluationLog.overall_status, func.count(models.EvaluationLog.id))
        .group_by(models.EvaluationLog.overall_status)
        .all()
    )

    return {
        "total_plans": total_plans,
        "total_evaluations": total_evals,
        "memory_groups": total_memory,
        "plans_by_site": dict(by_site),
        "plans_by_technique": dict(by_technique),
        "evaluations_by_status": dict(eval_by_status),
    }


# ─── Seed ────────────────────────────────────────────────────────────────────

@app.post("/api/seed")
def seed_database(db: Session = Depends(database.get_db)):
    existing = db.query(func.count(models.Plan.id)).scalar()
    if existing > 0:
        return {"message": f"Database already has {existing} plans — skipping seed."}

    seed_plans = get_all_seed_plans()
    created = 0
    for plan in seed_plans:
        try:
            db_plan = models.Plan(
                plan_name=plan.plan_name,
                disease_site=plan.disease_site,
                technique=plan.technique,
                total_dose_gy=plan.total_dose_gy,
                fractions=plan.fractions,
                dose_per_fraction_gy=plan.dose_per_fraction_gy,
                ptvs=[p.model_dump() for p in plan.ptvs],
                oars=[o.model_dump() for o in plan.oars],
                total_beams=plan.total_beams,
                total_segments=plan.total_segments,
                total_mus=plan.total_mus,
                mus_per_fraction=plan.mus_per_fraction,
                mu_efficiency=plan.mu_efficiency,
                segments_per_beam=plan.segments_per_beam,
                mus_per_segment=plan.mus_per_segment,
                beam_details=[b.model_dump() for b in plan.beam_details],
                notes=plan.notes,
                is_approved=plan.is_approved,
            )
            db.add(db_plan)
            created += 1
        except Exception as e:
            print(f"Seed error for {plan.plan_name}: {e}")

    db.commit()
    # Auto-build memory after seeding
    evaluator.rebuild_all_memory(db)
    return {"seeded": created, "message": f"Seeded {created} historical plans and built AI memory."}


# ─── Disease sites / techniques catalog ──────────────────────────────────────

@app.get("/api/catalog")
def get_catalog(db: Session = Depends(database.get_db)):
    sites = [r[0] for r in db.query(models.Plan.disease_site).distinct().all()]
    techniques = [r[0] for r in db.query(models.Plan.technique).distinct().all()]
    return {
        "disease_sites": sorted(sites),
        "techniques": sorted(techniques),
        "common_sites": ["Prostate", "Head_Neck", "Lung", "Brain", "Breast", "Rectum",
                         "Cervix", "Pancreas", "Liver", "Spine"],
        "common_techniques": ["VMAT", "IMRT", "SBRT_VMAT", "SRS_VMAT", "Tangent_IMRT", "3DCRT"],
    }
