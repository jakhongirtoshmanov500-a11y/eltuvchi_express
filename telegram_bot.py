"""
Telegram bot bilan bog'liq barcha funksiyalar shu yerda.

Ishlash prinsipi: WEBHOOK usuli — ya'ni bot doim ishlayotgan alohida
jarayon (process) sifatida emas, balki bizning FastAPI serverimizga
Telegram o'zi xabar yuborib turadi (POST /telegram/webhook orqali).
Bu — Render kabi web-service muhitida eng qulay va barqaror usul,
chunki alohida "doim ishlab turadigan" process kerak bo'lmaydi.
"""
import os
import httpx

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_API_BASE = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}" if TELEGRAM_BOT_TOKEN else None


async def send_telegram_message(chat_id, text: str, reply_markup: dict | None = None) -> None:
    """Berilgan chat_id'ga xabar yuboradi. Token yo'q yoki xatolik bo'lsa,
    dastur qulamaydi — faqat konsolga yozib qo'yadi (xabar yuborilmasligi
    tizimning boshqa qismlarini to'xtatib qo'ymasligi kerak)."""
    if not TELEGRAM_API_BASE:
        print("DIQQAT: TELEGRAM_BOT_TOKEN .env'da topilmadi — xabar yuborilmadi.")
        return
    if not chat_id:
        return

    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if reply_markup:
        payload["reply_markup"] = reply_markup

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(f"{TELEGRAM_API_BASE}/sendMessage", json=payload)
            if resp.status_code != 200:
                print(f"Telegram xabar yuborishda xatolik: {resp.status_code} {resp.text}")
    except Exception as e:
        print(f"Telegram xabar yuborishda istisno: {e}")


def contact_request_keyboard() -> dict:
    """Foydalanuvchidan telefon raqamini so'raydigan tugma (Telegram'ning
    o'zi telefon raqamini "ulashish" imkonini beradi, qo'lda yozdirmaymiz —
    bu xato ehtimolini yo'qotadi)."""
    return {
        "keyboard": [[{"text": "📱 Telefon raqamni ulashish", "request_contact": True}]],
        "resize_keyboard": True,
        "one_time_keyboard": True,
    }


def normalize_phone(raw_phone: str) -> str:
    """Telegram ba'zan '+' belgisisiz yuboradi (masalan '998901234567'),
    bazamizda esa '+998901234567' ko'rinishida saqlanadi — buni tenglashtiramiz."""
    phone = raw_phone.strip().replace(" ", "").replace("-", "")
    if not phone.startswith("+"):
        phone = "+" + phone
    return phone


async def set_telegram_webhook(webhook_url: str) -> dict:
    """Serverga bir marta ishga tushirilganda chaqiriladi — Telegram'ga
    'endi xabarlarni shu manzilga yubor' deb aytadi."""
    if not TELEGRAM_API_BASE:
        return {"ok": False, "error": "TELEGRAM_BOT_TOKEN yo'q"}
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(f"{TELEGRAM_API_BASE}/setWebhook", json={"url": webhook_url})
        return resp.json()
