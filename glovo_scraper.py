import asyncio
from playwright.async_api import async_playwright
import json
import re
from urllib.parse import urljoin, urlparse
import os
from datetime import datetime

def remove_duplicate_products(products):
    """Supprimer les produits en double basé sur le nom, la section et le prix"""
    unique_products = []
    seen_products = set()
    
    for product in products:
        # Créer une clé unique basée sur le nom, la section et le prix
        product_key = (
            product.get("product_name", "").strip().lower(),
            product.get("section", "").strip().lower(),
            product.get("product_price", "").strip().lower()
        )
        
        # Si le produit n'a pas été vu, l'ajouter à la liste
        if product_key not in seen_products:
            seen_products.add(product_key)
            unique_products.append(product)
        else:
            print(f"Produit en double ignoré: {product.get('product_name', 'N/A')}")
    
    return unique_products

def clean_product_name(name):
    """Nettoyer le nom du produit pour standardiser et éviter les doublons"""
    if name == "N/A":
        return name
    
    # Supprimer les espaces multiples et les caractères spéciaux inutiles
    name = re.sub(r'\s+', ' ', name).strip()
    
    # Standardiser la casse (première lettre en majuscule, reste en minuscule)
    name = name.capitalize()
    
    # Supprimer les préfixes/suffixes communs qui causent des doublons
    remove_patterns = [
        r'^\s*[-•*]\s*',  # Caractères spéciaux au début
        r'\s*[-•*]\s*$',  # Caractères spéciaux à la fin
        r'\s+$',          # Espaces à la fin
        r'^\s+',          # Espaces au début
    ]
    
    for pattern in remove_patterns:
        name = re.sub(pattern, '', name)
    
    return name

def filter_product_name(name, description):
    """
    Filtrer le nom du produit: si c'est un nombre, prendre les premiers mots de la description
    ou laisser vide si aucune information valide n'est disponible
    """
    if name == "N/A" or not name:
        return "N/A"
    
    # Vérifier si le nom est principalement numérique (comme "5,300")
    if re.match(r'^[\d\.,\s]+$', name.strip()):
        # Si le nom est un nombre, essayer d'extraire des informations de la description
        if description != "N/A" and description:
            # Prendre les 2-3 premiers mots de la description
            words = description.split()
            if len(words) >= 2:
                # Prendre les 2-3 premiers mots significatifs
                filtered_name = ' '.join(words[:3])
                print(f"Nom filtré: '{name}' -> '{filtered_name}' (à partir de la description)")
                return filtered_name
            else:
                # Si la description est trop courte, la prendre entièrement
                return description
        else:
            # Si pas de description, retourner N/A
            return "N/A"
    
    # Si le nom n'est pas numérique, le retourner tel quel
    return name

async def scrape_glovo():
    async with async_playwright() as p:
        # Configuration du browser
        browser = await p.chromium.launch(
            headless=False,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-accelerated-2d-canvas',
                '--no-first-run',
                '--no-zygote',
                '--disable-gpu'
            ]
        )
        
        # Configuration du contexte
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.110 Safari/537.36",
            locale="en-US",
            timezone_id="Europe/Paris",
        )
        
        # Désactiver les détections WebDriver
        await context.add_init_script("""
            delete navigator.__proto__.webdriver;
            Object.defineProperty(navigator, 'webdriver', { get: () => false });
        """)
        
        page = await context.new_page()
        
        # Villes à scraper
        villes = [ "sfax" , "monastir" , "sousse", "tunis"]
                   
        # Catégories à scraper
        categories = {
            "food": "food_1",
            "boutiques": "boutiques_22", 
            "supermarches": "supermarches_4"
        }
        
        # Options de promotion
        promo_params = "?promo-type=PERCENTAGE_DISCOUNT&promotions=PROMOTIONS"
        
        # Dossier pour stocker les résultats
        os.makedirs("glovo_data", exist_ok=True)
        
        # Obtenir la date et l'heure actuelles pour le nom de fichier
        current_date = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        
        for ville in villes:
            print(f"Scraping de la ville: {ville}")
            
            for cat_name, cat_id in categories.items():
                # Construire l'URL
                if cat_name == "supermarches" or cat_name == "boutiques":
                    url = f"https://glovoapp.com/en/tn/{ville}/categories/{cat_id}"
                else:
                    url = f"https://glovoapp.com/en/tn/{ville}/categories/{cat_id}{promo_params}"
                
                print(f"Scraping de l'URL: {url}")
                
                try:
                    # Aller à la page avec un timeout plus long
                    await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                    
                    # Accepter les cookies si la bannière est présente
                    await accept_cookies(page)
                    
                    # Attendre que le contenu se charge
                    await page.wait_for_timeout(5000)
                    
                    # Faire défiler la page pour charger tout le contenu
                    await scroll_page(page)
                    
                    # Vérifier si nous sommes sur la bonne page
                    page_title = await page.title()
                    print(f"Titre de la page: {page_title}")
                    
                    # Scraper le texte brut de la page
                    raw_text = await scrape_raw_text(page)
                    
                    # Scraper les données des catégories avec leurs produits
                    categories_data = await scrape_categories_with_products(context, page, ville, cat_name)
                    
                    # Sauvegarder les données dans un seul fichier avec la date
                    filename = f"glovo_data/{ville}_{cat_name}_{current_date}.json"
                    with open(filename, 'w', encoding='utf-8') as f:
                        json.dump({
                            "scraping_date": datetime.now().isoformat(),
                            "city": ville,
                            "category_type": cat_name,
                            "url": url,
                            "page_title": page_title,
                            "raw_text": raw_text[:5000] + "..." if len(raw_text) > 5000 else raw_text,
                            "data": categories_data
                        }, f, ensure_ascii=False, indent=2)
                    
                    print(f"Données complètes sauvegardées dans {filename}")
                    print(f"Nombre de catégories trouvées: {len(categories_data)}")
                    
                except Exception as e:
                    print(f"Erreur lors du scraping de {url}: {e}")
                    continue
        
        await browser.close()

