import os
photo_dir = "/root/shein/photo marie/"
for sku in os.listdir(photo_dir):
    desc_path = os.path.join(photo_dir, sku, "flatlay", "description.txt")
    if os.path.exists(desc_path):
        print(f"Syncing {sku} to Google Drive...")
        os.system(f"export DISPLAY=:10; /root/venv/bin/python /root/shein/fast_gdrive_sync.py --sku {sku}")
print("Finished syncing existing descriptions.")
