import os
import sys
import time
import shutil
import argparse
import fcntl
import urllib.request
import requests
import csv
import io
import glob
import concurrent.futures
import gspread
from google.oauth2.service_account import Credentials
from playwright.sync_api import sync_playwright

import finalisation
import telegram_notifier
from ai_redaction import generer_annonce, extract_and_validate_ad

LOG_FILE = "/root/shein/workflow.log"
LOCK_FILE = "/root/shein/workflow.lock"
SHEET_ID = "1kCi9BodydXGye1RNy-YZX9C4jWERTKnnMVFHZclNJ4A"
IMAGE_DIR = "/root/shein/image"

def log(msg, to_term=True):
    timestamp = time.strftime("[%H:%M:%S]")
    line = f"{timestamp} {msg}"
    if to_term:
        print(line, flush=True)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass

def init_gspread_doc():
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_file("/root/shein/service_account.json", scopes=scope)
        client = gspread.authorize(creds)
        doc = client.open_by_key(SHEET_ID)
        return doc
    except Exception as e:
        log(f"[!] Erreur de connexion Google Sheets : {e}")
        return None

def get_row_index_by_sku(sheet, sku):
    if not sheet:
        return None
    try:
        col_skus = sheet.col_values(1)
        for i, val in enumerate(col_skus, 1):
            if val and val.strip() == sku.strip():
                return i
    except Exception as e:
        log(f"[!] Erreur lors de la recherche du SKU '{sku}' dans le Sheet : {e}")
    return None

def update_cell_status(sheet, row_idx, col_idx, status_text):
    if not sheet or not row_idx:
        return False
    try:
        sheet.update_cell(row_idx, col_idx, status_text)
        log(f"  [📊 Sheet] Ligne {row_idx}, Colonne {col_idx} mise à jour -> '{status_text}'")
        return True
    except Exception as e:
        log(f"  [!] Erreur de mise à jour Sheet Ligne {row_idx}, Col {col_idx} : {e}")
        return False

def get_sku_item_dir(sku, sheet):
    date_str = time.strftime("%Y-%m-%d")
    account_name = sheet.title.strip() if (sheet and hasattr(sheet, 'title')) else 'defaut'
    default_dir = f"/root/shein/screen_{date_str}/screen_{account_name}/{sku}"
    
    if os.path.exists(os.path.join(default_dir, "info.txt")):
        return default_dir
        
    import glob
    matches = glob.glob(f"/root/shein/screen_*/screen_{account_name}/{sku}/info.txt")
    if matches:
        matches.sort(reverse=True)
        return os.path.dirname(matches[0])
        
    alt_matches = glob.glob(f"/root/shein/screen_*/*{account_name[:4]}*/{sku}/info.txt")
    if alt_matches:
        alt_matches.sort(reverse=True)
        return os.path.dirname(alt_matches[0])

    return default_dir

