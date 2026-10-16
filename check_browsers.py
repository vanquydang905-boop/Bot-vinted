import requests

ports = [44775, 42677, 38049, 43983, 44231]
for p in ports:
    try:
        r = requests.get(f"http://127.0.0.1:{p}/json/version", timeout=2).json()
        b_name = r.get("Browser", "")
        ws = r.get("webSocketDebuggerUrl", "")
        print(f"Port {p}: ACTIVE - {b_name}")
        pages = requests.get(f"http://127.0.0.1:{p}/json/list", timeout=2).json()
        for pg in pages:
            if pg.get("type") == "page":
                print(f"   Page: {pg.get('title')} | {pg.get('url')}")
    except Exception as e:
        print(f"Port {p}: INACTIVE ({e})")
