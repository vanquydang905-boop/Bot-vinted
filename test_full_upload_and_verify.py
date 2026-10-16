from playwright.sync_api import sync_playwright
import os, time

IMAGE_BASE_DIR = "/root/shein/image"
sku = "111432963"
screen_dir = os.path.join(IMAGE_BASE_DIR, sku, "image-screen")
photos = sorted([os.path.join(screen_dir, f) for f in os.listdir(screen_dir) if f.startswith("photo_") and f.endswith(".jpg")])

print(f"Testing full upload for SKU {sku} with {len(photos)} photos...")

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp("http://127.0.0.1:44231")
    context = browser.contexts[0]
    pages = [pg for pg in context.pages if "gemini.google.com" in pg.url]
    page = pages[0]
    page.bring_to_front()
    
    # 1. Reset chat
    print("1. Clicking Nouvelle discussion...")
    new_chat = page.locator("a[href='https://gemini.google.com/app'], button[aria-label*='Nouvelle discussion']").first
    if new_chat.is_visible():
        new_chat.click()
        page.wait_for_timeout(2000)

    # 2. Open popover menu
    print("2. Clicking Importation et outils button...")
    plus_btn = page.locator("button[aria-label*='Importation et outils']").first
    plus_btn.click()
    page.wait_for_timeout(800)

    # 3. Intercept file chooser on menu item click
    print("3. Clicking Importer des fichiers and intercepting file chooser...")
    with page.expect_file_chooser(timeout=5000) as fc_info:
        upload_item = page.locator("[aria-label*='Importer des fichiers']").first
        upload_item.click()

    file_chooser = fc_info.value
    print(f"4. File chooser intercepted! Setting {len(photos)} files...")
    file_chooser.set_files(photos)
    
    print("5. Waiting 5 seconds for Gemini to upload & display image thumbnails...")
    page.wait_for_timeout(5000)
    
    # Take screenshot of attached thumbnails in prompt box
    page.screenshot(path="/root/shein/verify_full_upload.png")
    print("Screenshot saved to /root/shein/verify_full_upload.png!")
