#!/usr/bin/env python3
"""
Orchestrateur Multi-Ports (4 Navigateurs AdsPower)
Lance et supervise en parallèle la génération complète (Flat-Lay Gemini + Meta AI Rédaction)
sur les 4 ports disponibles : 43983, 34115, 38049, 42677.
"""
import os
import sys
import time
import json
import subprocess
import signal

PYTHON_BIN = "/root/venv/bin/python"
WORKFLOW_SCRIPT = "/root/shein/workflow.py"
STATUS_FILE = "/root/shein/multi_ports_status.json"
ORCHESTRATOR_LOG = "/root/shein/orchestrator.log"

WORKERS_CONFIG = [
    {
        "name": "Worker 1 (Port 43983)",
        "port": 43983,
        "script": "/root/shein/runner_port_43983.py",
        "tabs": "elya_soc,laura_vsni,viki_sph,nice_mam",
        "log_file": "/root/shein/logs_worker_43983.log"
    },
    {
        "name": "Worker 2 (Port 34115)",
        "port": 34115,
        "script": "/root/shein/runner_port_34115.py",
        "tabs": "claravintage09,julie_last476,Helen_mil,marie_sdm963",
        "log_file": "/root/shein/logs_worker_34115.log"
    },
    {
        "name": "Worker 3 (Port 38049)",
        "port": 38049,
        "script": "/root/shein/runner_port_38049.py",
        "tabs": "faby_grb,lea_vani,lisa_llc,eica_ph,oria_nel",
        "log_file": "/root/shein/logs_worker_38049.log"
    },
    {
        "name": "Worker 4 (Port 42677)",
        "port": 42677,
        "script": "/root/shein/runner_port_42677.py",
        "tabs": "yurih_mlf,alix_vrt,jade_huo,neli_fyu,vera_los",
        "log_file": "/root/shein/logs_worker_42677.log"
    }
]

