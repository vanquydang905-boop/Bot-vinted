import os
import json
import re

DATA_FILE = "/root/shein/gdoc_tabs_data.json"

DEFAULT_PROMPT_FACE = """Fait exactement le même vêtement posé à plat sur le lit avec des draps bleu ciel doux code HEX : #87CEEB, légèrement froissé. Le vêtement doit être posé de façon naturelle et détendue, comme s'il venait d'être délicatement déposé — ni parfaitement lissé et symétrique, ni chiffonné ou jeté négligemment. Règles précises :
- Les deux manches doivent être entièrement visibles et étalées à plat sur le côté, jamais repliées, tordues, écrasées ou cachées sous le vêtement
- Chaque manche peut avoir un tombé légèrement différent de l'autre (une texture ou un angle très légèrement variable), mais aucune des deux ne doit paraître "abandonnée" ou en désordre — les deux doivent rester nettes et lisibles
- De légers plis naturels sont autorisés en haut, en bas et au niveau des manches du vêtement, mais ils doivent être fins et discrets, jamais un gros pli qui replie le tissu sur lui-même
- Aucun pli ne doit masquer, déformer ou cacher un motif, imprimé, texte ou détail présent sur le vêtement — la lisibilité du visuel doit toujours être totale et nette
- L'ourlet du bas peut présenter un très léger pli asymétrique sur UN SEUL côté (jamais les deux côtés à la fois)
- Si le vêtement comporte un lien, un ruban ou un nœud, il doit être noué à la main de façon réaliste et propre, pas parfaitement rond, pas totalement défait
- AUCUN accessoire visible : pas de sac, pas de cintre, pas de bijoux, pas de sous-vêtement qui dépasse
- La matière reste globalement lisse avec juste assez d'irrégularité pour ne pas faire "repassé au fer" ou "rendu 3D"
- Le vêtement est centré dans l'image, avec une marge de 35 cm visible de CHAQUE côté (gauche, droite, haut, bas)
- Photo prise STRICTEMENT DU DESSUS (vue du dessus flat-lay bird's eye view à 90°)
- Le drap bleu ciel (#87CEEB) est clairement visible tout autour en arrière-plan
- Photo produit e-commerce professionnelle réaliste pour vente en ligne, VUE DE FACE"""

DEFAULT_PROMPT_BACK = """Fait exactement le même vêtement posé à plat sur le lit avec des draps bleu ciel doux code HEX : #87CEEB, légèrement froissé. Le vêtement doit être posé de façon naturelle et détendue. VUE DE DOS :
- Montrer clairement le DOS / l'arrière du vêtement
- Les coutures arrière, le pan dorsal et le fermoir/zip (si présent) doivent être bien visibles et étalés à plat
- Les deux côtés arrière doivent être entièrement visibles
- AUCUN accessoire visible
- Le vêtement est centré avec 35 cm de marge tout autour
- Photo prise STRICTEMENT DU DESSUS (flat-lay vue du dessus à 90°)
- Le drap bleu ciel (#87CEEB) est clairement visible tout autour
- Photo produit e-commerce professionnelle réaliste pour vente en ligne, VUE DE DOS"""

ALIASES = {
    "neli_fyu": "nely_fyu",
    "helen": "helen_mil",
    "marie": "marie_sdm963",
    "marie_sdm": "marie_sdm963",
}

