import re
import sys
import os
import urllib.request
import telegram_notifier
from playwright.sync_api import sync_playwright

if len(sys.argv) < 2:
    print("Usage: python scraper.py [PORT_CDP] <SKU_OU_URL>")
    sys.exit(1)

output_base_dir = None
if len(sys.argv) >= 4:
    port = sys.argv[1]
    input_arg = sys.argv[2].strip()
    output_base_dir = sys.argv[3].strip()
elif len(sys.argv) >= 3:
    port = sys.argv[1]
    input_arg = sys.argv[2].strip()
else:
    if sys.argv[1].isdigit():
        port = sys.argv[1]
        print("Erreur: SKU ou URL manquant.")
        sys.exit(1)
    else:
        port = "44231"
        input_arg = sys.argv[1].strip()

print(f"Utilisation du port CDP : {port}")

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
        if (
            "risk/challenge" in url
            or "risk/action/limit" in url
            or "risk-id" in url
            or "captcha" in url
            or "verify" in title
            or "status: 403" in title
        ):
            return True
        return page.evaluate('''() => {
            const body = document.body ? document.body.innerText.toLowerCase() : "";
            if (body.includes("status: 403") || body.includes("contrôle de sécurité")) {
                return true;
            }
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
        print(f"\n  [⚠️ BLOCAGE / CAPTCHA DÉTECTÉ] Contrôle de sécurité SHEIN ou limite 403 sur : {page.url}")
        print("  [⏳ PAUSE] Envoi d'une alerte Telegram et attente de déblocage...")
        try:
            telegram_notifier.send_telegram_message(
                f"⚠️ <b>ALERTE SÉCURITÉ / 403 SHEIN !</b>\n"
                f"Page de blocage / captcha détectée sur le navigateur unique :\n<code>{page.url}</code>\n\n"
                f"⏸️ <b>Le scraping est en pause.</b>\n"
                f"Veuillez recharger ou valider le contrôle de sécurité dans Chromium pour reprendre."
            )
        except Exception as e:
            print(f"  [!] Erreur envoi Telegram: {e}")

        # Pause jusqu'à la résolution du captcha ou déblocage de la page
        while True:
            page.wait_for_timeout(3000)
            if not is_real_captcha_present(page):
                print("  [✅ SÉCURITÉ RÉSOLUE] Reprise automatique du scraping !")
                try:
                    telegram_notifier.send_telegram_message("✅ <b>SÉCURITÉ RÉSOLUE !</b>\nReprise du scraping.")
                except Exception:
                    pass
                page.wait_for_timeout(2000)
                return True
    return True

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
    context = browser.contexts[0]
    page = context.new_page()

    apply_stealth_and_human_behavior(page)

    if input_arg.startswith("http://") or input_arg.startswith("https://"):
        target_url = input_arg
        page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
        check_and_handle_captcha(page)
        apply_stealth_and_human_behavior(page)
    else:
        print(f"Recherche du SKU / produit : {input_arg}...")
        search_url = f"https://fr.shein.com/pdsearch/{input_arg}/"
        page.goto(search_url, wait_until="domcontentloaded", timeout=60000)
        check_and_handle_captcha(page)
        apply_stealth_and_human_behavior(page)

        product_link = page.evaluate('''() => {
            const links = Array.from(document.querySelectorAll("a[href*=\\"-p-\\"], .product-card a, .goods-title-link, [class*=\\"goods-item\\"] a"));
            return links.length > 0 ? links[0].href : null;
        }''')

        if product_link:
            target_url = product_link.split("?")[0]
            print(f"Navigation vers la page produit : {target_url}")
            page.goto(target_url, referer=search_url, wait_until="domcontentloaded", timeout=60000)
            check_and_handle_captcha(page)
            apply_stealth_and_human_behavior(page)
        else:
            print(f"Erreur : Aucun produit trouvé pour le SKU / terme de recherche '{input_arg}'.")
            page.close()
            sys.exit(1)

    print(f"Navigation vers la page produit : {target_url}")
    page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(3000)

    title = page.title()
    final_url = page.url
    print("Titre :", title)
    print("URL finale :", final_url)

    # Extraction du vrai SKU depuis le DOM ou le code source (goods_sn / text 'SKU:')
    sku = page.evaluate('''() => {
        // 1. Recherche dans les éléments texte pour 'SKU:'
        const allElements = Array.from(document.querySelectorAll('*'));
        for (const el of allElements) {
            if (el.children.length === 0 && el.textContent && el.textContent.includes('SKU:')) {
                const match = el.textContent.match(/SKU:\\s*([a-zA-Z0-9_-]+)/i);
                if (match) return match[1];
            }
        }
        // 2. Recherche globale dans le texte de la page
        const bodyMatch = document.body.innerText.match(/SKU:\\s*([a-zA-Z0-9_-]+)/i);
        if (bodyMatch) return bodyMatch[1];
        return null;
    }''')

    html = page.content()
    if not sku:
        # Recherche regex secours dans le JSON HTML (goods_sn)
        m_sn = re.search(r'"goods_sn":\s*"([^"]+)"', html)
        if m_sn:
            sku = m_sn.group(1)
        else:
            m_sku_text = re.search(r'SKU:\s*([a-zA-Z0-9_-]+)', html, re.IGNORECASE)
            if m_sku_text:
                sku = m_sku_text.group(1)
            else:
                # Secours avec l'ID produit extrait de l'URL
                match_id = re.search(r"-p-(\d+)", target_url)
                sku = match_id.group(1) if match_id else "article"

    item_dir = output_base_dir if output_base_dir else os.path.join("image", sku)
    dossier_images = item_dir
    dossier_desc = item_dir
    os.makedirs(item_dir, exist_ok=True)

    # --- EXTRACTION DES INFORMATIONS (PRIX, TYPE, CATEGORIE, TITRE) ---
    info_data = page.evaluate('''() => {
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

    title_val = info_data.get("title") or title
    breadcrumbs_val = info_data.get("breadcrumbs") or type_val or "N/A"
    price_val = price_val if price_val else "N/A"
    type_val = type_val if type_val else "N/A"

    print(f"Vrai SKU identifié : {sku}")
    print(f"Type / Catégorie : {type_val}")
    print(f"Prix SHEIN : {price_val}")
    print(f"Dossier photos HD : {dossier_images}")
    print(f"Dossier captures description : {dossier_desc}\n")

    info_text_content = (
        f"SKU: {sku}\n"
        f"SKU_RECHERCHE: {input_arg}\n"
        f"Titre: {title_val}\n"
        f"Prix SHEIN: {price_val}\n"
        f"Type / Catégorie: {type_val}\n"
        f"Fil d'ariane (Breadcrumb): {breadcrumbs_val}\n"
        f"URL: {target_url}\n"
    )

    with open(os.path.join(item_dir, "info.txt"), "w", encoding="utf-8") as f:
        f.write(info_text_content)

    def safe_screenshot(path_out, selector=None):
        try:
            if selector:
                loc = page.locator(selector).first
                if loc.count() > 0:
                    loc.screenshot(path=path_out, timeout=20000)
                    return True
            page.screenshot(path=path_out, timeout=20000)
            return True
        except Exception as e:
            print(f"    Warning: screenshot {path_out} failed ({e})")
            return False

    # --- CAPTURES DE DESCRIPTION (desc-screen) ---
    print("Captures d'écran de description en cours...")

    # 1. Capture 1: Titre complet (Haut de page / Vue d'ensemble du produit : en-tête, galerie gauche, titre, prix, couleur, tailles, bouton Ajouter au panier sans les articles suggérés bas de page)
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
    print(f"  [1/3] Capture du titre complet : {screen_title}")

    # 2. Ouvrir le guide des tailles / tableau des mesures (accordéon ou lien)
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
    page.wait_for_timeout(1500)

    # Repositionner la section des tailles au centre du champ de vision
    page.evaluate('''() => {
        const section = document.querySelector("[name=\\"ProductIntroSizeGuide\\"]") || 
                        document.querySelector(".sui-drawer__container, [class*=\\"size-chart\\"], [class*=\\"product-chart\\"]");
        if (section) section.scrollIntoView({ block: "center" });
    }''')
    page.wait_for_timeout(500)

    # Capture 2: Tableau des tailles (vue gauche / standard)
    screen_size1 = os.path.join(dossier_desc, "size_chart_1.png")
    safe_screenshot(screen_size1)
    print(f"  [2/3] Capture du tableau des tailles (gauche) : {screen_size1}")

    # 3. Défiler le tableau des tailles vers la droite pour afficher les colonnes masquées
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

    # Capture 3: Tableau des tailles (vue défilée vers la droite)
    if has_scrolled:
        screen_size2 = os.path.join(dossier_desc, "size_chart_2.png")
        safe_screenshot(screen_size2)
        print(f"  [3/3] Capture du tableau des tailles (droite) : {screen_size2}")

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

    page.close()

# Traitement et nettoyage des URLs pour obtenir la haute résolution (HD)
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

# Limiter strictement aux photos de la galerie de la couleur sélectionnée (max 8 photos)
hd_images = hd_images[:8]

print(f"\n{len(hd_images)} photo(s) HD identifiée(s). Téléchargement en cours...")

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

nb_telecharges = 0
for img_url in hd_images:
    temp_dest = os.path.join(dossier_images, f"temp_{nb_telecharges + 1}.jpg")
    try:
        req = urllib.request.Request(img_url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp, open(temp_dest, "wb") as f:
            f.write(resp.read())
        taille_ko = round(os.path.getsize(temp_dest) / 1024, 1)
        if taille_ko < 20:
            if os.path.exists(temp_dest):
                os.remove(temp_dest)
        else:
            nb_telecharges += 1
            fichier_final = os.path.join(dossier_images, f"photo_{nb_telecharges}.jpg")
            os.rename(temp_dest, fichier_final)
            print(f"  [{nb_telecharges}] Enregistrée : {fichier_final} ({taille_ko} Ko)")
    except Exception as e:
        if os.path.exists(temp_dest):
            os.remove(temp_dest)
        print(f"  Erreur lors du téléchargement de {img_url} : {e}")

print(f"\nTerminé ! {nb_telecharges} photos HD enregistrées dans {dossier_images}")
try:
    page.close()
except Exception:
    pass