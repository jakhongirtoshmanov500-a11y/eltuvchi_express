import json
import os
import secrets
from contextlib import asynccontextmanager
from datetime import date
from typing import List, Optional

from fastapi import FastAPI, Request, Depends, Form, HTTPException, status, APIRouter
from pydantic import BaseModel
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, text, extract
from sqlalchemy.orm import selectinload

from database import engine, Base, get_db, AsyncSessionLocal
from telegram_bot import (
    send_telegram_message,
    contact_request_keyboard,
    normalize_phone,
    set_telegram_webhook,
    validate_telegram_init_data,
)
from models import (
    User,
    UserRole,
    Order,
    OrderStatus,
    OrderItem,
    PartnerProfile,
    Product,
    SystemSetting,
    WeatherCondition,
    CourierProfile,
    City,
    Transaction,
    TransactionType,
)
from auth import (
    hash_password,
    verify_password,
    get_current_admin_user,
    require_owner,
    get_current_partner_user,
    RedirectToLogin,
)

# Buyurtma statuslarining o'zbekcha nomlari
STATUS_LABELS_UZ = {
    "created": "Yaratildi",
    "accepted_by_partner": "Hamkor qabul qildi",
    "preparing": "Tayyorlanmoqda",
    "looking_for_courier": "Kuryer izlanmoqda",
    "on_the_way": "Yo'lda",
    "delivered": "Yetkazildi",
    "cancelled": "Bekor qilindi",
}

# Keyingi bosqich uchun xarita
NEXT_STATUS_MAP = {
    "created": ("accepted_by_partner", "✅ Hamkor qabul qildi"),
    "accepted_by_partner": ("preparing", "🍳 Tayyorlanmoqda"),
    "preparing": ("looking_for_courier", "🔍 Kuryer izlash"),
    "looking_for_courier": ("on_the_way", "🛵 Yo'lda"),
    "on_the_way": ("delivered", "✅ Yetkazildi"),
}


async def seed_default_data():
    """Baza bo'sh bo'lganda boshlang'ich shaharlar va OWNER akkauntini kiritish"""
    async with AsyncSessionLocal() as session:
        cities_result = await session.execute(select(City))
        if not cities_result.scalars().first():
            session.add_all([City(name="Uchquduq"), City(name="Zarafshon")])
            await session.commit()
            print("Shaharlar (Uchquduq, Zarafshon) qo'shildi.")

        owner_result = await session.execute(select(User).where(User.role == UserRole.OWNER))
        if not owner_result.scalars().first():
            owner_phone = os.getenv("OWNER_PHONE")
            owner_password = os.getenv("OWNER_PASSWORD")
            if owner_phone and owner_password:
                owner = User(
                    full_name=os.getenv("OWNER_NAME", "Egasi"),
                    phone_number=owner_phone,
                    role=UserRole.OWNER,
                    password_hash=hash_password(owner_password),
                    is_active=True,
                )
                session.add(owner)
                await session.commit()
                print(f"OWNER akkaunt yaratildi: {owner_phone}")
            else:
                print("DIQQAT: OWNER_PHONE va OWNER_PASSWORD .env faylida topilmadi.")


# ==================== STARTUP / SHUTDOWN ====================
@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    print("PostgreSQL jadvallari tayyor.")
    await seed_default_data()
    yield


app = FastAPI(title="Eltuvchi Express API", lifespan=lifespan)

SESSION_SECRET_KEY = os.getenv("SESSION_SECRET_KEY")
if not SESSION_SECRET_KEY:
    print("DIQQAT: SESSION_SECRET_KEY .env'da yo'q — vaqtinchalik tasodifiy kalit ishlatilyapti.")
    SESSION_SECRET_KEY = secrets.token_hex(32)

app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET_KEY)


@app.exception_handler(RedirectToLogin)
async def redirect_to_login_handler(request: Request, exc: RedirectToLogin):
    return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)


# Statik fayllar va shablonlar
os.makedirs("static/images", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# APIRouter konfiguratsiyalari
admin_router = APIRouter(tags=["Admin Dashboard"])
settings_router = APIRouter(
    prefix="/admin/settings", tags=["Tizim Sozlamalari"], dependencies=[Depends(require_owner)]
)
orders_router = APIRouter(
    prefix="/admin/orders", tags=["Buyurtmalar Boshqaruvi"], dependencies=[Depends(get_current_admin_user)]
)
partners_router = APIRouter(
    prefix="/admin/partners", tags=["Do'konlar Boshqaruvi"], dependencies=[Depends(get_current_admin_user)]
)
products_router = APIRouter(
    prefix="/admin/products", tags=["Mahsulotlar (Menu) Boshqaruvi"], dependencies=[Depends(get_current_admin_user)]
)
couriers_router = APIRouter(
    prefix="/admin/couriers", tags=["Kuryerlar Boshqaruvi"], dependencies=[Depends(get_current_admin_user)]
)
clients_router = APIRouter(
    prefix="/admin/clients", tags=["Mijozlar Boshqaruvi"], dependencies=[Depends(get_current_admin_user)]
)
operators_router = APIRouter(
    prefix="/admin/operators", tags=["Operatorlar Boshqaruvi"], dependencies=[Depends(require_owner)]
)
finance_router = APIRouter(
    prefix="/admin/finance", tags=["Moliyaviy Boshqaruv"], dependencies=[Depends(require_owner)]
)
shop_router = APIRouter(prefix="/api/shop", tags=["Mijoz Mini App"])
partner_router = APIRouter(prefix="/partner", tags=["Hamkor Kabineti"])


# ==================== 0. LOGIN / LOGOUT ====================
@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse(request=request, name="login.html", context={"error": None})


@app.post("/login")
async def login_submit(
    request: Request,
    phone_number: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(User).where(
            User.phone_number == phone_number,
            User.role.in_([UserRole.OWNER, UserRole.ADMIN, UserRole.PARTNER]),
        )
    )
    user = result.scalars().first()

    if not user or not user.is_active or not user.password_hash or not verify_password(password, user.password_hash):
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={"error": "Telefon raqami yoki parol noto'g'ri"},
        )

    request.session["user_id"] = user.id

    if user.role == UserRole.PARTNER:
        return RedirectResponse(url="/partner", status_code=status.HTTP_303_SEE_OTHER)
    return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)


