import asyncio
import json
import requests
import websockets
import os
import sys
import time
import base64

IMAGE_DIR = "/root/shein/image"
SKU = "sz2403276962416149"
PROMPT_PATH = "/root/shein/prompt_annonce.txt"

async def send_cdp(ws, method, params=None, req_id=1):
    msg = {"id": req_id, "method": method}
    if params:
        msg["params"] = params
    await ws.send(json.dumps(msg))
    while True:
        res = json.loads(await ws.recv())
        if res.get("id") == req_id:
            return res.get("result", {})

async def main():
    # 1. Obtenir URL WebSocket de l'onglet Meta AI
    r = requests.get("http://127.0.0.1:44231/json/list").json()
    meta_tabs = [item for item in r if "meta.ai" in item.get("url", "")]
    if not meta_tabs:
        print("[!] Onglet Meta AI introuvable sur le port 44231.")
        return
    
    ws_url = meta_tabs[0]["webSocketDebuggerUrl"]
    print(f"[✓] Connexion au WebSocket Meta AI : {ws_url}")
    
    async with websockets.connect(ws_url) as ws:
        await send_cdp(ws, "Runtime.enable", req_id=1)
        await send_cdp(ws, "DOM.enable", req_id=2)
        
        # Charger le prompt et info.txt
        with open(PROMPT_PATH, "r", encoding="utf-8") as f:
            prompt_tpl = f.read()
            
        info_file = os.path.join(IMAGE_DIR, SKU, "info.txt")
        with open(info_file, "r", encoding="utf-8", errors="ignore") as f:
            info_txt = f.read()
            
        prompt_text = prompt_tpl.replace("{TAILLE}", "Taille L").replace("{INFO_TXT}", info_txt)
        
        # Récupérer les photos/captures d'écran
        screen_dir = os.path.join(IMAGE_DIR, SKU, "image-screen")
        photos = sorted([os.path.join(screen_dir, f) for f in os.listdir(screen_dir) if f.endswith((".jpg", ".png"))])[:3]
        print(f"  Preparation envoi prompt Meta AI avec {len(photos)} photos...")
        
        # 2. Uploader les fichiers photos via input[type="file"] si present
        doc = await send_cdp(ws, "DOM.getDocument", req_id=3)
        root_node_id = doc["root"]["nodeId"]
        
        file_input_node = await send_cdp(ws, "DOM.querySelector", {"nodeId": root_node_id, "selector": 'input[type="file"]'}, req_id=4)
        file_node_id = file_input_node.get("nodeId")
        
        if file_node_id and photos:
            print(f"  [📸 Upload] Injection des {len(photos)} photo(s) dans input[type='file']...")
            await send_cdp(ws, "DOM.setFileInputFiles", {"files": photos, "nodeId": file_node_id}, req_id=5)
            await asyncio.sleep(2)
            
        # 3. Injecter le texte du prompt dans l'éditeur Meta AI
        js_type = """
        (() => {
            const el = document.querySelector('div[contenteditable="true"][data-testid="composer-input"], textarea[data-testid="composer-input"], div[contenteditable="true"]');
            if (!el) return false;
            el.focus();
            document.execCommand('insertText', false, %s);
            return true;
        })()
        """ % json.dumps(prompt_text)
        
        res_type = await send_cdp(ws, "Runtime.evaluate", {"expression": js_type}, req_id=6)
        print(f"  [✍️ Prompt] Focus & Insertion prompt : {res_type.get('result', {}).get('value')}")
        await asyncio.sleep(1)
        
        # 4. Cliquer sur le bouton d'envoi ou Simuler Touche Enter
        js_send = """
        (() => {
            const btn = document.querySelector('button[aria-label*="Envoyer"], button[aria-label*="Send"], button[data-testid="composer-send-button"]');
            if (btn && !btn.disabled) {
                btn.click();
                return "Click bouton send";
            }
            return "Bouton non cliquable";
        })()
        """
        res_send = await send_cdp(ws, "Runtime.evaluate", {"expression": js_send}, req_id=7)
        print(f"  [🚀 Envoi] Action envoi : {res_send.get('result', {}).get('value')}")
        
        if res_send.get("result", {}).get("value") != "Click bouton send":
            # Appuyer sur Entrée via Input.dispatchKeyEvent
            await send_cdp(ws, "Input.dispatchKeyEvent", {"type": "keyDown", "key": "Enter", "code": "Enter", "windowsVirtualKeyCode": 13}, req_id=8)
            await send_cdp(ws, "Input.dispatchKeyEvent", {"type": "keyUp", "key": "Enter", "code": "Enter", "windowsVirtualKeyCode": 13}, req_id=9)
            print("  [🚀 Envoi] Touche Entrée envoyée via CDP")
            
        # 5. Attendre la réponse contenant ANNONCE_FIN
        print("  [⏳ Attente] Attente de la génération de l'annonce par Meta AI...")
        fin = time.time() + 120
        while time.time() < fin:
            await asyncio.sleep(4)
            js_read = """
            (() => {
                const bodyText = document.body.innerText;
                if (bodyText.includes("ANNONCE_FIN")) {
                    return bodyText;
                }
                return "";
            })()
            """
            res_read = await send_cdp(ws, "Runtime.evaluate", {"expression": js_read}, req_id=10)
            text = res_read.get("result", {}).get("value", "")
            if "ANNONCE_FIN" in text:
                print("\n[✅ SUCCÈS Meta AI] Annonce générée reçue !")
                print("----------------------------------------")
                start_idx = text.find("ANNONCE_DEBUT")
                end_idx = text.find("ANNONCE_FIN") + len("ANNONCE_FIN")
                if start_idx != -1 and end_idx != -1:
                    raw_block = text[start_idx:end_idx]
                    print(raw_block)
                else:
                    print(text[-1500:])
                print("----------------------------------------")
                return True
                
        print("[❌ ÉCHEC Meta AI] Délai dépassé sans recevoir ANNONCE_FIN.")

if __name__ == "__main__":
    asyncio.run(main())
