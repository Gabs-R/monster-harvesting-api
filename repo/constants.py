from models import ClassType

# Centralized character class configurations
# This avoids redundancy across combat engine, character creation, and item drops.
CLASS_CONFIGS = {
    ClassType.MAGE: {
        "base_hp": 40,
        "base_ac": 13,
        "primary_stat": "wisdom",
        "weapon_categories": ["WIS", "HYBRID"]
    },
    ClassType.WARRIOR: {
        "base_hp": 70,
        "base_ac": 15,
        "primary_stat": "strength",
        "weapon_categories": ["STR", "HYBRID"]
    },
    ClassType.ARCHER: {
        "base_hp": 55,
        "base_ac": 14,
        "primary_stat": "agility",
        "weapon_categories": ["AGI", "HYBRID"]
    }
}

DEFAULT_CONFIG = {
    "base_hp": 50,
    "base_ac": 10,
    "primary_stat": "strength",
    "weapon_categories": ["HYBRID"]
}
