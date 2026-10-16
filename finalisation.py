import os
import re
import math
import hashlib

COEFFS = {
    "ROBE": 3.5,
    "BAS": 3.0,
    "HAUT": 2.5,
    "AUTRE": 3.0
}

PLANCHERS = {
    "ROBE": 38.0,
    "BAS": 32.0,
    "HAUT": 32.0,
    "AUTRE": 32.0
}

NEGO = 0.20
BENEF_MIN = 15.0
PRIX_MIN_GLOBAL = 32.0

BIBLIO_TITRES = [
    "Ozaël",
    "Asthéra",
    "Célyre",
    "Miralia",
    "Orsane",
    "Sylvaé",
    "Luméa",
    "Yélona",
    "Thalysia"
]

def calculer_prix(prix_achat, categorie="AUTRE"):
    cat = (categorie or "AUTRE").upper()
    if cat not in COEFFS:
        cat = "AUTRE"
        
    coeff = COEFFS.get(cat, 3.0)
    plancher = PLANCHERS.get(cat, 32.0)
    
    prix_base = prix_achat * coeff
    prix_brut = max(prix_base, plancher, PRIX_MIN_GLOBAL)
    
    # Garantie bénéfice minimum 15€ après négociation 20%
    prix_min_benef = (prix_achat + BENEF_MIN) / (1.0 - NEGO)
    prix_cible = max(prix_brut, prix_min_benef)
    
    # Arrondi au 0.50 € supérieur
    prix_annonce = math.ceil(prix_cible * 2.0) / 2.0
    return prix_annonce, prix_base, plancher, prix_min_benef

def lire_info(dossier_item):
    info_path = os.path.join(dossier_item, "info.txt")
    if not os.path.exists(info_path):
        return {}
        
    infos = {}
    with open(info_path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()
        
    infos["raw_content"] = content
    
    # Extraction SKU
    match_sku = re.search(r"SKU\s*:\s*([a-zA-Z0-9_-]+)", content, re.IGNORECASE)
    if match_sku:
        infos["sku"] = match_sku.group(1).strip()
    else:
        infos["sku"] = None
        
    # Extraction Prix (robuste aux formats "Prix SHEIN: PRICE AND AVAILABILITY 19,30€", "11.09 €", etc.)
    match_prix = re.search(r"(?:Prix\s*d'achat|Prix\s*SHEIN|Prix)\s*:[^\n\r]*?([0-9]+[.,][0-9]{1,2}|[0-9]+)\s*€?", content, re.IGNORECASE)
    if not match_prix:
        # Fallback : chercher n'importe quel montant en euros sur les lignes de prix
        match_prix = re.search(r"[Pp]rix[^\n\r]*?([0-9]+[.,][0-9]{1,2}|[0-9]+)\s*€", content)
    if match_prix:
        val_str = match_prix.group(1).replace(",", ".")
        try:
            infos["prix_achat"] = float(val_str)
        except ValueError:
            infos["prix_achat"] = 12.0
    else:
        infos["prix_achat"] = 12.0
        
    # Extraction Titre
    match_titre = re.search(r"Titre\s*:\s*(.+)", content, re.IGNORECASE)
    if match_titre:
        infos["titre"] = match_titre.group(1).strip()
        
    # Extraction URL
    match_url = re.search(r"URL\s*:\s*(.+)", content, re.IGNORECASE)
    if match_url:
        infos["url"] = match_url.group(1).strip()

    # Extraction Origine
    match_origine = re.search(r"Origine\s*:\s*(.+)", content, re.IGNORECASE)
    if match_origine:
        infos["origine"] = match_origine.group(1).strip()
    elif match_url:
        infos["origine"] = match_url.group(1).strip()
    else:
        infos["origine"] = "SHEIN"
        
    return infos

def ecrire_description(dossier_flatlay, annonce, infos, taille_input, cle_article=None, debug=False):
    os.makedirs(dossier_flatlay, exist_ok=True)
    
    prix_achat = infos.get("prix_achat")
    categorie = annonce.get("categorie", "AUTRE")
    
    if prix_achat is None or prix_achat <= 0:
        print("  [!] Erreur calcul prix : Prix d'achat manquant ou nul dans info.txt !")
        return None
        
    prix_annonce, prix_base, plancher, prix_min_benef = calculer_prix(prix_achat, categorie)
    
    if debug:
        print(f"  [DEBUG PRIX] SKU: {infos.get('sku')} | Prix achat: {prix_achat:.2f}€ | Catégorie: {categorie} (Coeff x{COEFFS.get(categorie, 3.0)}, Plancher {PLANCHERS.get(categorie, 32.0)}€) | Calcul base: {prix_base:.2f}€ | Min bénéf 15€: {prix_min_benef:.2f}€ -> Prix final annonce: {prix_annonce:.2f}€")
        
    sku_shein = infos.get("sku") or "MANQUANT"
    if sku_shein == "MANQUANT":
        print("  [!] ALERTE : SKU Shein absent de info.txt !")
        
    titre = annonce.get("titre", "")
    description_text = annonce.get("description", "")
    
    types_vinted = annonce.get("types_vinted", [])
    if isinstance(types_vinted, list):
        types_vinted_str = ", ".join(types_vinted)
    else:
        types_vinted_str = str(types_vinted)
        
    # Format: "Taille L" -> "Taille L" or "taille L"
    taille_formatted = taille_input.lower().replace("taille ", "").strip()
    if f"taille {taille_formatted}" not in titre.lower():
        titre_final = f"{titre} – taille {taille_formatted.upper()}"
    else:
        titre_final = titre
        
    # Marque fixe
    marque = "Kovéni"
        
    origine = infos.get("origine") or infos.get("url") or "SHEIN (depuis info.txt)"
    
    content = f"""=== DESCRIPTION (à copier-coller) ===
{description_text}

=== PRIX ===
Prix d'achat : {prix_achat:.2f} €
Prix minimum à mettre dans l'annonce : {prix_annonce:.2f} €

=== INFOS ===
Catégorie : {categorie}
Type Vinted : {types_vinted_str}
Marque : {marque}
SKU : {sku_shein}
Origine : {origine}
"""

    out_file = os.path.join(dossier_flatlay, "description.txt")
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(content)
        
    return out_file
