from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp("http://127.0.0.1:44231")
    context = browser.contexts[0]
    pages = [pg for pg in context.pages if "gemini.google.com" in pg.url]
    page = pages[0]
    page.bring_to_front()
    
    btn = page.locator("button[aria-label='Importation et outils']").first
    print("Clicking 'Importation et outils' button...")
    btn.click()
    page.wait_for_timeout(1000)
    
    items = page.locator("button, [role='menuitem'], mat-menu-item, div[role='button']").all()
    print(f"Scanning {len(items)} menu items:")
    for idx, item in enumerate(items):
        try:
            if item.is_visible():
                txt = item.inner_text().strip().replace("\n", " ")
                aria = item.get_attribute("aria-label") or ""
                print(f"  [{idx}] Aria='{aria}' | Text='{txt}'")
        except Exception:
            pass
