import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from eltuvchi_express.database import get_db
import eltuvchi_express.models_old as models_old, schemas

router = APIRouter(prefix="/orders", tags=["Buyurtmalar va Pochta"])

@router.post("/", response_model=schemas.OrderResponse)
def create_order(order: schemas.OrderCreate, db: Session = Depends(get_db)):
    random_code = str(uuid.uuid4().int)[:4]
    order_num = f"EX-{random_code}"
    
    commission = 0.0
    if order.order_type == models_old.OrderType.PARTNER and order.partner_id:
        partner = db.query(models_old.Partner).filter(models_old.Partner.id == order.partner_id).first()
        if partner:
            commission = (order.total_amount * partner.commission_rate) / 100.0
    else:
        commission = (order.delivery_fee * 0.15)

    new_order = models_old.Order(
        order_number=order_num,
        order_type=order.order_type,
        client_id=order.client_id,
        partner_id=order.partner_id,
        from_city_id=order.from_city_id,
        to_city_id=order.to_city_id,
        parcel_description=order.parcel_description,
        total_amount=order.total_amount,
        delivery_fee=order.delivery_fee,
        system_commission=commission,
        pickup_address=order.pickup_address,
        delivery_address=order.delivery_address,
        status=models_old.OrderStatus.CREATED
    )
    db.add(new_order)
    db.commit()
    db.refresh(new_order)
    return new_order

@router.get("/client/{client_id}", response_model=List[schemas.OrderResponse])
def get_client_orders(client_id: int, db: Session = Depends(get_db)):
    return db.query(models_old.Order).filter(models_old.Order.client_id == client_id).all()