#!/usr/bin/env python3
"""
runner_base.py - Moteur d'exécution autonome et isolé pour navigateur CDP dédié.
Chaque runner de port s'exécute indépendamment, sans partage de port, sans verrous flock,
et sans interférence avec les autres navigateurs.
"""
import os
import sys
import time
import glob
import json
import shutil
import gspread
from google.oauth2.service_account import Credentials
from playwright.sync_api import sync_playwright

import cdp_gemini_flatlay
import telegram_notifier
import finalisation
from ai_redaction import generer_annonce

SHEET_ID = "1kCi9BodydXGye1RNy-YZX9C4jWERTKnnMVFHZclNJ4A"

def get_log_func(log_file):
    def log(msg):
        ts = time.strftime("[%Y-%m-%d %H:%M:%S]")
        line = f"{ts} {msg}"
        print(line, flush=True)
        if log_file:
            try:
                with open(log_file, "a", encoding="utf-8") as f:
                    f.write(line + "\n")
            except Exception:
                pass
    return log

def init_gspread_doc(log):
    for attempt in range(5):
        try:
            scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
            creds = Credentials.from_service_account_file("/root/shein/service_account.json", scopes=scope)
            client = gspread.authorize(creds)
            return client.open_by_key(SHEET_ID)
        except Exception as e:
            log(f"  [!] Erreur connexion Google Sheets (tentative {attempt+1}/5) : {e}")
            time.sleep(3)
    return None

def get_worksheet_case_insensitive(doc, tab_name):
    if not doc:
        return None
    clean_target = tab_name.strip().lower()
    for ws in doc.worksheets():
        if ws.title.strip().lower() == clean_target:
            return ws
    return None

def update_cell_status(ws, row_idx, col_idx, status_text, log):
    if not ws or not row_idx:
        return False
    for attempt in range(4):
        try:
            ws.update_cell(row_idx, col_idx, status_text)
            log(f"  [📊 Sheet {ws.title}] Ligne {row_idx}, Col {col_idx} -> '{status_text}'")
            return True
        except Exception as e:
            log(f"  [!] Erreur mise à jour Sheet ({e}), attente {(attempt+1)*2}s...")
            time.sleep((attempt + 1) * 2)
    return False

def get_sku_item_dir(sku, account_name):
    date_str = time.strftime("%Y-%m-%d")
    default_dir = f"/root/shein/screen_{date_str}/screen_{account_name}/{sku}"
    if os.path.exists(os.path.join(default_dir, "info.txt")):
        return default_dir
    matches = glob.glob(f"/root/shein/screen_*/screen_{account_name}/{sku}/info.txt")
    if matches:
        matches.sort(reverse=True)
        return os.path.dirname(matches[0])
    alt_matches = glob.glob(f"/root/shein/screen_*/*{account_name[:4]}*/{sku}/info.txt")
    if alt_matches:
        alt_matches.sort(reverse=True)
        return os.path.dirname(alt_matches[0])
    return default_dir

def dismiss_gemini_popups(page):
    try:
        btns = page.locator('button:has-text("Compris"), button:has-text("Accepter"), button:has-text("Got it"), button:has-text("Dismiss")')
        for i in range(btns.count()):
            if btns.nth(i).is_visible():
                btns.nth(i).click(force=True, timeout=1000)
    except Exception:
        pass

def ensure_description_text(sku, account_name, ws, row_idx, item_dir, log):
    """
    Garantit que description.txt existe et est valide.
    Génère la description si absente, sans bloquer.
    """
    out_dir = item_dir
    desc_file = os.path.join(item_dir, "description.txt")
    if not os.path.exists(desc_file):
        legacy_desc = os.path.join(item_dir, "flatlay", "description.txt")
        if os.path.exists(legacy_desc):
            desc_file = legacy_desc

    if os.path.exists(desc_file) and os.path.getsize(desc_file) > 20:
        try:
            with open(desc_file, "r", encoding="utf-8") as f:
                content = f.read()
                if "tres bon etat" in content.lower() or "très bon état" in content.lower():
                    return content
        except Exception:
            pass

    log(f"  [📝 Description] Génération du texte de rédaction pour SKU {sku} ({account_name})...")
    # Taille par défaut ou lue
    import account_library
    taille_val = account_library.get_default_size(account_name)
    
    # Prompt template
    account_prompt_path = f"/root/shein/prompts/prompt_{account_name}.txt"
    if os.path.exists(account_prompt_path):
        prompt_template_path = account_prompt_path
    else:
        prompt_template_path = "/root/shein/prompt_annonce.txt"

    success, msg, annonce_data = generer_annonce(None, sku, prompt_template_path, item_dir, taille_val, account_name=account_name)
    if not success:
        log(f"  [⚠️ Avertissement Rédaction] {msg}")
        return ""

    infos = finalisation.lire_info(item_dir)
    if not infos.get("prix_achat"):
        infos["prix_achat"] = 12.0

    out_desc_path = finalisation.ecrire_description(out_dir, annonce_data, infos, taille_val, sku, debug=False)
    if out_desc_path and os.path.exists(out_desc_path):
        with open(out_desc_path, "r", encoding="utf-8") as f:
            content = f.read()
        if ws and row_idx:
            update_cell_status(ws, row_idx, 4, "Rédaction fait", log)
        return content
    return ""

