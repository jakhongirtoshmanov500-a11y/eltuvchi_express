from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from eltuvchi_express.database import get_db
import eltuvchi_express.models_old as models_old, schemas

router = APIRouter(prefix="/users", tags=["Foydalanuvchilar va Kuryerlar"])

@router.post("/", response_model=schemas.UserResponse)
def create_user(user: schemas.UserCreate, db: Session = Depends(get_db)):
    # Telegram ID bo'yicha bazada bor-yo'qligini tekshirish
    if user.telegram_id:
        existing_user = db.query(models_old.User).filter(models_old.User.telegram_id == user.telegram_id).first()
        if existing_user:
            return existing_user

    new_user = models_old.User(
        telegram_id=user.telegram_id,
        full_name=user.full_name,
        phone_number=user.phone_number,
        role=user.role,
        city_id=user.city_id
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user

@router.get("/telegram/{tg_id}", response_model=schemas.UserResponse)
def get_user_by_telegram(tg_id: str, db: Session = Depends(get_db)):
    user = db.query(models_old.User).filter(models_old.User.telegram_id == tg_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Foydalanuvchi topilmadi")
    return user

@router.get("/", response_model=List[schemas.UserResponse])
def get_users(db: Session = Depends(get_db)):
    return db.query(models_old.User).all()