async def accept_cookies(page):
    """Accepter les cookies si la bannière est présente"""
    try:
        # Attendre un peu pour que la page charge
        await page.wait_for_timeout(2000)
        
        # Essayer différents sélecteurs pour la bannière de cookies
        cookie_selectors = [
            'button#onetrust-accept-btn-handler',
            'button[aria-label*="cookie"] i',
            'button[aria-label*="Cookie"] i',
            'button[class*="cookie"]',
            'button:has-text("Accept")',
            'button:has-text("ACCEPT")',
            'button:has-text("Accepter")',
            'button:has-text("J\'accepte")',
            'button:has-text("Tout accepter")'
        ]
        
        for selector in cookie_selectors:
            try:
                accept_button = await page.query_selector(selector)
                if accept_button and await accept_button.is_visible():
                    await accept_button.click()
                    print("Cookies acceptés")
                    await page.wait_for_timeout(1000)
                    return True
            except:
                continue
                
        print("Aucune bannière de cookies trouvée ou déjà acceptée")
        return False
    except Exception as e:
        print(f"Erreur lors de l'acceptation des cookies: {e}")
        return False

async def scroll_page(page):
    """Faire défiler la page pour charger tout le contenu"""
    print("Défilement de la page pour charger tout le contenu...")
    
    try:
        # Obtenir la hauteur de la page
        previous_height = await page.evaluate("document.body.scrollHeight")
        
        # Faire défiler jusqu'en bas de la page
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(3000)
        
        # Vérifier si de nouveaux contenus ont été chargés
        current_height = await page.evaluate("document.body.scrollHeight")
        
        # Continuer à faire défiler si la hauteur a changé
        scroll_attempts = 0
        while current_height != previous_height and scroll_attempts < 10:
            previous_height = current_height
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(3000)
            current_height = await page.evaluate("document.body.scrollHeight")
            scroll_attempts += 1
            print(f"Défilement {scroll_attempts}, hauteur: {current_height}")
        
        print("Défilement terminé")
    except Exception as e:
        print(f"Erreur lors du défilement: {e}")

async def scrape_raw_text(page):
    """Scraper tout le texte brut de la page"""
    try:
        # Obtenir tout le texte de la page
        raw_text = await page.evaluate("""
            () => {
                // Fonction pour extraire tout le texte visible
                function getVisibleText(element) {
                    let text = '';
                    if (element.nodeType === Node.TEXT_NODE && element.textContent.trim() !== '') {
                        text = element.textContent.trim() + ' ';
                    } else {
                        for (let child of element.childNodes) {
                            if (child.nodeType === Node.ELEMENT_NODE) {
                                // Vérifier si l'élément is visible
                                const style = window.getComputedStyle(child);
                                if (style.display !== 'none' and style.visibility !== 'hidden' and style.opacity !== '0') {
                                    text += getVisibleText(child);
                                }
                            } else if (child.nodeType === Node.TEXT_NODE) {
                                text += child.textContent.trim() + ' ';
                            }
                        }
                    }
                    return text;
                }
                
                return getVisibleText(document.body);
            }
        """)
        
        # Nettoyer le texte (supprimer les espaces multiples)
        raw_text = re.sub(r'\s+', ' ', raw_text).strip()
        return raw_text
    except Exception as e:
        print(f"Erreur lors du scraping du texte brut: {e}")
        return ""

