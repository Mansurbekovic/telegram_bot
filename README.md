# Feedback / Order Management Bot — Setup

## 1. BOT_TOKEN olish
1. Telegram'da [@BotFather](https://t.me/BotFather) ga yozing.
2. `/newbot` -> nom va username bering.
3. Sizga beriladigan tokenni saqlang — bu `BOT_TOKEN`.

## 2. ADMIN_CHAT_ID (guruh ID) olish
1. Yangi Telegram guruh yarating (masalan "Buyurtmalar").
2. Botni shu guruhga a'zo qiling.
3. Guruh ID'sini bilish uchun eng oson yo'l: guruhga [@userinfobot](https://t.me/userinfobot)
   ni qo'shing yoki botga guruhda biror narsa yozdirib, `getUpdates` orqali
   `chat.id` maydonini o'qing (u manfiy son bo'ladi, masalan `-1001234567890`).
4. Botning guruhda xabarlarni o'qiy olishi uchun BotFather'da
   `/setprivacy` -> `Disable` qiling (aks holda bot guruhdagi oddiy xabarlarni,
   jumladan admin javoblarini, ko'ra olmaydi — faqat @mention yoki reply'larni ko'radi,
   privacy disabled bo'lsa hammasi ko'rinadi va reply mexanizmi ishonchli ishlaydi).

## 3. Lokal ishga tushirish
```bash
pip install -r requirements.txt
cp _env.example .env   # keyin BOT_TOKEN va ADMIN_CHAT_ID ni to'ldiring
python main.py
```

## 4. Render'ga deploy qilish (Free tier)
1. Kodni GitHub repo'ga push qiling.
2. Render Dashboard -> New -> Web Service -> repo'ni tanlang.
3. Build Command: `pip install -r requirements.txt`
4. Start Command: `python main.py`
5. Environment -> quyidagilarni qo'shing:
   - `BOT_TOKEN`
   - `ADMIN_CHAT_ID`
6. Deploy qiling. Free tarif bu bot uchun to'liq yetarli — hech qanday og'ir
   hisoblash (compiling, ML va h.k.) yo'q, faqat matn almashinuvi.

## Ishlash mantig'i (qisqacha)

**Mijoz tomonidan:**
1. `/start` -> xush kelibsiz xabari
2. Mijoz matn yozadi -> bot uni quyidagi formatda admin guruhga yuboradi:
   ```
   📝 New Order / Message

   👤 Name: Ism Familiya
   🔗 Username: @username
   🆔 Telegram ID: 123456789

   💬 Content:
   <mijoz yozgan matn>

   🆔 Client ID: 123456789
   ```
3. Mijozga: "✅ Your request has been received..."

**Admin tomonidan:**
1. Guruhdagi shu xabarga Telegram'ning tabiiy "Reply" funksiyasi bilan javob yozasiz.
2. Bot xabar matnidagi `🆔 Client ID: <raqam>` qatorini o'qib, mijozni topadi.
3. Mijozga shaxsiy chatda quyidagicha yuboriladi:
   ```
   👨‍💻 Admin Reply: <sizning matningiz>
   ```
4. Guruhga tasdiq: "✅ Reply delivered to client."

## Nega bu Render Free (512MB)'da barqaror ishlaydi
- Ma'lumotlar bazasi yo'q — hech narsa diskka yozilmaydi.
- FSM/session xotira ishlatilmaydi — har bir xabar mustaqil qayta ishlanadi,
  kerakli barcha ma'lumot (Client ID) xabar matnining o'zida saqlanadi.
- Faqat matn almashinuvi — CPU/RAM yukini oshiradigan hech qanday operatsiya yo'q.
- Har bir tashqi xabar yuborish `try/except` bilan o'ralgan — foydalanuvchi botni
  bloklab qo'ysa ham (`TelegramForbiddenError`), jarayon yiqilib qolmaydi.
