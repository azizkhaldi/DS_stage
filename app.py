import streamlit as st
import requests
import json

st.set_page_config(page_title="Glovo Assistant", layout="wide")

# Sidebar avec filtres
with st.sidebar:
    st.header("🔍 Filtres")
    
    # Gestion d'erreur pour la récupération des villes
    try:
        cities_response = requests.get("http://localhost:8000/cities", timeout=5)
        if cities_response.status_code == 200:
            available_cities = ["Toutes"] + cities_response.json()
        else:
            available_cities = ["Toutes", "Tunis", "Sfax", "Sousse", "Monastir"]
    except requests.exceptions.RequestException:
        available_cities = ["Toutes", "Tunis", "Sfax", "Sousse", "Monastir"]
    
    city = st.selectbox("Ville", available_cities)
    search_type = st.selectbox("Type", ["Tout", "Magasins", "Produits", "Vérifications", "Avis"])
    max_price = st.slider("Prix max (DT)", 0, 100, 50) if search_type == "Produits" else None

# Interface principale
st.title("🤖 Assistant Glovo Intelligent")
st.write("Trouvez les meilleurs deals, avis et vérifications près de chez vous!")

query = st.text_input("Que cherchez-vous aujourd'hui?",
                     placeholder="Ex: Pizza pas chère, Promotions supermarché, Avis restaurants, Vérifications...")

if st.button("Rechercher") and query:
    with st.spinner("🔍 Recherche en cours avec IA..."):
        try:
            # Préparer les filtres
            filters = {}
            if city != "Toutes":
                filters["city"] = city
            
            # Mapping des types de recherche
            type_mapping = {
                "Magasins": "store",
                "Produits": "product", 
                "Vérifications": "verification",
                "Avis": "review"
            }
            
            if search_type != "Tout":
                filters["doc_type"] = type_mapping.get(search_type, search_type.lower())
            
            # Appel API
            payload = {
                "message": query,
                "city": city if city != "Toutes" else None,
                "filters": filters
            }
            
            response = requests.post(
                "http://localhost:8000/chat",
                json=payload,
                timeout=15
            )
            
            if response.status_code == 200:
                result = response.json()
                
                # Affichage réponse LLM
                st.success("💡 **Réponse IA:**")
                st.write(result.get('response', 'Aucune réponse'))
                
                # Résultats détaillés
                if result.get('results'):
                    st.subheader(f"📋 {len(result['results'])} résultat(s) trouvé(s):")
                    
                    for i, item in enumerate(result['results'][:8]):
                        metadata = item.get('metadata', {})
                        item_type = item.get('type', 'unknown')
                        
                        # Titre selon le type
                        if item_type == 'product':
                            title = f"🛒 {metadata.get('product_name', 'Produit')}"
                        elif item_type == 'store':
                            title = f"🏪 {metadata.get('store_name', 'Magasin')}"
                        elif item_type == 'verification':
                            title = f"✅ {metadata.get('place_name', 'Vérification')}"
                        elif item_type == 'review':
                            title = f"⭐ Avis de {metadata.get('author', 'Utilisateur')}"
                        else:
                            title = f"🔍 Résultat {i+1}"
                        
                        with st.expander(title):
                            # Affichage selon le type
                            if item_type == 'product':
                                st.write(f"**🏪 Magasin:** {metadata.get('store_name', 'N/A')}")
                                st.write(f"**📍 Ville:** {metadata.get('city', 'N/A')}")
                                st.write(f"**💰 Prix:** {metadata.get('price', 'N/A')}")
                                if metadata.get('promotion') != 'N/A':
                                    st.write(f"**🎯 Promotion:** {metadata.get('promotion', 'N/A')}")
                                st.write(f"**📝 Description:** {metadata.get('description', 'N/A')}")
                            
                            elif item_type == 'store':
                                st.write(f"**📍 Ville:** {metadata.get('city', 'N/A')}")
                                st.write(f"**📦 Type:** {metadata.get('category_type', 'N/A')}")
                                st.write(f"**🚚 Livraison:** {metadata.get('delivery_fee', 'N/A')}")
                                st.write(f"**⏱️ Temps:** {metadata.get('delivery_time', 'N/A')}")
                                st.write(f"**⭐ Note:** {metadata.get('rating', 'N/A')}")
                                st.write(f"**📊 Avis:** {metadata.get('reviews', 'N/A')}")
                            
                            elif item_type == 'verification':
                                st.write(f"**🏢 Nom:** {metadata.get('nom', 'N/A')}")
                                st.write(f"**📍 Adresse:** {metadata.get('adresse', 'N/A')}")
                                st.write(f"**📞 Téléphone:** {metadata.get('telephone', 'N/A')}")
                                st.write(f"**✅ Statut:** {metadata.get('verification_status', 'N/A')}")
                                st.write(f"**📈 Score:** {metadata.get('best_overall_score', 'N/A')}")
                            
                            elif item_type == 'review':
                                st.write(f"**😊 Sentiment:** {metadata.get('sentiment', 'N/A')}")
                                st.write(f"**⭐ Note:** {metadata.get('sentiment_rating', 'N/A')}")
                                st.write(f"**🗣️ Langue:** {metadata.get('language', 'N/A')}")
                                st.write(f"**📅 Date:** {metadata.get('date', 'N/A')}")
                            
                            # Score de similarité
                            st.write(f"**🔍 Pertinence:** {item.get('score', 0):.2f}")
                
                # Suggestions de filtres
                if result.get('suggested_filters'):
                    st.info("💡 **Suggestions:** " + " | ".join(result['suggested_filters']))
                    
            else:
                st.error(f"❌ Erreur API: {response.status_code} - {response.text}")
                
        except requests.exceptions.RequestException as e:
            st.error("❌ Impossible de se connecter à l'API. Assurez-vous que le serveur est démarré.")
            st.error(f"Détail: {e}")
        except Exception as e:
            st.error(f"❌ Erreur: {str(e)}")

