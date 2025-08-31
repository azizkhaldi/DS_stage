import json
import os
import numpy as np
from typing import List, Dict, Any, Optional
from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, Distance, PointStruct
from sentence_transformers import SentenceTransformer
import ollama
from datetime import datetime
import re

class GlovoQdrantRAG:
    def __init__(self, json_directory="glovo_data", collection_name="glovo_data"):
        self.json_directory = json_directory
        self.collection_name = collection_name
        self.embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
        self.qdrant_client = QdrantClient(":memory:")  # Local pour POC
        # Pour production: QdrantClient(url="http://localhost:6333")
        
        self.data = []
        self.documents = []
        
    def initialize_qdrant(self):
        """Initialise la collection Qdrant"""
        try:
            self.qdrant_client.recreate_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(
                    size=self.embedding_model.get_sentence_embedding_dimension(),
                    distance=Distance.COSINE
                )
            )
            print("✓ Collection Qdrant initialisée")
        except Exception as e:
            print(f"✗ Erreur initialisation Qdrant: {e}")
    
    def load_and_index_data(self):
        """Charge et indexe toutes les données dans Qdrant"""
        if not self.load_json_files():
            return False
        
        self.prepare_documents()
        self.index_documents()
        return True
    
    def load_json_files(self):
        """Charge les fichiers JSON"""
        import glob
        json_files = glob.glob(os.path.join(self.json_directory, "*.json"))
        
        if not json_files:
            print("Aucun fichier JSON trouvé")
            return False
        
        for file_path in json_files:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    self.data.append(json.load(f))
            except Exception as e:
                print(f"Erreur chargement {file_path}: {e}")
        
        print(f"✓ {len(self.data)} fichiers JSON chargés")
        return True
    
    def prepare_documents(self):
        """Prépare les documents pour l'indexation"""
        print("Préparation des documents...")
        
        for city_data in self.data:
            city = city_data.get('city', 'Inconnu')
            category_type = city_data.get('category_type', 'Inconnu')
            
            for store in city_data.get('data', []):
                store_data = self._create_store_document(store, city, category_type)
                self.documents.append(store_data)
                
                for product in store.get('products', []):
                    product_data = self._create_product_document(product, store, city)
                    self.documents.append(product_data)
        
        print(f"✓ {len(self.documents)} documents préparés")
    
    def _create_store_document(self, store, city, category_type):
        """Crée un document pour un magasin"""
        store_text = f"""
        Magasin: {store.get('category_name', 'Inconnu')}
        Ville: {city}
        Type: {category_type}
        Frais livraison: {store.get('delivery_fee', 'N/A')}
        Temps livraison: {store.get('delivery_time', 'N/A')}
        Note: {store.get('rating', 'N/A')}
        Avis: {store.get('number_of_reviews', 'N/A')}
        Promotion: {store.get('promotion', 'N/A')}
        """
        
        return {
            'id': f"store_{store.get('category_name', '').lower()}_{city}",
            'type': 'store',
            'content': store_text,
            'metadata': {
                'store_name': store.get('category_name', 'Inconnu'),
                'city': city,
                'category_type': category_type,
                'delivery_fee': store.get('delivery_fee', 'N/A'),
                'delivery_time': store.get('delivery_time', 'N/A'),
                'rating': store.get('rating', 'N/A'),
                'reviews': store.get('number_of_reviews', 'N/A'),
                'promotion': store.get('promotion', 'N/A'),
                'url': store.get('category_url', '')
            }
        }
    
    def _create_product_document(self, product, store, city):
        """Crée un document pour un produit"""
        product_text = f"""
        Produit: {product.get('product_name', 'Inconnu')}
        Magasin: {store.get('category_name', 'Inconnu')}
        Ville: {city}
        Prix: {product.get('product_price', 'N/A')}
        Prix original: {product.get('original_price', 'N/A')}
        Promotion: {product.get('promotion', 'N/A')}
        Description: {product.get('description', 'N/A')}
        Section: {product.get('section', 'N/A')}
        """
        
        return {
            'id': f"product_{product.get('product_name', '').lower()}_{store.get('category_name', '').lower()}",
            'type': 'product',
            'content': product_text,
            'metadata': {
                'product_name': product.get('product_name', 'Inconnu'),
                'store_name': store.get('category_name', 'Inconnu'),
                'city': city,
                'price': product.get('product_price', 'N/A'),
                'original_price': product.get('original_price', 'N/A'),
                'promotion': product.get('promotion', 'N/A'),
                'description': product.get('description', 'N/A'),
                'section': product.get('section', 'N/A'),
                'image': product.get('product_image', 'N/A')
            }
        }
    
    def index_documents(self):
        """Indexe tous les documents dans Qdrant"""
        print("Indexation dans Qdrant...")
        
        points = []
        for i, doc in enumerate(self.documents):
            # Générer l'embedding
            embedding = self.embedding_model.encode(doc['content']).tolist()
            
            points.append(PointStruct(
                id=i,
                vector=embedding,
                payload={
                    'content': doc['content'],
                    'type': doc['type'],
                    'metadata': doc['metadata'],
                    'id': doc['id']
                }
            ))
        
        # Indexer par batch
        self.qdrant_client.upsert(
            collection_name=self.collection_name,
            points=points
        )
        
        print(f"✓ {len(points)} documents indexés dans Qdrant")
    
    def search(self, query: str, city: Optional[str] = None, 
               doc_type: Optional[str] = None, top_k: int = 10):
        """Recherche avec filtres dans Qdrant"""
        # Embedding de la requête
        query_embedding = self.embedding_model.encode(query).tolist()
        
        # Construire les filtres
        filter_conditions = {}
        if city:
            filter_conditions['metadata.city'] = city
        if doc_type:
            filter_conditions['type'] = doc_type
        
        # Recherche dans Qdrant
        search_result = self.qdrant_client.search(
            collection_name=self.collection_name,
            query_vector=query_embedding,
            query_filter=filter_conditions,
            limit=top_k
        )
        
        return [
            {
                'score': result.score,
                'content': result.payload['content'],
                'type': result.payload['type'],
                'metadata': result.payload['metadata']
            }
            for result in search_result
        ]
    
    def generate_with_llama(self, query: str, context: List[Dict]):
        """Génération de réponse avec Llama2 via Ollama"""
        # Préparer le contexte
        context_text = "\n".join([
            f"Résultat {i+1}:\n{result['content']}\n" 
            for i, result in enumerate(context[:3])
        ])
        
        prompt = f"""
        Tu es un assistant expert Glovo. Réponds en français de manière helpful et précise.

        QUESTION: {query}

        CONTEXTE:
        {context_text}

        RÉPONSE (sois concis, utilise les prix et promotions exacts, propose des alternatives si pertinent):
        """
        
        try:
            response = ollama.chat(
                model='llama2',
                messages=[{'role': 'user', 'content': prompt}],
                options={'temperature': 0.3}
            )
            return response['message']['content']
        except Exception as e:
            return f"Désolé, erreur de génération: {e}"
    
    def chat(self, query: str, city: Optional[str] = None):
        """Pipeline complet de chat"""
        # Recherche RAG
        results = self.search(query, city=city, top_k=5)
        
        # Génération avec Llama2
        if results:
            response = self.generate_with_llama(query, results)
        else:
            response = "Désolé, je n'ai pas trouvé d'informations correspondantes."
        
        return {
            'response': response,
            'results': results,
            'suggested_filters': self._suggest_filters(query, city)
        }
    
    def _suggest_filters(self, query: str, city: Optional[str]):
        """Suggère des filtres pertinents"""
        filters = []
        
        if not city and any(word in query.lower() for word in ['tunis', 'sfax', 'sousse', 'monastir']):
            filters.append("Spécifiez une ville pour des résultats plus précis")
        
        if 'promo' in query.lower() or 'réduction' in query.lower():
            filters.append("Filtre: Promotions actives")
        
        return filters

# Initialisation globale
rag_system = GlovoQdrantRAG()
rag_system.initialize_qdrant()
rag_system.load_and_index_data()