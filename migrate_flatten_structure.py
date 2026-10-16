#!/usr/bin/env python3
"""
migrate_flatten_structure.py
Aplatit la structure de chaque SKU sur le VPS :
- Met tous les fichiers directement à la racine de {sku}/
- Supprime les sous-dossiers 'image-screen', 'desc-screen', 'flatlay'
- Supprime les doublons (original.jpg, doublons photo_*.jpg dans flatlay, prompts et captures debug)
"""
import os
import glob
import shutil

def flatten_sku(sku_dir):
    sku = os.path.basename(sku_dir)
    files_moved = 0
    duplicates_removed = 0

    # 1. Traiter image-screen/
    img_screen = os.path.join(sku_dir, "image-screen")
    if os.path.exists(img_screen) and os.path.isdir(img_screen):
        for f in os.listdir(img_screen):
            src = os.path.join(img_screen, f)
            dst = os.path.join(sku_dir, f)
            if not os.path.exists(dst):
                shutil.move(src, dst)
                files_moved += 1
            else:
                os.remove(src)
                duplicates_removed += 1
        try:
            os.rmdir(img_screen)
        except Exception:
            pass

    # 2. Traiter desc-screen/
    desc_screen = os.path.join(sku_dir, "desc-screen")
    if os.path.exists(desc_screen) and os.path.isdir(desc_screen):
        for f in os.listdir(desc_screen):
            src = os.path.join(desc_screen, f)
            dst = os.path.join(sku_dir, f)
            if not os.path.exists(dst):
                shutil.move(src, dst)
                files_moved += 1
            else:
                os.remove(src)
                duplicates_removed += 1
        try:
            os.rmdir(desc_screen)
        except Exception:
            pass

    # 3. Traiter flatlay/
    flatlay = os.path.join(sku_dir, "flatlay")
    if os.path.exists(flatlay) and os.path.isdir(flatlay):
        for f in os.listdir(flatlay):
            src = os.path.join(flatlay, f)
            dst = os.path.join(sku_dir, f)
            # Supprimer les doublons et fichiers inutiles
            if f in ["original.jpg", "prompt_face.txt", "prompt_back.txt"] or f.startswith("debug_echec_"):
                try:
                    os.remove(src)
                    duplicates_removed += 1
                except Exception:
                    pass
                continue

            if not os.path.exists(dst):
                shutil.move(src, dst)
                files_moved += 1
            else:
                # Fichier déjà présent à la racine (ex: photo_*.jpg déjà déplacé d'image-screen)
                try:
                    os.remove(src)
                    duplicates_removed += 1
                except Exception:
                    pass
        try:
            shutil.rmtree(flatlay, ignore_errors=True)
        except Exception:
            pass

    return files_moved, duplicates_removed

def main():
    print("🚀 Démarrage de l'aplatissement des dossiers SKU sur le VPS...")
    sku_dirs = []
    # Trouver tous les dossiers SKU
    for sdir in glob.glob("/root/shein/screen_*/*/*"):
        if os.path.isdir(sdir) and os.path.basename(sdir) not in ["flatlay", "image-screen", "desc-screen"]:
            sku_dirs.append(sdir)

    for sdir in glob.glob("/root/shein/image/*"):
        if os.path.isdir(sdir) and sdir not in sku_dirs:
            sku_dirs.append(sdir)

    total_skus = len(sku_dirs)
    print(f"Trouvé {total_skus} dossiers SKU à restructurer.")

    total_moved = 0
    total_dup = 0

    for idx, sku_dir in enumerate(sku_dirs, 1):
        m, d = flatten_sku(sku_dir)
        total_moved += m
        total_dup += d
        if idx % 200 == 0 or idx == total_skus:
            print(f"[{idx}/{total_skus}] Traités... Fichiers déplacés: {total_moved}, Doublons nettoyés: {total_dup}")

    print("\n✅ APLATISSEMENT TERMINÉ AVEC SUCCÈS !")
    print(f"   • Total SKUs traités : {total_skus}")
    print(f"   • Fichiers déplacés à la racine de {{sku}} : {total_moved}")
    print(f"   • Doublons supprimés (copies, original.jpg, debug) : {total_dup}")

if __name__ == "__main__":
    main()
