from sqlalchemy import Column, Integer, String, ForeignKey, Boolean, Enum
from sqlalchemy.orm import relationship
import enum
from database import Base

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
    created_at = Column(String)

    # Relationships
    character = relationship("Character", back_populates="user", uselist=False)
    deserter_state = relationship("DeserterState", back_populates="user", uselist=False)

class Character(Base):
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

    user = relationship("User", back_populates="character")
    weapon = relationship("Weapon")

class Weapon(Base):
    __tablename__ = "weapons"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    category = Column(Enum(WeaponCategory))
    tier = Column(Integer)
    damage_dice = Column(String) # Format: "1d8", "3d10"

class Monster(Base):
    __tablename__ = "monsters"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    tier = Column(Integer)
    base_hp = Column(Integer)
    base_ac = Column(Integer)

class WorldSession(Base):
    __tablename__ = "world_sessions"

    id = Column(Integer, primary_key=True, index=True)
    host_id = Column(String, ForeignKey("users.discord_id"), unique=True)
    guest_id = Column(String, ForeignKey("users.discord_id"), nullable=True, unique=True)
    mode = Column(Enum(CoopMode), default=CoopMode.OBSERVER)
    active_monster_id = Column(Integer, ForeignKey("monsters.id"), nullable=True)

class DeserterState(Base):
    __tablename__ = "deserter_states"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, ForeignKey("users.discord_id"), unique=True)
    active = Column(Boolean, default=False) # Activating means next solo fight scales up +1 tier

    user = relationship("User", back_populates="deserter_state")