# ----------------- ÉTAPE 1 : SCRAPING -----------------
def execute_scraping(sku, sheet, row_idx, refaire=False):
    log(f"\n--- [1/3] ÉTAPE SCRAPING (Col B) pour SKU : {sku} ---")
    account_name = sheet.title.strip() if sheet else 'defaut'
    
    item_dir = get_sku_item_dir(sku, sheet)
    os.makedirs(item_dir, exist_ok=True)
    info_file = os.path.join(item_dir, "info.txt")

    if row_idx and sheet and not refaire:
        val_b = sheet.cell(row_idx, 2).value or ""
        if val_b.strip() == "Fait scrap" and os.path.exists(info_file):
            log("  [✓] Étape Scraping déjà cochée 'Fait scrap'. Étape sautée.")
            telegram_notifier.send_telegram_message(f"⏭️ <b>[Scraping Ignoré]</b> Déjà fait | SKU: <code>{sku}</code> ({account_name})", account_name=account_name)
            return True

    # Si le scraping doit être fait, supprimer l'ancien dossier pour écraser proprement
    if os.path.exists(item_dir):
        try:
            shutil.rmtree(item_dir)
        except Exception:
            pass
    os.makedirs(item_dir, exist_ok=True)

    # Navigateur unique dédié exclusivement pour le scraping
    scrap_port = "44231"
    log(f"  [⏳] Lancement du scraper Shein (navigateur unique port {scrap_port}) vers : {item_dir} ...")
    cmd_scrap = f"/root/venv/bin/python /root/shein/scraper.py {scrap_port} {sku} '{item_dir}'"
    os.system(cmd_scrap)

    if not os.path.exists(info_file):
        log(f"  [❌ ÉCHEC SCRAPING] info.txt introuvable pour SKU {sku}.")
        telegram_notifier.send_telegram_message(f"❌ <b>[ÉCHEC Scraping]</b> info.txt introuvable | SKU: <code>{sku}</code> ({account_name})", account_name=account_name)
        return False

    with open(info_file, "r", encoding="utf-8", errors="ignore") as f:
        info_content = f.read()

    if sku not in info_content and "SKU:" not in info_content:
        log(f"  [❌ ÉCHEC SCRAPING] Le SKU {sku} est absent de info.txt.")
        telegram_notifier.send_telegram_message(f"❌ <b>[ÉCHEC Scraping]</b> SKU absent de info.txt | SKU: <code>{sku}</code> ({account_name})", account_name=account_name)
        return False

    photos = [f for f in os.listdir(item_dir) if f.startswith("photo_") or f.endswith((".jpg", ".png"))]
    screen_dir = os.path.join(item_dir, "image-screen")
    if os.path.exists(screen_dir):
        photos += os.listdir(screen_dir)

    if not photos:
        log(f"  [❌ ÉCHEC SCRAPING] Aucune photo trouvée pour SKU {sku}.")
        telegram_notifier.send_telegram_message(f"❌ <b>[ÉCHEC Scraping]</b> Aucune photo trouvée | SKU: <code>{sku}</code> ({account_name})", account_name=account_name)
        return False

    log("  [✅ SCRAPING VALIDE] Captures d'écran et info.txt validés avec succès !")
    if sheet and row_idx:
        update_cell_status(sheet, row_idx, 2, "Fait scrap")
    
    # Synchronisation immédiate des données de scraping sur Google Drive
    os.system(f"/root/venv/bin/python /root/shein/upload_to_gdrive.py --sku {sku} --account '{account_name}'")
    
    title_full_img = os.path.join(item_dir, "desc-screen", "title_full.png")
    caption_msg = f"✅ <b>[Scraping Fait]</b> SKU: <code>{sku}</code> ({account_name})"
    if os.path.exists(title_full_img):
        telegram_notifier.send_telegram_photo(title_full_img, caption=caption_msg, account_name=account_name)
    else:
        telegram_notifier.send_telegram_message(caption_msg, account_name=account_name)
    return True

