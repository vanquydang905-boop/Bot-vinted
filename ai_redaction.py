import os
import sys
import time
import json
import re
import base64
import requests
import asyncio
import websockets
import concurrent.futures

JS_COLLER = """
(fichiers) => {
  const dt = new DataTransfer();
  for (const f of fichiers) {
    const bin = atob(f.data);
    const octets = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) octets[i] = bin.charCodeAt(i);
    dt.items.add(new File([octets], f.nom, { type: f.type || 'image/jpeg' }));
  }
  const zone = document.querySelector('div[contenteditable="true"][data-testid="composer-input"]')
            || document.querySelector('textarea[data-testid="composer-input"]')
            || document.querySelector('div[contenteditable="true"]');
  if (!zone) return false;
  zone.focus();
  zone.dispatchEvent(new ClipboardEvent('paste',
      { clipboardData: dt, bubbles: true, cancelable: true }));
  return true;
}
"""

def extract_and_validate_ad(raw_text):
    if not raw_text or not raw_text.strip():
        return False, "Réponse IA vide.", None

    block = raw_text.strip()
    if "ANNONCE_DEBUT" in block and "ANNONCE_FIN" in block:
        start_block = block.rfind("ANNONCE_DEBUT") + len("ANNONCE_DEBUT")
        end_block = block.rfind("ANNONCE_FIN")
        if end_block > start_block:
            block = block[start_block:end_block].strip()

    first_brace = block.find("{")
    last_brace = block.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        json_str = block[first_brace:last_brace + 1].strip()
    else:
        json_str = block.strip()
        if not json_str.startswith("{"):
            json_str = "{" + json_str
        if not json_str.endswith("}"):
            json_str = json_str + "}"

    try:
        data = json.loads(json_str, strict=False)
    except Exception:
        # Tentative de nettoyage automatique (virgules superflues, markdown fences, guillemets simples)
        cleaned_json = re.sub(r",\s*([\}\]])", r"\1", json_str)
        cleaned_json = re.sub(r"^```(?:json)?\s*", "", cleaned_json).strip()
        cleaned_json = re.sub(r"\s*```$", "", cleaned_json).strip()
        try:
            data = json.loads(cleaned_json, strict=False)
        except Exception:
            # Fallback regex robuste pour extraire directement les clés si le JSON a une anomalie syntaxique
            data = {}
            for field in ["titre", "description", "categorie", "couleur"]:
                m = re.search(rf'"{field}"\s*:\s*"([^"]+)"', block, re.DOTALL)
                if not m:
                    m = re.search(rf"'{field}'\s*:\s*'([^']+)'", block, re.DOTALL)
                if m:
                    data[field] = m.group(1).strip()
                    
            m_types = re.search(r'"types_vinted"\s*:\s*\[(.*?)\]', block, re.DOTALL)
            if not m_types:
                m_types = re.search(r"'types_vinted'\s*:\s*\[(.*?)\]", block, re.DOTALL)
            if m_types:
                data["types_vinted"] = [item.strip().strip('"\'') for item in m_types.group(1).split(",") if item.strip()]
            else:
                data["types_vinted"] = []

            if not data.get("titre") or not data.get("description"):
                return False, f"JSON invalide renvoyé par l'IA et impossible à réparer", None

    required_keys = ["titre", "description", "categorie", "types_vinted", "couleur"]
    for k in required_keys:
        if k not in data:
            return False, f"Clé requise '{k}' manquante dans la réponse JSON.", None

    cat_raw = str(data.get("categorie", "")).lower().strip()
    if "robe" in cat_raw:
        cat = "ROBE"
    elif any(x in cat_raw for x in ["jupe", "pantalon", "short", "bas", "jean"]):
        cat = "BAS"
    elif any(x in cat_raw for x in ["top", "haut", "blouse", "pull", "gilet", "body", "t-shirt", "chemise"]):
        cat = "HAUT"
    else:
        cat = "AUTRE"

    types_vinted = data.get("types_vinted")
    if not isinstance(types_vinted, list) or len(types_vinted) > 3:
        return False, "types_vinted doit être une liste de 0 à 3 éléments.", None

    desc = str(data.get("description", "")).lower()
    if not any(etat in desc for etat in ["tres bon etat", "très bon état", "bon etat", "bon état"]):
        return False, "La description ne contient pas la ligne d'état ('Très bon état' ou 'Bon état').", None

    data["categorie_norme"] = cat
    data["categorie"] = cat
    return True, "OK", data

