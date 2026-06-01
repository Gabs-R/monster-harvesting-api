from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
import schemas
from database import get_db
from services.user_service import create_player_character

router = APIRouter()

@router.post("/users/{discord_id}/characters", response_model=schemas.Character)
def create_character(discord_id: str, request: schemas.CharacterCreateRequest, db: Session = Depends(get_db)):
    """
    Creates a new character for a user. If the user doesn't exist, they are implicitly created.
    Uses the new Service Layer architecture to handle business rules.
    """
    new_character = create_player_character(db, discord_id, request)
    return new_character