async def scrape_categories_with_products(context, page, ville, cat_type):
    """Scraper les catégories et leurs produits"""
    categories_data = []
    
    # Attendre que les catégories se chargent
    try:
        # Essayer d'attendre les cartes de catégories
        await page.wait_for_selector('[data-test-id="category-cell"]', timeout=10000)
    except:
        print("Timeout en attendant les catégories, tentative de continuer...")
    
    # Sélecteurs plus spécifiques pour les catégories
    category_selectors = [
        '[data-test-id="category-cell"]',
        'a[href*="/store/"]',
        'a[href*="/tn/en/"]',
        '.store-card',
        '.venue-card',
        '.category-card',
        '[class*="store-card"]',
        '[class*="venue-card"]'
    ]
    
    categories = []
    for selector in category_selectors:
        try:
            found_categories = await page.query_selector_all(selector)
            if found_categories and len(found_categories) > 0:
                print(f"Trouvé {len(found_categories)} éléments avec le sélecteur: {selector}")
                # Filtrer pour ne garder que les éléments pertinents
                for cat in found_categories:
                    if await is_probably_category(cat):
                        categories.append(cat)
                if categories:
                    print(f"Trouvé {len(categories)} catégories après filtrage")
                    break
        except Exception as e:
            print(f"Erreur avec le sélecteur {selector}: {e}")
            continue
    
    # Si aucun sélecteur standard ne fonctionne, essayer une approche plus large
    if not categories:
        print("Aucune catégorie trouvée avec les sélecteurs standards, tentative avec une approche plus large...")
        all_elements = await page.query_selector_all('a, div, section, article')
        categories = [el for el in all_elements if await is_probably_category(el)]
    
    if not categories:
        print("Aucune catégorie trouvée sur la page")
        # Prendre une capture d'écran pour debugger
        await page.screenshot(path="glovo_data/debug_no_categories.png")
        return categories_data
    
    print(f"Traitement de {len(categories)} catégories...")
    
    for i, category in enumerate(categories):
        try:
            print(f"Traitement de la catégorie {i+1}/{len(categories)}")
            
            # Extraire les informations de la catégorie
            category_info = await extract_category_info(category)
            
            # Vérifier si c'est une vraie catégorie (pas un faux positif)
            if (category_info['category_name'] == "N/A" or 
                category_info['category_url'] == "N/A" or
                "glovoapp.com" not in category_info['category_url']):
                print(f"Catégorie ignorée (données insuffisantes): {category_info['category_name']}")
                continue
            
            print(f"Scraping des produits pour: {category_info.get('category_name', 'Unknown')}")
            
            # Scraper les produits de cette catégorie
            products = await scrape_products(context, category_info['category_url'], cat_type)
            
            # CORRECTION: Déduplication finale
            products = remove_duplicate_products(products)
            print(f"Produits uniques après déduplication: {len(products)}")
            
            categories_data.append({
                **category_info,
                "products": products
            })
            
        except Exception as e:
            print(f"Erreur lors du scraping d'une catégorie: {e}")
            continue
    
    return categories_data

async def is_probably_category(element):
    """Déterminer si un élément est probablement une catégorie"""
    try:
        # Vérifier si l'élément est visible
        if not await element.is_visible():
            return False
        
        # Vérifier la taille et le contenu
        bounding_box = await element.bounding_box()
        if not bounding_box or bounding_box['height'] < 100 or bounding_box['width'] < 100:
            return False
        
        # Vérifier le contenu texte
        text = await element.text_content()
        if not text or len(text.strip()) < 10:
            return False
        
        # Vérifier si cela contient des éléments communs aux catégories
        has_image = await element.query_selector('img')
        has_title = await element.query_selector('h1, h2, h3, h4, h5, h6, [class*="title"], [class*="name"]')
        
        return has_image or has_title
    except:
        return False

async def extract_category_info(category):
    """Extraire les informations d'une catégorie"""
    try:
        # Nom de la catégorie
        name = "N/A"
        name_selectors = [
            '[data-test-id="category-cell-name"]',
            '.store-name',
            '.venue-name',
            'h1, h2, h3, h4, h5, h6',
            '[class*="title"]',
            '[class*="name"]'
        ]
        
        for selector in name_selectors:
            try:
                name_elem = await category.query_selector(selector)
                if name_elem:
                    name = await name_elem.text_content()
                    name = name.strip() if name else "N/A"
                    if name != "N/A":
                        break
            except:
                continue
        
        # URL de la catégorie
        url = "N/A"
        if await category.get_attribute('href'):
            url = await category.get_attribute('href')
        else:
            link_elem = await category.query_selector('a')
            if link_elem:
                url = await link_elem.get_attribute('href')
        
        if url and url != "N/A":
            url = urljoin("https://glovoapp.com", url)
        
        # Image
        image = "N/A"
        img_elem = await category.query_selector('img')
        if img_elem:
            image = await img_elem.get_attribute('src')
            if image and not image.startswith('http'):
                image = urljoin("https://glovoapp.com", image)
        
        # Extraire les autres informations
        full_text = await category.text_content()
        
        # Utiliser des expressions régulières pour extraire les informations
        delivery_fee_match = re.search(r'(\d+[\.,]?\d*\s*[DT|€|£|$])', full_text)
        delivery_fee = delivery_fee_match.group(1) if delivery_fee_match else "N/A"
        
        delivery_time_match = re.search(r'(\d+\s*-\s*\d+\s*min|\d+\s*min)', full_text)
        delivery_time = delivery_time_match.group(1) if delivery_time_match else "N/A"
        
        rating_match = re.search(r'(\d+%)', full_text)
        rating = rating_match.group(1) if rating_match else "N/A"
        
        reviews_match = re.search(r'\((\d+)\)', full_text)
        reviews = reviews_match.group(1) if reviews_match else "N/A"
        
        promotion_match = re.search(r'(-?\d+%[^()]*)', full_text)
        promotion = promotion_match.group(1).strip() if promotion_match else "N/A"
        
        return {
            "category_name": name,
            "category_url": url,
            "image": image,
            "delivery_fee": delivery_fee,
            "delivery_time": delivery_time,
            "rating": rating,
            "number_of_reviews": reviews,
            "promotion": promotion
        }
        
    except Exception as e:
        print(f"Erreur lors de l'extraction des informations de catégorie: {e}")
        return {
            "category_name": "N/A",
            "category_url": "N/A",
            "image": "N/A",
            "delivery_fee": "N/A",
            "delivery_time": "N/A",
            "rating": "N/A",
            "number_of_reviews": "N/A",
            "promotion": "N/A"
        }

