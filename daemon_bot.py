import subprocess
import os

def start():
    # Kill any existing instance
    os.system("pkill -9 -f telegram_bot.py 2>/dev/null || true")
    
    log_file = open("/root/shein/telegram_bot.log", "a")
    p = subprocess.Popen(
        ["/root/venv/bin/python", "-u", "/root/shein/telegram_bot.py"],
        cwd="/root/shein",
        stdin=subprocess.DEVNULL,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        start_new_session=True
    )
    print(f"Telegram bot process started with PID: {p.pid}")

if __name__ == "__main__":
    start()