def log(msg):
    ts = time.strftime("[%Y-%m-%d %H:%M:%S]")
    line = f"{ts} {msg}"
    print(line, flush=True)
    try:
        with open(ORCHESTRATOR_LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass

import asyncio
import websockets
import requests

def auto_dismiss_meta_popups():
    """Ferme les modales et alertes résiduelles sur les onglets Meta AI pour garantir la non-obstruction."""
    async def _dismiss():
        for port in [43983, 34115, 38049, 42677]:
            try:
                r = requests.get(f"http://127.0.0.1:{port}/json/list", timeout=1.0).json()
                meta_tabs = [t for t in r if "meta.ai" in t.get("url", "")]
                if not meta_tabs: continue
                ws_url = meta_tabs[0]["webSocketDebuggerUrl"]
                async with websockets.connect(ws_url, close_timeout=1.0) as ws:
                    js = """
                    (() => {
                        let count = 0;
                        for (const b of document.querySelectorAll("button")) {
                            const txt = (b.innerText || "").trim().toLowerCase();
                            if (txt === "abandonner" || txt === "quitter") { b.click(); count++; }
                        }
                        const bd = document.querySelector('button[data-testid="connect-apps-dismiss-button"]');
                        if (bd) { bd.click(); count++; }
                        return count;
                    })()
                    """
                    await ws.send(json.dumps({"id": 99, "method": "Runtime.evaluate", "params": {"expression": js, "returnByValue": True}}))
                    res = json.loads(await asyncio.wait_for(ws.recv(), timeout=1.5))
                    cnt = res.get("result", {}).get("result", {}).get("value", 0)
                    if cnt > 0:
                        log(f"🛡️ [Watchdog] {cnt} alerte(s) bloquante(s) fermée(s) sur Meta AI (port {port})")
            except Exception:
                pass
    try:
        asyncio.run(_dismiss())
    except Exception:
        pass

# État d'avancement des workers
active_procs = {}

def start_worker(cfg):
    cmd = [
        PYTHON_BIN, "-u", cfg["script"]
    ]
    log_fp = open(cfg["log_file"], "a", encoding="utf-8")
    proc = subprocess.Popen(cmd, cwd="/root/shein", stdout=log_fp, stderr=subprocess.STDOUT)
    log(f"🚀 [{cfg['name']}] Démarré avec PID {proc.pid} via {cfg['script']}")
    return proc, log_fp

def get_last_activity(log_path):
    if not os.path.exists(log_path):
        return "Initialisation..."
    try:
        with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
            lines = [l.strip() for l in f.readlines() if l.strip()]
            for l in reversed(lines):
                if any(k in l for k in ["SKU :", "SUCCÈS", "Meta AI", "Gemini", "Drive", "DÉJÀ", "Étape", "Sheet"]):
                    return l[:100]
            if lines:
                return lines[-1][:100]
    except Exception:
        pass
    return "En attente..."

def cleanup(sig=None, frame=None):
    log("\n🛑 Arrêt demandé de l'orchestrateur. Fermeture des 4 workers...")
    for cfg in WORKERS_CONFIG:
        p_info = active_procs.get(cfg["port"])
        if p_info:
            proc, fp = p_info
            if proc.poll() is None:
                try:
                    proc.terminate()
                    time.sleep(0.5)
                    if proc.poll() is None:
                        proc.kill()
                except Exception:
                    pass
            try: fp.close()
            except Exception: pass
    log("Toutes les instances ont été arrêtées.")
    sys.exit(0)

signal.signal(signal.SIGINT, cleanup)
signal.signal(signal.SIGTERM, cleanup)

def main():
    log("=================================================================")
    log("⭐ DÉMARRAGE ORCHESTRATEUR MULTI-PORTS (4 NAVIGATEURS DISPONIBLES)")
    log("=================================================================")

    # 1. Démarrer les 4 workers
    for cfg in WORKERS_CONFIG:
        proc, fp = start_worker(cfg)
        active_procs[cfg["port"]] = (proc, fp)
        time.sleep(1.0)

    # 2. Boucle de surveillance active jusqu'à la fin
    iter_count = 0
    while True:
        iter_count += 1
        all_done = True
        status_report = []

        # Watchdog auto-amélioration : nettoyer les popups toutes les 25s
        if iter_count % 5 == 0:
            auto_dismiss_meta_popups()

        for cfg in WORKERS_CONFIG:
            port = cfg["port"]
            proc, fp = active_procs.get(port, (None, None))
            retcode = proc.poll() if proc else -1
            is_running = (retcode is None)

            # Auto-amélioration : détection de blocage d'un worker (> 7 minutes sans log)
            if is_running:
                try:
                    mtime = os.path.getmtime(cfg["log_file"])
                    idle_secs = time.time() - mtime
                    if idle_secs > 420:
                        log(f"⚠️ [{cfg['name']}] Inactif depuis {int(idle_secs)}s (> 7 min). Relance watchdog...")
                        try:
                            proc.terminate()
                            time.sleep(1)
                            if proc.poll() is None:
                                proc.kill()
                        except Exception:
                            pass
                        try: fp.close()
                        except Exception: pass
                        new_proc, new_fp = start_worker(cfg)
                        active_procs[port] = (new_proc, new_fp)
                        proc = new_proc
                        is_running = True
                except Exception:
                    pass

            if is_running:
                all_done = False
                state_str = f"🟢 EN COURS (PID {proc.pid})"
            elif retcode != 0:
                log(f"⚠️ [{cfg['name']}] Sortie anormale (code {retcode}). Relance automatique dans 3s...")
                time.sleep(3)
                try: fp.close()
                except Exception: pass
                new_proc, new_fp = start_worker(cfg)
                active_procs[port] = (new_proc, new_fp)
                all_done = False
                state_str = f"🔄 REDÉMARRÉ (PID {new_proc.pid})"
            else:
                state_str = f"🏁 TERMINÉ AVEC SUCCÈS (code 0)"

            activity = get_last_activity(cfg["log_file"])
            status_report.append({
                "worker": cfg["name"],
                "port": port,
                "tabs": cfg["tabs"],
                "pid": proc.pid if proc else None,
                "running": is_running,
                "state": state_str,
                "last_activity": activity
            })

        # Sauvegarder l'état dans JSON pour consultation externe
        try:
            with open(STATUS_FILE, "w", encoding="utf-8") as f:
                json.dump({"timestamp": time.time(), "workers": status_report}, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

        # Affichage régulier dans le terminal / log toutes les 15 secondes
        if iter_count % 3 == 0:
            log("--- [📊 POINT DE SITUATION SURVEILLANCE] ---")
            for sr in status_report:
                log(f"  • {sr['worker']} : {sr['state']} | {sr['last_activity']}")

        if all_done:
            log("🎉 TOUS LES WORKERS ONT TERMINÉ LEUR TRAITEMENT SUR L'ENSEMBLE DES ONGLETS !")
            break

        time.sleep(5)

if __name__ == "__main__":
    main()
