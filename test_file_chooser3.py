import asyncio
import websockets
import json
import requests
import time

async def main():
    try:
        r = requests.put("http://127.0.0.1:44231/json/new?url=https://drive.google.com/drive/folders/1Edqavh2ORhg5n5R-zZAj8H-RKK8lV-S0", timeout=5).json()
        ws_url = r["webSocketDebuggerUrl"]
    except Exception as e:
        print("Erreur création page:", e)
        return

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
                    
        # Intercept file chooser
        await wait_for_response(await send("Page.setInterceptFileChooserDialog", {"enabled": True}))
        
        print("Waiting for page load...")
        await asyncio.sleep(6)
        
        async def click_element(js_selector):
            js = f"""
            (() => {{
                const el = {js_selector};
                if (!el) return null;
                const rect = el.getBoundingClientRect();
                return {{x: rect.x + rect.width/2, y: rect.y + rect.height/2}};
            }})()
            """
            resp = await wait_for_response(await send("Runtime.evaluate", {"expression": js, "returnByValue": True}))
            val = resp.get("result", {}).get("result", {}).get("value")
            if not val:
                print("Element non trouvé:", js_selector)
                return False
                
            x, y = val["x"], val["y"]
            print(f"Clicking at {x}, {y}")
            await send("Input.dispatchMouseEvent", {"type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": 1})
            await asyncio.sleep(0.1)
            await send("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": x, "y": y, "button": "left", "clickCount": 1})
            return True

        print("Clicking 'Nouveau'...")
        new_btn_js = "Array.from(document.querySelectorAll('button')).find(b => b.innerText.includes('Nouveau') || b.innerText.includes('New'))"
        if not await click_element(new_btn_js):
            print("Echec clique Nouveau")
            return
            
        await asyncio.sleep(1)
        
        print("Clicking 'Importer un fichier'...")
        upload_btn_js = "Array.from(document.querySelectorAll('[role=\"menuitem\"]')).find(b => b.innerText.includes('Importer un fichier') || b.innerText.includes('File upload'))"
        if not await click_element(upload_btn_js):
            print("Echec clique Importer")
            return

        print("Waiting for FileChooserOpened event...")
        try:
            for _ in range(30):
                msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=1.0))
                if msg.get("method") == "Page.fileChooserOpened":
                    print("Event reçu!", msg)
                    resp = await wait_for_response(await send("Page.handleFileChooser", {
                        "action": "accept",
                        "files": ["/root/shein/photo marie/sz2403276962416149/flatlay/description.txt"]
                    }))
                    print("Fichier accepté:", resp)
                    break
        except asyncio.TimeoutError:
            print("Timeout en attendant FileChooserOpened")
        
        print("Fini!")

asyncio.run(main())
