from datetime import time
from typing import Optional
from pydantic import BaseModel


class LieuOut(BaseModel):
    id: str
    nom: str
    type_lieu: str
    adresse: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    est_base_depart: bool

    class Config:
        from_attributes = True


class LieuCreate(BaseModel):
    nom: str
    type_lieu: str
    adresse: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    est_base_depart: bool = False


class PatientCreate(BaseModel):
    nom: str
    prenom: Optional[str] = None
    lieu_habituel_id: Optional[str] = None


class ConsultationCreate(BaseModel):
    patient_id: str
    lieu_id: str
    type_prestation_libelle: str  # 'consultation' | 'bilan_semi_complet' | 'bilan_complet'
    parite_semaine: str = "AB"
    jour_semaine: str
    creneau_fixe: bool = False
    priorite: int = 3
    fenetre_debut: time
    fenetre_fin: time


class ConsultationOut(BaseModel):
    id: str
    patient_id: str
    lieu_id: str
    jour_semaine: str
    fenetre_debut: time
    fenetre_fin: time
    creneau_fixe: bool

    class Config:
        from_attributes = True


class EtapePlanning(BaseModel):
    consultation_id: str
    patient_nom: str
    lieu_nom: str
    arrivee: str
    depart: str
    trajet_depuis_precedent_minutes: int


class ResultatOptimisation(BaseModel):
    jour: str
    etapes: list[EtapePlanning]
    duree_trajet_totale_minutes: int
    distance_totale_km: float
