import streamlit as st
import pandas as pd
import requests
import time

st.set_page_config(page_title="Google Places API Extractor", layout="wide")

st.title("📍 Google Maps Extractor (Officiel API)")
st.markdown("Extraction propre, 100% légale et ultra-rapide via Google Cloud Places API.")

# --- BARRE DE PARAMÈTRES ---
with st.sidebar:
    st.header("🔑 Authentification")
    api_key = st.text_input(
        "Clé API Google Places", 
        type="password", 
        help="Créez votre clé sur la Google Cloud Console (APIs & Services -> Credentials)"
    )

    st.header("1. Ciblage")
    city = st.text_input("Ville", value="Casablanca")
    area = st.text_input("Quartier / Zone", value="Gauthier")
    keywords = st.text_input("Mots-clés (optionnel)", placeholder="ex: Italien, Sushi, Burger...")

    st.header("2. Filtres d'Écrémage")
    min_rating = st.slider("Note minimum (⭐)", min_value=0.0, max_value=5.0, value=4.2, step=0.1)
    min_reviews = st.number_input("Nombre d'avis minimum", min_value=0, value=30, step=10)
    
    st.header("3. Quantité")
    # L'API renvoie 20 résultats par page. 3 pages = 60 résultats max par requête.
    max_pages = st.slider("Nombre de pages (20 résultats/page)", 1, 3, 2)
    
    lancer = st.button("🚀 Lancer l'extraction API", type="primary", use_container_width=True)

if lancer:
    if not api_key:
        st.error("⚠️ Veuillez entrer une clé API Google valide dans la barre latérale.")
    else:
        # Construction de la requête
        query_parts = [k for k in [keywords, "Restaurant", area, city] if k.strip()]
        full_query = " ".join(query_parts)
        
        st.info(f"Recherche API en cours : **{full_query}**")
        
        progress_bar = st.progress(0, text="Interrogation de l'API Google...")
        extracted_data = []
        
        # Point de terminaison (Endpoint) de la nouvelle Google Places API
        url = "https://places.googleapis.com/v1/places:searchText"
        
        # Champs que nous demandons à Google de nous renvoyer (FieldMask)
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": api_key,
            "X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.rating,places.userRatingCount,places.nationalPhoneNumber,places.websiteUri,places.location,places.googleMapsUri"
        }

        payload = {
            "textQuery": full_query,
            "languageCode": "fr"
        }

        next_page_token = None

        try:
            for page_idx in range(max_pages):
                if next_page_token:
                    payload["pageToken"] = next_page_token
                    # Google impose un délai obligatoire de 2 secondes avant d'utiliser un pageToken
                    time.sleep(2) 

                response = requests.post(url, json=payload, headers=headers)
                
                if response.status_code != 200:
                    st.error(f"Erreur API Google ({response.status_code}): {response.text}")
                    break
                
                data = response.json()
                places = data.get("places", [])
                
                if not places:
                    break # Plus de résultats disponibles

                # Traitement et filtrage des résultats
                for place in places:
                    nom = place.get("displayName", {}).get("text", "N/A")
                    note = place.get("rating", 0.0)
                    avis = place.get("userRatingCount", 0)

                    # Application stricte de tes filtres
                    if note < min_rating or avis < min_reviews:
                        continue

                    adresse = place.get("formattedAddress", "N/A")
                    telephone = place.get("nationalPhoneNumber", "N/A")
                    site_web = place.get("websiteUri", "N/A")
                    maps_url = place.get("googleMapsUri", "N/A")
                    
                    location = place.get("location", {})
                    lat = location.get("latitude", "N/A")
                    lng = location.get("longitude", "N/A")

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
                        "Lien_Google_Maps": maps_url
                    })

                next_page_token = data.get("nextPageToken")
                progress_bar.progress(int(((page_idx + 1) / max_pages) * 100))
                
                if not next_page_token:
                    break # On a atteint la fin absolue de la liste Google

            progress_bar.empty()

            # Affichage des résultats
            if extracted_data:
                df_final = pd.DataFrame(extracted_data).drop_duplicates(subset=['Nom'])
                st.success(f"🎯 Extraction terminée : {len(df_final)} restaurants correspondent à vos critères !")
                st.dataframe(df_final, use_container_width=True)

                csv_buffer = df_final.to_csv(index=False, encoding='utf-8-sig').encode('utf-8-sig')
                st.download_button(
                    label="📥 Télécharger l'export Officiel (CSV)",
                    data=csv_buffer,
                    file_name=f"GoogleAPI_{area}_{city}.csv",
                    mime="text/csv",
                    type="primary"
                )
            else:
                st.warning("L'API a renvoyé des résultats, mais aucun n'a survécu à vos filtres de Note/Avis.")

        except Exception as e:
            st.error(f"Une erreur inattendue est survenue : {e}")