async def _send_cdp(ws, method, params=None, req_id=1):
    msg = {"id": req_id, "method": method}
    if params:
        msg["params"] = params
    await ws.send(json.dumps(msg))
    while True:
        res = json.loads(await ws.recv())
        if res.get("id") == req_id:
            return res.get("result", {})

async def run_meta_ai_cdp_async(prompt_text, photo_paths, port=44231, ws_url=None):
    if not ws_url:
        try:
            r = requests.get(f"http://127.0.0.1:{port}/json/list", timeout=3).json()
            meta_tabs = [item for item in r if "meta.ai" in item.get("url", "")]
            if not meta_tabs:
                new_tab = requests.put(f"http://127.0.0.1:{port}/json/new?https://www.meta.ai/", timeout=5).json()
                ws_url = new_tab.get("webSocketDebuggerUrl")
            else:
                ws_url = meta_tabs[0]["webSocketDebuggerUrl"]
        except Exception as e:
            print(f"  [!] Erreur résolution tab Meta AI sur port {port}: {e}")
            return ""
    
    async with websockets.connect(ws_url) as ws:
        await _send_cdp(ws, "Runtime.enable", req_id=1)
        await _send_cdp(ws, "DOM.enable", req_id=2)
        await _send_cdp(ws, "Page.enable", req_id=3)
        
        # Réinitialiser la conversation via le bouton 'Nouvelle discussion' ou URL
        js_reset = """
        (() => {
            // Dismiss all blocking popups/dialogs first
            for (const b of document.querySelectorAll("button")) {
                const txt = (b.innerText || "").trim().toLowerCase();
                if (txt === "abandonner" || txt === "quitter" || txt === "leave") b.click();
            }
            const btn_dismiss = document.querySelector('button[data-testid="connect-apps-dismiss-button"]');
            if (btn_dismiss) btn_dismiss.click();

            const btn = Array.from(document.querySelectorAll('a, button, div[role="button"], span'))
                .find(el => el.innerText && el.innerText.trim() === 'Nouvelle discussion');
            if (btn) {
                btn.click();
                return "clicked";
            }
            return "not_found";
        })()
        """
        res_reset = await _send_cdp(ws, "Runtime.evaluate", {"expression": js_reset}, req_id=10)
        if res_reset.get("result", {}).get("value") != "clicked":
            await _send_cdp(ws, "Page.navigate", {"url": "https://www.meta.ai/"}, req_id=101)
        
        # Attendre que le composer soit disponible dans le DOM et fermer les alertes
        for _ in range(12):
            await asyncio.sleep(1)
            js_dismiss = """
            (() => {
                for (const b of document.querySelectorAll("button")) {
                    const txt = (b.innerText || "").trim().toLowerCase();
                    if (txt === "abandonner" || txt === "quitter") b.click();
                }
                const bd = document.querySelector('button[data-testid="connect-apps-dismiss-button"]');
                if (bd) bd.click();
                return Boolean(document.querySelector('div[contenteditable="true"], textarea[data-testid="composer-input"], div[data-testid="composer-input"]'));
            })()
            """
            res_check = await _send_cdp(ws, "Runtime.evaluate", {"expression": js_dismiss}, req_id=11)
            if res_check.get("result", {}).get("value") is True:
                break

        # 1. Coller les photos en premier
        fichiers_b64 = []
        for p in photo_paths:
            if os.path.exists(p):
                with open(p, "rb") as f_img:
                    fichiers_b64.append({
                        "nom": os.path.basename(p),
                        "data": base64.b64encode(f_img.read()).decode(),
                        "type": "image/png" if p.endswith(".png") else "image/jpeg"
                    })
        
        if fichiers_b64:
            # Envoyer toutes les photos par tranches de 3 max
            for i in range(0, len(fichiers_b64), 3):
                tranche = fichiers_b64[i:i+3]
                js_paste_exec = f"({JS_COLLER})({json.dumps(tranche)})"
                await _send_cdp(ws, "Runtime.evaluate", {"expression": js_paste_exec}, req_id=7 + i)
                await asyncio.sleep(2)
            await asyncio.sleep(1)

        # 2. Insérer le texte du prompt en second
        js_insert = """
        (() => {
            const el = document.querySelector('div[contenteditable="true"][data-testid="composer-input"]')
                    || document.querySelector('textarea[data-testid="composer-input"]')
                    || document.querySelector('div[contenteditable="true"]');
            if (!el) return false;
            el.focus();
            document.execCommand('insertText', false, %s);
            ['input', 'change', 'keydown', 'keyup'].forEach(ev => {
                el.dispatchEvent(new Event(ev, { bubbles: true, cancelable: true }));
            });
            return true;
        })()
        """ % json.dumps(prompt_text)
        
        await _send_cdp(ws, "Runtime.evaluate", {"expression": js_insert}, req_id=4)
        await asyncio.sleep(1.5)
            
        js_click = """
        (() => {
            const btn = document.querySelector('button[data-testid="composer-send-button"], button[aria-label*="Envoyer"], button[aria-label*="Send"], button.bg-linear-to-r');
            if (btn) {
                btn.removeAttribute("disabled");
                btn.disabled = false;
                btn.click();
                btn.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
                return "click";
            }
            return "none";
        })()
        """
        for _ in range(6):
            res_c = await _send_cdp(ws, "Runtime.evaluate", {"expression": js_click}, req_id=8)
            if res_c.get("result", {}).get("value") == "click":
                break
            await asyncio.sleep(1)

        await _send_cdp(ws, "Input.dispatchKeyEvent", {"type": "keyDown", "key": "Enter", "code": "Enter", "windowsVirtualKeyCode": 13}, req_id=14)
        await _send_cdp(ws, "Input.dispatchKeyEvent", {"type": "keyUp", "key": "Enter", "code": "Enter", "windowsVirtualKeyCode": 13}, req_id=15)

        fin = time.time() + 90
        while time.time() < fin:
            await asyncio.sleep(4)
            res_read = await _send_cdp(ws, "Runtime.evaluate", {"expression": "document.body.innerText"}, req_id=9)
            t = res_read.get("result", {}).get("value", "")
            
            start_idx = t.rfind("ANNONCE_DEBUT")
            end_idx = t.rfind("ANNONCE_FIN")
            
            if start_idx != -1 and end_idx > start_idx and "titre" in t[start_idx:end_idx]:
                return t[start_idx:end_idx + len("ANNONCE_FIN")]
                
            # Fallback: extraction ciblée du dernier bloc JSON valide
            titre_idx = t.rfind('"titre"')
            if titre_idx != -1:
                first_brace = t.rfind('{', 0, titre_idx)
                last_brace = t.rfind('}')
                if first_brace != -1 and last_brace > first_brace:
                    possible_json = t[first_brace:last_brace + 1]
                    if '"description"' in possible_json and '"types_vinted"' in possible_json:
                        return possible_json
                    
    return ""