@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)


# ==================== 1. ADMIN DASHBOARD ====================
@admin_router.get("/admin", response_class=HTMLResponse)
async def admin_dashboard(
    request: Request,
    city_id: Optional[int] = None,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    today = date.today()
    is_owner = current_user.role == UserRole.OWNER
    active_city_id = city_id if is_owner else current_user.city_id

    cities_query = await db.execute(select(City).order_by(City.name))
    all_cities = cities_query.scalars().all()

    partners_stmt = select(PartnerProfile).options(selectinload(PartnerProfile.city))
    if active_city_id is not None:
        partners_stmt = partners_stmt.where(PartnerProfile.city_id == active_city_id)
    partners_query = await db.execute(partners_stmt)
    partners = partners_query.scalars().all()
    active_partners = sum(1 for p in partners if p.is_open)

    products_stmt = select(Product).options(selectinload(Product.partner))
    if active_city_id is not None:
        products_stmt = products_stmt.join(PartnerProfile, Product.partner_id == PartnerProfile.id).where(
            PartnerProfile.city_id == active_city_id
        )
    products_query = await db.execute(products_stmt)
    products = products_query.scalars().all()

    couriers_stmt = select(User).where(User.role == UserRole.COURIER, User.is_active == True)
    if active_city_id is not None:
        couriers_stmt = couriers_stmt.where(User.city_id == active_city_id)
    couriers_query = await db.execute(couriers_stmt)
    couriers = couriers_query.scalars().all()
    active_couriers = len(couriers)

    all_couriers_stmt = (
        select(User)
        .where(User.role == UserRole.COURIER)
        .options(selectinload(User.courier_profile), selectinload(User.city))
        .order_by(User.created_at.desc())
    )
    if active_city_id is not None:
        all_couriers_stmt = all_couriers_stmt.where(User.city_id == active_city_id)
    all_couriers_query = await db.execute(all_couriers_stmt)
    all_couriers = all_couriers_query.scalars().all()

    clients_stmt = (
        select(
            User,
            func.count(Order.id).label("order_count"),
            func.coalesce(func.sum(Order.total_price), 0).label("total_spent"),
        )
        .outerjoin(Order, Order.client_id == User.id)
        .where(User.role == UserRole.CLIENT)
    )
    if active_city_id is not None:
        clients_stmt = clients_stmt.where(User.city_id == active_city_id)
    clients_stmt = clients_stmt.group_by(User.id).order_by(User.created_at.desc())
    clients = (await db.execute(clients_stmt)).all()

    operators_query = await db.execute(
        select(User)
        .where(User.role == UserRole.ADMIN)
        .options(selectinload(User.city))
        .order_by(User.created_at.desc())
    )
    operators = operators_query.scalars().all()

    orders_count_stmt = select(func.count(Order.id)).where(func.date(Order.created_at) == today)
    revenue_stmt = select(func.sum(Order.delivery_fee)).where(
        func.date(Order.created_at) == today, Order.status == OrderStatus.DELIVERED
    )
    if active_city_id is not None:
        orders_count_stmt = orders_count_stmt.join(
            PartnerProfile, Order.partner_id == PartnerProfile.id
        ).where(PartnerProfile.city_id == active_city_id)
        revenue_stmt = revenue_stmt.join(
            PartnerProfile, Order.partner_id == PartnerProfile.id
        ).where(PartnerProfile.city_id == active_city_id)

    today_orders_count = (await db.execute(orders_count_stmt)).scalar() or 0
    today_revenue_val = (await db.execute(revenue_stmt)).scalar() or 0.0
    today_revenue = f"{today_revenue_val:,.0f}".replace(",", " ")

    orders_stmt = select(Order).options(selectinload(Order.items)).order_by(Order.created_at.desc())
    if active_city_id is not None:
        orders_stmt = orders_stmt.join(PartnerProfile, Order.partner_id == PartnerProfile.id).where(
            PartnerProfile.city_id == active_city_id
        )
    orders_query = await db.execute(orders_stmt)
    orders = orders_query.scalars().all()

    setting_query = await db.execute(select(SystemSetting))
    system_setting = setting_query.scalars().first()

    if system_setting:
        suggested_delivery_fee = system_setting.base_delivery_fee * system_setting.weather_multiplier
    else:
        suggested_delivery_fee = 10000.0

    products_json = json.dumps(
        [
            {
                "id": p.id,
                "name": p.name,
                "price": p.price,
                "partner_id": p.partner_id,
                "partner_name": p.partner.brand_name if p.partner else "",
            }
            for p in products
            if p.is_available
        ]
    )

    birthday_query = await db.execute(
        select(User).where(
            User.role == UserRole.CLIENT,
            User.birth_date.isnot(None),
            extract("month", User.birth_date) == today.month,
            extract("day", User.birth_date) == today.day,
        )
    )
    birthday_clients_today = birthday_query.scalars().all()
    for _c in birthday_clients_today:
        _c.age = today.year - _c.birth_date.year - (
            (today.month, today.day) < (_c.birth_date.month, _c.birth_date.day)
        )

    recent_transactions = []
    if is_owner:
        tx_query = await db.execute(
            select(Transaction)
            .options(
                selectinload(Transaction.user),
                selectinload(Transaction.partner),
                selectinload(Transaction.created_by),
            )
            .order_by(Transaction.created_at.desc())
            .limit(50)
        )
        recent_transactions = tx_query.scalars().all()

    analytics = None
    if is_owner:
        month_start = today.replace(day=1)
        courier_pct = (system_setting.courier_share_percent if system_setting else 80.0) / 100
        default_commission_pct = (system_setting.service_commission_percent if system_setting else 10.0) / 100

        async def compute_period_stats(period_start):
            stmt = (
                select(Order)
                .options(selectinload(Order.partner))
                .where(Order.status == OrderStatus.DELIVERED, func.date(Order.created_at) >= period_start)
            )
            if active_city_id is not None:
                stmt = stmt.join(PartnerProfile, Order.partner_id == PartnerProfile.id).where(
                    PartnerProfile.city_id == active_city_id
                )
            delivered = (await db.execute(stmt)).scalars().all()

            courier_pay = partner_pay = commission_income = delivery_income = 0.0
            for o in delivered:
                rate = (o.partner.commission_rate / 100) if o.partner else default_commission_pct
                commission = o.total_price * rate
                partner_pay += o.total_price - commission
                commission_income += commission
                c_pay = o.delivery_fee * courier_pct
                courier_pay += c_pay
                delivery_income += o.delivery_fee - c_pay

            return {
                "order_count": len(delivered),
                "courier_pay": courier_pay,
                "partner_pay": partner_pay,
                "commission_income": commission_income,
                "delivery_income": delivery_income,
                "net_profit": commission_income + delivery_income,
            }

        async def compute_loss_stats(period_start):
            stmt = select(
                func.count(Order.id), func.coalesce(func.sum(Order.total_price + Order.delivery_fee), 0)
            ).where(Order.status == OrderStatus.CANCELLED, func.date(Order.created_at) >= period_start)
            if active_city_id is not None:
                stmt = stmt.join(PartnerProfile, Order.partner_id == PartnerProfile.id).where(
                    PartnerProfile.city_id == active_city_id
                )
            count, total = (await db.execute(stmt)).first()
            return {"count": count or 0, "amount": total or 0.0}

        analytics = {
            "today": await compute_period_stats(today),
            "month": await compute_period_stats(month_start),
            "today_loss": await compute_loss_stats(today),
            "month_loss": await compute_loss_stats(month_start),
        }

    return templates.TemplateResponse(
        request=request,
        name="admin.html",
        context={
            "current_user": current_user,
            "is_owner": is_owner,
            "all_cities": all_cities,
            "active_city_id": active_city_id,
            "active_couriers": active_couriers,
            "active_partners": active_partners,
            "today_orders_count": today_orders_count,
            "today_revenue": today_revenue,
            "system_setting": system_setting,
            "orders": orders,
            "couriers": couriers,
            "all_couriers": all_couriers,
            "clients": clients,
            "operators": operators,
            "partners": partners,
            "products": products,
            "products_json": products_json,
            "suggested_delivery_fee": suggested_delivery_fee,
            "weather_conditions": [w.value for w in WeatherCondition],
            "order_statuses": [s.value for s in OrderStatus],
            "status_labels": STATUS_LABELS_UZ,
            "next_status_map": NEXT_STATUS_MAP,
            "recent_transactions": recent_transactions,
            "birthday_clients_today": birthday_clients_today,
            "analytics": analytics,
        },
    )


# ==================== 2. TIZIM SOZLAMALARI ====================
@settings_router.post("")
async def update_settings(
    base_fee: float = Form(...),
    weather_condition: str = Form(...),
    weather_multiplier: float = Form(...),
    service_commission_percent: float = Form(...),
    courier_share_percent: float = Form(...),
    db: AsyncSession = Depends(get_db),
):
    try:
        weather_enum = WeatherCondition(weather_condition)
    except ValueError:
        raise HTTPException(status_code=400, detail="Noto'g'ri ob-havo qiymati")

    if not (0 <= courier_share_percent <= 100):
        raise HTTPException(status_code=400, detail="Kuryer ulushi 0-100 oralig'ida bo'lishi kerak")

    setting_query = await db.execute(select(SystemSetting))
    setting = setting_query.scalars().first()

    if not setting:
        setting = SystemSetting(
            base_delivery_fee=base_fee,
            weather_condition=weather_enum,
            weather_multiplier=weather_multiplier,
            service_commission_percent=service_commission_percent,
            courier_share_percent=courier_share_percent,
        )
        db.add(setting)
    else:
        setting.base_delivery_fee = base_fee
        setting.weather_condition = weather_enum
        setting.weather_multiplier = weather_multiplier
        setting.service_commission_percent = service_commission_percent
        setting.courier_share_percent = courier_share_percent

    await db.commit()
    return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)


