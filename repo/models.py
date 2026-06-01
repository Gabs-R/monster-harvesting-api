from sqlalchemy import Column, Integer, String, ForeignKey, Boolean, Enum, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum
from database import Base

class TimestampMixin:
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

class ClassType(enum.Enum):
    MAGE = "Mage"
    WARRIOR = "Warrior"
    ARCHER = "Archer"

class WeaponCategory(enum.Enum):
    STR = "STR"
    AGI = "AGI"
    WIS = "WIS"
    HYBRID = "HYBRID"

class CoopMode(enum.Enum):
    OBSERVER = "OBSERVER"
    ACTIVE = "ACTIVE"

class User(Base):
    __tablename__ = "users"

    discord_id = Column(String, primary_key=True, index=True)
    created_at = Column(DateTime, default=func.now(), nullable=False)

    # Relationships
    character = relationship("Character", back_populates="user", uselist=False)
    deserter_state = relationship("DeserterState", back_populates="user", uselist=False)

class Character(TimestampMixin, Base):
    __tablename__ = "characters"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, ForeignKey("users.discord_id"), unique=True)
    name = Column(String, index=True)
    class_name = Column(Enum(ClassType))
    world_system = Column(String) # High Fantasy, Cyberpunk, etc.

    # Progression
    level = Column(Integer, default=1)
    xp = Column(Integer, default=0)
    
    # HP
    max_hp = Column(Integer)
    current_hp = Column(Integer)
    
    # Attributes (4d6 drop lowest, mathematically clamped)
    strength = Column(Integer)
    agility = Column(Integer)
    wisdom = Column(Integer)
    luck = Column(Integer)
    
    # Equipped Weapon
    equipped_weapon_id = Column(Integer, ForeignKey("weapons.id"), nullable=True)
    
    # Language preference — locked to this character's story run
    language = Column(String, default="en", nullable=False)

    user = relationship("User", back_populates="character")
    weapon = relationship("Weapon")
    story_state = relationship("StoryState", back_populates="character", uselist=False, cascade="all, delete-orphan")
    story_events = relationship("StoryEvent", back_populates="character", cascade="all, delete-orphan")
    inventory = relationship("InventoryItem", back_populates="character", cascade="all, delete-orphan")


class Weapon(TimestampMixin, Base):
    __tablename__ = "weapons"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    category = Column(Enum(WeaponCategory))
    tier = Column(Integer)
    damage_dice = Column(String) # Format: "1d8", "3d10"

class Monster(TimestampMixin, Base):
    __tablename__ = "monsters"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    tier = Column(Integer)
    base_hp = Column(Integer)
    base_ac = Column(Integer)

class WorldSession(TimestampMixin, Base):
    __tablename__ = "world_sessions"

    id = Column(Integer, primary_key=True, index=True)
    host_id = Column(String, ForeignKey("users.discord_id"), unique=True)
    guest_id = Column(String, ForeignKey("users.discord_id"), nullable=True, unique=True)
    mode = Column(Enum(CoopMode), default=CoopMode.OBSERVER)
    active_monster_id = Column(Integer, ForeignKey("monsters.id"), nullable=True)

class DeserterState(TimestampMixin, Base):
    __tablename__ = "deserter_states"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, ForeignKey("users.discord_id"), unique=True)
    active = Column(Boolean, default=False) # Activating means next solo fight scales up +1 tier

    user = relationship("User", back_populates="deserter_state")

class StoryState(TimestampMixin, Base):
    __tablename__ = "story_states"

    id = Column(Integer, primary_key=True, index=True)
    character_id = Column(Integer, ForeignKey("characters.id", ondelete="CASCADE"), unique=True)
    current_arc = Column(String, default="Prologue")
    location = Column(String, default="Starting Town")
    objective = Column(String, default="Find your first quest.")
    checkpoint_summary = Column(String, default="")
    checkpoint_index = Column(Integer, default=0)
    memory_state = Column(String, default="{}")

    character = relationship("Character", back_populates="story_state")

class StoryEvent(TimestampMixin, Base):
    __tablename__ = "story_events"

    id = Column(Integer, primary_key=True, index=True)
    character_id = Column(Integer, ForeignKey("characters.id", ondelete="CASCADE"))
    event_type = Column(String)  # 'hunt', 'rest', 'story', 'creation'
    description = Column(String)
    is_major = Column(Boolean, default=False)

    character = relationship("Character", back_populates="story_events")


class InventoryItem(TimestampMixin, Base):
    """One row per item in a character's backpack.
    
    References the shared Weapon catalogue — no stat duplication.
    Max 10 items per character enforced at the service layer.
    """
    __tablename__ = "inventory_items"

    id = Column(Integer, primary_key=True, index=True)
    character_id = Column(Integer, ForeignKey("characters.id", ondelete="CASCADE"))
    weapon_id = Column(Integer, ForeignKey("weapons.id"))
    is_equipped = Column(Boolean, default=False)

    character = relationship("Character", back_populates="inventory")
    weapon = relationship("Weapon")


