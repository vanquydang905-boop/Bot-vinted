import asyncio
import websockets
import json
import requests

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
        
        await asyncio.sleep(6)
        js = "Array.from(document.querySelectorAll('button')).map(b => b.innerText || b.getAttribute('aria-label')).join(', ')"
        resp = await wait_for_response(await send("Runtime.evaluate", {"expression": js, "returnByValue": True}))
        print("Buttons:", resp.get("result", {}).get("result", {}).get("value"))

asyncio.run(main())
