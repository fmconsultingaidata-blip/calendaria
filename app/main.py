from datetime import time
from typing import Optional
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from fastapi import Request, Form, Depends
from fastapi.responses import RedirectResponse
from datetime import time

from . import models, schemas
from .database import engine, get_db, Base
from .distance_service import get_distance_matrix
from .optimizer import optimize_day

models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Planning optimisé de consultations - POC")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

JOURS_ORDRE = ["lundi", "mardi", "mercredi", "jeudi", "vendredi"]
HEURE_DEBUT_JOURNEE = time(9, 0)
HEURE_FIN_JOURNEE = time(18, 0)
HEURE_FIN_VENDREDI = time(12, 30)  # blocage vendredi après-midi (rédaction)


def to_minutes(t: time) -> int:
    return t.hour * 60 + t.minute


# --------------------------------------------------------------
# Référentiel : types de prestations (seed automatique au démarrage)
# --------------------------------------------------------------
@app.on_event("startup")
def seed_types_prestations():
    db = next(get_db())
    existing = {t.libelle for t in db.query(models.TypePrestation).all()}
    defaults = {"consultation": 45, "bilan_semi_complet": 90, "bilan_complet": 120}
    for libelle, duree in defaults.items():
        if libelle not in existing:
            db.add(models.TypePrestation(libelle=libelle, duree_minutes=duree))
    db.commit()


# --------------------------------------------------------------
# Lieux
# --------------------------------------------------------------
@app.post("/lieux", response_model=schemas.LieuOut)
def create_lieu(lieu: schemas.LieuCreate, db: Session = Depends(get_db)):
    db_lieu = models.Lieu(**lieu.model_dump())
    db.add(db_lieu)
    db.commit()
    db.refresh(db_lieu)
    return db_lieu


@app.get("/lieux", response_model=list[schemas.LieuOut])
def list_lieux(db: Session = Depends(get_db)):
    return db.query(models.Lieu).all()


# --------------------------------------------------------------
# Patients
# --------------------------------------------------------------
@app.post("/patients")
def create_patient(patient: schemas.PatientCreate, db: Session = Depends(get_db)):
    db_patient = models.Patient(**patient.model_dump())
    db.add(db_patient)
    db.commit()
    db.refresh(db_patient)
    return db_patient


# --------------------------------------------------------------
# Consultations
# --------------------------------------------------------------
@app.post("/consultations", response_model=schemas.ConsultationOut)
def create_consultation(c: schemas.ConsultationCreate, db: Session = Depends(get_db)):
    type_prestation = db.query(models.TypePrestation).filter_by(libelle=c.type_prestation_libelle).first()
    if not type_prestation:
        raise HTTPException(400, f"Type de prestation inconnu: {c.type_prestation_libelle}")

    if c.jour_semaine not in JOURS_ORDRE:
        raise HTTPException(400, f"Jour invalide: {c.jour_semaine}")

    # Blocage vendredi après-midi
    if c.jour_semaine == "vendredi" and c.fenetre_fin > HEURE_FIN_VENDREDI and not c.creneau_fixe:
        raise HTTPException(400, "Le vendredi après-midi est bloqué (temps réservé à la rédaction)")

    # Contrainte bilans : créneau fixe uniquement mardi ou vendredi 10h-12h
    if c.creneau_fixe and c.jour_semaine not in ("mardi", "vendredi"):
        raise HTTPException(400, "Un créneau fixe de bilan doit être le mardi ou le vendredi")

    db_c = models.Consultation(
        patient_id=c.patient_id,
        lieu_id=c.lieu_id,
        type_prestation_id=type_prestation.id,
        parite_semaine=c.parite_semaine,
        jour_semaine=c.jour_semaine,
        creneau_fixe=c.creneau_fixe,
        priorite=c.priorite,
        fenetre_debut=c.fenetre_debut,
        fenetre_fin=c.fenetre_fin,
    )
    db.add(db_c)
    db.commit()
    db.refresh(db_c)
    return db_c


@app.get("/consultations", response_model=list[schemas.ConsultationOut])
def list_consultations(jour: Optional[str] = None, db: Session = Depends(get_db)):
    q = db.query(models.Consultation)
    if jour:
        q = q.filter(models.Consultation.jour_semaine == jour)
    return q.all()


