import os
import sys
import re
import time
import random
import io
import subprocess
import asyncio
import streamlit as st
import pandas as pd
from playwright.sync_api import sync_playwright

# --- CORRECTIFS COMPATIBILITÉ (Windows & Serveurs Cloud) ---
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
    max_scrolls = st.slider("Profondeur de scroll (x10 résultats approx.)", 1, 10, 3)
    
    lancer = st.button("🚀 Lancer le Scrape PRO", type="primary", use_container_width=True)

# Fonctions utilitaires sécurisées
def get_safe_text(page, selector):
    loc = page.locator(selector)
    return loc.first.text_content().strip() if loc.count() > 0 else "N/A"

def get_safe_attr(page, selector, attr):
    loc = page.locator(selector)
    return loc.first.get_attribute(attr) if loc.count() > 0 else "N/A"

def ensure_chromium_installed():
    """Télécharge Chromium en coulisses si le cloud l'a oublié"""
    try:
        with sync_playwright() as p:
            p.chromium.launch(headless=True, args=["--no-sandbox"]).close()
    except Exception:
        st.toast("⚠️ Premier démarrage : Installation du moteur Chromium (15 sec)...", icon="⚙️")
        subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)

if lancer:
    query_parts = [k for k in [keywords, "Restaurant", area, city] if k.strip()]
    full_query = " ".join(query_parts)
    
    st.info(f"Recherche générée : **{full_query}**")
    
    progress_bar = st.progress(0, text="Vérification de l'environnement...")
    status_text = st.empty()
    extracted_data = []

    try:
        # Vérifie ou installe le navigateur dans le cloud
        ensure_chromium_installed()
        
        progress_bar.progress(5, text="Démarrage du navigateur...")

        with sync_playwright() as p:
            # Mode Headless + Anti-sandbox obligatoires pour le Cloud
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu"
                ]
            )
            
            context = browser.new_context(
                viewport={"width": 1300, "height": 900}, 
                locale="fr-FR",
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            )
            page = context.new_page()

            status_text.text("Interrogation des serveurs Google Maps...")
            page.goto(f"https://www.google.com/maps/search/{full_query}")

            # Refus/Acceptation cookies RGPD auto
            try: page.click("button:has-text('Tout accepter')", timeout=4000)
            except: pass

            page.wait_for_selector('div[role="feed"]', timeout=12000)

            # ÉTAPE 1 : SCROLL DE LA LISTE
            status_text.text("Aspiration de la liste principale...")
            for _ in range(max_scrolls):
                page.keyboard.press("PageDown")
                time.sleep(random.uniform(1.2, 1.8))

            fiches = page.locator('a[href*="/maps/place/"]').all()
            urls_uniques = list(set([f.get_attribute("href") for f in fiches if f.get_attribute("href")]))
            
            total_places = len(urls_uniques)
            status_text.text(f"{total_places} fiches brutes trouvées. Début de l'analyse filtrée...")

            # ÉTAPE 2 : VISITE CHIRURGICALE & FILTRAGE
            for i, url in enumerate(urls_uniques):
                pct = int(((i + 1) / total_places) * 100)
                progress_bar.progress(pct, text=f"Analyse {i+1}/{total_places}...")
                
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=15000)
                    page.wait_for_selector('h1', timeout=5000)
                    
                    nom = get_safe_text(page, 'h1')
                    note_str = get_safe_text(page, 'div[role="img"][aria-label*="étoiles"]')
                    
                    note = 0.0
                    match_note = re.search(r"(\d[.,]\d)", note_str)
                    if match_note:
                        note = float(match_note.group(1).replace(',', '.'))

                    avis = 0
                    avis_str = get_safe_text(page, 'button[jsaction*="reviews"]')
                    match_avis = re.search(r"\(([\d\s,kK]+)\)", avis_str)
                    if match_avis:
                        clean_a = match_avis.group(1).replace(' ', '').lower()
                        if 'k' in clean_a:
                            avis = int(float(clean_a.replace('k','').replace(',','.')) * 1000)
                        else:
                            avis = int(re.sub(r"[^\d]", "", clean_a))

                    # Écrémage : Rejet immédiat si sous le filtre
                    if note < min_rating or avis < min_reviews:
                        continue 

                    # Aspiration complète "API-Like"
                    adresse = get_safe_text(page, 'button[data-item-id="address"]')
                    
                    raw_phone = get_safe_attr(page, 'button[data-item-id^="phone:tel:"]', 'data-item-id')
                    telephone = raw_phone.replace('phone:tel:', '') if raw_phone != "N/A" else "N/A"
                    
                    site_web = get_safe_attr(page, 'a[data-item-id="authority"]', 'href')
                    
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

                except Exception:
                    continue # On ignore les fiches corrompues

            browser.close()

        # AFFICHAGE FINAL
        status_text.empty()
        progress_bar.empty()

        if len(extracted_data) > 0:
            df_final = pd.DataFrame(extracted_data)
            st.success(f"🎯 Extraction réussie : {len(df_final)} restaurants valides conservés !")
            
            st.dataframe(df_final, use_container_width=True)

            csv_buffer = df_final.to_csv(index=False, encoding='utf-8-sig').encode('utf-8-sig')
            
            st.download_button(
                label="📥 Télécharger l'export Enrichi (CSV)",
                data=csv_buffer,
                file_name=f"Maps_PRO_{area}_{city}.csv",
                mime="text/csv",
                type="primary"
            )
        else:
            st.warning("Aucun restaurant ne respecte ces critères (Note trop haute ou pas assez d'avis).")

    except Exception as fatal_e:
        st.error(f"Erreur d'exécution : {fatal_e}")
