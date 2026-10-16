from playwright.sync_api import sync_playwright
import json

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp("http://127.0.0.1:44231")
    context = browser.contexts[0]
    pages = [pg for pg in context.pages if "gemini.google.com" in pg.url]
    page = pages[0]
    page.bring_to_front()
    
    print("Gemini Page URL:", page.url)
    
    # 1. Click Plus (+) button
    plus_btn = page.locator("button[aria-label*='Importation'], button[aria-label*='Plus'], button[aria-label*='Tải'], button[aria-label*='tệp'], button.uploader-button, button:has(mat-icon)").first
    if plus_btn.is_visible():
        print("Clicking plus button...")
        plus_btn.click()
        page.wait_for_timeout(1500)
    
    # 2. Dump all visible interactive elements after clicking Plus
    elements = page.locator("button, [role='menuitem'], mat-nested-tree-node, div[role='button'], span").all()
    print(f"Found {len(elements)} elements. Filtering visible items with text...")
    for idx, el in enumerate(elements):
        try:
            if el.is_visible():
                txt = el.inner_text().strip().replace("\n", " ")
                if txt and len(txt) < 60:
                    aria = el.get_attribute("aria-label") or ""
                    tag = el.evaluate("e => e.tagName")
                    print(f"  [{idx}] Tag={tag} | Aria='{aria}' | Text='{txt}'")
        except Exception:
            pass
