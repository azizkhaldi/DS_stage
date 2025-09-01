import asyncio
import json
import os
import random
import re
import time
from datetime import datetime
import logging
from playwright.async_api import async_playwright
import pytesseract
from PIL import Image
import cv2
import numpy as np

class StoriesTester:
    def __init__(self, output_dir="stories_test"):
        self.output_dir = output_dir
        self.stories_dir = os.path.join(output_dir, "stories")
        os.makedirs(self.stories_dir, exist_ok=True)
        
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
        self.logger = logging.getLogger(__name__)
        
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self.instagram_logged_in = False
        
        # Configurer le chemin de Tesseract si nécessaire (Windows)
        if os.name == 'nt':  # Windows
            try:
                pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
            except:
                self.logger.warning("Tesseract non trouvé, l'OCR ne fonctionnera pas")

    async def initialize_browser(self):
        """Initialise le navigateur"""
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            headless=False,
            args=[
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-web-security',
                '--start-maximized'
            ]
        )
        
        self.context = await self.browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            java_script_enabled=True,
            locale="fr-FR"
        )
        
        self.page = await self.context.new_page()

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

    async def human_like_delay(self, min_wait=1, max_wait=3):
        """Pause aléatoire pour sembler humain"""
        await asyncio.sleep(random.uniform(min_wait, max_wait))

    async def manual_instagram_login(self):
        """Connexion manuelle à Instagram"""
        if self.instagram_logged_in:
            return True
            
        self.logger.info("📸 Veuillez vous connecter manuellement à Instagram...")
        
        await self.page.goto("https://www.instagram.com/accounts/login/", timeout=120000)
        
        start_time = time.time()
        while True:
            if time.time() - start_time > 300:
                self.logger.warning("Timeout connexion Instagram")
                return False
            
            current_url = self.page.url.lower()
            if ("instagram.com" in current_url and 
                "login" not in current_url and 
                "accounts" not in current_url):
                self.logger.info("✅ Connexion Instagram réussie!")
                self.instagram_logged_in = True
                return True
            
            await asyncio.sleep(5)

    async def is_in_instagram_story_viewer(self):
        """Vérifie si on est dans un story viewer Instagram"""
        try:
            indicators = [
                'div[role="dialog"][aria-modal="true"]',
                'section[aria-label*="tory"]',
                'div[class*="story"]',
                'div[class*="Story"]',
                'video',
                'div[aria-label*="suivant"]',
                'div[aria-label*="next"]'
            ]
            
            for indicator in indicators:
                element = await self.page.query_selector(indicator)
                if element:
                    return True
            
            current_url = self.page.url.lower()
            if "/stories/" in current_url:
                return True
                
            return False
            
        except Exception as e:
            self.logger.warning(f"Erreur vérification story viewer Instagram: {e}")
            return False

    async def detect_instagram_story_elements(self):
        """Détecte les éléments de stories Instagram"""
        try:
            detection_methods = [
                lambda: self.page.query_selector_all('div[role="button"][tabindex="0"]'),
                lambda: self.page.query_selector_all('div[style*="border-radius: 50%"]'),
                lambda: self.page.query_selector_all('div[class*="circle"]'),
                lambda: self.page.query_selector_all('div[class*="ring"]'),
                lambda: self.page.query_selector_all('header div[role="button"]'),
                lambda: self.page.query_selector_all('header div[style*="background-image"]'),
                lambda: self.page.query_selector_all('div[aria-label*="story"]'),
                lambda: self.page.query_selector_all('div[aria-label*="Story"]')
            ]
            
            story_elements = []
            for i, method in enumerate(detection_methods):
                try:
                    elements = await method()
                    if elements:
                        self.logger.info(f"Méthode Instagram {i+1} a trouvé {len(elements)} éléments")
                        story_elements.extend(elements)
                except Exception as e:
                    continue
            
            # Filtrer les doublons
            unique_elements = []
            seen_ids = set()
            for element in story_elements:
                try:
                    element_id = await element.evaluate('el => el.id || el.className || el.outerHTML.substring(0, 100)')
                    if element_id not in seen_ids:
                        seen_ids.add(element_id)
                        unique_elements.append(element)
                except:
                    continue
            
            return unique_elements
            
        except Exception as e:
            self.logger.error(f"Erreur détection éléments stories Instagram: {e}")
            return []

    def analyze_promo_with_ocr(self, image_path):
        """Analyse l'image avec OCR pour détecter les promotions"""
        try:
            # Charger l'image
            img = cv2.imread(image_path)
            
            # Prétraitement de l'image pour améliorer l'OCR
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            
            # Appliquer un seuil pour obtenir une image binaire
            thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
            
            # Inverser les couleurs si nécessaire (texte blanc sur fond sombre)
            inverted = cv2.bitwise_not(thresh)
            
            # Utiliser pytesseract pour extraire le texte
            custom_config = r'--oem 3 --psm 6 -l fra+eng'
            text = pytesseract.image_to_string(inverted, config=custom_config)
            
            # Nettoyer le texte
            text = text.strip()
            
            if not text:
                return {
                    'has_promo': False,
                    'promo_type': None,
                    'promo_details': None,
                    'extracted_text': None
                }
            
            # Mots-clés pour détecter les promotions
            promo_keywords = {
                'promo': ['promo', 'promotion', 'soldes', 'sale', 'réduction', 'rabais', 'offre'],
                'discount': ['%', 'pourcent', 'percent', 'réduction', 'remise', 'discount'],
                'code': ['code', 'codepromo', 'promocode', 'coupon', 'voucher'],
                'limited': ['limitée', 'limited', 'temps', 'time', 'jusqu\'à', 'until'],
                'free': ['gratuit', 'free', 'offert', 'cadeau', 'gift'],
                'price': ['€', 'eur', 'euro', '$', 'usd', 'price', 'prix']
            }
            
            # Détecter le type de promotion
            promo_type = None
            promo_details = []
            text_lower = text.lower()
            
            # Vérifier chaque catégorie de promotion
            for category, keywords in promo_keywords.items():
                for keyword in keywords:
                    if keyword in text_lower:
                        if not promo_type:
                            promo_type = category
                        promo_details.append(keyword)
            
            # Si on a trouvé des indications de promotion
            has_promo = promo_type is not None
            
            return {
                'has_promo': has_promo,
                'promo_type': promo_type,
                'promo_details': promo_details if has_promo else None,
                'extracted_text': text if has_promo else None  # Ne retourner le texte que si promo détectée
            }
            
        except Exception as e:
            self.logger.error(f"Erreur lors de l'analyse OCR: {e}")
            return {
                'has_promo': False,
                'promo_type': None,
                'promo_details': None,
                'extracted_text': None
            }

    async def capture_all_instagram_stories(self):
        """Capture tous les stories Instagram disponibles et analyse les promotions"""
        stories_data = []
        try:
            story_index = 0
            max_stories = 10
            
            while story_index < max_stories:
                # Capturer le story actuel
                screenshot_filename = f"ig_story_{story_index}_{int(time.time())}.png"
                screenshot_path = os.path.join(self.stories_dir, screenshot_filename)
                await self.page.screenshot(path=screenshot_path)
                
                # Extraire le texte avec OCR
                ocr_result = self.analyze_promo_with_ocr(screenshot_path)
                
                # Extraire le texte HTML également
                html_text = await self.page.evaluate('''() => {
                    const textEl = document.querySelector('div[dir="auto"], div[class*="text"], div[class*="caption"]');
                    return textEl ? textEl.textContent.trim() : '';
                }''')
                
                # Combiner les résultats
                story_info = {
                    'text': html_text[:200] + "..." if len(html_text) > 200 else html_text,
                    'screenshot': screenshot_path,
                    'timestamp': datetime.now().isoformat(),
                    'index': story_index,
                    'has_promo': ocr_result['has_promo'],
                    'promo_type': ocr_result['promo_type'],
                    'promo_details': ocr_result['promo_details'],
                    'ocr_text': ocr_result['extracted_text']
                }
                
                stories_data.append(story_info)
                
                self.logger.info(f"✅ Story Instagram {story_index + 1} capturé - Promotion: {ocr_result['has_promo']}")
                if ocr_result['has_promo']:
                    self.logger.info(f"📢 Type de promotion: {ocr_result['promo_type']} - Détails: {ocr_result['promo_details']}")
                
                # Passer au story suivant
                if story_index < max_stories - 1:
                    try:
                        await asyncio.sleep(2)
                        viewport_size = await self.page.evaluate("() => ({width: window.innerWidth, height: window.innerHeight})")
                        await self.page.mouse.click(viewport_size['width'] * 0.85, viewport_size['height'] / 2)
                        await asyncio.sleep(2)
                        story_index += 1
                    except Exception as e:
                        self.logger.warning(f"Impossible de passer au story suivant: {e}")
                        break
                else:
                    break
                    
        except Exception as e:
            self.logger.error(f"Erreur capture stories Instagram: {e}")
        
        return stories_data

    async def test_instagram_stories(self, test_url, place_info):
        """Teste la récupération des stories Instagram pour une URL spécifique"""
        self.logger.info(f"🧪 Test des stories Instagram pour: {place_info.get('place_name', 'Unknown')}")
        
        try:
            stories_data = []
            has_stories = False
            
            if not self.instagram_logged_in:
                success = await self.manual_instagram_login()
                if not success:
                    return {
                        'has_stories': False,
                        'stories': []
                    }
            
            await self.page.goto(test_url, timeout=90000)
            await asyncio.sleep(5)
            
            story_elements = await self.detect_instagram_story_elements()
            self.logger.info(f"📖 Éléments de stories Instagram trouvés: {len(story_elements)}")
            
            if story_elements:
                self.logger.info("🔍 Test de clic sur les éléments Instagram...")
                
                for i, element in enumerate(story_elements[:5]):
                    try:
                        self.logger.info(f"Essai de clic sur l'élément {i+1}")
                        before_url = self.page.url
                        
                        await element.click()
                        await asyncio.sleep(3)
                        
                        is_in_viewer = await self.is_in_instagram_story_viewer()
                        
                        if is_in_viewer:
                            self.logger.info("✅ Story viewer Instagram détecté!")
                            has_stories = True
                            stories_data = await self.capture_all_instagram_stories()
                            break
                        else:
                            if self.page.url != before_url:
                                await self.page.go_back()
                                await asyncio.sleep(2)
                            
                    except Exception as e:
                        self.logger.warning(f"Erreur avec l'élément Instagram {i+1}: {e}")
                        continue
            
            # Statistiques sur les promotions détectées
            promo_count = sum(1 for story in stories_data if story.get('has_promo', False))
            
            return {
                'has_stories': has_stories,
                'stories': stories_data if has_stories else [],
                'promo_stats': {
                    'total_stories': len(stories_data),
                    'promo_stories': promo_count,
                    'promo_percentage': (promo_count / len(stories_data) * 100) if stories_data else 0
                }
            }
            
        except Exception as e:
            self.logger.error(f"Erreur vérification stories Instagram: {e}")
            return {
                'has_stories': False,
                'stories': [],
                'promo_stats': {
                    'total_stories': 0,
                    'promo_stories': 0,
                    'promo_percentage': 0
                }
            }

    def load_verification_data(self, file_path="verification_results.json"):
        """Charge les données de vérification depuis le fichier JSON"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return data
        except Exception as e:
            self.logger.error(f"Erreur lors du chargement du fichier {file_path}: {e}")
            return []

    def extract_instagram_urls(self, verification_data):
        """Extrait les URLs Instagram des données de vérification"""
        instagram_urls = []
        
        for item in verification_data:
            place_name = item.get('place_name', 'Unknown')
            social_links = item.get('social_links', [])
            
            for link in social_links:
                if link.get('type') == 'instagram' and link.get('verified', False):
                    instagram_urls.append({
                        'url': link['url'],
                        'place_name': place_name,
                        'place_info': item
                    })
        
        return instagram_urls

    async def run_tests_from_verification_file(self, verification_file="verification.json"):
        """Exécute les tests des stories pour tous les URLs Instagram du fichier de vérification"""
        # Charger les données de vérification
        verification_data = self.load_verification_data(verification_file)
        if not verification_data:
            self.logger.error("Aucune donnée de vérification trouvée")
            return []
        
        # Extraire les URLs Instagram vérifiés
        instagram_urls = self.extract_instagram_urls(verification_data)
        if not instagram_urls:
            self.logger.error("Aucun URL Instagram vérifié trouvé")
            return []
        
        self.logger.info(f"📋 {len(instagram_urls)} URLs Instagram vérifiés trouvés")
        
        # Initialiser le navigateur
        await self.initialize_browser()
        
        results = []
        
        # Tester chaque URL Instagram
        for idx, instagram_info in enumerate(instagram_urls):
            self.logger.info(f"🔍 Test {idx+1}/{len(instagram_urls)}: {instagram_info['place_name']}")
            
            result = await self.test_instagram_stories(
                instagram_info['url'], 
                instagram_info['place_info']
            )
            
            # Ajouter les informations du lieu aux résultats
            result['place_name'] = instagram_info['place_name']
            result['instagram_url'] = instagram_info['url']
            result['place_info'] = instagram_info['place_info']
            
            results.append(result)
            
            # Sauvegarder les résultats après chaque test
            output_file = os.path.join(self.output_dir, f"stories_test_results_{int(time.time())}.json")
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(results, f, indent=2, ensure_ascii=False)
            
            self.logger.info(f"📊 Résultats intermédiaires sauvegardés dans {output_file}")
            
            # Attendre un peu avant le prochain test
            await self.human_like_delay(2, 5)
        
        # Fermer le navigateur
        await self.close_browser()
        
        # Sauvegarder les résultats finaux
        final_output_file = os.path.join(self.output_dir, f"stories_test_final_results_{int(time.time())}.json")
        with open(final_output_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        
        self.logger.info(f"📊 Résultats finaux sauvegardés dans {final_output_file}")
        return results

# Fonction principale pour tester
async def main():
    verification_file = "verification.json"
    
    if not os.path.exists(verification_file):
        print(f"❌ Fichier {verification_file} non trouvé")
        return
    
    tester = StoriesTester()
    results = await tester.run_tests_from_verification_file(verification_file)
    
    print(f"\n✅ Test terminé!")
    print(f"Nombre de comptes Instagram testés: {len(results)}")
    
    # Statistiques globales
    total_stories = sum(len(result.get('stories', [])) for result in results)
    total_promo_stories = sum(result.get('promo_stats', {}).get('promo_stories', 0) for result in results)
    
    print(f"Total de stories analysés: {total_stories}")
    print(f"Total de stories avec promotions: {total_promo_stories}")
    
    # Détails par compte
    for result in results:
        if result['has_stories']:
            print(f"\n🏪 {result['place_name']}:")
            print(f"   Stories: {len(result['stories'])}")
            print(f"   Promotions: {result['promo_stats']['promo_stories']}")
            print(f"   Taux de promotion: {result['promo_stats']['promo_percentage']:.2f}%")
            
            # Afficher les détails des promotions
            for i, story in enumerate(result['stories']):
                if story['has_promo']:
                    print(f"   📢 Story {i+1}: {story['promo_type']} - {story['promo_details']}")
    
    print(f"\nRésultats détaillés sauvegardés dans le dossier {tester.output_dir}")

if __name__ == "__main__":
    asyncio.run(main())
