import os
import time
import fcntl
import threading
import requests
from contextlib import contextmanager
from playwright.sync_api import sync_playwright

# 4 navigateurs AdsPower dédiés à l'IA (Gemini & Meta AI)
AI_BROWSERS_CONFIG = [
    {
        "port": 43983,
        "accounts": ["elya_soc", "laura_vsni", "viki_sph", "nice_mam"],
        "name": "AdsPower 43983 (elya_soc / laura_vsni / viki_sph / nice_mam)"
    },
    {
        "port": 34115,
        "accounts": ["jess_smth", "claravintage09", "julie_last476", "helen_mil", "helen", "marie_sdm963", "marie"],
        "name": "AdsPower 34115 (claravintage09 / julie_last476 / helen_mil / marie_sdm963)"
    },
    {
        "port": 38049,
        "accounts": ["faby_grb", "lea_vani", "lisa_llc", "eica_ph", "oria_nel"],
        "name": "AdsPower 38049 (faby_grb / lea_vani / lisa_llc / eica_ph / oria_nel)"
    },
    {
        "port": 42677,
        "accounts": ["yurih_mlf", "alix_vrt", "jade_huo", "neli_fyu", "nely_fyu", "vera_los"],
        "name": "AdsPower 42677 (yurih_mlf / alix_vrt / jade_huo / neli_fyu / vera_los)"
    }
]

# Navigateur unique dédié au scraping Shein
SCRAPER_BROWSER_CONFIG = {
    "port": 44231,
    "accounts": ["marie_sdm963", "neli_fyu", "vera_los", "oria_nel", "nice_mam"],
    "name": "Chrome 44231 (Scraping Shein)"
}

BROWSERS_CONFIG = AI_BROWSERS_CONFIG + [SCRAPER_BROWSER_CONFIG]

LOCK_DIR = "/root/shein/browser_locks"
os.makedirs(LOCK_DIR, exist_ok=True)

# ---------------------------------------------------------------------------
# GESTION DES VERROUS EXCLUSIFS PAR PORT (Thread + OS flock)
# ---------------------------------------------------------------------------
_port_thread_locks = {}
_global_lock = threading.Lock()
_port_current_user = {}  # port -> user_tag

def _get_thread_lock(port):
    with _global_lock:
        if port not in _port_thread_locks:
            _port_thread_locks[port] = threading.Lock()
        return _port_thread_locks[port]

def try_acquire_port(port, user_tag="worker", timeout=0.0):
    """
    Tente d'acquérir de manière exclusive un port (verrou thread in-process + flock OS inter-process).
    Si timeout <= 0: tentative non-bloquante immédiate.
    Si timeout > 0: tentative avec attente progressive jusqu'à timeout.
    Retourne (fd, port) si succès, None sinon.
    """
    t_lock = _get_thread_lock(port)
    start_t = time.time()

    if timeout <= 0:
        acquired_thread = t_lock.acquire(blocking=False)
        if not acquired_thread:
            return None
    else:
        acquired_thread = t_lock.acquire(blocking=True, timeout=timeout)
        if not acquired_thread:
            return None

    lock_path = os.path.join(LOCK_DIR, f"browser_{port}.lock")
    fd = None
    try:
        fd = open(lock_path, "w")
        elapsed = time.time() - start_t
        remaining = max(0.0, timeout - elapsed)

        if remaining <= 0:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        else:
            flock_ok = False
            while time.time() - start_t <= timeout:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    flock_ok = True
                    break
                except (OSError, IOError):
                    time.sleep(0.05)
            if not flock_ok:
                raise OSError("flock timeout")

        with _global_lock:
            _port_current_user[port] = user_tag

        return (fd, port)
    except (OSError, IOError):
        if fd:
            try: fd.close()
            except Exception: pass
        t_lock.release()
        return None

