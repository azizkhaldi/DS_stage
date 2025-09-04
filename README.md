# 🤖 OmniData Chatbot – Web, Social Media & Glovo Intelligence Suite

Cette suite intelligente permet de scraper, structurer, analyser et exploiter des données multi-sources (Google Maps, Facebook, Instagram, Glovo) pour les restaurants et commerces en Tunisie.

Elle combine Playwright, BeautifulSoup, LangChain, LangGraph, LLM (Ollama/Llama2), OCR et NLP pour obtenir des données fiables, enrichies et prêtes à l’usage.
Un chatbot RAG (Retrieval-Augmented Generation) exploite ces données via Qdrant, FastAPI et Streamlit.

---
# 📌 Fonctionnalités principales

🌍 Web scraping multi-sources : Google Maps, Glovo, Facebook, Instagram.

🧠 Structuration intelligente des données avec LangChain + LangGraph + LLM (Ollama/Llama2).

🔎 Vérification & scoring automatique (fuzzy matching, numéros de téléphone, adresses).

💬 Chatbot RAG avec recherche sémantique, filtres (ville, promo, prix, type de produit).

🖼️ OCR (locr) intégré pour détecter automatiquement les promotions dans les images (stories, posts).

📊 Analyse NLP avancée : sentiment, aspects (service, food, price, ambiance…), extraction de mots-clés.

🌐 API REST (FastAPI) + Interface utilisateur (Streamlit).

⚡ Support multilingue (français, anglais, arabe, tunisien).
-----

## 1️⃣ `webscraper.py`

📂 **Fichier d’entrée :** `places.jsonl`  
📦 **Fichier de sortie :** `result.json`  

### 🔹 Workflow
1. **Scraping Google (Playwright)**
   - Simulation navigateur (User-Agent, scroll)
   - Gestion CAPTCHA
   - Extraction HTML brut
2. **Parsing & Nettoyage (BeautifulSoup)**
   - Suppression balises inutiles (script, style…)
   - Extraction texte pertinent (adresse, horaires, avis…)
   - Extraction liens (Facebook, Instagram, site web…)
3. **Analyse & Filtrage des Liens**
   - Règles strictes pour réseaux sociaux
   - Normalisation & dédoublonnage des URLs
4. **Extraction Structurée (LLM - Ollama + LangChain)**
   - JSON structuré : nom, adresse, téléphone…
   - Brochure marketing concise
   - Sélection liens pertinents
5. **Validation & Stockage**
   - Vérification JSON (`regex` + `json.loads`)
   - Ajout métadonnées (timestamp, longueur texte…)
   - Sauvegarde → `result.json`

---
<img width="747" height="801" alt="image" src="https://github.com/user-attachments/assets/e03a841a-f8dc-471b-9a3b-00ec1d603720" />  <img width="1038" height="182" alt="image" src="https://github.com/user-attachments/assets/a89d71b9-1dce-4bc0-aa6b-08a86139803c" />


## 2️⃣ `social_media_verification.py`

📂 **Fichier d’entrée :** `result.json`  
📦 **Fichier de sortie :** `verification_results.json`  

### 🔹 Workflow
1. **Initialisation Navigateur (Playwright)**
   - Chromium headless=False
   - Contexte + page configurés (User-Agent, viewport)
2. **Connexion Facebook**
   - Login manuel
   - Session authentifiée prête pour scraping
3. **Scraping Réseaux Sociaux**
   - Facebook : page « À propos » (scroll + contenu complet)
   - Instagram : header du profil et extraction du nom
   - Gestion erreurs & timeout
4. **Analyse & Vérification**
   - Normalisation numéros de téléphone
   - Calcul score correspondance nom (`fuzz.partial_ratio`)
   - Détection adresse dans texte ou nom profil
   - Vérification téléphone
   - Calcul score global pondéré
5. **Agrégation & Statut Global**
   - Meilleur score par restaurant
   - Statut : `VERIFIED / LIKELY_CORRECT / UNVERIFIED`
6. **Sauvegarde & Fermeture**
   - Résultats → `verification_results.json`

### 🔹 Modèles IA utilisés
| Modèle | Usage |
|--------|-------|
| `all-mpnet-base-v2` | Comparaison sémantique générale (nom, texte) |
| `paraphrase-multilingual-MiniLM-L12-v2` | Comparaison adresses multilingue (courtes) |

### 🔹 Composantes du score global
| Composante | Description | Poids |
|------------|------------|-------|
| `name_score` | Similarité fuzzy nom JSON vs texte social | 1 |
| `address_score` | Similarité fuzzy adresse + bonus si détectée dans nom | 3 |
| `phone` | Vérification correspondance téléphone | 2 |

**Formule :**

overall_score = ((name_score×1) + (address_score×3) + (phone_score×2)) / (1+3+2)
# Interprétation

- **≥ 0.6 → VERIFIED**  
- **0.4 – 0.6 → LIKELY_CORRECT**  
- **< 0.4 → UNVERIFIED**

  
- **Remarque :** parmi tous les liens vérifiés (Facebook, Instagram), celui qui obtient le score le plus élevé détermine si l'établissement est marqué comme `VERIFIED`.

