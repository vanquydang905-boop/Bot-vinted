import os

skus = [
    "sz25031833445974160",
    "sz25090625524872632",
    "sz25061128578553815",
    "sz260607113347487727971",
    "sz25042804329900356",
    "sz260225103792008540882",
    "sz2412213215914642",
    "sz25070165663024042",
    "sz25031279667378585",
    "sz25022030065602844"
]

for sku in skus:
    desc_path = os.path.join("/root/shein/photo marie", sku, "flatlay", "description.txt")
    if os.path.exists(desc_path):
        print(f"Syncing {sku} to Google Drive...")
        os.system(f"export DISPLAY=:10; /root/venv/bin/python /root/shein/fast_gdrive_sync.py --sku {sku}")

print("Finished syncing specific descriptions.")
