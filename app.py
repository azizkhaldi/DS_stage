# app.py
import streamlit as st
import requests
import json

st.set_page_config(page_title="Glovo Assistant", layout="wide")

# Sidebar avec filtres
with st.sidebar:
    st.header("🔍 Filtres")
    city = st.selectbox("Ville", ["Toutes"] + requests.get("http://localhost:8000/cities").json())
    search_type = st.selectbox("Type", ["Tout", "Magasins", "Produits"])
    max_price = st.slider("Prix max (DT)", 0, 100, 50) if search_type == "Produits" else None

# Interface principale
st.title("🤖 Assistant Glovo Intelligent")
st.write("Trouvez les meilleurs deals et livraisons près de chez vous!")

query = st.text_input("Que cherchez-vous aujourd'hui?",
                     placeholder="Ex: Pizza pas chère, Promotions supermarché, Livraison gratuite...")

if st.button("Rechercher") and query:
    with st.spinner("🔍 Recherche en cours avec IA..."):
        # Appel API
        response = requests.post(
            "http://localhost:8000/chat",
            json={"message": query, "city": city if city != "Toutes" else None}
        ).json()
    
    # Affichage réponse LLM
    st.success("💡 **Réponse IA:**")
    st.write(response['response'])
    
    # Résultats détaillés
    if response['results']:
        st.subheader("📋 Résultats trouvés:")
        
        for i, result in enumerate(response['results'][:5]):
            with st.expander(f"🔍 {result['metadata'].get('product_name', result['metadata'].get('store_name', 'Résultat'))}"):
                if result['type'] == 'product':
                    st.write(f"**🏪 Magasin:** {result['metadata']['store_name']}")
                    st.write(f"**💰 Prix:** {result['metadata']['price']}")
                    if result['metadata']['promotion'] != 'N/A':
                        st.write(f"**🎯 Promotion:** {result['metadata']['promotion']}")
                    st.write(f"**📝 Description:** {result['metadata']['description']}")
                
                else:  # store
                    st.write(f"**📍 Ville:** {result['metadata']['city']}")
                    st.write(f"**🚚 Livraison:** {result['metadata']['delivery_fee']}")
                    st.write(f"**⭐ Note:** {result['metadata']['rating']}")

# Suggestions automatiques
st.sidebar.header("💡 Suggestions")
suggestions = [
    "Pizza pas chère Tunis",
    "Promotions Monoprix",
    "Livraison gratuite Sfax",
    "Restaurants 4.5+ étoiles"
]

for suggestion in suggestions:
    if st.sidebar.button(suggestion):
        st.experimental_set_query_params(q=suggestion)
        st.rerun()