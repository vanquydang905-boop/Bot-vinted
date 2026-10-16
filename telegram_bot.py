import os
import requests
import time
import subprocess
import threading
from dotenv import load_dotenv
from telegram_subscribers import add_subscriber, get_subscribers, load_data as load_subscribers_data
from conflict_manager import (
    get_running_workflows,
    check_workflow_conflict,
    stop_workflow,
    get_browsers_status
)

load_dotenv("/root/shein/.env")

# Anti-rebond (debounce) : mémorise le dernier événement par chat_id
_user_last_action = {}
_action_lock = threading.Lock()

def is_duplicate_action(chat_id, action_key, debounce_seconds=2.5):
    """
    Vérifie si un utilisateur a envoyé la même action dans un intervalle trop court.
    """
    now = time.time()
    with _action_lock:
        last_time, last_key = _user_last_action.get(chat_id, (0, ""))
        if last_key == action_key and (now - last_time) < debounce_seconds:
            return True
        _user_last_action[chat_id] = (now, action_key)
        return False

def get_all_tokens():
    tokens = []
    main_token = os.getenv("TELEGRAM_BOT_TOKEN")
    if main_token: tokens.append(main_token)
    for k, v in os.environ.items():
        if k.startswith("BOT_TOKEN_") and v:
            if v not in tokens:
                tokens.append(v)
    return tokens

def get_updates(token, offset=None):
    url = f"https://api.telegram.org/bot{token}/getUpdates"
    params = {"timeout": 30, "offset": offset}
    try:
        r = requests.get(url, params=params, timeout=40)
        return r.json()
    except Exception:
        return {}

def send_message(token, text, target_chat_id=None):
    if not token:
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    
    # Répondre directement au chat ciblé si précisé
    if target_chat_id:
        try:
            requests.post(url, json={"chat_id": target_chat_id, "text": text, "parse_mode": "HTML"}, timeout=10)
        except Exception as e:
            print(f"[Telegram Bot] Erreur send_message direct à {target_chat_id} : {e}")
        return

    # Sinon diffuser aux abonnés du compte
    account_name = get_account_for_token(token)
    subscribers = get_subscribers(account_name)
    for cid in subscribers:
        try:
            requests.post(url, json={"chat_id": cid, "text": text, "parse_mode": "HTML"}, timeout=10)
        except Exception as e:
            print(f"[Telegram Bot] Erreur send_message broadcast à {cid} : {e}")

def get_account_for_token(token):
    scraper_tok = os.getenv("BOT_TOKEN_SCRAPER")
    default_tok = os.getenv("TELEGRAM_BOT_TOKEN")
    if token in [scraper_tok, default_tok]:
        return "all"
        
    for k, v in os.environ.items():
        if k.startswith("BOT_TOKEN_") and v == token:
            name_part = k.replace("BOT_TOKEN_", "").lower()
            if "scraper" in name_part: return "all"
            if "marie" in name_part: return "marie_sdm963"
            if "neli" in name_part: return "neli_fyu"
            if "clara" in name_part: return "claravintage09"
            if "lea" in name_part: return "lea_vani"
            if "vera" in name_part: return "vera_los"
            if "elya" in name_part: return "elya_soc"
            if "oria" in name_part: return "oria_nel"
            if "alix" in name_part: return "alix_vrt"
            if "jess" in name_part: return "jess_smth"
            if "faby" in name_part: return "faby_grb"
            if "lisa" in name_part: return "lisa_llc"
            if "yurih" in name_part: return "yurih_mlf"
            if "jade" in name_part: return "jade_huo"
            if "nice" in name_part: return "nice_mam"
            if "viki" in name_part: return "viki_sph"
            if "julie" in name_part: return "julie_last476"
            if "laura" in name_part: return "laura_vsni"
            if "helen" in name_part: return "helen_mil"
            if "eica" in name_part: return "eica_ph"
            return name_part
    return "all"