# Message d'information si l'API n'est pas disponible
try:
    # Test de connexion à l'API
    health_response = requests.get("http://localhost:8000/health", timeout=3)
    if health_response.status_code == 200:
        health_data = health_response.json()
        if health_data.get('rag_available'):
            st.sidebar.success("✅ API connectée")
        else:
            st.sidebar.warning("⚠️ API connectée mais données non chargées")
except requests.exceptions.RequestException:
    st.sidebar.error("❌ API non connectée")

# Suggestions automatiques
st.sidebar.header("💡 Suggestions rapides")
suggestions = [
    "Pizza pas chère Tunis",
    "Promotions Monoprix",
    "Livraison gratuite Sfax",
    "Restaurants 4.5+ étoiles",
    "Avis Red Castle",
    "Vérifications restaurants"
]

for suggestion in suggestions:
    if st.sidebar.button(suggestion, key=f"sugg_{suggestion}"):
        st.session_state.query = suggestion
        st.rerun()

# Documentation de l'API
with st.sidebar.expander("ℹ️ Aide"):
    st.write("""
    **Types de recherche:**
    - 🏪 **Magasins**: Restaurants, supermarchés, boutiques
    - 🛒 **Produits**: Items avec prix et promotions  
    - ✅ **Vérifications**: Données de vérification web
    - ⭐ **Avis**: Commentaires et évaluations
    
    **Exemples:**
    - `pizza tunis` - Produits
    - `restaurants 4 étoiles` - Magasins
    - `avis positifs` - Avis
    - `vérifications` - Données vérifiées
    """)

# Initialisation de la query si suggestion cliquée
if 'query' not in st.session_state:
    st.session_state.query = ""

if st.session_state.query:
    query = st.session_state.query
    st.session_state.query = ""  # Reset après utilisation
    st.rerun()

# Footer
st.sidebar.markdown("---")
st.sidebar.info("🤖 Powered by Glovo RAG API | Ollama Llama2 | Qdrant")
