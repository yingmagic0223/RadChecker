"""
Realistic synthetic historical treatment plans for seeding the database.
Values are based on published literature and typical clinical practice.
"""
import random
from schemas import PlanCreate, PTVEntry, OAREntry, BeamDetail


rng = random.Random(42)


def _jitter(base: float, pct: float = 0.10) -> float:
    return round(base * (1 + rng.uniform(-pct, pct)), 1)


def _int_jitter(base: int, pct: float = 0.12) -> int:
    return max(1, round(base * (1 + rng.uniform(-pct, pct))))


# ─── Prostate VMAT (2-arc, 6FFF) ─────────────────────────────────────────────

def _prostate_vmat() -> list[PlanCreate]:
    plans = []
    for i in range(12):
        total_dose = rng.choice([78.0, 79.2, 60.0, 70.0])
        fractions = {78.0: 39, 79.2: 44, 60.0: 20, 70.0: 28}[total_dose]
        ptv_vol = _jitter(150, 0.35)
        has_sv = rng.random() > 0.4
        ptvs = [PTVEntry(name="PTV_Prostate", volume_cc=ptv_vol, prescribed_dose_gy=total_dose)]
        if has_sv:
            ptvs.append(PTVEntry(name="PTV_SV", volume_cc=_jitter(80, 0.4), prescribed_dose_gy=round(total_dose * 0.9, 1)))

        oars = [
            OAREntry(name="Rectum", volume_cc=_jitter(55, 0.3), overlaps={"PTV_Prostate": _jitter(12, 0.5)}),
            OAREntry(name="Bladder", volume_cc=_jitter(200, 0.4), overlaps={"PTV_Prostate": _jitter(18, 0.5)}),
            OAREntry(name="FemoralHead_L", volume_cc=_jitter(90, 0.1), overlaps={}),
            OAREntry(name="FemoralHead_R", volume_cc=_jitter(88, 0.1), overlaps={}),
        ]

        segs = _int_jitter(354)  # 177 per arc × 2
        mu_eff = _jitter(670, 0.12)
        total_mu = round(mu_eff * total_dose)
        plans.append(PlanCreate(
            plan_name=f"Prostate_VMAT_{i+1:02d}",
            disease_site="Prostate",
            technique="VMAT",
            total_dose_gy=total_dose,
            fractions=fractions,
            ptvs=ptvs,
            oars=oars,
            total_beams=2,
            total_segments=segs,
            total_mus=float(total_mu),
            beam_details=[
                BeamDetail(name="Arc1_CW", gantry_angle=181, couch_angle=0, collimator_angle=30,
                           energy_mv="6FFF", mu=total_mu * 0.52, segments=segs // 2),
                BeamDetail(name="Arc2_CCW", gantry_angle=179, couch_angle=0, collimator_angle=330,
                           energy_mv="6FFF", mu=total_mu * 0.48, segments=segs - segs // 2),
            ],
        ))
    return plans


# ─── H&N VMAT SIB (2-arc, 6MV) ───────────────────────────────────────────────

def _hn_vmat() -> list[PlanCreate]:
    plans = []
    for i in range(10):
        high_dose = 70.0
        mid_dose = 59.4
        low_dose = 54.0
        fractions = 35

        ptv_high_vol = _jitter(280, 0.30)
        ptv_mid_vol = _jitter(420, 0.30)
        ptv_low_vol = _jitter(560, 0.30)

        ptvs = [
            PTVEntry(name="PTV70", volume_cc=ptv_high_vol, prescribed_dose_gy=high_dose),
            PTVEntry(name="PTV59", volume_cc=ptv_mid_vol, prescribed_dose_gy=mid_dose),
            PTVEntry(name="PTV54", volume_cc=ptv_low_vol, prescribed_dose_gy=low_dose),
        ]

        oars = [
            OAREntry(name="SpinalCord", volume_cc=_jitter(30, 0.2), overlaps={"PTV54": _jitter(1.5, 0.5)}),
            OAREntry(name="Brainstem", volume_cc=_jitter(25, 0.2), overlaps={}),
            OAREntry(name="Parotid_L", volume_cc=_jitter(22, 0.35), overlaps={"PTV54": _jitter(5, 0.6)}),
            OAREntry(name="Parotid_R", volume_cc=_jitter(24, 0.35), overlaps={"PTV54": _jitter(4.5, 0.6)}),
            OAREntry(name="Mandible", volume_cc=_jitter(60, 0.2), overlaps={"PTV70": _jitter(3, 0.5)}),
            OAREntry(name="Larynx", volume_cc=_jitter(18, 0.3), overlaps={"PTV59": _jitter(8, 0.4)}),
        ]

        segs = _int_jitter(354)
        mu_eff = _jitter(580, 0.13)
        total_mu = round(mu_eff * high_dose)
        plans.append(PlanCreate(
            plan_name=f"HN_VMAT_{i+1:02d}",
            disease_site="Head_Neck",
            technique="VMAT",
            total_dose_gy=high_dose,
            fractions=fractions,
            ptvs=ptvs,
            oars=oars,
            total_beams=2,
            total_segments=segs,
            total_mus=float(total_mu),
            beam_details=[
                BeamDetail(name="Arc1_CW", gantry_angle=181, couch_angle=0, collimator_angle=30,
                           energy_mv="6", mu=total_mu * 0.51, segments=segs // 2),
                BeamDetail(name="Arc2_CCW", gantry_angle=179, couch_angle=0, collimator_angle=330,
                           energy_mv="6", mu=total_mu * 0.49, segments=segs - segs // 2),
            ],
        ))
    return plans


# ─── H&N IMRT 9-field ─────────────────────────────────────────────────────────

def _hn_imrt() -> list[PlanCreate]:
    plans = []
    angles = [0, 40, 80, 120, 160, 200, 240, 280, 320]
    for i in range(9):
        high_dose = 70.0
        fractions = 35
        ptvs = [
            PTVEntry(name="PTV70", volume_cc=_jitter(260, 0.30), prescribed_dose_gy=70.0),
            PTVEntry(name="PTV59", volume_cc=_jitter(400, 0.30), prescribed_dose_gy=59.4),
            PTVEntry(name="PTV54", volume_cc=_jitter(530, 0.30), prescribed_dose_gy=54.0),
        ]
        oars = [
            OAREntry(name="SpinalCord", volume_cc=_jitter(30, 0.2), overlaps={"PTV54": _jitter(1.2, 0.5)}),
            OAREntry(name="Parotid_L", volume_cc=_jitter(21, 0.35), overlaps={"PTV54": _jitter(4.5, 0.6)}),
            OAREntry(name="Parotid_R", volume_cc=_jitter(23, 0.35), overlaps={"PTV54": _jitter(4.2, 0.6)}),
            OAREntry(name="Mandible", volume_cc=_jitter(58, 0.2), overlaps={"PTV70": _jitter(2.5, 0.5)}),
        ]
        n_beams = 9
        segs_per_beam = _int_jitter(11)
        total_segs = n_beams * segs_per_beam
        mu_eff = _jitter(460, 0.14)
        total_mu = round(mu_eff * high_dose)
        mu_per_beam = total_mu / n_beams

        plans.append(PlanCreate(
            plan_name=f"HN_IMRT_{i+1:02d}",
            disease_site="Head_Neck",
            technique="IMRT",
            total_dose_gy=high_dose,
            fractions=fractions,
            ptvs=ptvs,
            oars=oars,
            total_beams=n_beams,
            total_segments=total_segs,
            total_mus=float(total_mu),
            beam_details=[
                BeamDetail(name=f"Beam_{a}deg", gantry_angle=a, couch_angle=0,
                           collimator_angle=0, energy_mv="6", mu=round(mu_per_beam, 1),
                           segments=segs_per_beam)
                for a in angles
            ],
        ))
    return plans


# ─── Lung SBRT VMAT (48–60 Gy / 3–5 fx) ─────────────────────────────────────

def _lung_sbrt() -> list[PlanCreate]:
    plans = []
    rx_options = [(48.0, 4), (50.0, 5), (54.0, 3), (60.0, 5), (48.0, 3)]
    for i in range(10):
        total_dose, fractions = rx_options[i % len(rx_options)]
        ptv_vol = _jitter(35, 0.55)  # small to medium lung tumors
        ptvs = [PTVEntry(name="PTV_Lung", volume_cc=ptv_vol, prescribed_dose_gy=total_dose)]
        oars = [
            OAREntry(name="Lung_Ipsilateral", volume_cc=_jitter(1500, 0.2),
                     overlaps={"PTV_Lung": _jitter(ptv_vol * 0.6, 0.2)}),
            OAREntry(name="Lung_Contralateral", volume_cc=_jitter(1600, 0.2), overlaps={}),
            OAREntry(name="SpinalCord", volume_cc=_jitter(30, 0.15), overlaps={}),
            OAREntry(name="Esophagus", volume_cc=_jitter(25, 0.2), overlaps={}),
            OAREntry(name="Heart", volume_cc=_jitter(500, 0.3), overlaps={}),
        ]
        n_arcs = rng.choice([2, 3])
        segs = _int_jitter(n_arcs * 177)
        mu_eff = _jitter(900, 0.18)  # higher due to small fields and high dose/fx
        total_mu = round(mu_eff * total_dose)
        plans.append(PlanCreate(
            plan_name=f"Lung_SBRT_{i+1:02d}",
            disease_site="Lung",
            technique="SBRT_VMAT",
            total_dose_gy=total_dose,
            fractions=fractions,
            ptvs=ptvs,
            oars=oars,
            total_beams=n_arcs,
            total_segments=segs,
            total_mus=float(total_mu),
            beam_details=[
                BeamDetail(name=f"Arc{j+1}", gantry_angle=181 if j == 0 else 179,
                           couch_angle=0, collimator_angle=15 if j == 0 else 345,
                           energy_mv="6FFF", mu=total_mu / n_arcs, segments=segs // n_arcs)
                for j in range(n_arcs)
            ],
        ))
    return plans


# ─── Brain SRS (15–24 Gy / 1–3 fx) ──────────────────────────────────────────

def _brain_srs() -> list[PlanCreate]:
    plans = []
    rx_options = [(18.0, 1), (20.0, 1), (24.0, 1), (27.0, 3), (30.0, 3), (21.0, 1)]
    for i in range(8):
        total_dose, fractions = rx_options[i % len(rx_options)]
        ptv_vol = _jitter(8, 0.60)  # small brain mets
        ptvs = [PTVEntry(name="PTV_Brain", volume_cc=ptv_vol, prescribed_dose_gy=total_dose)]
        oars = [
            OAREntry(name="Brainstem", volume_cc=_jitter(22, 0.15), overlaps={"PTV_Brain": _jitter(0.5, 0.6)}),
            OAREntry(name="OpticChiasm", volume_cc=_jitter(0.8, 0.3), overlaps={}),
            OAREntry(name="Brain", volume_cc=_jitter(1300, 0.1), overlaps={"PTV_Brain": ptv_vol}),
            OAREntry(name="Cochlea_L", volume_cc=_jitter(0.15, 0.2), overlaps={}),
            OAREntry(name="Cochlea_R", volume_cc=_jitter(0.15, 0.2), overlaps={}),
        ]
        n_arcs = rng.choice([3, 4, 5])
        segs = _int_jitter(n_arcs * 160)
        mu_eff = _jitter(2800, 0.20)  # very high — single/few fraction, high dose
        total_mu = round(mu_eff * total_dose)
        plans.append(PlanCreate(
            plan_name=f"Brain_SRS_{i+1:02d}",
            disease_site="Brain",
            technique="SRS_VMAT",
            total_dose_gy=total_dose,
            fractions=fractions,
            ptvs=ptvs,
            oars=oars,
            total_beams=n_arcs,
            total_segments=segs,
            total_mus=float(total_mu),
            beam_details=[
                BeamDetail(name=f"Arc{j+1}", gantry_angle=rng.randint(0, 359),
                           couch_angle=rng.choice([0, 30, 60, 330, 300]),
                           collimator_angle=rng.randint(0, 45),
                           energy_mv="6FFF", mu=total_mu / n_arcs, segments=segs // n_arcs)
                for j in range(n_arcs)
            ],
        ))
    return plans


# ─── Breast Tangents (3D / simple IMRT) ──────────────────────────────────────

def _breast_imrt() -> list[PlanCreate]:
    plans = []
    rx_options = [(50.0, 25), (40.05, 15), (42.56, 16), (50.0, 25)]
    for i in range(8):
        total_dose, fractions = rx_options[i % len(rx_options)]
        whole_breast = _jitter(700, 0.30)
        has_boost = rng.random() > 0.5
        ptvs = [PTVEntry(name="PTV_WholeBread", volume_cc=whole_breast, prescribed_dose_gy=total_dose)]
        if has_boost:
            ptvs.append(PTVEntry(name="PTV_Boost", volume_cc=_jitter(60, 0.4),
                                 prescribed_dose_gy=round(total_dose + 10, 1)))

        oars = [
            OAREntry(name="Heart", volume_cc=_jitter(490, 0.3), overlaps={"PTV_WholeBread": _jitter(15, 0.6)}),
            OAREntry(name="Lung_Ipsilateral", volume_cc=_jitter(1400, 0.2),
                     overlaps={"PTV_WholeBread": _jitter(80, 0.4)}),
            OAREntry(name="Lung_Contralateral", volume_cc=_jitter(1500, 0.2), overlaps={}),
        ]

        n_beams = 2 if not has_boost else 4
        segs_per_beam = _int_jitter(6 if not has_boost else 8)
        total_segs = n_beams * segs_per_beam
        mu_eff = _jitter(285, 0.12)
        total_mu = round(mu_eff * total_dose)

        plans.append(PlanCreate(
            plan_name=f"Breast_IMRT_{i+1:02d}",
            disease_site="Breast",
            technique="Tangent_IMRT",
            total_dose_gy=total_dose,
            fractions=fractions,
            ptvs=ptvs,
            oars=oars,
            total_beams=n_beams,
            total_segments=total_segs,
            total_mus=float(total_mu),
            beam_details=[
                BeamDetail(name=f"Tangent_{j+1}", gantry_angle=[45, 135, 225, 315][j % 4],
                           couch_angle=0, collimator_angle=0,
                           energy_mv="6", mu=total_mu / n_beams, segments=segs_per_beam)
                for j in range(n_beams)
            ],
        ))
    return plans


# ─── Rectum VMAT (2-arc) ──────────────────────────────────────────────────────

def _rectum_vmat() -> list[PlanCreate]:
    plans = []
    for i in range(8):
        total_dose = rng.choice([50.4, 45.0, 54.0])
        fractions = {50.4: 28, 45.0: 25, 54.0: 30}[total_dose]
        ptvs = [
            PTVEntry(name="PTV_Rectum", volume_cc=_jitter(400, 0.30), prescribed_dose_gy=total_dose),
        ]
        if rng.random() > 0.5:
            ptvs.append(PTVEntry(name="PTV_Nodes", volume_cc=_jitter(200, 0.4),
                                 prescribed_dose_gy=round(total_dose * 0.85, 1)))

        oars = [
            OAREntry(name="Bladder", volume_cc=_jitter(200, 0.4), overlaps={"PTV_Rectum": _jitter(20, 0.5)}),
            OAREntry(name="SmallBowel", volume_cc=_jitter(300, 0.5), overlaps={"PTV_Rectum": _jitter(10, 0.7)}),
            OAREntry(name="FemoralHead_L", volume_cc=_jitter(90, 0.1), overlaps={}),
            OAREntry(name="FemoralHead_R", volume_cc=_jitter(88, 0.1), overlaps={}),
        ]
        segs = _int_jitter(354)
        mu_eff = _jitter(540, 0.12)
        total_mu = round(mu_eff * total_dose)
        plans.append(PlanCreate(
            plan_name=f"Rectum_VMAT_{i+1:02d}",
            disease_site="Rectum",
            technique="VMAT",
            total_dose_gy=total_dose,
            fractions=fractions,
            ptvs=ptvs,
            oars=oars,
            total_beams=2,
            total_segments=segs,
            total_mus=float(total_mu),
            beam_details=[
                BeamDetail(name="Arc1_CW", gantry_angle=181, couch_angle=0, collimator_angle=30,
                           energy_mv="6", mu=total_mu * 0.52, segments=segs // 2),
                BeamDetail(name="Arc2_CCW", gantry_angle=179, couch_angle=0, collimator_angle=330,
                           energy_mv="6", mu=total_mu * 0.48, segments=segs - segs // 2),
            ],
        ))
    return plans


def get_all_seed_plans() -> list[PlanCreate]:
    all_plans = (
        _prostate_vmat() +
        _hn_vmat() +
        _hn_imrt() +
        _lung_sbrt() +
        _brain_srs() +
        _breast_imrt() +
        _rectum_vmat()
    )
    return all_plans
