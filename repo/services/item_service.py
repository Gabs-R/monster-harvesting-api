"""Item service — governs weapon drops, auto-equip, and inventory management.

Design decisions:
- Inventory cap: 10 items per character
- Auto-equip: if new item has a higher max roll than equipped weapon, swap automatically
- Drop rate: 25% base — reduced for trivial kills
- Weapon catalogue is shared
"""

from __future__ import annotations
import random
import logging
from typing import Optional
from sqlalchemy.orm import Session

import models
from combat_engine import get_max_weapon_damage
from constants import CLASS_CONFIGS, DEFAULT_CONFIG

logger = logging.getLogger(__name__)

INVENTORY_CAP = 10
BASE_DROP_CHANCE = 0.25
TRIVIAL_DROP_CHANCE = 0.12

def try_drop_item(
    db: Session,
    char: models.Character,
    monster: models.Monster,
) -> tuple[Optional[models.Weapon], str]:
    """Attempts to drop an appropriate item after a monster kill."""
    # Determine drop chance
    level_gap = char.level - monster.tier
    drop_chance = TRIVIAL_DROP_CHANCE if level_gap >= 3 else BASE_DROP_CHANCE

    if random.random() > drop_chance:
        return None, "none"

    # Get eligible categories from config
    config = CLASS_CONFIGS.get(char.class_name, DEFAULT_CONFIG)
    eligible_categories = config["weapon_categories"]

    # Weapon tier = monster tier (±1)
    min_tier = max(1, monster.tier - 1)
    max_tier = monster.tier + 1

    candidates = (
        db.query(models.Weapon)
        .filter(
            models.Weapon.tier >= min_tier,
            models.Weapon.tier <= max_tier,
            models.Weapon.category.in_([
                models.WeaponCategory[c] for c in eligible_categories
            ])
        )
        .all()
    )

    if not candidates:
        return None, "none"

    dropped = random.choice(candidates)

    # Check inventory cap
    current_count = (
        db.query(models.InventoryItem)
        .filter(models.InventoryItem.character_id == char.id)
        .count()
    )

    if current_count >= INVENTORY_CAP:
        return dropped, "full"

    # Determine if this weapon is better than currently equipped
    equipped_weapon = char.weapon
    equipped_max = get_max_weapon_damage(equipped_weapon.damage_dice) if equipped_weapon else 0
    dropped_max = get_max_weapon_damage(dropped.damage_dice)

    if dropped_max > equipped_max:
        # Auto-equip
        _unequip_all(db, char)
        inv_item = models.InventoryItem(
            character_id=char.id,
            weapon_id=dropped.id,
            is_equipped=True,
        )
        db.add(inv_item)
        char.equipped_weapon_id = dropped.id
        return dropped, "equipped"
    else:
        # Just stash
        inv_item = models.InventoryItem(
            character_id=char.id,
            weapon_id=dropped.id,
            is_equipped=False,
        )
        db.add(inv_item)
        return dropped, "added"

def _unequip_all(db: Session, char: models.Character) -> None:
    """Marks all inventory items for this character as unequipped."""
    db.query(models.InventoryItem).filter(
        models.InventoryItem.character_id == char.id,
        models.InventoryItem.is_equipped == True
    ).update({"is_equipped": False})

def seed_starting_weapon(db: Session, character: models.Character) -> None:
    """Helper to initialize the first weapon for a new character."""
    config = CLASS_CONFIGS.get(character.class_name, DEFAULT_CONFIG)
    primary_cat = config["weapon_categories"][0]
    
    starting_weapon = db.query(models.Weapon).filter(
        models.Weapon.tier == 1,
        models.Weapon.category == models.WeaponCategory[primary_cat]
    ).first()
    
    if starting_weapon:
        inv_item = models.InventoryItem(
            character_id=character.id,
            weapon_id=starting_weapon.id,
            is_equipped=True
        )
        db.add(inv_item)
        character.equipped_weapon_id = starting_weapon.id
        db.flush()

