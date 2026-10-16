import os
import time
import glob
import json
from dotenv import load_dotenv
import telegram_notifier
from telegram_subscribers import get_subscribers

load_dotenv("/root/shein/.env")

def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)

def find_completed_skus_for_account(account_name):
    """
    Recherche tous les SKUs ayant des images Flat-Lay et une description.txt
    pour le compte donné.
    """
    skus_found = {}
    pattern = f"/root/shein/screen_*/screen_{account_name}/*"
    for sku_dir in sorted(glob.glob(pattern)):
        if not os.path.isdir(sku_dir):
            continue
        sku = os.path.basename(sku_dir)
        flatlay_dir = os.path.join(sku_dir, "flatlay")
        desc_path = os.path.join(flatlay_dir, "description.txt")
        face_path = os.path.join(flatlay_dir, "flatlay_face.png")
        back_path = os.path.join(flatlay_dir, "flatlay_back.png")

        has_images = (os.path.exists(face_path) and os.path.getsize(face_path) > 0) or \
                     (os.path.exists(back_path) and os.path.getsize(back_path) > 0)
        has_desc = os.path.exists(desc_path) and os.path.getsize(desc_path) > 0

        if has_images and has_desc:
            photo_paths = []
            if os.path.exists(face_path) and os.path.getsize(face_path) > 0:
                photo_paths.append(face_path)
            if os.path.exists(back_path) and os.path.getsize(back_path) > 0:
                photo_paths.append(back_path)

            with open(desc_path, "r", encoding="utf-8", errors="ignore") as f:
                desc_text = f.read().strip()

            skus_found[sku] = {
                "sku": sku,
                "account": account_name,
                "photos": photo_paths,
                "description": desc_text,
                "dir": sku_dir
            }

    return skus_found

def main():
    log("=== Démarrage de l'envoi des articles terminés aux collaborateurs connectés ===")
    with open("/root/shein/telegram_subscribers.json", "r", encoding="utf-8") as f:
        subs_data = json.load(f)

    accounts_map = subs_data.get("accounts", {})
    if not accounts_map:
        log("❌ Aucun compte avec des collaborateurs enregistrés dans telegram_subscribers.json.")
        return

    total_sent = 0

    for account_name, chat_ids in sorted(accounts_map.items()):
        if not chat_ids:
            continue

        log(f"\n📂 Compte '{account_name}' - Destinataires enregistrés : {chat_ids}")
        completed_skus = find_completed_skus_for_account(account_name)

        if not completed_skus:
            log(f"  ℹ️ Aucun article complet (images + description) trouvé pour '{account_name}'.")
            continue

        log(f"  🚀 {len(completed_skus)} SKU(s) complets trouvés. Début de l'envoi...")

        for idx, (sku, data) in enumerate(completed_skus.items(), 1):
            log(f"  [{idx}/{len(completed_skus)}] Envoi du SKU {sku} ({len(data['photos'])} photos + description)...")
            try:
                # 1. Envoi du groupe de photos
                if data["photos"]:
                    res_media = telegram_notifier.send_telegram_media_group(data["photos"], account_name=account_name)
                    if not res_media:
                        log(f"    ⚠️ Erreur envoi photos pour SKU {sku}")
                
                # 2. Envoi du message de révision avec la description et les boutons d'action
                res_msg = telegram_notifier.send_telegram_review_message(sku, account_name, description=data["description"], phase=3)
                if res_msg:
                    log(f"    ✅ SKU {sku} envoyé avec succès !")
                    total_sent += 1
                else:
                    log(f"    ❌ Échec envoi message/boutons pour SKU {sku}")

            except Exception as e:
                log(f"    ❌ Erreur lors de l'envoi du SKU {sku} : {e}")

            # Pause pour respecter les limites de débit Telegram (anti-flood)
            time.sleep(2.0)

    log(f"\n🎉 Opération terminée : {total_sent} article(s) renvoyé(s) aux collaborateurs connectés !")

if __name__ == "__main__":
    main()
