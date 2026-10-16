import urllib.request
import json
import os
from dotenv import load_dotenv

load_dotenv("/root/shein/.env")

for k, v in os.environ.items():
    if ("BOT_TOKEN" in k or k == "TELEGRAM_BOT_TOKEN") and v:
        try:
            url = f"https://api.telegram.org/bot{v}/getUpdates"
            res = json.loads(urllib.request.urlopen(url).read().decode())
            results = res.get("result", [])
            print(f"=== {k} (updates count: {len(results)}) ===")
            for item in results:
                msg = item.get("message", {})
                sender = msg.get("from", {}).get("first_name")
                chat_id = msg.get("chat", {}).get("id")
                txt = msg.get("text")
                print(f"   from: {sender} ({chat_id}) text: {txt}")
        except Exception as e:
            print(f"{k} err: {e}")
