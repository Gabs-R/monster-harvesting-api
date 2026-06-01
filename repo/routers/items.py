from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
import models
import schemas

router = APIRouter()

@router.get("/items", response_model=list[schemas.Weapon])
def list_available_weapons(db: Session = Depends(get_db)):
    """
    Returns the list of all discoverable weapons in the game.
    """
    return db.query(models.Weapon).all()

@router.get("/items/{item_id}", response_model=schemas.Weapon)
def get_item_details(item_id: int, db: Session = Depends(get_db)):
    """
    Returns details for a specific item.
    """
    item = db.query(models.Weapon).filter(models.Weapon.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return item
