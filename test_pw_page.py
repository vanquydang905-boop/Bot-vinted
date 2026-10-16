from playwright.sync_api import sync_playwright
import requests
import time

r = requests.put("http://127.0.0.1:44231/json/new?url=https://example.com").json()
ws_url = r["webSocketDebuggerUrl"]

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp(ws_url)
    context = browser.contexts[0]
    
    # Attendre que la page apparaisse
    for _ in range(10):
        if context.pages:
            break
        time.sleep(0.5)
        
    print("Pages:", context.pages)
    if context.pages:
        page = context.pages[0]
        print("Page URL:", page.url)
