import asyncio
import websockets
import json
import requests
import time

async def main():
    try:
        r = requests.put("http://127.0.0.1:44231/json/new?url=https://drive.google.com/", timeout=5).json()
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
            while True:
                resp = json.loads(await ws.recv())
                if resp.get("id") == msg["id"]:
                    return resp

        # Naviguer
        print("Navigation...")
        await send("Page.navigate", {"url": "https://drive.google.com/drive/folders/1Edqavh2ORhg5n5R-zZAj8H-RKK8lV-S0"})
        await asyncio.sleep(4)

        # Récupérer le document
        doc = await send("DOM.getDocument")
        root_id = doc["result"]["root"]["nodeId"]
        
        # Trouver l'input file
        node = await send("DOM.querySelector", {"nodeId": root_id, "selector": "input[type='file']"})
        print("Input file node:", node)
        
        input_node_id = node.get("result", {}).get("nodeId")
        if input_node_id:
            res = await send("DOM.setFileInputFiles", {
                "files": ["/root/shein/photo marie/sz2403276962416149/flatlay/description.txt"],
                "nodeId": input_node_id
            })
            print("Set file files:", res)
        else:
            print("Aucun input file trouvé")

asyncio.run(main())
