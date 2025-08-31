import asyncio
import json
import os
import random
import re
import time
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
from rapidfuzz import fuzz
from unidecode import unidecode
import numpy as np

class SocialMediaVerifier:
    def __init__(self, json_path, output_json="verification_results.json"):
        self.json_path = json_path
        self.output_json = output_json
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        
        # Modèles IA
        self.general_model = SentenceTransformer('all-mpnet-base-v2')
        self.address_model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
        
        # Configuration
        self.weights = {
            'name': 1.0,
            'address': 3.0,
            'phone': 2.0
        }
        self.address_threshold = 0.3
        self.min_address_length = 10

    async def initialize_browser(self):
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(headless=False)
        self.context = await self.browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            viewport={"width": 1366, "height": 768}
        )
        self.page = await self.context.new_page()

    async def close_browser(self):
        if self.page:
            await self.page.close()
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()

    async def login_to_facebook(self):
        """Connexion manuelle à Facebook"""
        print("🔐 Connexion à Facebook...")
        await self.page.goto("https://www.facebook.com/login", timeout=60000)
        
        print("Veuillez vous connecter manuellement à Facebook dans le navigateur...")
        start_time = time.time()
        while True:
            if time.time() - start_time > 300:  # 5 minutes timeout
                raise Exception("Timeout lors de la connexion manuelle")
            if "facebook.com" in self.page.url and "login" not in self.page.url:
                print("✅ Connexion réussie")
                break
            await asyncio.sleep(5)

    async def scrape_facebook_about(self, fb_url):
        """Scrape la page À propos de Facebook avec login"""
        try:
            about_url = f"{fb_url.rstrip('/')}/about"
            await self.page.goto(about_url, timeout=60000)
            await self.page.wait_for_selector("body", state="attached")
            
            # Scroll pour charger tout le contenu
            await self.page.evaluate("""async () => {
                await new Promise(resolve => {
                    let scrolled = 0;
                    const scrollInterval = setInterval(() => {
                        window.scrollBy(0, 300);
                        scrolled += 300;
                        if (scrolled >= document.body.scrollHeight || scrolled > 5000) {
                            clearInterval(scrollInterval);
                            resolve();
                        }
                    }, 300);
                });
            }""")
            
            await asyncio.sleep(3)
            return await self.page.content()
        except Exception as e:
            print(f"Erreur scraping Facebook {fb_url}: {str(e)}")
            return None

    async def scrape_instagram_header(self, ig_url):
        """Scrape l'en-tête Instagram et retourne le texte complet"""
        try:
            # Créer un nouveau contexte pour Instagram
            ig_context = await self.browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                viewport={"width": 1366, "height": 768}
            )
            ig_page = await ig_context.new_page()
            
            await ig_page.goto(ig_url, timeout=60000)
            await ig_page.wait_for_selector("header", timeout=15000)

            # Récupérer tout le texte de l'en-tête du profil
            header_text = await ig_page.evaluate('''() => {
                const header = document.querySelector('header');
                return header ? header.innerText : '';
            }''')

            await ig_context.close()
            
            return header_text
            
        except Exception as e:
            print(f"Erreur scraping Instagram {ig_url}: {str(e)}")
            return None

    def normalize_phone_number(self, phone):
        """Normalise le numéro de téléphone pour la comparaison"""
        if not phone:
            return ""
        # Garder seulement les chiffres
        digits = re.sub(r'[^\d]', '', str(phone))
        # Pour les numéros tunisiens, garder les 8 derniers chiffres
        if digits.startswith('216'):
            digits = digits[3:]  # Enlever le 216
        elif len(digits) > 8:
            digits = digits[-8:]  # Garder les 8 derniers chiffres
        return digits

    def extract_phone_numbers_from_text(self, text):
        """Extrait et normalise les numéros de téléphone d'un texte"""
        phone_patterns = [
            r'(?:\+|00)?216\s*\d{1,3}\s*\d{2}\s*\d{2}\s*\d{2}',
            r'\d{2}\s*\d{3}\s*\d{3}',
            r'\d{3}\s*\d{2}\s*\d{2}\s*\d{2}',
            r'(?:\d{2}\s*){4}',
            r'\d{8}'
        ]
        
        phones = []
        for pattern in phone_patterns:
            found_phones = re.findall(pattern, text)
            for phone in found_phones:
                normalized = self.normalize_phone_number(phone)
                if normalized:
                    phones.append(normalized)
        return list(set(phones))

    def check_phone_match(self, json_phone, text_phones):
        """Vérifie si le téléphone JSON correspond à un des téléphones extraits"""
        if not json_phone:
            return False
        
        json_normalized = self.normalize_phone_number(json_phone)
        for phone in text_phones:
            if json_normalized == phone:
                return True
            # Vérification partielle (les 8 derniers chiffres)
            if len(json_normalized) >= 8 and len(phone) >= 8:
                if json_normalized[-8:] == phone[-8:]:
                    return True
        return False

    def extract_address_from_name(self, profile_name, restaurant_address):
        """Détecte les éléments d'adresse dans le nom du profil"""
        if not profile_name or not restaurant_address:
            return 0.0
        
        profile_name_lower = profile_name.lower()
        address_lower = restaurant_address.lower()
        
        # Liste des mots communs à exclure
        common_words = {'restaurant', 'cafe', 'bistro', 'pub', 'bar', 'grill', 'pizza', 'burger', 'tunis', 'tunisie'}
        
        # Extraire les parties significatives de l'adresse
        address_parts = []
        for part in re.split(r'[,;]', address_lower):
            part = part.strip()
            words = part.split()
            # Garder seulement les parties avec des mots significatifs
            if (len(part) > 3 and 
                not any(word in common_words for word in words) and
                not part.isdigit()):
                address_parts.append(part)
        
        # Vérifier chaque partie d'adresse dans le nom du profil
        max_score = 0.0
        for part in address_parts:
            if part in profile_name_lower:
                # Score basé sur l'importance de la correspondance
                score = min(len(part) / len(profile_name_lower) * 3, 0.9)
                max_score = max(max_score, score)
            else:
                # Vérifier les mots individuels de l'adresse
                words = [w for w in part.split() if len(w) > 2 and w not in common_words]
                for word in words:
                    if word in profile_name_lower:
                        score = 0.6  # Score élevé pour un mot d'adresse dans le nom
                        max_score = max(max_score, score)
        
        return max_score

    def analyze_social_content(self, social_text, restaurant, profile_name=None):
        """Analyse le contenu d'une page sociale avec détection d'adresse dans le nom"""
        if not social_text:
            return {
                'name_score': 0.0,
                'address_score': 0.0,
                'phone_match': False,
                'overall_score': 0.0,
                'details': []
            }
        
        social_text_lower = social_text.lower()
        restaurant_name = restaurant['nom'].lower()
        restaurant_address = restaurant['adresse'].lower()
        
        # Score du nom
        name_score = fuzz.partial_ratio(restaurant_name, social_text_lower) / 100
        
        # Score de l'adresse dans le texte complet
        address_in_text_score = fuzz.partial_ratio(restaurant_address, social_text_lower) / 100
        
        # Score additionnel si l'adresse est détectée dans le nom du profil
        address_in_name_score = 0.0
        if profile_name:
            address_in_name_score = self.extract_address_from_name(profile_name, restaurant_address)
        
        # Prendre le meilleur score d'adresse
        address_score = max(address_in_text_score, address_in_name_score)
        
        # Vérification du téléphone
        text_phones = self.extract_phone_numbers_from_text(social_text)
        phone_match = self.check_phone_match(restaurant.get('telephone'), text_phones)
        
        # Calcul du score global pondéré
        scores = {
            'name': max(name_score, 0.1),
            'address': max(address_score, 0.1),
            'phone': 1.0 if phone_match else 0
        }
        overall_score = sum(scores[k] * self.weights[k] for k in scores) / sum(self.weights[k] for k in scores)
        
        # Détails des correspondances
        details = []
        if name_score >= 0.6:
            details.append(f"Nom ({name_score:.2f})")
        if address_score >= 0.4:
            source = "nom" if address_in_name_score > address_in_text_score else "texte"
            details.append(f"Adresse ({address_score:.2f} - {source})")
        if phone_match:
            details.append("Téléphone")
        
        return {
            'name_score': float(name_score),
            'address_score': float(address_score),
            'phone_match': phone_match,
            'overall_score': float(overall_score),
            'details': " | ".join(details) if details else "Aucune correspondance forte"
        }

    def extract_profile_name_from_instagram(self, header_text):
        """Extrait le nom du profil Instagram depuis le header"""
        if not header_text:
            return None
        
        lines = header_text.split('\n')
        if len(lines) >= 2:
            # Le nom du profil est généralement sur la deuxième ligne
            return lines[1].strip()
        return None

    async def verify_restaurant(self, restaurant):
        """Vérifie un restaurant avec ses liens sociaux"""
        result = {
            'id': restaurant.get('id'),
            'place_name': restaurant.get('place_name'),
            'nom': restaurant.get('nom'),
            'adresse': restaurant.get('adresse'),
            'telephone': restaurant.get('telephone'),
            'social_links': [],
            'verification_status': 'UNVERIFIED',
            'verification_details': 'Aucune vérification effectuée',
            'best_overall_score': 0.0
        }
        
        # Vérifier chaque lien social
        for link in restaurant.get('links', []):
            link_result = {
                'url': link['url'],
                'type': link['type'],
                'name_score': 0.0,
                'address_score': 0.0,
                'phone_match': False,
                'overall_score': 0.0,
                'verified': False,
                'details': 'Non analysé'
            }
            
            social_text = None
            profile_name = None
            
            if link['type'] == 'facebook':
                # Scraper Facebook
                fb_html = await self.scrape_facebook_about(link['url'])
                if fb_html:
                    social_text = BeautifulSoup(fb_html, 'html.parser').get_text('\n', strip=True)
            
            elif link['type'] == 'instagram':
                # Scraper Instagram
                social_text = await self.scrape_instagram_header(link['url'])
                if social_text:
                    # Extraire le nom du profil pour la détection d'adresse
                    profile_name = self.extract_profile_name_from_instagram(social_text)
            
            if social_text:
                # Analyser le contenu avec détection d'adresse dans le nom
                analysis = self.analyze_social_content(social_text, restaurant, profile_name)
                
                # Déterminer si le lien est vérifié
                verified = analysis['overall_score'] >= 0.6
                
                link_result.update({
                    'name_score': analysis['name_score'],
                    'address_score': analysis['address_score'],
                    'phone_match': analysis['phone_match'],
                    'overall_score': analysis['overall_score'],
                    'verified': verified,
                    'details': analysis['details']
                })
            
            result['social_links'].append(link_result)
        
        # Trouver le meilleur score global
        if result['social_links']:
            best_link = max(result['social_links'], key=lambda x: x['overall_score'])
            result['best_overall_score'] = best_link['overall_score']
        
        # Déterminer le statut global
        verified_links = [link for link in result['social_links'] if link['verified']]
        if verified_links:
            result['verification_status'] = 'VERIFIED'
            result['verification_details'] = f"Confirmé par {len(verified_links)} lien(s) social(ux)"
        elif any(link['overall_score'] >= 0.4 for link in result['social_links']):
            result['verification_status'] = 'LIKELY_CORRECT'
            result['verification_details'] = "Correspondance probable mais non confirmée"
        
        return result

    async def verify_all_restaurants(self):
        """Vérifie tous les restaurants"""
        with open(self.json_path, 'r', encoding='utf-8') as f:
            restaurants = json.load(f)
        
        await self.initialize_browser()
        await self.login_to_facebook()
        
        results = []
        for restaurant in restaurants:
            print(f"\n🔍 Vérification de {restaurant.get('place_name')}...")
            try:
                result = await self.verify_restaurant(restaurant)
                results.append(result)
                await asyncio.sleep(random.uniform(5, 15))
            except Exception as e:
                print(f"Erreur: {str(e)}")
                continue
        
        await self.close_browser()
        
        # Sauvegarder les résultats
        with open(self.output_json, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        
        print(f"\n✅ Résultats sauvegardés dans {self.output_json}")
        return results

if __name__ == "__main__":
    verifier = SocialMediaVerifier("result.json")
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(verifier.verify_all_restaurants())
    finally:
        loop.close()