import time
import os
import sys
import argparse
import requests
from playwright.sync_api import sync_playwright

IMAGE_BASE_DIR = "/root/shein/image"
OUTPUT_BASE_DIR = "/root/shein/photo marie"

PROMPT_FACE = """Fait exactement le même vêtement posé à plat sur le lit avec des draps bleu ciel doux code HEX : #87CEEB, légèrement froissé. Le vêtement doit être posé de façon naturelle et détendue, comme s'il venait d'être délicatement déposé — ni parfaitement lissé et symétrique, ni chiffonné ou jeté négligemment. Règles précises :
- Les deux manches doivent être entièrement visibles et étalées à plat sur le côté, jamais repliées, tordues, écrasées ou cachées sous le vêtement
- Chaque manche peut avoir un tombé légèrement différent de l'autre (une texture ou un angle très légèrement variable), mais aucune des deux ne doit paraître "abandonnée" ou en désordre — les deux doivent rester nettes et lisibles
- De légers plis naturels sont autorisés en haut, en bas et au niveau des manches du vêtement, mais ils doivent être fins et discrets, jamais un gros pli qui replie le tissu sur lui-même
- Aucun pli ne doit masquer, déformer ou cacher un motif, imprimé, texte ou détail présent sur le vêtement — la lisibilité du visuel doit toujours être totale et nette
- L'ourlet du bas peut présenter un très léger pli asymétrique sur UN SEUL côté (jamais les deux côtés à la fois)
- Si le vêtement comporte un lien, un ruban ou un nœud, il doit être noué à la main de façon réaliste et propre, pas parfaitement rond, pas totalement défait
- AUCUN accessoire visible : pas de sac, pas de cintre, pas de bijoux, pas de sous-vêtement qui dépasse
- La matière reste globalement lisse avec juste assez d'irrégularité pour ne pas faire "repassé au fer" ou "rendu 3D"
- Le vêtement est centré dans l'image, avec une marge de 35 cm visible de CHAQUE côté (gauche, droite, haut, bas)
- Photo prise STRICTEMENT DU DESSUS (vue du dessus flat-lay bird's eye view à 90°)
- Le drap bleu ciel (#87CEEB) est clairement visible tout autour en arrière-plan
- Photo produit e-commerce professionnelle réaliste pour vente en ligne, VUE DE FACE"""

PROMPT_BACK = """Fait exactement le même vêtement posé à plat sur le lit avec des draps bleu ciel doux code HEX : #87CEEB, légèrement froissé. Le vêtement doit être posé de façon naturelle et détendue. VUE DE DOS :
- Montrer clairement le DOS / l'arrière du vêtement
- Les coutures arrière, le pan dorsal et le fermoir/zip (si présent) doivent être bien visibles et étalés à plat
- Les deux côtés arrière doivent être entièrement visibles
- AUCUN accessoire visible
- Le vêtement est centré avec 35 cm de marge tout autour
- Photo prise STRICTEMENT DU DESSUS (flat-lay vue du dessus à 90°)
- Le drap bleu ciel (#87CEEB) est clairement visible tout autour
- Photo produit e-commerce professionnelle réaliste pour vente en ligne, VUE DE DOS"""

def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)

def find_best_photo(sku):
    screen_dir = os.path.join(IMAGE_BASE_DIR, sku, "image-screen")
    if not os.path.exists(screen_dir):
        return None
    photos = sorted([os.path.join(screen_dir, f) for f in os.listdir(screen_dir) if f.startswith("photo_") and f.endswith(".jpg")])
    if photos:
        return photos[0]
    return None

def extract_and_save_images(page, output_dir, prefix):
    os.makedirs(output_dir, exist_ok=True)
    imgs = page.query_selector_all("img")
    saved_count = 0
    for idx, img in enumerate(imgs):
        src = img.get_attribute("src") or ""
        alt = img.get_attribute("alt") or ""
        if ("googleusercontent" in src or "blob:" in src or "generativelanguage" in src) and ("photo" not in alt.lower() and "profile" not in alt.lower()):
            box = img.bounding_box()
            if box and box["width"] > 150 and box["height"] > 150:
                img_path = os.path.join(output_dir, f"{prefix}_{saved_count+1}.png")
                try:
                    img.screenshot(path=img_path)
                    log(f"  [+] Image sauvegardée : {img_path}")
                    saved_count += 1
                except Exception as e:
                    log(f"  [!] Erreur capture image : {e}")
    
    fallback_path = os.path.join(output_dir, f"{prefix}_page.png")
    page.screenshot(path=fallback_path)
    log(f"  [+] Capture de secours : {fallback_path}")
    return saved_count

