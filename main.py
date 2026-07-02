import json
import os
import time
import urllib.parse
import urllib.request

from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")

if TOKEN == "YOUR_BOT_TOKEN_HERE":
    print("Bot tokenini o'zingizning Telegram bot tokeningiz bilan almashtiring.")
    print("Masalan: $env:TELEGRAM_BOT_TOKEN='8766488720:AAEFFqzOUQcdzQ1ywvAjfP1VgoqUDSO2t88'")
    raise SystemExit(1)


def api(method, data=None):
    url = f"https://api.telegram.org/bot{TOKEN}/{method}"
    if data is None:
        request = urllib.request.Request(url, method="GET")
    else:
        body = urllib.parse.urlencode(data).encode()
        request = urllib.request.Request(url, data=body, method="POST")

    with urllib.request.urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def send_message(chat_id, text):
    api("sendMessage", {"chat_id": chat_id, "text": text, "parse_mode": "HTML"})


def main():
    print("Bot ishga tushdi. To'xtatish uchun Ctrl+C bosing.")
    offset = 0

    while True:
        try:
            result = api("getUpdates", {"offset": offset, "timeout": 10})
        except Exception as exc:
            print("Xatolik yuz berdi:", exc)
            time.sleep(5)
            continue

        for update in result.get("result", []):
            offset = update["update_id"] + 1
            message = update.get("message", {})
            chat_id = message.get("chat", {}).get("id")
            text = (message.get("text") or "").strip()

            if not chat_id:
                continue

            if text in ["/start", "/help"]:
                send_message(chat_id, "Salom! Men oddiy Telegram botman. Menga biror xabar yozing.")
            else:
                send_message(chat_id, f"Siz yozgan xabar: {text}")


if __name__ == "__main__":
    main()