def format_status_message(account_for_bot):
    """
    Construit le rapport d'état en temps réel du bot et des workflows.
    """
    running = get_running_workflows()
    browsers = get_browsers_status()
    subs_data = load_subscribers_data()

    msg = "📊 <b>ÉTAT DU SYSTÈME ET DES WORKFLOWS</b>\n\n"

    # Statut du compte actuel
    account_busy = any(j["tab"] == account_for_bot or j["tab"] == "all" for j in running)
    if account_busy:
        active_job = next((j for j in running if j["tab"] == account_for_bot or j["tab"] == "all"), None)
        msg += f"• <b>Compte actuel ({account_for_bot}) :</b> 🔴 <b>OCCUPÉ</b>\n"
        if active_job:
            msg += f"  - Étape : <code>{active_job['step']}</code> | Durée : {active_job['etime']} (PID: {active_job['pid']})\n"
            msg += f"  - Activité : <i>{active_job['activity']}</i>\n\n"
    else:
        msg += f"• <b>Compte actuel ({account_for_bot}) :</b> 🟢 <b>LIBRE</b>\n\n"

    # Workflows en cours globalement
    if running:
        msg += f"⚙️ <b>Workflows actifs sur le serveur ({len(running)}) :</b>\n"
        for j in running:
            msg += f"  ▫️ Compte : <b>{j['tab']}</b> | Étape : <code>{j['step']}</code> (PID : {j['pid']})\n"
            msg += f"     Durée : {j['etime']} | <i>{j['activity']}</i>\n"
        msg += "\n"
    else:
        msg += "⚙️ <b>Workflows actifs :</b> Aucun traitement en cours (serveur au repos).\n\n"

    # Navigateurs CDP
    msg += "🌐 <b>Navigateurs CDP (Multi-comptes) :</b>\n"
    for b in browsers:
        stat_icon = "🟢 Libre" if (b["active"] and not b["locked"]) else ("🟡 Utilisé" if b["locked"] else "🔴 Inactif")
        msg += f"  • Port <code>{b['port']}</code> : {stat_icon}\n"

    # Collaborateurs enregistrés
    acc_users = subs_data.get("accounts", {}).get(account_for_bot, [])
    if acc_users:
        user_names = []
        for uid in acc_users:
            u_info = subs_data.get("users", {}).get(str(uid), {})
            name = u_info.get("first_name", f"ID {uid}")
            user_names.append(name)
        msg += f"\n👥 <b>Collaborateurs connectés :</b> {', '.join(user_names)}\n"

    msg += "\n💡 <i>Tapez <code>/stop</code> pour interrompre votre workflow, ou <code>/help</code> pour l'aide.</i>"
    return msg

