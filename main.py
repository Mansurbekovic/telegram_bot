"""
main.py — Feedback / Order Management Bot (aiogram 3.x)

Architecture
------------
Client (private chat) --/start, description--> Bot --forwards--> Admin Group
Admin (native "Reply" in group)  --> Bot parses Client ID --> Bot --> Client (private chat)

Design notes
------------
- Stateless bridge: the only "state" the system needs (which client an admin
  message belongs to) is carried inside the forwarded message's own text via
  a `Client ID` tag, so nothing needs to be persisted or held in memory.
- No database, no FSM storage — keeps memory footprint minimal for
  constrained environments such as Render's Free tier (512MB RAM).
- Every outbound message to a *client* goes through `safe_send_message`,
  which absorbs `TelegramForbiddenError` (user blocked the bot) and any
  other delivery failure without ever propagating into the polling loop.
- User-supplied text is HTML-escaped before being embedded in an
  HTML-parsed message, so a name or message containing `<`/`&`/etc.
  can't break formatting or inject unintended markup.
"""

from __future__ import annotations

import asyncio
import html
import logging
import re
import signal
from dataclasses import dataclass

from aiogram import Bot, Dispatcher, Router, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ChatType, ParseMode
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.filters import BaseFilter, Command, CommandStart
from aiogram.types import Message
from aiohttp import web

import config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger("feedback_bot")

CLIENT_ID_TAG_RE = re.compile(r"🆔 Client ID:\s*(\d+)")

WELCOME_TEXT = (
    "👋 Assalomu alaykum!\n\n"
    "Bu — buyurtma / fikr-mulohaza boti. Qanday ilova (APK) buyurtma qilmoqchi "
    "bo'lsangiz, uni bir xabarda batafsil yozib yuboring "
    "(masalan: ilova nomi, veb-sayt manzili, qo'shimcha talablar).\n\n"
    "Xabaringizni administratorga yuboraman va tez orada javob olasiz."
)
HELP_TEXT = (
    "Shunchaki xohlagan ilovangiz haqida yozing — men uni administratorga "
    "yetkazaman. Boshlash uchun /start."
)
RECEIVED_TEXT = "✅ Your request has been received. The admin will review it and reply shortly."
NON_TEXT_PROMPT = (
    "Iltimos, buyurtmangizni matn (text) ko'rinishida yuboring — shunda uni "
    "administratorga to'g'ri yetkaza olaman."
)
ADMIN_SEND_FAILED_TEXT = (
    "⚠️ Xabaringizni yuborishda texnik xatolik yuz berdi. Birozdan so'ng qayta urinib ko'ring."
)
DELIVERED_TEXT = "✅ Reply delivered to client."
DELIVERY_FAILED_TEXT = "❌ Javobni yetkazib bo'lmadi — foydalanuvchi botni bloklagan bo'lishi mumkin."
TEXT_ONLY_REPLY_WARNING = "⚠️ Faqat matnli javoblarni yuborish mumkin."


@dataclass(frozen=True)
class ClientInfo:
    """Normalized, HTML-safe representation of a Telegram user for display."""

    user_id: int
    display_name: str
    username: str | None

    @classmethod
    def from_message(cls, message: Message) -> "ClientInfo":
        user = message.from_user
        return cls(
            user_id=user.id,
            display_name=html.escape(user.full_name or "Noma'lum"),
            username=user.username,
        )

    @property
    def username_line(self) -> str:
        return f"@{html.escape(self.username)}" if self.username else "yo'q"


class ReplyToBotMessage(BaseFilter):
    """True only when the update is a reply to a message the bot itself sent."""

    async def __call__(self, message: Message, bot: Bot) -> bool:
        reply = message.reply_to_message
        return bool(reply and reply.from_user and reply.from_user.id == bot.id)


def build_admin_order_message(client: ClientInfo, content: str) -> str:
    """Format the message forwarded to the admin group, with the tracking tag."""
    safe_content = html.escape(content)
    return (
        "📝 <b>New Order / Message</b>\n\n"
        f"👤 <b>Name:</b> {client.display_name}\n"
        f"🔗 <b>Username:</b> {client.username_line}\n"
        f"🆔 <b>Telegram ID:</b> <code>{client.user_id}</code>\n\n"
        f"💬 <b>Content:</b>\n{safe_content}\n\n"
        f"🆔 Client ID: {client.user_id}"
    )


def extract_client_id(order_message_text: str) -> int | None:
    match = CLIENT_ID_TAG_RE.search(order_message_text)
    return int(match.group(1)) if match else None