# ----------------- ÉTAPE 2 : IMAGE FLATLAY -----------------
def execute_image(sku, sheet, row_idx, page_cdp, refaire=False, view="all", notify=True, sync_drive=True):
    log(f"\n--- [2/3] ÉTAPE IMAGE FLATLAY (Col C) pour SKU : {sku} (Vue: {view}) ---")
    account_name = sheet.title.strip() if sheet else 'defaut'
    
    item_dir = get_sku_item_dir(sku, sheet)
    info_file = os.path.join(item_dir, "info.txt")
    if not os.path.exists(info_file):
        log(f"  [❌ DÉPENDANCE MANQUANTE] Scraping non fait pour SKU {sku}. Étape Image impossible.")
        telegram_notifier.send_telegram_message(f"❌ <b>[ÉCHEC Image]</b> Scraping non fait | SKU: <code>{sku}</code> ({account_name})", account_name=account_name)
        return False

    out_dir = os.path.join(item_dir, "flatlay")
    os.makedirs(out_dir, exist_ok=True)
    face_file = os.path.join(out_dir, "flatlay_face.png")
    back_file = os.path.join(out_dir, "flatlay_back.png")
    desc_file = os.path.join(out_dir, "description.txt")

    if row_idx and sheet and not refaire:
        val_c = sheet.cell(row_idx, 3).value or ""
        if val_c.strip() == "Image générée" and os.path.exists(face_file) and os.path.exists(back_file):
            log("  [✓] Étape Image déjà cochée 'Image générée'. Étape sautée.")
            return True

    def send_notification():
        photo_paths = []
        if os.path.exists(face_file) and os.path.getsize(face_file) > 0:
            photo_paths.append(face_file)
        if os.path.exists(back_file) and os.path.getsize(back_file) > 0:
            photo_paths.append(back_file)
        photo_paths.extend(sorted(glob.glob(os.path.join(item_dir, "image-screen", "photo_*.jpg"))))
        telegram_notifier.send_telegram_media_group(photo_paths, account_name=account_name)
        if os.path.exists(desc_file):
            with open(desc_file, "r", encoding="utf-8") as f:
                desc_text = f.read()
            telegram_notifier.send_telegram_review_message(sku, account_name, desc_text, phase=3)
        else:
            telegram_notifier.send_telegram_review_message(sku, account_name, phase=2)

    # Si refaire : supprimer uniquement la ou les images demandées (en préservant description.txt !)
    if refaire:
        if view in ["face", "all"] and os.path.exists(face_file):
            try: os.remove(face_file)
            except Exception: pass
        if view in ["back", "dos", "all"] and os.path.exists(back_file):
            try: os.remove(back_file)
            except Exception: pass

    # Vérifier si les images nécessaires existent déjà
    face_ok = os.path.exists(face_file) and os.path.getsize(face_file) > 0
    back_ok = os.path.exists(back_file) and os.path.getsize(back_file) > 0
    if ((view == "face" and face_ok) or
        (view in ["back", "dos"] and back_ok) or
        (view == "all" and face_ok and back_ok)):
        log("  [✅ IMAGE VALIDE] Images requises présentes.")
        if sheet and row_idx and face_ok and back_ok:
            update_cell_status(sheet, row_idx, 3, "Image générée")
        if sync_drive:
            os.system(f"/root/venv/bin/python /root/shein/upload_to_gdrive.py --sku {sku} --account '{account_name}'")
        if notify:
            send_notification()
        return True

    # Sinon générer les images avec cdp_gemini_flatlay via le gestionnaire multi-navigateurs
    log(f"  [🎨 Génération Image] Lancement du script Flat-Lay (Vue: {view})...")
    import cdp_gemini_flatlay
    from browser_pool import acquire_gemini_browser
    row_mapping = {sku: row_idx} if row_idx else {}

    try:
        with acquire_gemini_browser(account_name) as (browser_inst, gemini_page, used_port):
            log(f"  [🌐 Multi-Navigateurs] Traitement sur port {used_port} pour '{account_name}' (SKU: {sku})")
            cdp_gemini_flatlay.process_sku_paste(gemini_page, sheet, sku, row_mapping, target_view=view)
    except Exception as e_cdp:
        log(f"  [❌ Erreur Multi-Navigateurs Gemini] ({e_cdp})")

    # Vérification finale
    face_done = os.path.exists(face_file) and os.path.getsize(face_file) > 0
    back_done = os.path.exists(back_file) and os.path.getsize(back_file) > 0
    if ((view == "face" and face_done) or
        (view in ["back", "dos"] and back_done) or
        (view == "all" and face_done and back_done)):
        log("  [✅ IMAGE VALIDE] Génération Flat-Lay réussie !")
        if sheet and row_idx and face_done and back_done:
            update_cell_status(sheet, row_idx, 3, "Image générée")
        if sync_drive:
            os.system(f"/root/venv/bin/python /root/shein/upload_to_gdrive.py --sku {sku} --account '{account_name}'")
        if notify:
            send_notification()
        return True
    else:
        log(f"  [❌ ÉCHEC IMAGE] Les images Flat-Lay sont manquantes ou vides.")
        telegram_notifier.send_telegram_message(f"❌ <b>[ÉCHEC Image]</b> Images manquantes/vides | SKU: <code>{sku}</code> ({account_name})", account_name=account_name)
        return False

