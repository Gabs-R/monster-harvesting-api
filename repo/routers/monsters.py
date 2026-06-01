from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
import models
import schemas
from typing import Optional

router = APIRouter()

@router.get("/monsters", response_model=list[schemas.Monster])
def list_monsters(tier: Optional[int] = None, db: Session = Depends(get_db)):
    """
    Returns the list of monsters, optionally filtered by tier.
    """
    query = db.query(models.Monster)
    if tier is not None:
        query = query.filter(models.Monster.tier == tier)
    return query.all()

@router.get("/monsters/{monster_id}", response_model=schemas.Monster)
def get_monster(monster_id: int, db: Session = Depends(get_db)):
    """
    Returns details for a specific monster.
    """
    monster = db.query(models.Monster).filter(models.Monster.id == monster_id).first()
    if not monster:
        raise HTTPException(status_code=404, detail="Monster not found")
    return monster