# --------------------------------------------------------------
# Optimisation
# --------------------------------------------------------------
@app.post("/optimize/{jour}", response_model=schemas.ResultatOptimisation)
def optimize(jour: str, db: Session = Depends(get_db)):
    if jour not in JOURS_ORDRE:
        raise HTTPException(400, "Jour invalide")

    base = db.query(models.Lieu).filter_by(est_base_depart=True).first()
    if not base:
        raise HTTPException(400, "Aucun lieu marqué comme base de départ (est_base_depart=True)")

    consultations = db.query(models.Consultation).filter_by(jour_semaine=jour).all()
    if not consultations:
        raise HTTPException(404, f"Aucune consultation trouvée pour {jour}")

    # Construction de la liste des lieux dans l'ordre [base, arrêt1, arrêt2, ...]
    lieux_ordonnes = [{"adresse": base.adresse, "latitude": base.latitude, "longitude": base.longitude}]
    for c in consultations:
        lieux_ordonnes.append({
            "adresse": c.lieu.adresse,
            "latitude": c.lieu.latitude,
            "longitude": c.lieu.longitude,
        })

    minutes_matrix, km_matrix = get_distance_matrix(lieux_ordonnes)

    day_end = HEURE_FIN_VENDREDI if jour == "vendredi" else HEURE_FIN_JOURNEE
    stops = []
    for c in consultations:
        stops.append({
            "id": c.id,
            "duration_minutes": c.type_prestation.duree_minutes,
            "window_start": to_minutes(c.fenetre_debut),
            "window_end": to_minutes(c.fenetre_fin),
        })

    result = optimize_day(
        base={"duration_minutes": 0},
        stops=stops,
        minutes_matrix=minutes_matrix,
        day_start_minutes=to_minutes(HEURE_DEBUT_JOURNEE),
        day_end_minutes=to_minutes(day_end),
    )

    if result is None:
        raise HTTPException(422, "Aucune solution trouvée : contraintes horaires incompatibles entre elles")

    def fmt(m):
        return f"{m // 60:02d}:{m % 60:02d}"

    etapes = []
    total_minutes_trajet = 0
    total_km = 0.0
    prev_node = 0
    for i, step in enumerate(result):
        node = step["node"]
        arrival = step["arrival_minutes"]
        if node == 0:
            continue  # dépôt (début ou retour) — pas affiché comme étape patient
        c = consultations[node - 1]
        trajet = minutes_matrix[prev_node][node]
        total_minutes_trajet += trajet
        total_km += km_matrix[prev_node][node]
        departure = arrival + c.type_prestation.duree_minutes
        etapes.append(schemas.EtapePlanning(
            consultation_id=c.id,
            patient_nom=f"{c.patient.prenom or ''} {c.patient.nom}".strip(),
            lieu_nom=c.lieu.nom,
            arrivee=fmt(arrival),
            depart=fmt(departure),
            trajet_depuis_precedent_minutes=trajet,
        ))
        prev_node = node

    return schemas.ResultatOptimisation(
        jour=jour,
        etapes=etapes,
        duree_trajet_totale_minutes=total_minutes_trajet,
        distance_totale_km=round(total_km, 2),
    )


@app.post("/ajouter_patient")
def ajouter_patient(
    nom: str = Form(...),
    prenom: str = Form(...),
    nom_lieu: str = Form(...),
    type_lieu: str = Form(...),  # 'ecole' ou 'cabinet'
    adresse: str = Form(...),
    jour_semaine: str = Form(...),
    parite_semaine: str = Form(...),  # 'A', 'B', ou 'AB'
    type_prestation_id: str = Form(...),
    fenetre_debut: str = Form(...),  # Format "HH:MM"
    fenetre_fin: str = Form(...),     # Format "HH:MM"
    db: Session = Depends(get_db)
):
    # 1. Créer ou récupérer le lieu
    lieu = db.query(models.Lieu).filter(models.Lieu.nom == nom_lieu).first()
    if not lieu:
        lieu = models.Lieu(nom=nom_lieu, type_lieu=type_lieu, adresse=adresse)
        db.add(lieu)
        db.commit()
        db.refresh(lieu)

    # 2. Créer le patient
    patient = models.Patient(nom=nom, prenom=prenom, lieu_habituel_id=lieu.id)
    db.add(patient)
    db.commit()
    db.refresh(patient)

    # 3. Convertir les heures textuelles en objets Time
    h_debut = time.fromisoformat(fenetre_debut)
    h_fin = time.fromisoformat(fenetre_fin)

    # 4. Créer la consultation associée
    consultation = models.Consultation(
        patient_id=patient.id,
        lieu_id=lieu.id,
        type_prestation_id=type_prestation_id,
        jour_semaine=jour_semaine,
        parite_semaine=parite_semaine,
        fenetre_debut=h_debut,
        fenetre_fin=h_fin
    )
    db.add(consultation)
    db.commit()

    # Redirection vers la page d'accueil
    return RedirectResponse(url="/", status_code=303)


# Le montage des fichiers statiques doit impérativement rester tout à la fin
app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")