async def _get_or_create_setting(db: AsyncSession) -> SystemSetting:
    result = await db.execute(select(SystemSetting))
    setting = result.scalars().first()
    if not setting:
        setting = SystemSetting()
        db.add(setting)
    return setting


@settings_router.post("/birthday")
async def update_birthday_setting(
    birthday_bonus_amount: float = Form(...),
    db: AsyncSession = Depends(get_db),
):
    setting = await _get_or_create_setting(db)
    setting.birthday_bonus_amount = birthday_bonus_amount
    await db.commit()
    return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)


@settings_router.post("/referral")
async def update_referral_setting(
    referral_program_text: str = Form(""),
    db: AsyncSession = Depends(get_db),
):
    setting = await _get_or_create_setting(db)
    setting.referral_program_text = referral_program_text
    await db.commit()
    return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)


@settings_router.post("/cashback")
async def update_cashback_setting(
    bonus_cashback_text: str = Form(""),
    db: AsyncSession = Depends(get_db),
):
    setting = await _get_or_create_setting(db)
    setting.bonus_cashback_text = bonus_cashback_text
    await db.commit()
    return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)


# ==================== 3. BUYURTMALAR BOSHQARUVI ====================
@orders_router.post("/create")
async def create_order(
    partner_id: int = Form(...),
    client_name: str = Form(...),
    client_phone: str = Form(...),
    delivery_address: str = Form(...),
    product_ids: List[int] = Form(...),
    quantities: List[int] = Form(...),
    db: AsyncSession = Depends(get_db),
):
    if len(product_ids) != len(quantities) or len(product_ids) == 0:
        raise HTTPException(status_code=400, detail="Mahsulotlar ro'yxati noto'g'ri")

    partner_for_city_query = await db.execute(select(PartnerProfile).where(PartnerProfile.id == partner_id))
    partner_for_city = partner_for_city_query.scalars().first()
    if not partner_for_city:
        raise HTTPException(status_code=404, detail="Bunday do'kon topilmadi")

    client_query = await db.execute(select(User).where(User.phone_number == client_phone))
    client = client_query.scalars().first()
    if not client:
        client = User(
            full_name=client_name,
            phone_number=client_phone,
            role=UserRole.CLIENT,
            is_active=True,
            city_id=partner_for_city.city_id,
        )
        db.add(client)
        await db.flush()
    elif client.city_id is None:
        client.city_id = partner_for_city.city_id

    total_price = 0.0
    order_items_data = []
    for product_id, qty in zip(product_ids, quantities):
        if qty <= 0:
            continue
        prod_query = await db.execute(
            select(Product).where(Product.id == product_id, Product.partner_id == partner_id)
        )
        product = prod_query.scalars().first()
        if not product:
            raise HTTPException(status_code=400, detail=f"Mahsulot topilmadi (id={product_id})")

        total_price += product.price * qty
        order_items_data.append((product, qty))

    if not order_items_data:
        raise HTTPException(status_code=400, detail="Kamida bitta mahsulot tanlanishi kerak")

    setting_query = await db.execute(select(SystemSetting))
    setting = setting_query.scalars().first()
    delivery_fee = setting.base_delivery_fee * setting.weather_multiplier if setting else 10000.0

    new_order = Order(
        client_id=client.id,
        partner_id=partner_id,
        status=OrderStatus.CREATED,
        total_price=total_price,
        delivery_fee=delivery_fee,
        delivery_address=delivery_address,
    )
    db.add(new_order)
    await db.flush()

    for product, qty in order_items_data:
        db.add(
            OrderItem(
                order_id=new_order.id,
                product_id=product.id,
                product_name=product.name,
                unit_price=product.price,
                quantity=qty,
            )
        )

    await db.commit()
    return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)


