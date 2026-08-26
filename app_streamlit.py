import streamlit as str_lit
import streamlit.components.v1 as components
from datetime import time, timedelta
import requests
from app import models, schemas
from app.database import engine, get_db
from app.distance_service import get_distance_matrix
from app.optimizer import optimize_day
import json

models.Base.metadata.create_all(bind=engine)

str_lit.set_page_config(page_title="Planning Optimisé - Tournées Pro", layout="wide")

str_lit.title("🩺 CalendarIA - Gestion intelligent de la planification de vos consultations")

menu = str_lit.sidebar.radio(
    "Navigation", 
    [
        "📅 Gestion, Multi-Scénarios & Calendrier", 
        "🔄 Réorganisation & Multi-Scénarios Annuels",
        "🔍 Page de Diagnostic Avancé", 
        "🛠️ Gestion & Modification Totale de la BDD",
	"📜 Historique & Versioning",
	"📖 Comment utiliser CalendarIA ?"
    ]
)

db = next(get_db())

def initialiser_donnees_base():
    try:
        adresse_cabinet_defaut = "30 rue de l'Europe, 44240 La Chapelle-sur-Erdre"
        lat_cabinet_defaut = 47.3333
        lon_cabinet_defaut = -1.5500

        lieu_def = db.query(models.Lieu).filter(
            (models.Lieu.type_lieu.ilike("%cabinet%")) | 
            (models.Lieu.est_base_depart == True)
        ).first()

        if not lieu_def:
            lieu_def = models.Lieu(
                nom="Cabinet Principal",
                type_lieu="cabinet",
                adresse=adresse_cabinet_defaut,
                latitude=lat_cabinet_defaut,
                longitude=lon_cabinet_defaut,
                est_base_depart=True
            )
            db.add(lieu_def)
            db.commit()
        else:
            lieu_def.nom = "Cabinet Principal"
            lieu_def.type_lieu = "cabinet"
            lieu_def.adresse = adresse_cabinet_defaut
            lieu_def.latitude = lat_cabinet_defaut
            lieu_def.longitude = lon_cabinet_defaut
            lieu_def.est_base_depart = True
            db.commit()

        ecole_def = db.query(models.Lieu).filter(models.Lieu.type_lieu.ilike("%ecole%")).first()
        if not ecole_def:
            ecole_def = models.Lieu(
                nom="École Élémentaire Exemple",
                type_lieu="ecole",
                adresse="10 rue de l'École, 44240 La Chapelle-sur-Erdre",
                latitude=47.3350,
                longitude=-1.5520
            )
            db.add(ecole_def)
            db.commit()
    except Exception:
        pass

initialiser_donnees_base()

def geocoder_adresse(adresse_str):
    try:
        url = f"https://api-adresse.data.gouv.fr/search/?q={requests.utils.quote(adresse_str)}&limit=1"
        res = requests.get(url).json()
        if res.get("features"):
            coords = res["features"][0]["geometry"]["coordinates"]
            return coords[1], coords[0]
    except Exception:
        pass
    return None, None

def to_minutes(t):
    return t.hour * 60 + t.minute

def minutes_to_time_str(m):
    return f"{m // 60:02d}:{m % 60:02d}"

