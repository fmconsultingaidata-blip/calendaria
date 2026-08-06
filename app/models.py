import uuid
from sqlalchemy import Column, String, Float, Boolean, Integer, ForeignKey, Time
from sqlalchemy.orm import relationship
from .database import Base


def gen_id():
    return str(uuid.uuid4())


class Lieu(Base):
    __tablename__ = "lieux"
    id = Column(String, primary_key=True, default=gen_id)
    nom = Column(String, nullable=False)
    type_lieu = Column(String, nullable=False)  # 'ecole' | 'cabinet'
    adresse = Column(String, nullable=False)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    est_base_depart = Column(Boolean, default=False)


class TypePrestation(Base):
    __tablename__ = "types_prestations"
    id = Column(String, primary_key=True, default=gen_id)
    libelle = Column(String, unique=True, nullable=False)  # consultation | bilan_semi_complet | bilan_complet
    duree_minutes = Column(Integer, nullable=False)


class Patient(Base):
    __tablename__ = "patients"
    id = Column(String, primary_key=True, default=gen_id)
    nom = Column(String, nullable=False)
    prenom = Column(String, nullable=True)
    lieu_habituel_id = Column(String, ForeignKey("lieux.id"), nullable=True)


class Consultation(Base):
    __tablename__ = "consultations"
    id = Column(String, primary_key=True, default=gen_id)
    patient_id = Column(String, ForeignKey("patients.id"), nullable=False)
    lieu_id = Column(String, ForeignKey("lieux.id"), nullable=False)
    type_prestation_id = Column(String, ForeignKey("types_prestations.id"), nullable=False)
    parite_semaine = Column(String, default="AB")  # A | B | AB
    jour_semaine = Column(String, nullable=False)  # lundi..vendredi
    creneau_fixe = Column(Boolean, default=False)
    priorite = Column(Integer, default=3)

    # Fenêtre horaire souhaitée (dénormalisé pour simplifier le POC ;
    # dans le schéma complet c'est la table disponibilites_souhaitees)
    fenetre_debut = Column(Time, nullable=False)
    fenetre_fin = Column(Time, nullable=False)

    patient = relationship("Patient")
    lieu = relationship("Lieu")
    type_prestation = relationship("TypePrestation")

# Exemple dans app/models.py
class Trajet(Base):
    __tablename__ = "trajets"
    id = Column(String, primary_key=True, default=gen_id)
    origine_id = Column(String, ForeignKey("lieux.id"), nullable=False)
    destination_id = Column(String, ForeignKey("lieux.id"), nullable=False)
    duree_minutes = Column(Float, nullable=False)
    distance_km = Column(Float, nullable=False)  # Stockage de la distance en km

import json
from datetime import datetime
from sqlalchemy import Text, DateTime

class VersionPlanning(Base):
    __tablename__ = "versions_planning"

    id = Column(String, primary_key=True, default=gen_id)
    titre = Column(String, nullable=False)
    date_sauvegarde = Column(DateTime, default=datetime.utcnow)
    # Stockage de l'état complet du planning sous forme de JSON
    donnees_json = Column(Text, nullable=False)