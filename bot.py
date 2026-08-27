import os
import asyncio
import logging
import httpx
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
API_URL = os.getenv("API_URL", "http://127.0.0.1:8000")

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# --- ASOSIY MENYU BTN ---
def get_main_keyboard():
    # Paramer qo'shilgan Pinggy havolasi
    web_app_url = "https://ssvdg-84-54-72-15.run.pinggy-free.link?ngrok-skip-browser-warning=true"

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🛍️ Buyurtma berish (Mini App)",
                    web_app=WebAppInfo(url=web_app_url)
                )
            ],
            [
                InlineKeyboardButton(text="📦 Pochta jo'natish", callback_data="send_parcel"),
                InlineKeyboardButton(text="🚖 Kuryer bo'lib ishlash", callback_data="become_courier")
            ],
            [
                InlineKeyboardButton(text="📞 Qo'llab-quvvatlash", callback_data="support")
            ]
        ]
    )
    return keyboard

# /start komandasi
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_name = message.from_user.full_name
    tg_id = str(message.from_user.id)

    # Backend API bilan bog'lanib foydalanuvchini ro'yxatdan o'tkazish
    async with httpx.AsyncClient() as client:
        try:
            await client.post(
                f"{API_URL}/users/",
                json={
                    "telegram_id": tg_id,
                    "full_name": user_name,
                    "phone_number": tg_id,
                    "role": "client"
                }
            )
        except Exception as e:
            logging.error(f"Backend API bilan ulanishda xato: {e}")

    welcome_text = (
        f"Assalomu alaykum, {user_name}!\n\n"
        f"**Eltuvchi Express** xizmatiga xush kelibsiz!\n"
        f"Uchquduq va Zarafshon bo'ylab tezkor yetkazib berish va pochta xizmatlaridan foydalanishingiz mumkin."
    )
    await message.answer(welcome_text, parse_mode="Markdown", reply_markup=get_main_keyboard())

async def main():
    # Eski webhookni o'chiramiz va to'planib qolgan eski xabarlarni tozalaymiz
    await bot.delete_webhook(drop_pending_updates=True)
    print("Bot muvaffaqiyatli ishga tushdi!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())