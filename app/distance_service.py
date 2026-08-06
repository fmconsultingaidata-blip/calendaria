"""
Calcule la matrice temps/distance entre une liste de lieux.

- Si GOOGLE_MAPS_API_KEY est définie : appelle la Distance Matrix API
  (remplace la formule Sheets =INDEX(getGoogleMapsDistance(...))).
- Sinon : repli sur une estimation à vol d'oiseau (Haversine) à 40 km/h
  moyen, suffisant pour tester le moteur d'optimisation sans clé API.

Retourne deux matrices carrées (minutes, km) alignées sur l'ordre
de la liste de lieux passée en entrée.
"""
import os
import math
import requests

GOOGLE_MAPS_API_KEY = "AIzaSyAtF0_VQ8rFHj0JazkraqKj4BFN1NI6eLI"
DISTANCE_MATRIX_URL = "https://maps.googleapis.com/maps/api/distancematrix/json"


def _haversine_km(lat1, lon1, lat2, lon2):
    R = 6371
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def get_distance_matrix(lieux: list[dict]) -> tuple[list[list[int]], list[list[float]]]:
    """
    lieux: liste de dicts avec au moins {latitude, longitude} (ou adresse si clé API dispo)
    Retourne (matrice_minutes, matrice_km)
    """
    n = len(lieux)

    if GOOGLE_MAPS_API_KEY:
        addresses = [l["adresse"] for l in lieux]
        origins = "|".join(addresses)
        destinations = origins
        resp = requests.get(
            DISTANCE_MATRIX_URL,
            params={
                "origins": origins,
                "destinations": destinations,
                "mode": "driving",
                "key": GOOGLE_MAPS_API_KEY,
            },
            timeout=15,
        )
        data = resp.json()
        minutes = [[0] * n for _ in range(n)]
        km = [[0.0] * n for _ in range(n)]
        for i, row in enumerate(data["rows"]):
            for j, elem in enumerate(row["elements"]):
                if elem["status"] == "OK":
                    minutes[i][j] = round(elem["duration"]["value"] / 60)
                    km[i][j] = round(elem["distance"]["value"] / 1000, 2)
                else:
                    # trajet impossible/inconnu -> pénalité forte pour décourager le solveur
                    minutes[i][j] = 9999
                    km[i][j] = 9999
        return minutes, km

    # --- Repli sans clé API : estimation Haversine à 40 km/h ---
    minutes = [[0] * n for _ in range(n)]
    km = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            d = _haversine_km(
                lieux[i]["latitude"], lieux[i]["longitude"],
                lieux[j]["latitude"], lieux[j]["longitude"],
            )
            km[i][j] = round(d, 2)
            minutes[i][j] = max(1, round(d / 40 * 60))  # 40 km/h moyen
    return minutes, km