def run_web_ai_redaction(page, prompt_text, photo_paths, account_name=None):
    from browser_pool import acquire_meta_browser, find_candidate_ports
    
    # 1. Tenter via le pool multi-navigateurs avec basculement automatique
    candidate_ports = find_candidate_ports(account_name)
    tried_ports = []
    max_attempts = len(candidate_ports) if candidate_ports else 3

    for attempt in range(max_attempts):
        used_port = None
        try:
            with acquire_meta_browser(account_name=account_name, timeout=25, exclude_ports=tried_ports) as (ws_url, used_port):
                tried_ports.append(used_port)
                print(f"  [🤖 Rédaction IA via Meta AI] Essai sur port {used_port} (Compte: '{account_name}', Essai {attempt + 1}/{max_attempts})...", flush=True)

                def _worker():
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    res = loop.run_until_complete(run_meta_ai_cdp_async(prompt_text, photo_paths, port=used_port, ws_url=ws_url))
                    loop.close()
                    return res

                executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
                future = executor.submit(_worker)
                try:
                    raw_res = future.result(timeout=110)
                except concurrent.futures.TimeoutError:
                    print(f"  [⚠️ Timeout Meta AI] Délai de 110s dépassé sur port {used_port}. Basculement sur un autre navigateur libre...", flush=True)
                    executor.shutdown(wait=False, cancel_futures=True)
                    raw_res = ""

                if raw_res and ("ANNONCE_FIN" in raw_res or "titre" in raw_res):
                    print(f"  [✅ Meta AI] Réponse valide obtenue avec succès sur port {used_port} !", flush=True)
                    return raw_res
                else:
                    print(f"  [⚠️ Meta AI] Réponse incomplète/vide sur port {used_port}. Test d'un autre navigateur libre...", flush=True)
        except Exception as e:
            print(f"  [!] Exception Meta AI sur port {used_port or 'inconnu'} : {e}", flush=True)
            time.sleep(1)

    print("  [⚠️ Meta AI CDP Multi-Navigateurs] Navigateurs du pool épuisés, test du fallback Playwright...", flush=True)

    # Fallback si page Playwright fournie
    if page and hasattr(page, "goto"):
        try:
            page.goto("https://www.meta.ai/")
            page.wait_for_timeout(3000)
            
            fichiers_b64 = []
            for p in photo_paths:
                if os.path.exists(p):
                    with open(p, "rb") as f:
                        fichiers_b64.append({
                            "nom": os.path.basename(p),
                            "data": base64.b64encode(f.read()).decode(),
                            "type": "image/png" if p.endswith(".png") else "image/jpeg"
                        })

            if fichiers_b64:
                page.evaluate(JS_COLLER, fichiers_b64[:3])
                page.wait_for_timeout(3000)

            js_insert = """
            (text) => {
                const el = document.querySelector('div[contenteditable="true"][data-testid="composer-input"], textarea[data-testid="composer-input"], div[contenteditable="true"]');
                if (!el) return;
                el.focus();
                document.execCommand('insertText', false, text);
                ['input', 'change', 'keydown', 'keyup'].forEach(ev => {
                    el.dispatchEvent(new Event(ev, { bubbles: true, cancelable: true }));
                });
            }
            """
            page.evaluate(js_insert, prompt_text)
            page.wait_for_timeout(1000)

            js_click = """
            () => {
                const btn = document.querySelector('button[aria-label*="Envoyer"], button[aria-label*="Send"], button[data-testid="composer-send-button"], button.bg-linear-to-r');
                if (btn) {
                    btn.removeAttribute("disabled");
                    btn.disabled = false;
                    btn.click();
                    return true;
                }
                return false;
            }
            """
            clicked = page.evaluate(js_click)
            if not clicked:
                page.keyboard.press("Enter")

            fin = time.time() + 90
            while time.time() < fin:
                page.wait_for_timeout(4000)
                content = page.content()
                if "ANNONCE_FIN" in content:
                    text = page.locator("body").inner_text()
                    if "ANNONCE_FIN" in text:
                        return text
                else:
                    text = page.locator("body").inner_text()
                    titre_idx = text.rfind('"titre"')
                    if titre_idx != -1:
                        first_brace = text.rfind('{', 0, titre_idx)
                        last_brace = text.rfind('}')
                        if first_brace != -1 and last_brace > first_brace:
                            possible_json = text[first_brace:last_brace + 1]
                            if '"description"' in possible_json and '"types_vinted"' in possible_json:
                                return possible_json
        except Exception as e:
            print(f"  [!] Erreur Meta AI Playwright : {e}")
    return ""

