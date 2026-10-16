import os
import json
import threading
from dotenv import load_dotenv

load_dotenv("/root/shein/.env")

SUBSCRIBERS_FILE = "/root/shein/telegram_subscribers.json"
DEFAULT_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

_lock = threading.Lock()

def _normalize_account(account_name):
    if not account_name:
        return "all"
    clean = account_name.strip().lower().replace("-", "_").replace(" ", "_")
    if "scraper" in clean or clean in ["all", "tous", "tout"]:
        return "all"
    if "marie" in clean: return "marie_sdm963"
    if "neli" in clean: return "neli_fyu"
    if "clara" in clean: return "claravintage09"
    if "lea" in clean: return "lea_vani"
    if "vera" in clean: return "vera_los"
    if "elya" in clean: return "elya_soc"
    if "oria" in clean: return "oria_nel"
    if "alix" in clean: return "alix_vrt"
    if "lisa" in clean: return "lisa_llc"
    if "viki" in clean: return "viki_sph"
    if "faby" in clean: return "faby_grb"
    if "julie" in clean: return "julie_last476"
    if "laura" in clean: return "laura_vsni"
    if "jade" in clean: return "jade_huo"
    if "nice" in clean: return "nice_mam"
    if "yurih" in clean: return "yurih_mlf"
    if "helen" in clean: return "helen_mil"
    if "eica" in clean: return "eica_ph"
    return clean

def load_data():
    with _lock:
        if not os.path.exists(SUBSCRIBERS_FILE):
            initial_data = {
                "global_subscribers": [str(DEFAULT_CHAT_ID)] if DEFAULT_CHAT_ID else [],
                "accounts": {},
                "users": {}
            }
            try:
                with open(SUBSCRIBERS_FILE, "w", encoding="utf-8") as f:
                    json.dump(initial_data, f, indent=2, ensure_ascii=False)
            except Exception:
                pass
            return initial_data

        try:
            with open(SUBSCRIBERS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if not isinstance(data, dict):
                    data = {}
                if "global_subscribers" not in data:
                    data["global_subscribers"] = []
                if "accounts" not in data:
                    data["accounts"] = {}
                if "users" not in data:
                    data["users"] = {}
                # Ensure default chat id is always present
                if DEFAULT_CHAT_ID and str(DEFAULT_CHAT_ID) not in data["global_subscribers"]:
                    data["global_subscribers"].append(str(DEFAULT_CHAT_ID))
                return data
        except Exception:
            return {
                "global_subscribers": [str(DEFAULT_CHAT_ID)] if DEFAULT_CHAT_ID else [],
                "accounts": {},
                "users": {}
            }

def save_data(data):
    with _lock:
        try:
            with open(SUBSCRIBERS_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[Subscribers] Erreur lors de la sauvegarde : {e}")

def add_subscriber(chat_id, account_name=None, user_info=None):
    """
    Enregistre un chat_id comme abonné pour recevoir les notifications et envoyer des commandes.
    """
    if not chat_id:
        return
    chat_id_str = str(chat_id)
    norm_acc = _normalize_account(account_name)

    data = load_data()
    changed = False

    # Enregistrer dans le compte spécifique ou dans global
    if norm_acc == "all":
        if chat_id_str not in data["global_subscribers"]:
            data["global_subscribers"].append(chat_id_str)
            changed = True
    else:
        if norm_acc not in data["accounts"]:
            data["accounts"][norm_acc] = []
        if chat_id_str not in data["accounts"][norm_acc]:
            data["accounts"][norm_acc].append(chat_id_str)
            changed = True



    # Métadonnées utilisateur
    if user_info and isinstance(user_info, dict):
        if chat_id_str not in data["users"]:
            data["users"][chat_id_str] = {}
        data["users"][chat_id_str].update(user_info)
        changed = True

    if changed:
        save_data(data)
        print(f"[Subscribers] Nouvel abonné enregistré : chat_id={chat_id_str} pour compte='{norm_acc}'")

def get_subscribers(account_name=None):
    """
    Retourne la liste unique des chat_id abonnés qui doivent recevoir les messages.
    """
    data = load_data()
    subscribers = set()

    # Chat ID par défaut depuis .env
    if DEFAULT_CHAT_ID:
        subscribers.add(str(DEFAULT_CHAT_ID))

    # Abonnés globaux
    for cid in data.get("global_subscribers", []):
        subscribers.add(str(cid))

    # Abonnés du compte spécifique
    norm_acc = _normalize_account(account_name)
    if norm_acc != "all" and norm_acc in data.get("accounts", {}):
        for cid in data["accounts"][norm_acc]:
            subscribers.add(str(cid))

    return list(subscribers)