def process_single_sku(page, sku):
    photo_path = find_best_photo(sku)
    if not photo_path:
        log(f"[!] Pas de photo source disponible pour SKU {sku}")
        return False
        
    out_dir = os.path.join(OUTPUT_BASE_DIR, sku, "flatlay")
    face_exists = os.path.exists(os.path.join(out_dir, "flatlay_face.png")) or os.path.exists(os.path.join(out_dir, "flatlay_face_1.png"))
    back_exists = os.path.exists(os.path.join(out_dir, "flatlay_back.png")) or os.path.exists(os.path.join(out_dir, "flatlay_back_1.png"))
    
    if face_exists and back_exists:
        log(f"[=] SKU {sku} déjà traité (images existantes), ignoré.")
        return True
        
    log(f"=== Traitement SKU : {sku} ===")
    log(f"  Photo source : {photo_path}")
    log(f"  Dossier de sortie : {out_dir}")
    
    # 1. Upload photo via file input or plus button
    log("  Importation photo...")
    file_input = page.query_selector("input[type='file']")
    if not file_input:
        plus_btn = page.query_selector("button[aria-label*='Importation'], button[aria-label*='Plus']")
        if plus_btn:
            plus_btn.click()
            page.wait_for_timeout(1000)
        file_input = page.query_selector("input[type='file']")
        
    if file_input:
        file_input.set_input_files(photo_path)
        log("  Fichier chargé !")
        page.wait_for_timeout(2000)
    else:
        log("  [!] file_input introuvable")
        
    # 2. FACE
    if not face_exists:
        log("  Envoi du prompt FACE...")
        prompt_div = page.query_selector("div[contenteditable='true']")
        if prompt_div:
            prompt_div.click()
            page.keyboard.insert_text(PROMPT_FACE)
            page.wait_for_timeout(1000)
            
            send_btn = page.query_selector("button[aria-label*='Envoyer'], button[aria-label*='submit']")
            if send_btn and send_btn.is_enabled():
                send_btn.click()
            else:
                page.keyboard.press("Enter")
                
            log("  Génération FACE en cours (attente 25s)...")
            page.wait_for_timeout(25000)
            extract_and_save_images(page, out_dir, "flatlay_face")
            
    # 3. BACK
    if not back_exists:
        log("  Envoi du prompt DOS...")
        prompt_div = page.query_selector("div[contenteditable='true']")
        if prompt_div:
            prompt_div.click()
            page.keyboard.insert_text(PROMPT_BACK)
            page.wait_for_timeout(1000)
            
            send_btn = page.query_selector("button[aria-label*='Envoyer'], button[aria-label*='submit']")
            if send_btn and send_btn.is_enabled():
                send_btn.click()
            else:
                page.keyboard.press("Enter")
                
            log("  Génération DOS en cours (attente 25s)...")
            page.wait_for_timeout(25000)
            extract_and_save_images(page, out_dir, "flatlay_back")
            
    return True

def get_gemini_ws_url():
    try:
        pages = requests.get("http://127.0.0.1:44231/json/list", timeout=3).json()
        for p in pages:
            if p.get("type") == "page" and "gemini.google.com" in p.get("url", ""):
                return p.get("webSocketDebuggerUrl")
        for p in pages:
            if p.get("type") == "page":
                return p.get("webSocketDebuggerUrl")
    except Exception as e:
        log(f"Error fetching json/list: {e}")
    return "http://127.0.0.1:44231"

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sku", type=str, help="SKU unique à traiter")
    parser.add_argument("--all", action="store_true", help="Traiter tous les SKUs dans image/")
    args = parser.parse_args()
    
    if not args.sku and not args.all:
        args.all = True
        
    if args.all:
        skus = sorted([d for d in os.listdir(IMAGE_BASE_DIR) if os.path.isdir(os.path.join(IMAGE_BASE_DIR, d))])
    else:
        skus = [args.sku]
        
    log(f"Lancement de la génération pour {len(skus)} SKU(s)...")
    ws_url = get_gemini_ws_url()
    log(f"Connexion au WebSocket cible : {ws_url}")
    
    with sync_playwright() as p:
        try:
            browser = p.chromium.connect_over_cdp(ws_url, timeout=10000)
            context = browser.contexts[0]
            
            page = None
            if context.pages:
                page = context.pages[0]
            else:
                page = context.new_page()
                
            if "gemini.google.com" not in page.url:
                page.goto("https://gemini.google.com/app", wait_until="domcontentloaded")
                page.wait_for_timeout(3000)
                
            page.bring_to_front()
            log(f"Onglet Gemini connecté : {page.url}")
            
            for idx, sku in enumerate(skus, 1):
                log(f"\n[{idx}/{len(skus)}] Traitement du SKU : {sku}")
                process_single_sku(page, sku)
                time.sleep(2)
        except Exception as e:
            log(f"[ERR] Erreur lors de la connexion/exécution : {e}")

if __name__ == "__main__":
    main()
