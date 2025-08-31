import asyncio
import json
import os
import random
import re
import time
from datetime import datetime
import logging
from playwright.async_api import async_playwright

class StoriesTester:
    def __init__(self, test_url, output_dir="stories_test"):
        self.test_url = test_url
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

    async def capture_all_instagram_stories(self):
        """Capture tous les stories Instagram disponibles"""
        stories_data = []
        try:
            story_index = 0
            max_stories = 10
            
            while story_index < max_stories:
                # Capturer le story actuel
                screenshot_filename = f"ig_story_{story_index}_{int(time.time())}.png"
                screenshot_path = os.path.join(self.stories_dir, screenshot_filename)
                await self.page.screenshot(path=screenshot_path)
                
                # Extraire le texte
                story_text = await self.page.evaluate('''() => {
                    const textEl = document.querySelector('div[dir="auto"], div[class*="text"], div[class*="caption"]');
                    return textEl ? textEl.textContent.trim() : 'Aucun texte détecté';
                }''')
                
                stories_data.append({
                    'text': story_text[:200] + "..." if len(story_text) > 200 else story_text,
                    'screenshot': screenshot_path,
                    'timestamp': datetime.now().isoformat(),
                    'index': story_index
                })
                
                self.logger.info(f"✅ Story Instagram {story_index + 1} capturé")
                
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

    async def test_instagram_stories(self):
        """Teste la récupération des stories Instagram"""
        self.logger.info("🧪 Test des stories Instagram")
        
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
            
            await self.page.goto(self.test_url, timeout=90000)
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
            
            return {
                'has_stories': has_stories,
                'stories': stories_data if has_stories else []
            }
            
        except Exception as e:
            self.logger.error(f"Erreur vérification stories Instagram: {e}")
            return {
                'has_stories': False,
                'stories': []
            }

    async def run_test(self):
        """Exécute le test des stories"""
        await self.initialize_browser()
        
        result = await self.test_instagram_stories()
        
        await self.close_browser()
        
        output_file = os.path.join(self.output_dir, f"stories_test_result_{int(time.time())}.json")
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        
        self.logger.info(f"📊 Résultats sauvegardés dans {output_file}")
        return result

# Fonction principale pour tester
async def main():
    test_url = input("Entrez l'URL Instagram à tester: ").strip()
    
    if not test_url:
        print("URL invalide")
        return
    
    tester = StoriesTester(test_url)
    results = await tester.run_test()
    
    print(f"\n✅ Test terminé!")
    print(f"Stories trouvés: {results['has_stories']}")
    print(f"Nombre de stories capturés: {len(results['stories'])}")
    print(f"Format JSON:")
    print(json.dumps(results, indent=2))

if __name__ == "__main__":
    asyncio.run(main())