@orders_router.post("/{order_id}/update")
async def update_order_status_and_courier(
    order_id: int,
    new_status: str = Form(...),
    courier_id: Optional[int] = Form(None),
    db: AsyncSession = Depends(get_db),
):
    order_query = await db.execute(
        select(Order).options(selectinload(Order.partner)).where(Order.id == order_id)
    )
    order = order_query.scalars().first()

    if not order:
        raise HTTPException(status_code=404, detail="Buyurtma topilmadi")

    old_status = order.status
    old_courier_id = order.courier_id

    try:
        order.status = OrderStatus(new_status)
    except ValueError:
        raise HTTPException(status_code=400, detail="Noto'g'ri buyurtma holati")

    if courier_id:
        order.courier_id = courier_id

    await db.commit()

    try:
        if order.status != old_status:
            client_query = await db.execute(select(User).where(User.id == order.client_id))
            client = client_query.scalars().first()
            if client and client.telegram_id:
                label = STATUS_LABELS_UZ.get(order.status.value, order.status.value)
                await send_telegram_message(
                    client.telegram_id,
                    f"📦 <b>Buyurtma #{order.id}</b> holati yangilandi:\n<b>{label}</b>",
                )

        if courier_id and courier_id != old_courier_id:
            courier_query = await db.execute(select(User).where(User.id == courier_id))
            courier = courier_query.scalars().first()
            if courier and courier.telegram_id:
                partner_name = order.partner.brand_name if order.partner else "—"
                await send_telegram_message(
                    courier.telegram_id,
                    f"🛵 Sizga yangi buyurtma biriktirildi!\n\n"
                    f"<b>Buyurtma:</b> #{order.id}\n"
                    f"<b>Do'kon:</b> {partner_name}\n"
                    f"<b>Manzil:</b> {order.delivery_address}",
                )
    except Exception as e:
        print(f"Bildirishnoma yuborishda xatolik: {e}")

    return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)


# ==================== 4. DO'KONLAR BOSHQARUVI ====================
@partners_router.post("/create")
async def create_partner(
    brand_name: str = Form(...),
    category: str = Form(...),
    address: str = Form(...),
    city_id: int = Form(...),
    commission_rate: float = Form(10.0),
    opening_time: str = Form("09:00"),
    closing_time: str = Form("23:00"),
    login_phone: Optional[str] = Form(None),
    login_password: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
    owner: User = Depends(require_owner),
):
    new_partner = PartnerProfile(
        brand_name=brand_name,
        category=category,
        address=address,
        city_id=city_id,
        commission_rate=commission_rate,
        opening_time=opening_time,
        closing_time=closing_time,
        is_open=True,
        balance=0.0,
    )
    db.add(new_partner)
    await db.flush()

    if login_phone and login_password:
        existing = await db.execute(select(User).where(User.phone_number == login_phone))
        if existing.scalars().first():
            raise HTTPException(status_code=400, detail="Bu telefon raqami allaqachon band")
        partner_user = User(
            full_name=brand_name,
            phone_number=login_phone,
            role=UserRole.PARTNER,
            password_hash=hash_password(login_password),
            is_active=True,
        )
        db.add(partner_user)
        await db.flush()
        new_partner.user_id = partner_user.id

    await db.commit()
    return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)


@partners_router.post("/{partner_id}/update")
async def update_partner(
    partner_id: int,
    brand_name: str = Form(...),
    category: str = Form(...),
    address: str = Form(...),
    city_id: int = Form(...),
    commission_rate: float = Form(...),
    opening_time: str = Form(...),
    closing_time: str = Form(...),
    db: AsyncSession = Depends(get_db),
    owner: User = Depends(require_owner),
):
    partner_query = await db.execute(select(PartnerProfile).where(PartnerProfile.id == partner_id))
    partner = partner_query.scalars().first()

    if not partner:
        raise HTTPException(status_code=404, detail="Do'kon topilmadi")

    partner.brand_name = brand_name
    partner.category = category
    partner.address = address
    partner.city_id = city_id
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


@partners_router.post("/{partner_id}/set-login")
async def set_partner_login(
    partner_id: int,
    login_phone: str = Form(...),
    login_password: str = Form(...),
    db: AsyncSession = Depends(get_db),
    owner: User = Depends(require_owner),
):
    partner_query = await db.execute(
        select(PartnerProfile).options(selectinload(PartnerProfile.user)).where(PartnerProfile.id == partner_id)
    )
    partner = partner_query.scalars().first()
    if not partner:
        raise HTTPException(status_code=404, detail="Do'kon topilmadi")

    if partner.user_id:
        partner.user.phone_number = login_phone
        partner.user.password_hash = hash_password(login_password)
        partner.user.is_active = True
    else:
        existing = await db.execute(select(User).where(User.phone_number == login_phone))
        if existing.scalars().first():
            raise HTTPException(status_code=400, detail="Bu telefon raqami allaqachon band")
        partner_user = User(
            full_name=partner.brand_name,
            phone_number=login_phone,
            role=UserRole.PARTNER,
            password_hash=hash_password(login_password),
            is_active=True,
        )
        db.add(partner_user)
        await db.flush()
        partner.user_id = partner_user.id

    await db.commit()
    return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)