def process_single_sku(gemini_page, ws, sku, row_idx, account_name, log):
    """
    Traite un SKU complet sur le navigateur dédié :
    1. Vérifie si scraping est présent
    2. Génère Flatlay Face & Dos sur Gemini
    3. Valide description
    4. Synchronise Google Drive
    5. Notifie Telegram (SEULEMENT sur succès complet, zéro spam sur échec)
    """
    # Fichiers directement à la racine de {sku}
    face_file = os.path.join(item_dir, "flatlay_face.png")
    back_file = os.path.join(item_dir, "flatlay_back.png")
    desc_file = os.path.join(item_dir, "description.txt")

    # Fallback compatibilité anciens sous-dossiers
    if not os.path.exists(face_file):
        legacy_face = os.path.join(item_dir, "flatlay", "flatlay_face.png")
        if os.path.exists(legacy_face): face_file = legacy_face
    if not os.path.exists(back_file):
        legacy_back = os.path.join(item_dir, "flatlay", "flatlay_back.png")
        if os.path.exists(legacy_back): back_file = legacy_back
    if not os.path.exists(desc_file):
        legacy_desc = os.path.join(item_dir, "flatlay", "description.txt")
        if os.path.exists(legacy_desc): desc_file = legacy_desc

    face_exists = os.path.exists(face_file) and os.path.getsize(face_file) > 1000
    back_exists = os.path.exists(back_file) and os.path.getsize(back_file) > 1000

    if face_exists and back_exists:
        log(f"  [✓] SKU {sku} a déjà ses images Flat-Lay (Face & Dos).")
        update_cell_status(ws, row_idx, 3, "Image générée", log)
        return True

    # Vérification photos sources directement dans item_dir (ou secours dans image-screen)
    photos = [f for f in os.listdir(item_dir) if f.startswith("photo_") and f.endswith(".jpg")]
    if not photos:
        screen_dir = os.path.join(item_dir, "image-screen")
        if os.path.exists(screen_dir):
            photos = [f for f in os.listdir(screen_dir) if f.startswith("photo_") and f.endswith(".jpg")]

    if not photos or not os.path.exists(os.path.join(item_dir, "info.txt")):
        log(f"  [⏳ Scraping requis] Photos sources manquantes pour {sku}.")
        import socket
        s = socket.socket()
        s.settimeout(0.5)
        res = s.connect_ex(('127.0.0.1', 44231))
        s.close()
        if res == 0:
            log(f"  [Scraping] Lancement scraper sur port 44231 pour {sku}...")
            os.system(f"/root/venv/bin/python /root/shein/scraper.py 44231 {sku} '{item_dir}' > /dev/null 2>&1")
            if os.path.exists(os.path.join(item_dir, "info.txt")):
                update_cell_status(ws, row_idx, 2, "Fait scrap", log)
                if os.path.exists(screen_dir):
                    photos = [f for f in os.listdir(screen_dir) if f.startswith("photo_") and f.endswith(".jpg")]
        if not photos or not os.path.exists(os.path.join(item_dir, "info.txt")):
            log(f"  [ℹ️ Ignoré] SKU {sku} ({account_name}) non scrapé. Zéro spam Telegram.")
            return False

    # Détermination de la vue à générer
    if not face_exists and not back_exists:
        target_view = "all"
    elif not face_exists:
        target_view = "face"
    else:
        target_view = "back"

    log(f"  [🎨 Gemini Flat-Lay] Démarrage génération vue '{target_view}' pour SKU {sku} ({account_name})...")
    dismiss_gemini_popups(gemini_page)

    row_mapping = {sku: row_idx}
    try:
        cdp_gemini_flatlay.process_sku_paste(gemini_page, ws, sku, row_mapping, target_view=target_view)
    except Exception as e_gem:
        log(f"  [⚠️ Erreur exécution Gemini] ({e_gem})")

    # Re-vérification des images générées
    face_ok = os.path.exists(face_file) and os.path.getsize(face_file) > 1000
    back_ok = os.path.exists(back_file) and os.path.getsize(back_file) > 1000

    if face_ok and back_ok:
        log(f"  [✅ IMAGES VALIDES] Flat-Lay Face & Dos confirmés pour SKU {sku} !")
        update_cell_status(ws, row_idx, 3, "Image générée", log)

        # Vérification / génération de la description
        desc_text = ""
        if os.path.exists(desc_file) and os.path.getsize(desc_file) > 20:
            try:
                with open(desc_file, "r", encoding="utf-8") as f:
                    desc_text = f.read()
            except Exception:
                pass
        if not desc_text:
            desc_text = ensure_description_text(sku, account_name, ws, row_idx, item_dir, log)

        # Synchronisation Google Drive
        log(f"  [☁️ Drive] Synchronisation rapide SKU {sku}...")
        os.system(f"/root/venv/bin/python /root/shein/upload_to_gdrive.py --sku {sku} --account '{account_name}'")

        # Notification Telegram EXCLUSIVEMENT sur succès
        photo_paths = [face_file, back_file]
        log(f"  [📱 Telegram] Envoi du groupe de médias et de la fiche de révision...")
        telegram_notifier.send_telegram_media_group(photo_paths, account_name=account_name)
        telegram_notifier.send_telegram_review_message(sku, account_name, desc_text, phase=3)

        log(f"  [🎉 SUCCÈS COMPLET] SKU {sku} ({account_name}) finalisé et expédié !")
        return True
    else:
        try:
            if cdp_gemini_flatlay.check_gemini_quota(gemini_page):
                q_info = cdp_gemini_flatlay.get_gemini_quota_info(gemini_page) or "Limite d'images atteinte"
                log(f"  [⏳ Quota Actif] {q_info} | Pause intelligente de 120s...")
                time.sleep(120)
        except Exception:
            pass
        log(f"  [⚠️ Échec temporaire Image] SKU {sku} ({account_name}) - sera retenté au prochain tour. Zéro spam Telegram.")
        return False

