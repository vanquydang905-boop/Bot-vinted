"""
chrome_drive_upload.py
Upload description.txt vers Google Drive en utilisant le navigateur Chrome deja connecte.
Usage:
    python chrome_drive_upload.py --sku <SKU>
    python chrome_drive_upload.py --all
"""

import os
import sys
import time
import argparse
import asyncio
import json
import requests

if "DISPLAY" not in os.environ:
    os.environ["DISPLAY"] = ":10"

CDP_URL = "http://127.0.0.1:44231"
FLATLAY_BASE = "/root/shein/photo marie"


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


async def get_or_open_drive_tab():
    """Retourne le ws_url d'un onglet Google Drive ouvert, ou en cree un."""
    import websockets
    try:
        r = requests.get(f"{CDP_URL}/json/list", timeout=5).json()
    except Exception as e:
        log(f"[X] CDP non accessible : {e}")
        return None

    drive_tabs = [t for t in r if t.get("type") == "page" and "drive.google.com" in t.get("url", "")]
    if drive_tabs:
        return drive_tabs[0]["webSocketDebuggerUrl"]

    log("  [Drive] Ouverture d'un nouvel onglet Google Drive...")
    ws_url_global = r[0]["webSocketDebuggerUrl"]
    async with websockets.connect(ws_url_global, max_size=2**25) as ws:
        await ws.send(json.dumps({
            "id": 1, "method": "Target.createTarget",
            "params": {"url": "https://drive.google.com/drive/my-drive"}
        }))
        await ws.recv()
    await asyncio.sleep(5)
    r2 = requests.get(f"{CDP_URL}/json/list", timeout=5).json()
    drive_tabs = [t for t in r2 if t.get("type") == "page" and "drive.google.com" in t.get("url", "")]
    return drive_tabs[0]["webSocketDebuggerUrl"] if drive_tabs else None


async def upload_via_cdp(ws_url, desc_path):
    import websockets
    async with websockets.connect(ws_url, max_size=2**25, ping_timeout=30) as ws:
        req_id = 1

        async def send(method, params=None):
            nonlocal req_id
            msg = {"id": req_id, "method": method, "params": params or {}}
            await ws.send(json.dumps(msg))
            req_id += 1
            return msg["id"]

        async def recv_until(target_id, timeout=15):
            deadline = time.time() + timeout
            while time.time() < deadline:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=1.0)
                    msg = json.loads(raw)
                    if msg.get("id") == target_id:
                        return msg
                except asyncio.TimeoutError:
                    continue
            return None

        async def eval_js(js, timeout=10):
            mid = await send("Runtime.evaluate", {
                "expression": js, "returnByValue": True,
                "awaitPromise": True, "userGesture": True
            })
            return await recv_until(mid, timeout=timeout + 5)

        # Activer interception file chooser
        await recv_until(await send("Page.setInterceptFileChooserDialog", {"enabled": True}))
        await send("Page.bringToFront")
        await asyncio.sleep(1.5)

        # Clic bouton Nouveau
        log("  [Drive] Clic sur 'Nouveau'...")
        r1 = await eval_js("""
        (() => {
            const btns = Array.from(document.querySelectorAll('button,[role="button"]'));
            const b = btns.find(b => /^(Nouveau|New|\\+ Nouveau)$/.test((b.innerText||'').trim()));
            if (b) { b.click(); return true; }
            const aria = document.querySelector('[aria-label="Nouveau"],[aria-label="New"]');
            if (aria) { aria.click(); return true; }
            return false;
        })()
        """)
        if not r1.get("result", {}).get("result", {}).get("value"):
            log("  [X] Bouton 'Nouveau' non trouve.")
            return False

        await asyncio.sleep(1.5)

        # Clic Importer un fichier
        log("  [Drive] Clic sur 'Importer un fichier'...")
        r2 = await eval_js("""
        (() => {
            const all = Array.from(document.querySelectorAll('li,[role="menuitem"],span'));
            const el = all.find(e => {
                const t = (e.innerText||e.textContent||'').trim();
                return t === 'Importer un fichier' || t === 'File upload';
            });
            if (el) { el.click(); return true; }
            return false;
        })()
        """)
        if not r2.get("result", {}).get("result", {}).get("value"):
            log("  [X] Bouton 'Importer un fichier' non trouve.")
            return False

        # Attendre FileChooserOpened
        log("  [Drive] En attente du selecteur de fichier...")
        deadline = time.time() + 12
        while time.time() < deadline:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=1.5)
                msg = json.loads(raw)
                if msg.get("method") == "Page.fileChooserOpened":
                    log("  [Drive] Selecteur intercepte ! Injection du fichier...")
                    fid = await send("Page.handleFileChooser", {
                        "action": "accept",
                        "files": [desc_path]
                    })
                    await recv_until(fid, timeout=10)
                    log(f"  [OK] Fichier envoye : {os.path.basename(desc_path)}")
                    await asyncio.sleep(4)
                    return True
            except asyncio.TimeoutError:
                continue

        log("  [X] Timeout - selecteur non recu.")
        return False


async def upload_sku(sku):
    desc_path = os.path.join(FLATLAY_BASE, sku, "flatlay", "description.txt")
    if not os.path.exists(desc_path):
        log(f"[X] description.txt introuvable : {desc_path}")
        return False

    log(f"\n[>] Upload Drive pour SKU : {sku}")
    ws_url = await get_or_open_drive_tab()
    if not ws_url:
        log("[X] Onglet Drive inaccessible.")
        return False

    success = await upload_via_cdp(ws_url, desc_path)
    if success:
        log(f"  [OK] Upload reussi pour {sku}")
    else:
        log(f"  [X] Echec upload pour {sku}")
    return success


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sku", type=str, help="SKU unique a uploader")
    parser.add_argument("--all", action="store_true", help="Uploader tous les SKUs avec description.txt")
    args = parser.parse_args()

    if args.all:
        skus = []
        for sku_dir in sorted(os.listdir(FLATLAY_BASE)):
            desc = os.path.join(FLATLAY_BASE, sku_dir, "flatlay", "description.txt")
            if os.path.exists(desc):
                skus.append(sku_dir)
        log(f"[Liste] {len(skus)} SKU(s) a uploader...")
        for i, sku in enumerate(skus, 1):
            log(f"\n[{i}/{len(skus)}] Traitement de {sku}...")
            asyncio.run(upload_sku(sku))
            time.sleep(2)
        log("\n[DONE] Tous les uploads termines !")
    elif args.sku:
        success = asyncio.run(upload_sku(args.sku))
        sys.exit(0 if success else 1)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