---
<img width="1040" height="831" alt="image" src="https://github.com/user-attachments/assets/8adcd10d-a74d-4429-b132-42469f1a28a0" />

## 3️⃣ pub_scraper.py

- **Fichier d’entrée :** `verification_results.json`  
- **Fichier de sortie :** `social_media_data_final.json`  

### Workflow
1. Initialisation navigateur Chromium (desktop)  
2. Connexion réseaux sociaux (Facebook, Instagram)  
3. Navigation & interaction humaine simulée (scroll + délais aléatoires)  
4. Extraction contenu visible (texte nettoyé)  
5. Extraction métadonnées : likes, commentaires, partages, description  
6. Scraping multimédia : photos, stories, posts  
7. Sauvegarde progressive + timestamp  

---
<img width="1844" height="758" alt="image" src="https://github.com/user-attachments/assets/d901e8eb-2338-4588-9a2d-0f3e2aa38622" />

## 4️⃣ storie_scraper.py

- **Fichier d’entrée :** URL Instagram  
- **Fichier de sortie :** `stories_test_result_xxx.json`  

### Workflow
1. Initialisation navigateur (Playwright)  
2. Connexion Instagram (login manuel)  
3. Détection stories  
4. Capture stories : screenshot + texte visible
5. Analyse OCR des captures pour détecter automatiquement les promotions
6. Statut & résultats (has_stories=True/False)  
7. Sauvegarde JSON + fermeture navigateur  

---

## 5️⃣ AdvancedFacebookReviewsScraper.py

- **Fichier d’entrée :** `places.json` avec URLs Facebook  
- **Fichier de sortie :** `reviews.json` + dossier `analysis/`  

### Workflow
1. Initialisation navigateur + cookies (Playwright)  
2. Connexion Facebook (login manuel si nécessaire)  
3. Navigation vers page des avis  
4. Extraction avis : filtres, nettoyage, suppression doublons  
5. Prétraitement linguistique : détection langue + nettoyage
6. Analyse NLP (sentiment, aspects, mots-clés)
7. Agrégation (distribution sentiments, score moyen par aspect)
8. Sauvegarde → reviews.json + analysis/
   
### Analyse NLP
- Sentiment global  
- Aspects (service, food, price, ambiance…)  
- Extraction mots-clés  
- Agrégation : distribution sentiment, score moyen, tendances  

### Sauvegarde
- Avis enrichis + analyse CSV/statistiques/graphiques  

# 📚 Modèles utilisés dans `AdvancedFacebookReviewsScraper.py`

## 1) Détection de langue
- **fastText LID-176** → `lid.176.ftz`
  - Avantages : rapide, robuste pour FR/EN/AR/TN.
  - Fallback : `langdetect` si le modèle n’est pas dispo.
  
## 2) Sentiment (multilingue)
- **cardiffnlp/twitter-xlm-roberta-base-sentiment**
  - 3 classes : negative / neutral / positive
  - Très bon sur textes courts (avis, posts).

## 3) Extraction d’aspects (zero-shot)
- **joeddav/xlm-roberta-large-xnli**
  - Labels proposés : `["service", "food", "price", "ambiance", "delivery", "cleanliness"]`
  - Permet de scorer chaque avis sur ces aspects sans fine-tuning.

## 4) Mots-clés (multilingue)
- **KeyBERT** avec embedding :
  - **sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2**
  - Alternatif si léger : **all-MiniLM-L6-v2** (un peu moins bon en AR).

## 5) Embeddings (agrégation / recherche / dédoublonnage sémantique)
- **sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2**

## 6) (Optionnel) Résumé d’avis longs (multilingue)
- **csebuetnlp/mT5_multilingual_XLSum**
  - Court résumé pour fiches synthèse.

## 7) (Optionnel) Toxicité / grossièretés (filtrage)
- **unitary/unbiased-toxic-roberta** (principalement EN, utile pour filtrer)

---
<img width="1877" height="745" alt="image" src="https://github.com/user-attachments/assets/383d34fb-82d1-4f06-a634-93172943a49b" />

## 6️⃣ glovo_scraper.py

- **Fichier d’entrée :** URL Glovo  
- **Fichier de sortie :** `products.json`  

### Workflow
1. Initialisation navigateur (Playwright)  
2. Détection sections produits  
3. Scraping produits : nom, prix, image, promo, description  
4. Nettoyage & filtrage (normalisation, suppression doublons)  
5. Méthode fallback : regex, scraping large  
6. Compilation résultats structurés (JSON)  
7. Sauvegarde + fermeture navigateur  

---

## 🔧 Technologies & Librairies

- **Playwright :** navigation automatisée  
- **BeautifulSoup :** parsing HTML  
- **LLM + LangChain :** structuration et extraction intelligente  
- **FuzzyWuzzy :** comparaison textuelle  
- **NLTK / Transformers :** NLP et analyse sentiment  
- **JSON :** stockage structuré  
- **Python 3.11+**  

---

## ✅ Points forts et améliorations

