import os
import requests
import json
from dotenv import load_dotenv
from telegram_subscribers import get_subscribers

load_dotenv("/root/shein/.env")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

def get_token_for_account(account_name=None):
    if account_name:
        clean_name = account_name.strip().lower().replace('-', '_').replace(' ', '_')
        if 'marie' in clean_name:
            token = os.getenv("BOT_TOKEN_MARIE_SDM963")
        elif 'neli' in clean_name:
            token = os.getenv("BOT_TOKEN_NELI_FYU12")
        elif 'clara' in clean_name:
            token = os.getenv("BOT_TOKEN_CLARAVINTAGE09")
        elif 'lea' in clean_name:
            token = os.getenv("BOT_TOKEN_LEA_VANI09")
        elif 'vera' in clean_name:
            token = os.getenv("BOT_TOKEN_VERA_LOS09")
        elif 'elya' in clean_name:
            token = os.getenv("BOT_TOKEN_ELYA_SOC09")
        elif 'oria' in clean_name:
            token = os.getenv("BOT_TOKEN_ORIA_NEL009")
        elif 'alix' in clean_name:
            token = os.getenv("BOT_TOKEN_ALIX_VRT09")
        elif 'lisa' in clean_name:
            token = os.getenv("BOT_TOKEN_LISA_LLC009")
        elif 'viki' in clean_name:
            token = os.getenv("BOT_TOKEN_VIKI_SPH009")
        elif 'faby' in clean_name:
            token = os.getenv("BOT_TOKEN_FABY_GRB009")
        elif 'julie' in clean_name:
            token = os.getenv("BOT_TOKEN_JULIE_LAST476")
        elif 'laura' in clean_name:
            token = os.getenv("BOT_TOKEN_LAURA_VSNI009")
        elif 'helen' in clean_name:
            token = os.getenv("BOT_TOKEN_HELEN_MIL009")
        elif 'jade' in clean_name:
            token = os.getenv("BOT_TOKEN_JADE_HUO009")
        elif 'yurih' in clean_name:
            token = os.getenv("BOT_TOKEN_YURIH_MLF009")
        elif 'eica' in clean_name:
            token = os.getenv("BOT_TOKEN_EICA_PH")
        else:
            env_key = f"BOT_TOKEN_{clean_name.upper()}"
            token = os.getenv(env_key)
        if token:
            return token
    return os.getenv("BOT_TOKEN_SCRAPER") or TELEGRAM_BOT_TOKEN

def send_telegram_message(message, account_name=None):
    bot_token = get_token_for_account(account_name)
    if not bot_token:
        print("[Telegram] Bot token manquant. Message non envoyé.")
        return False
        
    chat_ids = get_subscribers(account_name)
    if not chat_ids:
        print("[Telegram] Aucun abonné trouvé.")
        return False

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    success = False
    for cid in chat_ids:
        payload = {
            "chat_id": cid,
            "text": message,
            "parse_mode": "HTML"
        }
        try:
            res = requests.post(url, json=payload, timeout=10)
            if res.status_code == 200:
                success = True
        except Exception as e:
            print(f"[Telegram] Échec envoi message à {cid}: {e}")
    return success

def send_telegram_photo(photo_path, caption=None, account_name=None):
    bot_token = get_token_for_account(account_name)
    if not bot_token or not os.path.exists(photo_path):
        return False
        
    chat_ids = get_subscribers(account_name)
    if not chat_ids:
        return False

    url = f"https://api.telegram.org/bot{bot_token}/sendPhoto"
    success = False
    for cid in chat_ids:
        try:
            with open(photo_path, "rb") as photo_file:
                files = {"photo": photo_file}
                data = {"chat_id": cid}
                if caption:
                    data["caption"] = caption
                    data["parse_mode"] = "HTML"
                res = requests.post(url, data=data, files=files, timeout=30)
                if res.status_code == 200:
                    success = True
        except Exception as e:
            print(f"[Telegram] Échec envoi photo à {cid}: {e}")
    return success

def send_telegram_media_group(photo_paths, account_name=None):
    bot_token = get_token_for_account(account_name)
    if not bot_token:
        return False
        
    chat_ids = get_subscribers(account_name)
    if not chat_ids:
        return False

    valid_paths = [p for p in photo_paths if os.path.exists(p)][:10]
    if not valid_paths:
        return False

    url = f"https://api.telegram.org/bot{bot_token}/sendMediaGroup"
    success = False
    for cid in chat_ids:
        media = []
        files = {}
        file_handles = []
        try:
            for i, path in enumerate(valid_paths):
                name = f"photo{i}"
                media.append({"type": "photo", "media": f"attach://{name}"})
                fh = open(path, "rb")
                file_handles.append(fh)
                files[name] = fh

            data = {"chat_id": cid, "media": json.dumps(media)}
            r = requests.post(url, data=data, files=files, timeout=40)
            if r.status_code == 200:
                success = True
        except Exception as e:
            print(f"[Telegram] Échec envoi media group à {cid}: {e}")
        finally:
            for fh in file_handles:
                fh.close()
    return success

def send_telegram_review_message(sku, account_name, description=None, phase=3):
    bot_token = get_token_for_account(account_name)
    if not bot_token:
        return False

    chat_ids = get_subscribers(account_name)
    if not chat_ids:
        return False

    drive_link = "https://drive.google.com/drive/folders/1Edqavh2ORhg5n5R-zZAj8H-RKK8lV-S0"

    if phase == 2:
        text = f"✅ <b>Images Générées</b> | SKU: <code>{sku}</code> ({account_name})\n\n"
        text += "<i>Vérifiez les images ci-dessus. Si elles conviennent, vous pouvez lancer la phase 3 (/redaction). Sinon, utilisez les boutons ci-dessous pour corriger.</i>"
        
        keyboard = {
            "inline_keyboard": [
                [
                    {"text": "🔄 Face", "callback_data": f"redo_face|{sku}"},
                    {"text": "🔄 Dos", "callback_data": f"redo_back|{sku}"},
                    {"text": "🔄 Face+Dos", "callback_data": f"redo_image|{sku}"}
                ]
            ]
        }
    else:
        text = f"✅ <b>Article Terminé</b> | SKU: <code>{sku}</code> ({account_name})\n\n"
        if description:
            text += f"<b>Description:</b>\n{description}\n\n"
        text += f"🔗 <a href='{drive_link}'>Lien Drive</a>"

        if len(text) > 4000:
            text = text[:4000] + "..."

        keyboard = {
            "inline_keyboard": [
                [
                    {"text": "📢 Marquer comme publié", "callback_data": f"mark_published|{sku}"}
                ],
                [
                    {"text": "🔄 Face", "callback_data": f"redo_face|{sku}"},
                    {"text": "🔄 Dos", "callback_data": f"redo_back|{sku}"},
                    {"text": "🔄 Face+Dos", "callback_data": f"redo_image|{sku}"}
                ],
                [
                    {"text": "🔄 Description", "callback_data": f"redo_desc|{sku}"},
                    {"text": "🔄 TOUT (Img+Desc)", "callback_data": f"redo_all|{sku}"}
                ]
            ]
        }
    
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    success = False
    for cid in chat_ids:
        payload = {
            "chat_id": cid,
            "text": text,
            "parse_mode": "HTML",
            "reply_markup": json.dumps(keyboard)
        }
        try:
            r = requests.post(url, json=payload, timeout=15)
            if r.status_code == 200:
                success = True
        except Exception as e:
            print(f"[Telegram] Échec envoi review msg à {cid}: {e}")
    return success
