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

        resp = await wait_for_response(await send("Network.getAllCookies"))
        cookies = resp.get("result", {}).get("cookies", [])
        print("Got", len(cookies), "cookies")
        
        # Format for requests
        cookie_str = "; ".join([f"{c['name']}={c['value']}" for c in cookies if "google.com" in c["domain"]])
        print("Cookies for google.com:", cookie_str[:50] + "...")

asyncio.run(main())