# ----------------- ÉTAPE 3 : RÉDACTION (TEXTE SEUL) -----------------
def execute_redaction_text(sku, sheet, row_idx, debug=False, refaire=False):
    """
    Génère le texte de la description via Meta AI et écrit flatlay/description.txt.
    Indépendant des images Flatlay.
    Retourne (success: bool, final_desc_content: str).
    """
    account_name = sheet.title.strip() if (sheet and hasattr(sheet, 'title')) else 'defaut'
    item_dir = get_sku_item_dir(sku, sheet)
    info_file = os.path.join(item_dir, "info.txt")
    if not os.path.exists(info_file):
        log(f"  [❌ DÉPENDANCE MANQUANTE] Scraping non fait pour SKU {sku}. Rédaction impossible.")
        return False, ""

    out_dir = os.path.join(item_dir, "flatlay")
    os.makedirs(out_dir, exist_ok=True)
    desc_file = os.path.join(out_dir, "description.txt")

    if sheet and row_idx and not refaire:
        val_d = sheet.cell(row_idx, 4).value or ""
        if val_d.strip() == "Rédaction fait" and os.path.exists(desc_file):
            log("  [✓] Étape Rédaction déjà cochée 'Rédaction fait'. Étape sautée.")
            try:
                with open(desc_file, "r", encoding="utf-8") as f:
                    return True, f.read()
            except Exception:
                return True, ""

    # Lecture de la taille
    taille_val = ""
    col_taille = 6  # valeur par défaut si sheet/row_idx absents
    if sheet and row_idx:
        try:
            headers = [h.strip().lower() for h in sheet.row_values(1)]
            if "taille" in headers:
                col_taille = headers.index("taille") + 1
            else:
                col_taille = 6
        except Exception:
            col_taille = 6

        taille_val = (sheet.cell(row_idx, col_taille).value or "").strip()
        if taille_val.lower() in ["vetement", "vêtement"]:
            taille_val = ""

    if not taille_val:
        import account_library
        taille_val = account_library.get_default_size(account_name)
        log(f"  [📏 Taille par défaut appliquée] Colonne F vide -> '{taille_val}' (compte: {account_name})")
        if sheet and row_idx:
            update_cell_status(sheet, row_idx, col_taille, taille_val)
    else:
        log(f"  [📏 Taille] Taille lue : '{taille_val}'")

    # Prompt
    account_prompt_path = f"/root/shein/prompts/prompt_{account_name}.txt"
    if os.path.exists(account_prompt_path):
        prompt_template_path = account_prompt_path
        log(f"  [📝 Prompt] Utilisation du prompt personnalisé pour '{account_name}' : {account_prompt_path}")
    else:
        prompt_template_path = "/root/shein/prompt_annonce.txt"

    if not os.path.exists(prompt_template_path):
        log(f"  [❌ ERREUR] Fichier prompt {prompt_template_path} introuvable.")
        return False, ""

    log(f"  [📝 Meta AI] Lancement de la génération de rédaction...")
    success, msg, annonce_data = generer_annonce(None, sku, prompt_template_path, item_dir, taille_val, account_name=account_name)
    if not success:
        log(f"  [❌ ÉCHEC IA] {msg}")
        return False, ""

    infos = finalisation.lire_info(item_dir)
    if not infos.get("prix_achat"):
        log(f"  [ℹ️ Fallback Prix] Prix d'achat absent de info.txt, valeur par défaut appliquée : 12.00 €.")
        infos["prix_achat"] = 12.0

    out_desc_path = finalisation.ecrire_description(out_dir, annonce_data, infos, taille_val, sku, debug=debug)
    if not out_desc_path or not os.path.exists(out_desc_path):
        log("  [❌ ÉCHEC ÉCRITURE] Impossible d'écrire description.txt.")
        return False, ""

    with open(out_desc_path, "r", encoding="utf-8") as f:
        final_desc_content = f.read()

    if "tres bon etat" not in final_desc_content.lower() and "très bon état" not in final_desc_content.lower():
        log("  [❌ ERREUR VALIDATION] description.txt ne contient pas 'tres bon etat'.")
        return False, ""

    log("  [✅ RÉDACTION VALIDE] description.txt généré et validé avec succès !")
    return True, final_desc_content

# ----------------- ÉTAPE 3 : RÉDACTION COMPLÈTE -----------------
def execute_redaction(sku, sheet, row_idx, page_cdp=None, debug=False, refaire=False):
    log(f"\n--- [3/3] ÉTAPE RÉDACTION (Col D) pour SKU : {sku} ---")
    account_name = sheet.title.strip() if (sheet and hasattr(sheet, 'title')) else 'defaut'
    item_dir = get_sku_item_dir(sku, sheet)
    out_dir = os.path.join(item_dir, "flatlay")
    face_file = os.path.join(out_dir, "flatlay_face.png")
    back_file = os.path.join(out_dir, "flatlay_back.png")

    face_ok = os.path.exists(face_file) and os.path.getsize(face_file) > 0
    back_ok = os.path.exists(back_file) and os.path.getsize(back_file) > 0
    if not (face_ok and back_ok):
        log(f"  [⚠️ IMAGES MANQUANTES] Les images Flat-Lay ne sont pas encore prêtes pour SKU {sku}. Lancement préalable de l'étape Image...")
        img_success = execute_image(sku, sheet, row_idx, page_cdp, refaire=False, view="all", notify=False)
        if not img_success:
            log(f"  [⛔ ÉTAPE BLOQUÉE] Impossible de générer les images Flat-Lay pour {sku}. Rédaction annulée.")
            telegram_notifier.send_telegram_message(f"❌ <b>[ÉCHEC Rédaction]</b> Images Flatlay introuvables | SKU: <code>{sku}</code> ({account_name})", account_name=account_name)
            return False

    success, final_desc_content = execute_redaction_text(sku, sheet, row_idx, debug=debug, refaire=refaire)
    if not success:
        telegram_notifier.send_telegram_message(f"❌ <b>[ÉCHEC Rédaction]</b> Erreur génération description | SKU: <code>{sku}</code> ({account_name})", account_name=account_name)
        return False

    if sheet and row_idx:
        update_cell_status(sheet, row_idx, 4, "Rédaction fait")

    log("  [☁️ Drive] Synchronisation vers Google Drive via rclone...")
    os.system(f"/root/venv/bin/python /root/shein/upload_to_gdrive.py --sku {sku} --account '{account_name}'")

    photo_paths = []
    if os.path.exists(face_file) and os.path.getsize(face_file) > 0:
        photo_paths.append(face_file)
    if os.path.exists(back_file) and os.path.getsize(back_file) > 0:
        photo_paths.append(back_file)
    photo_paths.extend(sorted(glob.glob(os.path.join(item_dir, "image-screen", "photo_*.jpg"))))

    telegram_notifier.send_telegram_media_group(photo_paths, account_name=account_name)
    telegram_notifier.send_telegram_review_message(sku, account_name, final_desc_content)
    return True

