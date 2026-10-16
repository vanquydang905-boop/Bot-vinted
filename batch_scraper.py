import re
import sys
import os
import time
import urllib.request
import csv
import io
import telegram_notifier
from playwright.sync_api import sync_playwright

DEFAULT_SHEET_URL = "https://docs.google.com/spreadsheets/d/1kCi9BodydXGye1RNy-YZX9C4jWERTKnnMVFHZclNJ4A/edit"
DEFAULT_CSV_URL = "https://docs.google.com/spreadsheets/d/1kCi9BodydXGye1RNy-YZX9C4jWERTKnnMVFHZclNJ4A/export?format=csv&gid=0"

if len(sys.argv) >= 2 and sys.argv[1].isdigit():
    port = sys.argv[1]
    sheet_input_url = sys.argv[2] if len(sys.argv) >= 3 else DEFAULT_SHEET_URL
else:
    port = "44231"
    sheet_input_url = sys.argv[1] if len(sys.argv) >= 2 else DEFAULT_SHEET_URL

print(f"Utilisation du port CDP : {port}")

# Conversion de l'URL Google Sheets en lien CSV
if "docs.google.com/spreadsheets" in sheet_input_url and "export?format=csv" not in sheet_input_url:
    match_gid = re.search(r"gid=(\d+)", sheet_input_url)
    gid = match_gid.group(1) if match_gid else "0"
    match_doc = re.search(r"/d/([a-zA-Z0-9_-]+)", sheet_input_url)
    doc_id = match_doc.group(1) if match_doc else ""
    csv_url = f"https://docs.google.com/spreadsheets/d/{doc_id}/export?format=csv&gid={gid}"
else:
    csv_url = sheet_input_url

print(f"Extraction de la liste des SKU depuis Google Sheets...")
headers_http = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

skus_with_rows = []
try:
    req = urllib.request.Request(csv_url, headers=headers_http)
    with urllib.request.urlopen(req, timeout=15) as resp:
        content = resp.read().decode("utf-8")
        reader = csv.reader(io.StringIO(content))
        for row_idx, row in enumerate(reader, 1):
            if row and row[0].strip():
                sku_val = row[0].strip()
                if not sku_val.lower().startswith("sku"):
                    skus_with_rows.append((row_idx, sku_val))
except Exception as e:
    print(f"Erreur lors de la lecture du fichier Google Sheets : {e}")
    sys.exit(1)

print(f"{len(skus_with_rows)} SKU(s) trouvés dans le fichier Google Sheet.")

import random

def apply_stealth_and_human_behavior(page):
    try:
        page.evaluate('''() => {
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            Object.defineProperty(navigator, 'languages', {get: () => ['fr-FR', 'fr', 'en-US', 'en']});
            Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
            window.chrome = { runtime: {} };
        }''')
    except Exception:
        pass
    
    pause_ms = int(random.uniform(1500, 3000))
    page.wait_for_timeout(pause_ms)
    
    try:
        page.evaluate("window.scrollBy({top: Math.floor(Math.random() * 250 + 100), behavior: 'smooth'})")
        page.wait_for_timeout(300)
    except Exception:
        pass

def is_real_captcha_present(page):
    try:
        url = page.url.lower()
        title = page.title().lower()
        if "risk/challenge" in url or "risk-id" in url or "captcha" in url or "verify" in title:
            return True
        return page.evaluate('''() => {
            const selectors = [
                ".sui-captcha-container",
                "#sui-captcha-dialog",
                ".geetest_holder",
                ".geetest_wrap",
                "iframe[src*='geetest']",
                "iframe[src*='captcha']",
                "div[class*='captcha-dialog']",
                "div[class*='captcha-box']"
            ];
            for (const s of selectors) {
                const el = document.querySelector(s);
                if (el && (el.offsetWidth > 0 || el.offsetHeight > 0 || getComputedStyle(el).display !== 'none')) {
                    return true;
                }
            }
            return false;
        }''')
    except Exception:
        return False