def process_command(token, text, chat_id=None, user_name="Utilisateur"):
    raw_text = text.strip()
    text_lower = raw_text.lower()
    parts = text_lower.split()
    if not parts: return
    cmd = parts[0]

    # Anti-doublon pour éviter les spams de commandes
    if chat_id and is_duplicate_action(chat_id, raw_text, debounce_seconds=2.0):
        print(f"[Telegram Bot] Doublon ignoré pour chat_id {chat_id} : {raw_text}")
        return

    account_for_bot = get_account_for_token(token)

    # 1. COMMANDE /start, /help, /aide
    if cmd in ["/start", "start", "/help", "help", "aide", "/aide"]:
        welcome_msg = (
            f"👋 <b>Bonjour {user_name} !</b>\n"
            f"Vous êtes connecté(e) au bot dédié : <b>{account_for_bot}</b>.\n\n"
            f"<b>Commandes de production :</b>\n"
            f"• <code>/scrap</code> : Capturer les photos & infos Shein\n"
            f"• <code>/image</code> : Générer les Flat-Lay IA (Face & Dos)\n"
            f"• <code>/redaction</code> : Rédiger la description de vente\n"
            f"• <code>/complet</code> : Enchaîner Image + Rédaction\n"
            f"• <code>/all</code> : Exécuter toutes les étapes (Scrap + Image + Rédaction)\n\n"
            f"<b>Commandes de contrôle & diagnostic :</b>\n"
            f"• <code>/status</code> : Voir l'état du compte et des workflows actifs\n"
            f"• <code>/stop</code> : Arrêter le workflow en cours pour ce compte\n"
            f"• <code>/force [cmd]</code> : Forcer l'arrêt et relancer (ex: <code>/force /all</code>)\n"
        )
        send_message(token, welcome_msg, target_chat_id=chat_id)
        return

    # 2. COMMANDE /status, /etat, /info
    if cmd in ["/status", "status", "/etat", "etat", "/info", "info"]:
        status_msg = format_status_message(account_for_bot)
        send_message(token, status_msg, target_chat_id=chat_id)
        return

    # 3. GESTION DU /force
    is_forced = False
    if cmd in ["/force", "force"]:
        is_forced = True
        if len(parts) > 1:
            cmd = parts[1]
            parts = parts[1:]
        else:
            send_message(token, "⚠️ Précisez la commande à forcer. Exemple : <code>/force /all</code> ou <code>/force /scrap</code>", target_chat_id=chat_id)
            return

    # 4. COMMANDE /stop, /kill, /annuler
    if cmd in ["/stop", "stop", "/kill", "kill", "/annuler", "annuler"]:
        target_to_stop = account_for_bot
        if len(parts) > 1 and parts[1] in ["all", "tous", "tout"] and account_for_bot == "all":
            target_to_stop = "all"

        stopped, stop_msg = stop_workflow(target_to_stop, forced_by_user=user_name)
        if stopped:
            send_message(token, f"🛑 <b>Arrêt effectué par {user_name} :</b>\n{stop_msg}", target_chat_id=chat_id)
        else:
            send_message(token, f"ℹ️ <b>Aucun workflow à arrêter :</b> {stop_msg}", target_chat_id=chat_id)
        return

    # 5. DÉTERMINATION DU COMPTE CIBLE ET DE L'ÉTAPE
    # Scoping intelligent : sur un bot de compte spécifique, /all cible CE compte
    if account_for_bot != "all":
        tabs = account_for_bot
    else:
        # Sur le bot scraper principal
        if len(parts) > 1:
            param = " ".join(parts[1:]).strip().lower()
            tabs = "all" if param in ["all", "tous", "tout"] else ",".join(parts[1:])
        else:
            tabs = "all"

    step = "all"
    if cmd in ["/scrap", "scrap"]:
        step = "scrap"
    elif cmd in ["/image", "image"]:
        step = "image"
    elif cmd in ["/redaction", "redaction"]:
        step = "redaction"
    elif cmd in ["/complet", "complet"]:
        step = "generate"
    elif cmd in ["/all", "all"]:
        step = "all"
    else:
        help_msg = (
            f"❓ Commande non reconnue : <code>{raw_text}</code>\n\n"
            f"Tapez <code>/help</code> pour voir la liste des commandes ou <code>/status</code> pour voir l'état."
        )
        send_message(token, help_msg, target_chat_id=chat_id)
        return

    # 6. GESTION DES CONFLITS
    conflict = check_workflow_conflict(tabs, step)
    if conflict:
        if is_forced:
            send_message(token, f"⚡ <b>Interruption forcée :</b> Arrêt du workflow existant (PID {conflict['pid']}) pour relancer <code>{cmd}</code>...", target_chat_id=chat_id)
            stop_workflow(tabs, forced_by_user=user_name)
            time.sleep(1.0)
        else:
            conflict_msg = (
                f"⚠️ <b>CONFLIT D'EXÉCUTION :</b> Un workflow est déjà actif !\n\n"
                f"• Compte en cours : <b>{conflict['tab']}</b>\n"
                f"• Étape : <code>{conflict['step']}</code> (PID : <code>{conflict['pid']}</code>)\n"
                f"• En cours depuis : <b>{conflict['etime']}</b>\n"
                f"• Activité récente : <i>{conflict['activity']}</i>\n\n"
                f"<b>Que souhaitez-vous faire ?</b>\n"
                f"1. Patientez que le traitement se termine.\n"
                f"2. Tapez <code>/status</code> pour suivre l'avancement en temps réel.\n"
                f"3. Tapez <code>/stop</code> pour interrompre le traitement.\n"
                f"4. Tapez <code>/force {raw_text}</code> pour forcer l'arrêt et relancer immédiatement."
            )
            send_message(token, conflict_msg, target_chat_id=chat_id)
            return

    # 7. LANCEMENT SÉCURISÉ DU WORKFLOW
    confirm_msg = (
        f"🚀 <b>Commande validée ({user_name}) :</b>\n"
        f"• Compte cible : <b>{tabs}</b>\n"
        f"• Étape : <b>{step}</b>\n"
        f"<i>Lancement du workflow en arrière-plan...</i>"
    )
    send_message(token, confirm_msg, target_chat_id=chat_id)

    # Nettoyage préventif du verrou de cet onglet spécifique
    tab_clean = tabs.replace(",", "_").replace(" ", "")
    step_clean = (step or "complet").strip().lower()
    lock_path = f"/root/shein/workflow_{tab_clean}_{step_clean}.lock" if tabs != "all" else f"/root/shein/workflow_all_{step_clean}.lock"
    if os.path.exists(lock_path):
        try: os.remove(lock_path)
        except Exception: pass

    command = [
        "/root/venv/bin/python",
        "/root/shein/workflow.py",
        "--auto",
        "--step", step,
        "--tab", tabs
    ]
    with open("/root/shein/workflow.log", "a") as out_f:
        proc = subprocess.Popen(command, cwd="/root/shein", stdout=out_f, stderr=out_f)

    # Informer du PID attribué
    time.sleep(0.5)
    send_message(token, f"✅ <b>Processus démarré avec succès</b> (PID : <code>{proc.pid}</code>). Vous recevrez les résultats au fur et à mesure.", target_chat_id=chat_id)

