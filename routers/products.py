from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from eltuvchi_express.database import get_db
import eltuvchi_express.models_old as models_old, schemas

router = APIRouter(prefix="/products", tags=["Mahsulotlar (Kafelar uchun)"])

@router.post("/", response_model=schemas.ProductResponse)
def create_product(product: schemas.ProductCreate, db: Session = Depends(get_db)):
    new_product = models_old.Product(**product.model_dump())
    db.add(new_product)
    db.commit()
    db.refresh(new_product)
    return new_product

@router.get("/partner/{partner_id}", response_model=List[schemas.ProductResponse])
def get_products_by_partner(partner_id: int, db: Session = Depends(get_db)):
    return db.query(models_old.Product).filter(
        models_old.Product.partner_id == partner_id,
        models_old.Product.is_available == True
    ).all()