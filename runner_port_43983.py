#!/usr/bin/env python3
"""
runner_port_43983.py - Runner dédié au navigateur AdsPower Port 43983
Comptes assignés : elya_soc, laura_vsni, viki_sph, nice_mam
Exécution 100% isolée sans aucun partage de port ni verrou inter-processus.
"""
import sys
import requests
from runner_base import run_dedicated_browser_runner

PROFILE_ID = "k1fcj5nk"
FALLBACK_PORT = 34267
TABS = ["elya_soc", "laura_vsni", "viki_sph", "nice_mam"]

def get_live_port():
    try:
        r = requests.get(f"http://127.0.0.1:50325/api/v1/browser/active?user_id={PROFILE_ID}", timeout=2.0).json()
        if r.get("code") == 0 and r.get("data", {}).get("status") == "Active":
            p = int(r["data"]["debug_port"])
            return p
    except Exception:
        pass
    return FALLBACK_PORT

PORT = get_live_port()
LOG_FILE = f"/root/shein/logs_worker_43983.log"

if __name__ == "__main__":
    try:
        print(f"🚀 [Runner elya_soc] Port dynamique résolu : {PORT}")
        run_dedicated_browser_runner(port=PORT, tabs=TABS, log_file=LOG_FILE)
    except KeyboardInterrupt:
        print(f"\n[Arrêt] Runner Port {PORT} arrêté par l'utilisateur.")
        sys.exit(0)