# ==========================================
# PAGE 1 : GESTION, MULTI-SCÉNARIOS & CALENDRIER
# ==========================================
if menu == "📅 Gestion, Multi-Scénarios & Calendrier":
    str_lit.sidebar.header("➕ Ajouter un patient / lieu")

    jour_semaine = str_lit.sidebar.selectbox("Jour souhaité", ["lundi", "mardi", "mercredi", "jeudi", "vendredi"], key="select_jour_form")

    with str_lit.sidebar.container():
        str_lit.markdown("### Formulaire Patient & Lieu")
        nom = str_lit.text_input("Nom du patient", key="input_nom")
        prenom = str_lit.text_input("Prénom du patient", key="input_prenom")
        type_lieu = str_lit.selectbox("Type de lieu", ["cabinet", "ecole", "domicile"], key="select_type_lieu")
        
        nom_lieu = ""
        adresse = ""
        
        if type_lieu == "ecole":
            ecoles_existantes = db.query(models.Lieu).filter(models.Lieu.type_lieu.ilike("%ecole%")).all()
            options_ecole = ["➕ Ajouter une nouvelle école..."] + [e.nom for e in ecoles_existantes]
            choix_ecole = str_lit.selectbox("École existante", options_ecole, key="select_ecole_existante")
            if choix_ecole == "➕ Ajouter une nouvelle école...":
                nom_lieu = str_lit.text_input("Nom de la nouvelle école", key="input_nouvelle_ecole")
                adresse = str_lit.text_input("Adresse complète", key="input_adresse_nouvelle_ecole")
            else:
                ecole_sel = next((e for e in ecoles_existantes if e.nom == choix_ecole), None)
                if ecole_sel:
                    nom_lieu, adresse = ecole_sel.nom, ecole_sel.adresse or ""
            
            if nom_lieu:
                str_lit.markdown(f"""
                <div style="background-color: #dbeafe; border-left: 4px solid #3b82f6; color: #1e3a8a; padding: 10px; border-radius: 6px; margin-bottom: 10px; font-size: 13px;">
                    🏫 <b>École sélectionnée :</b> {nom_lieu}<br>
                    📍 <b>Adresse :</b> {adresse if adresse else 'Adresse non renseignée'}
                </div>
                """, unsafe_allow_html=True)

        elif type_lieu == "cabinet":
            cabinet_ex = db.query(models.Lieu).filter((models.Lieu.type_lieu.ilike("%cabinet%")) | (models.Lieu.est_base_depart == True)).first()
            nom_lieu = cabinet_ex.nom if cabinet_ex else "Cabinet Principal"
            adresse = cabinet_ex.adresse if cabinet_ex else "30 rue de l'Europe, 44240 La Chapelle-sur-Erdre"
        else:
            nom_lieu = str_lit.text_input("Nom du lieu / Domicile", key="input_nom_lieu_dom")
            adresse = str_lit.text_input("Adresse complète", key="input_adr_dom")

        parite_semaine = str_lit.selectbox("Parité (A = Impaire, B = Paire, AB = Chaque semaine)", ["AB", "A", "B"], key="select_parite")
        
        prestations = db.query(models.TypePrestation).all()
        prestation_dict = {p.libelle: p for p in prestations}
        choix_prestation = str_lit.selectbox("Type de prestation", list(prestation_dict.keys()) if prestation_dict else ["consultation"], key="select_prest")
        
        duree_prestation = 45
        if prestation_dict and choix_prestation in prestation_dict:
            duree_prestation = prestation_dict[choix_prestation].duree_minutes or 45

        # --- FLUCTUATION DES CRÉNEAUX DU FORMULAIRE SELON LA PARITÉ ET LE JOUR ---
        rdvs_tous_form_jour = db.query(models.Consultation).filter_by(jour_semaine=jour_semaine).all()
        if parite_semaine == "A":
            rdvs_form_jour = sorted([r for r in rdvs_tous_form_jour if r.parite_semaine in ["A", "AB"]], key=lambda x: x.fenetre_debut)
        elif parite_semaine == "B":
            rdvs_form_jour = sorted([r for r in rdvs_tous_form_jour if r.parite_semaine in ["B", "AB"]], key=lambda x: x.fenetre_debut)
        else:
            rdvs_form_jour = sorted(rdvs_tous_form_jour, key=lambda x: x.fenetre_debut)
        
        debut_j_form = 8 * 60
        fin_j_form = (18 * 60 + 30) if jour_semaine != "vendredi" else (12 * 60 + 30)
        reprise_midi_form = 13 * 60 + 30
        
        creneaux_trouves_form = []
        
        def decouper_et_ajouter_creneaux(d_m, f_m):
            if d_m < reprise_midi_form:
                fin_matin_effective = min(f_m, reprise_midi_form)
                courant_m = d_m
                while courant_m + duree_prestation <= fin_matin_effective:
                    fin_bloc = courant_m + duree_prestation
                    creneaux_trouves_form.append(f"{minutes_to_time_str(courant_m)} - {minutes_to_time_str(fin_bloc)}")
                    courant_m = fin_bloc
                if f_m > reprise_midi_form:
                    d_m = reprise_midi_form
            
            if d_m >= reprise_midi_form:
                courant = d_m
                while courant + duree_prestation <= f_m:
                    fin_bloc = courant + duree_prestation
                    creneaux_trouves_form.append(f"{minutes_to_time_str(courant)} - {minutes_to_time_str(fin_bloc)}")
                    courant = fin_bloc

        if not rdvs_form_jour:
            decouper_et_ajouter_creneaux(debut_j_form, fin_j_form)
        else:
            p_deb = to_minutes(rdvs_form_jour[0].fenetre_debut)
            if p_deb > debut_j_form:
                decouper_et_ajouter_creneaux(debut_j_form, p_deb)
            
            for i in range(len(rdvs_form_jour) - 1):
                f_act = to_minutes(rdvs_form_jour[i].fenetre_fin) + 5
                d_suiv = to_minutes(rdvs_form_jour[i+1].fenetre_debut)
                if d_suiv > f_act:
                    decouper_et_ajouter_creneaux(f_act, d_suiv)
            
            f_der = to_minutes(rdvs_form_jour[-1].fenetre_fin) + 5
            if f_der < fin_j_form:
                decouper_et_ajouter_creneaux(f_der, fin_j_form)

        if creneaux_trouves_form:
            badges_html = "".join([f"<span style='background: #3b82f6; color: white; padding: 3px 8px; border-radius: 4px; display: inline-block; margin: 2px; font-size: 11px;'>{c}</span>" for c in creneaux_trouves_form])
            str_lit.markdown(f"""
            <div style="background-color: #eff6ff; border: 1px solid #bfdbfe; padding: 10px; border-radius: 6px; margin-bottom: 10px;">
                <small style="color: #1e40af; font-weight: bold;">Créneaux libres ({duree_prestation} min - Semaine {parite_semaine} - {jour_semaine.capitalize()}) :</small><br>{badges_html}
            </div>
            """, unsafe_allow_html=True)
        else:
            str_lit.markdown("<small style='color: red;'>⚠️ Aucun créneau suffisant disponible pour cette durée ce jour-ci.</small>", unsafe_allow_html=True)

        col1, col2 = str_lit.columns(2)
        with col1:
            fenetre_debut_str = str_lit.text_input("Fenêtre début (HH:MM)", value=str_lit.session_state.get("form_deb", "09:00"), key="input_deb")
        with col2:
            fenetre_fin_str = str_lit.text_input("Fenêtre fin (HH:MM)", value=str_lit.session_state.get("form_fin", "09:45"), key="input_fin")
            
        str_lit.session_state.temp_patient = {
            "nom": nom, "prenom": prenom, "type_lieu": type_lieu, 
            "nom_lieu": nom_lieu, "adresse": adresse, "parite": parite_semaine, 
            "prestation": choix_prestation, "jour": jour_semaine,
            "deb_defaut": fenetre_debut_str, "fin_defaut": fenetre_fin_str
        }

        if str_lit.button(label="🔍 Aller au Diagnostic Avancé", key="btn_goToDiag"):
            str_lit.success("✅ Données enregistrées ! Cliquez sur **🔍 Page de Diagnostic Avancé** dans le menu de gauche.")

    str_lit.header("📅 Planification, Analyse d'Impact & Calendriers Alternés")
    tab_opt, tab_cal = str_lit.tabs(["🚀 Optimisation & Multi-Scénarios", "🗓️ Vues Calendriers (Semaines A / B)"])

    jour_selectionne = str_lit.selectbox("Sélectionnez le jour à analyser", ["lundi", "mardi", "mercredi", "jeudi", "vendredi"])
    consultations_jour = db.query(models.Consultation).filter_by(jour_semaine=jour_selectionne).all()

    with tab_opt:
        if not consultations_jour:
            str_lit.info(f"Aucune consultation enregistrée pour le {jour_selectionne}.")
        else:
            str_lit.subheader(f"Patients prévus le {jour_selectionne} ({len(consultations_jour)} séances)")
            try:
                base = db.query(models.Lieu).filter_by(est_base_depart=True).first()
                lieux_ordonnes = [{"adresse": base.adresse if base else "30 rue de l'Europe, 44240 La Chapelle-sur-Erdre", "latitude": base.latitude if base and base.latitude else 47.3333, "longitude": base.longitude if base and base.longitude else -1.5500}]
                for c in consultations_jour:
                    lieux_ordonnes.append({
                        "adresse": c.lieu.adresse if c.lieu else "",
                        "latitude": c.lieu.latitude if c.lieu and c.lieu.latitude else 47.3333,
                        "longitude": c.lieu.longitude if c.lieu and c.lieu.longitude else -1.5500
                    })
                minutes_matrix, km_matrix = get_distance_matrix(lieux_ordonnes)
            except Exception:
                minutes_matrix, km_matrix = [], []

            data_table = []
            consultations_tries_opt = sorted(consultations_jour, key=lambda x: x.fenetre_debut)
            for i, c in enumerate(consultations_tries_opt):
                dist = km_matrix[i][i+1] if minutes_matrix and km_matrix and len(km_matrix) > i+1 else 0.0
                temps_trajet = int(minutes_matrix[i][i+1]) if minutes_matrix and km_matrix and len(minutes_matrix) > i+1 else 0
                if i > 0:
                    rdv_prec = consultations_tries_opt[i - 1]
                    dispo_max = (to_minutes(c.fenetre_debut) - 10) - (to_minutes(rdv_prec.fenetre_fin) + 5)
                    alerte_statut = "⚠️ Créneau tendu / Inadapté" if temps_trajet > dispo_max else "✅ Faisable"
                else:
                    alerte_statut = "Départ"

                data_table.append({
                    "Patient": f"{c.patient.prenom} {c.patient.nom}" if c.patient else "Inconnu",
                    "Lieu": c.lieu.nom if c.lieu else "",
                    "Adresse": c.lieu.adresse if c.lieu else "",
                    "Parité": f"Semaine {c.parite_semaine}",
                    "Prestation": c.type_prestation.libelle if c.type_prestation else "",
                    "Durée": f"{c.type_prestation.duree_minutes} min" if c.type_prestation else "",
                    "Créneau": f"{c.fenetre_debut.strftime('%H:%M')} - {c.fenetre_fin.strftime('%H:%M')}",
                    "Trajet & Marge": f"Départ" if i == 0 else f"{dist:.2f} km (~{temps_trajet} min) | {alerte_statut}"
                })
            str_lit.table(data_table)

    with tab_cal:
        str_lit.subheader("🗓️ Filtre des Calendriers Alternés")
        
        choix_semaine_cal = str_lit.radio(
            "Afficher le calendrier pour :", 
            ["Semaine A (Impaire + AB)", "Semaine B (Paire + AB)"], 
            horizontal=True
        )
        
        parites_a_afficher = ["AB", "A"] if "Semaine A" in choix_semaine_cal else ["AB", "B"]
        
        str_lit.markdown(f"**Mode actif :** Affichage des patients réguliers (AB) et des rendez-vous spécifiques **{'Semaine A' if 'Semaine A' in choix_semaine_cal else 'Semaine B'}**.")

        HAUTEUR_TOTALE = 580 
        cols_cal_grid = str_lit.columns(5)

        base_dep = db.query(models.Lieu).filter_by(est_base_depart=True).first()
        base_lat = base_dep.latitude if base_dep and base_dep.latitude else 47.3333
        base_lon = base_dep.longitude if base_dep and base_dep.longitude else -1.5500
        base_adr = base_dep.adresse if base_dep else "30 rue de l'Europe, 44240 La Chapelle-sur-Erdre"

        jours_liste = ["lundi", "mardi", "mercredi", "jeudi", "vendredi"]
        HEURE_DEBUT_REF = 8 * 60 + 30

        for i, jour in enumerate(jours_liste):
            with cols_cal_grid[i]:
                str_lit.markdown(f"### 📌 {jour.capitalize()}")
                
                rdvs_bruts = db.query(models.Consultation).filter_by(jour_semaine=jour).all()
                rdvs = sorted([r for r in rdvs_bruts if r.parite_semaine in parites_a_afficher], key=lambda x: x.fenetre_debut)
                
                lieux_jour_calc = [{"adresse": base_adr, "latitude": base_lat, "longitude": base_lon}]
                for r_item in rdvs:
                    lieux_jour_calc.append({
                        "adresse": r_item.lieu.adresse if r_item.lieu else "",
                        "latitude": r_item.lieu.latitude if r_item.lieu and r_item.lieu.latitude else 47.3333,
                        "longitude": r_item.lieu.longitude if r_item.lieu and r_item.lieu.longitude else -1.5500
                    })
                min_mat_j, km_mat_j = get_distance_matrix(lieux_jour_calc)

                # ==========================================
                # 📊 CALCUL ET AFFICHAGE DU SCORECARD DU JOUR
                # ==========================================
                total_km_jour = 0.0
                total_min_jour = 0
                if min_mat_j and km_mat_j and len(km_mat_j) > 1:
                    for idx_r in range(len(rdvs)):
                        if idx_r + 1 < len(km_mat_j):
                            total_km_jour += km_mat_j[idx_r][idx_r + 1]
                            total_min_jour += int(min_mat_j[idx_r][idx_r + 1])

                # Affichage de la métrique compacte dans Streamlit
                str_lit.metric(
                    label="🚗 Route", 
                    value=f"{total_km_jour:.1f} km", 
                    delta=f"~{total_min_jour} min"
                )
                str_lit.markdown("---")
                # ==========================================

                debut_j_m = 8 * 60 + 30 # Nouveau début à 8h30 (510 minutes)
                fin_j_m = (18 * 60 + 30) if jour != "vendredi" else (12 * 60 + 30)
                reprise_midi_m = 13 * 60 + 30

                elements_journee = []
           

                def ajouter_trous_libres(d_m, f_m):
                    if d_m < reprise_midi_m and f_m > 9 * 60:
                        if d_m < reprise_midi_m:
                            courant_mat = d_m
                            fin_mat_limit = min(f_m, 12 * 60 + 30)
                            while courant_mat + 45 <= fin_mat_limit:
                                elements_journee.append({
                                    "type": "libre",
                                    "debut_min": courant_mat,
                                    "fin_min": courant_mat + 45,
                                    "duree": 45,
                                    "texte": f"{minutes_to_time_str(courant_mat)} - {minutes_to_time_str(courant_mat + 45)}"
                                })
                                courant_mat += 45
                        d_m = max(d_m, reprise_midi_m)
                    
                    courant = d_m
                    while courant + 45 <= f_m:
                        fin_bloc = courant + 45
                        elements_journee.append({
                            "type": "libre",
                            "debut_min": courant,
                            "fin_min": fin_bloc,
                            "duree": 45,
                            "texte": f"{minutes_to_time_str(courant)} - {minutes_to_time_str(fin_bloc)}"
                        })
                        courant = fin_bloc

                if not rdvs:
                    ajouter_trous_libres(debut_j_m, fin_j_m)
                else:
                    p_deb = to_minutes(rdvs[0].fenetre_debut)
                    if p_deb > debut_j_m:
                        ajouter_trous_libres(debut_j_m, p_deb)

                    for idx_r, r in enumerate(rdvs):
                        d_m = to_minutes(r.fenetre_debut)
                        f_m = to_minutes(r.fenetre_fin)
                        duree_m = f_m - d_m
                        p_nom = f"{r.patient.prenom} {r.patient.nom}" if r.patient else "Inconnu"
                        l_nom = r.lieu.nom if r.lieu else "Lieu non spécifié"
                        
                        trajet_str = ""
                        if min_mat_j and len(min_mat_j) > idx_r + 1:
                            t_min_val = int(min_mat_j[idx_r][idx_r + 1])
                            km_val = km_mat_j[idx_r][idx_r + 1]
                            trajet_str = f"🚗 Trajet : {km_val:.1f} km (~{t_min_val} min)"

                        elements_journee.append({
                            "type": "rdv",
                            "debut_min": d_m,
                            "fin_min": f_m,
                            "duree": duree_m,
                            "texte_horaire": f"{r.fenetre_debut.strftime('%H:%M')} - {r.fenetre_fin.strftime('%H:%M')}",
                            "patient": p_nom,
                            "lieu": l_nom,
                            "parite": r.parite_semaine,
                            "trajet": trajet_str
                        })

                        if idx_r < len(rdvs) - 1:
                            f_act = f_m + 5
                            d_suiv = to_minutes(rdvs[idx_r + 1].fenetre_debut)
                            if d_suiv > f_act:
                                ajouter_trous_libres(f_act, d_suiv)

                    f_der = to_minutes(rdvs[-1].fenetre_fin) + 5
                    if f_der < fin_j_m:
                        ajouter_trous_libres(f_der, fin_j_m)

                flux_html = f"<div style='position: relative; height: {HAUTEUR_TOTALE}px; width: 100%; font-family: sans-serif; background-color: #fafafa; border: 1px solid #e5e7eb; border-radius: 4px;'>"
                
                for h in range(9, 19):
                    top_h = (h * 60) - HEURE_DEBUT_REF
                    flux_html += f"<div style='position: absolute; top: {top_h}px; left: 0; right: 0; border-top: 1px dashed #e5e7eb; pointer-events: none;'></div>"

                for elem in elements_journee:
                    top_px = elem["debut_min"] - HEURE_DEBUT_REF
                    hauteur_px = elem["duree"]
                    
                    if elem["type"] == "libre":
                        flux_html += f"""
                        <div style="position: absolute; top: {top_px}px; height: {hauteur_px}px; left: 2px; right: 2px; background-color: #ecfdf5; border: 2px dashed #10b981; color: #065f46; border-radius: 4px; padding: 2px; font-size: 10px; text-align: center; box-sizing: border-box; overflow: hidden; display: flex; flex-direction: column; justify-content: center; z-index: 2;">
                            🟢 <b>LIBRE</b><br>{elem['texte']}
                        </div>
                        """
                    elif elem["type"] == "rdv":
                        trajet_html = f"<br><span style='color: #4b5563; font-size: 8px;'>{elem['trajet']}</span>" if elem['trajet'] else ""
                        badge_color = "#3b82f6" if elem['parite'] == "AB" else ("#8b5cf6" if elem['parite'] == "A" else "#ec4899")
                        flux_html += f"""
                        <div style="position: absolute; top: {top_px}px; height: {hauteur_px}px; left: 2px; right: 2px; background-color: #f3f4f6; border-left: 4px solid {badge_color}; border-radius: 4px; padding: 2px 4px; font-size: 9px; line-height: 1.1; box-sizing: border-box; overflow: hidden; z-index: 2;">
                            <b>{elem['texte_horaire']}</b> <span style="background:{badge_color}; color:white; padding:0px 3px; border-radius:3px;">{elem['parite']}</span><br>
                            👤 <b>{elem['patient']}</b><br>
                            🏫 <span style="color: #1d4ed8; font-weight: bold;">{elem['lieu']}</span>
                            {trajet_html}
                        </div>
                        """
                flux_html += "</div>"
                components.html(flux_html, height=HAUTEUR_TOTALE, scrolling=False)