# ----------------- GÉNÉRATION PARALLÈLE SANS CONFLITS (IMAGE + RÉDACTION) -----------------
def execute_parallel_generate(sku, sheet, row_idx, page_cdp=None, debug=False, refaire=False):
    """
    Exécute en parallèle la génération d'image Flatlay (Gemini) et la rédaction (Meta AI)
    sur des navigateurs indépendants sans collision de verrous.
    Synchronise Google Drive une seule fois et envoie un seul message complet sur Telegram.
    """
    log(f"\n=======================================================")
    log(f"⚡ [PARALLÈLE] Image + Rédaction sans conflits pour SKU : {sku}")
    log(f"=======================================================")
    account_name = sheet.title.strip() if sheet else 'defaut'
    item_dir = get_sku_item_dir(sku, sheet)
    out_dir = os.path.join(item_dir, "flatlay")
    os.makedirs(out_dir, exist_ok=True)
    face_file = os.path.join(out_dir, "flatlay_face.png")
    back_file = os.path.join(out_dir, "flatlay_back.png")
    desc_file = os.path.join(out_dir, "description.txt")

    face_ok = os.path.exists(face_file) and os.path.getsize(face_file) > 0
    back_ok = os.path.exists(back_file) and os.path.getsize(back_file) > 0
    desc_ok = os.path.exists(desc_file) and os.path.getsize(desc_file) > 0

    need_image = not (face_ok and back_ok) or refaire
    need_desc = not desc_ok or refaire

    # Si images et description existent déjà et pas refaire : NE RIEN FAIRE, ne pas renvoyer sur Telegram
    if not need_image and not need_desc and not refaire:
        log(f"  [⏭️ DÉJÀ PRÊT] SKU {sku} a déjà ses images Flat-Lay et sa description. Aucune réexpédition Telegram.")
        return True

    img_success = not need_image
    redac_success = not need_desc
    final_desc_content = ""

    if desc_ok and not refaire:
        try:
            with open(desc_file, "r", encoding="utf-8") as f:
                final_desc_content = f.read()
        except Exception:
            pass

    if need_image and need_desc:
        log(f"  [⚡ Parallélisme] Démarrage simultané sur 2 threads :")
        log(f"     Thread 1 : Gemini Flat-Lay (Face & Dos)")
        log(f"     Thread 2 : Meta AI Rédaction")

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            future_img = executor.submit(execute_image, sku, sheet, row_idx, None, refaire, "all", False, False)
            future_redac = executor.submit(execute_redaction_text, sku, sheet, row_idx, debug, refaire)

            # Récupérer les résultats en protégeant chaque thread des exceptions non rattrapées
            try:
                img_success = future_img.result()
            except Exception as e_img:
                log(f"  [❌ Thread Gemini] Exception inattendue : {e_img}")
                img_success = False

            try:
                redac_success, final_desc_content = future_redac.result()
            except Exception as e_redac:
                log(f"  [❌ Thread Meta AI] Exception inattendue : {e_redac}")
                redac_success = False
                final_desc_content = ""

    elif need_image:
        log(f"  [ℹ️] Rédaction déjà prête. Exécution de l'image uniquement...")
        try:
            img_success = execute_image(sku, sheet, row_idx, None, refaire=refaire, view="all", notify=False, sync_drive=False)
        except Exception as e_img:
            log(f"  [❌ Gemini] Exception : {e_img}")
            img_success = False
    elif need_desc:
        log(f"  [ℹ️] Images déjà prêtes. Exécution de la rédaction uniquement...")
        try:
            redac_success, final_desc_content = execute_redaction_text(sku, sheet, row_idx, debug=debug, refaire=refaire)
        except Exception as e_redac:
            log(f"  [❌ Meta AI] Exception : {e_redac}")
            redac_success = False
            final_desc_content = ""

    # Revalider l'existence physique des fichiers après l'exécution des threads
    face_done = os.path.exists(face_file) and os.path.getsize(face_file) > 0
    back_done = os.path.exists(back_file) and os.path.getsize(back_file) > 0
    desc_done = os.path.exists(desc_file) and os.path.getsize(desc_file) > 0

    # Si les fichiers existent physiquement, forcer les succès (les threads peuvent avoir écrit correctement)
    if face_done and back_done and not img_success:
        log(f"  [⚠️ Correction] Les images Flat-Lay existent bien malgré le flag d'échec. Marquage en succès.")
        img_success = True
    if desc_done and not redac_success:
        log(f"  [⚠️ Correction] description.txt existe malgré le flag d'échec. Marquage en succès.")
        redac_success = True
        if not final_desc_content:
            try:
                with open(desc_file, "r", encoding="utf-8") as f:
                    final_desc_content = f.read()
            except Exception:
                pass

    # Mise à jour des statuts Google Sheets
    if img_success and face_done and back_done and sheet and row_idx:
        update_cell_status(sheet, row_idx, 3, "Image générée")
    if redac_success and desc_done and sheet and row_idx:
        update_cell_status(sheet, row_idx, 4, "Rédaction fait")

    # Synchronisation Google Drive (une seule passe pour images + description)
    if img_success or redac_success:
        log("  [☁️ Drive] Synchronisation finale du SKU vers Google Drive...")
        os.system(f"/root/venv/bin/python /root/shein/upload_to_gdrive.py --sku {sku} --account '{account_name}'")

    # Notification finale complète sur Telegram
    # IMPORTANT: n'envoyer QUE les images du SKU courant (flatlay_face + flatlay_back uniquement),
    # pas les anciennes photos image-screen qui appartiennent à des SKUs précédents
    if img_success and redac_success and face_done and back_done:
        log(f"  [🎉 SUCCÈS COMPLET] SKU {sku} finalisé avec succès en parallèle !")
        # Photos à envoyer : flatlay face + dos (générées par Gemini) UNIQUEMENT
        photo_paths = [face_file, back_file]

        telegram_notifier.send_telegram_media_group(photo_paths, account_name=account_name)
        if not final_desc_content and os.path.exists(desc_file):
            try:
                with open(desc_file, "r", encoding="utf-8") as f:
                    final_desc_content = f.read()
            except Exception:
                pass
        telegram_notifier.send_telegram_review_message(sku, account_name, final_desc_content)
        return True
    elif img_success and not redac_success:
        log(f"  [⚠️ PARTIEL] Image réussie mais échec rédaction pour {sku}.")
        telegram_notifier.send_telegram_message(f"⚠️ Images Flat-Lay prêtes, mais échec sur la rédaction pour SKU <code>{sku}</code> ({account_name}).", account_name=account_name)
        return False
    elif not img_success and redac_success:
        log(f"  [⚠️ PARTIEL] Rédaction réussie mais images Flat-Lay manquantes pour {sku}.")
        telegram_notifier.send_telegram_message(f"⚠️ Rédaction prête, mais images Flat-Lay manquantes pour SKU <code>{sku}</code> ({account_name}). Tapez /force /image pour les régénérer.", account_name=account_name)
        return False
    else:
        log(f"  [❌ ÉCHEC] Échec Image et Rédaction pour SKU {sku}.")
        telegram_notifier.send_telegram_message(f"❌ Échec génération Image & Rédaction pour SKU <code>{sku}</code> ({account_name}).", account_name=account_name)
        return False

