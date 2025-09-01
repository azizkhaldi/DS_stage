from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from contextlib import asynccontextmanager
import uvicorn
import re

# Import sécurisé
try:
    from glovo_chatbot import GlovoQdrantRAG
    HAS_RAG_SYSTEM = True
except ImportError as e:
    print(f"⚠️  Import error: {e}")
    HAS_RAG_SYSTEM = False

# Initialisation
rag_system = None
if HAS_RAG_SYSTEM:
    try:
        rag_system = GlovoQdrantRAG()
        print("✅ Système RAG initialisé")
    except Exception as e:
        print(f"❌ Erreur initialisation RAG: {e}")
        rag_system = None

# Gestion moderne du lifespan
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    if HAS_RAG_SYSTEM and rag_system:
        try:
            print("🔄 Chargement des données...")
            rag_system.initialize_qdrant()
            if rag_system.load_and_index_data():
                print(f"✅ {len(rag_system.documents)} documents chargés")
            else:
                print("❌ Échec du chargement des données")
        except Exception as e:
            print(f"❌ Erreur chargement données: {e}")
    yield
    # Shutdown (optionnel)

app = FastAPI(
    title="Glovo RAG API", 
    version="1.0",
    lifespan=lifespan
)

class ChatRequest(BaseModel):
    message: str
    city: Optional[str] = None
    filters: Optional[dict] = {}

class SearchRequest(BaseModel):
    query: str
    city: Optional[str] = None
    store_type: Optional[str] = None
    max_price: Optional[float] = None
    has_promotion: Optional[bool] = None

class ReviewFilter(BaseModel):
    min_rating: Optional[int] = None
    sentiment: Optional[str] = None
    language: Optional[str] = None

class SocialFilter(BaseModel):
    platform: Optional[str] = None
    min_score: Optional[float] = None
    verified_only: Optional[bool] = None

def is_rag_available():
    """Vérifie si le système RAG est disponible"""
    return rag_system is not None and hasattr(rag_system, 'documents') and rag_system.documents

@app.get("/")
async def root():
    return {
        "status": "online", 
        "rag_available": is_rag_available(),
        "endpoints": {
            "chat": "/chat",
            "search": "/search",
            "reviews": "/reviews",
            "social": "/social",
            "verification": "/verification",
            "cities": "/cities",
            "stores": "/stores/{city}",
            "health": "/health"
        }
    }

@app.post("/chat")
async def chat_endpoint(request: ChatRequest):
    """Chat interactif avec IA - Tous types de données"""
    if not is_rag_available():
        raise HTTPException(status_code=503, detail="Système RAG non disponible")
    
    try:
        result = rag_system.chat(request.message, request.city)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur: {str(e)}")

@app.post("/search")
async def search_endpoint(request: SearchRequest):
    """Recherche avancée avec filtres - Produits et magasins"""
    if not is_rag_available():
        return {"count": 0, "results": []}
    
    try:
        results = rag_system.search(request.query, city=request.city, top_k=20)
        
        # Filtrage manuel
        filtered_results = []
        for result in results:
            metadata = result.get('metadata', {})
            
            # Filtre type de store
            if request.store_type and metadata.get('category_type') != request.store_type:
                continue
                
            # Filtre prix
            if request.max_price:
                price = extract_price(metadata.get('price', '0'))
                if price > request.max_price:
                    continue
            
            # Filtre promotion
            if request.has_promotion:
                promotion = metadata.get('promotion', 'N/A')
                if promotion == 'N/A':
                    continue
            
            filtered_results.append(result)
        
        return {"count": len(filtered_results), "results": filtered_results}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur recherche: {str(e)}")

