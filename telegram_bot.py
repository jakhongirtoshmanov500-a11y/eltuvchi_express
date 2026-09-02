"""
Eltuvchi Express & J-Global Tijorat Tizimi
Telegram Bot va Mini App Integratsiyasi (Production-Ready Versiya)

Ushbu modul yuqori yuklama (high-load) sharoitida buyurtmalarni uzilishlarsiz 
qabul qilish, mijoz/kuryer bildirishnomalarini tezkor yuborish va 
Telegram Mini App initData xavfsizligini ta'minlash uchun mo'ljallangan.
"""

import os
import re
import time
import hashlib
import hmac
import json as _json
from urllib.parse import parse_qsl
import httpx

# Ekologik o'zgaruvchilardan tokenni olish
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_API_BASE = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}" if TELEGRAM_BOT_TOKEN else None

# Yuqori yuklamaga mo'ljallangan global HTTP Async Ulanishlar Hovuzi (Connection Pool)
# Limits: bir vaqtning o'zida 100 ta ulanish va 20 ta doimiy ochiq liniya (keep-alive)
http_client = httpx.AsyncClient(
    timeout=httpx.Timeout(10.0, connect=5.0),
    limits=httpx.Limits(max_connections=100, max_keepalive_connections=20)
)


async def close_telegram_bot_client():
    """FastAPI server to'xtatilganda HTTP mijozni xotiradan xavfsiz o'chirish."""
    await http_client.aclose()


async def send_telegram_message(chat_id: int | str, text: str, reply_markup: dict | None = None) -> bool:
    """
    Berilgan chat_id'ga HTML formatida bildirishnoma yuboradi.
    
    Tizim qulamasligi uchun barcha xatoliklar ushlanadi hamda async logga yoziladi.
    Yuqori yuklamalarda so'rovlar navbat bilan, serverni sekinlashtirmasdan uzatiladi.
    """
    if not TELEGRAM_API_BASE:
        print("DIQQAT: TELEGRAM_BOT_TOKEN .env faylida topilmadi — xabar yuborish o'tkazib yuborildi.")
        return False
    if not chat_id:
        return False

    payload = {
        "chat_id": chat_id, 
        "text": text, 
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup

    try:
        resp = await http_client.post(f"{TELEGRAM_API_BASE}/sendMessage", json=payload)
        if resp.status_code == 200:
            return True
        else:
            print(f"[Xatolar Logi] Telegram API Xatosi: Status {resp.status_code} | Tafsilot: {resp.text}")
            return False
    except httpx.RequestError as exc:
        print(f"[Tarmoq Xatosi] Telegram serveriga ulanishda uzilish: {exc}")
        return False
    except Exception as e:
        print(f"[Kutilmagan Xatolik] send_telegram_message: {e}")
        return False


def contact_request_keyboard() -> dict:
    """Foydalanuvchidan telefon raqamini tasdiqlashni so'rovchi rasmiy tugma."""
    return {
        "keyboard": [[{"text": "📱 Telefon raqamni ulashish", "request_contact": True}]],
        "resize_keyboard": True,
        "one_time_keyboard": True,
    }


def normalize_phone(raw_phone: str) -> str:
    """
    Kiritilgan har qanday formatdagi telefon raqamini tozalaydi va
    yagona standart (+998XXXXXXXXX) ko'rinishiga keltirib beradi.
    
    Masalan: '8 (90) 123-45-67' -> '+998901234567' (agar 9 xonali bo'lsa +998 ulanadi)
    """
    if not raw_phone:
        return ""
    
    # Faqat raqamli belgilarni ajratib olish
    digits = re.sub(r"\D", "", raw_phone)
    
    # O'zbekiston raqamlari standarti uchun
    if len(digits) == 9:
        digits = "998" + digits
    elif len(digits) == 12 and digits.startswith("8"):
        digits = "998" + digits[3:]
        
    return f"+{digits}"


async def set_telegram_webhook(webhook_url: str) -> dict:
    """
    FastAPI server ishga tushganda Telegram Webhook'ni avtomatik sozlashi uchun.
    Ilova doimiy rejimda uzilishlarsiz ishlashini kafolatlaydi.
    """
    if not TELEGRAM_API_BASE:
        return {"ok": False, "error": "TELEGRAM_BOT_TOKEN sozlanmagan"}
    try:
        resp = await http_client.post(
            f"{TELEGRAM_API_BASE}/setWebhook", 
            json={"url": webhook_url, "drop_pending_updates": False}
        )
        return resp.json()
    except Exception as e:
        return {"ok": False, "error": str(e)}


def validate_telegram_init_data(init_data: str, max_age_seconds: int = 86400) -> dict | None:
    """
    Telegram Mini App (WebApp) orqali yuborilgan initData xavfsizlik kalitini 
    HMAC-SHA256 standarti bo'yicha vaqt va imzolarini tekshiradi.
    
    Soxta buyurtmalar va tajovuzlarning oldini oladi.
    """
    if not TELEGRAM_BOT_TOKEN or not init_data:
        return None

    try:
        parsed = dict(parse_qsl(init_data, strict_parsing=True))
        received_hash = parsed.pop("hash", None)
        if not received_hash:
            return None

        # Replay Attack (soxta ma'lumotlarni takroran yuborish) xavfidan xavfsizlik:
        auth_date = int(parsed.get("auth_date", 0))
        if (time.time() - auth_date) > max_age_seconds:
            print("[Xavfsizlik Ogohlantirishi] initData vaqti o'tib ketgan (Expired Session).")
            return None

        # Telegram standartiga ko'ra ma'lumotlarni saralash va tekshirish
        data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
        secret_key = hmac.new(b"WebAppData", TELEGRAM_BOT_TOKEN.encode(), hashlib.sha256).digest()
        computed_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

        if not hmac.compare_digest(computed_hash, received_hash):
            print("[Xavfsizlik Ogohlantirishi] Soxtalashtirilgan initData aniqlandi!")
            return None

        user_json = parsed.get("user")
        if not user_json:
            return None
            
        return _json.loads(user_json)
    except Exception as e:
        print(f"[Avariya Logi] initData tekshirishda xatolik: {e}")
        return None