def parse_tab_content(content, tab_name=""):
    if not content or content.startswith("FETCH_ERROR_"):
        return "Taille M", DEFAULT_PROMPT_FACE, DEFAULT_PROMPT_BACK

    taille = "Taille M"
    combined = tab_name + "\n" + content[:500]
    t_match = re.search(r"TAILLE\s*([A-Z0-9]+)", combined, re.IGNORECASE)
    if t_match:
        taille = f"Taille {t_match.group(1).upper()}"

    section = None
    face_lines = []
    back_lines = []

    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line:
            continue
            
        # Clean border lines like ════════════════════════
        if set(line) <= {"═", "-", "=", "_"}:
            continue
            
        upper = line.upper()

        # Stop section if entering another category or non-clothing prompt
        if len(line) <= 35 and any(h in upper for h in ["CHAUSSURE", "POUR UN SAC", "PROMPT BIJOUX", "TAPISSERIE", "PROMPT 3", "PROMPTE 3", "PROMPT 1 —"]):
            section = None
            continue

        # Detect DOS header
        if any(h in upper for h in ["VUE DE DOS", "PROMPT DOS", "PROMPT 2 : VUE DE DOS", "PROMPT 2: VUE DE DOS", "PROMPT 2"]) or upper in ("DOS", "DOS :", "DOS:"):
            section = "BACK"
            continue
            
        # Detect FACE header
        if any(h in upper for h in ["VUE DE FACE", "PROMPT FACE", "PROMPT 1 : VUE DE FACE", "PROMPT 1: VUE DE FACE", "PROMPT 1"]) or upper in ("FACE", "FACE :", "FACE:"):
            section = "FACE"
            continue

        if section == "FACE":
            face_lines.append(line)
        elif section == "BACK":
            back_lines.append(line)

    p_face = "\n".join(face_lines).strip() if face_lines else DEFAULT_PROMPT_FACE
    p_back = "\n".join(back_lines).strip() if back_lines else DEFAULT_PROMPT_BACK

    return taille, p_face, p_back

MARIE_DEFAULT_ENTRY = {
    "account": "marie_sdm963",
    "default_size": "Taille L",
    "prompt_face": DEFAULT_PROMPT_FACE,
    "prompt_back": DEFAULT_PROMPT_BACK,
    "tab_id": None,
    "url": None
}

def load_accounts_library():
    library = {}
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                raw_data = json.load(f)
            for acc_name, info in raw_data.items():
                content = info.get("content", "")
                taille, p_face, p_back = parse_tab_content(content, acc_name)
                clean_name = acc_name.strip().lower()
                library[clean_name] = {
                    "account": clean_name,
                    "default_size": taille,
                    "prompt_face": p_face,
                    "prompt_back": p_back,
                    "tab_id": info.get("tab_id"),
                    "url": info.get("url")
                }
        except Exception as e:
            print(f"[!] Erreur lecture bibliotheque comptes ({e})")

    # Enregistrement explicite du compte Marie sous tous ses alias
    for alias in ["marie_sdm963", "marie", "marie_sdm"]:
        if alias not in library:
            library[alias] = MARIE_DEFAULT_ENTRY

    return library

# Cache en mémoire
_LIBRARY_CACHE = None

def get_library():
    global _LIBRARY_CACHE
    if _LIBRARY_CACHE is None:
        _LIBRARY_CACHE = load_accounts_library()
    return _LIBRARY_CACHE

def find_account_entry(account_name):
    if not account_name:
        return None
    lib = get_library()
    clean = account_name.strip().lower()

    # Check direct match
    if clean in lib:
        return lib[clean]

    # Check alias
    if clean in ALIASES and ALIASES[clean] in lib:
        return lib[ALIASES[clean]]

    # Check alias reverse
    for k_alias, v_alias in ALIASES.items():
        if v_alias == clean and k_alias in lib:
            return lib[k_alias]

    # Check partial match (e.g. "elya" in "elya_soc")
    for k, v in lib.items():
        if (k in clean or clean in k) and k not in ["lien bot", "onglet 17"]:
            return v
    return None

def get_default_size(account_name):
    entry = find_account_entry(account_name)
    if entry and entry.get("default_size"):
        return entry["default_size"]
    return "Taille M"

def get_prompts(account_name):
    entry = find_account_entry(account_name)
    if entry:
        p_face = entry.get("prompt_face") or DEFAULT_PROMPT_FACE
        p_back = entry.get("prompt_back") or DEFAULT_PROMPT_BACK
        return p_face, p_back
    return DEFAULT_PROMPT_FACE, DEFAULT_PROMPT_BACK

