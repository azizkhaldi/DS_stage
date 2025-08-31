import asyncio
import json
import os
import random
import re
import time
from datetime import datetime
from urllib.parse import urlparse
import logging
from playwright.async_api import async_playwright

class SocialMediaScraper:
    def __init__(self, json_path, output_dir="social_media_data"):
        self.json_path = json_path
        self.output_dir = output_dir
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self.instagram_logged_in = False
        
        # Configuration des dossiers (seulement screenshots et stories)
        self.screenshots_dir = os.path.join(output_dir, "screenshots")
        self.stories_dir = os.path.join(output_dir, "stories")
        
        for directory in [self.screenshots_dir, self.stories_dir]:
            os.makedirs(directory, exist_ok=True)
        
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
        self.logger = logging.getLogger(__name__)

    async def initialize_browser(self):
        """Initialise le navigateur avec une configuration desktop complète"""
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

    async def login_to_facebook(self):
        """Connexion manuelle à Facebook"""
        self.logger.info("🔐 Connexion à Facebook...")
        
        await self.page.goto("https://www.facebook.com/login", timeout=120000)
        self.logger.info("Veuillez vous connecter à Facebook...")
        
        start_time = time.time()
        while True:
            if time.time() - start_time > 300:
                self.logger.warning("Timeout connexion Facebook, continuation...")
                break
            current_url = self.page.url.lower()
            if ("facebook.com" in current_url and 
                "login" not in current_url and 
                "checkpoint" not in current_url):
                self.logger.info("✅ Connexion Facebook réussie")
                break
            await asyncio.sleep(5)

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

    async def navigate_with_retry(self, url, max_retries=3, timeout=90000):
        """Navigation avec retry et timeout augmenté"""
        for attempt in range(max_retries):
            try:
                await self.page.goto(url, timeout=timeout, wait_until="domcontentloaded")
                await asyncio.sleep(5)
                return True
            except Exception as e:
                self.logger.warning(f"Tentative {attempt + 1} échouée pour {url}: {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(5)
        return False

    async def scroll_to_element(self, element):
        """Scroll jusqu'à l'élément et le centre à l'écran"""
        await element.scroll_into_view_if_needed()
        await self.page.evaluate('''(element) => {
            element.scrollIntoView({behavior: 'smooth', block: 'center', inline: 'center'});
        }''', element)
        await self.human_like_delay(1, 2)

    async def extract_visible_text(self):
        """Extrait seulement le texte visible de la page (pas les scripts JSON)"""
        return await self.page.evaluate('''() => {
            // Sélecteur pour exclure les scripts, styles et éléments cachés
            const ignoreSelectors = [
                'script', 'style', 'noscript', 'meta', 'link',
                '[style*="display: none"]', 
                '[style*="visibility: hidden"]',
                '[aria-hidden="true"]',
                '.hidden', '[hidden]'
            ];
            
            // Fonction pour vérifier si un élément est visible
            function isVisible(element) {
                if (!element) return false;
                const style = window.getComputedStyle(element);
                return style.display !== 'none' && 
                       style.visibility !== 'hidden' && 
                       element.offsetWidth > 0 && 
                       element.offsetHeight > 0;
            }
            
            // Récupérer tout le texte visible
            const allElements = document.body.querySelectorAll('*');
            const visibleTexts = [];
            const seenTexts = new Set();
            
            for (const element of allElements) {
                // Vérifier si l'élément doit être ignoré
                let shouldIgnore = false;
                for (const selector of ignoreSelectors) {
                    if (element.matches(selector) || element.closest(selector)) {
                        shouldIgnore = true;
                        break;
                    }
                }
                
                if (shouldIgnore || !isVisible(element)) continue;
                
                // Prendre le texte si c'est un élément de contenu
                const text = element.textContent.trim();
                if (text && text.length > 2 && !seenTexts.has(text)) {
                    // Filtrer le texte JSON/technique
                    if (!text.startsWith('{"require":') && 
                        !text.startsWith('{"__html":') &&
                        !text.includes('"clpData":') &&
                        !text.includes('"gkxData":') &&
                        !text.includes('"bxData":')) {
                        seenTexts.add(text);
                        visibleTexts.push(text);
                    }
                }
            }
            
            return visibleTexts.join('\\n\\n');
        }''')

    def extract_metadata_from_text(self, raw_text, platform):
        """Extrait les métadonnées depuis le texte brut"""
        text_lower = raw_text.lower()
        
        if platform == 'facebook':
            return self._extract_facebook_metadata_from_text(text_lower, raw_text)
        elif platform == 'instagram':
            return self._extract_instagram_metadata_from_text(text_lower, raw_text)
        return {}

    def _extract_facebook_metadata_from_text(self, text_lower, raw_text):
        """Extrait les métadonnées Facebook depuis le texte brut"""
        metadata = {
            'likes': 0,
            'comments': 0,
            'shares': 0,
            'description': ''
        }
        
        # Patterns améliorés pour Facebook
        like_patterns = [
            r'(\d+[\.,]?\d*)\s*(j\'aime|like|réaction|👍)',
            r'([\d,]+)\s*personnes* aiment',
            r'([\d,]+)\s*likes',
            r'aimé par ([\d,]+)',
        ]
        
        comment_patterns = [
            r'(\d+[\.,]?\d*)\s*(commentaire|comment|réponse|💬)',
            r'([\d,]+)\s*commentaires',
            r'commenter par ([\d,]+)',
        ]
        
        share_patterns = [
            r'(\d+[\.,]?\d*)\s*(partage|share|🔁|↪)',
            r'([\d,]+)\s*partages',
            r'partagé ([\d,]+) fois',
        ]
        
        # Chercher les nombres
        for pattern in like_patterns:
            match = re.search(pattern, text_lower)
            if match:
                metadata['likes'] = self._parse_number(match.group(1))
                break
        
        for pattern in comment_patterns:
            match = re.search(pattern, text_lower)
            if match:
                metadata['comments'] = self._parse_number(match.group(1))
                break
        
        for pattern in share_patterns:
            match = re.search(pattern, text_lower)
            if match:
                metadata['shares'] = self._parse_number(match.group(1))
                break
        
        # Extraire la description (premières lignes significatives)
        metadata['description'] = self._extract_description(raw_text)
        
        return metadata

    def _extract_instagram_metadata_from_text(self, text_lower, raw_text):
        """Extrait les métadonnées Instagram depuis le texte brut"""
        metadata = {
            'likes': 0,
            'comments': 0,
            'description': ''
        }
        
        # Patterns améliorés pour Instagram
        like_patterns = [
            r'(\d+[\.,]?\d*[km]?)\s*(like|aimer|j\'aime|❤|♥)',
            r'([\d,]+[km]?)\s*likes',
            r'aimé par ([\d,]+[km]?)',
            r'([\d,]+[km]?)\s*❤️'
        ]
        
        comment_patterns = [
            r'(\d+[\.,]?\d*[km]?)\s*(commentaire|comment|💬)',
            r'([\d,]+[km]?)\s*commentaires',
            r'commenter par ([\d,]+[km]?)',
        ]
        
        # Chercher les nombres avec support k/m
        for pattern in like_patterns:
            match = re.search(pattern, text_lower)
            if match:
                metadata['likes'] = self._parse_number(match.group(1))
                break
        
        for pattern in comment_patterns:
            match = re.search(pattern, text_lower)
            if match:
                metadata['comments'] = self._parse_number(match.group(1))
                break
        
        # Extraire la description pour Instagram
        metadata['description'] = self._extract_instagram_description(raw_text)
        
        return metadata

    def _parse_number(self, number_str):
        """Parse les nombres avec k/m et séparateurs"""
        if not number_str:
            return 0
        
        # Nettoyer la chaîne
        clean_str = number_str.replace(',', '').replace('.', '').lower()
        
        # Vérifier les suffixes k/m
        if 'k' in clean_str:
            num = float(clean_str.replace('k', '')) * 1000
            return int(num)
        elif 'm' in clean_str:
            num = float(clean_str.replace('m', '')) * 1000000
            return int(num)
        
        # Nombre normal
        try:
            return int(clean_str)
        except ValueError:
            return 0

    def _extract_description(self, raw_text):
        """Extrait la description depuis le texte brut"""
        # Prendre les premières lignes significatives
        lines = raw_text.split('\n')
        meaningful_lines = []
        
        for line in lines:
            line = line.strip()
            if (len(line) > 20 and 
                not any(word in line.lower() for word in ['like', 'comment', 'share', 'partage', 'follow', 'suivre', 'views', 'vues'])):
                meaningful_lines.append(line)
                if len(meaningful_lines) >= 3:  # Maximum 3 lignes
                    break
        
        return ' '.join(meaningful_lines)[:500]  # Limiter à 500 caractères

    def _extract_instagram_description(self, raw_text):
        """Extrait la description Instagram spécifique"""
        lines = raw_text.split('\n')
        description_lines = []
        
        # Chercher le texte descriptif (éviter les métadonnées)
        for i, line in enumerate(lines):
            line = line.strip()
            if (len(line) > 10 and 
                not any(word in line.lower() for word in [
                    'like', 'comment', 'view', 'vu', 'follow', 'suivre',
                    'likes', 'comments', 'views', 'vues', 'posted', 'publié'
                ]) and
                not re.match(r'^\d+[km]?$', line) and  # Éviter les nombres seuls
                not line.startswith('@') and  # Éviter les mentions
                not line.startswith('#')):  # Éviter les hashtags
                description_lines.append(line)
        
        return ' '.join(description_lines[:5])[:400]  # 5 lignes max, 400 caractères

    async def check_and_scrape_facebook_stories(self, fb_url, restaurant_id, restaurant_name):
        """Vérifie et scrape les stories Facebook s'ils sont présents"""
        try:
            stories_data = []
            has_stories = False
            
            # Aller sur la page principale
            await self.page.goto(fb_url, timeout=90000)
            await asyncio.sleep(5)
            
            # Vérifier la présence de stories
            story_elements = await self.page.query_selector_all('div[aria-label="Story"]')
            
            if story_elements:
                self.logger.info(f"📖 Stories Facebook trouvés: {len(story_elements)}")
                has_stories = True
                
                # Cliquer sur le premier story pour ouvrir la visionneuse
                await story_elements[0].click()
                await asyncio.sleep(3)
                
                # Capturer chaque story
                story_index = 0
                while True:
                    # Capturer la screenshot du story
                    safe_name = re.sub(r'[^a-zA-Z0-9_]', '_', restaurant_name)[:30]
                    screenshot_filename = f"fb_{restaurant_id}_{safe_name}_story_{story_index}_{int(time.time())}.png"
                    screenshot_path = os.path.join(self.stories_dir, screenshot_filename)
                    
                    # Trouver l'élément du story
                    story_container = await self.page.query_selector('div[role="main"]') or await self.page.query_selector('div[aria-label="Story"]')
                    if story_container:
                        await story_container.screenshot(path=screenshot_path)
                    
                    # Extraire le texte du story
                    story_text = await self.page.evaluate('''() => {
                        const textEl = document.querySelector('div[dir="auto"]');
                        return textEl ? textEl.textContent.trim() : '';
                    }''')
                    
                    stories_data.append({
                        'text': story_text[:200] + "..." if len(story_text) > 200 else story_text,
                        'screenshot': screenshot_path,
                        'timestamp': datetime.now().isoformat()
                    })
                    
                    self.logger.info(f"✅ Story Facebook {story_index + 1} capturé")
                    
                    # Essayer de passer au story suivant
                    try:
                        next_button = await self.page.query_selector('div[aria-label="Story suivant"]')
                        if next_button:
                            await next_button.click()
                            await asyncio.sleep(2)
                            story_index += 1
                        else:
                            break
                    except:
                        break
            
            return {
                'has_stories': has_stories,
                'stories': stories_data
            }
            
        except Exception as e:
            self.logger.error(f"Erreur vérification stories Facebook: {e}")
            return {'has_stories': False, 'stories': []}

    async def check_and_scrape_instagram_stories(self, ig_url, restaurant_id, restaurant_name):
        """Vérifie et scrape les stories Instagram s'ils sont présents"""
        try:
            stories_data = []
            has_stories = False
            
            if not self.instagram_logged_in:
                success = await self.manual_instagram_login()
                if not success:
                    return {'has_stories': False, 'stories': []}
            
            # Aller sur la page principale
            await self.page.goto(ig_url, timeout=90000)
            await asyncio.sleep(5)
            
            # Vérifier la présence de stories (cercle en haut)
            story_elements = await self.page.query_selector_all('div[role="button"] > div:has(div[style*="background-image"])')
            
            if not story_elements:
                # Essayer une autre sélection pour les stories
                story_elements = await self.page.query_selector_all('div[class*="story"]')
            
            if story_elements:
                self.logger.info(f"📖 Stories Instagram trouvés: {len(story_elements)}")
                has_stories = True
                
                # Cliquer sur le premier story
                await story_elements[0].click()
                await asyncio.sleep(3)
                
                # Capturer chaque story
                story_index = 0
                while True:
                    # Capturer la screenshot du story
                    safe_name = re.sub(r'[^a-zA-Z0-9_]', '_', restaurant_name)[:30]
                    screenshot_filename = f"ig_{restaurant_id}_{safe_name}_story_{story_index}_{int(time.time())}.png"
                    screenshot_path = os.path.join(self.stories_dir, screenshot_filename)
                    
                    # Prendre une capture d'écran de tout le story
                    await self.page.screenshot(path=screenshot_path)
                    
                    # Extraire le texte du story
                    story_text = await self.page.evaluate('''() => {
                        const textEl = document.querySelector('div[role="dialog"] div[dir="auto"]');
                        return textEl ? textEl.textContent.trim() : '';
                    }''')
                    
                    stories_data.append({
                        'text': story_text[:200] + "..." if len(story_text) > 200 else story_text,
                        'screenshot': screenshot_path,
                        'timestamp': datetime.now().isoformat()
                    })
                    
                    self.logger.info(f"✅ Story Instagram {story_index + 1} capturé")
                    
                    # Essayer de passer au story suivant
                    try:
                        next_area = await self.page.query_selector('div[role="dialog"]')
                        if next_area:
                            # Cliquer sur la droite pour le story suivant
                            box = await next_area.bounding_box()
                            if box:
                                await self.page.mouse.click(box['x'] + box['width'] * 0.8, box['y'] + box['height'] / 2)
                                await asyncio.sleep(2)
                                story_index += 1
                            else:
                                break
                        else:
                            break
                    except:
                        break
            
            return {
                'has_stories': has_stories,
                'stories': stories_data
            }
            
        except Exception as e:
            self.logger.error(f"Erreur vérification stories Instagram: {e}")
            return {'has_stories': False, 'stories': []}

    async def scrape_facebook_photos_section(self, fb_url, restaurant_id, restaurant_name, max_photos=3):
        """Scrape la section photos de Facebook avec texte visible seulement"""
        try:
            photos_data = []
            
            # Naviguer directement vers les photos publiées
            photos_url = fb_url.rstrip('/') + '/photos_by/'
            self.logger.info(f"📱 Navigation vers les photos publiées: {photos_url}")
            
            success = await self.navigate_with_retry(photos_url)
            if not success:
                # Essayer l'URL standard si celle-ci ne fonctionne pas
                photos_url = fb_url.rstrip('/') + '/photos/'
                self.logger.info(f"📱 Navigation vers: {photos_url}")
                success = await self.navigate_with_retry(photos_url)
                if not success:
                    return photos_data
            
            await asyncio.sleep(8)
            
            # Faire défiler pour charger plus de contenu
            for _ in range(3):
                await self.page.evaluate("window.scrollBy(0, 1500)")
                await self.human_like_delay(3, 5)
            
            # Trouver les photos publiées (éviter photos de profil/couverture)
            photo_elements = await self.page.query_selector_all('a[href*="/photo.php?fbid="], a[href*="/photos/"]')
            
            # Filtrer pour éviter les photos de profil/couverture
            filtered_photos = []
            for element in photo_elements:
                href = await element.get_attribute('href')
                if href and ('/photo.php?fbid=' in href or '/photos/' in href):
                    if '/pb.' not in href:  # Éviter les photos de profil
                        filtered_photos.append(element)
            
            self.logger.info(f"📸 {len(filtered_photos)} photos publiées trouvées")
            
            # ✅ CORRECTION - PRENDRE LES PREMIÈRES PHOTOS (LES PLUS RÉCENTES)
            recent_photos = filtered_photos[:max_photos]
            
            for i, photo_element in enumerate(recent_photos):
                try:
                    # Cliquer sur la photo pour l'ouvrir
                    await photo_element.click()
                    await asyncio.sleep(5)
                    
                    # Attendre que le modal de photo s'ouvre
                    await self.page.wait_for_selector('div[role="dialog"]', timeout=10000)
                    
                    # Capturer screenshot
                    safe_name = re.sub(r'[^a-zA-Z0-9_]', '_', restaurant_name)[:30]
                    screenshot_filename = f"fb_{restaurant_id}_{safe_name}_photo_{i}_{int(time.time())}.png"
                    screenshot_path = os.path.join(self.screenshots_dir, screenshot_filename)
                    
                    # Prendre screenshot de la photo ouverte
                    photo_modal = await self.page.query_selector('div[role="dialog"]')
                    if photo_modal:
                        await photo_modal.screenshot(path=screenshot_path)
                    else:
                        await self.page.screenshot(path=screenshot_path)
                    
                    # EXTRAIRE SEULEMENT LE TEXTE VISIBLE
                    raw_text = await self.extract_visible_text()
                    
                    # Attendre un peu pour que le contenu se charge
                    await asyncio.sleep(2)
                    
                    # EXTRACTION DES MÉTADONNÉES DEPUIS LE TEXTE VISIBLE
                    metadata = self.extract_metadata_from_text(raw_text, 'facebook')
                    
                    # SUPPRIMER raw_text et text_length du résultat final
                    photos_data.append({
                        'type': 'facebook_photo',
                        'description': metadata['description'],
                        'likes': metadata['likes'],
                        'comments': metadata['comments'],
                        'shares': metadata['shares'],
                        'engagement': metadata['likes'] + metadata['comments'] + metadata['shares'],
                        'screenshot': screenshot_path,
                        'scraped_at': datetime.now().isoformat()
                    })
                    
                    self.logger.info(f"✅ Photo Facebook {i+1}: {metadata['likes']} 👍 {metadata['comments']} 💬 {metadata['shares']} 🔄")
                    
                    # Fermer le modal de photo
                    close_button = await self.page.query_selector('div[aria-label="Fermer"], div[aria-label="Close"]')
                    if close_button:
                        await close_button.click()
                    else:
                        # Cliquer en dehors pour fermer
                        await self.page.mouse.click(10, 10)
                    
                    await self.human_like_delay(3, 5)
                    
                except Exception as e:
                    self.logger.error(f"Erreur sur photo {i}: {e}")
                    # Essayer de fermer le modal en cas d'erreur
                    try:
                        close_button = await self.page.query_selector('div[aria-label="Fermer"], div[aria-label="Close"]')
                        if close_button:
                            await close_button.click()
                        else:
                            await self.page.mouse.click(10, 10)
                    except:
                        pass
                    continue
            
            return photos_data
            
        except Exception as e:
            self.logger.error(f"Erreur scraping photos Facebook: {e}")
            return []

    async def scrape_instagram_individual_posts(self, ig_url, restaurant_id, restaurant_name, max_posts=3):
        """Scrape chaque post Instagram avec texte visible seulement"""
        try:
            if not self.instagram_logged_in:
                success = await self.manual_instagram_login()
                if not success:
                    self.logger.warning("Non connecté à Instagram")
                    return []
            
            self.logger.info(f"📸 Navigation vers: {ig_url}")
            success = await self.navigate_with_retry(ig_url)
            if not success:
                return []
            
            await asyncio.sleep(10)
            
            # Faire défiler pour charger les posts
            for _ in range(3):
                await self.page.evaluate("window.scrollBy(0, 1200)")
                await self.human_like_delay(3, 5)
            
            # Chercher les liens des posts
            post_links = await self.page.evaluate('''() => {
                const links = [];
                const postElements = document.querySelectorAll('a[href*="/p/"], a[href*="/reel/"]');
                for (const element of postElements) {
                    const href = element.getAttribute('href');
                    if (href && !href.includes('/stories/')) {
                        links.push('https://www.instagram.com' + href);
                    }
                }
                return links.slice(0, 15);
            }''')
            
            self.logger.info(f"🔗 {len(post_links)} posts Instagram trouvés")
            
            posts_data = []
            
            for i, post_url in enumerate(post_links[:max_posts]):
                try:
                    # Ouvrir le post individuel
                    await self.page.goto(post_url, timeout=120000)
                    await asyncio.sleep(8)
                    
                    # Capturer screenshot
                    safe_name = re.sub(r'[^a-zA-Z0-9_]', '_', restaurant_name)[:30]
                    screenshot_filename = f"ig_{restaurant_id}_{safe_name}_post_{i}_{int(time.time())}.png"
                    screenshot_path = os.path.join(self.screenshots_dir, screenshot_filename)
                    
                    await self.page.screenshot(path=screenshot_path)
                    
                    # EXTRAIRE SEULEMENT LE TEXTE VISIBLE
                    raw_text = await self.extract_visible_text()
                    
                    # Attendre que le contenu se charge
                    await asyncio.sleep(3)
                    
                    # EXTRACTION DES MÉTADONNÉES DEPUIS LE TEXTE VISIBLE
                    metadata = self.extract_metadata_from_text(raw_text, 'instagram')
                    
                    # Extraire la date simplement
                    date_info = await self.page.evaluate('''() => {
                        const timeEl = document.querySelector('time');
                        return timeEl ? timeEl.getAttribute('datetime') : '';
                    }''')
                    
                    # SUPPRIMER raw_text et text_length du résultat final
                    posts_data.append({
                        'type': 'instagram_post',
                        'description': metadata['description'],
                        'likes': metadata['likes'],
                        'comments': metadata['comments'],
                        'engagement': metadata['likes'] + metadata['comments'],
                        'date': date_info,
                        'post_url': post_url,
                        'screenshot': screenshot_path,
                        'scraped_at': datetime.now().isoformat()
                    })
                    
                    self.logger.info(f"✅ Post Instagram {i+1}: {metadata['likes']} ❤️ {metadata['comments']} 💬")
                    
                    await self.human_like_delay(5, 8)
                    
                except Exception as e:
                    self.logger.error(f"Erreur scraping post Instagram {post_url}: {e}")
                    continue
            
            return posts_data
            
        except Exception as e:
            self.logger.error(f"Erreur scraping Instagram: {e}")
            return []

    async def scrape_restaurant_social_media(self, restaurant):
        """Scrape les médias sociaux d'un restaurant"""
        result = {
            'id': restaurant.get('id'),
            'place_name': restaurant.get('place_name'),
            'nom': restaurant.get('nom'),
            'facebook_data': {'photos': [], 'stories': [], 'has_stories': False},
            'instagram_data': {'posts': [], 'stories': [], 'has_stories': False},
            'scraped_at': datetime.now().isoformat()
        }
        
        restaurant_id = restaurant.get('id', 'unknown')
        restaurant_name = restaurant.get('place_name', 'unknown')
        
        # Facebook - seulement les photos publiées
        facebook_links = [link for link in restaurant.get('social_links', []) 
                         if link['type'] == 'facebook' and link['verified']]
        
        if facebook_links:
            try:
                self.logger.info(f"📱 Scraping Facebook Photos: {restaurant_name}")
                
                # Vérifier et scraper les stories Facebook
                fb_stories = await self.check_and_scrape_facebook_stories(
                    facebook_links[0]['url'], restaurant_id, restaurant_name
                )
                result['facebook_data']['has_stories'] = fb_stories['has_stories']
                result['facebook_data']['stories'] = fb_stories['stories']
                
                # Scraper les photos Facebook publiées (3 dernières)
                photos = await self.scrape_facebook_photos_section(
                    facebook_links[0]['url'], restaurant_id, restaurant_name, max_photos=3
                )
                result['facebook_data']['photos'] = photos
            except Exception as e:
                self.logger.error(f"Erreur scraping Facebook: {e}")
        
        # Instagram - 3 posts minimum
        instagram_links = [link for link in restaurant.get('social_links', []) 
                          if link['type'] == 'instagram' and link['verified']]
        
        if instagram_links:
            try:
                self.logger.info(f"📸 Scraping Instagram: {restaurant_name}")
                
                # Vérifier et scraper les stories Instagram
                ig_stories = await self.check_and_scrape_instagram_stories(
                    instagram_links[0]['url'], restaurant_id, restaurant_name
                )
                result['instagram_data']['has_stories'] = ig_stories['has_stories']
                result['instagram_data']['stories'] = ig_stories['stories']
                
                # Scraper les posts Instagram (3 minimum)
                posts = await self.scrape_instagram_individual_posts(
                    instagram_links[0]['url'], restaurant_id, restaurant_name, max_posts=3
                )
                result['instagram_data']['posts'] = posts
            except Exception as e:
                self.logger.error(f"Erreur scraping Instagram: {e}")
        
        return result

    async def scrape_all_restaurants(self, max_restaurants=None):
        """Scrape tous les restaurants"""
        with open(self.json_path, 'r', encoding='utf-8') as f:
            restaurants = json.load(f)
        
        if max_restaurants:
            restaurants = restaurants[:max_restaurants]
        
        await self.initialize_browser()
        
        # Se connecter à Facebook
        await self.login_to_facebook()
        
        results = []
        for restaurant in restaurants:
            self.logger.info(f"\n🎯 Scraping: {restaurant.get('place_name')}")
            try:
                result = await self.scrape_restaurant_social_media(restaurant)
                results.append(result)
                
                # Sauvegarder progressivement
                output_file = os.path.join(self.output_dir, f"social_media_data_{int(time.time())}.json")
                with open(output_file, 'w', encoding='utf-8') as f:
                    json.dump(results, f, indent=2, ensure_ascii=False)
                
                self.logger.info(f"✅ Données sauvegardées pour {restaurant['place_name']}")
                await asyncio.sleep(random.uniform(15, 25))
                
            except Exception as e:
                self.logger.error(f"❌ Erreur scraping {restaurant['place_name']}: {e}")
                continue
        
        await self.close_browser()
        
        # Sauvegarde finale
        final_output = os.path.join(self.output_dir, "social_media_data_final.json")
        with open(final_output, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        
        self.logger.info(f"\n🎉 Scraping terminé! Résultats sauvegardés dans {final_output}")
        return results

# Fonction principale
async def main():
    scraper = SocialMediaScraper("verification_results.json")
    
    try:
        await scraper.scrape_all_restaurants(max_restaurants=1)
    except Exception as e:
        scraper.logger.error(f"Erreur principale: {e}")
    finally:
        await scraper.close_browser()

if __name__ == "__main__":
    asyncio.run(main())