def process_callback(token, callback):
    data = callback.get("data", "")
    message = callback.get("message", {})
    chat_id = message.get("chat", {}).get("id")
    from_user = callback.get("from", {})
    user_name = from_user.get("first_name", "Utilisateur")

    cb_id = callback.get("id")

    # Anti-rebond sur les clics de boutons
    if chat_id and is_duplicate_action(chat_id, data, debounce_seconds=2.0):
        requests.post(f"https://api.telegram.org/bot{token}/answerCallbackQuery", json={"callback_query_id": cb_id, "text": "⏳ Clic déjà pris en compte..."})
        return

    account_name = get_account_for_token(token)
    if chat_id:
        add_subscriber(chat_id, account_name, user_info=from_user)

    parts = data.split("|")
    if len(parts) < 2:
        requests.post(f"https://api.telegram.org/bot{token}/answerCallbackQuery", json={"callback_query_id": cb_id})
        return
    action = parts[0]
    sku = parts[1]
    
    # 1. ACTION : MARQUER COMME PUBLIÉ
    if action == "mark_published":
        tab_name = account_name
        try:
            import workflow
            doc = workflow.init_gspread_doc()
            sheet = None
            row_idx = None
            if doc:
                clean_tab = tab_name.strip().lower()
                all_ws = doc.worksheets()
                worksheets_to_search = all_ws if clean_tab == "all" else [ws for ws in all_ws if ws.title.strip().lower() == clean_tab]
                for s in worksheets_to_search:
                    try:
                        idx = workflow.get_row_index_by_sku(s, sku)
                        if idx:
                            sheet = s
                            row_idx = idx
                            break
                    except Exception:
                        pass
            if sheet and row_idx:
                headers = [h.strip().lower() for h in sheet.row_values(1)]
                col_publier = headers.index("publier") + 1 if "publier" in headers else 7
                sheet.update_cell(row_idx, col_publier, "oui")
                requests.post(f"https://api.telegram.org/bot{token}/answerCallbackQuery", json={"callback_query_id": cb_id, "text": "✅ Marqué comme publié dans le Sheet !"})
                send_message(token, f"📢 <b>Article Marqué Publié par {user_name} !</b>\n- SKU : <code>{sku}</code>\n- Onglet : <code>{sheet.title}</code> (Ligne {row_idx}, Colonne G = 'oui')", target_chat_id=chat_id)
            else:
                requests.post(f"https://api.telegram.org/bot{token}/answerCallbackQuery", json={"callback_query_id": cb_id, "text": "❌ SKU introuvable"})
                send_message(token, f"❌ Impossible de trouver le SKU <code>{sku}</code> dans le Google Sheet.", target_chat_id=chat_id)
        except Exception as e:
            requests.post(f"https://api.telegram.org/bot{token}/answerCallbackQuery", json={"callback_query_id": cb_id, "text": f"❌ Erreur : {e}"})
            send_message(token, f"❌ Erreur mise à jour Sheet pour {sku} : <code>{e}</code>", target_chat_id=chat_id)
        return

    step = "image"
    view = "all"
    if action == "redo_face":
        step = "image"
        view = "face"
    elif action == "redo_back":
        step = "image"
        view = "back"
    elif action == "redo_image":
        step = "image"
        view = "all"
    elif action == "redo_desc":
        step = "redaction"
        view = "all"
    elif action == "redo_all":
        step = "generate"
        view = "all"

    # 2. ACTIONS DE RÉGÉNÉRATION : CONTRÔLE DE CONFLIT SUR CE SKU / COMPTE
    conflict = check_workflow_conflict(account_name, step)
    if conflict:
        requests.post(f"https://api.telegram.org/bot{token}/answerCallbackQuery", json={"callback_query_id": cb_id, "text": f"⚠️ Un workflow est déjà actif sur {conflict['tab']} !"})
        send_message(token, f"⚠️ Impossible de lancer <code>{action}</code> sur SKU <code>{sku}</code> : un workflow est déjà actif pour <b>{conflict['tab']}</b> (PID: {conflict['pid']}). Tapez <code>/status</code> pour voir l'état.", target_chat_id=chat_id)
        return

    requests.post(f"https://api.telegram.org/bot{token}/answerCallbackQuery", json={"callback_query_id": cb_id, "text": f"⏳ Lancement : {action}..."})
        
    send_message(token, f"⚙️ <b>Action demandée par {user_name} :</b> {action} pour le SKU <code>{sku}</code>.\nLancement en arrière-plan...", target_chat_id=chat_id)
    
    command = [
        "/root/venv/bin/python",
        "/root/shein/workflow.py",
        "--sku", sku,
        "--step", step,
        "--view", view,
        "--refaire",
        "--tab", account_name
    ]
    with open("/root/shein/workflow.log", "a") as out_f:
        subprocess.Popen(command, cwd="/root/shein", stdout=out_f, stderr=out_f)

