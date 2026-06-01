from sqlalchemy.orm import Session
from fastapi import HTTPException
import models
import schemas
from combat_engine import roll_4d6_drop_lowest
from constants import CLASS_CONFIGS, DEFAULT_CONFIG

def create_player_character(db: Session, discord_id: str, request: schemas.CharacterCreateRequest, overwrite: bool = False) -> models.Character:
    """
    Handles the business logic of character creation, including implicit user creation,
    stat generation, and persistence.
    """
    
    # 1. User check/creation
    user_obj = db.query(models.User).filter(models.User.discord_id == discord_id).first()
    if not user_obj:
        user_obj = models.User(discord_id=discord_id)
        db.add(user_obj)
        db.flush()
    
    # 2. Check character limit and Overwrite mechanic
    char_check = db.query(models.Character).filter(models.Character.user_id == discord_id).first()
    if char_check:
        if not overwrite:
            raise HTTPException(status_code=400, detail="User already has a character.")
        else:
            db.query(models.StoryEvent).filter(models.StoryEvent.character_id == char_check.id).delete()
            db.query(models.StoryState).filter(models.StoryState.character_id == char_check.id).delete()
            db.query(models.InventoryItem).filter(models.InventoryItem.character_id == char_check.id).delete()
            db.delete(char_check)
            db.flush()
            db.expire_all()
        
    # 3. Class-based Initialization using centralized config
    char_class = models.ClassType(request.class_name.value)
    config = CLASS_CONFIGS.get(char_class, DEFAULT_CONFIG)
    max_hp = config["base_hp"]
        
    # 4. Generate stats and instantiate the Character
    new_character = models.Character(
        user_id=discord_id,
        name=request.name,
        class_name=char_class,
        world_system=request.world_system,
        language=request.language,
        level=1,
        xp=0,
        max_hp=max_hp,
        current_hp=max_hp,
        strength=roll_4d6_drop_lowest(),
        agility=roll_4d6_drop_lowest(),
        wisdom=roll_4d6_drop_lowest(),
        luck=roll_4d6_drop_lowest()
    )
    
    db.add(new_character)
    db.flush()
    
    # 5. Initialize the starting weapon
    from services.item_service import seed_starting_weapon
    seed_starting_weapon(db, new_character)

    # 6. Initialize the starting story state
    initial_story_state = models.StoryState(
        character_id=new_character.id,
        current_arc="Prologue",
        location="Starting Town",
        objective="Find your first quest.",
        checkpoint_summary="A new adventurer arrives.",
        checkpoint_index=0
    )
    db.add(initial_story_state)
    
    db.commit()
    db.refresh(new_character)
    
    return new_character