class FeedbackBot:
    """Wires together the bot, dispatcher, routers, and health-check server."""

    def __init__(self, token: str, admin_chat_id: int, port: int) -> None:
        self.admin_chat_id = admin_chat_id
        self.port = port
        self.bot = Bot(token=token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
        self.dp = Dispatcher()
        self._runner: web.AppRunner | None = None
        self._register_routers()

    # -- routing setup --------------------------------------------------

    def _register_routers(self) -> None:
        self.dp.include_router(self._build_client_router())
        self.dp.include_router(self._build_admin_router())

    def _build_client_router(self) -> Router:
        router = Router(name="client")

        @router.message(CommandStart(), F.chat.type == ChatType.PRIVATE)
        async def cmd_start(message: Message) -> None:
            await message.answer(WELCOME_TEXT)

        @router.message(Command("help"), F.chat.type == ChatType.PRIVATE)
        async def cmd_help(message: Message) -> None:
            await message.answer(HELP_TEXT)

        @router.message(F.chat.type == ChatType.PRIVATE, F.text, ~F.text.startswith("/"))
        async def handle_description(message: Message) -> None:
            await self._handle_client_description(message)

        @router.message(F.chat.type == ChatType.PRIVATE)
        async def handle_other_content(message: Message) -> None:
            await message.answer(NON_TEXT_PROMPT)

        return router

    def _build_admin_router(self) -> Router:
        router = Router(name="admin")

        @router.message(
            F.chat.id == self.admin_chat_id,
            F.reply_to_message,
            ReplyToBotMessage(),
        )
        async def handle_admin_reply(message: Message) -> None:
            await self._handle_admin_reply(message)

        return router

    # -- client-facing logic ---------------------------------------------

    async def _handle_client_description(self, message: Message) -> None:
        client = ClientInfo.from_message(message)
        order_text = build_admin_order_message(client, message.text)

        try:
            await self.bot.send_message(chat_id=self.admin_chat_id, text=order_text)
        except Exception:
            logger.exception("Admin guruhga xabar yuborib bo'lmadi (client_id=%s)", client.user_id)
            await message.answer(ADMIN_SEND_FAILED_TEXT)
            return

        await message.answer(RECEIVED_TEXT)

    # -- admin-facing logic -----------------------------------------------

    async def _handle_admin_reply(self, message: Message) -> None:
        parent_text = message.reply_to_message.text or message.reply_to_message.caption or ""
        client_id = extract_client_id(parent_text)
        if client_id is None:
            # Reply to some other bot message (e.g. a confirmation) — not an order thread.
            return

        reply_text = message.text or message.caption
        if not reply_text:
            await message.reply(TEXT_ONLY_REPLY_WARNING)
            return

        delivered = await self.safe_send_message(client_id, f"👨‍💻 Admin Reply: {reply_text}")
        await message.reply(DELIVERED_TEXT if delivered else DELIVERY_FAILED_TEXT)

    # -- outbound delivery guard -------------------------------------------

    async def safe_send_message(self, chat_id: int, text: str) -> bool:
        """Send a message to a client, absorbing any delivery failure."""
        try:
            await self.bot.send_message(chat_id=chat_id, text=text)
            return True
        except TelegramForbiddenError:
            logger.warning("Foydalanuvchi botni bloklagan (chat_id=%s).", chat_id)
        except TelegramBadRequest as exc:
            logger.warning("Bad request xabar yuborishda (chat_id=%s): %s", chat_id, exc)
        except Exception:
            logger.exception("Kutilmagan xatolik xabar yuborishda (chat_id=%s)", chat_id)
        return False

    # -- health-check server (keeps Render's free Web Service happy) ------

    async def _start_health_server(self) -> None:
        app = web.Application()
        app.router.add_get("/", lambda _request: web.Response(text="Bot ishlayapti"))
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, "0.0.0.0", self.port)
        await site.start()
        logger.info("Health-check server %s portda ishga tushdi.", self.port)

    async def _stop_health_server(self) -> None:
        if self._runner is not None:
            await self._runner.cleanup()

    # -- lifecycle ----------------------------------------------------------

    async def run(self) -> None:
        await self._start_health_server()
        try:
            logger.info("Bot polling boshlandi.")
            await self.dp.start_polling(self.bot, handle_signals=False)
        finally:
            await self._stop_health_server()
            await self.bot.session.close()
            logger.info("Bot to'xtatildi, resurslar tozalandi.")


async def _main() -> None:
    app = FeedbackBot(token=config.BOT_TOKEN, admin_chat_id=config.ADMIN_CHAT_ID, port=config.PORT)

    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop_event.set)

    run_task = asyncio.create_task(app.run())
    await stop_event.wait()

    logger.info("To'xtatish signali qabul qilindi, bot yakunlanmoqda...")
    run_task.cancel()
    try:
        await run_task
    except asyncio.CancelledError:
        pass


if __name__ == "__main__":
    asyncio.run(_main())
