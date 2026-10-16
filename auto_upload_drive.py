import time
import subprocess
import sys

FOLDER_ID = "1Edqavh2ORhg5n5R-zZAj8H-RKK8lV-S0"
CMD = ["/root/venv/bin/python", "/root/shein/upload_to_gdrive.py", "--folder-id", FOLDER_ID]

print(f"[{time.strftime('%H:%M:%S')}] Démarrage de la tentative de synchronisation Google Drive...", flush=True)

while True:
    res = subprocess.run(CMD, capture_output=True, text=True)
    output = res.stdout.strip()
    if output:
        print(output, flush=True)
        
    if "Synchronisation Google Drive terminée" in output:
        print(f"\n[{time.strftime('%H:%M:%S')}] 🎉 TOUS LES DOSSIERS ONT ÉTÉ TÉLÉVERSÉS AVEC SUCCÈS SUR GOOGLE DRIVE !", flush=True)
        break
        
    if "ACCÈS NON PARTAGÉ" in output:
        print(f"[{time.strftime('%H:%M:%S')}] En attente du partage du dossier Google Drive avec vinted@sheun-vinted.iam.gserviceaccount.com... (nouvelle tentative dans 10s)", flush=True)
        
    time.sleep(10)