def generer_annonce(page, sku, prompt_template_path, info_dir, taille_full, account_name=None):
    with open(prompt_template_path, "r", encoding="utf-8") as f:
        prompt_template = f.read()

    info_file = os.path.join(info_dir, "info.txt")
    if not os.path.exists(info_file):
        return False, "Fichier info.txt introuvable.", None

    with open(info_file, "r", encoding="utf-8", errors="ignore") as f:
        info_txt_content = f.read()

    # Nettoyage strict de info.txt pour supprimer les URLs, prix Shein et noms de marques
    cleaned_lines = []
    forbidden_brands = ["shein", "dazy", "solersun", "franclia", "emery rose", "motf", "romwe", "glowmode"]
    for line in info_txt_content.splitlines():
        line_lower = line.lower()
        if any(kw in line_lower for kw in ["url:", "origine:", "prix shein:"]):
            continue
        line_clean = line
        for b in forbidden_brands:
            line_clean = re.sub(rf"\b{b}\b", "", line_clean, flags=re.IGNORECASE)
        cleaned_lines.append(line_clean)
    info_txt_clean = "\n".join(cleaned_lines)

    prompt_text = prompt_template.replace("{TAILLE}", taille_full).replace("{INFO_TXT}", info_txt_clean)

    photo_paths = []
    # 1. Vérification directe dans info_dir ({sku})
    if os.path.exists(info_dir):
        all_direct = sorted([os.path.join(info_dir, f) for f in os.listdir(info_dir) if f.endswith((".jpg", ".png"))])
        size_photos = [p for p in all_direct if "size_chart" in os.path.basename(p).lower()]
        title_photos = [p for p in all_direct if "title_full" in os.path.basename(p).lower()]
        prod_photos = [p for p in all_direct if os.path.basename(p).startswith("photo_")]
        if prod_photos:
            photo_paths = size_photos + title_photos + [prod_photos[0]]

    # 2. Secours dans les anciens sous-dossiers si non trouvé
    if not photo_paths:
        desc_screen = os.path.join(info_dir, "desc-screen")
        if not os.path.exists(desc_screen):
            desc_screen = f"/root/shein/image/{sku}/desc-screen"

        image_screen = os.path.join(info_dir, "image-screen")
        if not os.path.exists(image_screen):
            image_screen = f"/root/shein/image/{sku}/image-screen"

        if os.path.exists(desc_screen) and os.listdir(desc_screen):
            all_files = sorted([os.path.join(desc_screen, f) for f in os.listdir(desc_screen) if f.endswith((".jpg", ".png"))])
            size_photos = [p for p in all_files if "size_chart" in os.path.basename(p).lower()]
            title_photos = [p for p in all_files if "title_full" in os.path.basename(p).lower()]
            other_photos = [p for p in all_files if p not in size_photos and p not in title_photos]
            photo_paths = size_photos + other_photos + title_photos
            if not photo_paths:
                photo_paths = all_files
                
        if os.path.exists(image_screen) and os.listdir(image_screen):
            img_files = sorted([os.path.join(image_screen, f) for f in os.listdir(image_screen) if f.endswith((".jpg", ".png"))])
            if img_files and img_files[0] not in photo_paths:
                photo_paths.insert(0, img_files[0])

    print(f"  [🤖 Rédaction IA via Meta AI] Envoi du prompt ({taille_full}) avec {len(photo_paths)} photo(s) pour '{account_name}'...")
    raw_response = run_web_ai_redaction(page, prompt_text, photo_paths, account_name=account_name)

    valid, reason, data = extract_and_validate_ad(raw_response)
    if not valid:
        return False, f"Échec validation annonce : {reason}", None

    return True, "Succès", data
