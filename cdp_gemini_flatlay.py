import time
import os
import sys
import json
import base64
import glob
import re
import urllib.request
import csv
import io
import shutil
import gspread
from google.oauth2.service_account import Credentials
from playwright.sync_api import sync_playwright

IMAGE_BASE_DIR = "/root/shein/image"
OUTPUT_BASE_DIR = "/root/shein/screen_marie"
SHEET_CSV_URL = "https://docs.google.com/spreadsheets/d/1zmlzcgozbhvbs_SrTBi0S1E-igDeSZQtRIrrjqUpYU0/export?format=csv&gid=160439786"
ATTENTE_MAX = 240  # secondes max par génération

def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)

def init_gspread():
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_file("/root/shein/service_account.json", scopes=scope)
        client = gspread.authorize(creds)
        return client.open_by_key("1zmlzcgozbhvbs_SrTBi0S1E-igDeSZQtRIrrjqUpYU0").sheet1
    except Exception as e:
        log(f"[!] Erreur connexion gspread : {e}")
        return None

def update_google_sheet_status(gspread_sheet, row_idx, scrap_status="Fait scrap", image_status="Image générée"):
    if not gspread_sheet or not row_idx:
        return False
    try:
        if scrap_status:
            gspread_sheet.update_cell(row_idx, 2, scrap_status)
        if image_status:
            gspread_sheet.update_cell(row_idx, 3, image_status)
        log(f"  [📊 Google Sheet] Ligne {row_idx} mise à jour: Col B='{scrap_status}', Col C='{image_status}'")
        return True
    except Exception as e:
        log(f"  [!] Erreur mise à jour Google Sheet : {e}")
        return False

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

# Script JS pour simuler un coller (ClipboardEvent paste) avec DataTransfer et File
JS_COLLER = """
(fichiers) => {
  const dt = new DataTransfer();
  for (const f of fichiers) {
    const bin = atob(f.data);
    const octets = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) octets[i] = bin.charCodeAt(i);
    dt.items.add(new File([octets], f.nom, { type: f.type || 'image/jpeg' }));
  }
  const zone = document.querySelector('rich-textarea div[contenteditable="true"]')
            || document.querySelector('div[contenteditable="true"]');
  if (!zone) return false;
  zone.focus();
  zone.dispatchEvent(new ClipboardEvent('paste',
      { clipboardData: dt, bubbles: true, cancelable: true }));
  return true;
}
"""

# Script JS pour extraire l'image aux dimensions naturelles (HD) via Canvas HTML5
JS_CANVAS = """
(e) => {
  const canvas = document.createElement("canvas");
  canvas.width = e.naturalWidth || e.width;
  canvas.height = e.naturalHeight || e.height;
  const ctx = canvas.getContext("2d");
  ctx.drawImage(e, 0, 0);
  return canvas.toDataURL("image/png").split(",")[1];
}
"""

def fetch_sku_row_mapping():
    mapping = {}
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        req = urllib.request.Request(SHEET_CSV_URL, headers=headers)
        with urllib.request.urlopen(req) as resp:
            content = resp.read().decode("utf-8")
            reader = csv.reader(io.StringIO(content))
            for row_idx, row in enumerate(reader, 1):
                if row and row[0].strip():
                    sku = row[0].strip()
                    mapping[sku] = row_idx
    except Exception as e:
        log(f"[!] Erreur lecture mapping Google Sheet : {e}")
    return mapping

def images_generees(page):
    """Retourne les éléments img haute résolution générés par Gemini."""
    resultat = []
    imgs = page.locator("model-response img, message-content img, div.image-container img")
    for i in range(imgs.count()):
        el = imgs.nth(i)
        try:
            w, h = el.evaluate("e => [e.naturalWidth || e.width || 0, e.naturalHeight || e.height || 0]")
            src = el.evaluate("e => e.src || ''")
        except Exception:
            continue
        if w >= 300 and h >= 300 and "profile" not in src:
            resultat.append(el)
    return resultat

