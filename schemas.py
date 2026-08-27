from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from models import UserRole, OrderType, OrderStatus, WeatherCondition  # WeatherCondition import qilindi

# --- SHAHAR SXEMALARI ---
class CityCreate(BaseModel):
    name: str

class CityResponse(BaseModel):
    id: int
    name: str
    is_active: bool

    class Config:
        from_attributes = True

# --- FOYDALANUVCHI SXEMALARI ---
class UserCreate(BaseModel):
    telegram_id: Optional[str] = None
    full_name: str
    phone_number: str
    role: UserRole = UserRole.CLIENT
    city_id: Optional[int] = None

class UserResponse(BaseModel):
    id: int
    telegram_id: Optional[str]
    full_name: str
    phone_number: str
    role: UserRole
    city_id: Optional[int]
    balance: float
    is_active: bool

    class Config:
        from_attributes = True

# --- KAFE / DO'KON (PARTNER) SXEMALARI ---
class PartnerCreate(BaseModel):
    name: str
    city_id: int
    owner_user_id: int
    category: str  # Kafe, Dorixona, Do'kon
    commission_rate: float = 10.0
    address: str

class PartnerResponse(BaseModel):
    id: int
    name: str
    category: str
    commission_rate: float
    address: str
    is_active: bool

    class Config:
        from_attributes = True

# --- MAHSULOT SXEMALARI ---
class ProductCreate(BaseModel):
    partner_id: int
    name: str
    description: Optional[str] = None
    price: float
    image_url: Optional[str] = None

class ProductResponse(BaseModel):
    id: int
    partner_id: int
    name: str
    description: Optional[str]
    price: float
    image_url: Optional[str]
    is_available: bool

    class Config:
        from_attributes = True

# --- BUYURTMA VA POCHTA SXEMALARI ---
class OrderCreate(BaseModel):
    order_type: OrderType
    client_id: int
    partner_id: Optional[int] = None
    from_city_id: Optional[int] = None
    to_city_id: Optional[int] = None
    parcel_description: Optional[str] = None
    total_amount: float
    delivery_fee: float
    pickup_address: Optional[str] = None
    delivery_address: str

class OrderResponse(BaseModel):
    id: int
    order_number: str
    order_type: OrderType
    client_id: int
    partner_id: Optional[int]
    courier_id: Optional[int]
    total_amount: float
    delivery_fee: float
    system_commission: float
    status: OrderStatus
    delivery_address: str
    created_at: datetime

    class Config:
        from_attributes = True

# --- TIZIM SOZLAMALARI (OB-HAVO) SXEMALARI ---
class SystemSettingUpdate(BaseModel):
    base_delivery_fee: Optional[float] = 10000.0
    service_commission_percent: Optional[float] = 10.0
    weather_condition: WeatherCondition = WeatherCondition.CLEAR
    weather_multiplier: Optional[float] = 1.0
    auto_weather_pricing: Optional[bool] = True

class SystemSettingResponse(BaseModel):
    id: int
    base_delivery_fee: float
    service_commission_percent: float
    weather_condition: WeatherCondition
    weather_multiplier: float
    auto_weather_pricing: bool

    class Config:
        from_attributes = True