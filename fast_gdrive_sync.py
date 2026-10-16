import os
import sys
import argparse
import time
import json
import asyncio
import websockets
import requests

if "DISPLAY" not in os.environ or os.environ["DISPLAY"] == ":1":
    os.environ["DISPLAY"] = ":10"

import pyautogui

def log(msg):
    print(msg, flush=True)

async def upload_file_via_gui(sku):
    desc_path = f"/root/shein/photo marie/{sku}/flatlay/description.txt"
    if not os.path.exists(desc_path):
        log(f"  [❌ Drive] Fichier introuvable: {desc_path}")
        return False
        
    try:
        import websockets
        r = requests.get("http://127.0.0.1:44231/json/list", timeout=5).json()
        drive_tabs = [t for t in r if t.get("type") == "page" and "https://drive.google.com/drive" in t.get("url", "")]
        if not drive_tabs:
            log("  [☁️ Drive] Aucun onglet Drive ouvert, création d'un nouvel onglet...")
            ws_url_global = r[0]["webSocketDebuggerUrl"]
            import websockets
            async with websockets.connect(ws_url_global, max_size=2**25) as ws:
                await ws.send(json.dumps({"id": 1, "method": "Target.createTarget", "params": {"url": "https://drive.google.com/drive/my-drive"}}))
                msg = json.loads(await ws.recv())
                if "result" in msg and "targetId" in msg["result"]:
                    # Wait a bit for the tab to load
                    await asyncio.sleep(4)
                    r = requests.get("http://127.0.0.1:44231/json/list", timeout=5).json()
                    drive_tabs = [t for t in r if t.get("type") == "page" and "https://drive.google.com/drive" in t.get("url", "")]
            
        if not drive_tabs:
            log("  [❌ Drive] Échec de l'ouverture de l'onglet Google Drive.")
            return False
            
        ws_url = drive_tabs[0]["webSocketDebuggerUrl"]
    except Exception as e:
        log(f"  [❌ Drive] Erreur connexion CDP: {e}")
        return False

    async with websockets.connect(ws_url, max_size=2**25) as ws:
        req_id = 1
        async def send(method, params=None):
            nonlocal req_id
            msg = {"id": req_id, "method": method, "params": params or {}}
            await ws.send(json.dumps(msg))
            req_id += 1
            return msg["id"]
            
        async def wait_for_response(expected_id):
            while True:
                msg = json.loads(await ws.recv())
                if msg.get("id") == expected_id:
                    return msg

        log("  [☁️ Drive] Activation de l'onglet...")
        await send("Page.bringToFront")
        await asyncio.sleep(1)
        
        # Focus de la fenêtre SunBrowser via xdotool
        os.system('xdotool search --class "SunBrowser" windowactivate --sync 2>/dev/null || xdotool search --class "Chromium" windowactivate --sync 2>/dev/null || true')
        await asyncio.sleep(1)
        
        # Click Nouveau
        log("  [☁️ Drive] Clic sur Nouveau...")
        js1 = """
        (() => {
            const btn = Array.from(document.querySelectorAll('button')).find(b => (b.innerText||'').includes('Nouveau') || (b.innerText||'').includes('New'));
            if (btn) { btn.click(); return true; }
            return false;
        })()
        """
        resp = await wait_for_response(await send("Runtime.evaluate", {"expression": js1, "returnByValue": True, "userGesture": True}))
        if not resp.get("result", {}).get("result", {}).get("value"):
            log("  [❌ Drive] Bouton Nouveau introuvable.")
            return False
            
        await asyncio.sleep(1)
        
        # Click Importer
        log("  [☁️ Drive] Clic sur Importer un fichier...")
        js2 = """
        (() => {
            const btn = Array.from(document.querySelectorAll('*')).find(b => (b.innerText||'').includes('Importer un fichier') || (b.innerText||'').toLowerCase().includes('upload'));
            if (btn) { btn.click(); return true; }
            return false;
        })()
        """
        resp2 = await wait_for_response(await send("Runtime.evaluate", {"expression": js2, "returnByValue": True, "userGesture": True}))
        if not resp2.get("result", {}).get("result", {}).get("value"):
            log("  [❌ Drive] Bouton Importer introuvable.")
            return False

        log("  [☁️ Drive] Remplissage du dialogue d'upload...")
        time.sleep(2.5) # Attente de l'ouverture du dialogue GTK
        
        # Focus la barre de chemin du fichier
        pyautogui.hotkey('ctrl', 'l')
        time.sleep(0.5)
        
        # Effacer l'existant
        pyautogui.press('backspace')
        time.sleep(0.2)
        
        # Taper le chemin absolu
        pyautogui.write(desc_path, interval=0.02)
        time.sleep(0.5)
        
        # Entrée pour valider
        pyautogui.press('enter')
        time.sleep(0.5)
        # S'il y a un autre popup ou si Enter dans la barre valide direct (GTK valide direct le fichier si absolu)
        
        log("  [✅ Drive] Fichier soumis à l'upload.")
        return True

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sku", type=str, required=True, help="SKU de l'article")
    args = parser.parse_args()
    
    log(f"[▶️] Synchronisation Drive GUI pour {args.sku}")
    
    # Needs DISPLAY to be set for pyautogui/xdotool
    if "DISPLAY" not in os.environ:
        os.environ["DISPLAY"] = ":1"
    
    success = asyncio.run(upload_file_via_gui(args.sku))
    
    if not success:
        sys.exit(1)

if __name__ == "__main__":
    main()
