import os
import re
import time
import signal
import subprocess
import glob
from dotenv import load_dotenv

load_dotenv("/root/shein/.env")

LOG_FILE = "/root/shein/workflow.log"

def get_running_workflows():
    """
    Détecte tous les processus workflow.py en cours d'exécution.
    Retourne une liste de dictionnaires décrivant chaque tâche active.
    """
    running = []
    try:
        # ps aux pour capturer tous les processus python exécutant workflow.py
        res = subprocess.run(["ps", "-eo", "pid,etime,args"], capture_output=True, text=True)
        lines = res.stdout.strip().split("\n")
        
        for line in lines:
            line_str = line.strip()
            if "workflow.py" in line_str and "grep" not in line_str and "defunct" not in line_str:
                parts = line_str.split(None, 2)
                if len(parts) >= 3:
                    pid = int(parts[0])
                    etime = parts[1]
                    cmdline = parts[2]

                    # Ne pas inclure le script lui-même s'il s'appelle workflow.py (ex: grep ou tools)
                    if not ("python" in cmdline and "workflow.py" in cmdline):
                        continue

                    # Extraire --tab
                    tab_match = re.search(r"--tab\s+([^\s]+)", cmdline)
                    tab = tab_match.group(1) if tab_match else "unknown"

                    # Extraire --step
                    step_match = re.search(r"--step\s+([^\s]+)", cmdline)
                    step = step_match.group(1) if step_match else "all"

                    # Extraire --sku
                    sku_match = re.search(r"--sku\s+([^\s]+)", cmdline)
                    sku = sku_match.group(1) if sku_match else None

                    # Extraire la dernière activité depuis workflow.log
                    last_activity = get_last_activity_for_tab(tab, sku)

                    running.append({
                        "pid": pid,
                        "tab": tab,
                        "step": step,
                        "sku": sku,
                        "etime": etime,
                        "activity": last_activity,
                        "cmd": cmdline
                    })
    except Exception as e:
        print(f"[ConflictManager] Erreur get_running_workflows: {e}")

    return running

def get_last_activity_for_tab(tab, sku=None):
    """
    Lit les dernières lignes de workflow.log pour afficher ce que fait le workflow.
    """
    if not os.path.exists(LOG_FILE):
        return "Initialisation..."
    try:
        res = subprocess.run(["tail", "-n", "40", LOG_FILE], capture_output=True, text=True)
        lines = [l.strip() for l in res.stdout.strip().split("\n") if l.strip()]
        for l in reversed(lines):
            if "SKU :" in l or "Traitement" in l or "Génération" in l or "RÉDACTION" in l or "Scraping" in l or "Parcours" in l:
                clean_l = re.sub(r"\[\d{2}:\d{2}:\d{2}\]", "", l).strip()
                clean_l = re.sub(r"[-=]{3,}", "", clean_l).strip()
                if clean_l:
                    return clean_l[:80]
        if lines:
            return lines[-1][:80]
    except Exception:
        pass
    return "En cours d'exécution"

def check_workflow_conflict(target_tab, target_step=None):
    """
    Vérifie si un workflow conflictuel est déjà en cours pour target_tab.
    - Deux comptes distincts (ex: helen_mil et eica_ph) s'exécutent en parallèle SANS conflit.
    - Conflit direct si un workflow est déjà actif sur le même compte (job_tab == clean_target).
    - Conflit si target_tab == 'all' et qu'un workflow quelconque est en cours.
    - Si un job 'all' est en cours, il ne bloque un compte spécifique que si les étapes interfèrent 
      (ex: deux scrapings simultanés sur le même compte). Si le job 'all' fait 'scrap', un compte 
      spécifique peut générer ses images et sa rédaction en parallèle sans conflit.
    """
    running = get_running_workflows()
    if not running:
        return None

    clean_target = (target_tab or "").strip().lower()
    clean_step = (target_step or "all").strip().lower()

    for job in running:
        job_tab = job["tab"].strip().lower()
        job_step = job.get("step", "all").strip().lower()

        # 1. Même compte : conflit direct (évite deux processus sur le même onglet Sheet)
        if job_tab == clean_target:
            return job

        # 2. Nouvelle commande globale ('all') : attend que les tâches ciblées se terminent
        if clean_target == "all":
            return job

        # 3. Job global 'all' en cours :
        if job_tab == "all":
            # Si le job global fait la même étape ou 'all', c'est un conflit potentiel
            if job_step == "all" or job_step == clean_step:
                return job
            # Si le job global fait 'scrap' et que le compte spécifique fait 'image', 'redaction' ou 'generate', PAS DE CONFLIT !
            if job_step == "scrap" and clean_step in ["image", "redaction", "generate"]:
                continue
            return job

    return None

def stop_workflow(target_tab=None, forced_by_user="Utilisateur"):
    """
    Arrête proprement et de façon ciblée le workflow pour target_tab.
    Ne touche JAMAIS aux workflows des autres comptes.
    """
    running = get_running_workflows()
    if not running:
        return False, "Aucun workflow actif trouvé."

    stopped = []
    clean_target = (target_tab or "").strip().lower()

    for job in running:
        job_tab = job["tab"].strip().lower()
        should_stop = False

        if clean_target in ["all", "tous", "tout"]:
            should_stop = True
        elif job_tab == clean_target:
            should_stop = True

        if should_stop:
            pid = job["pid"]
            try:
                # 1. Envoi SIGTERM
                os.kill(pid, signal.SIGTERM)
                time.sleep(0.5)
                # 2. Si encore vivant, SIGKILL
                try:
                    os.kill(pid, 0)
                    os.kill(pid, signal.SIGKILL)
                except OSError:
                    pass
                stopped.append((job["tab"], pid))
            except Exception as e:
                print(f"[ConflictManager] Erreur lors de l'arrêt du PID {pid}: {e}")

    # Nettoyage des verrous correspondants
    if clean_target in ["all", "tous", "tout"]:
        for lock_f in glob.glob("/root/shein/workflow_*.lock"):
            try: os.remove(lock_f)
            except Exception: pass
        if os.path.exists("/root/shein/workflow.lock"):
            try: os.remove("/root/shein/workflow.lock")
            except Exception: pass
    else:
        tab_clean = clean_target.replace(",", "_").replace(" ", "")
        lock_path = f"/root/shein/workflow_{tab_clean}.lock"
        if os.path.exists(lock_path):
            try: os.remove(lock_path)
            except Exception: pass

    if stopped:
        msg = f"Arrêt de {len(stopped)} processus : " + ", ".join([f"{t} (PID {p})" for t, p in stopped])
        return True, msg
    else:
        return False, f"Aucun workflow correspondant à '{target_tab}' n'était en cours."

def get_browsers_status():
    """
    Vérifie l'état des 5 navigateurs CDP et retourne leur statut d'occupation.
    """
    from browser_pool import BROWSERS_CONFIG, get_lock_file, is_port_active
    status_list = []
    
    for b in BROWSERS_CONFIG:
        port = b["port"]
        active = is_port_active(port)
        lock_file = get_lock_file(port)
        locked = False
        
        # Test du verrou
        if os.path.exists(lock_file):
            import fcntl
            try:
                fd = open(lock_file, "a")
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                fcntl.flock(fd, fcntl.LOCK_UN)
                fd.close()
            except (OSError, IOError):
                locked = True

        accounts_str = ", ".join(b["accounts"])
        status_list.append({
            "port": port,
            "name": b["name"],
            "accounts": accounts_str,
            "active": active,
            "locked": locked
        })
        
    return status_list
