"""Calcule la matrice temps/distance entre une liste de lieux.

- Utilise la clé API définie dans les secrets Streamlit (.streamlit/secrets.toml)
  via st.secrets["GOOGLE_MAPS_API_KEY"].
- Sinon : repli sur une estimation Haversine à 40 km/h.
"""

import math
import requests
import streamlit as st

# Récupération de la clé depuis les Secrets Streamlit
try:
  GOOGLE_MAPS_API_KEY = st.secrets["GOOGLE_MAPS_API_KEY"]
except (KeyError, FileNotFoundError):
  GOOGLE_MAPS_API_KEY = ""

DISTANCE_MATRIX_URL = (
    "https://maps.googleapis.com/maps/api/distancematrix/json"
)


def _haversine_km(lat1, lon1, lat2, lon2):
  R = 6371
  phi1, phi2 = math.radians(lat1), math.radians(lat2)
  dphi = math.radians(lat2 - lat1)
  dlambda = math.radians(lon2 - lon1)
  a = (
      math.sin(dphi / 2) ** 2
      + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
  )
  return 2 * R * math.asin(math.sqrt(a))


def get_distance_matrix(
    lieux: list[dict],
) -> tuple[list[list[int]], list[list[float]]]:
  """lieux: liste de dicts avec au moins {latitude, longitude} (ou adresse si clé API dispo)

  Retourne (matrice_minutes, matrice_km)
  """
  n = len(lieux)
  if n == 0:
    return [], []

  # --- Mode 1 : Appel à Google Distance Matrix API ---
  if GOOGLE_MAPS_API_KEY:
    addresses = []
    for l in lieux:
      adr = l.get("adresse") if isinstance(l, dict) else getattr(l, "adresse", "")
      if not adr or not str(adr).strip():
        adr = "30 rue de l'Europe, 44240 La Chapelle-sur-Erdre"
      addresses.append(str(adr).strip())

    origins = "|".join(addresses)
    destinations = origins

    try:
      resp = requests.get(
          DISTANCE_MATRIX_URL,
          params={
              "origins": origins,
              "destinations": destinations,
              "mode": "driving",
              "language": "fr",
              "key": GOOGLE_MAPS_API_KEY,
          },
          timeout=15,
      )
      data = resp.json()

      if data.get("status") == "OK":
        minutes = [[0] * n for _ in range(n)]
        km = [[0.0] * n for _ in range(n)]

        for i, row in enumerate(data.get("rows", [])):
          for j, elem in enumerate(row.get("elements", [])):
            if elem.get("status") == "OK":
              minutes[i][j] = round(elem["duration"]["value"] / 60)
              km[i][j] = round(elem["distance"]["value"] / 1000, 2)
            else:
              minutes[i][j] = 9999
              km[i][j] = 9999
        return minutes, km
      else:
        st.error(
            f"Erreur API Google ({data.get('status')}):"
            f" {data.get('error_message', '')}"
        )

    except Exception as e:
      st.error(f"Erreur lors de la requête vers Google Maps : {e}")

  # --- Mode 2 : Repli Haversine si clé introuvable ou erreur ---
  minutes = [[0] * n for _ in range(n)]
  km = [[0.0] * n for _ in range(n)]
  for i in range(n):
    for j in range(n):
      if i == j:
        continue
      lat1 = lieux[i].get("latitude", 47.3333)
      lon1 = lieux[i].get("longitude", -1.5500)
      lat2 = lieux[j].get("latitude", 47.3333)
      lon2 = lieux[j].get("longitude", -1.5500)

      d = _haversine_km(lat1, lon1, lat2, lon2)
      km[i][j] = round(d, 2)
      minutes[i][j] = max(1, round(d / 40 * 60))

  return minutes, km