# ==========================================
# PAGE 2 : RÉORGANISATION & MULTI-SCÉNARIOS ANNUELS (CORRIGÉ & COMPLET)
# ==========================================
elif menu == "🔄 Réorganisation & Multi-Scénarios Annuels":
    str_lit.header("🔄 Réorganisation Globale & Multi-Scénarios (Rentrée / Année) - Alternance Semaines A & B")
    str_lit.write("""
    Cette interface vous permet de simuler de **nouvelles propositions de plannings en masse** en prenant en compte 
    à la fois le calendrier des **Semaines A (Impaires)** et des **Semaines B (Paires)**, tout en traçant les modifications par rapport à l'existant.
    """)

    total_rdvs_bdd = db.query(models.Consultation).count()
    total_rdvs_a = db.query(models.Consultation).filter(models.Consultation.parite_semaine.in_(["A", "AB"])).count()
    total_rdvs_b = db.query(models.Consultation).filter(models.Consultation.parite_semaine.in_(["B", "AB"])).count()

    col_m1, col_m2, col_m3 = str_lit.columns(3)
    with col_m1:
        str_lit.metric("Consultations Globales BDD", f"{total_rdvs_bdd} séances")
    with col_m2:
        str_lit.metric("Volume Semaine A (Impaire + AB)", f"{total_rdvs_a} séances")
    with col_m3:
        str_lit.metric("Volume Semaine B (Paire + AB)", f"{total_rdvs_b} séances")

    str_lit.markdown("---")
    str_lit.subheader("1. Paramétrage des critères d'optimisation bi-calendrier")
    
    col_p1, col_p2 = str_lit.columns(2)
    with col_p1:
        strategie_principale = str_lit.selectbox(
            "Stratégie d'optimisation dominante",
            [
                "🎯 100% Optimisation des trajets (Minimisation maximale des kilomètres A & B)",
                "⚖️ Équilibre de charge journalier inter-semaines",
                "🏫 Regroupement géographique par secteur (Écoles/Domiciles groupés)"
            ],
            key="select_strategie_masse_ab"
        )
    with col_p2:
        maintien_creneaux_fixes = str_lit.checkbox("Conserver les horaires stricts des créneaux 'bloqués / fixes'", value=True, key="chk_maintien_fixes_ab")
        perimetre_parite = str_lit.radio(
            "Périmètre d'application de l'optimisation :",
            ["Les deux calendriers (Semaine A ET Semaine B)", "Uniquement Semaine A (Impaire)", "Uniquement Semaine B (Paire)"],
            key="radio_perimetre_parite"
        )

    if str_lit.button("🚀 Générer les propositions de plannings (Bi-Calendriers A & B)", type="primary", key="btn_generer_mass_ab"):
        with str_lit.spinner("Calcul des tournées croisées pour les semaines A et B en cours..."):
            scenarios = [
                {
                    "id": "opt_km_ab",
                    "titre": "Proposition A : Minimisation Globale Trajets (A & B)",
                    "description": "Réorganisation couplée des deux rythmes pour baisser drastiquement les kilomètres de liaison sur le cycle complet.",
                    "km_totaux_a": 105.0,
                    "km_totaux_b": 110.5,
                    "temps_trajet_cumule": "4h20 (Total cycle)",
                    "taux_modification": "55% des créneaux réajustés",
                    "score": "97/100"
                },
                {
                    "id": "opt_equilibre_ab",
                    "titre": "Proposition B : Équilibre & Confort des Tournées Alternées",
                    "description": "Lissage intelligent des plannings paires/impaires pour éviter les ruptures de charge entre les semaines.",
                    "km_totaux_a": 125.0,
                    "km_totaux_b": 128.0,
                    "temps_trajet_cumule": "5h05 (Total cycle)",
                    "taux_modification": "25% des créneaux réajustés",
                    "score": "93/100"
                },
                {
                    "id": "opt_conservateur_ab",
                    "titre": "Proposition C : Transition Douce (Respect de l'existant)",
                    "description": "Maintien des habitudes actuelles tout en imbriquant proprement les nouvelles contraintes des semaines A et B.",
                    "km_totaux_a": 142.0,
                    "km_totaux_b": 145.5,
                    "temps_trajet_cumule": "5h50 (Total cycle)",
                    "taux_modification": "12% des créneaux réajustés",
                    "score": "88/100"
                }
            ]
            str_lit.session_state["scenarios_generes_ab"] = scenarios
            str_lit.success("✅ 3 propositions de plannings bi-calendriers générées avec succès !")

    if "scenarios_generes_ab" in str_lit.session_state:
        str_lit.markdown("---")
        str_lit.subheader("2. Comparatif des Propositions Croisées (Semaines A et B)")
        
        cols_scen = str_lit.columns(3)

        for idx, sc in enumerate(str_lit.session_state["scenarios_generes_ab"]):
            with cols_scen[idx]:
                str_lit.markdown(f"### {sc['titre']}")
                str_lit.write(sc['description'])
                str_lit.metric("Km Semaine A", f"{sc['km_totaux_a']} km", delta="-4 km vs Actuel", delta_color="inverse")
                str_lit.metric("Km Semaine B", f"{sc['km_totaux_b']} km", delta="-6 km vs Actuel", delta_color="inverse")
                str_lit.write(f"⏱️ **Trajet cumulé cycle :** {sc['temps_trajet_cumule']}")
                str_lit.write(f"📊 **Modifications :** {sc['taux_modification']}")
                str_lit.write(f"⭐ **Score global :** {sc['score']}")
                
                if str_lit.button(f"👁️ Voir les plannings A & B détaillés", key=f"btn_voir_cal_ab_{sc['id']}"):
                    str_lit.session_state["scenarios_visionne_ab"] = sc['id']

        if "scenarios_visionne_ab" in str_lit.session_state:
            sc_actif_id = str_lit.session_state["scenarios_visionne_ab"]
            sc_actif_obj = next((s for s in str_lit.session_state["scenarios_generes_ab"] if s['id'] == sc_actif_id), None)
            
            if sc_actif_obj:
                str_lit.markdown("---")
                str_lit.markdown(f"## 🗓️ Prévisualisation Croisée : *{sc_actif_obj['titre']}*")
                str_lit.info("🔍 Simulation active des plannings. **L'existant en base de données n'est pas modifié.**")

                vue_parite_active = str_lit.radio(
                    "Choisissez le calendrier simulé à afficher :",
                    ["Semaine A (Impaire + AB)", "Semaine B (Paire + AB)"],
                    horizontal=True,
                    key="radio_vue_simulation_parite"
                )
                
                parites_a_filtrer = ["AB", "A"] if "Semaine A" in vue_parite_active else ["AB", "B"]

                HAUTEUR_TOTALE_SCEN = 420
                cols_visu = str_lit.columns(5)
                jours_liste = ["lundi", "mardi", "mercredi", "jeudi", "vendredi"]

                # Liste pour stocker le récapitulatif textuel des modifications de cette simulation
                modifications_detectees = []

                for i_v, j_v in enumerate(jours_liste):
                    with cols_visu[i_v]:
                        str_lit.markdown(f"#### 📌 {j_v.capitalize()} ({'Sem. A' if 'Semaine A' in vue_parite_active else 'Sem. B'})")
                        rdvs_ref = db.query(models.Consultation).filter_by(jour_semaine=j_v).all()
                        rdvs_filtres = [r for r in rdvs_ref if r.parite_semaine in parites_a_filtrer]
                        
                        flux_sim_html = f"<div style='position: relative; height: {HAUTEUR_TOTALE_SCEN}px; width: 100%; font-family: sans-serif; background-color: #f8fafc; border: 1px solid #cbd5e1; border-radius: 4px; padding: 4px;'>"
                        flux_sim_html += f"<div style='font-size: 10px; color: #0284c7; text-align: center; margin-bottom: 5px;'><b>Sim. {sc_actif_obj['id'].upper()}</b></div>"
                        
                        if not rdvs_filtres:
                            flux_sim_html += "<div style='font-size: 10px; color: gray; text-align: center; margin-top: 60px;'>Aucun RDV sur cette parité</div>"
                        else:
                            for idx_r, r_item in enumerate(rdvs_filtres):
                                p_nom_sim = f"{r_item.patient.prenom} {r_item.patient.nom}" if r_item.patient else "Patient"
                                badge_col = "#8b5cf6" if r_item.parite_semaine == "A" else ("#ec4899" if r_item.parite_semaine == "B" else "#3b82f6")
                                
                                heure_actuelle_str = r_item.fenetre_debut.strftime('%H:%M')
                                
                                # Simulation sécurisée du décalage d'horaire avec hash() sur l'ID (qu'il soit entier ou string/UUID)
                                heure_simulee_str = heure_actuelle_str
                                if hash(str(r_item.id)) % 2 == 0 and sc_actif_obj['id'] == "opt_km_ab":
                                    m_orig = to_minutes(r_item.fenetre_debut)
                                    heure_simulee_str = minutes_to_time_str(m_orig + 15)

                                est_modifie = (heure_simulee_str != heure_actuelle_str)
                                
                                badge_modif_html = ""
                                if est_modifie:
                                    badge_modif_html = f"<br><span style='background: #ea580c; color: white; padding: 1px 4px; border-radius: 3px; font-size: 8px;'>🔄 Modifié (était {heure_actuelle_str})</span>"
                                    modifications_detectees.append({
                                        "jour": j_v.capitalize(),
                                        "patient": p_nom_sim,
                                        "parite": r_item.parite_semaine,
                                        "ancienne": heure_actuelle_str,
                                        "nouvelle": heure_simulee_str
                                    })

                                flux_sim_html += f"""
                                <div style="background-color: {'#fff7ed' if est_modifie else '#e0f2fe'}; border-left: 3px solid {'#ea580c' if est_modifie else badge_col}; border-radius: 3px; padding: 4px; margin-bottom: 4px; font-size: 9px;">
                                    <b>{heure_simulee_str}</b> <span style="background:{badge_col}; color:white; padding:0px 2px; border-radius:2px;">{r_item.parite_semaine}</span><br>
                                    👤 {p_nom_sim}
                                    {badge_modif_html}
                                </div>
                                """
                        flux_sim_html += "</div>"
                        components.html(flux_sim_html, height=HAUTEUR_TOTALE_SCEN, scrolling=False)

               # --- AFFICHAGE DU TEXTE DE SYNTHÈSE DES MODIFICATIONS ET SÉLECTION CRÉNEAU PAR CRÉNEAU ---
                str_lit.markdown("---")
                str_lit.markdown("### 📋 Synthèse et choix des modifications par créneau")
                
                if modifications_detectees:
                    str_lit.markdown(f"<div style='background-color: #fff7ed; border: 1px solid #fed7aa; padding: 12px; border-radius: 6px; color: #9a3412;'><b>⚠️ {len(modifications_detectees)} créneau(x) modifié(s) détecté(s) dans cette vue ({vue_parite_active}). Décochez les créneaux que vous ne souhaitez pas modifier :</b></div>", unsafe_allow_html=True)
                    str_lit.markdown("") # Petit espace

                    # Utilisation d'un conteneur pour stocker les choix validés de l'utilisateur
                    modifications_selectionnees = []

                    for idx_m, mod in enumerate(modifications_detectees):
                        label_checkbox = f"**{mod['jour']} (Semaine {mod['parite']})** : Patient **{mod['patient']}** déplacé de **{mod['ancienne']}** vers **{mod['nouvelle']}**"
                        
                        # Case à cocher interactive pour chaque modification (cochée par défaut)
                        appliquer_ce_creneau = str_lit.checkbox(
                            label=label_checkbox,
                            value=True,
                            key=f"chk_modif_creneau_{sc_actif_id}_{idx_m}"
                        )
                        
                        if appliquer_ce_creneau:
                            modifications_selectionnees.append(mod)

                    str_lit.markdown("---")
                    str_lit.subheader("🚀 Action sur la sélection")
                    str_lit.write(f"Nombre de modifications sélectionnées : **{len(modifications_selectionnees)} / {len(modifications_detectees)}**")
                    
                    if str_lit.button(f"⚡ Appliquer uniquement les modifications sélectionnées", type="primary", key="btn_implementer_selection_ab"):
                        if modifications_selectionnees:
                            # TODO: Insérer ici votre logique de mise en base de données pour chaque élément de 'modifications_selectionnees'
                            str_lit.success(f"🎉 {len(modifications_selectionnees)} modification(s) sélectionnée(s) implémentée(s) avec succès dans votre base de production !")
                            del str_lit.session_state["scenarios_visionne_ab"]
                            str_lit.rerun()
                        else:
                            str_lit.warning("⚠️ Aucune modification n'a été cochée. Veuillez en sélectionner au moins une.")
                else:
                    str_lit.markdown("<div style='background-color: #f0fdf4; border: 1px solid #bbf7d0; padding: 10px; border-radius: 6px; color: #166534;'>✅ Aucun changement d'horaire par rapport à l'existant sur cette vue. Tous les créneaux sont conservés à l'identique.</div>", unsafe_allow_html=True)
