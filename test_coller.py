from playwright.sync_api import sync_playwright
import os, base64, time, json

IMAGE_BASE_DIR = "/root/shein/image"
sku = "sz2403276962416149"
screen_dir = os.path.join(IMAGE_BASE_DIR, sku, "image-screen")
photos = sorted([os.path.join(screen_dir, f) for f in os.listdir(screen_dir) if f.startswith("photo_") and f.endswith(".jpg")])

fichiers = []
for chemin in photos[:3]:
    with open(chemin, "rb") as f:
        fichiers.append({
            "nom": os.path.basename(chemin),
            "data": base64.b64encode(f.read()).decode(),
            "type": "image/jpeg"
        })

JS_COLLER = """
([fichiers]) => {
  const dt = new DataTransfer();
  for (const f of fichiers) {
    const bin = atob(f.data);
    const octets = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) octets[i] = bin.charCodeAt(i);
    dt.items.add(new File([octets], f.nom, { type: f.type || 'image/jpeg' }));
  }
  const zone = document.querySelector('rich-textarea div[contenteditable="true"]')
            || document.querySelector('div[contenteditable="true"]');
  if (!zone) return "Zone introuvable";
  zone.focus();
  zone.dispatchEvent(new ClipboardEvent('paste',
      { clipboardData: dt, bubbles: true, cancelable: true }));
  return "Paste event dispatched successfully!";
}
"""

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp("http://127.0.0.1:44231")
    context = browser.contexts[0]
    pages = [pg for pg in context.pages if "gemini.google.com" in pg.url]
    page = pages[0]
    page.bring_to_front()
    
    print("Navigating to Gemini...")
    page.goto("https://gemini.google.com/app")
    page.wait_for_timeout(3000)
    
    print(f"Executing JS_COLLER for {len(fichiers)} photos...")
    res = page.evaluate(JS_COLLER, [fichiers])
    print("JS_COLLER result:", res)
    
    page.wait_for_timeout(5000)
    page.screenshot(path="/root/shein/coller_test_screenshot.png")
    print("Screenshot saved to /root/shein/coller_test_screenshot.png!")
