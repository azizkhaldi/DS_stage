import asyncio
import json
import os
import re
import time
import pandas as pd
import numpy as np
from datetime import datetime
from urllib.parse import urlparse
import logging
from playwright.async_api import async_playwright
from collections import Counter
from langdetect import detect, DetectorFactory, LangDetectException
import arabic_reshaper
from bidi.algorithm import get_display
import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification, pipeline
import emoji
import html
import urllib.request
import hashlib

# Configuration du logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Assurer la reproductibilité de langdetect
DetectorFactory.seed = 0

class AdvancedFacebookReviewsScraper:
    def __init__(self, json_path, output_dir="facebook_reviews_advanced"):
        self.json_path = json_path
        self.output_dir = output_dir
        
        # Configuration des dossiers
        self.reviews_dir = os.path.join(output_dir, "reviews")
        self.analysis_dir = os.path.join(output_dir, "analysis")
        self.models_dir = os.path.join(output_dir, "models")
        self.cookies_dir = os.path.join(output_dir, "cookies")
        
        for directory in [self.reviews_dir, self.analysis_dir, self.models_dir, self.cookies_dir]:
            os.makedirs(directory, exist_ok=True)
        
        # Chargement des modèles
        self._load_models()
        
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self.is_logged_in = False

    def _load_models(self):
        """Charge les modèles de NLP"""
        try:
            # Modèle de sentiment multilingue (nlptown/bert-base-multilingual-uncased-sentiment)
            logger.info("🔄 Chargement du modèle de sentiment BERT multilingue...")
            self.sentiment_pipeline = pipeline(
                "sentiment-analysis",
                model="nlptown/bert-base-multilingual-uncased-sentiment",
                tokenizer="nlptown/bert-base-multilingual-uncased-sentiment",
                device=0 if torch.cuda.is_available() else -1
            )
            
        except Exception as e:
            logger.error(f"❌ Erreur chargement modèles: {e}")
            raise

    async def initialize_browser(self):
        """Initialise le navigateur"""
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            headless=False,
            args=[
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-web-security',
                '--disable-blink-features=AutomationControlled',
                '--start-maximized'
            ]
        )
        
        # Charger les cookies existants si disponibles
        cookies = await self.load_cookies()
        
        self.context = await self.browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            java_script_enabled=True,
            locale="fr-FR",
            # Désactiver la détection WebDriver
            extra_http_headers={
                'Accept-Language': 'fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
            }
        )
        
        if cookies:
            await self.context.add_cookies(cookies)
        
        # Masquer WebDriver
        await self.context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
        """)
        
        self.page = await self.context.new_page()

    async def save_cookies(self):
        """Sauvegarde les cookies pour les sessions futures"""
        cookies = await self.context.cookies()
        cookies_file = os.path.join(self.cookies_dir, "facebook_cookies.json")
        with open(cookies_file, 'w') as f:
            json.dump(cookies, f)
        logger.info("✅ Cookies sauvegardés")

    async def load_cookies(self):
        """Charge les cookies d'une session précédente"""
        cookies_file = os.path.join(self.cookies_dir, "facebook_cookies.json")
        if os.path.exists(cookies_file):
            with open(cookies_file, 'r') as f:
                return json.load(f)
        return None

    async def close_browser(self):
        """Ferme le navigateur"""
        if self.page:
            await self.page.close()
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()

    async def check_login_status(self):
        """Vérifie si l'utilisateur est connecté à Facebook"""
        try:
            await self.page.goto("https://www.facebook.com", timeout=30000)
            await asyncio.sleep(3)
            
            # Vérifier plusieurs indicateurs de connexion
            login_indicators = [
                await self.page.query_selector('[aria-label="Profil"]'),
                await self.page.query_selector('a[href*="/me/"]'),
                await self.page.query_selector('div[aria-label="Menu"]'),
            ]
            
            # Si au moins un indicateur est présent, nous sommes connectés
            if any(login_indicators):
                logger.info("✅ Déjà connecté à Facebook via les cookies")
                self.is_logged_in = True
                return True
                
            return False
        except Exception as e:
            logger.warning(f"Erreur vérification statut connexion: {e}")
            return False

    async def login_to_facebook(self):
        """Connexion manuelle à Facebook avec gestion des cookies"""
        logger.info("🔐 Connexion à Facebook...")
        
        # D'abord vérifier si nous sommes déjà connectés via les cookies
        if await self.check_login_status():
            return True
        
        await self.page.goto("https://www.facebook.com/login", timeout=120000)
        logger.info("Veuillez vous connecter à Facebook...")
        
        start_time = time.time()
        while time.time() - start_time < 300:
            current_url = self.page.url.lower()
            if ("facebook.com" in current_url and 
                "login" not in current_url and 
                "checkpoint" not in current_url):
                logger.info("✅ Connexion Facebook réussie")
                self.is_logged_in = True
                await self.save_cookies()
                return True
            await asyncio.sleep(5)
        
        logger.warning("⏰ Timeout connexion Facebook")
        return False

    def preprocess_text(self, text, language=None):
        """Prétraitement linguistique avancé"""
        if not text:
            return ""
        
        # Décodage HTML et émojis
        text = html.unescape(text)
        text = emoji.demojize(text, delimiters=(" ", " "))
        
        # Nettoyage basique
        text = re.sub(r'http\S+', '', text)  # Remove URLs
        text = re.sub(r'@\w+', '', text)     # Remove mentions
        text = re.sub(r'#\w+', '', text)     # Remove hashtags
        
        if language == 'arabic' or self.detect_language(text) == 'arabic':
            return self._preprocess_arabic(text)
        elif language == 'tunisian':
            return self._preprocess_tunisian(text)
        elif language in ['french', 'english']:
            return self._preprocess_romance(text)
        else:
            # Pour langue inconnue, nettoyage minimal
            text = re.sub(r'[^\w\s]', ' ', text)  # Garder lettres, chiffres, espaces
            return text.strip()

    def _preprocess_arabic(self, text):
        """Prétraitement spécifique arabe"""
        # Normalisation des lettres
        text = re.sub(r'[أإآ]', 'ا', text)  # Unifier alif
        text = re.sub(r'[ة]', 'ه', text)    # Ta marbuta to ha
        text = re.sub(r'[ى]', 'ي', text)    # Alif maqsura to ya
        
        # Suppression des diacritiques
        text = re.sub(r'[\u064B-\u065F]', '', text)  # Remove harakat
        
        # Normalisation espaces
        text = re.sub(r'\s+', ' ', text)
        
        return text.strip()

    def _preprocess_tunisian(self, text):
        """Prétraitement spécifique tunisien (mixte arabe/français)"""
        # Nettoyer le texte
        text = re.sub(r'[^\w\s]', ' ', text)  # Garder lettres, chiffres, espaces
        text = re.sub(r'\s+', ' ', text)       # Normalize spaces
        
        return text.strip()

    def _preprocess_romance(self, text):
        """Prétraitement français/anglais"""
        text = text.lower()
        text = re.sub(r'[^\w\s]', ' ', text)  # Remove punctuation
        text = re.sub(r'\d+', '', text)        # Remove numbers
        text = re.sub(r'\s+', ' ', text)       # Normalize spaces
        
        return text.strip()

    def detect_language(self, text):
        """Détection de langue avec langdetect et détection spécifique du tunisien"""
        if not text or len(text.strip()) < 10:
            return "unknown"
        
        try:
            # Nettoyer le texte pour une meilleure détection
            clean_text = re.sub(r'[^\w\s]', ' ', text)
            clean_text = re.sub(r'\d+', '', clean_text)
            clean_text = re.sub(r'\s+', ' ', clean_text).strip()
            
            if len(clean_text) < 5:
                return "unknown"
            
            # Détection spécifique du tunisien (mixte arabe/français)
            if self._is_tunisian_text(clean_text):
                return "tunisian"
                
            # Détection standard avec langdetect
            lang_code = detect(clean_text)
            
            lang_map = {
                'ar': 'arabic',
                'fr': 'french', 
                'en': 'english',
                'es': 'spanish',
                'it': 'italian'
            }
            
            return lang_map.get(lang_code, 'unknown')
        except LangDetectException:
            return "unknown"
        except Exception:
            return "unknown"

    def _is_tunisian_text(self, text):
        """Détecte si le texte est en dialecte tunisien"""
        # Mots et patterns caractéristiques du tunisien
        tunisian_patterns = [
            r'\b(باش|برشا|باهي|يا سيدي|علاش|ماشي|شكون|فما|فمّا|زعمة|زعما|بالتوفيق|يلا|يلّا|نحكيو|نحكي|تحكي)\b',
            r'\b(walahi|wallah|yalla|barcha|behi|3lech|machi|chkoun|famma|z3ma|z3ama)\b',
            r'\b(وْلَاهِي|وْلّا|بَارْشَا|بَاهِي|عْلَاش|مَاشِي|شْكُون|فَمَّا|زْعْمَة|زْعَامَة)\b',
        ]
        
        # Caractéristiques du tunisien: mélange de français et d'arabe
        has_arabic = bool(re.search(r'[\u0600-\u06FF]', text))
        has_french = bool(re.search(r'\b(le|la|les|de|des|et|est|à|au|aux|pour)\b', text.lower()))
        
        # Vérifier les patterns spécifiques
        for pattern in tunisian_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        
        # Si le texte contient à la fois de l'arabe et du français, c'est probablement du tunisien
        if has_arabic and has_french and len(text.split()) > 3:
            return True
            
        return False

    def analyze_sentiment_bert(self, text):
        """Analyse de sentiment avec BERT multilingue"""
        if not text or len(text) < 10:
            return {"sentiment": "neutral", "score": 0.0, "label": "3 stars", "rating": 3}
        
        try:
            result = self.sentiment_pipeline(text[:512])[0]  # Truncate to model limit
            
            # Le modèle nlptown retourne des évaluations en étoiles (1-5)
            rating = int(result['label'].split()[0])  # Extraire le nombre d'étoiles
            
            if rating >= 4:
                sentiment = "positive"
            elif rating == 3:
                sentiment = "neutral"
            else:
                sentiment = "negative"
            
            return {
                "sentiment": sentiment,
                "score": result['score'],
                "label": result['label'],
                "rating": rating
            }
        except Exception as e:
            logger.warning(f"Erreur analyse sentiment: {e}")
            return {"sentiment": "neutral", "score": 0.0, "label": "3 stars", "rating": 3}

    def extract_aspects(self, text, language):
        """Extraction des aspects et sentiment par aspect"""
        aspects_keywords = {
            'service': ['service', 'serveur', 'staff', 'employé', 'accueil', 'خدمة', 'نادل', 'نضام'],
            'food': ['nourriture', 'plat', 'repas', 'cuisine', 'goût', 'طعام', 'أكلة', 'مكلة'],
            'price': ['prix', 'cher', 'abordable', 'coût', 'valeur', 'سعر', 'غالي', 'ثمن'],
            'ambiance': ['ambiance', 'décor', 'musique', 'environnement', 'جو', 'أجواء', 'طاقة'],
            'quality': ['qualité', 'fraîcheur', 'propreté', 'نظافة', 'جودة', 'طازج'],
            'waiting': ['attente', 'temps', 'rapide', 'lent', 'انتظار', 'وقت', 'مدة'],
            'location': ['emplacement', 'emplacement', 'موقع', 'مكان', 'adresse', 'عنوان']
        }
        
        # Ajouter des mots-clés spécifiques au tunisien
        if language == 'tunisian':
            aspects_keywords['service'].extend(['خدمة', 'نضام', 'عاملين', 'ستاف'])
            aspects_keywords['food'].extend(['مكلة', 'أكلة', 'ماكلة', 'طعم'])
            aspects_keywords['price'].extend(['ثمن', 'فلوس', 'قيمة', 'بري'])
            aspects_keywords['ambiance'].extend(['هواء', 'جو', 'أجواء', 'طاقة'])
        
        aspects = {}
        preprocessed_text = self.preprocess_text(text, language)
        
        for aspect, keywords in aspects_keywords.items():
            aspect_count = 0
            aspect_sentences = []
            
            for keyword in keywords:
                if keyword in preprocessed_text:
                    aspect_count += 1
                    # Extraire la phrase autour du mot-clé
                    sentences = re.split(r'[.!?]', text)
                    for sentence in sentences:
                        if keyword in sentence.lower():
                            aspect_sentences.append(sentence.strip())
            
            if aspect_count > 0:
                # Analyser le sentiment pour cet aspect
                aspect_text = ' '.join(aspect_sentences) if aspect_sentences else text
                sentiment = self.analyze_sentiment_bert(aspect_text)
                
                aspects[aspect] = {
                    'count': aspect_count,
                    'sentiment': sentiment['sentiment'],
                    'score': sentiment['score'],
                    'rating': sentiment['rating'],
                    'sentences': aspect_sentences[:3]  # Garder 3 exemples max
                }
        
        return aspects

    def is_valid_review(self, text):
        """Vérifie si le texte est un vrai avis"""
        if not text or len(text) < 30:
            return False
        
        # Patterns à exclure (éléments d'interface, boutons, etc.)
        exclusion_patterns = [
            r'J\'aime.*Répondre',
            r'\d+\s*sem',
            r'\d+\s*ans',
            r'Recommandez-vous.*OuiNon',
            r'followers',
            r'FacebookFacebook',
            r'Recommandé par',
            r'Publications',
            r'Rechercher',
            r'Message',
            r'Partager',
            r'Commenter',
            r'Écrivez un commentaire',
            r'Voir la traduction',
            r'Toutes les réactions',
            r'\d+\s*commentaires'
        ]
        
        for pattern in exclusion_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return False
        
        # Vérifier la répétition de mots (spam)
        words = text.split()
        if len(words) > 0:
            word_counts = Counter(words)
            most_common_count = word_counts.most_common(1)[0][1]
            if most_common_count > len(words) * 0.3:  # Si un mot représente plus de 30% du texte
                return False
        
        # Vérifier le nombre de mots
        if len(words) < 5:
            return False
        
        return True

    async def extract_review_data(self, review_element):
        """Extraction des données d'avis directement depuis le HTML - Version améliorée"""
        try:
            # Extraire le texte avec une méthode plus robuste
            review_data = await review_element.evaluate('''(element) => {
                // Essayer plusieurs sélecteurs pour trouver le texte
                const selectors = [
                    'div[dir="auto"]',
                    'div.x1yztbdb',
                    'div.x1n2onr6',
                    'div.x1qjc9v5',
                    'div.x1q0g3np',
                    'span.x1lliihq',
                    'div.xdj266r'
                ];
                
                let fullText = '';
                
                // Essayer chaque sélecteur
                for (const selector of selectors) {
                    const elements = element.querySelectorAll(selector);
                    for (const el of elements) {
                        if (el.textContent && el.textContent.trim().length > 5) {
                            fullText += el.textContent.trim() + ' ';
                        }
                    }
                    if (fullText.length > 10) break;
                }
                
                // Si toujours pas de texte, essayer de récupérer tout le texte de l'élément
                if (fullText.length < 10) {
                    fullText = element.textContent.trim();
                }
                
                // Extraire la note - essayer plusieurs méthodes
                let rating = null;
                
                // Méthode 1: aria-label
                const ariaLabel = element.getAttribute('aria-label') || '';
                const ratingMatch = ariaLabel.match(/\\d+/);
                if (ratingMatch) rating = parseInt(ratingMatch[0]);
                
                // Méthode 2: chercher des étoiles
                if (rating === null) {
                    const starElements = element.querySelectorAll('[aria-label*="star"], [aria-label*="étoile"]');
                    for (const star of starElements) {
                        const label = star.getAttribute('aria-label') || '';
                        const starMatch = label.match(/\\d+/);
                        if (starMatch) {
                            rating = parseInt(starMatch[0]);
                            break;
                        }
                    }
                }
                
                // Extraire la date
                let date = '';
                const timeSelectors = ['time', 'abbr', 'span.x4k7w5x', 'span.x1lliihq'];
                for (const selector of timeSelectors) {
                    const timeEl = element.querySelector(selector);
                    if (timeEl) {
                        date = timeEl.getAttribute('datetime') || timeEl.textContent || timeEl.getAttribute('title') || '';
                        if (date) break;
                    }
                }
                
                // Extraire l'auteur
                let author = '';
                const authorSelectors = [
                    'a[role="link"][href*="/user/"]',
                    'a[role="link"][href*="/profile/"]',
                    'a.x1i10hfl',
                    'span.x1lliihq a'
                ];
                
                for (const selector of authorSelectors) {
                    const authorEl = element.querySelector(selector);
                    if (authorEl) {
                        author = authorEl.textContent.trim();
                        if (author) break;
                    }
                }
                
                return {
                    text: fullText.trim(),
                    rating: rating,
                    date: date,
                    author: author
                };
            }''')
            
            # Vérification du texte avec filtrage amélioré
            if not review_data['text'] or not self.is_valid_review(review_data['text']):
                return None
            
            # Détection de langue
            language = self.detect_language(review_data['text'])
            
            # Prétraitement du texte
            cleaned_text = self.preprocess_text(review_data['text'], language)
            
            # Analyse de sentiment
            sentiment = self.analyze_sentiment_bert(cleaned_text)
            
            # Extraction des aspects
            aspects = self.extract_aspects(cleaned_text, language)
            
            # Extraction des mots-clés
            keywords = self._extract_keywords(cleaned_text, language)
            
            # Créer un ID unique basé sur le contenu
            content_hash = hashlib.md5(review_data['text'].encode()).hexdigest()
            
            return {
                'review_id': f"rev_{content_hash}",
                'author': review_data['author'] or "Unknown",
                'rating': review_data['rating'],
                'original_text': review_data['text'],
                'cleaned_text': cleaned_text,
                'date': review_data['date'] or "Unknown date",
                'language': language,
                'sentiment': sentiment['sentiment'],
                'sentiment_score': sentiment['score'],
                'sentiment_label': sentiment['label'],
                'sentiment_rating': sentiment['rating'],
                'aspects': aspects,
                'keywords': keywords,
                'scraped_at': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.warning(f"Erreur extraction avis: {e}")
            return None

    def _extract_keywords(self, text, language):
        """Extraction des mots-clés avec filtrage avancé"""
        if not text:
            return []
        
        # Stop words par langue
        stop_words = {
            'arabic': {'و', 'في', 'من', 'على', 'أن', 'هذا', 'هذه', 'كان', 'يكون', 'هو', 'هي'},
            'tunisian': {'و', 'في', 'من', 'على', 'أن', 'هذا', 'هذه', 'كان', 'le', 'la', 'les', 'de', 'des', 'et', 'est'},
            'french': {'le', 'la', 'les', 'de', 'des', 'du', 'et', 'est', 'en', 'à', 'au', 'aux', 'pour'},
            'english': {'the', 'and', 'is', 'in', 'to', 'of', 'a', 'an', 'for', 'on', 'with', 'at', 'by'}
        }
        
        words = re.findall(r'\b\w+\b', text.lower())
        keywords = []
        
        for word in words:
            if (len(word) > 2 and  # Réduit la longueur minimale
                word not in stop_words.get(language, set()) and
                not word.isdigit() and
                not any(char.isdigit() for char in word)):
                keywords.append(word)
        
        return keywords

    async def navigate_to_reviews(self, fb_url):
        """Navigation vers la page des avis avec gestion des timeouts"""
        reviews_url = fb_url.rstrip('/') + '/reviews/'
        logger.info(f"📝 Navigation vers: {reviews_url}")
        
        try:
            # Essayer plusieurs fois avec des timeouts différents
            for attempt in range(3):
                try:
                    await self.page.goto(reviews_url, timeout=60000, wait_until="domcontentloaded")
                    logger.info("✅ Page chargée avec succès")
                    return True
                except Exception as e:
                    logger.warning(f"⚠️ Tentative {attempt + 1} échouée: {e}")
                    if attempt < 2:
                        logger.info("🔄 Nouvelle tentative...")
                        await asyncio.sleep(5)
            
            # Si toutes les tentatives échouent, essayer une méthode alternative
            logger.info("🔄 Utilisation de la méthode alternative de navigation...")
            await self.page.goto(fb_url, timeout=60000, wait_until="domcontentloaded")
            await asyncio.sleep(5)
            
            # Essayer de cliquer sur le lien des avis
            review_links = await self.page.query_selector_all('a[href*="/reviews"], a[aria-label*="review"], a[aria-label*="avis"]')
            if review_links:
                await review_links[0].click()
                await asyncio.sleep(8)
                return True
            else:
                logger.error("❌ Impossible de trouver le lien des avis")
                return False
                
        except Exception as e:
            logger.error(f"❌ Erreur navigation: {e}")
            return False

    async def scrape_facebook_reviews(self, fb_url, restaurant_id, restaurant_name, max_reviews=50):
        """Scrape les avis Facebook avec techniques avancées"""
        reviews_data = []
        seen_review_ids = set()  # Pour éviter les doublons
        
        try:
            # Navigation vers les avis
            navigation_success = await self.navigate_to_reviews(fb_url)
            if not navigation_success:
                return reviews_data
            
            await asyncio.sleep(8)  # Attendre que la page se charge
            
            logger.info("🔄 Recherche des avis...")
            
            # Essayer différents sélecteurs pour les avis
            review_selectors = [
                'div[role="article"]',
                'div.x1yztbdb',
                'div.x1n2onr6',
                'div.x1qjc9v5',
                'div.x1q0g3np',
                'div.x1lq5wgf',
                'div.x1gryazu'
            ]
            
            loaded_count = 0
            scroll_attempts = 0
            max_scroll_attempts = 8
            
            while scroll_attempts < max_scroll_attempts and loaded_count < max_reviews:
                # Scroll down progressivement
                for _ in range(2):
                    await self.page.evaluate("window.scrollBy(0, 800)")
                    await asyncio.sleep(2)
                
                await asyncio.sleep(3)
                
                # Vérifier les nouveaux avis avec différents sélecteurs
                for selector in review_selectors:
                    try:
                        review_elements = await self.page.query_selector_all(selector)
                        current_count = len(review_elements)
                        
                        if current_count > loaded_count:
                            loaded_count = current_count
                            scroll_attempts = 0
                            logger.info(f"📊 {loaded_count} avis détectés")
                            break
                    except:
                        continue
                else:
                    scroll_attempts += 1
                
                if loaded_count >= max_reviews:
                    break
            
            # Extraction des avis
            logger.info("🔍 Extraction des données...")
            review_elements = []
            
            for selector in review_selectors:
                try:
                    elements = await self.page.query_selector_all(selector)
                    if elements:
                        review_elements.extend(elements)
                except:
                    continue
            
            # Éliminer les doublons basés sur la position
            unique_elements = []
            seen_positions = set()
            
            for element in review_elements:
                try:
                    # Utiliser la position pour identifier les doublons
                    bounding_box = await element.bounding_box()
                    if bounding_box:
                        position = f"{bounding_box['x']}_{bounding_box['y']}"
                        if position not in seen_positions:
                            seen_positions.add(position)
                            unique_elements.append(element)
                except:
                    unique_elements.append(element)
            
            logger.info(f"📝 {len(unique_elements)} avis uniques à analyser")
            
            for i, review_element in enumerate(unique_elements[:max_reviews]):
                try:
                    review_data = await self.extract_review_data(review_element)
                    if review_data and review_data['review_id'] not in seen_review_ids:
                        seen_review_ids.add(review_data['review_id'])
                        reviews_data.append(review_data)
                        logger.info(f"✅ Avis {len(reviews_data)}: {review_data['sentiment']} ({review_data['language']})")
                    
                    # Pause pour éviter la surcharge
                    if i % 3 == 0:
                        await asyncio.sleep(1)
                        
                except Exception as e:
                    logger.warning(f"Erreur avis {i}: {e}")
                    continue
                    
        except Exception as e:
            logger.error(f"❌ Erreur scraping: {e}")
        
        return reviews_data

    def analyze_reviews_data(self, reviews_data, restaurant_name):
        """Analyse approfondie des données"""
        if not reviews_data:
            return None
        
        try:
            df = pd.DataFrame(reviews_data)
            
            # Statistiques de base
            total_reviews = len(df)
            sentiment_counts = df['sentiment'].value_counts().to_dict()
            
            # Analyse des aspects
            all_aspects = {}
            for review in reviews_data:
                for aspect, data in review.get('aspects', {}).items():
                    if aspect not in all_aspects:
                        all_aspects[aspect] = {'count': 0, 'positive': 0, 'negative': 0, 'neutral': 0}
                    
                    all_aspects[aspect]['count'] += data['count']
                    all_aspects[aspect][data['sentiment']] += 1
            
            # Mots-clés par sentiment
            positive_keywords = []
            negative_keywords = []
            
            for review in reviews_data:
                if review['sentiment'] == 'positive':
                    positive_keywords.extend(review['keywords'])
                elif review['sentiment'] == 'negative':
                    negative_keywords.extend(review['keywords'])
            
            # Calcul de la note moyenne
            ratings = [r.get('rating') for r in reviews_data if r.get('rating') is not None]
            avg_rating = sum(ratings) / len(ratings) if ratings else None
            
            # Calcul de la note moyenne basée sur le sentiment BERT
            sentiment_ratings = [r.get('sentiment_rating', 3) for r in reviews_data if 'sentiment_rating' in r]
            avg_sentiment_rating = sum(sentiment_ratings) / len(sentiment_ratings) if sentiment_ratings else None
            
            return {
                'restaurant_name': restaurant_name,
                'total_reviews': total_reviews,
                'sentiment_distribution': sentiment_counts,
                'language_distribution': df['language'].value_counts().to_dict() if 'language' in df.columns else {},
                'aspects_analysis': all_aspects,
                'positive_keywords': Counter(positive_keywords).most_common(15),
                'negative_keywords': Counter(negative_keywords).most_common(15),
                'avg_rating': avg_rating,
                'avg_sentiment_rating': avg_sentiment_rating,
                'analysis_date': datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"Erreur dans l'analyse des données: {e}")
            return None

    async def run_analysis(self, max_reviews_per_restaurant=30):
        """Exécute l'analyse complète"""
        with open(self.json_path, 'r', encoding='utf-8') as f:
            restaurants = json.load(f)
        
        await self.initialize_browser()
        login_success = await self.login_to_facebook()
        
        if not login_success:
            logger.error("❌ Échec connexion Facebook")
            await self.close_browser()
            return []
        
        results = []
        
        for restaurant in restaurants:
            try:
                restaurant_id = restaurant['id']
                restaurant_name = restaurant['place_name']
                
                logger.info(f"\n🍽️  Analyse: {restaurant_name}")
                
                # Trouver le lien Facebook
                facebook_links = [link for link in restaurant.get('social_links', []) 
                                 if link['type'] == 'facebook' and link['verified']]
                
                if not facebook_links:
                    logger.warning("❌ Aucun lien Facebook")
                    continue
                
                fb_url = facebook_links[0]['url']
                
                # Scraper les avis
                reviews = await self.scrape_facebook_reviews(
                    fb_url, restaurant_id, restaurant_name, max_reviews_per_restaurant
                )
                
                if not reviews:
                    logger.warning("❌ Aucun avis trouvé")
                    continue
                
                logger.info(f"✅ {len(reviews)} avis récupérés")
                
                # Analyser les données
                analysis = self.analyze_reviews_data(reviews, restaurant_name)
                
                if not analysis:
                    logger.warning("❌ Échec de l'analyse des données")
                    continue
                
                # Sauvegarder
                timestamp = int(time.time())
                reviews_file = os.path.join(self.reviews_dir, f"reviews_{restaurant_id}_{timestamp}.json")
                analysis_file = os.path.join(self.analysis_dir, f"analysis_{restaurant_id}_{timestamp}.json")
                
                with open(reviews_file, 'w', encoding='utf-8') as f:
                    json.dump(reviews, f, indent=2, ensure_ascii=False)
                
                with open(analysis_file, 'w', encoding='utf-8') as f:
                    json.dump(analysis, f, indent=2, ensure_ascii=False)
                
                results.append({
                    'restaurant_id': restaurant_id,
                    'restaurant_name': restaurant_name,
                    'reviews_count': len(reviews),
                    'analysis': analysis,
                    'files': {
                        'reviews': reviews_file,
                        'analysis': analysis_file
                    }
                })
                
                logger.info(f"✅ {len(reviews)} avis analysés")
                logger.info(f"   📊 Sentiment: {analysis['sentiment_distribution']}")
                
                # Pause entre les restaurants
                await asyncio.sleep(10)
                
            except Exception as e:
                logger.error(f"❌ Erreur restaurant {restaurant.get('place_name', 'inconnu')}: {e}")
                continue
        
        await self.close_browser()
        
        # Sauvegarde finale
        final_output = os.path.join(self.output_dir, "advanced_analysis_final.json")
        with open(final_output, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        
        logger.info(f"\n🎉 Analyse avancée terminée! Résultats dans {final_output}")
        return results

# Exécution
async def main():
    scraper = AdvancedFacebookReviewsScraper("verification_results.json")
    await scraper.run_analysis(max_reviews_per_restaurant=30)

if __name__ == "__main__":
    asyncio.run(main())