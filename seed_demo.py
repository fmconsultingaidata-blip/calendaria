"""
Insère un jeu de données de démo via l'API, pour tester l'optimisation
sans tout saisir à la main.

Usage : lancer le serveur (uvicorn app.main:app --reload) puis, dans un
autre terminal : python seed_demo.py
"""
import requests

BASE_URL = "http://127.0.0.1:8000"

# Coordonnées réelles (La Chapelle-sur-Erdre / Carquefou / Treillières)
lieux = [
    {"nom": "Base", "type_lieu": "cabinet", "adresse": "7 Rue Simone de Beauvoir, 44240 La Chapelle-sur-Erdre",
     "latitude": 47.2966, "longitude": -1.5169, "est_base_depart": True},
    {"nom": "École La Chapelle", "type_lieu": "ecole", "adresse": "5 Rue de Lorraine, 44240 La Chapelle-sur-Erdre",
     "latitude": 47.2980, "longitude": -1.5200, "est_base_depart": False},
    {"nom": "École Carquefou", "type_lieu": "ecole", "adresse": "4 rue Victor Hugo, Carquefou",
     "latitude": 47.2926, "longitude": -1.4956, "est_base_depart": False},
    {"nom": "Cabinet Treillières", "type_lieu": "cabinet", "adresse": "14 place de l'Église, 44199 Treillières",
     "latitude": 47.3661, "longitude": -1.5442, "est_base_depart": False},
]

lieu_ids = {}
for l in lieux:
    r = requests.post(f"{BASE_URL}/lieux", json=l)
    r.raise_for_status()
    lieu_ids[l["nom"]] = r.json()["id"]

patients = [
    {"nom": "Martin", "prenom": "Léa"},
    {"nom": "Dubois", "prenom": "Nathan"},
    {"nom": "Petit", "prenom": "Emma"},
    {"nom": "Roy", "prenom": "Hugo"},
]
patient_ids = {}
for p in patients:
    r = requests.post(f"{BASE_URL}/patients", json=p)
    r.raise_for_status()
    patient_ids[p["nom"]] = r.json()["id"]

consultations = [
    {"patient_id": patient_ids["Martin"], "lieu_id": lieu_ids["École La Chapelle"],
     "type_prestation_libelle": "consultation", "jour_semaine": "mardi",
     "fenetre_debut": "09:00:00", "fenetre_fin": "09:45:00"},
    {"patient_id": patient_ids["Dubois"], "lieu_id": lieu_ids["École Carquefou"],
     "type_prestation_libelle": "bilan_semi_complet", "jour_semaine": "mardi",
     "creneau_fixe": True, "fenetre_debut": "10:00:00", "fenetre_fin": "11:30:00"},
    {"patient_id": patient_ids["Petit"], "lieu_id": lieu_ids["Cabinet Treillières"],
     "type_prestation_libelle": "consultation", "jour_semaine": "mardi",
     "fenetre_debut": "13:00:00", "fenetre_fin": "16:00:00"},
    {"patient_id": patient_ids["Roy"], "lieu_id": lieu_ids["École La Chapelle"],
     "type_prestation_libelle": "consultation", "jour_semaine": "mardi",
     "fenetre_debut": "13:00:00", "fenetre_fin": "17:00:00"},
]
for c in consultations:
    r = requests.post(f"{BASE_URL}/consultations", json=c)
    r.raise_for_status()

print("Données de démo insérées. Teste maintenant : POST /optimize/mardi")