def get_or_recreate_gemini_page(context, current_page, log):
    """
    Vérifie la réactivité de l'onglet Gemini. Si l'onglet est fermé ou a crashé,
    le réinitialise proprement.
    """
    if current_page:
        try:
            if not current_page.is_closed():
                current_page.evaluate("1 + 1")
                return current_page
        except Exception:
            try: current_page.close()
            except Exception: pass

    log("  [🔄 Récupération Navigateur] Réouverture d'un onglet Gemini sain...")
    gemini_page = context.new_page()
    try:
        gemini_page.goto("https://gemini.google.com/app?hl=fr", wait_until="domcontentloaded", timeout=35000)
    except Exception as e:
        log(f"  [⚠️ Navigation initiale] ({e})")
    gemini_page.bring_to_front()
    dismiss_gemini_popups(gemini_page)
    return gemini_page

def run_dedicated_browser_runner(port, tabs, log_file):
    """
    Boucle principale permanente d'un runner dédié à son port CDP.
    Gère la reconnexion automatique en cas de coupure navigateur.
    """
    log = get_log_func(log_file)
    log("=" * 65)
    log(f"🚀 DÉMARRAGE RUNNER DÉDIÉ - PORT {port}")
    log(f"   Onglets assignés : {', '.join(tabs)}")
    log("   Isolation totale : AUCUN emprunt de port, AUCUN verrou partagé.")
    log("=" * 65)

    while True:
        try:
            log(f"🌐 [CDP {port}] Connexion Playwright à http://127.0.0.1:{port}...")
            with sync_playwright() as p:
                browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{port}", timeout=30000)
                context = browser.contexts[0]

                # Recherche ou ouverture initiale de l'onglet Gemini
                gemini_pages = [pg for pg in context.pages if "gemini.google.com" in pg.url]
                if gemini_pages:
                    gemini_page = gemini_pages[0]
                    log(f"  [✓] Onglet Gemini existant réutilisé : {gemini_page.url}")
                else:
                    gemini_page = context.new_page()
                    log("  [+] Ouverture d'un nouvel onglet Gemini...")
                    gemini_page.goto("https://gemini.google.com/app?hl=fr", wait_until="domcontentloaded", timeout=25000)

                gemini_page.bring_to_front()
                dismiss_gemini_popups(gemini_page)

                # Connexion Google Sheets
                doc = init_gspread_doc(log)
                if not doc:
                    log("  [❌] Impossible d'ouvrir Google Sheets. Attente 15s...")
                    time.sleep(15)
                    continue

                # Boucle de surveillance permanente sur les onglets assignés
                cycle_count = 0
                sku_since_page_refresh = 0

                while True:
                    cycle_count += 1
                    total_processed = 0
                    total_pending = 0

                    for tab_name in tabs:
                        ws = get_worksheet_case_insensitive(doc, tab_name)
                        if not ws:
                            log(f"  [!] Onglet '{tab_name}' introuvable dans le Google Sheet.")
                            continue

                        account_name = ws.title.strip()
                        log(f"\n📂 [Onglet {account_name}] Examen des lignes...")

                        try:
                            rows = ws.get_all_values()
                        except Exception as e_get:
                            log(f"  [!] Erreur lecture lignes ({e_get}). Réouverture doc...")
                            doc = init_gspread_doc(log)
                            continue

                        if len(rows) <= 1:
                            log(f"  [i] Onglet '{account_name}' vide ou seulement en-tête.")
                            continue

                        # Parcourir chaque SKU de l'onglet
                        for row_idx, r in enumerate(rows[1:], start=2):
                            if not r or not r[0].strip():
                                continue
                            sku = r[0].strip()

                            val_c = r[2].strip() if len(r) > 2 else ""
                            item_dir = get_sku_item_dir(sku, account_name)
                            face_f = os.path.join(item_dir, "flatlay_face.png")
                            if not os.path.exists(face_f):
                                face_f = os.path.join(item_dir, "flatlay", "flatlay_face.png")
                            back_f = os.path.join(item_dir, "flatlay_back.png")
                            if not os.path.exists(back_f):
                                back_f = os.path.join(item_dir, "flatlay", "flatlay_back.png")
                            has_images = (os.path.exists(face_f) and os.path.getsize(face_f) > 1000 and
                                          os.path.exists(back_f) and os.path.getsize(back_f) > 1000)

                            if val_c == "Image générée" and has_images:
                                continue

                            total_pending += 1
                            log(f"\n--- [⚡ Traitement] SKU: {sku} | Onglet: {account_name} | Ligne: {row_idx} ---")

                            # Prophylaxie mémoire : recycler l'onglet Gemini tous les 12 SKUs pour éviter les crashs V8
                            if sku_since_page_refresh >= 12:
                                log("  [🧹 Nettoyage V8] Recyclage de l'onglet Gemini pour libérer la mémoire...")
                                try: gemini_page.close()
                                except Exception: pass
                                gemini_page = None
                                sku_since_page_refresh = 0

                            # S'assurer que gemini_page est valide et vivant
                            gemini_page = get_or_recreate_gemini_page(context, gemini_page, log)
                            
                            try:
                                ok = process_single_sku(gemini_page, ws, sku, row_idx, account_name, log)
                            except Exception as e_proc:
                                log(f"  [⚠️ Erreur SKU {sku}] ({e_proc})")
                                ok = False
                                if any(k in str(e_proc).lower() for k in ["crash", "closed", "destroy"]):
                                    try: gemini_page.close()
                                    except Exception: pass
                                    gemini_page = None

                            if ok:
                                total_processed += 1
                                sku_since_page_refresh += 1
                            
                            # Pause courte entre chaque SKU pour laisser respirer le navigateur
                            time.sleep(2)

                    log(f"\n📊 [Surveillance Port {port}] Cycle #{cycle_count} terminé. Traités ce cycle : {total_processed} | En attente : {total_pending}")
                    if total_pending == 0:
                        log(f"🎉 [Port {port}] Tous les SKUs des onglets {tabs} sont 100% finalisés !")
                        log(f"   Mode veille active (vérification de nouveaux SKUs toutes les 60s)...")
                        time.sleep(60)
                    else:
                        log(f"   Pause de 20s avant la prochaine passe de génération...")
                        time.sleep(20)

        except Exception as e_main:
            log(f"⚠️ [Exception Port {port}] Perte de session ou crash : {e_main}")
            log("   Tentative de reconnexion automatique dans 5 secondes...")
            time.sleep(5)