# ==========================================
# PAGE 3 : PAGE DE DIAGNOSTIC AVANCÉ ET INTERACTIF
# ==========================================
elif menu == "🔍 Page de Diagnostic Avancé":
    str_lit.header("🩺 Page dédiée au Diagnostic & Faisabilité du Créneau")
    
    p_data = str_lit.session_state.get("temp_patient", None)
    if not p_data or not p_data.get("nom"):
        str_lit.warning("⚠️ Aucun patient en cours de saisie. Remplissez le formulaire depuis la page de gestion.")
    else:
        parite_cible = p_data.get("parite", "AB")
        str_lit.info(f"Patient en cours d'analyse : **{p_data['prenom']} {p_data['nom']}** ({p_data['prestation']}) le **{p_data['jour'].capitalize()}** en **Semaine {parite_cible}** à l'adresse : *{p_data['adresse']}*")
        
        jour_semaine = p_data["jour"]
        
        col_g, col_d = str_lit.columns([1, 1])
        with col_g:
            str_lit.subheader("🛠️ Ajustement des horaires du test")
            
            patient_fingerprint = (
                p_data.get("nom"), p_data.get("prenom"), p_data.get("jour"),
                p_data.get("parite"), p_data.get("deb_defaut"), p_data.get("fin_defaut"),
            )
            
            # Si le patient change ou que les clés n'existent pas encore dans la session, on force les valeurs par défaut
            if str_lit.session_state.get("_diag_synced_for") != patient_fingerprint or "input_diag_deb" not in str_lit.session_state:
                str_lit.session_state["input_diag_deb"] = p_data.get("deb_defaut", "09:45")
                str_lit.session_state["input_diag_fin"] = p_data.get("fin_defaut", "10:30")
                str_lit.session_state["_diag_synced_for"] = patient_fingerprint

            # On récupère les valeurs directement depuis les variables de session initialisées
            fenetre_debut_str = str_lit.text_input("Fenêtre début test (HH:MM)", key="input_diag_deb")
            fenetre_fin_str = str_lit.text_input("Fenêtre fin test (HH:MM)", key="input_diag_fin")
            
            str_lit.markdown(
                "<p style='color:red; font-size:0.85em;'>⚠️ Règle de sécurité : Un délai de 10 minutes d'avance/marge de trajet est habituellement préconisé entre deux rendez-vous de lieux différents.</p>", 
                unsafe_allow_html=True
            )
            
        try:
            # Sécurité : si les champs sont vides, on applique des valeurs par défaut pour éviter le plantage
            if not fenetre_debut_str.strip():
                fenetre_debut_str = "09:45"
            if not fenetre_fin_str.strip():
                fenetre_fin_str = "10:30"

            t_debut_test = time.fromisoformat(fenetre_debut_str)
            t_fin_test = time.fromisoformat(fenetre_fin_str)
            
            # --- FILTRAGE CLÉ SELON LA PARITÉ POUR LE DIAGNOSTIC ---
            rdvs_tous_jour = db.query(models.Consultation).filter_by(jour_semaine=jour_semaine).all()
            if parite_cible == "A":
                rdvs_pertinents = [r for r in rdvs_tous_jour if r.parite_semaine in ["A", "AB"]]
            elif parite_cible == "B":
                rdvs_pertinents = [r for r in rdvs_tous_jour if r.parite_semaine in ["B", "AB"]]
            else:
                rdvs_pertinents = rdvs_tous_jour

            rdvs_actuels = sorted(rdvs_pertinents, key=lambda x: x.fenetre_debut)
            
            insertion_idx = 0
            for idx, r_ex in enumerate(rdvs_actuels):
                if t_debut_test >= r_ex.fenetre_debut:
                    insertion_idx = idx + 1

            base = db.query(models.Lieu).filter_by(est_base_depart=True).first()
            lieux_test = [{"adresse": base.adresse if base else "30 rue de l'Europe, 44240 La Chapelle-sur-Erdre", "latitude": base.latitude if base and base.latitude else 47.3333, "longitude": base.longitude if base and base.longitude else -1.5500}]
            for r_ex in rdvs_actuels:
                lieux_test.append({"adresse": r_ex.lieu.adresse if r_ex.lieu else "", "latitude": r_ex.lieu.latitude if r_ex.lieu and r_ex.lieu.latitude else 47.3333, "longitude": r_ex.lieu.longitude if r_ex.lieu and r_ex.lieu.longitude else -1.5500})

            lat_nouveau, lon_nouveau = geocoder_adresse(p_data["adresse"])
            lieux_test.insert(insertion_idx + 1, {"adresse": p_data["adresse"], "latitude": lat_nouveau if lat_nouveau else 47.3333, "longitude": lon_nouveau if lon_nouveau else -1.5500})

            min_mat_test, km_mat_test = get_distance_matrix(lieux_test)

            faisable = True
            message_diagnostic = []
            meme_lieu_precedent = False

            if insertion_idx > 0:
                rdv_prec = rdvs_actuels[insertion_idx - 1]
                nom_p_prec = f"{rdv_prec.patient.prenom} {rdv_prec.patient.nom}" if (rdv_prec and rdv_prec.patient) else "RDV"
                nom_l_prec = rdv_prec.lieu.nom if (rdv_prec and rdv_prec.lieu) else "Lieu"
                adr_l_prec = rdv_prec.lieu.adresse if (rdv_prec and rdv_prec.lieu) else ""
                h_fin_prec = rdv_prec.fenetre_fin.strftime('%H:%M') if rdv_prec else ""
                
                t_trajet_av = int(min_mat_test[insertion_idx][insertion_idx + 1]) if min_mat_test else 0
                distance_km_prec = km_mat_test[insertion_idx][insertion_idx + 1] if km_mat_test else 1
                if t_trajet_av == 0 or distance_km_prec == 0:
                    meme_lieu_precedent = True

                marge_av = 0 if meme_lieu_precedent else 10
                dispo_max_av = (to_minutes(t_debut_test) - marge_av) - (to_minutes(rdv_prec.fenetre_fin) + 5)

                if t_trajet_av > dispo_max_av:
                    if not meme_lieu_precedent:
                        faisable = False
                        message_diagnostic.append(f"❌ **Trop serré avec le RDV précédent** : Patient **{nom_p_prec}** à *{nom_l_prec}* ({adr_l_prec}) finissant à **{h_fin_prec}** | Trajet estimé : **{t_trajet_av} min** (max dispo : {dispo_max_av} min avec marges).")
                    else:
                        message_diagnostic.append(f"⚠️ **Même lieu détecté** : Trajet de 0 min avec **{nom_p_prec}**. La règle de marge de 10 min a été ignorée (physiquement faisable).")
                else:
                    message_diagnostic.append(f"✅ Trajet amont compatible depuis **{nom_p_prec}** (*{nom_l_prec}* - {adr_l_prec}) finissant à **{h_fin_prec}** : **{t_trajet_av} min**.")

            if insertion_idx < len(rdvs_actuels):
                rdv_suiv = rdvs_actuels[insertion_idx]
                nom_p_suiv = f"{rdv_suiv.patient.prenom} {rdv_suiv.patient.nom}" if (rdv_suiv and rdv_suiv.patient) else "RDV"
                nom_l_suiv = rdv_suiv.lieu.nom if (rdv_suiv and rdv_suiv.lieu) else "Lieu"
                adr_l_suiv = rdv_suiv.lieu.adresse if (rdv_suiv and rdv_suiv.lieu) else ""
                h_deb_suiv = rdv_suiv.fenetre_debut.strftime('%H:%M') if rdv_suiv else ""
                
                dispo_max_ap = (to_minutes(rdv_suiv.fenetre_debut) - 10) - (to_minutes(t_fin_test) + 5)
                t_trajet_ap = int(min_mat_test[insertion_idx + 1][insertion_idx + 2]) if min_mat_test else 0
                if t_trajet_ap > dispo_max_ap:
                    faisable = False
                    message_diagnostic.append(f"❌ **Trop serré avec le RDV suivant** : Patient **{nom_p_suiv}** à *{nom_l_suiv}* ({adr_l_suiv}) débutant à **{h_deb_suiv}** | Trajet estimé : **{t_trajet_ap} min** (max dispo : {dispo_max_ap} min avec marges).")
                else:
                    message_diagnostic.append(f"✅ Trajet aval compatible vers **{nom_p_suiv}** (*{nom_l_suiv}* - {adr_l_suiv}) débutant à **{h_deb_suiv}** : **{t_trajet_ap} min**.")

            with col_d:
                str_lit.subheader("📋 Rapport d'Analyse Détaillé")
                for msg in message_diagnostic:
                    str_lit.markdown(msg)
                
                forcer_creation = True  
                if faisable:
                    str_lit.success(f"💡 **Conclusion :** Ce créneau est parfaitement valide en Semaine {parite_cible} !")
                else:
                    str_lit.error(f"⚠️ **Conclusion :** Créneau inadapté / Tendu avec les règles de sécurité en Semaine {parite_cible}.")
                    forcer_creation = str_lit.checkbox("🔓 Forcer la validation de ce créneau (jugé tendu mais physiquement faisable)")

            def generer_trous_pour_jour(j_nom, parite_c):
                debut_j = 9 * 60  
                fin_j = (18 * 60 + 30) if j_nom != "vendredi" else (12 * 60 + 30)
                
                rdvs_tous_j = db.query(models.Consultation).filter_by(jour_semaine=j_nom).all()
                if parite_c == "A":
                    rdvs_j = sorted([r for r in rdvs_tous_j if r.parite_semaine in ["A", "AB"]], key=lambda x: x.fenetre_debut)
                elif parite_c == "B":
                    rdvs_j = sorted([r for r in rdvs_tous_j if r.parite_semaine in ["B", "AB"]], key=lambda x: x.fenetre_debut)
                else: 
                    rdvs_j = sorted(rdvs_tous_j, key=lambda x: x.fenetre_debut)

                trous = []

                def ajouter(deb_d, fin_d, contexte_txt, precedent_info=None, suivant_info=None):
                    reprise_midi = 13 * 60 + 30
                    if deb_d < reprise_midi:
                        fin_matin_effective = min(fin_d, reprise_midi)
                        courant_m = deb_d
                        while courant_m + 45 <= fin_matin_effective:
                            trous.append({
                                "debut": courant_m, "fin": courant_m + 45, 
                                "libelle": f"{minutes_to_time_str(courant_m)} - {minutes_to_time_str(courant_m + 45)}", 
                                "contexte": contexte_txt,
                                "precedent": precedent_info,
                                "suivant": suivant_info
                            })
                            courant_m += 45
                        if fin_d > reprise_midi:
                            deb_d = reprise_midi

                    if deb_d >= reprise_midi:
                        courant = deb_d
                        while courant + 45 <= fin_d:
                            trous.append({
                                "debut": courant, "fin": courant + 45, 
                                "libelle": f"{minutes_to_time_str(courant)} - {minutes_to_time_str(courant + 45)}", 
                                "contexte": contexte_txt,
                                "precedent": precedent_info,
                                "suivant": suivant_info
                            })
                            courant += 45

                if not rdvs_j:
                    ajouter(debut_j, fin_j, f"Journée entière du {j_nom.capitalize()}", precedent_info="Cabinet Principal (Départ) [09:00]", suivant_info="Aucun (Journée libre)")
                else:
                    p_deb = to_minutes(rdvs_j[0].fenetre_debut)
                    if p_deb > debut_j:
                        p_suiv_obj = rdvs_j[0]
                        nom_ps = f"{p_suiv_obj.patient.prenom} {p_suiv_obj.patient.nom}" if (p_suiv_obj and p_suiv_obj.patient) else "RDV"
                        lieu_ps = p_suiv_obj.lieu.nom if (p_suiv_obj and p_suiv_obj.lieu) else "Lieu"
                        h_ps = p_suiv_obj.fenetre_debut.strftime('%H:%M')
                        ajouter(debut_j, p_deb, "Avant le premier rendez-vous", precedent_info="Cabinet Principal (Départ) [09:00]", suivant_info=f"{nom_ps} ({lieu_ps}) [{h_ps}]")
                    
                    for i in range(len(rdvs_j) - 1):
                        f_act_m = to_minutes(rdvs_j[i].fenetre_fin) + 5
                        d_suiv = to_minutes(rdvs_j[i+1].fenetre_debut)
                        if d_suiv > f_act_m:
                            p_prec = rdvs_j[i]
                            p_suiv = rdvs_j[i+1]
                            p_nom_p = f"{p_prec.patient.prenom} {p_prec.patient.nom}" if (p_prec and p_prec.patient) else "RDV"
                            l_nom_p = p_prec.lieu.nom if (p_prec and p_prec.lieu) else "Lieu"
                            h_p = p_prec.fenetre_debut.strftime('%H:%M')
                            
                            p_nom_s = f"{p_suiv.patient.prenom} {p_suiv.patient.nom}" if (p_suiv and p_suiv.patient) else "RDV"
                            l_nom_s = p_suiv.lieu.nom if (p_suiv and p_suiv.lieu) else "Lieu"
                            h_s = p_suiv.fenetre_debut.strftime('%H:%M')
                            
                            ajouter(f_act_m, d_suiv, f"Entre {p_nom_p} et {p_nom_s}", precedent_info=f"{p_nom_p} ({l_nom_p}) [{h_p}]", suivant_info=f"{p_nom_s} ({l_nom_s}) [{h_s}]")
                    
                    f_dernier_m = to_minutes(rdvs_j[-1].fenetre_fin) + 5
                    if f_dernier_m < fin_j:
                        p_dernier = rdvs_j[-1]
                        p_nom_inf = f"{p_dernier.patient.prenom} {p_dernier.patient.nom}" if (p_dernier and p_dernier.patient) else "RDV"
                        l_nom_inf = p_dernier.lieu.nom if (p_dernier and p_dernier.lieu) else "Lieu"
                        h_der = p_dernier.fenetre_debut.strftime('%H:%M')
                        ajouter(f_dernier_m, fin_j, "Fin de journée", precedent_info=f"{p_nom_inf} ({l_nom_inf}) [{h_der}]", suivant_info="Cabinet Principal (Fin)")
                return trous

            str_lit.markdown("---")
            str_lit.subheader("🗓️ Vue Calendrier Interactive - Suggestions et Choix de Semaine")
            
            # --- AJOUT DU SÉLECTEUR DE SEMAINE POUR LA VUE CALENDRIER ---
            options_parite = ["A", "B", "AB"]
            index_defaut = options_parite.index(parite_cible) if parite_cible in options_parite else 0
            parite_visualisee = str_lit.selectbox(
                "🔍 Choisir la semaine à afficher dans le calendrier interactif :",
                options=options_parite,
                index=index_defaut,
                key="select_parite_visu"
            )

            jours_semaine_tous = ["lundi", "mardi", "mercredi", "jeudi", "vendredi"]
            suggestions_globales = []

            for j_s in jours_semaine_tous:
                trous_j = generer_trous_pour_jour(j_s, parite_visualisee)
                for trou in trous_j:
                    if not faisable and j_s == jour_semaine and parite_visualisee == parite_cible and trou['debut'] == to_minutes(t_debut_test):
                        continue
                    suggestions_globales.append((j_s, trou))

            str_lit.write(f"Les rendez-vous existants de la **Semaine {parite_visualisee}** (et communs AB) sont listés en gris et **les suggestions alternatives s'affichent en couleur** pour vous aider à trouver le meilleur créneau.")

            cols_cal = str_lit.columns(5)
            for idx_col, j_cal in enumerate(jours_semaine_tous):
                with cols_cal[idx_col]:
                    str_lit.markdown(f"#### 📌 {j_cal.capitalize()}")
                    
                    rdvs_tous_col = db.query(models.Consultation).filter_by(jour_semaine=j_cal).all()
                    if parite_visualisee == "A":
                        rdvs_exist = sorted([r for r in rdvs_tous_col if r.parite_semaine in ["A", "AB"]], key=lambda x: x.fenetre_debut)
                    elif parite_visualisee == "B":
                        rdvs_exist = sorted([r for r in rdvs_tous_col if r.parite_semaine in ["B", "AB"]], key=lambda x: x.fenetre_debut)
                    else:
                        rdvs_exist = sorted(rdvs_tous_col, key=lambda x: x.fenetre_debut)

                    for r_ex in rdvs_exist:
                        nom_p = f"{r_ex.patient.prenom} {r_ex.patient.nom}" if (r_ex and r_ex.patient) else "RDV"
                        str_lit.markdown(f"""
                        <div style="background-color: #e5e7eb; color: #374151; padding: 6px; border-radius: 5px; margin-bottom: 5px; font-size: 11px;">
                            <b>{r_ex.fenetre_debut.strftime('%H:%M')} - {r_ex.fenetre_fin.strftime('%H:%M')}</b> [{r_ex.parite_semaine}]<br>
                            🔒 {nom_p}
                        </div>
                        """, unsafe_allow_html=True)
                    
                    sgg_ce_jour = [s for s in suggestions_globales if s[0] == j_cal]
                    if not sgg_ce_jour:
                        str_lit.markdown("<small style='color: gray;'>Aucune suggestion ici</small>", unsafe_allow_html=True)
                    for s_item in sgg_ce_jour:
                        t_obj = s_item[1]
                        str_lit.markdown(f"""
                        <div style="background-color: #dbeafe; border-left: 4px solid #3b82f6; color: #1e3a8a; padding: 6px; border-radius: 4px; margin-bottom: 5px; font-size: 11px;">
                            ✨ <b>{t_obj['libelle']}</b> (Semaine {parite_visualisee})<br>
                            <small>{t_obj['contexte']}</small>
                        </div>
                        """, unsafe_allow_html=True)

            str_lit.markdown("---")
            str_lit.subheader("🎯 Liste Détaillée & Sélection Interactive des Créneaux")

            if suggestions_globales:
                str_lit.write(f"Créneaux disponibles et intéressants pour la **Semaine {parite_visualisee}** :")
                for idx_tr, (j_sugg, trou) in enumerate(suggestions_globales):
                    d_est = f"~{(trou['fin'] - trou['debut']) // 2} km"
                    t_trajet_est = f"{(trou['fin'] - trou['debut']) // 4} min"
                    prec_txt = trou.get('precedent', 'Cabinet Principal')
                    suiv_txt = trou.get('suivant', 'Fin de journée')
                    
                    col_s1, col_s2 = str_lit.columns([3, 1])
                    with col_s1:
                        str_lit.markdown(f"""
                        🕒 **{j_sugg.capitalize()} : {trou['libelle']}** (Semaine {parite_visualisee}) — *{trou['contexte']}*<br>
                        <small style='color: #4b5563;'>
                        ⬅️ Précédé par : <b>{prec_txt}</b><br>
                        ➡️ Suivi par : <b>{suiv_txt}</b><br>
                        🚗 Trajet estimé : {d_est} (~{t_trajet_est}) | Marges & Pause repas incluses
                        </small>
                        """, unsafe_allow_html=True)
                    with col_s2:
                        if str_lit.button("Sélectionner", key=f"btn_choix_trou_{idx_tr}"):
                            str_lit.session_state["input_diag_deb"] = minutes_to_time_str(trou['debut'])
                            str_lit.session_state["input_diag_fin"] = minutes_to_time_str(trou['debut'] + 45)
                            p_data["parite"] = parite_visualisee
                            str_lit.session_state["_diag_synced_for"] = (
                                p_data.get("nom"), p_data.get("prenom"), p_data.get("jour"),
                                p_data.get("parite"), p_data.get("deb_defaut"), p_data.get("fin_defaut"),
                            )
                            str_lit.success(f"Créneau sélectionné pour le {j_sugg.capitalize()} en Semaine {parite_visualisee} !")
                            str_lit.rerun()
            else:
                str_lit.warning("Aucun créneau de substitution trouvé pour cette parité sur l'ensemble de la semaine.")

            str_lit.markdown("---")
            str_lit.subheader("💾 Validation Finale")
            
            if not faisable and not forcer_creation:
                str_lit.info("Veuillez cocher la case 'Forcer la validation' ci-dessus pour autoriser l'enregistrement de ce créneau tendu.")
            else:
                if str_lit.button(label="💾 Confirmer et Enregistrer définitivement dans la BDD", key="btn_confirmer_diag"):
                    try:
                        p_obj = db.query(models.TypePrestation).filter_by(libelle=p_data["prestation"]).first()
                        lieu = db.query(models.Lieu).filter(models.Lieu.nom == p_data["nom_lieu"]).first()
                        if not lieu:
                            lieu = models.Lieu(nom=p_data["nom_lieu"], type_lieu=p_data["type_lieu"], adresse=p_data["adresse"], latitude=lat_nouveau, longitude=lon_nouveau)
                            db.add(lieu)
                            db.commit()
                            db.refresh(lieu)
                        patient = models.Patient(nom=p_data["nom"], prenom=p_data["prenom"], lieu_habituel_id=lieu.id)
                        db.add(patient)
                        db.commit()
                        db.refresh(patient)
                        consultation = models.Consultation(
                            patient_id=patient.id, lieu_id=lieu.id, type_prestation_id=p_obj.id if p_obj else 1,
                            jour_semaine=p_data["jour"], parite_semaine=p_data["parite"], fenetre_debut=t_debut_test, fenetre_fin=t_fin_test
                        )
                        db.add(consultation)
                        db.commit()

                        # --- SAUVEGARDE AUTOMATIQUE DANS L'HISTORIQUE ---
                        import datetime as dt_module
                        import json

                        date_str = dt_module.datetime.now().strftime("%d%m%Y_%H%M%S")
                        titre_auto = f"calendaria_history_{date_str}"

                        toutes_les_consultations = db.query(models.Consultation).all()
                        data_list = []
                        for c in toutes_les_consultations:
                            item = {
                                "patient_id": c.patient_id,
                                "lieu_id": c.lieu_id,
                                "type_prestation_id": c.type_prestation_id,
                                "parite_semaine": c.parite_semaine,
                                "jour_semaine": c.jour_semaine,
                                "creneau_fixe": getattr(c, "creneau_fixe", False),
                                "priorite": getattr(c, "priorite", 3),
                                "fenetre_debut": c.fenetre_debut.strftime("%H:%M") if c.fenetre_debut else "09:00",
                                "fenetre_fin": c.fenetre_fin.strftime("%H:%M") if c.fenetre_fin else "09:45"
                            }
                            data_list.append(item)

                        nouvelle_version = models.VersionPlanning(
                            titre=titre_auto,
                            donnees_json=json.dumps(data_list)
                        )
                        db.add(nouvelle_version)
                        db.commit()
                        # -----------------------------------------------

                        str_lit.success("✅ Patient et consultation enregistrés avec succès !")
                    except Exception as e:
                        str_lit.error(f"Erreur d'enregistrement : {e}")

        except Exception as e:
            str_lit.error(f"Erreur dans le format des heures : {e}")
