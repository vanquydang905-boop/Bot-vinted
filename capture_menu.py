import asyncio
import websockets
import json
import requests
import time
import base64

async def main():
    try:
        r = requests.get("http://127.0.0.1:44231/json/list").json()
        drive_tabs = [t for t in r if t.get("type") == "page" and "drive.google.com" in t.get("url", "")]
        if not drive_tabs: return
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
        
        # Click Nouveau
        x, y = 81, 99
        await send("Input.dispatchMouseEvent", {"type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": 1})
        await asyncio.sleep(0.1)
        await send("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": x, "y": y, "button": "left", "clickCount": 1})
        
        await asyncio.sleep(1)
        
        # Capture
        resp = await wait_for_response(await send("Page.captureScreenshot"))
        data = resp.get("result", {}).get("data")
        if data:
            with open("/root/.gemini/antigravity-ide/brain/4d82def4-ef26-4c1d-8c4e-cda3b0229121/menu_screenshot.png", "wb") as f:
                f.write(base64.b64decode(data))

asyncio.run(main())