def check_and_handle_captcha(page, timeout_sec=0):
    if is_real_captcha_present(page):
        print(f"\n  [⚠️ DÉTECTION CAPTCHA] Contrôle de sécurité détecté sur : {page.url}")
        print("  [⏳ PAUSE] Envoi d'une notification Telegram et mise en pause du script...")
        try:
            telegram_notifier.send_telegram_message(
                f"⚠️ <b>DÉTECTION CAPTCHA / SÉCURITÉ !</b>\n"
                f"Un captcha a été détecté sur Chrome :\n<code>{page.url}</code>\n\n"
                f"⏸️ <b>Le script est en pause</b> jusqu'à ce que vous le résolviez sur le navigateur."
            )
        except Exception as e:
            print(f"  [!] Erreur envoi Telegram: {e}")

        # Pause infinie jusqu'à la résolution du captcha
        while True:
            page.wait_for_timeout(3000)
            if not is_real_captcha_present(page):
                print("  [✅ CAPTCHA RÉSOLU] Reprise automatique du script !")
                try:
                    telegram_notifier.send_telegram_message("✅ <b>CAPTCHA RÉSOLU !</b>\nReprise automatique du scraping.")
                except Exception:
                    pass
                page.wait_for_timeout(2000)
                return True
    return True

def scrape_single_sku(page, target_input):
    apply_stealth_and_human_behavior(page)

    if target_input.startswith("http://") or target_input.startswith("https://"):
        target_url = target_input
        page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
        check_and_handle_captcha(page)
        apply_stealth_and_human_behavior(page)
    else:
        search_url = f"https://fr.shein.com/pdsearch/{target_input}/"
        page.goto(search_url, wait_until="domcontentloaded", timeout=60000)
        check_and_handle_captcha(page)
        apply_stealth_and_human_behavior(page)

        product_link = page.evaluate('''() => {
            const links = Array.from(document.querySelectorAll("a[href*=\\"-p-\\"], .product-card a, .goods-title-link, [class*=\\"goods-item\\"] a"));
            return links.length > 0 ? links[0].href : null;
        }''')

        if not product_link:
            print(f"  [X] Aucun produit trouvé sur SHEIN pour '{target_input}'")
            return None
        target_url = product_link.split("?")[0]
        page.goto(target_url, referer=search_url, wait_until="domcontentloaded", timeout=60000)
        check_and_handle_captcha(page)
        apply_stealth_and_human_behavior(page)

    # Attente du chargement complet du produit
    try:
        page.wait_for_selector(".product-intro__head-price, .price-single, [class*='price'], h1, .product-intro", timeout=6000)
    except Exception:
        pass

    # Extraction du vrai SKU
    sku = page.evaluate('''() => {
        const allElements = Array.from(document.querySelectorAll('*'));
        for (const el of allElements) {
            if (el.children.length === 0 && el.textContent && el.textContent.includes('SKU:')) {
                const match = el.textContent.match(/SKU:\\s*([a-zA-Z0-9_-]+)/i);
                if (match) return match[1];
            }
        }
        const bodyMatch = document.body.innerText.match(/SKU:\\s*([a-zA-Z0-9_-]+)/i);
        if (bodyMatch) return bodyMatch[1];
        return null;
    }''')

    html = page.content()
    if not sku:
        m_sn = re.search(r'"goods_sn":\s*"([^"]+)"', html)
        if m_sn:
            sku = m_sn.group(1)
        else:
            m_sku_text = re.search(r'SKU:\s*([a-zA-Z0-9_-]+)', html, re.IGNORECASE)
            if m_sku_text:
                sku = m_sku_text.group(1)
            else:
                match_id = re.search(r"-p-(\d+)", target_url)
                sku = match_id.group(1) if match_id else target_input

    dossier_images = os.path.join("image", sku, "image-screen")
    dossier_desc = os.path.join("image", sku, "desc-screen")
    os.makedirs(dossier_images, exist_ok=True)
    os.makedirs(dossier_desc, exist_ok=True)

    # --- EXTRACTION DES INFORMATIONS (PRIX, TYPE, CATEGORIE, TITRE) ---
    info_data = page.evaluate('''() => {
        // 1. Prix affiché sur SHEIN
        let price = "";
        const priceSelectors = [
            ".product-intro__head-price",
            ".product-intro__head-mainprice",
            ".price-single",
            "[class*=\\"price-sale\\"]",
            "[class*=\\"sale-price\\"]",
            "[class*=\\"Price\\"]",
            "[class*=\\"price\\"]"
        ];
        for (const sel of priceSelectors) {
            const els = document.querySelectorAll(sel);
            for (const el of els) {
                const txt = el.innerText ? el.innerText.trim() : "";
                if (txt && (txt.includes("€") || txt.includes("$"))) {
                    price = txt.replace(/\\n/g, " ");
                    break;
                }
            }
            if (price) break;
        }

        // 2. Breadcrumbs / Catégorie / Type
        const crumbEls = Array.from(document.querySelectorAll(".bread-crumb__item, .breadcrumb a, .breadcrumb span, [class*=\\"crumb\\"] a, [class*=\\"crumb\\"] span, nav[aria-label*=\\"crumb\\"] a, [class*=\\"breadcrumb\\"]"));
        let crumbs = [];
        crumbEls.forEach(el => {
            const t = el.innerText ? el.innerText.trim() : "";
            if (t && t !== "/" && t !== ">" && !crumbs.includes(t)) {
                crumbs.push(t);
            }
        });
        const breadcrumbStr = crumbs.join(" > ");
        const mainType = crumbs.length > 0 ? crumbs[crumbs.length - 1] : "";

        // 3. Spécifications du tableau de détails
        let specType = "";
        const specRows = Array.from(document.querySelectorAll(".product-intro__description-table-item, [class*=\\"description-item\\"], [class*=\\"attr-item\\"], .key-value-item"));
        for (const row of specRows) {
            const keyEl = row.querySelector(".key, [class*=\\"key\\"]");
            const valEl = row.querySelector(".val, [class*=\\"val\\"]");
            if (keyEl && valEl) {
                const k = keyEl.innerText.trim();
                const v = valEl.innerText.trim();
                if (k.toLowerCase().includes("type") || k.toLowerCase().includes("style") || k.toLowerCase().includes("catégorie")) {
                    specType += (specType ? " | " : "") + `${k}: ${v}`;
                }
            }
        }

        // 4. Titre
        const titleEl = document.querySelector(".product-intro__head-name, h1, [class*=\\"goods-name\\"]");
        const titleText = titleEl ? titleEl.innerText.trim() : document.title;

        return {
            title: titleText,
            price: price,
            breadcrumbs: breadcrumbStr,
            mainType: mainType,
            specType: specType
        };
    }''')

    # Secours Regex HTML si prix ou type non trouvé
    price_val = info_data.get("price") or ""
    if not price_val:
        m_price = re.search(r'"formatPrice"\s*:\s*"([^"]+)"', html)
        if m_price:
            price_val = m_price.group(1)
        else:
            m_amount = re.search(r'(\d+[.,]\d+\s*€|€\s*\d+[.,]\d+)', html)
            if m_amount:
                price_val = m_amount.group(1)

    type_val = info_data.get("specType") or info_data.get("mainType") or info_data.get("breadcrumbs") or ""
    if not type_val:
        m_cat = re.search(r'"cat_name"\s*:\s*"([^"]+)"', html)
        if m_cat:
            type_val = m_cat.group(1)

    title_val = info_data.get("title") or "N/A"
    breadcrumbs_val = info_data.get("breadcrumbs") or type_val or "N/A"
    price_val = price_val if price_val else "N/A"
    type_val = type_val if type_val else "N/A"

    print(f"  [+] Vrai SKU : {sku}")
    print(f"  [+] Type / Catégorie : {type_val}")
    print(f"  [+] Prix SHEIN : {price_val}")

    # Enregistrement du fichier info.txt
    info_text_content = (
        f"SKU: {sku}\n"
        f"Titre: {title_val}\n"
        f"Prix SHEIN: {price_val}\n"
        f"Type / Catégorie: {type_val}\n"
        f"Fil d'ariane (Breadcrumb): {breadcrumbs_val}\n"
        f"URL: {target_url}\n"
    )

    with open(os.path.join("image", sku, "info.txt"), "w", encoding="utf-8") as f:
        f.write(info_text_content)

    with open(os.path.join(dossier_desc, "info.txt"), "w", encoding="utf-8") as f:
        f.write(info_text_content)

    def safe_screenshot(path_out, selector=None):
        try:
            if not selector:
                selector = '[class*="product-intro"], .product-intro'
            loc = page.locator(selector).first
            if loc.count() > 0:
                loc.screenshot(path=path_out, timeout=10000, animations="disabled")
                return True
            page.screenshot(path=path_out, timeout=10000, animations="disabled")
            return True
        except Exception as e:
            print(f"    (Warning capture {os.path.basename(path_out)}: {e})")
              # Capture 1: Titre complet (Haut de page / Vue d'ensemble du produit : en-tête, galerie gauche, titre, prix, couleur, tailles, bouton Ajouter au panier sans les articles suggérés bas de page)
    screen_title = os.path.join(dossier_desc, "title_full.png")
    
    page.evaluate('''() => {
        const btns = document.querySelectorAll(".title-expand-icon, [class*=\\"title-expand\\"], [class*=\\"expand-icon\\"]");
        btns.forEach(b => b.click());
        window.scrollTo(0, 0);
    }''')
    page.wait_for_timeout(600)

    clip_box = page.evaluate('''() => {
        const btnCart = document.querySelector("button[class*=\\"add-to-cart\\"], .product-intro__add-btn, [class*=\\"addToCart\\"], .btn-add, .product-intro__submit");
        const purchaseControl = document.querySelector(".purchase-control, [class*=\\"purchase-control\\"]");
        let maxY = 750;
        if (btnCart) {
            const r = btnCart.getBoundingClientRect();
            maxY = r.bottom + 40;
        } else if (purchaseControl) {
            const r = purchaseControl.getBoundingClientRect();
            maxY = r.bottom + 120;
        }
        return {
            x: 0,
            y: 0,
            width: window.innerWidth || 1280,
            height: Math.min(Math.max(650, maxY), 900)
        };
    }''')

    try:
        page.screenshot(path=screen_title, clip=clip_box, timeout=10000)
    except Exception as e:
        print(f"    (Warning capture title_full: {e})")
        safe_screenshot(screen_title)

    # 2. Ouvrir le guide des tailles / accordéon "Tailles & Mesures"
    page.evaluate('''() => {
        let btn = document.querySelector("[name=\\"ProductIntroSizeGuide\\"] button");
        if (!btn) {
            const els = Array.from(document.querySelectorAll("button, a, div[role=\\"button\\"], span"));
            btn = els.find(e => e.innerText && (
                e.innerText.includes("Tailles & Mesures") ||
                e.innerText.trim() === "Guide des tailles" ||
                e.innerText.trim() === "Size Guide"
            ));
        }
        if (btn) {
            btn.scrollIntoView();
            btn.click();
        }
    }''')
    page.wait_for_timeout(1000)

    # Repositionner au centre du champ de vision
    page.evaluate('''() => {
        const section = document.querySelector("[name=\\"ProductIntroSizeGuide\\"]") || 
                        document.querySelector(".sui-drawer__container, [class*=\\"size-chart\\"], [class*=\\"product-chart\\"]");
        if (section) section.scrollIntoView({ block: "center" });
    }''')
    page.wait_for_timeout(500)

    size_selector = '[name="ProductIntroSizeGuide"], .sui-drawer__container, [class*="size-chart"], [class*="product-chart"]'

    # Capture 2: Tableau des tailles (gauche)
    screen_size1 = os.path.join(dossier_desc, "size_chart_1.png")
    safe_screenshot(screen_size1, selector=size_selector)

    # 3. Défiler le tableau vers la droite
    has_scrolled = page.evaluate('''() => {
        const containers = document.querySelectorAll(".bsc-common-size-table__content, [class*=\\"size-table__content\\"], [class*=\\"size-table\\"], .scroll-box, [class*=\\"scroll-box\\"], [class*=\\"table-wrap\\"]");
        let scrolled = false;
        containers.forEach(box => {
            if (box.scrollWidth > box.clientWidth) {
                box.scrollLeft = box.scrollWidth;
                scrolled = true;
            }
        });
        return scrolled;
    }''')
    page.wait_for_timeout(500)

    if has_scrolled:
        screen_size2 = os.path.join(dossier_desc, "size_chart_2.png")
        safe_screenshot(screen_size2, selector=size_selector)

    # Extraction des photos HD uniquement pour la COULEUR CHOISIE (galerie principale)
    gallery_urls = page.evaluate('''() => {
        let urls = [];
        const galleryContainer = document.querySelector(".product-intro__gallery, [class*=\\"product-intro__gallery\\"], [class*=\\"crop-image-container\\"], .product-intro");
        if (galleryContainer) {
            const imgs = Array.from(galleryContainer.querySelectorAll("img"));
            for (const img of imgs) {
                const src = img.getAttribute("data-origin-src") || 
                            img.getAttribute("data-hd-src") || 
                            img.getAttribute("data-src") || 
                            img.src || 
                            img.getAttribute("src") || "";
                if (src && src.includes("ltwebstatic")) {
                    urls.push(src);
                }
            }
        }
        return urls;
    }''')

    if not gallery_urls:
        html_clean = html.replace("\\/", "/")
        gallery_urls = re.findall(r"(?:https?:)?//img\.ltwebstatic\.com/[^\s\"\'\>\?\\]+\.(?:jpg|jpeg|webp)", html_clean)

    hd_images = []
    seen_keys = set()
    exclude_kw = ["logo", "icon", "badge", "banner", "avatar", "pay_", "express", "flag", "star", "nav_", "footer", "button", "size-chart"]

    for src in gallery_urls:
        if not src.startswith("http"):
            src = "https:" + src

        if any(kw in src.lower() for kw in exclude_kw):
            continue

        hd_url = re.sub(r'_thumbnail_[^\.]+', '', src)
        hd_url = re.sub(r'_\d+x\d*', '', hd_url)
        hd_url = re.sub(r'\.(webp|avif)$', '.jpg', hd_url)

        clean_key = re.sub(r'\.(jpg|jpeg|webp|avif)$', '', hd_url)
        if clean_key not in seen_keys:
            seen_keys.add(clean_key)
            hd_images.append(hd_url)

    # Limiter aux photos de la couleur sélectionnée (max 8 photos)
    hd_images = hd_images[:8]

    # Téléchargement et filtrage strict des photos (ignorer les icônes < 20 Ko)
    nb_telecharges = 0
    for img_url in hd_images:
        temp_dest = os.path.join(dossier_images, f"temp_{nb_telecharges + 1}.jpg")
        try:
            req = urllib.request.Request(img_url, headers=headers_http)
            with urllib.request.urlopen(req, timeout=15) as resp, open(temp_dest, "wb") as f:
                f.write(resp.read())
            
            taille_ko = round(os.path.getsize(temp_dest) / 1024, 1)
            if taille_ko < 20:
                # Image inutile / petit badge / icône -> suppression
                if os.path.exists(temp_dest):
                    os.remove(temp_dest)
            else:
                nb_telecharges += 1
                fichier_final = os.path.join(dossier_images, f"photo_{nb_telecharges}.jpg")
                os.rename(temp_dest, fichier_final)
        except Exception as e:
            if os.path.exists(temp_dest):
                os.remove(temp_dest)

    return sku, nb_telecharges

