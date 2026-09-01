import enum
from sqlalchemy import Column, Integer, String, Float, Boolean, ForeignKey, DateTime, Date, Enum, Text
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base

class UserRole(enum.Enum):
    OWNER = "owner"
    ADMIN = "admin"
    PARTNER = "partner"
    COURIER = "courier"
    CLIENT = "client"

class OrderStatus(enum.Enum):
    CREATED = "created"
    ACCEPTED_BY_PARTNER = "accepted_by_partner"
    PREPARING = "preparing"
    LOOKING_FOR_COURIER = "looking_for_courier"
    ON_THE_WAY = "on_the_way"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"

class WeatherCondition(enum.Enum):
    CLEAR = "clear"
    HOT = "hot"
    COLD = "cold"
    RAIN = "rain"
    SNOW = "snow"
    WINDY = "windy"

class City(Base):
    __tablename__ = "cities"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, unique=True)  # masalan: "Uchquduq", "Zarafshon"
    is_active = Column(Boolean, default=True)

    partners = relationship("PartnerProfile", back_populates="city")
    operators = relationship("User", back_populates="city")

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(String, unique=True, index=True, nullable=True)
    full_name = Column(String, nullable=False)
    phone_number = Column(String, unique=True, nullable=False)
    role = Column(Enum(UserRole), default=UserRole.CLIENT)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Faqat OWNER/ADMIN (operator) rollari uchun ishlatiladi — mijoz/kuryer/hamkorda bo'sh qoladi
    password_hash = Column(String, nullable=True)

    # Operator (ADMIN) uchun: qaysi shaharga biriktirilgan. OWNER uchun NULL — cheklovsiz.
    city_id = Column(Integer, ForeignKey("cities.id"), nullable=True)
    city = relationship("City", back_populates="operators")

    # Faqat mijoz (CLIENT) uchun ishlatiladi — tug'ilgan kun bonusi tizimi uchun.
    # Mijoz o'z kabinetida (keyingi bosqichda) kiritadi, hozircha bo'sh qoladi.
    birth_date = Column(Date, nullable=True)

    # cascade="all, delete-orphan": kuryer/hamkor User o'chirilganda,
    # unga bog'liq profil ham avtomatik o'chadi (aks holda FK xatolik beradi)
    courier_profile = relationship("CourierProfile", back_populates="user", uselist=False, cascade="all, delete-orphan")
    partner_profile = relationship("PartnerProfile", back_populates="user", uselist=False, cascade="all, delete-orphan")

class CourierProfile(Base):
    __tablename__ = "courier_profiles"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    passport_data = Column(String, nullable=True)
    transport_type = Column(String, default="walking")
    is_approved = Column(Boolean, default=False)
    is_online = Column(Boolean, default=False)
    balance = Column(Float, default=0.0)

    user = relationship("User", back_populates="courier_profile")

class PartnerProfile(Base):
    __tablename__ = "partner_profiles"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    city_id = Column(Integer, ForeignKey("cities.id"), nullable=True)
    brand_name = Column(String, nullable=False)
    category = Column(String, nullable=False)
    address = Column(String, nullable=False)
    is_open = Column(Boolean, default=True)
    balance = Column(Float, default=0.0)

    commission_rate = Column(Float, default=10.0)
    opening_time = Column(String, default="09:00")
    closing_time = Column(String, default="23:00")

    user = relationship("User", back_populates="partner_profile")
    city = relationship("City", back_populates="partners")
    products = relationship("Product", back_populates="partner", cascade="all, delete-orphan")
    
    # QO'SHILDI: Hamkor buyurtmalari ro'yxatiga bog'lanish
    orders = relationship("Order", back_populates="partner")

class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    partner_id = Column(Integer, ForeignKey("partner_profiles.id"))
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    price = Column(Float, nullable=False)
    is_available = Column(Boolean, default=True)

    partner = relationship("PartnerProfile", back_populates="products")

