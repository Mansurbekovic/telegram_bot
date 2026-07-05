import http.client
import json
import os
import re
import socket
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

from config import ADMIN_CHAT_ID, BOT_TOKEN, PORT

API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}/"

CLIENT_ID_PATTERN = re.compile(r"🆔 Client ID:\s*(-?\d+)")

# getUpdates uzluksiz ishlashi uchun sozlamalar
POLL_TIMEOUT = 30           # Telegram long-polling kutish vaqti (soniya)
MIN_RETRY_DELAY = 2         # birinchi xatodan keyingi kutish (soniya)
MAX_RETRY_DELAY = 60        # ketma-ket xatolarda kutish shu qiymatdan oshmaydi
HEARTBEAT_INTERVAL = 300    # necha soniyada bir marta "tirikman" logi chiqadi
SELF_PING_INTERVAL = 600    # 10 daqiqada bir marta o'zini "uyg'otib" turadi (Render Free uxlamasin uchun)


def api(method, data=None, timeout=25):
    url = API_URL + method
    if data is None:
        request = urllib.request.Request(url, method="GET")
    else:
        body = urllib.parse.urlencode(data).encode()
        request = urllib.request.Request(url, data=body, method="POST")

    # Bu yerda maxsus network xatolari (timeout, uzilish, DNS va h.k.)
    # ataylab ushlanmaydi — ularni chaqiruvchi (getUpdates tsikli) mos
    # kutish (backoff) bilan qayta urinish uchun o'zi ushlaydi.
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def send_message(chat_id, text, reply_to_message_id=None):
    data = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if reply_to_message_id:
        data["reply_to_message_id"] = reply_to_message_id

    try:
        return api("sendMessage", data)
    except urllib.error.HTTPError as exc:
        print(f"sendMessage HTTP xatosi (chat_id={chat_id}):", exc.read())
    except Exception as exc:
        print(f"sendMessage xatosi (chat_id={chat_id}):", exc)
    return None


def build_admin_message(message):
    from_user = message.get("from", {})
    name = " ".join(filter(None, [from_user.get("first_name"), from_user.get("last_name")])) or "Noma'lum"
    username = f"@{from_user.get('username')}" if from_user.get("username") else "yo'q"
    client_id = from_user.get("id")
    text = message.get("text") or "(matn yo'q)"

    return (
        "📝 New Order / Message\n\n"
        f"👤 Name: {name}\n"
        f"🔗 Username: {username}\n"
        f"🆔 Telegram ID: {client_id}\n\n"
        f"💬 Content:\n{text}\n\n"
        f"🆔 Client ID: {client_id}"
    )


def handle_client_message(message):
    chat_id = message["chat"]["id"]
    text = (message.get("text") or "").strip()

    if text in ("/start", "/help"):
        send_message(
            chat_id,
            "Salom! 👋\nXabaringizni shu yerga yozing — biz uni ko'rib chiqamiz "
            "va imkon qadar tezroq javob beramiz.",
        )
        return

    admin_text = build_admin_message(message)
    result = send_message(ADMIN_CHAT_ID, admin_text)

    if result and result.get("ok"):
        send_message(chat_id, "✅ Sizning xabaringiz qabul qilindi. Tez orada javob beramiz.")
    else:
        send_message(
            chat_id,
            "⚠️ Xabaringizni yuborishda texnik xatolik yuz berdi. Birozdan so'ng qayta urinib ko'ring.",
        )


def handle_admin_reply(message):
    reply_to = message.get("reply_to_message")
    if not reply_to:
        return

    original_text = reply_to.get("text") or reply_to.get("caption") or ""
    match = CLIENT_ID_PATTERN.search(original_text)

    if not match:
        send_message(
            ADMIN_CHAT_ID,
            "⚠️ Ushbu xabardan Client ID topilmadi, javob yuborilmadi.",
            reply_to_message_id=message.get("message_id"),
        )
        return

    client_id = int(match.group(1))
    admin_reply_text = message.get("text") or ""

    result = send_message(client_id, f"👨‍💻 Admin Reply: {admin_reply_text}")

    if result and result.get("ok"):
        send_message(
            ADMIN_CHAT_ID,
            "✅ Reply delivered to client.",
            reply_to_message_id=message.get("message_id"),
        )
    else:
        send_message(
            ADMIN_CHAT_ID,
            "⚠️ Javobni mijozga yetkazib bo'lmadi (ehtimol u botni bloklagan).",
            reply_to_message_id=message.get("message_id"),
        )


class _HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Bot ishlayapti")

    def log_message(self, format, *args):
        pass  # Konsolni keraksiz log yozuvlaridan tozalash


def start_health_server():
    server = HTTPServer(("0.0.0.0", PORT), _HealthCheckHandler)
    server.serve_forever()


