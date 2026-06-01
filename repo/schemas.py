from pydantic import BaseModel
from typing import Optional
from enum import Enum

class ClassType(str, Enum):
    MAGE = "Mage"
    WARRIOR = "Warrior"
    ARCHER = "Archer"

class WeaponCategory(str, Enum):
    STR = "STR"
    AGI = "AGI"
    WIS = "WIS"
    HYBRID = "HYBRID"

class CoopMode(str, Enum):
    OBSERVER = "OBSERVER"
    ACTIVE = "ACTIVE"

class WeaponBase(BaseModel):
    name: str
    category: WeaponCategory
    tier: int
    damage_dice: str

class Weapon(WeaponBase):
    id: int
    class Config:
        from_attributes = True

class CharacterCreateRequest(BaseModel):
    name: str
    class_name: ClassType
    world_system: str
    language: str = "en"

class CharacterBase(BaseModel):
    name: str
    class_name: ClassType
    world_system: str
    language: str = "en"
    level: int = 1
    xp: int = 0
    max_hp: int
    current_hp: int
    strength: int
    agility: int
    wisdom: int
    luck: int
    equipped_weapon_id: Optional[int] = None

class Character(CharacterBase):
    id: int
    user_id: str
    class Config:
        from_attributes = True

class UserBase(BaseModel):
    discord_id: str
    created_at: str

class User(UserBase):
    character: Optional[Character] = None
    class Config:
        from_attributes = True

class WorldSessionBase(BaseModel):
    host_id: str
    guest_id: Optional[str] = None
    mode: CoopMode = CoopMode.OBSERVER
    active_monster_id: Optional[int] = None

class WorldSession(WorldSessionBase):
    id: int
    class Config:
        from_attributes = True

class DeserterStateBase(BaseModel):
    user_id: str
    active: bool = False

class DeserterState(DeserterStateBase):
    id: int
    class Config:
        from_attributes = True

class MonsterBase(BaseModel):
    name: str
    tier: int
    base_hp: int
    base_ac: int

class Monster(MonsterBase):
    id: int
    class Config:
        from_attributes = True

class StoryStateBase(BaseModel):
    current_arc: str
    location: str
    objective: str
    checkpoint_summary: str
    checkpoint_index: int

class StoryState(StoryStateBase):
    id: int
    character_id: int
    class Config:
        from_attributes = True

class StoryEventBase(BaseModel):
    event_type: str
    description: str
    is_major: bool

class StoryEvent(StoryEventBase):
    id: int
    character_id: int
    class Config:
        from_attributes = True
