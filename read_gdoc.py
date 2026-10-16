import asyncio
from playwright.async_api import async_playwright

async def main():
    url = "https://docs.google.com/document/d/1sSU_ayA86hPKvDtF5Kc9L6Dter8rzjp_IVZECrSjdjE/edit?tab=t.220ek8qxgidn"
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://127.0.0.1:44231")
        # Find or create a page
        context = browser.contexts[0]
        page = await context.new_page()
        print(f"Navigating to {url}...")
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=20000)
        except Exception as e:
            print("Goto exception (continuing anyway):", e)
        await asyncio.sleep(4)
        
        # Try to extract text
        # Google Docs renders in .kix-page or canvas or .kix-paragraphrenderer
        # Also innerText of document.body
        title = await page.title()
        print("Page Title:", title)
        
        # Take screenshot of page to see document tabs
        await page.screenshot(path="/root/shein/gdoc_screenshot.png")
        print("Screenshot saved to /root/shein/gdoc_screenshot.png")
        
        # Extract all text elements in the document
        dom_text = await page.evaluate("""() => {
            return {
                title: document.title,
                bodyText: document.body.innerText.substring(0, 3000)
            };
        }""")
        print("DOM Text:", dom_text)
        await page.close()

if __name__ == "__main__":
    asyncio.run(main())