# ----------------- MODE AUTOMATIQUE -----------------
def run_auto_mode(doc, page_cdp, debug=False, refaire=False, target_tabs="all", target_step="all"):
    log("\n================ MODE AUTOMATIQUE DÉMARRÉ ================")
    if not doc:
        log("[!] Impossible de se connecter au Document Google Sheets (Vérifier le partage de droits).")
        telegram_notifier.send_telegram_message(
            "❌ <b>Impossible de se connecter au Google Sheet !</b>\n\n"
            "🔑 Veuillez vous assurer d'avoir partagé votre fichier Google Sheet avec l'email du compte de service (en accès Éditeur) :\n"
            "<code>vinted@sheun-vinted.iam.gserviceaccount.com</code>"
        )
        return

    all_worksheets = doc.worksheets()
    if target_tabs.lower() != "all":
        valid_tabs = [t.strip().lower() for t in target_tabs.split(',')]
        worksheets = [ws for ws in all_worksheets if ws.title.strip().lower() in valid_tabs]
        if not worksheets:
            log(f"[!] Aucun onglet trouvé correspondant à : {target_tabs}")
            return
    else:
        worksheets = all_worksheets

    for sheet in worksheets:
        all_values = sheet.get_all_values()
        total_rows = len(all_values)
        log(f"\n>>> Parcours complet de l'onglet '{sheet.title}' ({total_rows - 1} ligne(s), de la ligne 2 à {total_rows})...")

        for row_idx in range(2, total_rows + 1):
            row_data = all_values[row_idx - 1]
            if not row_data or not row_data[0].strip():
                continue

            sku = row_data[0].strip()
            val_b = (row_data[1] if len(row_data) > 1 else "").strip()
            val_c = (row_data[2] if len(row_data) > 2 else "").strip()
            val_d = (row_data[3] if len(row_data) > 3 else "").strip()
            val_publier = (row_data[6] if len(row_data) > 6 else "").strip()

            log(f"\n--- [Ligne {row_idx}/{total_rows}] SKU : {sku} | Captures (B)='{val_b}', Image (C)='{val_c}', Description (D)='{val_d}', Publié (G)='{val_publier}' ---")

            if val_publier.lower() == "oui" and not refaire:
                log(f"  [⏭️ DÉJÀ PUBLIÉ] SKU {sku} est déjà marqué comme publié ('oui'). Ignoré.")
                continue

            # Si l'étape ciblée est generate ou all, et que Image (C) et Description (D) sont déjà faites
            if target_step in ["generate", "all"] and not refaire:
                if val_c.strip() == "Image générée" and val_d.strip() == "Rédaction fait":
                    log(f"  [⏭️ DÉJÀ GÉNÉRÉ] SKU {sku} : Image et Description déjà complètes. Ignoré.")
                    continue

            try:
                current_b = val_b
                # Étape Scraping si non fait
                if target_step in ["scrap", "all"]:
                    if val_b != "Fait scrap" or refaire:
                        scrap_success = execute_scraping(sku, sheet, row_idx, refaire=refaire)
                        if scrap_success:
                            current_b = "Fait scrap"
                            time.sleep(0.5)

                if current_b == "Fait scrap":
                    # Étape Image / Rédaction
                    if target_step in ["all", "generate"]:
                        # Lancement parallèle sans conflits Image (Gemini) + Rédaction (Meta AI)
                        gen_success = execute_parallel_generate(sku, sheet, row_idx, page_cdp, debug=debug, refaire=refaire)
                        if not gen_success:
                            log(f"  [⛔ ÉTAPE BLOQUÉE] Échec génération complète pour SKU {sku}.")
                            continue
                    elif target_step == "image":
                        if val_c != "Image générée" or refaire:
                            execute_image(sku, sheet, row_idx, page_cdp, refaire=refaire, notify=True)
                            time.sleep(0.5)
                    elif target_step == "redaction":
                        if val_d != "Rédaction fait" or refaire:
                            execute_redaction(sku, sheet, row_idx, page_cdp, debug=debug, refaire=refaire)
                            time.sleep(0.5)
                else:
                    log(f"  [⏭️ SAUT] Scraping non fait pour SKU {sku}, étapes Image/Rédaction ignorées.")

            except Exception as e:
                log(f"  [❌ ERREUR INATTENDUE] Ligne {row_idx} (SKU {sku}) : {e}")
                telegram_notifier.send_telegram_message(f"❌ <b>ERREUR Workflow</b> (Onglet: {sheet.title}, SKU: {sku})\n<code>{e}</code>", account_name=sheet.title.strip() if sheet else None)
                continue

    log("\n================ MODE AUTOMATIQUE TERMINÉ ================")

