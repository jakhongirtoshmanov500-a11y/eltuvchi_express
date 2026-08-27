import asyncio
from sqlalchemy.future import select
from database import AsyncSessionLocal, engine, Base
import models
from models import User, UserRole, SystemSetting

async def init_data():
    # 1. Barcha jadvallarni yaratish
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # 2. Boshlang'ich ma'lumotlarni kiritish
    async with AsyncSessionLocal() as db:
        try:
            # Tizim Egasini (Owner) tekshirish va yaratish
            result = await db.execute(select(User).filter(User.role == UserRole.OWNER))
            owner = result.scalars().first()
            
            if not owner:
                owner = User(
                    full_name="Jakhongir Toshmanov",
                    phone_number="+998930894418",
                    role=UserRole.OWNER
                )
                db.add(owner)
                print("--> Tizim Egasi (Owner) profili bazada yaratildi!")

            # Boshlang'ich Ob-havo va Tizim Sozlamalarini yaratish
            setting_result = await db.execute(select(SystemSetting))
            setting = setting_result.scalars().first()

            if not setting:
                default_setting = SystemSetting(
                    base_delivery_fee=10000.0,
                    service_commission_percent=10.0,
                    weather_multiplier=1.0,
                    auto_weather_pricing=True
                )
                db.add(default_setting)
                print("--> Boshlang'ich tizim va ob-havo sozlamalari yaratildi!")

            await db.commit()
            print("--> Baza muvaffaqiyatli tayyorlandi va yangilandi!")

        except Exception as e:
            print(f"Xatolik yuz berdi: {e}")
            await db.rollback()

if __name__ == "__main__":
    asyncio.run(init_data())