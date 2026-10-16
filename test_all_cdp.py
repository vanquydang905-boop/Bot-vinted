import asyncio
from playwright.sync_api import sync_playwright

ports = [44775, 42677, 38049, 43983, 44231]

with sync_playwright() as p:
    for port in ports:
        print(f"\nTesting connection to port {port}...")
        try:
            browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{port}", timeout=10000)
            ctx = browser.contexts[0]
            gemini_pages = [pg for pg in ctx.pages if "gemini.google.com" in pg.url]
            print(f"Port {port}: SUCCESS! Context pages: {len(ctx.pages)}, Gemini pages: {len(gemini_pages)}")
            if gemini_pages:
                print(f"  Gemini Title: {gemini_pages[0].title()} | URL: {gemini_pages[0].url[:60]}")
            browser.close()
        except Exception as e:
            print(f"Port {port}: FAILED ({e})")