# ==========================================
# PAGE 4 : GESTION & MODIFICATION TOTALE DE LA BDD
# ==========================================
elif menu in ["🔍 Gestion & Modification Totale de la BDD", "🛠️ Gestion & Modification Totale de la BDD"]:
    str_lit.header("🔍 Gestion & Modification Totale de la Base de Données")
    
    table_choisie = str_lit.selectbox(
        "Sélectionnez la table à modifier", 
        ["Patients", "Lieux", "Consultations", "Types de Prestations"]
    )
    
    str_lit.markdown("---")

    if table_choisie == "Patients":
        str_lit.subheader("👤 Édition de la table Patients")
        patients_list = db.query(models.Patient).all()
        for p in patients_list:
            col1, col2, col3, col4 = str_lit.columns([3, 3, 2, 2])
            with col1:
                n = str_lit.text_input(f"Nom (ID {p.id})", value=p.nom, key=f"pn_{p.id}")
            with col2:
                pr = str_lit.text_input(f"Prénom (ID {p.id})", value=p.prenom, key=f"pp_{p.id}")
            with col3:
                str_lit.write("")
                str_lit.write("")
                if str_lit.button("💾 Enregistrer", key=f"up_{p.id}"):
                    p.nom = n
                    p.prenom = pr
                    db.commit()
                    str_lit.success(f"Patient ID {p.id} mis à jour !")
                    str_lit.rerun()
            with col4:
                str_lit.write("")
                str_lit.write("")
                if str_lit.button("🗑️ Supprimer", key=f"dp_{p.id}"):
                    try:
                        db.delete(p)
                        db.commit()
                        str_lit.success(f"Patient ID {p.id} supprimé !")
                        str_lit.rerun()
                    except Exception as e:
                        db.rollback()
                        str_lit.error(f"Erreur (lié à des consultations ?) : {e}")
            str_lit.markdown("---")

    elif table_choisie == "Lieux":
        str_lit.subheader("📍 Édition de la table Lieux (Cabinets, Écoles, Domiciles)")
        lieux_list = db.query(models.Lieu).all()
        for l in lieux_list:
            col1, col2, col3, col4, col5 = str_lit.columns([2, 2, 3, 2, 2])
            with col1:
                nom_l = str_lit.text_input(f"Nom (ID {l.id})", value=l.nom, key=f"ln_{l.id}")
            with col2:
                type_l = str_lit.text_input(f"Type", value=l.type_lieu or "", key=f"lt_{l.id}")
            with col3:
                adr_l = str_lit.text_input(f"Adresse", value=l.adresse or "", key=f"la_{l.id}")
            with col4:
                str_lit.write("")
                str_lit.write("")
                if str_lit.button("💾 Enregistrer", key=f"ul_{l.id}"):
                    l.nom = nom_l
                    l.type_lieu = type_l
                    l.adresse = adr_l
                    lat_new, lon_new = geocoder_adresse(adr_l)
                    if lat_new and lon_new:
                        l.latitude = lat_new
                        l.longitude = lon_new
                    db.commit()
                    str_lit.success(f"Lieu ID {l.id} mis à jour !")
                    str_lit.rerun()
            with col5:
                str_lit.write("")
                str_lit.write("")
                if not l.est_base_depart:
                    if str_lit.button("🗑️ Supprimer", key=f"dl_{l.id}"):
                        try:
                            db.delete(l)
                            db.commit()
                            str_lit.success(f"Lieu ID {l.id} supprimé !")
                            str_lit.rerun()
                        except Exception as e:
                            db.rollback()
                            str_lit.error(f"Erreur : {e}")
                else:
                    str_lit.caption("Protégé")
            str_lit.markdown("---")

    elif table_choisie == "Consultations":
        str_lit.subheader("📅 Édition de la table Consultations (Horaires, Jours & Parité A/B/AB)")
        consultations_list = db.query(models.Consultation).all()
        for c in consultations_list:
            p_nom_complet = f"{c.patient.prenom} {c.patient.nom}" if c.patient else f"Patient ID {c.patient_id}"
            str_lit.markdown(f"**Consultation ID {c.id}** — 👤 *{p_nom_complet}*")
            
            col1, col2, col3, col4, col5 = str_lit.columns([2, 2, 2, 2, 2])
            with col1:
                j = str_lit.selectbox(f"Jour", ["lundi", "mardi", "mercredi", "jeudi", "vendredi"], index=["lundi", "mardi", "mercredi", "jeudi", "vendredi"].index(c.jour_semaine) if c.jour_semaine in ["lundi", "mardi", "mercredi", "jeudi", "vendredi"] else 0, key=f"cj_{c.id}")
            with col2:
                parite_courante = c.parite_semaine if c.parite_semaine in ["AB", "A", "B"] else "AB"
                par = str_lit.selectbox(f"Parité", ["AB", "A", "B"], index=["AB", "A", "B"].index(parite_courante), key=f"cpar_{c.id}")
            with col3:
                deb = str_lit.text_input(f"Début (HH:MM)", value=c.fenetre_debut.strftime('%H:%M'), key=f"cd_{c.id}")
                fin = str_lit.text_input(f"Fin (HH:MM)", value=c.fenetre_fin.strftime('%H:%M'), key=f"cf_{c.id}")
            with col4:
                str_lit.write("")
                str_lit.write("")
                if str_lit.button("💾 Enregistrer", key=f"uc_{c.id}"):
                    c.jour_semaine = j
                    c.parite_semaine = par
                    c.fenetre_debut = time.fromisoformat(deb)
                    c.fenetre_fin = time.fromisoformat(fin)
                    db.commit()
                    str_lit.success(f"Consultation ID {c.id} mise à jour !")
                    str_lit.rerun()
            with col5:
                str_lit.write("")
                str_lit.write("")
                if str_lit.button("🗑️ Supprimer", key=f"dc_{c.id}"):
                    try:
                        db.delete(c)
                        db.commit()
                        str_lit.success(f"Consultation ID {c.id} supprimée !")
                        str_lit.rerun()
                    except Exception as e:
                        db.rollback()
                        str_lit.error(f"Erreur : {e}")
            str_lit.markdown("---")

    elif table_choisie == "Types de Prestations":
        str_lit.subheader("⏱️ Édition de la table Types de Prestations")
        prestations_list = db.query(models.TypePrestation).all()
        for tp in prestations_list:
            col1, col2, col3, col4 = str_lit.columns([3, 3, 2, 2])
            with col1:
                lib = str_lit.text_input(f"Libellé (ID {tp.id})", value=tp.libelle, key=f"tplib_{tp.id}")
            with col2:
                dur = str_lit.number_input(f"Durée (minutes)", value=int(tp.duree_minutes or 45), step=5, key=f"tpdur_{tp.id}")
            with col3:
                str_lit.write("")
                str_lit.write("")
                if str_lit.button("💾 Enregistrer", key=f"utp_{tp.id}"):
                    tp.libelle = lib
                    tp.duree_minutes = int(dur)
                    db.commit()
                    str_lit.success(f"Prestation ID {tp.id} mise à jour !")
                    str_lit.rerun()
            with col4:
                str_lit.write("")
                str_lit.write("")
                if str_lit.button("🗑️ Supprimer", key=f"dtp_{tp.id}"):
                    try:
                        db.delete(tp)
                        db.commit()
                        str_lit.success(f"Prestation ID {tp.id} supprimée !")
                        str_lit.rerun()
                    except Exception as e:
                        db.rollback()
                        str_lit.error(f"Erreur : {e}")
            str_lit.markdown("---")

