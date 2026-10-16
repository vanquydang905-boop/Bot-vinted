#!/usr/bin/env python3
"""
runner_port_38049.py - Runner dédié au navigateur AdsPower Port 38049
Comptes assignés : faby_grb, lea_vani, lisa_llc, eica_ph, oria_nel
Exécution 100% isolée sans aucun partage de port ni verrou inter-processus.
"""
import sys
from runner_base import run_dedicated_browser_runner

PORT = 38049
TABS = ["faby_grb", "lea_vani", "lisa_llc", "eica_ph", "oria_nel"]
LOG_FILE = f"/root/shein/logs_worker_{PORT}.log"

if __name__ == "__main__":
    try:
        run_dedicated_browser_runner(port=PORT, tabs=TABS, log_file=LOG_FILE)
    except KeyboardInterrupt:
        print(f"\n[Arrêt] Runner Port {PORT} arrêté par l'utilisateur.")
        sys.exit(0)