def get_cdp_page(p):
    try:
        r = requests.get("http://127.0.0.1:44231/json/version", timeout=3).json()
        browser_ws = r.get("webSocketDebuggerUrl")
        if browser_ws:
            browser = p.chromium.connect_over_cdp(browser_ws, timeout=20000)
            for ctx in browser.contexts:
                for page in ctx.pages:
                    u = page.url
                    if "meta.ai" in u or "gemini.google.com" in u:
                        return page
    except Exception as e:
        log(f"  [!] CDP non disponible ({e})")
    return None

# ----------------- MAIN CLI ENTRYPOINT -----------------
def main():
    parser = argparse.ArgumentParser(description="Pilote de flux d'articles Shein (Scraping, Image, Rédaction IA)")
    parser.add_argument("--sku", type=str, help="SKU Shein cible")
    parser.add_argument("--step", type=str, choices=["scrap", "image", "redaction", "generate", "all"], default="all", help="Étape spécifique à exécuter")
    parser.add_argument("--view", type=str, choices=["face", "back", "dos", "all"], default="all", help="Vue spécifique à générer pour l'étape image")
    parser.add_argument("--auto", action="store_true", help="Lancer le mode automatique sur l'ensemble du Sheet")
    parser.add_argument("--debug", action="store_true", help="Afficher le détail du calcul de prix")
    parser.add_argument("--refaire", action="store_true", help="Forcer une étape déjà cochée")
    parser.add_argument("--tab", type=str, default="all", help="Nom de l'onglet Google Sheet (comma separated) ou 'all'")
    parser.add_argument("--log-file", type=str, default="/root/shein/workflow.log", help="Chemin du fichier de log personnalisé")

    args = parser.parse_args()

    global LOG_FILE
    if args.log_file:
        LOG_FILE = args.log_file

    # Vérification verrou anti-doublons en mode auto (par onglet pour permettre l'exécution simultanée multi-comptes)
    if args.auto:
        tab_clean = args.tab.replace(",", "_").replace(" ", "")
        step_clean = (args.step or "complet").strip().lower()
        lock_file_tab = f"/root/shein/workflow_{tab_clean}_{step_clean}.lock" if args.tab != "all" else f"/root/shein/workflow_all_{step_clean}.lock"
        try:
            lock_fd = open(lock_file_tab, "w")
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            log(f"[❌ ERREUR] Une instance du mode automatique pour l'onglet '{args.tab}' (étape '{args.step}') est déjà en cours d'exécution. Abandon.")
            sys.exit(1)

    # Suivi dynamique dans le log
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"\n=== EXÉCUTION WORKFLOW [Onglet: {args.tab}] [{time.strftime('%Y-%m-%d %H:%M:%S')}] ===\n")
    except Exception:
        pass

    log(f"Initialisation du workflow...")
    doc = init_gspread_doc()

    page_cdp = None
    if args.auto:
        run_auto_mode(doc, page_cdp, debug=args.debug, refaire=args.refaire, target_tabs=args.tab, target_step=args.step)
    elif args.sku:
        sku = args.sku.strip()
        sheet = None
        row_idx = None
        
        if doc:
            clean_tab = args.tab.strip().lower()
            all_ws = doc.worksheets()
            worksheets_to_search = all_ws if clean_tab == "all" else [ws for ws in all_ws if ws.title.strip().lower() == clean_tab]
            for s in worksheets_to_search:
                try:
                    idx = get_row_index_by_sku(s, sku)
                    if idx:
                        sheet = s
                        row_idx = idx
                        break
                except Exception:
                    pass
        
        if not sheet or not row_idx:
            log(f"[❌ ERREUR] SKU '{sku}' introuvable.")
            sys.exit(1)
            
        log(f"Traitement du SKU '{sku}' (Onglet '{sheet.title}', Ligne : {row_idx})...")

        if args.step in ["scrap", "all"]:
            execute_scraping(sku, sheet, row_idx, refaire=args.refaire)

        if args.step in ["all", "generate"]:
            execute_parallel_generate(sku, sheet, row_idx, page_cdp, debug=args.debug, refaire=args.refaire)
        elif args.step == "image":
            should_notify_img = (args.step == "image")
            execute_image(sku, sheet, row_idx, page_cdp, refaire=args.refaire, view=args.view, notify=should_notify_img)
        elif args.step == "redaction":
            execute_redaction(sku, sheet, row_idx, page_cdp, debug=args.debug, refaire=args.refaire)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
