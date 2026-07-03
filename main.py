import json
import os
import random
import re
import threading
import time
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

if not TOKEN:
    print("Bot tokeni topilmadi. Renderga yuklash uchun TELEGRAM_BOT_TOKEN muhit o'zgaruvchisini qo'shing.")
    print("Render Dashboard -> Environment -> Add Variable:")
    print("  Name: TELEGRAM_BOT_TOKEN")
    print("  Value: 123456:ABCDEF...")
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


FUNNY_INTROS = [
    "🎭 Diqqat-e'tibor bilan tinglang, aka:",
    "🤡 Rasmiy bayonot:",
    "📢 Butun mahalla bilsin:",
    "🍿 Voqea shunday bo'lgan:",
    "😂 Hazilakam bo'lsa ham eshiting:",
    "🎬 Film qahramoni sifatida aytsam:",
    "👑 Shohona tarzda e'lon qilaman:",
]

FUNNY_OUTROS = [
    "...va butun qishloq qotib-qotib kuldi! 😂🤣",
    "...shundan keyin hamma tarqalib ketdi. 🚶‍♂️💨",
    "...bunga hatto qo'shni ham hayron qoldi. 🧐",
    "...Netflix bunga serial chiqarsa bo'ladi. 🍿🎬",
    "...tarixga shu tarzda kirib qoldi. 📜✨",
    "...mushuk ham buni eshitib miyovladi. 🐱",
    "...bu haqda hali qo'shiq yozilmagan, lekin yoziladi. 🎤",
]

FUNNY_WORD_SWAPS = {
    "salom": "assalomu alaykum, ey buyuk zot 🙇",
    "yaxshi": "a'lo darajada zo'r 🔥",
    "yomon": "falokat darajasida yomon 💀",
    "pul": "million-milliard pul 💰🤑",
    "uxlamoqchiman": "bir hafta uxlab, ayiq kabi qishlamoqchiman 🐻💤",
    "ovqat": "qirol dasturxonidagi ziyofat 🍗👑",
    "charchadim": "poezd tortib kelgandek charchadim 🚂😵",
}


def funnify(text):
    if not text:
        return "Siz hech narsa yozmadingiz, lekin bo'sh joyning o'zi ham kulgili ekan! 😄"

    funny_text = text
    for word, replacement in FUNNY_WORD_SWAPS.items():
        funny_text = re.sub(rf"\b{re.escape(word)}\b", replacement, funny_text, flags=re.IGNORECASE)

    # Ba'zi so'zlarni tasodifiy bosh harflar bilan CHIROYLI qilib "qichqirtiramiz"
    words = funny_text.split()
    if len(words) > 2:
        idx = random.randrange(len(words))
        words[idx] = words[idx].upper() + random.choice(["‼️", "🔥", "😱", "🎉"])
        funny_text = " ".join(words)

    intro = random.choice(FUNNY_INTROS)
    outro = random.choice(FUNNY_OUTROS)

    return f"{intro}\n\n\u201c{funny_text}\u201d\n\n{outro}"


class _HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Bot ishlayapti")

    def log_message(self, format, *args):
        pass  # Konsolni keraksiz log yozuvlaridan tozalash


def start_health_server():
    port = int(os.getenv("PORT", "10000"))
    server = HTTPServer(("0.0.0.0", port), _HealthCheckHandler)
    server.serve_forever()


def main():
    # Render "Web Service" portni kutadi, shuning uchun alohida oqimda
    # kichik HTTP server ishga tushiramiz, bot esa asosiy oqimda ishlayveradi.
    threading.Thread(target=start_health_server, daemon=True).start()

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
                send_message(
                    chat_id,
                    "Salom! Men kulgi botiman 🤖😂\nMenga nima yozsangiz, uni yanada "
                    "kulgiliroq qilib qaytaraman. Sinab ko'ring!",
                )
            else:
                send_message(chat_id, funnify(text))


if __name__ == "__main__":
    main()