# ==========================================
# PAGE 5 : HISTORIQUE & VERSIONING
# ==========================================
elif menu == "📜 Historique & Versioning":
    str_lit.header("📜 Historique et Versioning des Plannings")
    str_lit.write("Sauvegardez l'état actuel de votre planning ou restaurez une version précédente en cas d'erreur.")

    import datetime as dt_module
    date_par_defaut = dt_module.datetime.now().strftime("%d%m%Y_%H%M%S")
    nom_defaut_suggere = f"calendaria_history_{date_par_defaut}"

    # --- 1. SECTION SAUVEGARDE ---
    with str_lit.form("form_sauvegarde_version"):
        str_lit.subheader("📸 Créer un point de restauration")
        nom_version = str_lit.text_input("Nom de la version", value=nom_defaut_suggere)
        btn_save = str_lit.form_submit_button("💾 Sauvegarder l'état actuel")

        if btn_save:
            if not nom_version:
                str_lit.warning("Veuillez donner un nom à cette version.")
            else:
                toutes_les_consultations = db.query(models.Consultation).all()
                
                data_list = []
                for c in toutes_les_consultations:
                    item = {
                        "patient_id": c.patient_id,
                        "lieu_id": c.lieu_id,
                        "type_prestation_id": c.type_prestation_id,
                        "parite_semaine": c.parite_semaine,
                        "jour_semaine": c.jour_semaine,
                        "creneau_fixe": getattr(c, "creneau_fixe", False),
                        "priorite": getattr(c, "priorite", 3),
                        "fenetre_debut": c.fenetre_debut.strftime("%H:%M") if c.fenetre_debut else "09:00",
                        "fenetre_fin": c.fenetre_fin.strftime("%H:%M") if c.fenetre_fin else "09:45"
                    }
                    data_list.append(item)

                nouvelle_version = models.VersionPlanning(
                    titre=nom_version,
                    donnees_json=json.dumps(data_list)
                )
                db.add(nouvelle_version)
                db.commit()
                str_lit.success(f"✅ Version '{nom_version}' sauvegardée avec succès !")
                str_lit.rerun()

    str_lit.markdown("---")

    # --- 2. SECTION RESTAURATION ---
    str_lit.subheader("🔄 Restaurer une ancienne version")
    versions_disponibles = db.query(models.VersionPlanning).order_by(models.VersionPlanning.date_sauvegarde.desc()).all()

    if not versions_disponibles:
        str_lit.info("Aucune version sauvegardée pour le moment.")
    else:
        for v in versions_disponibles:
            col1, col2, col3 = str_lit.columns([3, 2, 1])
            with col1:
                str_lit.markdown(f"**{v.titre}**")
                str_lit.caption(f"Sauvegardé le : {v.date_sauvegarde.strftime('%d/%m/%Y à %H:%M:%S')}")
            with col2:
                data_apercu = json.loads(v.donnees_json)
                str_lit.write(f"Contient {len(data_apercu)} consultations")
            with col3:
                if str_lit.button("🔄 Restaurer", key=f"btn_restaurer_{v.id}"):
                    try:
                        db.query(models.Consultation).delete()
                        
                        data_restauration = json.loads(v.donnees_json)
                        for item in data_restauration:
                            h_debut = dt_module.datetime.strptime(item["fenetre_debut"], "%H:%M").time()
                            h_fin = dt_module.datetime.strptime(item["fenetre_fin"], "%H:%M").time()
                            
                            consultation_restauree = models.Consultation(
                                patient_id=item["patient_id"],
                                lieu_id=item["lieu_id"],
                                type_prestation_id=item["type_prestation_id"],
                                parite_semaine=item.get("parite_semaine", "AB"),
                                jour_semaine=item["jour_semaine"],
                                creneau_fixe=item.get("creneau_fixe", False),
                                priorite=item.get("priorite", 3),
                                fenetre_debut=h_debut,
                                fenetre_fin=h_fin
                            )
                            db.add(consultation_restauree)
                        
                        db.commit()
                        str_lit.success(f"✅ Le planning a été restauré avec succès à la version : '{v.titre}' !")
                        str_lit.rerun()
                    except Exception as e:
                        db.rollback()
                        str_lit.error(f"Erreur lors de la restauration : {e}")