def poll_bot(token):
    acc = get_account_for_token(token)
    print(f"[{time.strftime('%H:%M:%S')}] Démarrage de l'écoute pour '{acc}' (token: {token[:15]}...)")
    offset = None
    while True:
        updates = get_updates(token, offset)
        if updates and updates.get("ok"):
            for item in updates.get("result", []):
                offset = item["update_id"] + 1
                
                if "callback_query" in item:
                    process_callback(token, item["callback_query"])
                    continue
                    
                msg = item.get("message")
                if msg and "text" in msg:
                    chat_id = str(msg["chat"]["id"])
                    sender_user = msg.get("from", {})
                    sender_name = sender_user.get("first_name", "") or msg.get("chat", {}).get("title", "Utilisateur")
                    
                    # Enregistrer automatiquement toute personne qui écrit au bot
                    add_subscriber(chat_id, acc, user_info=sender_user)
                    
                    print(f"[{time.strftime('%H:%M:%S')}] Message reçu sur '{acc}' de {sender_name} (chat_id: {chat_id}): '{msg['text']}'")
                    process_command(token, msg["text"], chat_id=chat_id, user_name=sender_name)
        time.sleep(1)

def main():
    tokens = get_all_tokens()
    if not tokens:
        print("Aucun token trouvé.")
        return
        
    print(f"Lancement de {len(tokens)} thread(s) de bot (Gestion des conflits & Multi-utilisateurs)...")
    threads = []
    for t in tokens:
        thread = threading.Thread(target=poll_bot, args=(t,))
        thread.daemon = True
        thread.start()
        threads.append(thread)
        
    for thread in threads:
        thread.join()

if __name__ == "__main__":
    main()
