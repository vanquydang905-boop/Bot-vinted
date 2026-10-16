import os
import json
import urllib.request
from dotenv import load_dotenv

load_dotenv("/root/shein/.env")

tokens = {}
for k, v in os.environ.items():
    if ("BOT_TOKEN" in k or k == "TELEGRAM_BOT_TOKEN") and v:
        tokens[k] = v

for k, tok in tokens.items():
    try:
        url = f"https://api.telegram.org/bot{tok}/getMe"
        res = json.loads(urllib.request.urlopen(url).read().decode())
        u = res.get("result", {})
        username = u.get("username")
        first_name = u.get("first_name")
        print(f"{k} -> @{username} | Name: {first_name}")
    except Exception as e:
        print(f"{k} -> error: {e}")