async def scrape_products(context, url, cat_type):
    """Scraper les produits d'une catégorie en deux phases pour les supermarchés"""
    # Vérifier que l'URL est valide
    if not url or url == "N/A" or "glovoapp.com" not in url:
        print(f"URL invalide pour les produits: {url}")
        return []
    
    # Ouvrir une nouvelle page pour les produits
    page = await context.new_page()
    products_data = []
    
    try:
        print(f"Navigation vers: {url}")
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        
        # Accepter les cookies si nécessaire
        await accept_cookies(page)
        
        # Attendre que le contenu se charge
        await page.wait_for_timeout(5000)
        
        # Faire défiler la page pour charger tout le contenu
        await scroll_page(page)
        
        # PHASE 1: Scraper les produits sans cliquer sur le bouton promo
        print("Phase 1: Scraping des produits sans promotion")
        products_phase1 = await scrape_products_improved(page, cat_type)
        products_data.extend(products_phase1)
        print(f"Phase 1: {len(products_phase1)} produits trouvés")
        
        # PHASE 2: Pour les supermarchés, cliquer sur le bouton promo et scraper à nouveau
        if cat_type == "supermarches":
            print("Phase 2: Recherche du bouton promo pour les supermarchés")
            
            # Vérifier s'il y a un bouton "Voir tous les produits en promo" ou similaire
            view_all_promo_selectors = [
                'button:has-text("promo")',
                'button:has-text("Promo")',
                'button:has-text("promotions")',
                'button:has-text("Promotions")',
                'a:has-text("promo")',
                'a:has-text("Promo")',
                'a:has-text("promotions")',
                'a:has-text("Promotions")',
                '[data-test-id*="promo"]',
                '[class*="promo"]'
            ]
            
            promo_button_found = False
            for selector in view_all_promo_selectors:
                try:
                    promo_button = await page.query_selector(selector)
                    if promo_button and await promo_button.is_visible():
                        print(f"Trouvé un bouton promo: {selector}")
                        await promo_button.click()
                        await page.wait_for_timeout(3000)
                        
                        # Attendre que les produits se chargent
                        await page.wait_for_timeout(2000)
                        
                        # Faire défiler à nouveau pour charger les nouveaux produits
                        await scroll_page(page)
                        
                        # Scraper les produits après avoir cliqué sur le bouton promo
                        products_phase2 = await scrape_products_improved(page, cat_type)
                        print(f"Phase 2: {len(products_phase2)} produits promotionnels trouvés")
                        
                        # Ajouter les nouveaux produits (éviter les doublons)
                        for product in products_phase2:
                            product_id = f"{product.get('product_name', '').lower()}_{product.get('product_price', '').lower()}"
                            existing_ids = {f"{p.get('product_name', '').lower()}_{p.get('product_price', '').lower()}" for p in products_data}
                            
                            if product_id not in existing_ids:
                                products_data.append(product)
                        
                        promo_button_found = True
                        break
                except Exception as e:
                    print(f"Erreur avec le sélecteur promo {selector}: {e}")
                    continue
            
            if not promo_button_found:
                print("Aucun bouton promo trouvé pour les supermarchés")
        
        # Pour les boutiques, garder tous les produits (pas seulement les promos)
        elif cat_type == "boutiques":
            print("Pour les boutiques, on garde tous les produits")
            # Rien à faire de spécial, on garde tous les produits scrapés
        
    except Exception as e:
        print(f"Impossible d'accéder à la page des produits {url}: {e}")
    
    finally:
        await page.close()
    
    # Déduplication finale
    products_data = remove_duplicate_products(products_data)
    print(f"Total produits après déduplication: {len(products_data)}")
    
    return products_data