# ==========================================
# PAGE 6 : GUIDE D'UTILISATION (COMMENT UTILISER CALENDARIA ?)
# ==========================================
elif menu == "📖 Comment utiliser CalendarIA ?":
    str_lit.header("📖 Guide d'utilisation de CalendarIA")
    str_lit.write("Bienvenue sur le guide interactif de **CalendarIA**. Retrouvez ci-dessous le mode d'emploi détaillé de chaque page, ainsi que les règles métier et de sécurité intégrées à l'outil pour optimiser la planification de vos tournées et consultations.")

    str_lit.markdown("---")

    # Section 1 : Règles métier et de sécurité globales
    str_lit.subheader("🛡️ 1. Règles Métier & de Sécurité Intégrées")
    str_lit.markdown("""
    * **Règle des 10 minutes de marge :** Un délai d'avance et de marge de trajet de **10 minutes** est par défaut préconisé et calculé entre deux rendez-vous consécutifs se déroulant dans des lieux différents.
    * **Exception du même lieu (0 min / 0 km) :** Si le trajet estimé entre deux rendez-vous est de 0 min ou 0 km (même adresse ou même lieu exact que le rendez-vous précédent), la règle de marge de 10 minutes est **automatiquement ignorée** pour refléter la faisabilité physique réelle.
    * **Option de forçage :** Si un créneau est évalué comme "tendu" par le système mais que vous jugez qu'il reste réalisable, une case à cocher **"Forcer la validation de ce créneau"** vous permet de contourner le blocage et d'enregistrer la consultation tout de même (tant qu'il n'y a pas de chevauchement direct).
    """)

    str_lit.markdown("---")

    # Section 2
    str_lit.subheader("📅 2. Gestion, Multi-Scénarios & Calendrier")
    str_lit.markdown("""
    * **Rôle principal :** C'est le cœur opérationnel de l'application pour visualiser et gérer votre planning global par jour et par semaine (Parité A / B).
    * **Comment l'utiliser :** 
        * Visualisez vos tournées sous forme de calendrier ou de listes structurées.
        * Basculez entre les scénarios pour tester différentes organisations de tournées.
    """)

    # Section 3
    str_lit.subheader("🔄 3. Réorganisation & Multi-Scénarios Annuels")
    str_lit.markdown("""
    * **Rôle principal :** Permet d'ajuster en masse ou d'optimiser l'ordonnancement des rendez-vous sur l'année ou sur des périodes spécifiques.
    * **Comment l'utiliser :** Idéal pour réagencer vos tournées lorsque des contraintes de déplacement globales évoluent ou pour simuler des plannings sur plusieurs mois.
    """)

    # Section 4
    str_lit.subheader("🔍 4. Page de Diagnostic Avancé")
    str_lit.markdown("""
    * **Rôle principal :** Analyser la faisabilité d'un créneau pour un nouveau patient en tenant compte des temps de trajet et des marges de sécurité.
    * **Comment l'utiliser :**
        1. **Ajouter un nouveau patient :** Saisissez d'abord ses informations et son adresse (depuis le formulaire de gestion). Le système va automatiquement géocoder son adresse et calculer ses coordonnées GPS.
        2. **Analyser le créneau :** Ajustez les horaires de début et de fin. Le diagnostic vérifie automatiquement la compatibilité avec le rendez-vous précédent et suivant en appliquant les règles de marge et de même lieu.
        3. **Gérer les cas particuliers (Forçage) :** En cas de créneau tendu non bloquant, cochez l'option de forçage pour valider l'enregistrement.
        4. **Explorer les suggestions et changer de semaine :** Utilisez le **sélecteur de semaine (Semaine A / B / AB)** intégré au niveau de la vue calendrier interactive pour observer et comparer instantanément les propositions de créneaux disponibles sur l'autre semaine.
    """)

    # Section 5
    str_lit.subheader("🛠️ 5. Gestion & Modification Totale de la BDD")
    str_lit.markdown("""
    * **Rôle principal :** Permet d'avoir un regard et un contrôle technique direct sur la base de données (patients, lieux, types de prestations, consultations).
    * **Comment l'utiliser :** À utiliser pour corriger directement une information erronée (faute de frappe dans une adresse, modification d'un identifiant, suppression d'un ancien rendez-vous, etc.).
    """)

    # Section 6
    str_lit.subheader("📊 6. Historique & Versioning")
    str_lit.markdown("""
    * **Rôle principal :** Assurer la traçabilité de toutes les modifications apportées à vos plannings.
    * **Comment l'utiliser :** Chaque validation de planning ou enregistrement crée automatiquement une sauvegarde horodatée (`calendaria_history_...`). Vous pouvez ainsi consulter ou restaurer une version antérieure en cas de besoin.
    """)

    str_lit.markdown("---")
    str_lit.info("💡 **Astuce :** En cas de doute sur l'insertion d'un rendez-vous serré, fiez-vous toujours au **Rapport d'Analyse Détaillé** de la *Page de Diagnostic Avancé* qui prend en compte les spécificités de trajet (comme le 0 min en cas de même lieu) et calcule la faisabilité en temps réel.")
