import asyncio
import json
import os
import random
import re
import time
from datetime import datetime
from typing import Dict, Any, Optional, List
from urllib.parse import quote, urlparse
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama import OllamaLLM

# Configuration
INPUT_FILE = "places.jsonl"
OUTPUT_FILE = "result.json"  # Changé de .jsonl à .json
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
MAX_TEXT_LENGTH = 2000  # Limite stricte pour le texte envoyé au LLM

# Modèle Ollama local
llm = OllamaLLM(model="llama2")  

# Prompts (inchangés)
EXTRACTION_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """Extrait les informations suivantes à partir du texte en français:
- Nom officiel
- Adresse complète
- Numéro de téléphone
- Site web
- Horaires d'ouverture
- Note Google (si disponible)
- Nombre d'avis

Retourne UNIQUEMENT un JSON valide:
{{
  "nom": "string",
  "adresse": "string",
  "telephone": "string",
  "site_web": "string",
  "horaires": "string",
  "note_google": float,
  "nombre_avis": int
}}

Texte brut filtré:
{text_content}""")
])

SUMMARY_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """Génère une brochure marketing concise (2-3 phrases) en français pour cet établissement:
{business_info}

Mets l'accent sur:
- Particularités uniques
- Ambiance
- Public cible
- Points forts

Sois persuasif et concis!""")
])

LINK_EXTRACTION_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are provided with a list of links found on a webpage. 
You are able to decide which of the links would be most relevant to include in a brochure about the company, 
such as links to social media, about page, or company pages.

SPECIFIC RULES FOR SOCIAL LINKS:
1. Facebook: Only keep main page links (facebook.com/PageName)
   - Remove: /videos/, /posts/, /photos/, /events/, /groups/
   - Remove: All parameters (?ref=, ?locale=, etc.)
   - Remove: www. prefix

2. Instagram: Only keep profile links (instagram.com/Username)
   - Remove: /p/, /reel/, /tv/, /stories/
   - Remove: All parameters (?hl=, ?utm=, etc.)
   - Remove: www. prefix

3. For other links: Keep important pages (about, contact, menu) but exclude:
   - Tracking links
   - Login pages
   - PDF/files
   - Generic pages (privacy policy, terms)

Return ONLY relevant links in this exact JSON format:
{{
    "links": [
        {{"type": "facebook", "url": "https://facebook.com/PageName"}},
        {{"type": "instagram", "url": "https://instagram.com/Username"}},
        {{"type": "website", "url": "https://company.com"}},
        {{"type": "other", "url": "https://company.com/about"}}
    ]
}}

BAD EXAMPLES TO AVOID:
- https://www.facebook.com/PageName/videos/123 → REJECT
- https://instagram.com/Username/reel/ABC → REJECT
- https://www.facebook.com/PageName?locale=fr_FR → REJECT
- https://m.facebook.com/PageName → REJECT (keep only desktop version)

GOOD EXAMPLES TO KEEP:
- https://facebook.com/PageName → KEEP
- https://instagram.com/Username → KEEP
- https://company.com/menu → KEEP