async def scrape_products_improved(page, cat_type):
    """Nouvelle méthode améliorée pour scraper les produits"""
    products_data = []
    
    try:
        # Trouver toutes les sections de produits
        section_selectors = [
            '.collection__children',
            '.category-section',
            '.menu-section',
            '.product-section',
            'section',
            '[data-test-id*="section"]',
            '[class*="section"]',
            '.list',
            '.contenter'
        ]
        
        sections = []
        for selector in section_selectors:
            try:
                found_sections = await page.query_selector_all(selector)
                if found_sections:
                    sections.extend(found_sections)
            except Exception as e:
                continue
        
        # Filtrer les sections pour ne garder que celles qui contiennent probablement des produits
        filtered_sections = []
        for section in sections:
            try:
                # Vérifier si la section contient des produits
                has_products = await section.query_selector('[data-test-id="product-cell"], .product-item, .item-card')
                if has_products:
                    filtered_sections.append(section)
                else:
                    # Vérifier si la section a un nom significatif
                    section_name = await extract_section_name(section)
                    if section_name != "N/A" and section_name not in ["Frequently asked questions", "Top categories: Tunisia"]:
                        filtered_sections.append(section)
            except:
                continue
        
        if not filtered_sections:
            # Essayer de trouver des conteneurs de produits directement
            product_containers = await page.query_selector_all('.store__body__dynamic_content, [data-test-id="store-content"], .list.contenter')
            filtered_sections = product_containers
        
        if not filtered_sections:
            # Si aucune section n'est trouvée, utiliser le body comme section unique
            filtered_sections = [await page.query_selector('body')]
        
        print(f"Trouvé {len(filtered_sections)} sections de produits après filtrage")
        
        for section in filtered_sections:
            try:
                # Extraire le nom de la section
                section_name = await extract_section_name(section)
                print(f"Scraping de la section: {section_name}")
                
                # Scraper les produits dans cette section
                section_products = await scrape_products_in_section_improved(section, cat_type)
                
                # Ajouter les informations de section aux produits
                for product in section_products:
                    product["section"] = section_name
                    products_data.append(product)
                    
            except Exception as e:
                print(f"Erreur lors du scraping d'une section: {e}")
                continue
                
    except Exception as e:
        print(f"Erreur lors du scraping par sections: {e}")
        # Fallback: essayer l'ancienne méthode
        products_data = await scrape_products_fallback(page, cat_type)
    
    return products_data

async def extract_section_name(section):
    """Extraire le nom d'une section avec plus de précision"""
    try:
        section_name = "N/A"
        
        # Sélecteurs prioritaires pour les noms de section
        section_name_selectors = [
            'h1, h2, h3, h4, h5, h6',
            '[data-test-id*="title"]',
            '[class*="title"]',
            '[class*="name"]',
            '[class*="header"]',
            '.section-title',
            '.category-title',
            '.collection-header',
            '.menu-category-title'
        ]
        
        for selector in section_name_selectors:
            try:
                name_elements = await section.query_selector_all(selector)
                for name_elem in name_elements:
                    if name_elem:
                        name_text = await name_elem.text_content()
                        name_text = name_text.strip()
                        if (name_text != "N/A" and 
                            len(name_text) > 2 and 
                            not name_text.isdigit() and
                            not any(word in name_text.lower() for word in ["login", "follow", "careers", "faq", "contact"])):
                            section_name = name_text
                            break
                if section_name != "N/A":
                    break
            except:
                continue
        
        return section_name
    except Exception as e:
        print(f"Erreur lors de l'extraction du nom de section: {e}")
        return "N/A"

async def scrape_products_in_section_improved(section, cat_type):
    """Scraper les produits dans une section spécifique avec méthode améliorée"""
    products = []
    seen_product_ids = set()  # Pour éviter les doublons dans la même section
    
    try:
        # Sélecteurs spécifiques pour les produits
        product_selectors = [
            '[data-test-id="product-cell"]',
            '[data-test-id*="product"]',
            '.product-item',
            '.item-card',
            '.product-card',
            '.menu-item',
            '.card',
            '.item',
            '[class*="product"]',
            '[class*="item"]',
            '.list-item',
            '.contenter-item'
        ]
        
        product_elements = []
        for selector in product_selectors:
            try:
                found_products = await section.query_selector_all(selector)
                if found_products:
                    product_elements.extend(found_products)
            except Exception as e:
                continue
        
        # Filtrer les éléments pour ne garder que les vrais produits
        filtered_product_elements = []
        for element in product_elements:
            if await is_probably_product(element):
                filtered_product_elements.append(element)
        
        print(f"Trouvé {len(filtered_product_elements)} éléments de produit valides dans la section")
        
        for product_element in filtered_product_elements:
            try:
                # Extraire les informations du produit avec la méthode améliorée
                product_info = await extract_product_info_improved_v2(product_element)
                
                # Appliquer le filtre sur le nom du produit
                product_info["product_name"] = filter_product_name(
                    product_info["product_name"], 
                    product_info["description"]
                )
                
                # Créer un identifiant unique pour ce produit
                product_id = f"{product_info.get('product_name', '').lower()}_{product_info.get('product_price', '').lower()}"
                
                # Éviter les doublons dans la même section
                if product_id not in seen_product_ids:
                    seen_product_ids.add(product_id)
                    
                    # Pour les supermarchés et boutiques, garder TOUS les produits
                    if cat_type == "supermarches" or cat_type == "boutiques":
                        products.append(product_info)
                    else:
                        # Pour food, ne garder que les produits en promo
                        if product_info.get("promotion", "N/A") != "N/A":
                            products.append(product_info)
                else:
                    print(f"Produit en double ignoré dans la même section: {product_info.get('product_name', 'N/A')}")
                    
            except Exception as e:
                print(f"Erreur lors du scraping d'un produit: {e}")
                continue
                
    except Exception as e:
        print(f"Erreur lors du scraping des produits dans la section: {e}")
    
    return products

