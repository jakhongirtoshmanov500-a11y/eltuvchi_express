from fastapi import Request, Depends, HTTPException, status
from fastapi.responses import RedirectResponse
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import User, UserRole

# bcrypt — parolni bir tomonlama xeshlaydi, hech qachon ochiq matnda saqlanmaydi
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain_password: str) -> str:
    return pwd_context.hash(plain_password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    return pwd_context.verify(plain_password, password_hash)


class RedirectToLogin(Exception):
    """/admin sahifasiga sessiyasiz kirilganda shu exception orqali /login'ga yo'naltiramiz."""
    pass


async def get_current_admin_user(request: Request, db: AsyncSession = Depends(get_db)) -> User:
    """
    Sessiyada saqlangan user_id orqali joriy foydalanuvchini topadi.
    Faqat OWNER yoki ADMIN (operator) rolidagilarga ruxsat beradi.
    Boshqa hollarda /login sahifasiga qaytaradi.
    """
    user_id = request.session.get("user_id")
    if not user_id:
        raise RedirectToLogin()

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalars().first()

    if not user or not user.is_active or user.role not in (UserRole.OWNER, UserRole.ADMIN):
        request.session.clear()
        raise RedirectToLogin()

    return user


async def require_owner(user: User = Depends(get_current_admin_user)) -> User:
    """Faqat OWNER kira oladigan route'lar uchun (masalan tizim sozlamalari, do'kon o'chirish)."""
    if user.role != UserRole.OWNER:
        raise HTTPException(status_code=403, detail="Bu amal uchun ruxsatingiz yo'q — faqat egasi (OWNER) bajara oladi")
    return user


def is_scoped_to_city(user: User) -> bool:
    """OWNER — cheklovsiz (True qaytarsa filtr YO'Q). Operator — faqat o'z shahri (city_id bo'yicha filtr)."""
    return user.role == UserRole.ADMIN and user.city_id is not None
