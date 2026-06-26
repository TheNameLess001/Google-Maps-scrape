import streamlit as st
import pandas as pd
from playwright.sync_api import sync_playwright
import random
import time
import re
import io

# Correctif pour éviter les crashs Playwright sur Windows + Streamlit
import sys, asyncio
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

st.set_page_config(page_title="Google Maps Scraper PRO", layout="wide")

st.title("📍 Google Maps Scraper (Édition API-Like)")
st.markdown("Extrayez les données complètes des fiches Google Maps avec pré-filtrage.")

# --- BARRE DE PARAMÈTRES (SIDEBAR) ---
with st.sidebar:
    st.header("1. Ciblage Géographique")
    city = st.text_input("Ville", value="Casablanca")
    area = st.text_input("Quartier / Zone", value="Gauthier")
    keywords = st.text_input("Mots-clés (optionnel)", placeholder="ex: Italien, Sushi, Burger...")

    st.header("2. Filtres d'Écrémage")
    min_rating = st.slider("Note minimum (⭐)", min_value=0.0, max_value=5.0, value=4.2, step=0.1)
    min_reviews = st.number_input("Nombre d'avis minimum", min_value=0, value=30, step=10)
    
    st.header("3. Limites")
    max_scrolls = st.slider("Profondeur de scroll (x10 résultats)", 1, 10, 3)
    
    lancer = st.button("🚀 Lancer le Scrape PRO", type="primary", use_container_width=True)

# Fonctions utilitaires sécurisées pour Playwright
def get_safe_text(page, selector):
    loc = page.locator(selector)
    return loc.first.text_content().strip() if loc.count() > 0 else "N/A"

def get_safe_attr(page, selector, attr):
    loc = page.locator(selector)
    return loc.first.get_attribute(attr) if loc.count() > 0 else "N/A"

if lancer:
    # Construction de la requête intelligente
    query_parts = [k for k in [keywords, "Restaurant", area, city] if k.strip()]
    full_query = " ".join(query_parts)
    
    st.info(f"Recherche générée : **{full_query}**")
    
    progress_bar = st.progress(0, text="Initialisation du navigateur...")
    status_text = st.empty()
    extracted_data = []

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False) # Laissez visible !
            context = browser.new_context(viewport={"width": 1300, "height": 900}, locale="fr-FR")
            page = context.new_page()

            status_text.text("Chargement de Google Maps...")
            page.goto(f"https://www.google.com/maps/search/{full_query}")

            # Refus/Acceptation cookies RGPD auto
            try: page.click("button:has-text('Tout accepter')", timeout=3000)
            except: pass

            page.wait_for_selector('div[role="feed"]', timeout=10000)

            # ÉTAPE 1 : SCROLL DE LA LISTE
            status_text.text("Aspiration de la liste principale...")
            for _ in range(max_scrolls):
                page.keyboard.press("PageDown")
                time.sleep(random.uniform(1.2, 2.0))

            # Récupération des liens bruts
            fiches = page.locator('a[href*="/maps/place/"]').all()
            urls_uniques = list(set([f.get_attribute("href") for f in fiches if f.get_attribute("href")]))
            
            total_places = len(urls_uniques)
            status_text.text(f"{total_places} restaurants bruts trouvés. Début de l'analyse filtrée...")

            # ÉTAPE 2 : VISITE CHIRURGICALE & FILTRAGE
            for i, url in enumerate(urls_uniques):
                pct = int(((i + 1) / total_places) * 100)
                progress_bar.progress(pct, text=f"Analyse {i+1}/{total_places}...")
                
                try:
                    page.goto(url, wait_until="domcontentloaded")
                    page.wait_for_selector('h1', timeout=5000)
                    
                    # 1. Capture rapide Note et Avis pour tester le filtre
                    nom = get_safe_text(page, 'h1')
                    note_str = get_safe_text(page, 'div[role="img"][aria-label*="étoiles"]')
                    
                    # Extraction Regex propre de la note (ex: "4,6")
                    note = 0.0
                    match_note = re.search(r"(\d[.,]\d)", note_str)
                    if match_note:
                        note = float(match_note.group(1).replace(',', '.'))

                    # Extraction Regex du nombre d'avis (ex: "(128)" ou "1,2 k")
                    avis = 0
                    avis_str = get_safe_text(page, 'button[jsaction*="reviews"]')
                    match_avis = re.search(r"\(([\d\s,kK]+)\)", avis_str)
                    if match_avis:
                        clean_a = match_avis.group(1).replace(' ', '').lower()
                        if 'k' in clean_a:
                            avis = int(float(clean_a.replace('k','').replace(',','.')) * 1000)
                        else:
                            avis = int(re.sub(r"[^\d]", "", clean_a))

                    # --- LE FILTRE COUPAN-GORGE ---
                    if note < min_rating or avis < min_reviews:
                        continue # On rejette, on ne perd pas 2 sec à extraire le reste !

                    # Si on arrive ici : LE RESTO A PASSÉ LE FILTRE, ON EXTRACTE TOUT :
                    
                    # Adresse
                    adresse = get_safe_text(page, 'button[data-item-id="address"]')
                    
                    # Téléphone (Astuce pro: on le tire de l'ID du bouton, 100% fiable)
                    raw_phone = get_safe_attr(page, 'button[data-item-id^="phone:tel:"]', 'data-item-id')
                    telephone = raw_phone.replace('phone:tel:', '') if raw_phone != "N/A" else "N/A"
                    
                    # Site Web
                    site_web = get_safe_attr(page, 'a[data-item-id="authority"]', 'href')
                    
                    # Coordonnées GPS (0€ : extraites directement de l'URL Google Maps !)
                    lat, lng = "N/A", "N/A"
                    gps_match = re.search(r"@(-?\d+\.\d+),(-?\d+\.\d+)", page.url)
                    if gps_match:
                        lat, lng = gps_match.group(1), gps_match.group(2)

                    extracted_data.append({
                        "Nom": nom,
                        "Note": note,
                        "Total_Avis": avis,
                        "Telephone": telephone,
                        "Site_Web": site_web,
                        "Quartier_Cible": area,
                        "Ville": city,
                        "Adresse_Complete": adresse,
                        "Latitude": lat,
                        "Longitude": lng,
                        "Lien_Google_Maps": url
                    })

                except Exception as e:
                    continue # Fiche buggée, on passe

            browser.close()

        # AFFICHAGE FINAL
        status_text.empty()
        progress_bar.empty()

        if len(extracted_data) > 0:
            df_final = pd.DataFrame(extracted_data)
            st.success(f"🎯 Terminé ! {len(df_final)} restaurants correspondent à vos critères strictement.")
            
            st.dataframe(df_final, use_container_width=True)

            # Conversion CSV
            csv_buffer = df_final.to_csv(index=False, encoding='utf-8-sig').encode('utf-8-sig')
            
            st.download_button(
                label="📥 Télécharger le fichier Enrichi (CSV)",
                data=csv_buffer,
                file_name=f"API_Maps_{area}_{city}.csv",
                mime="text/csv"
            )
        else:
            st.warning("Aucun restaurant n'a survécu à vos filtres. Essayez de baisser la note minimum ou le nombre d'avis !")

    except Exception as fatal_e:
        st.error(f"Erreur critique lors de l'exécution : {fatal_e}")