async def scrape_products_fallback(page, cat_type):
    """Méthode de fallback pour scraper les produits - version améliorée"""
    products_data = []
    seen_product_ids = set()  # Pour éviter les doublons
    
    try:
        print("Utilisation de la méthode fallback améliorée...")
        
        # Essayer plusieurs approches pour trouver les produits
        approaches = [
            # Approche 1: Chercher tous les éléments qui pourraient être des produits
            lambda: page.query_selector_all('div, article, section, li'),
            
            # Approche 2: Chercher par structure de données
            lambda: page.query_selector_all('[data-test-id], [class*="product"], [class*="item"], [class*="card"]'),
            
            # Approche 3: Chercher par présence de prix
            lambda: page.query_selector_all('*:has-text("[0-9][0-9.,]*[\\s]*[DT€£$]")')
        ]
        
        all_elements = []
        for i, approach in enumerate(approaches):
            try:
                elements = await approach()
                all_elements.extend(elements)
            except Exception as e:
                continue
        
        # Filtrer les doublons
        unique_elements = []
        seen_ids = set()
        for element in all_elements:
            try:
                element_id = await element.get_attribute('id') or await element.get_attribute('data-test-id') or str(await element.text_content())[:50]
                if element_id not in seen_ids:
                    seen_ids.add(element_id)
                    unique_elements.append(element)
            except:
                continue
        
        # Filtrer pour ne garder que les produits probables
        product_elements = [el for el in unique_elements if await is_probably_product(el)]
        print(f"Trouvé {len(product_elements)} produits probables après filtrage")
        
        for product_element in product_elements:
            try:
                # Extraire les informations du produit
                product_info = await extract_product_info_improved_v2(product_element)
                
                # Appliquer le filtre sur le nom du produit
                product_info["product_name"] = filter_product_name(
                    product_info["product_name"], 
                    product_info["description"]
                )
                
                # Créer un identifiant unique pour ce produit
                product_id = f"{product_info.get('product_name', '').lower()}_{product_info.get('product_price', '').lower()}"
                
                # Éviter les doublons
                if product_id not in seen_product_ids:
                    seen_product_ids.add(product_id)
                    
                    # Pour les supermarchés et boutiques, garder TOUS les produits
                    if cat_type == "supermarches" or cat_type == "boutiques":
                        products_data.append(product_info)
                    else:
                        # Pour food, ne garder que les produits en promo
                        if product_info.get("promotion", "N/A") != "N/A":
                            products_data.append(product_info)
                else:
                    print(f"Produit en double ignoré (fallback): {product_info.get('product_name', 'N/A')}")
                    
            except Exception as e:
                print(f"Erreur lors du scraping d'un produit (fallback): {e}")
                continue
                
    except Exception as e:
        print(f"Erreur lors de la méthode fallback: {e}")
    
    return products_data

async def is_probably_product(element):
    """Déterminer si un élément est probablement un produit avec plus de précision"""
    try:
        # Vérifier si l'élément est visible
        if not await element.is_visible():
            return False
        
        # Vérifier la taille et le contenu
        bounding_box = await element.bounding_box()
        if not bounding_box or bounding_box['height'] < 30 or bounding_box['width'] < 30:
            return False
        
        # Vérifier le contenu texte
        text = await element.text_content()
        if not text or len(text.strip()) < 3:
            return False
        
        # Éviter les éléments qui sont probablement des boutons ou des en-têtes
        if any(word in text.lower() for word in ["login", "sign", "follow", "career", "faq", "contact", "terms", "policy"]):
            return False
        
        # Vérifier si cela contient des éléments communs aux produits
        has_image = await element.query_selector('img')
        has_price = bool(re.search(r'(\d+[\.,]?\d*\s*[DT|€|£|$])', text))
        has_name = bool(re.search(r'[a-zA-Z]{3,}', text))  # Au moins 3 lettres
        
        # Un produit doit avoir au moins un prix OU un nom significatif avec une image
        return (has_price and has_name) or (has_image and has_name)
    except:
        return False

