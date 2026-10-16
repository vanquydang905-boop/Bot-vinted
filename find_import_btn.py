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
        
        # Click Nouveau
        x, y = 81, 99
        await send("Input.dispatchMouseEvent", {"type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": 1})
        await asyncio.sleep(0.1)
        await send("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": x, "y": y, "button": "left", "clickCount": 1})
        
        await asyncio.sleep(1)
        
        # Dump elements
        js = """
        Array.from(document.querySelectorAll('*'))
             .filter(el => {
                 const text = (el.innerText || '').toLowerCase();
                 return text.includes('importer') || text.includes('upload');
             })
             .map(el => {
                 const rect = el.getBoundingClientRect();
                 return { tag: el.tagName, text: el.innerText.substring(0, 30), rect: {x: rect.x, y: rect.y, w: Math.round(rect.width), h: Math.round(rect.height)} };
             })
             .filter(item => item.rect.w > 0 && item.rect.h > 0)
        """
        resp = await wait_for_response(await send("Runtime.evaluate", {"expression": js, "returnByValue": True}))
        print("Elements found:", json.dumps(resp.get("result", {}).get("result", {}).get("value"), indent=2))

asyncio.run(main())
