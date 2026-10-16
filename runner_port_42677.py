#!/usr/bin/env python3
"""
runner_port_42677.py - Runner dédié au navigateur AdsPower Port 42677
Comptes assignés : yurih_mlf, alix_vrt, jade_huo, neli_fyu, vera_los
Exécution 100% isolée sans aucun partage de port ni verrou inter-processus.
"""
import sys
from runner_base import run_dedicated_browser_runner

PORT = 42677
TABS = ["yurih_mlf", "alix_vrt", "jade_huo", "neli_fyu", "vera_los"]
LOG_FILE = f"/root/shein/logs_worker_{PORT}.log"

if __name__ == "__main__":
    try:
        run_dedicated_browser_runner(port=PORT, tabs=TABS, log_file=LOG_FILE)
    except KeyboardInterrupt:
        print(f"\n[Arrêt] Runner Port {PORT} arrêté par l'utilisateur.")
        sys.exit(0)
