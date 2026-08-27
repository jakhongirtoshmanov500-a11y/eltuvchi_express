import asyncio
from sqlalchemy import text
from database import engine

async def fix_database():
    async with engine.begin() as conn:
        # 1. Eski jadval va ENUM turini to'liq yo'qotamiz
        await conn.execute(text("DROP TABLE IF EXISTS system_settings CASCADE;"))
        await conn.execute(text("DROP TYPE IF EXISTS weathercondition CASCADE;"))
        
        # 2. Yangi WeatherCondition ENUM turini yaratamiz
        await conn.execute(text(
            "CREATE TYPE weathercondition AS ENUM ('CLEAR', 'RAIN', 'SNOW', 'EXTREME');"
        ))
        
        # 3. Yangi ustunlar bilan system_settings jadvalini noldan quramiz
        await conn.execute(text("""
            CREATE TABLE system_settings (
                id SERIAL PRIMARY KEY,
                base_delivery_fee FLOAT NOT NULL DEFAULT 10000.0,
                service_commission_percent FLOAT NOT NULL DEFAULT 10.0,
                weather_condition weathercondition NOT NULL DEFAULT 'CLEAR',
                weather_multiplier FLOAT NOT NULL DEFAULT 1.0,
                auto_weather_pricing BOOLEAN NOT NULL DEFAULT FALSE
            );
        """))
        
        # 4. Boshlang'ich standart sozlamani kiritamiz
        await conn.execute(text("""
            INSERT INTO system_settings 
            (base_delivery_fee, service_commission_percent, weather_condition, weather_multiplier, auto_weather_pricing)
            VALUES (10000.0, 10.0, 'CLEAR', 1.0, FALSE);
        """))
        
    print("PostgreSQL bazasidagi system_settings jadvali muvaffaqiyatli yangilandi!")

if __name__ == "__main__":
    asyncio.run(fix_database())