def update_google_sheet_status(sheet_page, row_idx, status="Fait"):
    try:
        sheet_page.bring_to_front()
        for col_letter in ["B", "C"]:
            cell_coord = f"{col_letter}{row_idx}"
            name_box = sheet_page.locator("#t-name-box").first
            name_box.click()
            name_box.fill(cell_coord)
            sheet_page.keyboard.press("Enter")
            sheet_page.wait_for_timeout(150)
            sheet_page.keyboard.type(status)
            sheet_page.keyboard.press("Enter")
            sheet_page.wait_for_timeout(200)
        return True
    except Exception as e:
        print(f"    (Erreur maj Google Sheet pour la ligne {row_idx} : {e})")
        return False

print("\nConnexion au navigateur Chrome...")
with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
    context = browser.contexts[0]

    # Onglet Google Sheets
    sheet_page = None
    for p_item in context.pages:
        if "spreadsheets" in p_item.url:
            sheet_page = p_item
            break
    if not sheet_page:
        sheet_page = context.new_page()
        sheet_page.goto(sheet_input_url, wait_until="domcontentloaded")
        sheet_page.wait_for_timeout(3000)

    # Onglet dédié au scraping SHEIN
    scrape_page = context.new_page()

    succes_count = 0
    erreur_count = 0

    for current_num, (row_idx, current_sku) in enumerate(skus_with_rows, 1):
        print(f"\n[{current_num}/{len(skus_with_rows)}] (Ligne Excel {row_idx}) SKU : {current_sku}")
        try:
            res = scrape_single_sku(scrape_page, current_sku)
            if res:
                sku_real, nb_photos = res
                print(f"  [OK] Scraping SKU {sku_real} terminé ({nb_photos} photos HD, 3 captures desc).")
                
                # Mise à jour Google Sheet
                updated = update_google_sheet_status(sheet_page, row_idx, status="Fait")
                if updated:
                    print(f"  [OK] Google Sheet mis à jour pour la ligne {row_idx} (B{row_idx} et C{row_idx} -> 'Fait')")
                succes_count += 1
            else:
                erreur_count += 1
        except Exception as e:
            print(f"  [X] Erreur lors du traitement du SKU {current_sku} : {e}")
            erreur_count += 1

    scrape_page.close()

print(f"\n==================================================")
print(f"SCRAPING PAR LOT TERMINÉ : {succes_count}/{len(skus_with_rows)} SKU(s) réussis, {erreur_count} erreur(s).")
print(f"==================================================")
