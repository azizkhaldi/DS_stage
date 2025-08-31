import asyncio
from playwright.async_api import async_playwright

async def scrape_instagram_header(ig_url):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            viewport={"width": 1366, "height": 768}
        )
        page = await context.new_page()

        await page.goto(ig_url, timeout=60000)
        await page.wait_for_selector("header", timeout=10000)

        # Récupérer tout le texte de l'en-tête du profil
        header_text = await page.evaluate('''() => {
            const header = document.querySelector('header');
            return header ? header.innerText : '';
        }''')

        print("✅ Texte du header extrait :")
        print(header_text)

        await context.close()
        await browser.close()
        return header_text

if __name__ == "__main__":
    test_url = "https://www.instagram.com/redcastleresto/"
    asyncio.run(scrape_instagram_header(test_url))
