import os
import sys
import re
import time
import random
import io
import shutil
import asyncio
import streamlit as st
import pandas as pd
from playwright.sync_api import sync_playwright

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

st.set_page_config(page_title="Google Maps Scraper PRO", layout="wide")

st.title("📍 Google Maps Scraper (Édition Cloud-Safe)")
st.markdown("Extrayez les données complètes des fiches Google Maps (Optimisé Streamlit Cloud).")

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

def get_safe_text(page, selector):
    loc = page.locator(selector)
    return loc.first.text_content().strip() if loc.count() > 0 else "N/A"

def get_safe_attr(page, selector, attr):
    loc = page.locator(selector)
    return loc.first.get_attribute(attr) if loc.count() > 0 else "N/A"

if lancer:
    query_parts = [k for k in [keywords, "Restaurant", area, city] if k.strip()]
    full_query = " ".join(query_parts)
    
    st.info(f"Recherche générée : **{full_query}**")
    
    progress_bar = st.progress(0, text="Recherche du navigateur Linux...")
    status_text = st.empty()
    extracted_data = []

    # --- LA MAGIE CLOUD : On cherche le Chromium natif installé par packages.txt ---
    system_chrome = shutil.which("chromium") or shutil.which("chromium-browser")

    try:
        with sync_playwright() as p:
            if system_chrome:
                # Mode Streamlit Cloud (100% stable, 0 RAM gaspillée)
                browser = p.chromium.launch(
                    executable_path=system_chrome,
                    headless=True,
                    args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]
                )
            else:
                # Fallback si tu testes sur ton PC Windows/Mac en local
                browser = p.chromium.launch(headless=True)
            
            context = browser.new_context(
                viewport={"width": 1300, "height": 900}, 
                locale="fr-FR",
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            )
            page = context.new_page()

            status_text.text("Connexion aux serveurs Google Maps...")
            page.goto(f"https://www.google.com/maps/search/{full_query}")

            try: page.click("button:has-text('Tout accepter')", timeout=3500)
            except: pass

            page.wait_for_selector('div[role="feed"]', timeout=12000)

            status_text.text("Aspiration de la liste principale...")
            for _ in range(max_scrolls):
                page.keyboard.press("PageDown")
                time.sleep(random.uniform(1.2, 1.8))

            fiches = page.locator('a[href*="/maps/place/"]').all()
            urls_uniques = list(set([f.get_attribute("href") for f in fiches if f.get_attribute("href")]))
            
            total_places = len(urls_uniques)
            status_text.text(f"{total_places} fiches brutes trouvées. Filtrage en cours...")

            for i, url in enumerate(urls_uniques):
                pct = int(((i + 1) / total_places) * 100)
                progress_bar.progress(pct, text=f"Analyse {i+1}/{total_places}...")
                
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=12000)
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

                    if note < min_rating or avis < min_reviews:
                        continue 

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
                    continue

            browser.close()

        status_text.empty()
        progress_bar.empty()

        if len(extracted_data) > 0:
            df_final = pd.DataFrame(extracted_data)
            st.success(f"🎯 Extraction réussie : {len(df_final)} restaurants valides !")
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
            st.warning("Aucun restaurant ne respecte ces critères.")

    except Exception as fatal_e:
        st.error(f"Erreur d'exécution : {fatal_e}")
