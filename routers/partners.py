from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from eltuvchi_express.database import get_db
import eltuvchi_express.models_old as models_old, schemas

router = APIRouter(prefix="/partners", tags=["Kafelar va Do'konlar"])

# 1. Yangi partner (kafe/do'kon) qo'shish
@router.post("/", response_model=schemas.PartnerResponse)
def create_partner(partner: schemas.PartnerCreate, db: Session = Depends(get_db)):
    new_partner = models_old.Partner(
        name=partner.name,
        city_id=partner.city_id,
        owner_user_id=partner.owner_user_id,
        category=partner.category,
        commission_rate=partner.commission_rate,
        address=partner.address
    )
    db.add(new_partner)
    db.commit()
    db.refresh(new_partner)
    return new_partner

# 2. Shahar bo'yicha partnerlarni olish (Masalan, faqat Uchquduqdagilari)
@router.get("/city/{city_id}", response_model=List[schemas.PartnerResponse])
def get_partners_by_city(city_id: int, db: Session = Depends(get_db)):
    return db.query(models_old.Partner).filter(
        models_old.Partner.city_id == city_id, 
        models_old.Partner.is_active == True
    ).all()