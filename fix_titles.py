import os
import re
import gspread
from google.oauth2.service_account import Credentials

def get_sheet():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_file("/root/shein/service_account.json", scopes=scope)
    client = gspread.authorize(creds)
    sheet = client.open_by_key("1zmlzcgozbhvbs_SrTBi0S1E-igDeSZQtRIrrjqUpYU0").worksheet("Recherche SKU")
    return sheet

def fix_all():
    print("Fetching sheet...")
    sheet = get_sheet()
    rows = sheet.get_all_values()
    
    sku_to_size = {}
    for r in rows[1:]:
        if r and r[0].strip():
            sku = r[0].strip()
            size = r[4].strip() if len(r) > 4 else ""
            sku_to_size[sku] = size
            
    base_dir = "/root/shein/photo marie"
    skus = os.listdir(base_dir)
    
    for sku in skus:
        desc_path = os.path.join(base_dir, sku, "flatlay", "description.txt")
        if os.path.exists(desc_path):
            with open(desc_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
                
            if len(lines) >= 2 and lines[0].strip() == "=== TITRE ===":
                old_title = lines[1].strip()
                
                # Remove model names
                names_to_remove = ["Ozaël - ", "Asthéra - ", "Célyre - ", "Miralia - ", "Orsane - ", "Sylvaé - ", "Luméa - ", "Yélona - ", "Thalysia - "]
                new_title = old_title
                for name in names_to_remove:
                    if new_title.startswith(name):
                        new_title = new_title[len(name):]
                
                size = sku_to_size.get(sku, "")
                taille_formatted = size.lower().replace("taille ", "").strip()
                size_str_new = f" - taille {taille_formatted.upper()}"
                
                # Normalize: remove any existing size suffix (handle both – and - dashes, with or without parentheses)
                new_title = re.sub(r'\s*[–\-]\s*[Tt]aille\s*\(?[A-Za-z0-9]+\)?$', '', new_title).strip()
                
                # Only add size if we have one
                if taille_formatted:
                    new_title = f"{new_title}{size_str_new}"
                    
                if old_title != new_title:
                    lines[1] = new_title + "\n"
                    with open(desc_path, "w", encoding="utf-8") as f:
                        f.writelines(lines)
                    print(f"Fixed title for {sku}: {new_title}")
                    os.system(f"/root/venv/bin/python /root/shein/upload_to_gdrive.py --sku {sku}")

if __name__ == "__main__":
    fix_all()
