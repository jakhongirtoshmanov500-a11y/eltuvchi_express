from datetime import date
from typing import Optional
from fastapi import FastAPI, Request, Depends, Form, HTTPException, status, APIRouter
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from database import engine, Base, get_db
import models
from models import (
    User, 
    UserRole, 
    Order, 
    OrderStatus, 
    PartnerProfile, 
    Product,
    SystemSetting, 
    WeatherCondition
)

app = FastAPI(title="Eltuvchi Express API")

# Statik fayllar va shablonlar (Logotip va rasmlar chiqishi uchun)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

@app.on_event("startup")
async def startup_event():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("PostgreSQL jadvallari muvaffaqiyatli yaratildi!")

# Routerlarni teglar (tags) bilan yaratamiz
admin_router = APIRouter(tags=["Admin Dashboard"])
settings_router = APIRouter(prefix="/admin/settings", tags=["Tizim Sozlamalari"])
orders_router = APIRouter(prefix="/admin/orders", tags=["Buyurtmalar Boshqaruvi"])
partners_router = APIRouter(prefix="/admin/partners", tags=["Do'konlar Boshqaruvi"])
products_router = APIRouter(prefix="/admin/products", tags=["Mahsulotlar (Menu) Boshqaruvi"])


# ==================== 1. ADMIN DASHBOARD ====================
@admin_router.get("/admin", response_class=HTMLResponse)
async def admin_dashboard(request: Request, db: AsyncSession = Depends(get_db)):
    today = date.today()

    # Faol kuryerlar
    couriers_query = await db.execute(
        select(User).where(User.role == UserRole.COURIER, User.is_active == True)
    )
    couriers = couriers_query.scalars().all()
    active_couriers = len(couriers)

    # Faol do'konlar
    partners_query = await db.execute(select(PartnerProfile))
    partners = partners_query.scalars().all()
    active_partners = sum(1 for p in partners if p.is_open)

    # Bugungi buyurtmalar soni
    orders_count_query = await db.execute(
        select(func.count(Order.id)).where(func.date(Order.created_at) == today)
    )
    today_orders_count = orders_count_query.scalar() or 0

    # Bugungi tushum (DELIVERED bo'lgan yetkazish to'lovlari yig'indisi)
    revenue_query = await db.execute(
        select(func.sum(Order.delivery_fee))
        .where(func.date(Order.created_at) == today, Order.status == OrderStatus.DELIVERED)
    )
    today_revenue_val = revenue_query.scalar() or 0.0
    today_revenue = f"{today_revenue_val:,.0f}".replace(",", " ")

    # Barcha buyurtmalar
    all_orders_query = await db.execute(
        select(Order).order_by(Order.created_at.desc())
    )
    orders = all_orders_query.scalars().all()

    # Tizim sozlamasi
    setting_query = await db.execute(select(SystemSetting))
    system_setting = setting_query.scalars().first()

    # Barcha mahsulotlar (Do'kon ma'lumoti bilan)
    products_query = await db.execute(
        select(Product).options(selectinload(Product.partner))
    )
    products = products_query.scalars().all()

    return templates.TemplateResponse(
        request=request, 
        name="admin.html",
        context={
            "active_couriers": active_couriers,
            "active_partners": active_partners,
            "today_orders_count": today_orders_count,
            "today_revenue": today_revenue,
            "system_setting": system_setting,
            "orders": orders,
            "couriers": couriers,
            "partners": partners,
            "products": products,
            "weather_conditions": [w.value for w in WeatherCondition],
            "order_statuses": [s.value for s in OrderStatus]
        }
    )


# ==================== 2. TIZIM SOZLAMALARI ====================
@settings_router.post("")
async def update_settings(
    base_fee: float = Form(...),
    weather_condition: str = Form(...),
    weather_multiplier: float = Form(...),
    db: AsyncSession = Depends(get_db)
):
    setting_query = await db.execute(select(SystemSetting))
    setting = setting_query.scalars().first()

    if not setting:
        setting = SystemSetting(
            base_delivery_fee=base_fee,
            weather_condition=WeatherCondition(weather_condition),
            weather_multiplier=weather_multiplier
        )
        db.add(setting)
    else:
        setting.base_delivery_fee = base_fee
        setting.weather_condition = WeatherCondition(weather_condition)
        setting.weather_multiplier = weather_multiplier

    await db.commit()
    return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)


# ==================== 3. BUYURTMALAR BOSHQARUVI ====================
@orders_router.post("/{order_id}/update")
async def update_order_status_and_courier(
    order_id: int,
    status: str = Form(...),
    courier_id: Optional[int] = Form(None),
    db: AsyncSession = Depends(get_db)
):
    order_query = await db.execute(select(Order).where(Order.id == order_id))
    order = order_query.scalars().first()

    if not order:
        raise HTTPException(status_code=404, detail="Buyurtma topilmadi")

    order.status = OrderStatus(status)
    if courier_id:
        order.courier_id = courier_id

    await db.commit()
    return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)


# ==================== 4. DO'KONLAR BOSHQARUVI ====================
@partners_router.post("/create")
async def create_partner(
    brand_name: str = Form(...),
    category: str = Form(...),
    address: str = Form(...),
    db: AsyncSession = Depends(get_db)
):
    new_partner = PartnerProfile(
        brand_name=brand_name,
        category=category,
        address=address,
        is_open=True,
        balance=0.0
    )
    db.add(new_partner)
    await db.commit()
    return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)

@partners_router.post("/{partner_id}/toggle")
async def toggle_partner_status(partner_id: int, db: AsyncSession = Depends(get_db)):
    partner_query = await db.execute(select(PartnerProfile).where(PartnerProfile.id == partner_id))
    partner = partner_query.scalars().first()
    if partner:
        partner.is_open = not partner.is_open
        await db.commit()
    return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)

@partners_router.post("/{partner_id}/delete")
async def delete_partner(partner_id: int, db: AsyncSession = Depends(get_db)):
    partner_query = await db.execute(select(PartnerProfile).where(PartnerProfile.id == partner_id))
    partner = partner_query.scalars().first()
    if partner:
        await db.delete(partner)
        await db.commit()
    return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)


# ==================== 5. MAHSULOTLAR (MENU) BOSHQARUVI ====================
@products_router.post("/create")
async def create_product(
    partner_id: int = Form(...),
    name: str = Form(...),
    price: float = Form(...),
    description: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db)
):
    new_product = Product(
        partner_id=partner_id,
        name=name,
        price=price,
        description=description,
        is_available=True
    )
    db.add(new_product)
    await db.commit()
    return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)

@products_router.post("/{product_id}/toggle")
async def toggle_product(product_id: int, db: AsyncSession = Depends(get_db)):
    prod_query = await db.execute(select(Product).where(Product.id == product_id))
    product = prod_query.scalars().first()
    if product:
        product.is_available = not product.is_available
        await db.commit()
    return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)

@products_router.post("/{product_id}/delete")
async def delete_product(product_id: int, db: AsyncSession = Depends(get_db)):
    prod_query = await db.execute(select(Product).where(Product.id == product_id))
    product = prod_query.scalars().first()
    if product:
        await db.delete(product)
        await db.commit()
    return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)


# Barcha routerlarni ilovaga ulash
app.include_router(admin_router)
app.include_router(settings_router)
app.include_router(orders_router)
app.include_router(partners_router)
app.include_router(products_router)