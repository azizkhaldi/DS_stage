# api.py
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional, List
import uvicorn

app = FastAPI(title="Glovo RAG API Qdrant", version="1.0")

class ChatRequest(BaseModel):
    message: str
    city: Optional[str] = None
    filters: Optional[dict] = None

class SearchRequest(BaseModel):
    query: str
    city: Optional[str] = None
    store_type: Optional[str] = None
    max_price: Optional[float] = None
    has_promotion: Optional[bool] = None

@app.post("/chat")
async def chat_endpoint(request: ChatRequest):
    """Endpoint de chat interactif"""
    try:
        result = rag_system.chat(request.message, request.city)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/search")
async def search_endpoint(request: SearchRequest):
    """Recherche avancée avec filtres"""
    try:
        # Construire les filtres Qdrant
        filters = {}
        if request.city:
            filters['metadata.city'] = request.city
        if request.store_type:
            filters['metadata.category_type'] = request.store_type
        if request.has_promotion:
            filters['metadata.promotion'] = {'$ne': 'N/A'}
        
        results = rag_system.search(
            request.query, 
            city=request.city,
            top_k=15
        )
        
        # Filtrer par prix si spécifié
        if request.max_price:
            results = [r for r in results if self._extract_price(r['metadata']['price']) <= request.max_price]
        
        return {
            'count': len(results),
            'results': results
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/cities")
async def get_cities():
    """Liste toutes les villes disponibles"""
    cities = set()
    for doc in rag_system.documents:
        if 'city' in doc['metadata']:
            cities.add(doc['metadata']['city'])
    return sorted(list(cities))

@app.get("/stores/{city}")
async def get_city_stores(city: str):
    """Magasins d'une ville spécifique"""
    stores = rag_system.search("", city=city, doc_type='store', top_k=50)
    return {
        'city': city,
        'store_count': len(stores),
        'stores': stores
    }

def _extract_price(price_str):
    """Extrait le prix numérique"""
    try:
        return float(re.sub(r'[^\d.,]', '', price_str).replace(',', '.'))
    except:
        return float('inf')

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)