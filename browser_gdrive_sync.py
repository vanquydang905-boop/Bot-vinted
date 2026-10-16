import os
import sys
import time
import glob
from playwright.sync_api import sync_playwright

STAGING_BASE = "/root/shein/drive_upload_staging/photo marie"
DRIVE_URL = "https://drive.google.com/drive/folders/1Edqavh2ORhg5n5R-zZAj8H-RKK8lV-S0"

def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)

def create_and_open_folder(page, folder_name):
    """Vérifie si un dossier existe, le crée si nécessaire, puis double-clique dessus."""
    log(f"  [📁 Dossier] Recherche/Création du dossier '{folder_name}'...")
    
    # Chercher si le dossier est déjà visible dans la liste
    folder_item = page.locator(f"[role='row']:has-text('{folder_name}'), [data-target='item']:has-text('{folder_name}')").first
    if folder_item.is_visible(timeout=3000):
        log(f"  [✓] Dossier '{folder_name}' trouvé, ouverture...")
        folder_item.dblclick()
        page.wait_for_timeout(2500)
        return True
        
    # Sinon créer le dossier
    new_btn = page.locator("button:has-text('Nouveau'), button:has-text('New')").first
    new_btn.click()
    page.wait_for_timeout(1000)
    
    folder_btn = page.locator("[role='menuitem']:has-text('Nouveau dossier'), [role='menuitem']:has-text('New folder')").first
    folder_btn.click()
    page.wait_for_timeout(1500)
    
    page.keyboard.type(folder_name)
    page.wait_for_timeout(500)
    page.keyboard.press("Enter")
    log(f"  [+] Dossier '{folder_name}' créé avec succès sur Google Drive.")
    page.wait_for_timeout(3000)
    
    # Ouvrir le nouveau dossier
    folder_item = page.locator(f"[role='row']:has-text('{folder_name}'), [data-target='item']:has-text('{folder_name}')").first
    if folder_item.is_visible(timeout=5000):
        folder_item.dblclick()
        page.wait_for_timeout(2500)
    return True

def upload_files_to_current_drive_folder(page, file_paths):
    if not file_paths:
        return
    log(f"  [⬆️ Upload] Téléversement de {len(file_paths)} fichier(s)...")
    
    new_btn = page.locator("button:has-text('Nouveau'), button:has-text('New')").first
    new_btn.click()
    page.wait_for_timeout(1000)
    
    upload_file_btn = page.locator("[role='menuitem']:has-text('Importer un fichier'), [role='menuitem']:has-text('File upload')").first
    
    with page.expect_file_chooser(timeout=10000) as fc_info:
        upload_file_btn.click()
        
    file_chooser = fc_info.value
    file_chooser.set_files(file_paths)
    log(f"  [⏳ Envoi] {len(file_paths)} fichier(s) transmis au navigateur...")
    
    # Attente de la fin des téléversements
    page.wait_for_timeout(3000 + (1000 * len(file_paths)))

def main():
    if not os.path.exists(STAGING_BASE):
        log(f"[!] Dossier staging '{STAGING_BASE}' non trouvé.")
        return

    skus = sorted([d for d in os.listdir(STAGING_BASE) if os.path.isdir(os.path.join(STAGING_BASE, d))])
    log(f"Lancement de la synchronisation Navigateur pour {len(skus)} SKU(s)...")

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp("http://127.0.0.1:44231")
        context = browser.contexts[0]
        pages = [pg for pg in context.pages if "drive.google.com" in pg.url]
        page = pages[0] if pages else context.new_page()
        page.bring_to_front()
        
        log(f"Navigation vers le dossier racine Google Drive...")
        page.goto(DRIVE_URL)
        page.wait_for_timeout(4000)
        
        # 1. Ouvrir ou créer le dossier 'photo marie'
        create_and_open_folder(page, "photo marie")
        photo_marie_url = page.url
        
        for idx, sku in enumerate(skus, 1):
            log(f"\n[{idx}/{len(skus)}] Traitement du SKU : {sku}")
            page.goto(photo_marie_url)
            page.wait_for_timeout(2500)
            
            # Dossier SKU
            create_and_open_folder(page, sku)
            sku_url = page.url
            
            # Sous-dossier 1 : origine
            orig_dir = os.path.join(STAGING_BASE, sku, "origine")
            if os.path.exists(orig_dir):
                create_and_open_folder(page, "origine")
                orig_files = []
                for root, dirs, files in os.walk(orig_dir):
                    for f in files:
                        orig_files.append(os.path.join(root, f))
                if orig_files:
                    upload_files_to_current_drive_folder(page, orig_files)
                    
            # Naviguer de retour dans le dossier SKU
            page.goto(sku_url)
            page.wait_for_timeout(2500)
            
            # Sous-dossier 2 : flatlay
            flat_dir = os.path.join(STAGING_BASE, sku, "flatlay")
            if os.path.exists(flat_dir):
                create_and_open_folder(page, "flatlay")
                flat_files = [os.path.join(flat_dir, f) for f in os.listdir(flat_dir) if os.path.isfile(os.path.join(flat_dir, f)) and not f.startswith("prompt_")]
                if flat_files:
                    upload_files_to_current_drive_folder(page, flat_files)
                    
        log("\n🎉 Synchronisation navigateur Google Drive terminée avec succès !")

if __name__ == "__main__":
    main()