@partners_router.post("/{partner_id}/delete")
async def delete_partner(
    partner_id: int,
    db: AsyncSession = Depends(get_db),
    owner: User = Depends(require_owner),
):
    partner_query = await db.execute(select(PartnerProfile).where(PartnerProfile.id == partner_id))
    partner = partner_query.scalars().first()
    if not partner:
        raise HTTPException(status_code=404, detail="Do'kon topilmadi")

    await db.delete(partner)
    await db.commit()
    return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)


# ==================== 5. MAHSULOTLAR BOSHQARUVI ====================
@products_router.post("/create")
async def create_product(
    partner_id: int = Form(...),
    name: str = Form(...),
    price: float = Form(...),
    description: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
    owner: User = Depends(require_owner),
):
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


@products_router.post("/{product_id}/update")
async def update_product(
    product_id: int,
    name: str = Form(...),
    price: float = Form(...),
    description: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
    owner: User = Depends(require_owner),
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
async def delete_product(product_id: int, db: AsyncSession = Depends(get_db), owner: User = Depends(require_owner)):
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
    city_id: Optional[int] = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    existing_query = await db.execute(select(User).where(User.phone_number == phone_number))
    if existing_query.scalars().first():
        raise HTTPException(status_code=400, detail="Bu telefon raqami allaqachon ro'yxatdan o'tgan")

    resolved_city_id = city_id if current_user.role == UserRole.OWNER else current_user.city_id

    new_user = User(
        full_name=full_name,
        phone_number=phone_number,
        role=UserRole.COURIER,
        city_id=resolved_city_id,
        is_active=True,
    )
    db.add(new_user)
    await db.flush()

    new_courier_profile = CourierProfile(
        user_id=new_user.id,
        transport_type=transport_type,
        is_approved=True,
        is_online=False,
        balance=0.0,
    )
    db.add(new_courier_profile)

    await db.commit()
    return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)


@couriers_router.post("/{user_id}/update")
async def update_courier(
    user_id: int,
    full_name: str = Form(...),
    phone_number: str = Form(...),
    transport_type: str = Form(...),
    city_id: Optional[int] = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    user_query = await db.execute(
        select(User)
        .where(User.id == user_id, User.role == UserRole.COURIER)
        .options(selectinload(User.courier_profile))
    )
    courier_user = user_query.scalars().first()
    if not courier_user:
        raise HTTPException(status_code=404, detail="Kuryer topilmadi")

    if phone_number != courier_user.phone_number:
        existing_query = await db.execute(
            select(User).where(User.phone_number == phone_number, User.id != user_id)
        )
        if existing_query.scalars().first():
            raise HTTPException(status_code=400, detail="Bu telefon raqami boshqa foydalanuvchiga tegishli")

    courier_user.full_name = full_name
    courier_user.phone_number = phone_number
    if courier_user.courier_profile:
        courier_user.courier_profile.transport_type = transport_type

    if current_user.role == UserRole.OWNER and city_id is not None:
        courier_user.city_id = city_id

    await db.commit()
    return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)


@couriers_router.post("/{user_id}/toggle")
async def toggle_courier(user_id: int, db: AsyncSession = Depends(get_db)):
    user_query = await db.execute(select(User).where(User.id == user_id, User.role == UserRole.COURIER))
    courier_user = user_query.scalars().first()
    if not courier_user:
        raise HTTPException(status_code=404, detail="Kuryer topilmadi")

    courier_user.is_active = not courier_user.is_active
    await db.commit()
    return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)


@couriers_router.post("/{user_id}/delete")
async def delete_courier(user_id: int, db: AsyncSession = Depends(get_db)):
    user_query = await db.execute(select(User).where(User.id == user_id, User.role == UserRole.COURIER))
    courier_user = user_query.scalars().first()
    if not courier_user:
        raise HTTPException(status_code=404, detail="Kuryer topilmadi")

    await db.delete(courier_user)
    await db.commit()
    return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)


# ==================== 7. MIJOZLAR BOSHQARUVI ====================
@clients_router.post("/{user_id}/toggle")
async def toggle_client(user_id: int, db: AsyncSession = Depends(get_db)):
    user_query = await db.execute(select(User).where(User.id == user_id, User.role == UserRole.CLIENT))
    client_user = user_query.scalars().first()
    if not client_user:
        raise HTTPException(status_code=404, detail="Mijoz topilmadi")

    client_user.is_active = not client_user.is_active
    await db.commit()
    return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)


@clients_router.post("/{user_id}/birthday-bonus")
async def mark_birthday_bonus_given(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    owner: User = Depends(require_owner),
):
    client_query = await db.execute(select(User).where(User.id == user_id, User.role == UserRole.CLIENT))
    client = client_query.scalars().first()
    if not client:
        raise HTTPException(status_code=404, detail="Mijoz topilmadi")

    setting = await _get_or_create_setting(db)

    db.add(Transaction(
        user_id=client.id,
        type=TransactionType.DEPOSIT,
        amount=setting.birthday_bonus_amount,
        note=f"Tug'ilgan kun bonusi — {client.full_name}",
        created_by_id=owner.id,
    ))
    await db.commit()
    return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)


# ==================== 8. OPERATORLAR BOSHQARUVI ====================
@operators_router.post("/create")
async def create_operator(
    full_name: str = Form(...),
    phone_number: str = Form(...),
    password: str = Form(...),
    city_id: int = Form(...),
    db: AsyncSession = Depends(get_db),
):
    existing = await db.execute(select(User).where(User.phone_number == phone_number))
    if existing.scalars().first():
        raise HTTPException(status_code=400, detail="Bu telefon raqami allaqachon band")

    new_operator = User(
        full_name=full_name,
        phone_number=phone_number,
        role=UserRole.ADMIN,
        city_id=city_id,
        password_hash=hash_password(password),
        is_active=True,
    )
    db.add(new_operator)
    await db.commit()
    return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)


@operators_router.post("/{user_id}/toggle")
async def toggle_operator(user_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.id == user_id, User.role == UserRole.ADMIN))
    operator = result.scalars().first()
    if not operator:
        raise HTTPException(status_code=404, detail="Operator topilmadi")

    operator.is_active = not operator.is_active
    await db.commit()
    return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)


