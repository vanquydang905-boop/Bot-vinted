#!/usr/bin/env python3
"""
generate_flatlay.py
-------------------
Genere des images flat-lay (FACE + DOS) a partir des photos de produit SHEIN
en utilisant l'API Gemini (google-genai) avec Imagen 3.

Usage:
    python generate_flatlay.py --sku <SKU>
    python generate_flatlay.py --all
    python generate_flatlay.py --sku <SKU> --api-key <KEY>  (optionnel si .env present)

Cle API chargee automatiquement depuis /root/shein/.env (GEMINI_API_KEY=...)
Resultats sauvegardes dans :
    image/<SKU>/flatlay/flatlay_face.jpg
    image/<SKU>/flatlay/flatlay_back.jpg
"""

import os
import sys
import argparse
import time

# Chargement automatique du fichier .env
try:
    from dotenv import load_dotenv
    # Cherche .env dans le meme dossier que ce script
    _env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    load_dotenv(dotenv_path=_env_path)
except ImportError:
    pass  # python-dotenv optionnel, on utilise les variables d'environnement classiques
from pathlib import Path
from io import BytesIO

# --- Dépendances ---
try:
    from google import genai
    from google.genai import types
except ImportError:
    print("Package 'google-genai' manquant. Installez-le avec :")
    print("   /root/venv/bin/pip install google-genai")
    sys.exit(1)

try:
    from PIL import Image
except ImportError:
    print("Package 'Pillow' manquant. Installez-le avec :")
    print("   /root/venv/bin/pip install Pillow")
    sys.exit(1)

# =============================================================================
# PROMPTS FLAT-LAY
# =============================================================================

PROMPT_FACE = """
Exact same garment as in the reference photo — FRONT VIEW (FACE), laid flat on a soft sky blue bed sheet color HEX #87CEEB, slightly wrinkled naturally.
The garment must be laid in a natural and relaxed way, as if just delicately placed — not perfectly smooth and symmetrical, nor crumpled or carelessly thrown.
Precise rules:
- All structural elements (collar, lapels, sleeves, buttons, straps, belt, etc.) must be fully visible and spread flat on the sheet
- If sleeves/straps exist, both must be entirely visible and spread to the sides, never folded, twisted or hidden
- Slight natural wrinkles allowed at top, bottom and sleeve areas — fine and discreet, never a large fold that doubles the fabric over itself
- No fold should cover, deform or hide any printed design, text, motif or detail on the garment — design visibility must always remain total and clear
- The bottom hem can have a very slight asymmetric fold on ONE side only (never both sides simultaneously)
- If a tie/ribbon/bow is present, it must be neatly hand-tied: realistic but tidy, not perfectly round, not completely undone
- NO accessories visible: no bag, no hanger, no jewelry, no underwear, no swimwear showing through
- The fabric remains globally smooth with just enough irregularity to not look ironed or 3D-rendered
- The garment is centered in frame, with 35cm margin visible on ALL sides (left, right, top, bottom)
- Photo taken from DIRECTLY ABOVE (top-down flat-lay bird's eye view)
- Sky blue sheet (#87CEEB) clearly visible as the background
- Realistic professional e-commerce product photography for online sale, front view
""".strip()

PROMPT_BACK = """
Exact same garment as in the reference photo — BACK VIEW (DOS), laid flat on a soft sky blue bed sheet color HEX #87CEEB, slightly wrinkled naturally.
The garment must be laid in a natural and relaxed way, as if just delicately placed — not perfectly smooth and symmetrical, nor crumpled or carelessly thrown.
Show clearly the BACK/REAR side of the garment:
- The back panel, rear seams, zipper (if present) must be fully visible and spread flat
- Both back sides (left and right) must be fully visible, never folded under
- Each side can have a slightly different drape but must remain neat and readable
- Slight natural wrinkles allowed at top, bottom and back seams — fine and discreet, never a large fold
- No fold should cover or hide any back detail (zipper, seam, back print, fabric texture)
- The back bottom hem can have a very slight asymmetric fold on ONE side only
- If a back tie/ribbon exists, it must be realistically but neatly laid visible
- NO accessories visible: no bag, no hanger, no jewelry, no underwear visible through garment
- The fabric remains globally smooth with just enough irregularity to not look ironed or 3D-rendered
- The garment is centered in frame, with 35cm margin visible on ALL sides (left, right, top, bottom)
- Photo taken from DIRECTLY ABOVE (top-down flat-lay bird's eye view)
- Sky blue sheet (#87CEEB) clearly visible as the background
- Realistic professional e-commerce product photography for online sale, back/rear view
""".strip()


# =============================================================================
# FONCTIONS UTILITAIRES
# =============================================================================