@app.get("/reviews")
async def get_reviews(
    place_name: Optional[str] = None,
    min_rating: Optional[int] = None,
    sentiment: Optional[str] = None,
    language: Optional[str] = None,
    limit: int = 10
):
    """Endpoint pour les avis - Filter par note, sentiment, langue"""
    if not is_rag_available():
        return {"count": 0, "reviews": []}
    
    try:
        # Recherche des avis
        results = rag_system.search("avis", doc_type="review", top_k=50)
        
        filtered_reviews = []
        for result in results:
            metadata = result.get('metadata', {})
            
            # Filtre par nom de lieu
            if place_name and place_name.lower() not in result.get('content', '').lower():
                continue
                
            # Filtre par note minimale
            if min_rating:
                rating = metadata.get('sentiment_rating', 0)
                if rating < min_rating:
                    continue
            
            # Filtre par sentiment
            if sentiment and metadata.get('sentiment') != sentiment:
                continue
                
            # Filtre par langue
            if language and metadata.get('language') != language:
                continue
            
            filtered_reviews.append(result)
            
            if len(filtered_reviews) >= limit:
                break
        
        return {
            "count": len(filtered_reviews),
            "filters": {
                "place_name": place_name,
                "min_rating": min_rating,
                "sentiment": sentiment,
                "language": language
            },
            "reviews": filtered_reviews
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur avis: {str(e)}")

@app.get("/social")
async def get_social_verification(
    platform: Optional[str] = None,
    min_score: Optional[float] = None,
    verified_only: Optional[bool] = None
):
    """Endpoint pour les vérifications sociales - Facebook, Instagram"""
    if not is_rag_available():
        return {"count": 0, "verifications": []}
    
    try:
        results = rag_system.search("vérification", doc_type="verification", top_k=50)
        
        social_data = []
        for result in results:
            metadata = result.get('metadata', {})
            
            # Extraire les liens sociaux du contenu
            content = result.get('content', '')
            social_links = []
            
            if 'facebook' in content.lower():
                social_links.append('facebook')
            if 'instagram' in content.lower():
                social_links.append('instagram')
            
            # Filtre par plateforme
            if platform and platform.lower() not in [p.lower() for p in social_links]:
                continue
                
            # Filtre par score minimum
            if min_score:
                score = metadata.get('best_overall_score', 0)
                if score < min_score:
                    continue
            
            # Filtre vérifié seulement
            if verified_only and metadata.get('verification_status') != 'VERIFIED':
                continue
            
            result['metadata']['social_platforms'] = social_links
            social_data.append(result)
        
        return {
            "count": len(social_data),
            "filters": {
                "platform": platform,
                "min_score": min_score,
                "verified_only": verified_only
            },
            "verifications": social_data
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur social: {str(e)}")

@app.get("/verification")
async def get_verification_data(
    place_name: Optional[str] = None,
    min_score: Optional[float] = None,
    status: Optional[str] = None
):
    """Endpoint pour les données de vérification complètes"""
    if not is_rag_available():
        return {"count": 0, "verifications": []}
    
    try:
        results = rag_system.search("", doc_type="verification", top_k=50)
        
        filtered_verifications = []
        for result in results:
            metadata = result.get('metadata', {})
            
            # Filtre par nom de lieu
            if place_name and place_name.lower() not in metadata.get('place_name', '').lower():
                continue
                
            # Filtre par score minimum
            if min_score:
                score = metadata.get('best_overall_score', 0)
                if score < min_score:
                    continue
            
            # Filtre par statut
            if status and metadata.get('verification_status') != status:
                continue
            
            filtered_verifications.append(result)
        
        return {
            "count": len(filtered_verifications),
            "filters": {
                "place_name": place_name,
                "min_score": min_score,
                "status": status
            },
            "verifications": filtered_verifications
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur vérification: {str(e)}")

@app.get("/cities")
async def get_cities():
    """Liste des villes disponibles"""
    if not is_rag_available():
        return ["Tunis", "Sfax", "Sousse", "Monastir"]
    
    try:
        cities = set()
        for doc in rag_system.documents:
            if 'metadata' in doc and 'city' in doc['metadata']:
                cities.add(doc['metadata']['city'])
        return sorted(list(cities))
    except Exception:
        return ["Tunis", "Sfax", "Sousse", "Monastir"]

@app.get("/stores/{city}")
async def get_city_stores(city: str):
    """Magasins par ville"""
    if not is_rag_available():
        return {"city": city, "store_count": 0, "stores": []}
    
    try:
        stores = rag_system.search("", city=city, doc_type="store", top_k=100)
        return {"city": city, "store_count": len(stores), "stores": stores}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur: {str(e)}")

@app.get("/health")
async def health_check():
    """Statut de santé"""
    if not is_rag_available():
        return {"status": "offline", "rag_available": False}
    
    return {
        "status": "online",
        "rag_available": True,
        "documents_loaded": len(rag_system.documents),
        "document_types": count_document_types()
    }

def count_document_types():
    """Compte les types de documents"""
    if not is_rag_available():
        return {}
    
    type_count = {}
    for doc in rag_system.documents:
        doc_type = doc.get('type', 'unknown')
        type_count[doc_type] = type_count.get(doc_type, 0) + 1
    
    return type_count

def extract_price(price_str):
    """Extrait le prix numérique"""
    if not price_str or price_str == 'N/A':
        return float('inf')
    try:
        numeric_str = re.sub(r'[^\d.,]', '', str(price_str))
        numeric_str = numeric_str.replace(',', '.')
        return float(numeric_str)
    except:
        return float('inf')

if __name__ == "__main__":
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)