@operators_router.post("/{user_id}/delete")
async def delete_operator(user_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.id == user_id, User.role == UserRole.ADMIN))
    operator = result.scalars().first()
    if not operator:
        raise HTTPException(status_code=404, detail="Operator topilmadi")

    await db.delete(operator)
    await db.commit()
    return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)


# ==================== 9. MOLIYAVIY BOSHQARUV ====================
@finance_router.post("/courier")
async def update_courier_balance(
    user_id: int = Form(...),
    action: str = Form(...),
    amount: float = Form(...),
    note: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Summa musbat bo'lishi kerak")

    result = await db.execute(
        select(User)
        .where(User.id == user_id, User.role == UserRole.COURIER)
        .options(selectinload(User.courier_profile))
    )
    courier = result.scalars().first()
    if not courier or not courier.courier_profile:
        raise HTTPException(status_code=404, detail="Kuryer topilmadi")

    if action == "deposit":
        courier.courier_profile.balance += amount
        tx_type = TransactionType.DEPOSIT
    elif action == "withdraw":
        courier.courier_profile.balance -= amount
        tx_type = TransactionType.WITHDRAWAL
    else:
        raise HTTPException(status_code=400, detail="Noto'g'ri amal turi")

    db.add(Transaction(
        user_id=courier.id,
        type=tx_type,
        amount=amount,
        note=note,
        created_by_id=current_user.id,
    ))
    await db.commit()
    return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)


@finance_router.post("/partner")
async def update_partner_balance(
    partner_id: int = Form(...),
    action: str = Form(...),
    amount: float = Form(...),
    note: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Summa musbat bo'lishi kerak")

    result = await db.execute(select(PartnerProfile).where(PartnerProfile.id == partner_id))
    partner = result.scalars().first()
    if not partner:
        raise HTTPException(status_code=404, detail="Do'kon topilmadi")

    if action == "deposit":
        partner.balance += amount
        tx_type = TransactionType.DEPOSIT
    elif action == "withdraw":
        partner.balance -= amount
        tx_type = TransactionType.WITHDRAWAL
    else:
        raise HTTPException(status_code=400, detail="Noto'g'ri amal turi")

    db.add(Transaction(
        partner_id=partner.id,
        type=tx_type,
        amount=amount,
        note=note,
        created_by_id=current_user.id,
    ))
    await db.commit()
    return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)


# ==================== 10. RESET ====================
@app.post("/admin/reset")
async def reset_system(
    confirmation: str = Form(...),
    db: AsyncSession = Depends(get_db),
    owner: User = Depends(require_owner),
):
    if confirmation != "TOZALASH":
        raise HTTPException(
            status_code=400,
            detail="Tasdiqlash matni noto'g'ri. Aniq katta harflarda 'TOZALASH' deb yozing.",
        )

    await db.execute(text("DELETE FROM order_items"))
    await db.execute(text("DELETE FROM orders"))
    await db.execute(text("DELETE FROM transactions"))
    await db.execute(text("DELETE FROM products"))
    await db.execute(text("DELETE FROM partner_profiles"))
    await db.execute(text("DELETE FROM courier_profiles"))
    await db.execute(text("DELETE FROM users WHERE role IN ('client', 'courier')"))
    await db.commit()

    return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)


# ==================== 11. TELEGRAM BOT ====================
@app.post("/telegram/webhook")
async def telegram_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    update = await request.json()
    message = update.get("message")
    if not message:
        return {"ok": True}

    chat_id = message["chat"]["id"]
    text_val = message.get("text", "")
    contact = message.get("contact")

    if text_val == "/start":
        await send_telegram_message(
            chat_id,
            "Assalomu alaykum! 👋 <b>Eltuvchi Express</b> botiga xush kelibsiz.\n\n"
            "Tizimga ulanish uchun quyidagi tugma orqali telefon raqamingizni yuboring:",
            reply_markup=contact_request_keyboard(),
        )
        return {"ok": True}

    if contact:
        phone = normalize_phone(contact.get("phone_number", ""))
        result = await db.execute(select(User).where(User.phone_number == phone))
        user = result.scalars().first()

        shop_url = str(request.base_url).rstrip("/") + "/shop"
        menu_keyboard = {
            "inline_keyboard": [[{"text": "🛍 Menyuni ochish", "web_app": {"url": shop_url}}]]
        }

        if user:
            user.telegram_id = str(chat_id)
            await db.commit()
            role_names = {
                UserRole.CLIENT: "mijoz",
                UserRole.COURIER: "kuryer",
                UserRole.PARTNER: "hamkor",
            }
            role_text = role_names.get(user.role, "foydalanuvchi")
            await send_telegram_message(
                chat_id,
                f"✅ Muvaffaqiyatli ulandingiz, <b>{user.full_name}</b>!\n"
                f"Siz tizimda <b>{role_text}</b> sifatida ro'yxatdan o'tgansiz.",
                reply_markup=menu_keyboard if user.role == UserRole.CLIENT else None,
            )
        else:
            new_user = User(
                full_name=contact.get("first_name") or "Mijoz",
                phone_number=phone,
                role=UserRole.CLIENT,
                telegram_id=str(chat_id),
            )
            db.add(new_user)
            await db.commit()
            await send_telegram_message(
                chat_id,
                "✅ Ro'yxatdan muvaffaqiyatli o'tdingiz!\n"
                "Endi quyidagi tugma orqali menyuni ochib, buyurtma berishingiz mumkin:",
                reply_markup=menu_keyboard,
            )
        return {"ok": True}

    return {"ok": True}


@app.get("/telegram/set-webhook")
async def telegram_set_webhook(request: Request, owner: User = Depends(require_owner)):
    webhook_url = str(request.base_url).rstrip("/") + "/telegram/webhook"
    result = await set_telegram_webhook(webhook_url)
    return {"webhook_url": webhook_url, "telegram_response": result}


# ==================== 12. MIJOZ MINI APP ENDPOINTS ====================
def _get_telegram_user_or_403(init_data: str) -> dict:
    tg_user = validate_telegram_init_data(init_data)
    if not tg_user:
        raise HTTPException(status_code=403, detail="Telegram tasdiqlanmadi.")
    return tg_user


class InitDataBody(BaseModel):
    init_data: str


class SetCityBody(BaseModel):
    init_data: str
    city_id: int


class OrderItemBody(BaseModel):
    product_id: int
    quantity: int


