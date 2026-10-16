import os
import shutil

IMAGE_BASE_DIR = "/root/shein/image"
OUTPUT_BASE_DIR = "/root/shein/photo marie"

PROMPT_FACE = """Fait exactement le même vêtement posé à plat sur le lit avec des draps bleu ciel doux code HEX : #87CEEB, légèrement froissé. Le vêtement doit être posé de façon naturelle et détendue, comme s'il venait d'être délicatement déposé — ni parfaitement lissé et symétrique, ni chiffonné ou jeté négligemment. Règles précises :
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

PROMPT_BACK = """Fait exactement le même vêtement posé à plat sur le lit avec des draps bleu ciel doux code HEX : #87CEEB, légèrement froissé. Le vêtement doit être posé de façon naturelle et détendue. VUE DE DOS :
- Montrer clairement le DOS / l'arrière du vêtement
- Les coutures arrière, le pan dorsal et le fermoir/zip (si présent) doivent être bien visibles et étalés à plat
- Les deux côtés arrière doivent être entièrement visibles
- AUCUN accessoire visible
- Le vêtement est centré avec 35 cm de marge tout autour
- Photo prise STRICTEMENT DU DESSUS (flat-lay vue du dessus à 90°)
- Le drap bleu ciel (#87CEEB) est clairement visible tout autour
- Photo produit e-commerce professionnelle réaliste pour vente en ligne, VUE DE DOS"""

def sync():
    if os.path.exists(OUTPUT_BASE_DIR):
        for sku in os.listdir(OUTPUT_BASE_DIR):
            out_dir = os.path.join(OUTPUT_BASE_DIR, sku, "flatlay")
            if os.path.isdir(out_dir):
                screen_dir = os.path.join(IMAGE_BASE_DIR, sku, "image-screen")
                if os.path.exists(screen_dir):
                    photos = sorted([os.path.join(screen_dir, f) for f in os.listdir(screen_dir) if f.startswith("photo_") and f.endswith(".jpg")])
                    if photos:
                        for p in photos:
                            fname = os.path.basename(p)
                            shutil.copyfile(p, os.path.join(out_dir, fname))
                        shutil.copyfile(photos[0], os.path.join(out_dir, "original.jpg"))
                        print(f"[+] Synchronisé SKU {sku} : {len(photos)} photos originales + original.jpg + prompts")
                
                with open(os.path.join(out_dir, "prompt_face.txt"), "w", encoding="utf-8") as f:
                    f.write(PROMPT_FACE)
                with open(os.path.join(out_dir, "prompt_back.txt"), "w", encoding="utf-8") as f:
                    f.write(PROMPT_BACK)

if __name__ == "__main__":
    sync()