def prepare_gemini_page(page):
    """
    S'assure que la page Gemini est sur un nouveau chat vierge, sans popups bloquantes,
    avec la zone d'édition contenteditable prête et active.
    """
    try:
        if "gemini.google.com" in (page.url or ""):
            new_chat_btn = page.locator('button:has-text("Nouvelle discussion"), a[href="/app"], [aria-label*="Nouvelle discussion"], [aria-label*="New chat"]').first
            if new_chat_btn.is_visible():
                new_chat_btn.click(force=True, timeout=2500)
                page.wait_for_timeout(1000)
            else:
                page.goto("https://gemini.google.com/app?hl=fr", wait_until="domcontentloaded", timeout=30000)
        else:
            page.goto("https://gemini.google.com/app?hl=fr", wait_until="domcontentloaded", timeout=30000)
    except Exception as e_nav:
        log(f"  [⚠️ Info Navigation] ({e_nav})")

    # Fermer les bannières / modales d'introduction ("C'est parti", "Compris", etc.)
    try:
        for btn_txt in ["C'est parti", "C’est parti", "Compris", "Continuer", "Accepter", "Got it", "Dismiss"]:
            b = page.locator(f'button:has-text("{btn_txt}")')
            for i in range(b.count()):
                if b.nth(i).is_visible():
                    b.nth(i).click(force=True, timeout=1000)
    except Exception:
        pass

    # S'assurer que le modèle n'est pas bloqué sur Flash-Lite (qui ne génère pas d'images)
    try:
        flash_lite_btn = page.locator('button:has-text("Flash-Lite")')
        if flash_lite_btn.count() > 0 and flash_lite_btn.first.is_visible():
            flash_lite_btn.first.click(force=True, timeout=2000)
            page.wait_for_timeout(500)
            pro_opt = page.locator('[role="menuitem"]:has-text("Pro"), [role="menuitem"]:has-text("Auto"), [role="option"]:has-text("Pro")')
            if pro_opt.count() > 0:
                pro_opt.first.click(force=True, timeout=2000)
    except Exception:
        pass

    # Attendre et focaliser la zone contenteditable
    try:
        page.wait_for_selector('rich-textarea div[contenteditable="true"], div[contenteditable="true"]', state="visible", timeout=25000)
        zone = page.locator('rich-textarea div[contenteditable="true"], div[contenteditable="true"]').first
        zone.focus()
        zone.click(force=True, timeout=2000)
    except Exception as e_zone:
        log(f"  [⚠️ Attente zone texte] ({e_zone})")

def count_attached_previews(page):
    try:
        return page.evaluate("""() => {
            const sel = 'uploader-file-item, div.attachment-container, img[src^="blob:"], [data-test-id*="attachment"], div.file-preview, rich-textarea img';
            return document.querySelectorAll(sel).length;
        }""")
    except Exception:
        return 0

def check_gemini_quota(page):
    try:
        return page.evaluate("""() => {
            const txt = (document.body.innerText || "").toLowerCase();
            return txt.includes("limite sera réinitialisée") || txt.includes("limite d'utilisation atteinte");
        }""")
    except Exception:
        return False

def get_gemini_quota_info(page):
    try:
        return page.evaluate("""() => {
            const txt = document.body.innerText || "";
            const lines = txt.split("\\n");
            for (const l of lines) {
                const s = l.trim();
                if (s.toLowerCase().includes("limite sera réinitialisée") || s.toLowerCase().includes("limite d'utilisation atteinte")) {
                    return s;
                }
            }
            return "";
        }""")
    except Exception:
        return ""

