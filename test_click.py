import asyncio
import websockets
import json
import requests
import time

async def main():
    try:
        r = requests.get("http://127.0.0.1:44231/json/list").json()
        drive_tabs = [t for t in r if t.get("type") == "page" and "drive.google.com" in t.get("url", "")]
        ws_url = drive_tabs[0]["webSocketDebuggerUrl"]
    except: return

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

        await send("Page.bringToFront")
        await asyncio.sleep(1)
        
        js = """
        (() => {
            const btn = Array.from(document.querySelectorAll('button')).find(b => (b.innerText||'').includes('Nouveau'));
            if (btn) {
                btn.click();
                return "Clicked Nouveau";
            }
            return "Not found";
        })()
        """
        resp = await wait_for_response(await send("Runtime.evaluate", {"expression": js, "returnByValue": True}))
        print(resp)
        
        await asyncio.sleep(1)
        
        js2 = """
        (() => {
            const btn = Array.from(document.querySelectorAll('*')).find(b => (b.innerText||'').includes('Importer un fichier') || (b.innerText||'').includes('upload'));
            if (btn) {
                btn.click();
                return "Clicked Importer";
            }
            return "Importer not found";
        })()
        """
        resp2 = await wait_for_response(await send("Runtime.evaluate", {"expression": js2, "returnByValue": True}))
        print(resp2)

asyncio.run(main())
