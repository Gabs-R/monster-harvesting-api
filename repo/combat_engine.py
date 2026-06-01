import random
import logging
from math import floor
from typing import Dict, Any
from models import ClassType
from constants import CLASS_CONFIGS, DEFAULT_CONFIG

# Configure logging for professional output
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

def roll_4d6_drop_lowest() -> int:
    """Rolls 4d6, drops the lowest value, and returns the sum. Clamped between 8 and 16."""
    rolls = [random.randint(1, 6) for _ in range(4)]
    rolls.remove(min(rolls))
    total = sum(rolls)
    return max(8, min(16, total))

def roll_d20() -> int:
    """Returns a random 1-20 integer."""
    return random.randint(1, 20)

def parse_and_roll_dice(dice_str: str) -> int:
    """Parses a string like '1d8' and returns the total damage roll."""
    if not dice_str or 'd' not in dice_str.lower():
        return 0
    try:
        count, sides = map(int, dice_str.lower().split('d'))
        return sum(random.randint(1, sides) for _ in range(count))
    except ValueError:
        logger.error(f"Failed to parse dice string: {dice_str}")
        return 0

def get_max_weapon_damage(dice_str: str) -> int:
    """Returns the maximum possible damage from a weapon dice string (e.g., '1d8' -> 8). Used for Critical Hits."""
    if not dice_str or 'd' not in dice_str.lower():
        return 0
    try:
        count, sides = map(int, dice_str.lower().split('d'))
        return count * sides
    except ValueError:
        logger.error(f"Failed to parse dice string for max damage: {dice_str}")
        return 0

def resolve_fight(character_data: Dict[str, Any], monster_data: Dict[str, Any], mode: str, has_deserter_curse: bool) -> Dict[str, Any]:
    """
    Executes a turn-based combat loop between a player and a monster.
    Returns a dictionary with the fight results, log, and any status changes.
    """
    combat_log = []
    
    player_hp = character_data["current_hp"]
    monster_hp = monster_data["base_hp"]
    monster_tier = monster_data["tier"]
    
    # Deserter Curse logic
    if has_deserter_curse:
        monster_tier += 1
        monster_hp += 15
        combat_log.append(f"⚠️ The Deserter Curse empowers the enemy! It fights as a Tier {monster_tier} monster.")

    # Get class-specific configuration
    try:
        # If class_name is a string, convert to Enum
        char_class = character_data["class_name"]
        if isinstance(char_class, str):
            char_class = ClassType(char_class)
        config = CLASS_CONFIGS.get(char_class, DEFAULT_CONFIG)
    except ValueError:
        config = DEFAULT_CONFIG

    # Calculate Player AC
    player_ac = config["base_ac"] + character_data["level"]
    
    # Calculate Co-Op modifiers
    hit_bonus = 0
    dmg_modifier = 1.0
    if mode == "ACTIVE":
        hit_bonus = 3
        dmg_modifier = 1.5
        combat_log.append("🤝 Active Co-Op Mode engaged! You have a massive combat advantage.")

    # Primary Stat determination
    pri_stat_name = config["primary_stat"]
    pri_stat_val = character_data.get(pri_stat_name, 10)
    stat_mod = floor((pri_stat_val - 10) / 2)

    # Initiative roll
    agi_val = character_data.get("agility", 10)
    agi_mod = floor((agi_val - 10) / 2)
    initiative_player = roll_d20() + agi_mod
    initiative_monster = roll_d20() + monster_tier
    player_turn = initiative_player >= initiative_monster
    
    combat_log.append(f"⚔️ Initiative: Player ({initiative_player}) vs Monster ({initiative_monster}).")

    rounds = 0
    max_rounds = 20
    
    while player_hp > 0 and monster_hp > 0 and rounds < max_rounds:
        rounds += 1
        
        if player_turn:
            # Player Attack Phase
            atk_roll = roll_d20()
            total_atk = atk_roll + character_data["level"] + stat_mod + hit_bonus
            
            if atk_roll == 20: 
                # Critical Hit!
                base_dmg = get_max_weapon_damage(character_data.get("weapon_dice", "1d6"))
                total_dmg = int(((base_dmg * 2) + stat_mod) * dmg_modifier)
                monster_hp -= total_dmg
                combat_log.append(f"[R{rounds}] 🌟 CRITICAL HIT! You deal {total_dmg} damage!")
            elif total_atk >= monster_data["base_ac"]:
                # Normal Hit
                base_dmg = parse_and_roll_dice(character_data.get("weapon_dice", "1d6"))
                total_dmg = int((base_dmg + stat_mod) * dmg_modifier)
                total_dmg = max(1, total_dmg)
                monster_hp -= total_dmg
                combat_log.append(f"[R{rounds}] ⚔️ You hit for {total_dmg} damage (Atk: {total_atk}).")
            else:
                combat_log.append(f"[R{rounds}] 🛡️ You miss (Atk: {total_atk} vs AC {monster_data['base_ac']}).")
        else:
            # Monster Attack Phase
            atk_roll = roll_d20()
            total_atk = atk_roll + monster_tier
            
            if total_atk >= player_ac:
                # Monster damage: 1d6 per tier + tier
                m_dmg = sum(random.randint(1, 6) for _ in range(monster_tier)) + monster_tier
                player_hp -= m_dmg
                combat_log.append(f"[R{rounds}] 🩸 Monster hits for {m_dmg} damage (Atk: {total_atk}).")
            else:
                combat_log.append(f"[R{rounds}] 🛡️ Monster misses (Atk: {total_atk} vs AC {player_ac}).")
                
        player_turn = not player_turn

    # Resolution
    victory = monster_hp <= 0
    xp_earned = 0
    observer_xp = 0
    
    if victory:
        combat_log.append("🏆 Victory! The monster is defeated.")
        xp_earned = 50 * monster_data["tier"]
        
        # Scaling penalty
        if character_data["level"] - monster_data["tier"] >= 3:
            xp_earned = int(xp_earned * 0.5)
            combat_log.append("⚠️ The monster was too weak, XP gained halved.")
            
        if mode == "OBSERVER":
            observer_xp = int(xp_earned * 0.3)
    else:
        if rounds >= max_rounds:
            combat_log.append("💨 The combat dragged on too long and the monster escaped!")
        else:
            combat_log.append("💀 Defeat! You were struck down.")
            xp_loss = int(character_data.get("xp", 0) * 0.1)
            character_data["xp"] = max(0, character_data.get("xp", 0) - xp_loss)
            player_hp = character_data["max_hp"] # Auto heal
            combat_log.append(f"🩹 You lost {xp_loss} XP but woke up fully healed.")
            
    return {
        "won": victory,
        "player_hp": player_hp,
        "monster_hp": monster_hp,
        "xp_earned": xp_earned,
        "observer_xp": observer_xp,
        "log": combat_log,
        "cleared_deserter": has_deserter_curse and victory
    }