def release_port(handle):
    """Libère le verrou OS et le verrou thread."""
    if not handle:
        return
    fd, port = handle
    with _global_lock:
        _port_current_user.pop(port, None)
    try:
        fcntl.flock(fd, fcntl.LOCK_UN)
        fd.close()
    except Exception:
        pass
    try:
        _get_thread_lock(port).release()
    except RuntimeError:
        pass

# Fonctions de compatibilité ascendante
def get_lock_file(port):
    return os.path.join(LOCK_DIR, f"browser_{port}.lock")

def try_acquire_port_lock(port):
    return try_acquire_port(port, timeout=0.0)

def release_port_lock(fd, port):
    if fd:
        release_port((fd, port))

def get_port_queue_status():
    """Retourne un résumé lisible de l'état des navigateurs."""
    with _global_lock:
        if not _port_current_user:
            return ["Tous les navigateurs sont libres."]
        return [f"Port {p} : occupé par {u}" for p, u in _port_current_user.items()]

def is_port_active(port):
    try:
        r = requests.get(f"http://127.0.0.1:{port}/json/version", timeout=1.5)
        return r.status_code == 200
    except Exception:
        return False

def find_candidate_ports(account_name=None, ai_only=True):
    """
    Retourne la liste des ports candidats ordonnés par priorité :
    1. Le port préféré pour ce compte
    2. Les autres ports actifs disponibles
    """
    clean = (account_name or "").strip().lower()
    config_list = AI_BROWSERS_CONFIG if ai_only else BROWSERS_CONFIG
    preferred = []
    fallback = []

    for b in config_list:
        port = b["port"]
        if not is_port_active(port):
            continue
        matched = any(acc in clean or clean in acc for acc in b["accounts"]) if clean else False
        if matched:
            preferred.append(port)
        else:
            fallback.append(port)

    return preferred + fallback

def acquire_available_port(candidate_ports, user_tag="worker", timeout=30.0):
    """
    Vérifie si l'un des ports candidats est IMMÉDIATEMENT libre (non-bloquant).
    Si libre, l'attribue instantanément sans aucune attente.
    Sinon, scrutation active toutes les 0.3s jusqu'à libération d'un navigateur ou timeout.
    """
    if not candidate_ports:
        return None, None

    # 1. Test non-bloquant : prendre le premier libre tout de suite
    for port in candidate_ports:
        handle = try_acquire_port(port, user_tag=user_tag, timeout=0.0)
        if handle:
            return handle, port

    # 2. Si tous occupés, attente avec boucle de scrutation
    start_t = time.time()
    while time.time() - start_t < timeout:
        for port in candidate_ports:
            handle = try_acquire_port(port, user_tag=user_tag, timeout=0.0)
            if handle:
                return handle, port
        time.sleep(0.3)

    return None, None

_thread_local = threading.local()

def get_thread_playwright():
    if not hasattr(_thread_local, "playwright") or _thread_local.playwright is None:
        _thread_local.playwright = sync_playwright().start()
    return _thread_local.playwright

