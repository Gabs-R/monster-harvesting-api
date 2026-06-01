import discord
from discord.ext import commands
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from database import SessionLocal
import models
from services.item_service import seed_weapons

intents = discord.Intents.default()
# We do NOT request message_content intent to avoid crashing if the user hasn't enabled it in the Developer Portal.
# Slash commands (app_commands) work natively without privileged intents.
intents.message_content = False

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

@bot.event
async def on_ready():
    print(f"Bot initialized: Logged in as {bot.user} (ID: {bot.user.id})")
    
    # Run the database seeder for items/weapons
    with SessionLocal() as db:
        seed_weapons(db)
        
    print("------")
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s) globally")
    except Exception as e:
        print(f"Failed to sync commands: {e}")


def _seed_monsters():
    """Populates the monsters table with a diverse roster if it's empty."""
    db = SessionLocal()
    try:
        if db.query(models.Monster).count() > 0:
            return
        monsters = [
            models.Monster(name="Giant Rat",        tier=1, base_hp=15, base_ac=10),
            models.Monster(name="Goblin Scout",     tier=1, base_hp=20, base_ac=11),
            models.Monster(name="Slime",            tier=1, base_hp=25, base_ac=8),
            models.Monster(name="Wild Wolf",        tier=1, base_hp=18, base_ac=12),
            models.Monster(name="Skeleton Archer",  tier=2, base_hp=28, base_ac=13),
            models.Monster(name="Orc Brute",        tier=2, base_hp=35, base_ac=12),
            models.Monster(name="Bandit Outlaw",    tier=2, base_hp=30, base_ac=11),
            models.Monster(name="Vampire Bat",      tier=2, base_hp=22, base_ac=14),
            models.Monster(name="Dark Mage",        tier=3, base_hp=40, base_ac=14),
            models.Monster(name="Stone Golem",      tier=3, base_hp=55, base_ac=16),
            models.Monster(name="Minotaur",         tier=3, base_hp=65, base_ac=13),
            models.Monster(name="Wyvern",           tier=4, base_hp=70, base_ac=15),
            models.Monster(name="Shadow Drake",     tier=4, base_hp=65, base_ac=17),
            models.Monster(name="Elder Lich",       tier=5, base_hp=90, base_ac=18),
            models.Monster(name="Ancient Dragon",   tier=5, base_hp=120, base_ac=19),
        ]
        db.add_all(monsters)
        db.commit()
        print(f"Seeded {len(monsters)} monsters.")
    finally:
        db.close()


async def run_bot():
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        print("DISCORD_TOKEN environment variable not set.")
        return
        
    await bot.load_extension("bot.cogs.system")
    await bot.load_extension("bot.cogs.rpg")
    await bot.load_extension("bot.cogs.hunt")
    await bot.load_extension("bot.cogs.inventory")
    await bot.load_extension("bot.cogs.coop")

    
    # Seed monsters if the table is empty
    _seed_monsters()
    
    print("Connecting to Discord...")
    await bot.start(token)
    
if __name__ == "__main__":
    import asyncio
    from dotenv import load_dotenv
    load_dotenv()
    asyncio.run(run_bot())