def generate_view_paste(page, prompt_text, out_file, fichiers_base64, view_label):
    prepare_gemini_page(page)
    page.wait_for_timeout(1000)

    # 0. Vérification préliminaire : compte déjà sous quota ?
    if check_gemini_quota(page):
        q_info = get_gemini_quota_info(page) or "Limite de génération d'images atteinte"
        log(f"  [⚠️ Quota Gemini Actif] {q_info}")
        return False
    
    # 1. Coller les photos via DataTransfer ClipboardEvent avec vérification de l'attachement réel
    log(f"  [📋 Copier-Coller {view_label}] Collage de {len(fichiers_base64)} photos dans la zone de message...")
    photos_attached = False

    for attempt in range(3):
        res_coller = page.evaluate(JS_COLLER, fichiers_base64)
        if not res_coller:
            log(f"  [!] Zone de saisie non disponible (essai {attempt+1}/3), nouvelle tentative...")
            page.wait_for_timeout(2000)
            continue
        
        # Attente de l'apparition des miniatures attachées
        attente_max_attach = 6 + len(fichiers_base64) * 2
        start_att = time.time()
        while time.time() - start_att < attente_max_attach:
            cnt = count_attached_previews(page)
            if cnt > 0:
                photos_attached = True
                log(f"  [📸 Vignettes {view_label}] {cnt} photo(s) confirmée(s) attachée(s) dans Gemini !")
                break
            page.wait_for_timeout(1000)

        if photos_attached:
            break
        else:
            log(f"  [⚠️ Vignettes {view_label}] Aucune miniature confirmée (essai {attempt+1}/3)...")
            page.wait_for_timeout(2000)

    # VÉRIFICATION STRICTE : Si aucune photo n'a pu être attachée, NE JAMAIS ENVOYER LE TEXTE SEUL
    if not photos_attached:
        log(f"  [⛔ ÉCHEC ATTACHEMENT {view_label}] Les photos sources n'ont pas pu être attachées dans Gemini. Envoi annulé pour éviter une génération sans image de référence.")
        return False
    
    # 2. Écrire le prompt et envoyer
    log(f"  [📝 Prompt {view_label}] Écriture du prompt et envoi...")
    js_insert_prompt = """
    (text) => {
        const el = document.querySelector('rich-textarea div[contenteditable="true"]') || document.querySelector('div[contenteditable="true"]');
        if (!el) return false;
        el.focus();
        document.execCommand('insertText', false, text);
        ['input', 'change'].forEach(ev => el.dispatchEvent(new Event(ev, { bubbles: true, cancelable: true })));
        return true;
    }
    """
    res_prompt = page.evaluate(js_insert_prompt, prompt_text)
    if not res_prompt:
        try:
            zone = page.locator('rich-textarea div[contenteditable="true"], div[contenteditable="true"]').first
            zone.focus()
            zone.click(force=True, timeout=2000)
            page.keyboard.insert_text(prompt_text)
        except Exception:
            pass
    page.wait_for_timeout(1000)

    send_btn = page.locator('button.send-button, button[aria-label*="Envoyer"], button[aria-label*="Send"]').first
    try:
        if send_btn.is_visible():
            send_btn.click(force=True, timeout=3000)
            log(f"  [🚀 Envoi {view_label}] Bouton envoi cliqué !")
        else:
            page.keyboard.press("Enter")
            log(f"  [🚀 Envoi {view_label}] Touche Entrée pressée !")
    except Exception:
        page.keyboard.press("Enter")
        log(f"  [🚀 Envoi {view_label}] Fallback Entrée pressée !")

    # 3. Attendre l'image générée ou détecter un message de refus / quota
    fin = time.time() + ATTENTE_MAX
    while time.time() < fin:
        imgs = images_generees(page)
        if imgs:
            break

        # Détection de quota / limite de génération
        if check_gemini_quota(page):
            q_info = get_gemini_quota_info(page) or "Limite de génération d'images atteinte"
            log(f"  [⚠️ Quota Gemini Détecté] {q_info}")
            break

        page.wait_for_timeout(3000)
        
    page.wait_for_timeout(4000)  # Laisser l'image finir de charger
    
    # 4. Enregistrer l'image HD (Direct Canvas Extract naturalDimensions)
    resultats = images_generees(page)
    if resultats:
        el = resultats[-1]
        try:
            b64_data = el.evaluate(JS_CANVAS)
            data = base64.b64decode(b64_data)
        except Exception as e_err:
            log(f"  [!] Extraction Canvas échouée ({e_err}), secours screenshot...")
            data = el.screenshot()
        with open(out_file, "wb") as f:
            f.write(data)
        kb = round(len(data) / 1024, 1)
        log(f"  [+] Image HD {view_label} extraite en direct (Canvas) : {out_file} ({kb} KB)")
        return True
    else:
        log(f"  [!] Aucune image générée détectée pour {view_label}.")
        # N'enregistrer le debug screenshot que si ce n'est pas un simple quota
        if not check_gemini_quota(page):
            debug_path = os.path.join(os.path.dirname(out_file), f"debug_echec_{view_label.lower()}.png")
            try: page.screenshot(path=debug_path)
            except Exception: pass
        if os.path.exists(out_file):
            try: os.remove(out_file)
            except Exception: pass
        return False

