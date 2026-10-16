import os
import sys
import time
import glob
import argparse
import subprocess

DEFAULT_FOLDER_ID = "1Edqavh2ORhg5n5R-zZAj8H-RKK8lV-S0"

def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)

def run_rclone(local_path, remote_path, folder_id):
    """
    Copie un fichier ou dossier local vers le chemin Google Drive spécifié via rclone.
    """
    remote_dest = f"gdrive:{remote_path}"
    cmd = [
        "rclone", "copy",
        local_path,
        remote_dest,
        "--drive-root-folder-id", folder_id,
        "--fast-list",
        "--transfers", "4",
        "--checkers", "8",
        "--exclude", "prompt_*.txt",
        "--stats-log-level", "NOTICE"
    ]
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        log(f"  [❌ rclone] Erreur lors de la copie de {local_path} vers {remote_path} : {e}")

def sync_single_sku(sku_dir, account, date_str, sku, folder_id):
    """
    Synchronise un SKU complet (dossier origine et flatlay) sur Google Drive.
    """
    remote_base = f"{account}/{date_str}/{sku}"
    synced_items = []

    # 1. Dossier 'origine'
    # Photos brutes image-screen/
    img_screen_dir = os.path.join(sku_dir, "image-screen")
    if os.path.exists(img_screen_dir) and os.listdir(img_screen_dir):
        run_rclone(img_screen_dir, f"{remote_base}/origine/", folder_id)
        synced_items.append("image-screen")

    # Guides des tailles desc-screen/
    desc_screen_dir = os.path.join(sku_dir, "desc-screen")
    if os.path.exists(desc_screen_dir) and os.listdir(desc_screen_dir):
        run_rclone(desc_screen_dir, f"{remote_base}/origine/", folder_id)
        synced_items.append("desc-screen")

    # Fichier info.txt
    info_path = os.path.join(sku_dir, "info.txt")
    if os.path.exists(info_path):
        run_rclone(info_path, f"{remote_base}/origine/", folder_id)
        synced_items.append("info.txt")

    # 2. Dossier 'flatlay'
    flatlay_dir = os.path.join(sku_dir, "flatlay")
    if os.path.exists(flatlay_dir) and os.listdir(flatlay_dir):
        run_rclone(flatlay_dir, f"{remote_base}/flatlay/", folder_id)
        synced_items.append("flatlay")

    if synced_items:
        log(f"  [✅ Drive] SKU {sku} ({account} - {date_str}) synchronisé -> {', '.join(synced_items)}")
    else:
        log(f"  [⚠️ Drive] Aucun fichier valide trouvé à synchroniser pour SKU {sku} dans {sku_dir}")

def find_sku_directory(account, sku):
    """
    Recherche le dossier du SKU en vérifiant d'abord aujourd'hui, puis dans les dates antérieures.
    Retourne (sku_dir, date_str).
    """
    today_str = time.strftime("%Y-%m-%d")
    today_dir = f"/root/shein/screen_{today_str}/screen_{account}/{sku}"
    if os.path.exists(today_dir):
        return today_dir, today_str

    # Recherche dans tous les dossiers screen_*
    matches = glob.glob(f"/root/shein/screen_*/screen_{account}/{sku}")
    if matches:
        # Prendre le match le plus récent
        matches.sort()
        best_match = matches[-1]
        # Extraire la date depuis le chemin /root/shein/screen_YYYY-MM-DD/...
        parts = best_match.split("/")
        date_folder = [p for p in parts if p.startswith("screen_20")]
        date_str = date_folder[0].replace("screen_", "") if date_folder else today_str
        return best_match, date_str

    # Recherche globale si le compte diffère légèrement
    any_matches = glob.glob(f"/root/shein/screen_*/*/{sku}")
    if any_matches:
        any_matches.sort()
        best_match = any_matches[-1]
        parts = best_match.split("/")
        date_folder = [p for p in parts if p.startswith("screen_20")]
        date_str = date_folder[0].replace("screen_", "") if date_folder else today_str
        return best_match, date_str

    return None, today_str

def sync_all(folder_id, target_account=None, target_date=None):
    """
    Synchronise tous les dossiers locaux existants vers Google Drive.
    """
    screen_dirs = sorted([d for d in os.listdir("/root/shein") if d.startswith("screen_") and os.path.isdir(os.path.join("/root/shein", d))])
    if target_date:
        screen_dirs = [d for d in screen_dirs if target_date in d]

    total_skus = 0
    for sdir in screen_dirs:
        date_str = sdir.replace("screen_", "")
        full_sdir = os.path.join("/root/shein", sdir)
        account_dirs = sorted([d for d in os.listdir(full_sdir) if os.path.isdir(os.path.join(full_sdir, d))])
        
        for acc_dir_name in account_dirs:
            acc_name = acc_dir_name.replace("screen_", "")
            if target_account and acc_name != target_account:
                continue

            full_acc_dir = os.path.join(full_sdir, acc_dir_name)
            skus = sorted([d for d in os.listdir(full_acc_dir) if os.path.isdir(os.path.join(full_acc_dir, d))])
            if not skus:
                continue

            log(f"\n📂 Synchronisation compte '{acc_name}' [{date_str}] ({len(skus)} SKUs)...")
            for idx, sku in enumerate(skus, 1):
                sku_path = os.path.join(full_acc_dir, sku)
                sync_single_sku(sku_path, acc_name, date_str, sku, folder_id)
                total_skus += 1

    log(f"\n🎉 Synchronisation globale terminée : {total_skus} SKU(s) traités.")

def main():
    parser = argparse.ArgumentParser(description="Synchronisation des données Shein vers Google Drive via rclone")
    parser.add_argument("--folder-id", type=str, default=DEFAULT_FOLDER_ID, help="ID du dossier Google Drive partagé")
    parser.add_argument("--account", type=str, default=None, help="Nom du compte/onglet")
    parser.add_argument("--sku", type=str, default=None, help="SKU spécifique à synchroniser")
    parser.add_argument("--date", type=str, default=None, help="Date spécifique (YYYY-MM-DD)")
    parser.add_argument("--all", action="store_true", help="Synchroniser tous les comptes et toutes les dates")
    args = parser.parse_args()

    folder_id = args.folder_id

    if args.sku:
        account = args.account.strip() if args.account else "defaut"
        sku_dir, date_str = find_sku_directory(account, args.sku)
        if sku_dir and os.path.exists(sku_dir):
            log(f"Synchronisation ciblée pour SKU {args.sku} (Compte: {account}, Date: {date_str})...")
            sync_single_sku(sku_dir, account, date_str, args.sku, folder_id)
        else:
            log(f"  [❌] Dossier introuvable pour SKU {args.sku} (Compte: {account})")
    elif args.all:
        log("Lancement de la synchronisation complète de tous les comptes et dates...")
        sync_all(folder_id)
    elif args.account:
        account = args.account.strip()
        log(f"Lancement de la synchronisation pour le compte '{account}'...")
        sync_all(folder_id, target_account=account, target_date=args.date)
    else:
        # Par défaut, synchroniser tout ce qui existe localement
        log("Aucun SKU ni compte spécifié. Lancement de la synchronisation globale...")
        sync_all(folder_id, target_date=args.date)

if __name__ == "__main__":
    main()