def get_api_key(cli_key):
    """
    Recupere la cle API dans l'ordre de priorite suivant :
    1. Argument --api-key en ligne de commande
    2. Variable d'environnement GEMINI_API_KEY (chargee depuis .env si present)
    """
    key = (cli_key or os.environ.get("GEMINI_API_KEY", "")).strip()
    if not key or key == "VOTRE_CLE_API_ICI":
        print("[ERR] Cle API Gemini manquante ou non configuree.")
        print("  Editez le fichier .env et remplacez VOTRE_CLE_API_ICI :")
        print("    /root/shein/.env  ->  GEMINI_API_KEY=AIza...votre_cle")
        print("  Ou passez --api-key <votre_cle> en argument CLI.")
        sys.exit(1)
    return key


def load_image_bytes(image_path):
    """Charge une image et la retourne en bytes JPEG."""
    img = Image.open(image_path)
    if img.mode not in ("RGB",):
        img = img.convert("RGB")
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def save_pil_image(pil_image, output_path):
    """Sauvegarde une image PIL en JPEG."""
    if pil_image.mode not in ("RGB",):
        pil_image = pil_image.convert("RGB")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    pil_image.save(output_path, format="JPEG", quality=90)
    size_kb = round(os.path.getsize(output_path) / 1024, 1)
    print(f"  [OK] Sauvegarde : {output_path} ({size_kb} KB)")


def pick_best_photo(image_screen_dir):
    """
    Choisit la meilleure photo de produit (photo_1.* en priorite, sinon la premiere disponible >= 20KB).
    """
    path_dir = Path(image_screen_dir)
    if not path_dir.exists():
        return None
    for ext in ("jpg", "jpeg", "png", "webp"):
        p1 = path_dir / f"photo_1.{ext}"
        if p1.exists() and p1.stat().st_size >= 20 * 1024:
            return str(p1)

    candidates = sorted(list(path_dir.glob("photo_*.*")) + list(path_dir.glob("*.jpg")) + list(path_dir.glob("*.png")))
    for p in candidates:
        if p.is_file() and p.stat().st_size >= 20 * 1024:
            return str(p)
    return None


def generate_with_imagen(client, product_image_path, view):
    """
    Utilise gemini-2.5-flash-image (generateContent) pour generer une image flat-lay.
    Ce modele supporte les images en entree et en sortie.
    Retourne une PIL Image ou None.
    """
    prompt = PROMPT_FACE if view == "FACE" else PROMPT_BACK
    img_bytes = load_image_bytes(product_image_path)

    print(f"  [~] Generation flat-lay {view} via gemini-2.5-flash-image...")
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash-image",
            contents=[
                types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg"),
                types.Part.from_text(text=f"Reference product image provided above. Generate a new image:\n\n{prompt}"),
            ],
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE", "TEXT"],
                temperature=1.0,
            ),
        )

        for part in response.candidates[0].content.parts:
            if part.inline_data and part.inline_data.mime_type.startswith("image/"):
                return Image.open(BytesIO(part.inline_data.data))

        print(f"  [!] Aucune image dans la reponse gemini-2.5-flash-image pour {view}")
        return None

    except Exception as e:
        print(f"  [!] gemini-2.5-flash-image echoue ({e})")
        return None


def generate_with_flash(client, product_image_path, view):
    """
    Fallback : utilise les autres modeles supportant la generation d'image.
    """
    prompt = PROMPT_FACE if view == "FACE" else PROMPT_BACK
    img_bytes = load_image_bytes(product_image_path)

    fallback_models = [
        "gemini-2.5-flash-image",
    ]

    for model_id in fallback_models:
        print(f"  [~] Tentative avec {model_id}...")
        try:
            response = client.models.generate_content(
                model=model_id,
                contents=[
                    types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg"),
                    types.Part.from_text(text=f"Reference product image provided above. Generate a new image:\n\n{prompt}"),
                ],
                config=types.GenerateContentConfig(
                    response_modalities=["IMAGE", "TEXT"],
                    temperature=1.0,
                ),
            )

            for part in response.candidates[0].content.parts:
                if part.inline_data and part.inline_data.mime_type.startswith("image/"):
                    return Image.open(BytesIO(part.inline_data.data))

            print(f"  [!] Aucune image dans la reponse {model_id}")

        except Exception as e:
            print(f"  [!] {model_id} echoue : {e}")
            continue

    print(f"  [ERR] Tous les modeles ont echoue pour {view}")
    return None


def generate_flatlay_image(client, product_image_path, view):
    """
    Essaie le modele de generation d'image principal, puis fallback.
    Retourne une PIL Image ou None.
    """
    img = generate_with_imagen(client, product_image_path, view)
    if img is not None:
        return img
    return generate_with_flash(client, product_image_path, view)


# =============================================================================
# TRAITEMENT PAR SKU
# =============================================================================