def self_ping_loop():
    """
    Render Free tarifida servisga 15 daqiqa hech qanday tashqi HTTP so'rov
    kelmasa, u avtomatik 'uxlab qoladi' (spin down). getUpdates ichki
    jarayon bo'lgani uchun bu holatning oldini olmaydi.

    Shuning uchun bot o'zining ochiq HTTP portiga (health-check) davriy
    ravishda o'zi so'rov yuborib turadi — bu Render uchun 'faol servis'
    signali bo'ladi va bot uxlab qolmaydi.

    Render bu servis uchun manzilni avtomatik SELF_URL yoki
    RENDER_EXTERNAL_URL muhit o'zgaruvchisida beradi.
    """
    self_url = os.getenv("SELF_URL") or os.getenv("RENDER_EXTERNAL_URL")

    if not self_url:
        print(
            "SELF_URL / RENDER_EXTERNAL_URL topilmadi - self-ping o'chirilgan. "
            "Bot Render Free'da 15 daqiqadan keyin uxlab qolishi mumkin. "
            "Render Environment'ga 'SELF_URL' qo'shing (masalan: https://sizning-app.onrender.com)."
        )
        return

    print(f"Self-ping yoqildi: {self_url} manzili har {SELF_PING_INTERVAL}s da so'raladi.")

    while True:
        time.sleep(SELF_PING_INTERVAL)
        try:
            with urllib.request.urlopen(self_url, timeout=15) as response:
                response.read()
            print("Self-ping OK")
        except Exception as exc:
            # Self-ping muvaffaqiyatsiz bo'lsa ham botning asosiy ishiga (Telegram bilan
            # ishlashiga) hech qanday ta'sir qilmaydi - shunchaki keyingi urinishda davom etadi.
            print(f"Self-ping xatosi (muhim emas, davom etamiz): {exc}")


def main():
    # Render "Web Service" portni kutadi, shuning uchun alohida oqimda
    # kichik HTTP server ishga tushiramiz, bot esa asosiy oqimda ishlayveradi.
    threading.Thread(target=start_health_server, daemon=True).start()
    threading.Thread(target=self_ping_loop, daemon=True).start()

    print("Bot ishga tushdi. To'xtatish uchun Ctrl+C bosing.")
    offset = 0
    retry_delay = MIN_RETRY_DELAY
    last_heartbeat = time.monotonic()

    while True:
        # --- "Tirikman" logi: Render loglarida bot qotmaganini ko'rish uchun ---
        now = time.monotonic()
        if now - last_heartbeat >= HEARTBEAT_INTERVAL:
            print("♥ heartbeat: bot ishlamoqda, offset =", offset)
            last_heartbeat = now

        # --- getUpdates: har xil xato turlarini alohida ushlab, mos backoff bilan qayta urinish ---
        try:
            result = api("getUpdates", {"offset": offset, "timeout": POLL_TIMEOUT}, timeout=POLL_TIMEOUT + 10)
        except (socket.timeout, TimeoutError):
            # Long-poll vaqti tugashi — bu normal holat, xato emas, darhol qayta so'raymiz
            continue
        except (urllib.error.URLError, ConnectionError, http.client.HTTPException, OSError) as exc:
            # Internet uzilishi / DNS / Telegram vaqtincha ishlamayotgani kabi holatlar
            print(f"getUpdates tarmoq xatosi: {exc}. {retry_delay}s dan keyin qayta urinamiz.")
            time.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, MAX_RETRY_DELAY)
            continue
        except json.JSONDecodeError as exc:
            print(f"getUpdates javobini o'qib bo'lmadi: {exc}. {retry_delay}s dan keyin qayta urinamiz.")
            time.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, MAX_RETRY_DELAY)
            continue
        except Exception as exc:
            # Kutilmagan har qanday xato — botni yiqitmasdan, kutib qayta urinamiz
            print(f"getUpdates kutilmagan xato: {exc}. {retry_delay}s dan keyin qayta urinamiz.")
            time.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, MAX_RETRY_DELAY)
            continue

        # So'rov muvaffaqiyatli o'tdi — kutish vaqtini boshlang'ich holatga qaytaramiz
        retry_delay = MIN_RETRY_DELAY

        if not result.get("ok"):
            print("getUpdates 'ok: false' qaytardi:", result)
            time.sleep(MIN_RETRY_DELAY)
            continue

        for update in result.get("result", []):
            offset = update["update_id"] + 1
            message = update.get("message")
            if not message:
                continue

            chat_id = message.get("chat", {}).get("id")
            if chat_id is None:
                continue

            try:
                if chat_id == ADMIN_CHAT_ID:
                    if message.get("reply_to_message"):
                        handle_admin_reply(message)
                    # Guruhdagi oddiy (reply bo'lmagan) xabarlar e'tiborsiz qoldiriladi
                else:
                    handle_client_message(message)
            except Exception as exc:
                # Bitta xabarni qayta ishlashdagi xato butun botni to'xtatmasligi kerak
                print("Xabarni qayta ishlashda xato:", exc)


if __name__ == "__main__":
    main()