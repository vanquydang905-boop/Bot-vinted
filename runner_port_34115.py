#!/usr/bin/env python3
"""
runner_port_34115.py - Runner dédié au navigateur AdsPower Port 34115
Comptes assignés : claravintage09, julie_last476, Helen_mil, marie_sdm963
Exécution 100% isolée sans aucun partage de port ni verrou inter-processus.
"""
import sys
from runner_base import run_dedicated_browser_runner

PORT = 34115
TABS = ["claravintage09", "julie_last476", "Helen_mil", "marie_sdm963"]
LOG_FILE = f"/root/shein/logs_worker_{PORT}.log"

if __name__ == "__main__":
    try:
        run_dedicated_browser_runner(port=PORT, tabs=TABS, log_file=LOG_FILE)
    except KeyboardInterrupt:
        print(f"\n[Arrêt] Runner Port {PORT} arrêté par l'utilisateur.")
        sys.exit(0)
