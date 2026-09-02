"""
Telegram bot bilan bog'liq barcha funksiyalar shu yerda.

Ishlash prinsipi: WEBHOOK usuli — ya'ni bot doim ishlayotgan alohida
jarayon (process) sifatida emas, balki bizning FastAPI serverimizga
Telegram o'zi xabar yuborib turadi (POST /telegram/webhook orqali).
Bu — Render kabi web-service muhitida eng qulay va barqaror usul.
"""
import os
import httpx
from typing import Optional


def get_telegram_api_base() -> Optional[str]:
    """Tokenni har safar jonli ravishda environment'dan o'qiydi.
    Bu import paytidagi keshlanib qolish xatosini butunlay yo'qotadi."""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if token:
        token = token.strip()
        return f"https://api.telegram.org/bot{token}"
    return None


async def send_telegram_message(chat_id, text: str, reply_markup: Optional[dict] = None) -> None:
    """Berilgan chat_id'ga xabar yuboradi."""
    api_base = get_telegram_api_base()
    if not api_base:
        print("DIQQAT: TELEGRAM_BOT_TOKEN .env'da topilmadi — xabar yuborilmadi.")
        return
    if not chat_id:
        return

    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if reply_markup:
        payload["reply_markup"] = reply_markup

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(f"{api_base}/sendMessage", json=payload)
            if resp.status_code != 200:
                print(f"Telegram xabar yuborishda xatolik: {resp.status_code} {resp.text}")
    except Exception as e:
        print(f"Telegram xabar yuborishda istisno: {e}")


def contact_request_keyboard() -> dict:
    """Foydalanuvchidan telefon raqamini so'raydigan tugma."""
    return {
        "keyboard": [[{"text": "📱 Telefon raqamni ulashish", "request_contact": True}]],
        "resize_keyboard": True,
        "one_time_keyboard": True,
    }


def normalize_phone(raw_phone: str) -> str:
    """Telefon raqamini standart formatga keltirish (+998...)."""
    phone = raw_phone.strip().replace(" ", "").replace("-", "")
    if not phone.startswith("+"):
        phone = "+" + phone
    return phone


async def set_telegram_webhook(webhook_url: str) -> dict:
    """Serverga bir marta ishga tushirilganda chaqiriladi — Webhook o'rnatadi."""
    api_base = get_telegram_api_base()
    if not api_base:
        return {"ok": False, "error": "TELEGRAM_BOT_TOKEN environment'dan topilmadi"}
    
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(f"{api_base}/setWebhook", json={"url": webhook_url})
            return resp.json()
    except Exception as e:
        return {"ok": False, "error": str(e)}