Links to analyze:
{links}""")
])

async def check_and_solve_captcha(page) -> bool:
    """Détecte et tente de résoudre les CAPTCHAs"""
    captcha_selectors = [
        "text=CAPTCHA", 
        "div#captcha", 
        "iframe[src*='captcha']",
        "text=Je ne suis pas un robot"
    ]
    
    for selector in captcha_selectors:
        if await page.locator(selector).count() > 0:
            print("🛑 CAPTCHA détecté! Résolution manuelle nécessaire...")
            start_time = time.time()
            while time.time() - start_time < 120:
                await asyncio.sleep(5)
                if await page.locator(selector).count() == 0:
                    print("✅ CAPTCHA résolu!")
                    return True
            print("⏱️ Temps écoulé pour le CAPTCHA")
            return False
    return False

async def extract_relevant_text_and_links(html: str) -> tuple[Optional[str], List[Dict[str, str]]]:
    """
    Extrait et filtre le texte pertinent et les liens depuis le HTML
    Retourne un tuple (texte, liens)
    """
    soup = BeautifulSoup(html, 'html.parser')
    
    # Supprimer les éléments inutiles
    for element in soup(['script', 'style', 'meta', 'link', 'noscript', 'img', 'svg', 'footer', 'header', 'nav']):
        element.decompose()
    
    # Extraire tous les liens pertinents
    all_links = []
    for link in soup.find_all('a', href=True):
        url = link['href'].strip()
        if not url or url.startswith('javascript:'):
            continue
        
        # Normaliser les URLs
        if url.startswith('/'):
            url = f"https://www.google.com{url}"
        
        # Filtrer les URLs de tracking et autres non pertinentes
        if any(x in url for x in ['/search?', 'google.com', 'support.google.com']):
            continue
            
        all_links.append({
            'url': url,
            'text': link.get_text(' ', strip=True)[:100]
        })
    
    # Extraire le texte pertinent
    text_parts = []
    
    # Priorité 1: Knowledge Panel de Google
    knowledge_panel = soup.find('div', {'class': re.compile(r'knowledge-panel|kno-rdesc')})
    if knowledge_panel:
        text_parts.append(knowledge_panel.get_text('\n', strip=True))
    
    # Priorité 2: Cartes d'entreprise
    business_cards = soup.find_all('div', {'class': re.compile(r'business-card|place-result')})
    if business_cards:
        text_parts.extend(card.get_text('\n', strip=True) for card in business_cards)
    
    # Priorité 3: Sections avec mots-clés pertinents
    keywords = ['adresse', 'téléphone', 'horaires', 'note', 'avis', 'contact', 'ouvert', 'fermé', 'heure']
    for element in soup.find_all(['div', 'section', 'article', 'span', 'li']):
        text = element.get_text(' ', strip=True)
        if len(text) > 20 and any(kw in text.lower() for kw in keywords):
            text_parts.append(text)
    
    # Combiner le texte
    filtered_text = '\n'.join(text_parts)[:MAX_TEXT_LENGTH] if text_parts else None
    
    return filtered_text, all_links

async def analyze_links(links: List[Dict[str, str]]) -> Dict[str, Any]:
    """Analyse les liens avec des règles strictes pour identifier les réseaux sociaux"""
    if not links:
        return {"links": []}
    
    social_links = []
    seen_urls = set()

    for link in links:
        url = link['url']
        lower_url = url.lower()
        
        # Facebook - Nettoyage approfondi
        if 'facebook.com' in lower_url:
            # Extraire le format de base de l'URL
            match = re.search(
                r'(https?://)(?:www\.|m\.)?(facebook\.com/[^/?]+)',
                url,
                re.IGNORECASE
            )
            if match:
                base_url = f"{match.group(1)}{match.group(2)}"
                
                # Vérifier que ce n'est pas une URL de contenu spécifique
                if not any(x in lower_url for x in [
                    '/videos/', '/posts/', '/photos/', '/events/', 
                    '/groups/', '/reel/', '/watch', '/story/', '/hashtag/'
                ]):
                    # Normaliser l'URL finale
                    clean_url = re.sub(
                        r'(https?://)(?:www\.)?(facebook\.com/[^/?]+).*',
                        r'\1\2',
                        url,
                        flags=re.IGNORECASE
                    )
                    if clean_url not in seen_urls:
                        seen_urls.add(clean_url)
                        social_links.append({
                            "type": "facebook",
                            "url": clean_url
                        })
        
        # Instagram - Nettoyage approfondi
        elif 'instagram.com' in lower_url:
            match = re.search(
                r'(https?://)(?:www\.)?(instagram\.com/[^/?]+)',
                url,
                re.IGNORECASE
            )
            if match:
                base_url = f"{match.group(1)}{match.group(2)}"
                
                if not any(x in lower_url for x in [
                    '/p/', '/reel/', '/tv/', '/stories/', '/story/'
                ]):
                    # Normaliser l'URL finale
                    clean_url = re.sub(
                        r'(https?://)(?:www\.)?(instagram\.com/[^/?]+).*',
                        r'\1\2',
                        url,
                        flags=re.IGNORECASE
                    )
                    if clean_url not in seen_urls:
                        seen_urls.add(clean_url)
                        social_links.append({
                            "type": "instagram",
                            "url": clean_url
                        })
    
    # Dédoublonnage final au cas où
    unique_links = []
    seen = set()
    for link in social_links:
        if link['url'] not in seen:
            seen.add(link['url'])
            unique_links.append(link)
    
    return {"links": unique_links}
async def scrape_google_page(page, place_name: str, location: str) -> tuple[Optional[str], List[Dict[str, str]]]:
    """Scrape la page Google et retourne le texte brut et les liens pertinents"""
    query = f"{place_name} {location}"
    url = f"https://www.google.com/search?q={quote(query)}"
    
    try:
        await page.goto(url, timeout=30000)
        
        # Vérifier les CAPTCHAs
        if await check_and_solve_captcha(page):
            print("CAPTCHA résolu, poursuite du scraping...")
        elif await page.locator("div#captcha").count() > 0:
            print("CAPTCHA non résolu, abandon...")
            return None, []
        
        # Attendre les résultats
        try:
            await page.wait_for_selector("div#search", timeout=10000)
        except Exception as e:
            print(f"Timeout sur les résultats: {str(e)}")
            return None, []
        
        # Scroller pour charger tout le contenu
        await page.evaluate("""async () => {
            await new Promise(resolve => {
                let scrolled = 0;
                const scrollStep = 200;
                const scrollInterval = setInterval(() => {
                    window.scrollBy(0, scrollStep);
                    scrolled += scrollStep;
                    if (scrolled >= document.body.scrollHeight || scrolled > 5000) {
                        clearInterval(scrollInterval);
                        resolve();
                    }
                }, 100);
            });
        }""")
        
        # Récupérer le HTML et extraire IMMÉDIATEMENT le texte et les liens
        html = await page.content()
        filtered_text, links = await extract_relevant_text_and_links(html)
        
        if not filtered_text:
            print("Aucun texte pertinent trouvé dans la page")
            return None, []
            
        print(f"Texte extrait: {len(filtered_text)} caractères, {len(links)} liens trouvés")
        return filtered_text, links
        
    except Exception as e:
        print(f"Erreur scraping: {str(e)}")
        return None, []

async def process_entry(browser, entry: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Traite une entrée complète avec scraping et LLM"""
    context = await browser.new_context(
        user_agent=USER_AGENT,
        viewport={'width': 1280, 'height': 1024}
    )
    page = await context.new_page()
    
    try:
        # Étape 1: Scraping pour obtenir texte et liens
        filtered_text, raw_links = await scrape_google_page(
            page,
            entry["place_name"],
            f"{entry['municipalite']}, {entry['gouvernorat']}"
        )
        
        if not filtered_text:
            print(f"❌ Aucun contenu pertinent pour {entry['place_name']}")
            return None
        
        # Étape 2: Extraction des informations avec LLM
        extraction_chain = EXTRACTION_PROMPT | llm
        extraction_response = await extraction_chain.ainvoke({"text_content": filtered_text})
        
        try:
            # Extraction du JSON depuis la réponse
            json_match = re.search(r'\{[\s\S]*\}', extraction_response.strip())
            if not json_match:
                print("⚠️ Aucun JSON trouvé dans la réponse du LLM")
                return None
                
            business_info = json.loads(json_match.group())
            print(f"✅ Données extraites pour {business_info.get('nom', 'inconnu')}")
        except json.JSONDecodeError as e:
            print(f"❌ Erreur de décodage JSON: {str(e)}")
            return None
        
        # Étape 3: Analyse des liens
        link_analysis = await analyze_links(raw_links)
        print(f"🔗 Liens trouvés: {len(link_analysis.get('links', []))}")
        
        # Étape 4: Génération de la brochure
        summary_chain = SUMMARY_PROMPT | llm
        summary = await summary_chain.ainvoke({
            "business_info": json.dumps(business_info, ensure_ascii=False)
        })
        
        return {
            **entry,
            **business_info,
            **link_analysis,
            "brochure": summary.strip(),
            "timestamp": datetime.now().isoformat(),
            "text_length": len(filtered_text),
            "raw_links_count": len(raw_links)
        }
        
    finally:
        await context.close()

