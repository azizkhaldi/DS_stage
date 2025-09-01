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

def is_rag_available():
    """Vérifie si le système RAG est disponible"""
    return rag_system is not None and hasattr(rag_system, 'documents') and rag_system.documents

@app.get("/")
async def root():
    return {"status": "online", "rag_available": is_rag_available()}

@app.post("/chat")
async def chat_endpoint(request: ChatRequest):
    """Chat interactif avec IA"""
    if not is_rag_available():
        return {
            "response": "⚠️  Système en cours d'initialisation. Veuillez réessayer dans quelques secondes.",
            "results": []
        }
    
    try:
        result = rag_system.chat(request.message, request.city)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur: {str(e)}")

@app.post("/search")
async def search_endpoint(request: SearchRequest):
    """Recherche avancée avec filtres"""
    if not is_rag_available():
        return {"count": 0, "results": []}
    
    try:
        # Construire les filtres
        filters = {}
        if request.city:
            filters['city'] = request.city
        if request.store_type:
            filters['store_type'] = request.store_type
        
        results = rag_system.search(request.query, city=request.city, top_k=15)
        
        # Filtrage manuel si nécessaire
        if request.max_price or request.has_promotion:
            filtered_results = []
            for result in results:
                if request.max_price:
                    price = extract_price(result['metadata'].get('price', '0'))
                    if price > request.max_price:
                        continue
                if request.has_promotion:
                    promotion = result['metadata'].get('promotion', 'N/A')
                    if promotion == 'N/A':
                        continue
                filtered_results.append(result)
            results = filtered_results
        
        return {"count": len(results), "results": results}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur recherche: {str(e)}")

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
        stores = []
        for doc in rag_system.documents:
            if (doc.get('type') == 'store' and 
                doc.get('metadata', {}).get('city') == city):
                stores.append(doc)
        
        return {"city": city, "store_count": len(stores), "stores": stores}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur: {str(e)}")

@app.get("/health")
async def health_check():
    """Statut de santé"""
    return {
        "status": "online",
        "rag_available": is_rag_available(),
        "documents_loaded": len(rag_system.documents) if is_rag_available() else 0
    }

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
