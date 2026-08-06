# POC — Planning optimisé de consultations

## Ce que fait ce POC

Optimise l'ordre des consultations d'**une journée** pour minimiser le temps
de trajet total, en respectant les fenêtres horaires de chaque rendez-vous
(y compris les créneaux fixes des bilans). Le point de départ/retour est le
lieu marqué `est_base_depart = true`.

Simplifications volontaires pour aller vite :
- Une seule journée à la fois (pas encore la répartition automatique sur
  toute la semaine ni la parité A/B — l'algorithme central est le même,
  cette partie s'ajoutera une fois le POC validé).
- SQLite au lieu de Postgres (bascule triviale plus tard : changer
  `DATABASE_URL` dans `app/database.py`).
- Sans clé Google Maps, les distances sont estimées à vol d'oiseau — assez
  fiable pour valider le concept, mais à activer pour la vraie précision.

## Installation

```bash
cd poc
python3 -m venv venv
source venv/bin/activate   # Windows : venv\Scripts\activate
pip install -r requirements.txt
```

## (Optionnel) Activer les vraies distances Google Maps

```bash
export GOOGLE_MAPS_API_KEY="ta_clé_ici"   # Windows : set GOOGLE_MAPS_API_KEY=ta_clé_ici
```

Sans cette variable, le calcul de distance utilise une estimation à vol
d'oiseau (suffisant pour tester le moteur d'optimisation).

## Lancer le serveur

```bash
uvicorn app.main:app --reload
```

Ouvre ensuite **http://127.0.0.1:8000** dans le navigateur — c'est
directement l'interface de test (le serveur sert aussi le frontend).

La doc interactive de l'API (utile pour créer des lieux/patients/
consultations à la main) est sur **http://127.0.0.1:8000/docs**.

## Insérer rapidement des données de démo

Dans un second terminal, serveur toujours lancé :

```bash
python seed_demo.py
```

Puis, dans le navigateur, sélectionne "Mardi" et clique sur "Optimiser".

## Prochaines étapes (après validation du POC)

1. Répartition automatique des consultations sur la semaine (pas juste un
   jour à la fois) + gestion de la parité A/B.
2. Passage à Postgres + schéma complet (`schema_planning_consultations.sql`
   fourni précédemment).
3. Fonctionnalité d'ajout d'un nouveau patient avec proposition de 2-3
   créneaux d'insertion et % d'impact sur le planning existant.
4. Cache des distances en base (`distances_cache`) au lieu de recalculer
   à chaque optimisation.