async def main():
    """Fonction principale"""
    # Vérifier le fichier d'entrée
    if not os.path.exists(INPUT_FILE):
        print(f"❌ Fichier {INPUT_FILE} introuvable!")
        return
    
    # Lire les entrées
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        entries = [json.loads(line) for line in f if line.strip()]
    
    print(f"📄 {len(entries)} entrées à traiter")
    
    # Démarrer Playwright
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            channel="chrome"
        )
        
        # Liste pour stocker tous les résultats
        all_results = []
        
        # Traitement des entrées
        for i, entry in enumerate(entries, 1):
            print(f"\n🔍 [{i}/{len(entries)}] Traitement: {entry['place_name']}")
            
            result = await process_entry(browser, entry)
            
            if result:
                all_results.append(result)
                print(f"✅ Succès: {result.get('nom', 'N/A')}")
            else:
                print("❌ Échec du traitement")
            
            # Délai aléatoire entre les requêtes
            delay = random.uniform(3, 10)
            print(f"⏳ Attente de {delay:.1f} secondes...")
            await asyncio.sleep(delay)
        
        # Écrire tous les résultats dans un seul fichier JSON
        if all_results:
            with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
                json.dump(all_results, f, ensure_ascii=False, indent=2)
            print(f"\n🎉 {len(all_results)} résultats enregistrés dans {OUTPUT_FILE}")
        else:
            print("\n⚠️ Aucun résultat à enregistrer")
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())