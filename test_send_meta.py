import asyncio
import json
import requests
import websockets
import time

async def send_cdp(ws, method, params=None, req_id=1):
    msg = {"id": req_id, "method": method}
    if params:
        msg["params"] = params
    await ws.send(json.dumps(msg))
    while True:
        res = json.loads(await ws.recv())
        if res.get("id") == req_id:
            return res.get("result", {})

async def test_meta_events():
    r = requests.get("http://127.0.0.1:44231/json/list").json()
    meta_tab = [item for item in r if "meta.ai" in item.get("url", "")][0]
    ws_url = meta_tab["webSocketDebuggerUrl"]
    
    async with websockets.connect(ws_url) as ws:
        await send_cdp(ws, "Runtime.enable", req_id=1)
        
        # Charger le prompt réel
        with open("/root/shein/prompt_annonce.txt", "r", encoding="utf-8") as f:
            prompt_tpl = f.read()
        with open("/root/shein/image/sz2403276962416149/info.txt", "r", encoding="utf-8", errors="ignore") as f:
            info_txt = f.read()
            
        prompt = prompt_tpl.replace("{TAILLE}", "Taille L").replace("{INFO_TXT}", info_txt)
        
        js_insert = """
        (() => {
            const el = document.querySelector('div[contenteditable="true"][data-testid="composer-input"], textarea[data-testid="composer-input"]');
            if (!el) return "No el";
            el.focus();
            document.execCommand('selectAll', false, null);
            document.execCommand('insertText', false, %s);
            ['input', 'change', 'keydown', 'keyup'].forEach(ev => {
                el.dispatchEvent(new Event(ev, { bubbles: true, cancelable: true }));
            });
            return "Inserted and events dispatched";
        })()
        """ % json.dumps(prompt)
        
        res_type = await send_cdp(ws, "Runtime.evaluate", {"expression": js_insert}, req_id=2)
        print("Type result:", res_type.get("result", {}).get("value"))
        await asyncio.sleep(1)
        
        js_click = """
        (() => {
            const btn = document.querySelector('button[aria-label*="Envoyer"], button[aria-label*="Send"], button[data-testid="composer-send-button"], button.bg-linear-to-r');
            if (btn) {
                btn.removeAttribute("disabled");
                btn.disabled = false;
                btn.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
                btn.click();
                return "Btn clicked!";
            }
            return "No button";
        })()
        """
        res_click = await send_cdp(ws, "Runtime.evaluate", {"expression": js_click}, req_id=3)
        print("Click result:", res_click.get("result", {}).get("value"))
        
        fin = time.time() + 45
        while time.time() < fin:
            await asyncio.sleep(4)
            res_text = await send_cdp(ws, "Runtime.evaluate", {"expression": "document.body.innerText"}, req_id=4)
            t = res_text.get("result", {}).get("value", "")
            
            # Chercher le DERNIER ANNONCE_DEBUT et ANNONCE_FIN
            start_idx = t.rfind("ANNONCE_DEBUT")
            end_idx = t.rfind("ANNONCE_FIN")
            
            # Vérifier qu'ils existent et que ANNONCE_FIN est situé APRES le second ANNONCE_DEBUT
            if start_idx != -1 and end_idx > start_idx and "titre" in t[start_idx:end_idx]:
                raw_json_block = t[start_idx:end_idx + len("ANNONCE_FIN")]
                print("\n[✅ SUCCESS AI GENERATED BLOCK]:")
                print(raw_json_block)
                return True
                
        print("\n[❌ TIMEOUT] Pas de réponse IA générée.")

if __name__ == "__main__":
    asyncio.run(test_meta_events())