class ShopOrderBody(BaseModel):
    init_data: str
    partner_id: int
    delivery_address: str
    items: List[OrderItemBody]


class ProfileUpdateBody(BaseModel):
    init_data: str
    first_name: Optional[str] = None
    birth_date: Optional[str] = None


@app.get("/shop", response_class=HTMLResponse)
async def shop_page(request: Request):
    return templates.TemplateResponse(request=request, name="shop.html", context={})


@shop_router.post("/me")
async def shop_me(body: InitDataBody, db: AsyncSession = Depends(get_db)):
    tg_user = _get_telegram_user_or_403(body.init_data)
    telegram_id = str(tg_user["id"])

    result = await db.execute(
        select(User).where(User.telegram_id == telegram_id, User.role == UserRole.CLIENT)
    )
    client = result.scalars().first()

    if not client:
        return {"registered": False}

    cities_result = await db.execute(select(City).order_by(City.name))
    cities = [{"id": c.id, "name": c.name} for c in cities_result.scalars().all()]

    return {
        "registered": True,
        "full_name": client.full_name,
        "first_name": client.full_name,
        "phone": client.phone_number,
        "birth_date": client.birth_date.strftime("%Y-%m-%d") if client.birth_date else "",
        "city_id": client.city_id,
        "cities": cities,
        "cashback_balance": 0.0,
        "referral_code": str(client.id),
    }


@shop_router.post("/profile/update")
async def shop_profile_update(body: ProfileUpdateBody, db: AsyncSession = Depends(get_db)):
    tg_user = _get_telegram_user_or_403(body.init_data)
    telegram_id = str(tg_user["id"])

    result = await db.execute(
        select(User).where(User.telegram_id == telegram_id, User.role == UserRole.CLIENT)
    )
    client = result.scalars().first()
    if not client:
        raise HTTPException(status_code=404, detail="Mijoz topilmadi")

    if body.first_name:
        client.full_name = body.first_name
    if body.birth_date:
        try:
            client.birth_date = date.fromisoformat(body.birth_date)
        except ValueError:
            pass

    await db.commit()
    return {"ok": True, "message": "Ma'lumotlar muvaffaqiyatli saqlandi!"}


@shop_router.get("/orders")
async def shop_user_orders(init_data: str, db: AsyncSession = Depends(get_db)):
    tg_user = _get_telegram_user_or_403(init_data)
    telegram_id = str(tg_user["id"])

    client_result = await db.execute(
        select(User).where(User.telegram_id == telegram_id, User.role == UserRole.CLIENT)
    )
    client = client_result.scalars().first()
    if not client:
        return []

    orders_result = await db.execute(
        select(Order)
        .options(selectinload(Order.partner), selectinload(Order.courier))
        .where(Order.client_id == client.id)
        .order_by(Order.created_at.desc())
        .limit(20)
    )
    orders = orders_result.scalars().all()

    return [
        {
            "id": o.id,
            "status": o.status.value,
            "total_amount": o.total_price + o.delivery_fee,
            "partner_name": o.partner.brand_name if o.partner else "Noma'lum do'kon",
            "courier_name": o.courier.full_name if o.courier else None,
            "created_at": o.created_at.isoformat() if o.created_at else "",
        }
        for o in orders
    ]


@shop_router.post("/set-city")
async def shop_set_city(body: SetCityBody, db: AsyncSession = Depends(get_db)):
    tg_user = _get_telegram_user_or_403(body.init_data)
    telegram_id = str(tg_user["id"])

    result = await db.execute(
        select(User).where(User.telegram_id == telegram_id, User.role == UserRole.CLIENT)
    )
    client = result.scalars().first()
    if not client:
        raise HTTPException(status_code=404, detail="Mijoz topilmadi")

    client.city_id = body.city_id
    await db.commit()
    return {"ok": True}


@shop_router.get("/partners")
async def shop_partners(city_id: int, init_data: Optional[str] = None, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(PartnerProfile).where(PartnerProfile.city_id == city_id, PartnerProfile.is_open == True)
    )
    partners = result.scalars().all()
    return [
        {"id": p.id, "name": p.brand_name, "category": p.category, "address": p.address, "is_open": p.is_open}
        for p in partners
    ]


@shop_router.get("/products")
async def shop_products(partner_id: int, init_data: Optional[str] = None, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Product).where(Product.partner_id == partner_id, Product.is_available == True)
    )
    products = result.scalars().all()
    return [
        {"id": p.id, "name": p.name, "price": p.price, "description": p.description, "category": "Menyu"}
        for p in products
    ]


@shop_router.post("/order")
async def shop_create_order(body: ShopOrderBody, db: AsyncSession = Depends(get_db)):
    tg_user = _get_telegram_user_or_403(body.init_data)
    telegram_id = str(tg_user["id"])

    client_result = await db.execute(
        select(User).where(User.telegram_id == telegram_id, User.role == UserRole.CLIENT)
    )
    client = client_result.scalars().first()
    if not client:
        raise HTTPException(status_code=404, detail="Mijoz topilmadi — avval botga /start bosing")

    if not body.items:
        raise HTTPException(status_code=400, detail="Savat bo'sh")

    partner_result = await db.execute(select(PartnerProfile).where(PartnerProfile.id == body.partner_id))
    partner = partner_result.scalars().first()
    if not partner:
        raise HTTPException(status_code=404, detail="Do'kon topilmadi")

    total_price = 0.0
    order_items_data = []
    for item in body.items:
        if item.quantity <= 0:
            continue
        prod_result = await db.execute(
            select(Product).where(Product.id == item.product_id, Product.partner_id == body.partner_id)
        )
        product = prod_result.scalars().first()
        if not product:
            raise HTTPException(status_code=400, detail=f"Mahsulot topilmadi (id={item.product_id})")
        total_price += product.price * item.quantity
        order_items_data.append((product, item.quantity))

    if not order_items_data:
        raise HTTPException(status_code=400, detail="Kamida bitta mahsulot tanlanishi kerak")

    setting_result = await db.execute(select(SystemSetting))
    setting = setting_result.scalars().first()
    delivery_fee = (setting.base_delivery_fee * setting.weather_multiplier) if setting else 10000.0

    new_order = Order(
        client_id=client.id,
        partner_id=body.partner_id,
        status=OrderStatus.CREATED,
        total_price=total_price,
        delivery_fee=delivery_fee,
        delivery_address=body.delivery_address,
    )
    db.add(new_order)
    await db.flush()

    for product, qty in order_items_data:
        db.add(OrderItem(
            order_id=new_order.id,
            product_id=product.id,
            product_name=product.name,
            unit_price=product.price,
            quantity=qty,
        ))

    await db.commit()

    try:
        await send_telegram_message(
            telegram_id,
            f"✅ Buyurtmangiz qabul qilindi!\n\n"
            f"<b>Buyurtma:</b> #{new_order.id}\n"
            f"<b>Do'kon:</b> {partner.brand_name}\n"
            f"<b>Jami:</b> {total_price:,.0f} so'm + yetkazish {delivery_fee:,.0f} so'm",
        )
    except Exception as e:
        print(f"Xabar yuborishda xatolik: {e}")

    return {"ok": True, "order_id": new_order.id}