# ---------------------------------------------------------------------------
# ACQUISITION NAVIGATEUR GEMINI — avec basculement automatique sans blocage
# ---------------------------------------------------------------------------
@contextmanager
def acquire_gemini_browser(account_name=None, timeout=120, p_instance=None, exclude_ports=None):
    """
    Acquiert un navigateur Gemini libre.
    Tente le port préféré du compte en priorité ; si occupé, bascule immédiatement
    sur un autre navigateur AdsPower libre sans attendre.
    Retourne (browser, page_gemini, port).
    """
    candidate_ports = [p for p in find_candidate_ports(account_name, ai_only=True) if p not in (exclude_ports or [])]
    if not candidate_ports:
        candidate_ports = find_candidate_ports(account_name, ai_only=True)

    if not candidate_ports:
        raise RuntimeError("Aucun navigateur AdsPower actif détecté pour Gemini.")

    handle, acquired_port = acquire_available_port(
        candidate_ports,
        user_tag=f"Gemini({account_name or '?'})",
        timeout=timeout
    )

    if not handle:
        raise TimeoutError(
            f"Délai d'attente dépassé ({timeout}s) pour obtenir un navigateur Gemini libre "
            f"pour '{account_name}'. Navigateurs : {get_port_queue_status()}"
        )

    print(f"  [🌐 Gemini] Port {acquired_port} accordé à '{account_name}'.", flush=True)

    def _connect_and_yield(p):
        browser = None
        for attempt in range(2):
            try:
                browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{acquired_port}", timeout=20000)
                break
            except Exception as e_conn:
                if attempt == 0:
                    time.sleep(1.5)
                else:
                    raise e_conn
        try:
            context = browser.contexts[0]
            gemini_pages = [pg for pg in context.pages if "gemini.google.com" in pg.url]
            if gemini_pages:
                gemini_page = gemini_pages[0]
            else:
                gemini_page = context.new_page()
                gemini_page.goto("https://gemini.google.com/app?hl=fr", wait_until="domcontentloaded", timeout=15000)
            gemini_page.bring_to_front()
            return browser, gemini_page
        except Exception:
            if browser:
                try: browser.close()
                except Exception: pass
            raise

    try:
        if p_instance:
            browser, gemini_page = _connect_and_yield(p_instance)
            try:
                yield browser, gemini_page, acquired_port
            finally:
                try: browser.close()
                except Exception: pass
        else:
            with sync_playwright() as p:
                browser, gemini_page = _connect_and_yield(p)
                try:
                    yield browser, gemini_page, acquired_port
                finally:
                    try: browser.close()
                    except Exception: pass
    finally:
        release_port(handle)
        print(f"  [🌐 Gemini] Port {acquired_port} libéré par '{account_name}'.", flush=True)

# ---------------------------------------------------------------------------
# ACQUISITION NAVIGATEUR META AI — avec basculement automatique sans blocage
# ---------------------------------------------------------------------------
@contextmanager
def acquire_meta_browser(account_name=None, timeout=30, exclude_ports=None):
    """
    Acquiert un navigateur Meta AI libre.
    Tente le port préféré en priorité ; si occupé (ex: par Gemini sur le même compte),
    bascule IMMÉDIATEMENT sur un autre navigateur AdsPower libre.
    Retourne (ws_url, port).
    """
    exclude_set = set(exclude_ports or [])
    candidate_ports = [p for p in find_candidate_ports(account_name, ai_only=True) if p not in exclude_set]
    if not candidate_ports:
        candidate_ports = find_candidate_ports(account_name, ai_only=True)

    if not candidate_ports:
        raise RuntimeError("Aucun navigateur AdsPower actif détecté pour Meta AI.")

    handle, acquired_port = acquire_available_port(
        candidate_ports,
        user_tag=f"MetaAI({account_name or '?'})",
        timeout=timeout
    )

    if not handle:
        raise TimeoutError(
            f"Délai d'attente dépassé ({timeout}s) pour obtenir un navigateur Meta AI libre "
            f"pour '{account_name}'. Navigateurs : {get_port_queue_status()}"
        )

    print(f"  [🌐 Meta AI] Port {acquired_port} accordé à '{account_name}'.", flush=True)

    ws_url = None
    try:
        r = requests.get(f"http://127.0.0.1:{acquired_port}/json/list", timeout=3.0).json()
        meta_tabs = [item for item in r if "meta.ai" in item.get("url", "")]
        if not meta_tabs:
            new_tab = requests.put(
                f"http://127.0.0.1:{acquired_port}/json/new?https://www.meta.ai/", timeout=4.0
            ).json()
            ws_url = new_tab.get("webSocketDebuggerUrl")
        else:
            ws_url = meta_tabs[0].get("webSocketDebuggerUrl")

        if not ws_url:
            raise RuntimeError(f"Impossible d'obtenir l'URL WebSocket Meta AI sur port {acquired_port}")

        yield ws_url, acquired_port
    finally:
        release_port(handle)
        print(f"  [🌐 Meta AI] Port {acquired_port} libéré par '{account_name}'.", flush=True)