def process_sku(sku, client, image_base_dir="image", output_base_dir="photo marie"):
    """
    Genere les flat-lays FACE + DOS pour un SKU donne.
    - Les photos source sont lues depuis : image_base_dir/<SKU>/image-screen/
    - Les flat-lays sont sauvegardes dans : output_base_dir/<SKU>/flatlay/
    Retourne True si au moins une image a ete generee ou deja existante.
    """
    sku_dir = os.path.join(image_base_dir, sku)
    image_screen_dir = os.path.join(sku_dir, "image-screen")
    flatlay_dir = os.path.join(output_base_dir, sku, "flatlay")

    if not os.path.isdir(image_screen_dir):
        print(f"  [!] Dossier image-screen introuvable pour SKU {sku}, ignore.")
        return False

    photo_path = pick_best_photo(image_screen_dir)
    if not photo_path:
        print(f"  [!] Aucune photo produit valide pour SKU {sku}, ignore.")
        return False

    print(f"  Photo reference  : {os.path.basename(photo_path)}")
    print(f"  Dossier sortie   : {flatlay_dir}")
    os.makedirs(flatlay_dir, exist_ok=True)
    success = False

    # --- FACE ---
    face_jpg = os.path.join(flatlay_dir, "flatlay_face.jpg")
    face_png = os.path.join(flatlay_dir, "flatlay_face.png")
    if os.path.exists(face_jpg) or os.path.exists(face_png):
        print(f"  [=] flatlay_face deja existant, ignore.")
        success = True
    else:
        face_img = generate_flatlay_image(client, photo_path, view="FACE")
        if face_img:
            save_pil_image(face_img, face_jpg)
            success = True
        time.sleep(2)

    # --- DOS ---
    back_jpg = os.path.join(flatlay_dir, "flatlay_back.jpg")
    back_png = os.path.join(flatlay_dir, "flatlay_back.png")
    if os.path.exists(back_jpg) or os.path.exists(back_png):
        print(f"  [=] flatlay_back deja existant, ignore.")
        success = True
    else:
        back_img = generate_flatlay_image(client, photo_path, view="DOS")
        if back_img:
            save_pil_image(back_img, back_jpg)
            success = True
        time.sleep(2)

    return success


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Genere des flat-lays FACE + DOS via API Gemini pour les produits SHEIN."
    )
    parser.add_argument("--sku", type=str, help="SKU unique a traiter")
    parser.add_argument("--all", action="store_true", dest="all_skus",
                        help="Traiter tous les SKU dans le dossier image/")
    parser.add_argument("--api-key", type=str, help="Cle API Gemini (ou definir GEMINI_API_KEY)")
    parser.add_argument("--image-dir", type=str, default="image",
                        help="Dossier source des images scrappees (defaut: image/)")
    parser.add_argument("--output-dir", type=str, default="photo marie",
                        help="Dossier de sortie des resultats (defaut: photo marie/)")

    args = parser.parse_args()

    if not args.sku and not args.all_skus:
        parser.print_help()
        sys.exit(1)

    api_key = get_api_key(args.api_key)
    client = genai.Client(api_key=api_key)

    image_base = args.image_dir
    output_base = args.output_dir

    print(f"Dossier source  : {image_base}/")
    print(f"Dossier sortie  : {output_base}/")
    print(f"  Structure : {output_base}/<SKU>/flatlay/flatlay_face.jpg")
    print(f"              {output_base}/<SKU>/flatlay/flatlay_back.jpg")
    print()

    generated_skus = []

    if args.all_skus:
        if not os.path.isdir(image_base):
            print(f"[ERR] Dossier source '{image_base}' introuvable.")
            sys.exit(1)
        skus = sorted([
            d for d in os.listdir(image_base)
            if os.path.isdir(os.path.join(image_base, d))
        ])
        if not skus:
            print(f"[ERR] Aucun SKU trouve dans '{image_base}'.")
            sys.exit(1)
        print(f"Traitement de {len(skus)} SKU(s)...")
        for i, sku in enumerate(skus, 1):
            print(f"\n[{i}/{len(skus)}] SKU : {sku}")
            ok = process_sku(sku, client, image_base, output_base)
            if ok:
                generated_skus.append(sku)
            if i < len(skus):
                time.sleep(3)
    else:
        print(f"Traitement SKU : {args.sku}")
        ok = process_sku(args.sku, client, image_base, output_base)
        if ok:
            generated_skus.append(args.sku)
        else:
            print("[ERR] Aucune image generee.")
            sys.exit(1)

    # --- Recap final ---
    print("\n" + "=" * 60)
    print(f"[DONE] Generation terminee : {len(generated_skus)} SKU(s) traites")
    print(f"Toutes les images sont dans : {os.path.abspath(output_base)}/")
    print()
    for sku in generated_skus:
        sku_out = os.path.join(output_base, sku, "flatlay")
        files = [f for f in os.listdir(sku_out) if f.endswith(".jpg") or f.endswith(".png")] if os.path.isdir(sku_out) else []
        print(f"  {sku}/flatlay/")
        for f in sorted(files):
            fpath = os.path.join(sku_out, f)
            kb = round(os.path.getsize(fpath) / 1024, 1)
            print(f"    {f}  ({kb} KB)")
    print("=" * 60)


if __name__ == "__main__":
    main()

