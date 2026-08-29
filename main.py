from contextlib import asynccontextmanager
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
    WeatherCondition,
    CourierProfile,
)


# ==================== STARTUP / SHUTDOWN ====================
# Eski @app.on_event("startup") o'rniga zamonaviy lifespan yondashuvi
@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("PostgreSQL jadvallari muvaffaqiyatli yaratildi!")
    yield
    # Ilova to'xtaganda bajariladigan tozalash ishlari (hozircha kerak emas)


app = FastAPI(title="Eltuvchi Express API", lifespan=lifespan)

# Statik fayllar va shablonlar (Logotip va rasmlar chiqishi uchun)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Routerlarni teglar (tags) bilan yaratamiz
admin_router = APIRouter(tags=["Admin Dashboard"])
settings_router = APIRouter(prefix="/admin/settings", tags=["Tizim Sozlamalari"])
orders_router = APIRouter(prefix="/admin/orders", tags=["Buyurtmalar Boshqaruvi"])
partners_router = APIRouter(prefix="/admin/partners", tags=["Do'konlar Boshqaruvi"])
products_router = APIRouter(prefix="/admin/products", tags=["Mahsulotlar (Menu) Boshqaruvi"])
couriers_router = APIRouter(prefix="/admin/couriers", tags=["Kuryerlar Boshqaruvi"])


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

    # Kuryerlar boshqaruvi jadvali uchun — faol va nofaol barchasi, profili bilan
    all_couriers_query = await db.execute(
        select(User)
        .where(User.role == UserRole.COURIER)
        .options(selectinload(User.courier_profile))
        .order_by(User.created_at.desc())
    )
    all_couriers = all_couriers_query.scalars().all()

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
            "all_couriers": all_couriers,
            "partners": partners,
            "products": products,
            "weather_conditions": [w.value for w in WeatherCondition],
            "order_statuses": [s.value for s in OrderStatus],
        },
    )


# ==================== 2. TIZIM SOZLAMALARI ====================
@settings_router.post("")
async def update_settings(
    base_fee: float = Form(...),
    weather_condition: str = Form(...),
    weather_multiplier: float = Form(...),
    db: AsyncSession = Depends(get_db),
):
    try:
        weather_enum = WeatherCondition(weather_condition)
    except ValueError:
        raise HTTPException(status_code=400, detail="Noto'g'ri ob-havo qiymati")

    setting_query = await db.execute(select(SystemSetting))
    setting = setting_query.scalars().first()

    if not setting:
        setting = SystemSetting(
            base_delivery_fee=base_fee,
            weather_condition=weather_enum,
            weather_multiplier=weather_multiplier,
        )
        db.add(setting)
    else:
        setting.base_delivery_fee = base_fee
        setting.weather_condition = weather_enum
        setting.weather_multiplier = weather_multiplier

    await db.commit()
    return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)


# ==================== 3. BUYURTMALAR BOSHQARUVI ====================
@orders_router.post("/{order_id}/update")
async def update_order_status_and_courier(
    order_id: int,
    # DIQQAT: parametr nomi "status" emas, "new_status" — chunki "status"
    # nomi FastAPI'ning status moduli bilan to'qnashib, status.HTTP_303_SEE_OTHER
    # chaqirilganda dastur xatolik berardi.
    new_status: str = Form(...),
    courier_id: Optional[int] = Form(None),
    db: AsyncSession = Depends(get_db),
):
    order_query = await db.execute(select(Order).where(Order.id == order_id))
    order = order_query.scalars().first()

    if not order:
        raise HTTPException(status_code=404, detail="Buyurtma topilmadi")

    try:
        order.status = OrderStatus(new_status)
    except ValueError:
        raise HTTPException(status_code=400, detail="Noto'g'ri buyurtma holati")

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
    commission_rate: float = Form(10.0),
    opening_time: str = Form("09:00"),
    closing_time: str = Form("23:00"),
    db: AsyncSession = Depends(get_db),
):
    new_partner = PartnerProfile(
        brand_name=brand_name,
        category=category,
        address=address,
        commission_rate=commission_rate,
        opening_time=opening_time,
        closing_time=closing_time,
        is_open=True,
        balance=0.0,
    )
    db.add(new_partner)
    await db.commit()
    return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)


# YANGI: admin.html'dagi tahrirlash (edit) modali shu route'ga murojaat qiladi,
# lekin bu route avval umuman mavjud emas edi -> tugma bosilganda 404 chiqardi.
@partners_router.post("/{partner_id}/update")
async def update_partner(
    partner_id: int,
    brand_name: str = Form(...),
    category: str = Form(...),
    address: str = Form(...),
    commission_rate: float = Form(...),
    opening_time: str = Form(...),
    closing_time: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    partner_query = await db.execute(select(PartnerProfile).where(PartnerProfile.id == partner_id))
    partner = partner_query.scalars().first()

    if not partner:
        raise HTTPException(status_code=404, detail="Do'kon topilmadi")

    partner.brand_name = brand_name
    partner.category = category
    partner.address = address
    partner.commission_rate = commission_rate
    partner.opening_time = opening_time
    partner.closing_time = closing_time

    await db.commit()
    return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)