# ==================== 13. HAMKOR KABINETI ====================
async def _get_own_partner(db: AsyncSession, current_user: User) -> PartnerProfile:
    result = await db.execute(select(PartnerProfile).where(PartnerProfile.user_id == current_user.id))
    partner = result.scalars().first()
    if not partner:
        raise HTTPException(status_code=404, detail="Sizga bog'langan do'kon topilmadi.")
    return partner


@partner_router.get("", response_class=HTMLResponse)
async def partner_dashboard(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_partner_user),
):
    partner = await _get_own_partner(db, current_user)

    products_result = await db.execute(
        select(Product).where(Product.partner_id == partner.id).order_by(Product.id.desc())
    )
    products = products_result.scalars().all()

    orders_result = await db.execute(
        select(Order)
        .options(selectinload(Order.items))
        .where(Order.partner_id == partner.id)
        .order_by(Order.created_at.desc())
        .limit(100)
    )
    orders = orders_result.scalars().all()

    return templates.TemplateResponse(
        request=request,
        name="partner.html",
        context={
            "partner": partner,
            "products": products,
            "orders": orders,
            "status_labels": STATUS_LABELS_UZ,
            "current_user": current_user,
        },
    )


@partner_router.post("/products/create")
async def partner_create_product(
    name: str = Form(...),
    price: float = Form(...),
    description: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_partner_user),
):
    partner = await _get_own_partner(db, current_user)
    db.add(Product(partner_id=partner.id, name=name, price=price, description=description, is_available=True))
    await db.commit()
    return RedirectResponse(url="/partner", status_code=status.HTTP_303_SEE_OTHER)


@partner_router.post("/products/{product_id}/update")
async def partner_update_product(
    product_id: int,
    name: str = Form(...),
    price: float = Form(...),
    description: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_partner_user),
):
    partner = await _get_own_partner(db, current_user)
    result = await db.execute(select(Product).where(Product.id == product_id, Product.partner_id == partner.id))
    product = result.scalars().first()
    if not product:
        raise HTTPException(status_code=404, detail="Mahsulot topilmadi")
    product.name = name
    product.price = price
    product.description = description
    await db.commit()
    return RedirectResponse(url="/partner", status_code=status.HTTP_303_SEE_OTHER)


@partner_router.post("/products/{product_id}/toggle")
async def partner_toggle_product(
    product_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_partner_user),
):
    partner = await _get_own_partner(db, current_user)
    result = await db.execute(select(Product).where(Product.id == product_id, Product.partner_id == partner.id))
    product = result.scalars().first()
    if not product:
        raise HTTPException(status_code=404, detail="Mahsulot topilmadi")
    product.is_available = not product.is_available
    await db.commit()
    return RedirectResponse(url="/partner", status_code=status.HTTP_303_SEE_OTHER)


@partner_router.post("/products/{product_id}/delete")
async def partner_delete_product(
    product_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_partner_user),
):
    partner = await _get_own_partner(db, current_user)
    result = await db.execute(select(Product).where(Product.id == product_id, Product.partner_id == partner.id))
    product = result.scalars().first()
    if not product:
        raise HTTPException(status_code=404, detail="Mahsulot topilmadi")
    await db.delete(product)
    await db.commit()
    return RedirectResponse(url="/partner", status_code=status.HTTP_303_SEE_OTHER)


@partner_router.post("/status")
async def partner_toggle_open(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_partner_user),
):
    partner = await _get_own_partner(db, current_user)
    partner.is_open = not partner.is_open
    await db.commit()
    return RedirectResponse(url="/partner", status_code=status.HTTP_303_SEE_OTHER)


@partner_router.post("/orders/{order_id}/status")
async def partner_update_order_status(
    order_id: int,
    new_status: str = Form(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_partner_user),
):
    partner = await _get_own_partner(db, current_user)
    result = await db.execute(select(Order).where(Order.id == order_id, Order.partner_id == partner.id))
    order = result.scalars().first()
    if not order:
        raise HTTPException(status_code=404, detail="Buyurtma topilmadi")

    allowed_statuses = {"accepted_by_partner", "preparing", "looking_for_courier", "cancelled"}
    if new_status not in allowed_statuses:
        raise HTTPException(status_code=403, detail="Bu holatga o'zgartirishga ruxsatingiz yo'q")

    old_status = order.status
    try:
        order.status = OrderStatus(new_status)
    except ValueError:
        raise HTTPException(status_code=400, detail="Noto'g'ri holat")
    await db.commit()

    try:
        if order.status != old_status:
            client_result = await db.execute(select(User).where(User.id == order.client_id))
            client = client_result.scalars().first()
            if client and client.telegram_id:
                label = STATUS_LABELS_UZ.get(order.status.value, order.status.value)
                await send_telegram_message(client.telegram_id, f"📦 Buyurtma #{order.id} holati yangilandi:\n<b>{label}</b>")
    except Exception as e:
        print(f"Bildirishnoma yuborishda xatolik: {e}")

    return RedirectResponse(url="/partner", status_code=status.HTTP_303_SEE_OTHER)


# Barcha routerlarni oxirida ulash
app.include_router(admin_router)
app.include_router(settings_router)
app.include_router(orders_router)
app.include_router(partners_router)
app.include_router(products_router)
app.include_router(couriers_router)
app.include_router(clients_router)
app.include_router(operators_router)
app.include_router(finance_router)
app.include_router(partner_router)
app.include_router(shop_router)