class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("users.id"))
    partner_id = Column(Integer, ForeignKey("partner_profiles.id"), nullable=True)
    courier_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    status = Column(Enum(OrderStatus), default=OrderStatus.CREATED)
    total_price = Column(Float, nullable=False)
    delivery_fee = Column(Float, nullable=False)
    delivery_address = Column(String, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow)

    # QO'SHILDI: main.py dagi compute_period_stats va boshqa statistikalar uchun zarur bog'lanishlar
    client = relationship("User", foreign_keys=[client_id])
    courier = relationship("User", foreign_keys=[courier_id])
    partner = relationship("PartnerProfile", back_populates="orders")

    # Buyurtma tarkibidagi mahsulotlar (nechta lavash, nechta kola va h.k.)
    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")


class OrderItem(Base):
    __tablename__ = "order_items"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    # product_id nullable=True: agar mahsulot keyinchalik o'chirilsa ham,
    # buyurtma tarixi (order_item) saqlanib qoladi — faqat bog'lanish uziladi
    product_id = Column(Integer, ForeignKey("products.id"), nullable=True)

    # DIQQAT: nom va narx shu yerda "suratga olinadi" (snapshot).
    # Sabab: agar ertaga admin mahsulot narxini o'zgartirsa yoki nomini
    # tahrirlasa, ESKI buyurtmalar o'sha vaqtdagi haqiqiy narx/nomni
    # ko'rsatishi kerak — hozirgi narxni emas. Aks holda hisobotlar
    # (masalan, "shu oy qancha sotildi") noto'g'ri chiqib qoladi.
    product_name = Column(String, nullable=False)
    unit_price = Column(Float, nullable=False)
    quantity = Column(Integer, nullable=False, default=1)

    order = relationship("Order", back_populates="items")
    product = relationship("Product")

class SystemSetting(Base):
    __tablename__ = "system_settings"

    id = Column(Integer, primary_key=True, index=True)
    base_delivery_fee = Column(Float, default=10000.0)
    service_commission_percent = Column(Float, default=10.0)
    weather_condition = Column(Enum(WeatherCondition), default=WeatherCondition.CLEAR)
    weather_multiplier = Column(Float, default=1.0)
    auto_weather_pricing = Column(Boolean, default=True)

    # Yetkazish narxining necha foizi kuryerga tegishli ekani (qolgani egasiga qoladi).
    # Masalan 80.0 = yetkazish narxining 80%i kuryerga, 20%i egasiga.
    courier_share_percent = Column(Float, default=80.0)

    # Tug'ilgan kun bonusi, referal va cashback dasturlari — bularning
    # barchasini faqat OWNER qo'lda kiritadi/o'zgartiradi.
    birthday_bonus_amount = Column(Float, default=0.0)
    referral_program_text = Column(Text, nullable=True)
    bonus_cashback_text = Column(Text, nullable=True)


class TransactionType(enum.Enum):
    DEPOSIT = "deposit"      # balansga pul qo'shish (masalan, naqd pulni "hisobga olish")
    WITHDRAWAL = "withdrawal"  # balansdan pul yechish (masalan, kuryerga naqd to'lab, balansdan ayirish)


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, index=True)

    # Tranzaksiya yoki kuryerga (user_id), yoki hamkorga (partner_id) tegishli bo'ladi —
    # ikkalasi bir vaqtda to'lmaydi, faqat bittasi ishlatiladi.
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    partner_id = Column(Integer, ForeignKey("partner_profiles.id"), nullable=True)

    type = Column(Enum(TransactionType), nullable=False)
    amount = Column(Float, nullable=False)
    note = Column(String, nullable=True)

    # Kim amalga oshirganini bilish uchun (hisobot va shaffoflik uchun muhim —
    # kim, qachon, kimning balansiga qo'l tekkizganini keyin tekshirish mumkin bo'lishi kerak)
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", foreign_keys=[user_id])
    partner = relationship("PartnerProfile", foreign_keys=[partner_id])
    created_by = relationship("User", foreign_keys=[created_by_id])