- Gestion manuelle + automatique CAPTCHA et login  
- Extraction multi-sources : Google, Facebook, Instagram, Glovo  
- Nettoyage et filtrage avancé des données  
- Calcul de score global pondéré pour vérification fiabilité  
- Sauvegarde structurée avec métadonnées et timestamps  
- Support multilingue (français, anglais, arabe, tunisien)  

<img width="1908" height="871" alt="image" src="https://github.com/user-attachments/assets/b64451b4-b36a-4a42-9874-bb8147625171" />


# 🚀 Pipeline Glovo Chatbot + API + App

Ce pipeline décrit le fonctionnement complet des fichiers `glovo_chatbot.py`, `api.py` et `app.py` pour un assistant Glovo intelligent.

---

## 1️⃣ glovo_chatbot.py – Moteur RAG

📂 **Input :** JSON Glovo scrappés (`glovo_data/*.json`)  
📦 **Output :** Base vectorielle Qdrant (mémoire ou serveur)

### 🔹 Workflow
- ⚡ Initialisation de `GlovoQdrantRAG`
- 📥 Chargement des fichiers JSON
- 📝 Préparation des documents :
  - Magasins
  - Produits
- 🔗 Indexation dans Qdrant via embeddings `SentenceTransformer`
- 🔍 Recherche intelligente (RAG) avec filtres : ville, type, top_k
- 💬 Génération de réponses via Llama2 (Ollama) avec contexte RAG
- 🏁 Pipeline complet : `chat(query, city)`  
  → Réponse IA + Résultats pertinents + Suggestions de filtres

### ✅ Points forts
- Multilingue : français, anglais, tunisien  
- Recherche par ville, promotions, type de magasin/produit  
- Embeddings vectoriels pour recherche sémantique

---

## 2️⃣ api.py – API FastAPI

📦 **Input :** `glovo_chatbot.py`  
📦 **Output :** API REST (`http://localhost:8000`)

### 🔹 Workflow
- ⚙️ Initialisation FastAPI avec `lifespan` (startup/shutdown)
- 📂 Chargement du système RAG (`GlovoQdrantRAG`)
- 🌐 Endpoints principaux :
  - `/` → statut & disponibilité RAG
  - `/chat` → chat interactif IA
  - `/search` → recherche avancée avec filtres (prix, promo, type)
  - `/cities` → liste des villes disponibles
  - `/stores/{city}` → magasins par ville
  - `/health` → état de santé API
- 🛠️ Gestion des filtres et extraction de prix
- 🔐 Sécurisation des imports et erreurs

### ✅ Points forts
- Centralisation des requêtes vers RAG  
- Filtrage avancé des résultats  
- Prêt pour intégration front-end

---
<img width="1765" height="965" alt="image" src="https://github.com/user-attachments/assets/55a8ce2a-2e8a-4990-abef-3860e202b730" />


<img width="1090" height="645" alt="image" src="https://github.com/user-attachments/assets/eb46790b-4feb-4739-a8a4-0756ba6047ce" />


<img width="1054" height="841" alt="image" src="https://github.com/user-attachments/assets/3edc5b91-3af9-4620-8920-b47c8e8565fd" />

## 3️⃣ app.py – Interface Streamlit

📦 **Input :** API FastAPI (`api.py`)  
📦 **Output :** Interface web utilisateur interactive

### 🔹 Workflow
- 📊 Configuration page et sidebar :
  - Ville
  - Type (Magasins / Produits)
  - Prix max
- ✏️ Saisie utilisateur : recherche via text input
- 🔗 Appel API `/chat` pour obtenir :
  - Réponse IA
  - Résultats détaillés
- 📂 Affichage dynamique avec `st.expander` pour chaque résultat
- ⚠️ Gestion erreurs API et suggestions automatiques
- 🎯 Boutons de suggestions rapides pour lancer une recherche

### ✅ Points forts
- Interface intuitive et responsive  
- Interaction directe avec API & RAG  
- Affichage clair promotions & détails produits

---
<img width="1901" height="927" alt="image" src="https://github.com/user-attachments/assets/dfa62c66-bd04-49bc-b502-243198be64ca" />

## 🔄 Pipeline global

mermaid
flowchart LR
    A[📦 JSON Glovo scrappés] --> B[🤖 glovo_chatbot.py]
    B --> C[💾 Qdrant Base Vectorielle / Embeddings]
    C --> D[🌐 api.py - FastAPI]
    D --> E[🖥️ app.py - Streamlit Front-End]
    E --> F[👤 Utilisateur final]

glovo_chatbot.py → moteur RAG

api.py → interface HTTP

app.py → front-end interactif

<img width="914" height="601" alt="image" src="https://github.com/user-attachments/assets/62fe4571-a0a3-44f7-9ba2-6173f811665f" />




## 🔧 Technologies & Librairies

-**Python**3.11+
-**FastAPI** → API REST
-**Streamlit** → interface web
-**Qdrant** → vector database
-**SentenceTransformer** → embeddings
-**Ollama / Llama2** → génération de réponses
-**Requests** → front-end → API
-**JSON** → stockage structuré
