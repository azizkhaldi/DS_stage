# 🌐 Web Scraping & Social Media Automation Suite

Cette suite de scripts permet de collecter, vérifier et analyser des informations à partir de différentes sources web (Google Maps, Facebook, Instagram, Glovo) pour les restaurants et commerces en Tunisie.  
Elle combine **Playwright, BeautifulSoup, LLM (Ollama + LangChain), NLP et modèles IA** pour obtenir des données fiables et structurées.

---

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

---

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

## 4️⃣ storie_scraper.py

- **Fichier d’entrée :** URL Instagram  
- **Fichier de sortie :** `stories_test_result_xxx.json`  

### Workflow
1. Initialisation navigateur (Playwright)  
2. Connexion Instagram (login manuel)  
3. Détection stories  
4. Capture stories : screenshot + texte visible  
5. Statut & résultats (has_stories=True/False)  
6. Sauvegarde JSON + fermeture navigateur  

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

---

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