async def extract_product_info_improved_v2(product):
    """Nouvelle version améliorée pour extraire les informations d'un produit"""
    try:
        # Obtenir tout le texte du produit
        full_text = await product.text_content()
        full_text = re.sub(r'\s+', ' ', full_text).strip()
        
        # Extraire le nom du produit - méthode améliorée
        name = await extract_product_name(product, full_text)
        
        # Nettoyer le nom du produit pour éviter les variations
        name = clean_product_name(name)
        
        # Extraire les prix avec méthode améliorée
        price_data = await extract_product_prices(product, full_text)
        
        # Image du produit
        image = await extract_product_image(product)
        
        # Promotion
        promotion = await extract_product_promotion(product, full_text)
        
        # Description du produit
        description = await extract_product_description(product, full_text, name)
        
        return {
            "product_name": name,
            "product_price": price_data.get("current_price", "N/A"),
            "original_price": price_data.get("original_price", "N/A"),
            "product_image": image,
            "promotion": promotion,
            "description": description
        }
        
    except Exception as e:
        print(f"Erreur lors de l'extraction des informations du produit: {e}")
        return {
            "product_name": "N/A",
            "product_price": "N/A",
            "original_price": "N/A",
            "product_image": "N/A",
            "promotion": "N/A",
            "description": "N/A"
        }

async def extract_product_name(product, full_text):
    """Extraire le nom du produit"""
    name = "N/A"
    name_selectors = [
        '[data-test-id="product-name"]',
        '.product-name',
        '.item-name',
        'h1, h2, h3, h4, h5, h6',
        '[class*="name"]',
        '[class*="title"]',
        '[class*="description"]:first-child'
    ]
    
    for selector in name_selectors:
        try:
            name_elem = await product.query_selector(selector)
            if name_elem:
                name = await name_elem.text_content()
                name = name.strip()
                if name != "N/A" and name not in ["x", "-", "x -"] and len(name) > 2:
                    return name
        except:
            continue
    
    # Si le nom n'est pas trouvé avec les sélecteurs, utiliser une regex
    if name == "N/A" or name in ["x", "-", "x -"] or len(name) <= 2:
        # Essayer d'extraire le texte avant le premier prix
        name_match = re.search(r'^([^\d€£$DT]+?)(?=\d)', full_text)
        if name_match:
            name = name_match.group(1).strip()
            # Nettoyer le nom
            name = re.sub(r'^[x\s\-]+', '', name).strip()
    
    # Si le nom est toujours invalide, essayer une autre approche
    if name in ["x", "-", "x -", "N/A"] or len(name) <= 2:
        # Chercher le premier texte significatif
        text_parts = full_text.split()
        for part in text_parts:
            if (len(part) > 2 and 
                not part.isdigit() and 
                not re.match(r'[\d\.,]+[DT€£$]', part) and
                part not in ["x", "-", "x -"]):
                name = part
                break
    
    return name

async def extract_product_prices(product, full_text):
    """Extraire les prix du produit avec méthode améliorée"""
    price = "N/A"
    promo_price = "N/A"
    original_price = "N/A"
    
    # Sélecteurs pour les prix
    price_selectors = [
        '[data-test-id="product-price"]',
        '.product-price',
        '.item-price',
        '.price',
        '[class*="price"]',
        '.current-price',
        '.final-price',
        '.original-price',
        '.old-price'
    ]
    
    # Chercher tous les éléments de prix
    price_elements = []
    for selector in price_selectors:
        try:
            elements = await product.query_selector_all(selector)
            price_elements.extend(elements)
        except:
            continue
    
    # Extraire les prix des éléments trouvés
    prices_found = []
    for price_elem in price_elements:
        try:
            price_text = await price_elem.text_content()
            price_match = re.search(r'(\d+[\.,]?\d*\s*[DT|€|£|$])', price_text)
            if price_match:
                prices_found.append(price_match.group(1))
        except:
            continue
    
    # Analyser les prix trouvés
    if len(prices_found) >= 2:
        # Si on a deux prix ou plus, le plus bas est généralement le prix promo
        try:
            # Convertir en nombres pour comparaison
            def parse_price(p):
                return float(re.sub(r'[^\d.,]', '', p).replace(',', '.'))
            
            prices_numeric = [parse_price(p) for p in prices_found]
            min_price = min(prices_numeric)
            max_price = max(prices_numeric)
            
            promo_price = prices_found[prices_numeric.index(min_price)]
            original_price = prices_found[prices_numeric.index(max_price)]
            price = promo_price
        except:
            # Fallback: prendre le premier prix comme prix actuel
            price = prices_found[0]
            if len(prices_found) > 1:
                original_price = prices_found[1]
    elif len(prices_found) == 1:
        price = prices_found[0]
    
    # Si les prix n'ont pas été trouvés avec les sélecteurs, utiliser une regex sur le texte complet
    if price == "N/A":
        price_match = re.search(r'(\d+[\.,]?\d*\s*[DT|€|£|$])', full_text)
        if price_match:
            price = price_match.group(1)
    
    # Chercher un prix barré pour le prix original
    if original_price == "N/A":
        # Chercher des éléments avec style de texte barré
        strikethrough_selectors = [
            's',
            'strike',
            'del',
            '[style*="line-through"]',
            '[class*="strike"]',
            '[class*="old"]'
        ]
        
        for selector in strikethrough_selectors:
            try:
                strike_elems = await product.query_selector_all(selector)
                for elem in strike_elems:
                    strike_text = await elem.text_content()
                    price_match = re.search(r'(\d+[\.,]?\d*\s*[DT|€|£|$])', strike_text)
                    if price_match:
                        original_price = price_match.group(1)
                        break
                if original_price != "N/A":
                    break
            except:
                continue
    
    # Si on n'a pas trouvé de prix original avec les sélecteurs, chercher dans le texte complet
    if original_price == "N/A":
        # Chercher un pattern avec deux prix
        two_prices_match = re.search(r'(\d+[\.,]?\d*\s*[DT|€|£|$])\s*(\d+[\.,]?\d*\s*[DT|€|£|$])', full_text)
        if two_prices_match:
            price1 = two_prices_match.group(1)
            price2 = two_prices_match.group(2)
            
            # Déterminer quel prix est le prix original (généralement le plus élevé)
            try:
                def parse_price(p):
                    return float(re.sub(r'[^\d.,]', '', p).replace(',', '.'))
                
                price1_num = parse_price(price1)
                price2_num = parse_price(price2)
                
                if price1_num > price2_num:
                    original_price = price1
                    price = price2
                else:
                    original_price = price2
                    price = price1
            except:
                # Si la conversion échoue, prendre le premier prix comme prix actuel
                price = price1
                original_price = price2
    
    return {
        "current_price": price,
        "original_price": original_price,
        "promo_price": promo_price
    }