def seed_weapons(db: Session) -> None:
    """Populates the weapons table if empty."""
    if db.query(models.Weapon).count() > 0:
        return

    weapons = [
        # Tier 1 — STR
        models.Weapon(name="Rusty Sword",       category=models.WeaponCategory.STR, tier=1, damage_dice="1d6"),
        models.Weapon(name="Iron Axe",          category=models.WeaponCategory.STR, tier=1, damage_dice="1d8"),
        # Tier 2 — STR
        models.Weapon(name="Battle Axe",        category=models.WeaponCategory.STR, tier=2, damage_dice="2d6"),
        models.Weapon(name="Knight Sword",      category=models.WeaponCategory.STR, tier=2, damage_dice="1d10"),
        # Tier 3 — STR
        models.Weapon(name="Warlord Hammer",    category=models.WeaponCategory.STR, tier=3, damage_dice="2d8"),
        models.Weapon(name="Greatsword",        category=models.WeaponCategory.STR, tier=3, damage_dice="2d10"),
        # Tier 4 — STR
        models.Weapon(name="Titan Cleaver",     category=models.WeaponCategory.STR, tier=4, damage_dice="3d8"),
        # Tier 5 — STR
        models.Weapon(name="Dragonbone Sword",  category=models.WeaponCategory.STR, tier=5, damage_dice="3d10"),

        # Tier 1 — AGI
        models.Weapon(name="Hunting Bow",       category=models.WeaponCategory.AGI, tier=1, damage_dice="1d6"),
        models.Weapon(name="Short Bow",         category=models.WeaponCategory.AGI, tier=1, damage_dice="1d8"),
        # Tier 2 — AGI
        models.Weapon(name="Elven Shortbow",    category=models.WeaponCategory.AGI, tier=2, damage_dice="2d6"),
        models.Weapon(name="Twin Daggers",      category=models.WeaponCategory.AGI, tier=2, damage_dice="1d10"),
        # Tier 3 — AGI
        models.Weapon(name="Shadow Crossbow",   category=models.WeaponCategory.AGI, tier=3, damage_dice="2d8"),
        models.Weapon(name="Recurve Bow",       category=models.WeaponCategory.AGI, tier=3, damage_dice="2d10"),
        # Tier 4 — AGI
        models.Weapon(name="Phantom Bow",       category=models.WeaponCategory.AGI, tier=4, damage_dice="3d8"),
        # Tier 5 — AGI
        models.Weapon(name="Mythril Longbow",   category=models.WeaponCategory.AGI, tier=5, damage_dice="3d10"),

        # Tier 1 — WIS
        models.Weapon(name="Apprentice Staff",  category=models.WeaponCategory.WIS, tier=1, damage_dice="1d6"),
        models.Weapon(name="Gnarled Wand",      category=models.WeaponCategory.WIS, tier=1, damage_dice="1d8"),
        # Tier 2 — WIS
        models.Weapon(name="Mage Staff",        category=models.WeaponCategory.WIS, tier=2, damage_dice="2d6"),
        models.Weapon(name="Crystal Orb",       category=models.WeaponCategory.WIS, tier=2, damage_dice="1d10"),
        # Tier 3 — WIS
        models.Weapon(name="Arcane Tome",       category=models.WeaponCategory.WIS, tier=3, damage_dice="2d8"),
        models.Weapon(name="Elemental Staff",   category=models.WeaponCategory.WIS, tier=3, damage_dice="2d10"),
        # Tier 4 — WIS
        models.Weapon(name="Void Conductor",    category=models.WeaponCategory.WIS, tier=4, damage_dice="3d8"),
        # Tier 5 — WIS
        models.Weapon(name="Aetheric Staff",    category=models.WeaponCategory.WIS, tier=5, damage_dice="3d10"),

        # HYBRID — any class
        models.Weapon(name="Blessed Dagger",    category=models.WeaponCategory.HYBRID, tier=1, damage_dice="1d6"),
        models.Weapon(name="Silver Kris",       category=models.WeaponCategory.HYBRID, tier=2, damage_dice="1d8"),
        models.Weapon(name="Runed Blade",       category=models.WeaponCategory.HYBRID, tier=3, damage_dice="2d6"),
        models.Weapon(name="Starforged Band",   category=models.WeaponCategory.HYBRID, tier=4, damage_dice="2d8"),
        models.Weapon(name="World Shard",       category=models.WeaponCategory.HYBRID, tier=5, damage_dice="3d8"),
    ]
    db.add_all(weapons)
    db.commit()
    logger.info(f"Seeded {len(weapons)} weapons.")