@partners_router.post("/{partner_id}/toggle")
async def toggle_partner_status(partner_id: int, db: AsyncSession = Depends(get_db)):
    partner_query = await db.execute(select(PartnerProfile).where(PartnerProfile.id == partner_id))
    partner = partner_query.scalars().first()
    if not partner:
        raise HTTPException(status_code=404, detail="Do'kon topilmadi")

    partner.is_open = not partner.is_open
    await db.commit()
    return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)


@partners_router.post("/{partner_id}/delete")
async def delete_partner(partner_id: int, db: AsyncSession = Depends(get_db)):
    partner_query = await db.execute(select(PartnerProfile).where(PartnerProfile.id == partner_id))
    partner = partner_query.scalars().first()
    if not partner:
        raise HTTPException(status_code=404, detail="Do'kon topilmadi")

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
    db: AsyncSession = Depends(get_db),
):
    # Mahsulot yaratishdan oldin, berilgan partner_id haqiqatan mavjudligini tekshiramiz
    partner_query = await db.execute(select(PartnerProfile).where(PartnerProfile.id == partner_id))
    if not partner_query.scalars().first():
        raise HTTPException(status_code=404, detail="Bunday do'kon topilmadi")

    new_product = Product(
        partner_id=partner_id,
        name=name,
        price=price,
        description=description,
        is_available=True,
    )
    db.add(new_product)
    await db.commit()
    return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)


# YANGI: mahsulotni tahrirlash uchun avval mavjud bo'lmagan route
@products_router.post("/{product_id}/update")
async def update_product(
    product_id: int,
    name: str = Form(...),
    price: float = Form(...),
    description: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
):
    prod_query = await db.execute(select(Product).where(Product.id == product_id))
    product = prod_query.scalars().first()

    if not product:
        raise HTTPException(status_code=404, detail="Mahsulot topilmadi")

    product.name = name
    product.price = price
    product.description = description

    await db.commit()
    return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)


@products_router.post("/{product_id}/toggle")
async def toggle_product(product_id: int, db: AsyncSession = Depends(get_db)):
    prod_query = await db.execute(select(Product).where(Product.id == product_id))
    product = prod_query.scalars().first()
    if not product:
        raise HTTPException(status_code=404, detail="Mahsulot topilmadi")

    product.is_available = not product.is_available
    await db.commit()
    return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)


@products_router.post("/{product_id}/delete")
async def delete_product(product_id: int, db: AsyncSession = Depends(get_db)):
    prod_query = await db.execute(select(Product).where(Product.id == product_id))
    product = prod_query.scalars().first()
    if not product:
        raise HTTPException(status_code=404, detail="Mahsulot topilmadi")

    await db.delete(product)
    await db.commit()
    return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)


# ==================== 6. KURYERLAR BOSHQARUVI ====================
@couriers_router.post("/create")
async def create_courier(
    full_name: str = Form(...),
    phone_number: str = Form(...),
    transport_type: str = Form("walking"),
    db: AsyncSession = Depends(get_db),
):
    # Telefon raqami unique bo'lgani uchun, avval band emasligini tekshiramiz —
    # aks holda IntegrityError chiqib, tushunarsiz 500-xatolik ko'rinardi.
    existing_query = await db.execute(select(User).where(User.phone_number == phone_number))
    if existing_query.scalars().first():
        raise HTTPException(status_code=400, detail="Bu telefon raqami allaqachon ro'yxatdan o'tgan")

    new_user = User(
        full_name=full_name,
        phone_number=phone_number,
        role=UserRole.COURIER,
        is_active=True,
    )
    db.add(new_user)
    await db.flush()  # new_user.id ni olish uchun, commit qilmasdan turib

    new_courier_profile = CourierProfile(
        user_id=new_user.id,
        transport_type=transport_type,
        is_approved=True,  # admin o'zi qo'shgani uchun avtomatik tasdiqlanadi
        is_online=False,
        balance=0.0,
    )
    db.add(new_courier_profile)

    await db.commit()
    return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)


@couriers_router.post("/{user_id}/toggle")
async def toggle_courier(user_id: int, db: AsyncSession = Depends(get_db)):
    user_query = await db.execute(
        select(User).where(User.id == user_id, User.role == UserRole.COURIER)
    )
    courier_user = user_query.scalars().first()
    if not courier_user:
        raise HTTPException(status_code=404, detail="Kuryer topilmadi")

    courier_user.is_active = not courier_user.is_active
    await db.commit()
    return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)


@couriers_router.post("/{user_id}/delete")
async def delete_courier(user_id: int, db: AsyncSession = Depends(get_db)):
    user_query = await db.execute(
        select(User).where(User.id == user_id, User.role == UserRole.COURIER)
    )
    courier_user = user_query.scalars().first()
    if not courier_user:
        raise HTTPException(status_code=404, detail="Kuryer topilmadi")

    # DIQQAT: kuryerda tugallanmagan (yo'lda) buyurtmalari bo'lsa, uni o'chirish
    # o'sha buyurtmalarni "egasiz" qoldiradi. Hozircha oddiy o'chirish qilyapmiz,
    # lekin productionda avval faol buyurtmalari yo'qligini tekshirish tavsiya etiladi.
    await db.delete(courier_user)
    await db.commit()
    return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)


# Barcha routerlarni ilovaga ulash
app.include_router(admin_router)
app.include_router(settings_router)
app.include_router(orders_router)
app.include_router(partners_router)
app.include_router(products_router)
app.include_router(couriers_router)