async def extract_product_image(product):
    """Extraire l'image du produit"""
    image = "N/A"
    img_selectors = [
        'img[src*="product"]',
        'img[src*="item"]',
        'img:not([src*="svg"])',
        'img:not([src*="minus"])',
        'img:not([src*="plus"])',
        '[class*="image"]',
        'img[src]'
    ]
    
    for selector in img_selectors:
        try:
            img_elem = await product.query_selector(selector)
            if img_elem:
                image = await img_elem.get_attribute('src')
                if image and not image.startswith('http'):
                    image = urljoin("https://glovoapp.com", image)
                # Éviter les images de boutons
                if (image != "N/A" and "svg" not in image and 
                    "minus" not in image and "plus" not in image and
                    "icon" not in image.lower()):
                    return image
        except:
            continue
    
    return image

async def extract_product_promotion(product, full_text):
    """Extraire la promotion du produit"""
    promotion = "N/A"
    promotion_selectors = [
        '[data-test-id="product-promotion"]',
        '.promotion',
        '.discount',
        '[class*="promo"]',
        '[class*="discount"]',
        '.discount-badge',
        '.promo-badge'
    ]
    
    for selector in promotion_selectors:
        try:
            promo_elem = await product.query_selector(selector)
            if promo_elem:
                promotion = await promo_elem.text_content()
                promotion = promotion.strip()
                if promotion != "N/A":
                    return promotion
        except:
            continue
    
    # Si la promotion n'est pas trouvée avec les sélecteurs, utiliser une regex
    if promotion == "N/A":
        # Chercher un pourcentage de réduction
        discount_match = re.search(r'(-?\d+)%', full_text)
        if discount_match:
            discount_value = discount_match.group(1)
            if discount_value != "100":  # Éviter les faux positifs
                promotion = f"-{discount_value}%"
        else:
            # Chercher d'autres motifs de promotion
            promotion_match = re.search(r'(promo|offre|réduction|discount|rabais|sale)', full_text, re.IGNORECASE)
            if promotion_match:
                promotion = "Promotion"
    
    return promotion

async def extract_product_description(product, full_text, product_name):
    """Extraire la description du produit"""
    description = "N/A"
    desc_selectors = [
        '[data-test-id="product-description"]',
        '.product-description',
        '.item-description',
        '[class*="description"]',
        '.product-details'
    ]
    
    for selector in desc_selectors:
        try:
            desc_elem = await product.query_selector(selector)
            if desc_elem:
                description = await desc_elem.text_content()
                description = description.strip()
                if description != "N/A" and description != product_name:
                    return description
        except:
            continue
    
    # Si la description n'est pas trouvée, essayer d'extraire le texte après le nom
    if description == "N/A" and product_name != "N/A":
        # Supprimer le nom et les prix du texte complet pour trouver la description
        description_text = full_text.replace(product_name, "").strip()
        price_pattern = r'\d+[\.,]?\d*\s*[DT|€|£|$]'
        description_text = re.sub(price_pattern, "", description_text).strip()
        description_text = re.sub(r'[-]?\d+%', "", description_text).strip()
        
        if description_text and len(description_text) > 5:
            description = description_text
    
    return description

if __name__ == "__main__":
    asyncio.run(scrape_glovo())