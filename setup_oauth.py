"""
setup_oauth.py - OAuth Google Drive
"""
import os, time, threading, urllib.parse
from wsgiref.simple_server import make_server, WSGIRequestHandler

SCOPES = ['https://www.googleapis.com/auth/drive']
TOKEN_FILE = '/root/shein/token.json'
REDIRECT_URI = 'http://localhost:8080/'

CLIENT_CONFIG = {
    "installed": {
        "client_id": "202264815644.apps.googleusercontent.com",
        "project_id": "rclone-154911",
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
        "client_secret": "eX08N33B9TjJ98XgNqFj0fIq",
        "redirect_uris": [REDIRECT_URI]
    }
}

def open_url_in_chrome(url):
    import requests, asyncio, json, websockets
    try:
        r = requests.get("http://127.0.0.1:44231/json/list", timeout=5).json()
        pages = [t for t in r if t.get("type") == "page"]
        if pages:
            ws_url = pages[0]["webSocketDebuggerUrl"]
            async def nav():
                async with websockets.connect(ws_url, max_size=2**25) as ws:
                    await ws.send(json.dumps({"id": 1, "method": "Page.navigate", "params": {"url": url}}))
                    await asyncio.wait_for(ws.recv(), timeout=5)
            asyncio.run(nav())
            print("[Chrome] Page ouverte.")
            return True
    except Exception as e:
        print(f"[Chrome] Erreur CDP: {e}")
    return False

def main():
    from google_auth_oauthlib.flow import InstalledAppFlow

    print("=== Configuration Google Drive OAuth ===")

    flow = InstalledAppFlow.from_client_config(CLIENT_CONFIG, SCOPES)
    # Définir le redirect_uri sur la session OAuth2 directement
    flow.redirect_uri = REDIRECT_URI

    # authorization_url() utilise flow.redirect_uri automatiquement
    auth_url, state = flow.authorization_url(
        access_type='offline',
        prompt='consent'
    )

    print(f"\nURL d'autorisation :\n{auth_url}\n")

    # Démarrer le serveur
    received = {'code': None}

    class Silent(WSGIRequestHandler):
        def log_message(self, *args): pass

    def app(environ, start_response):
        q = urllib.parse.parse_qs(environ.get('QUERY_STRING', ''))
        code = q.get('code', [None])[0]
        if code:
            received['code'] = code
        start_response('200 OK', [('Content-Type', 'text/html; charset=utf-8')])
        return [b"<html><body><h2 style='font-family:sans-serif;color:green'>Autorisation accordee ! Fermez cet onglet.</h2></body></html>"]

    server = make_server('localhost', 8080, app, handler_class=Silent)
    server.timeout = 1

    print("Serveur en attente sur http://localhost:8080 ...")
    
    def open_later():
        time.sleep(2)
        open_url_in_chrome(auth_url)

    threading.Thread(target=open_later, daemon=True).start()

    deadline = time.time() + 120
    while not received['code'] and time.time() < deadline:
        server.handle_request()

    if not received['code']:
        print("[ERREUR] Timeout. Reessaie.")
        return

    print("[OK] Code recu ! Echange en cours...")

    # fetch_token utilise flow.redirect_uri automatiquement
    flow.fetch_token(code=received['code'])
    creds = flow.credentials

    with open(TOKEN_FILE, 'w') as f:
        f.write(creds.to_json())

    print(f"\n[SUCCESS] token.json cree dans {TOKEN_FILE}")
    print("L'upload Google Drive fonctionne maintenant.")

if __name__ == '__main__':
    main()
