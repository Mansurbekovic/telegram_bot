import os
import sys

from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
_admin_chat_id_raw = os.getenv("ADMIN_CHAT_ID")

if not BOT_TOKEN:
    print("XATOLIK: BOT_TOKEN environment o'zgaruvchisi topilmadi.")
    sys.exit(1)

if not _admin_chat_id_raw:
    print("XATOLIK: ADMIN_CHAT_ID environment o'zgaruvchisi topilmadi.")
    sys.exit(1)

try:
    # Group chat IDs are negative (e.g. -1001234567890)
    ADMIN_CHAT_ID = int(_admin_chat_id_raw)
except ValueError:
    print("XATOLIK: ADMIN_CHAT_ID butun son bo'lishi kerak (masalan -1001234567890).")
    sys.exit(1)

PORT = int(os.getenv("PORT", "10000"))
