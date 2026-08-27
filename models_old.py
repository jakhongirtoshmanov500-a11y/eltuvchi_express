import enum
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, 
    DateTime, ForeignKey, Enum, Text
)
from sqlalchemy.orm import relationship
from eltuvchi_express.database import Base

# --- ENUM TURLARI (Rollar va Statuslar) ---
class UserRole(str, enum.Enum):
    OWNER = "owner"          # Siz (Tizim egasi)
    OPERATOR = "operator"    # Boshqaruvchi operator
    CLIENT = "client"        # Mijoz
    COURIER = "courier"      # Kuryer
    PARTNER = "partner"      # Kafe / Do'kon / Dorixona egasi

class OrderType(str, enum.Enum):
    PARTNER = "partner"      # Kafe, do'kon, dorixona buyurtmasi
    PARCEL = "parcel"        # Pochta va yengil yuk (Shahar ichida va shaharlararo)

class OrderStatus(str, enum.Enum):
    CREATED = "created"            # Yangi buyurtma
    ACCEPTED = "accepted"          # Qabul qilindi
    PREPARING = "preparing"        # Tayyorlanmoqda
    READY = "ready"                # Kuryer kutilmoqda
    ON_THE_WAY = "on_the_way"      # Kuryer yo'lda
    DELIVERED = "delivered"        # Yetkazildi
    CANCELLED = "cancelled"        # Bekor qilindi

class TransactionType(str, enum.Enum):
    DEPOSIT = "deposit"            # Balans to'ldirish (Click, Payme, Uzum va h.k.)
    COMMISSION = "commission"      # Tizim komissiyasi
    PAYOUT = "payout"              # Pul yechib olish

# --- MA'LUMOTLAR JADVALLARI ---

class City(Base):
    __tablename__ = "cities"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False) # Uchquduq, Zarafshon
    is_active = Column(Boolean, default=True)

    users = relationship("User", back_populates="city")
    partners = relationship("Partner", back_populates="city")


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(String, unique=True, index=True, nullable=True)
    full_name = Column(String, nullable=False)
    phone_number = Column(String, unique=True, nullable=False)
    role = Column(Enum(UserRole), default=UserRole.CLIENT, nullable=False)
    city_id = Column(Integer, ForeignKey("cities.id"), nullable=True)
    balance = Column(Float, default=0.0) # Kuryer va partnerlar balansi
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    city = relationship("City", back_populates="users")
    orders = relationship("Order", back_populates="client", foreign_keys="Order.client_id")
    deliveries = relationship("Order", back_populates="courier", foreign_keys="Order.courier_id")
    audit_logs = relationship("AuditLog", back_populates="operator")


class Partner(Base):
    __tablename__ = "partners"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False) # Masalan: "Lazzat Kafe", "Dori-Darmon"
    city_id = Column(Integer, ForeignKey("cities.id"), nullable=False)
    owner_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    category = Column(String, nullable=False) # Kafe, Dorixona, Do'kon
    commission_rate = Column(Float, default=10.0)
    address = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)

    city = relationship("City", back_populates="partners")
    products = relationship("Product", back_populates="partner")
    orders = relationship("Order", back_populates="partner")


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    partner_id = Column(Integer, ForeignKey("partners.id"), nullable=False)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    price = Column(Float, nullable=False)
    image_url = Column(String, nullable=True)
    is_available = Column(Boolean, default=True) # Stop-list uchun

    partner = relationship("Partner", back_populates="products")


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    order_number = Column(String, unique=True, index=True)
    order_type = Column(Enum(OrderType), default=OrderType.PARTNER)
    
    client_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    partner_id = Column(Integer, ForeignKey("partners.id"), nullable=True)
    courier_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    
    from_city_id = Column(Integer, ForeignKey("cities.id"), nullable=True)
    to_city_id = Column(Integer, ForeignKey("cities.id"), nullable=True)
    
    parcel_description = Column(Text, nullable=True)
    
    total_amount = Column(Float, nullable=False)
    delivery_fee = Column(Float, nullable=False)
    system_commission = Column(Float, default=0.0) # Sizning sof daromadingiz
    
    status = Column(Enum(OrderStatus), default=OrderStatus.CREATED)
    pickup_address = Column(Text, nullable=True)
    delivery_address = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    client = relationship("User", foreign_keys=[client_id], back_populates="orders")
    courier = relationship("User", foreign_keys=[courier_id], back_populates="deliveries")
    partner = relationship("Partner", back_populates="orders")


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    amount = Column(Float, nullable=False)
    type = Column(Enum(TransactionType), nullable=False)
    payment_system = Column(String, nullable=True)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class AuditLog(Base):
    """EGASINING NAZORAT PANELI UCHUN AUDIT LOG"""
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    operator_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    action = Column(String, nullable=False)
    details = Column(Text, nullable=True)
    ip_address = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    operator = relationship("User", back_populates="audit_logs")