def process_sku_paste(page, gspread_sheet, sku, row_mapping, target_view="all"):
    account_name = gspread_sheet.title.strip() if (gspread_sheet and hasattr(gspread_sheet, 'title') and gspread_sheet.title) else "defaut"
    date_str = time.strftime("%Y-%m-%d")
    item_dir = f"/root/shein/screen_{date_str}/screen_{account_name}/{sku}"
    if not os.path.exists(item_dir):
        matches = glob.glob(f"/root/shein/screen_*/screen_{account_name}/{sku}")
        if not matches:
            matches = glob.glob(f"/root/shein/screen_*/*{account_name[:4]}*/{sku}")
        if matches:
            matches.sort(reverse=True)
            item_dir = matches[0]
    # Fichiers placés directement à la racine de {sku}, sans sous-dossiers ni doublons
    out_dir = item_dir
    face_file = os.path.join(item_dir, "flatlay_face.png")
    back_file = os.path.join(item_dir, "flatlay_back.png")
    
    # Recherche des photos sources : directement dans item_dir, ou secours dans image-screen/
    photos = sorted([os.path.join(item_dir, f) for f in os.listdir(item_dir) if f.startswith("photo_") and f.endswith(".jpg")])
    if not photos:
        screen_dir = os.path.join(item_dir, "image-screen")
        if os.path.exists(screen_dir):
            photos = sorted([os.path.join(screen_dir, f) for f in os.listdir(screen_dir) if f.startswith("photo_") and f.endswith(".jpg")])
    if not photos:
        log(f"[!] Pas de photo source pour SKU {sku}")
        return
        
    log(f"\n=== Traitement SKU : {sku} ===")
    log(f"  Photo source originale : {photos[0]}")
    log(f"  Dossier de sortie : {out_dir}")
    
    # 1. Préparer les fichiers base64 pour le collage JS (Max 5 photos pour éviter la saturation d'attachement Gemini)
    photos_to_attach = photos[:5]
    fichiers_base64 = []
    for chemin in photos_to_attach:
        with open(chemin, "rb") as f:
            fichiers_base64.append({
                "nom": os.path.basename(chemin),
                "data": base64.b64encode(f.read()).decode(),
                "type": "image/jpeg"
            })
            
    # Récupérer les prompts spécifiques à ce compte depuis la bibliothèque
    import account_library
    prompt_face, prompt_back = account_library.get_prompts(account_name)
    log(f"  [🎨 Prompts Compte] Chargement des prompts personnalisés pour '{account_name}'")

    # 3. Génération Vue FACE (avec collage des photos + prompt FACE spécifique au compte)
    if target_view in ["face", "all"]:
        generate_view_paste(page, prompt_face, face_file, fichiers_base64, "FACE")
    
    # 4. Génération Vue DOS (avec collage des photos + prompt DOS spécifique au compte)
    if target_view in ["back", "dos", "all"]:
        generate_view_paste(page, prompt_back, back_file, fichiers_base64, "DOS")
    
    # 5. Mise à jour Google Sheet uniquement si les fichiers ont bien été générés
    row_idx = row_mapping.get(sku)
    if row_idx:
        f_ok = os.path.exists(face_file) and os.path.getsize(face_file) > 1000
        b_ok = os.path.exists(back_file) and os.path.getsize(back_file) > 1000
        if f_ok and b_ok:
            update_google_sheet_status(gspread_sheet, row_idx, scrap_status="Fait scrap", image_status="Image générée")
        elif f_ok or b_ok:
            log(f"  [⚠️ Partiel] Une seule face générée pour SKU {sku}. Statut Sheet non marqué 'Image générée'.")
        else:
            log(f"  [⚠️ Échec] Aucune image générée pour SKU {sku}. Statut Sheet inchangé.")

def main():
    log("Extraction de la correspondance des lignes Google Sheet...")
    row_mapping = fetch_sku_row_mapping()
    log(f"Trouvé {len(row_mapping)} SKU(s) mappés dans Google Sheet.")

    gspread_sheet = init_gspread()
    if gspread_sheet:
        log("Connexion à Google Sheets via Service Account (gspread) réussie !")

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp("http://127.0.0.1:44231")
        context = browser.contexts[0]
        pages = [pg for pg in context.pages if "gemini.google.com" in pg.url]
        page = pages[0] if pages else context.new_page()
        page.bring_to_front()
        
        skus = sorted([d for d in os.listdir(IMAGE_BASE_DIR) if os.path.isdir(os.path.join(IMAGE_BASE_DIR, d))])
        log(f"Lancement du traitement par copier-coller pour {len(skus)} SKU(s)...")
        
        for idx, sku in enumerate(skus, 1):
            log(f"\n[{idx}/{len(skus)}] Traitement du SKU : {sku}")
            process_sku_paste(page, gspread_sheet, sku, row_mapping)
            time.sleep(2)
            
    log("\nToutes les générations HD et mises à jour Google Sheet sont terminées avec succès !")

if __name__ == "__main__":
    main()
