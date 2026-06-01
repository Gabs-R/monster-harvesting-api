import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy.orm import Session
import random

from database import SessionLocal
import models
from combat_engine import resolve_fight, parse_and_roll_dice
from services.locale_service import t
from services.item_service import try_drop_item, INVENTORY_CAP

# XP thresholds per level: level * 100 XP to advance
XP_PER_LEVEL = 100


# ─── Helper: Level-up ─────────────────────────────────────────────────────────

def _check_level_up(char: models.Character) -> str | None:
    """Checks for level-up and applies it. Returns a translated message or None."""
    threshold = char.level * XP_PER_LEVEL
    if char.xp >= threshold:
        char.xp -= threshold
        char.level += 1
        char.max_hp += 5
        # Level-up grants +5 HP and caps at new max
        char.current_hp = min(char.current_hp + 5, char.max_hp)
        return f"🆙 **Level Up!** You are now Level **{char.level}**! (+5 max HP)"
    return None


# ─── Helper: Combat narrative (deterministic, no extra LLM call) ──────────────

def _build_combat_narrative(
    monster: models.Monster,
    char: models.Character,
    result: dict,
    story_location: str,
    lang: str,
) -> str:
    """Builds an in-world narrative summary of the fight outcome using locale templates."""
    rounds = sum(1 for line in result["log"] if line.startswith("[Round"))
    rounds = max(rounds, 1)
    won = result["won"]
    escaped = not won and result["log"] and "escaped" in result["log"][-1].lower()

    if won:
        return t(
            "combat_narrative_victory", lang,
            monster=monster.name,
            name=char.name,
            rounds=rounds,
            hp=result["player_hp"],
        )
    elif escaped:
        return t(
            "combat_narrative_escape", lang,
            monster=monster.name,
            name=char.name,
            rounds=rounds,
        )
    else:
        return t(
            "combat_narrative_defeat", lang,
            monster=monster.name,
            name=char.name,
            rounds=rounds,
            location=story_location,
        )


# ─── Helper: Character dict ───────────────────────────────────────────────────

def _build_char_dict(char: models.Character) -> dict:
    weapon_dice = "1d6"
    if char.weapon:
        weapon_dice = char.weapon.damage_dice
    return {
        "class_name": char.class_name.value,
        "level": char.level,
        "current_hp": char.current_hp,
        "max_hp": char.max_hp,
        "strength": char.strength,
        "agility": char.agility,
        "wisdom": char.wisdom,
        "luck": char.luck,
        "xp": char.xp,
        "weapon_dice": weapon_dice,
    }


def _build_monster_dict(monster: models.Monster) -> dict:
    return {
        "name": monster.name,
        "tier": monster.tier,
        "base_hp": monster.base_hp,
        "base_ac": monster.base_ac,
    }


# ─── Helper: Monster selection ────────────────────────────────────────────────

def _pick_monster(db: Session, char_level: int) -> models.Monster | None:
    """Picks a monster using appropriately weighted scaling based on char level."""
    monsters = db.query(models.Monster).all()
    if not monsters:
        return None

    # Base target tier increments every 2 levels (L1-2: T1, L3-4: T2, etc.)
    target_tier = min(5, max(1, ((char_level - 1) // 2) + 1))
    
    weights = []
    for m in monsters:
        diff = m.tier - target_tier
        if diff == 0:
            weights.append(60.0) # 60% for on-tier
        elif diff == 1:
            weights.append(10.0) # 10% for one tier higher
        elif diff == -1:
            weights.append(25.0) # 25% for one tier lower
        elif diff <= -2:
            weights.append(5.0)  # 5% for trivial fodder
        else:
            weights.append(0.0)  # Cannot encounter 2+ tiers higher

    # If by some edge case all weights are 0, fallback to uniform
    s = sum(weights)
    if s == 0:
        return random.choice(monsters)
        
    return random.choices(monsters, weights=weights, k=1)[0]


# ─── Helper: Hunt embed ───────────────────────────────────────────────────────

def _build_hunt_embed(
    monster: models.Monster,
    result: dict,
    char: models.Character,
    lang: str,
    kill_heal: int,
    narrative: str,
    item_msg: str,
    observer_char: models.Character | None,
) -> discord.Embed:
    won = result["won"]
    escaped = not won and result["log"] and "escaped" in result["log"][-1].lower()

    if won:
        color = discord.Color.gold()
        title = t("hunt_victory", lang, monster=monster.name, xp=result["xp_earned"])
    elif escaped:
        color = discord.Color.orange()
        title = t("hunt_escape", lang)
    else:
        xp_loss = int(char.xp * 0.1)
        color = discord.Color.red()
        title = t("hunt_defeat", lang, xp=xp_loss)

    embed = discord.Embed(title=title, color=color)

    # In-world narrative summary
    embed.description = f"*{narrative}*"

    # Last 6 meaningful log lines (skip initiative)
    combat_lines = [l for l in result["log"] if l.startswith("[Round")][-6:]
    if not combat_lines:
        combat_lines = result["log"][-4:]
    log_str = "\n".join(combat_lines)
    embed.add_field(name=t("hunt_combat_log", lang), value=f"```{log_str}```", inline=False)

    # HP display — shows the FINAL hp after all bonuses have been applied
    final_hp = char.current_hp
    embed.add_field(name="❤️ HP", value=f"{final_hp}/{char.max_hp}", inline=True)
    embed.add_field(name="⚔️ Monster HP", value=str(max(0, result["monster_hp"])), inline=True)

    if kill_heal > 0:
        embed.add_field(name=t("hunt_kill_heal", lang, heal=kill_heal), value="", inline=False)

    if item_msg:
        embed.add_field(name="", value=item_msg, inline=False)

    if observer_char and result["observer_xp"] > 0:
        embed.add_field(
            name=t("hunt_observer_xp", observer_char.language, xp=result["observer_xp"]),
            value="",
            inline=False
        )

    return embed


# ─── Cog ─────────────────────────────────────────────────────────────────────

class HuntCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def _load_char(self, discord_id: str, db: Session) -> models.Character | None:
        return db.query(models.Character).filter(models.Character.user_id == discord_id).first()

    @app_commands.command(name="hunt", description="Seek out a monster and fight it.")
    async def hunt_cmd(self, interaction: discord.Interaction):
        discord_id = str(interaction.user.id)
        db: Session = SessionLocal()

        try:
            char = self._load_char(discord_id, db)
            if not char:
                await interaction.response.send_message(t("no_character"), ephemeral=True)
                return

            lang = char.language
            monster = _pick_monster(db, char.level)
            if not monster:
                await interaction.response.send_message(t("hunt_no_monsters", lang), ephemeral=True)
                return

            # Co-op session detection
            world_session = db.query(models.WorldSession).filter(
                (models.WorldSession.host_id == discord_id) |
                (models.WorldSession.guest_id == discord_id)
            ).first()
            mode = "SOLO"
            observer_char = None
            if world_session:
                mode = world_session.mode.value
                guest_id = world_session.guest_id
                if guest_id and guest_id != discord_id:
                    observer_char = db.query(models.Character).filter(
                        models.Character.user_id == guest_id
                    ).first()

            # Deserter curse
            deserter_state = db.query(models.DeserterState).filter(
                models.DeserterState.user_id == discord_id,
                models.DeserterState.active == True
            ).first()
            has_deserter_curse = deserter_state is not None

            await interaction.response.defer()

            announcement = t("hunt_started", lang, monster=monster.name, tier=monster.tier)
            if has_deserter_curse:
                announcement += f"\n{t('hunt_deserter_warning', lang)}"
            if mode == "ACTIVE":
                announcement += f"\n{t('hunt_coop_active', lang)}"

            # Resolve fight — pass current snapshot of char
            char_dict = _build_char_dict(char)
            result = resolve_fight(char_dict, _build_monster_dict(monster), mode, has_deserter_curse)
            won = result["won"]
            escaped = not won and result["log"] and "escaped" in result["log"][-1].lower()

            # ─── Apply results ──────────────────────────────────────────
            kill_heal = 0
            dropped_weapon, drop_status = None, "none"

            if won:
                # 1. XP gain
                char.xp += result["xp_earned"]
                # 2. Keep post-combat HP (player may have taken damage while winning)
                char.current_hp = max(1, result["player_hp"])
                # 3. Kill bonus heal: roll 1d8, cap at max_hp
                kill_heal = parse_and_roll_dice("1d8")
                char.current_hp = min(char.current_hp + kill_heal, char.max_hp)
                # 4. Clear deserter curse on victory
                if has_deserter_curse and deserter_state:
                    deserter_state.active = False
                # 5. Item drop
                dropped_weapon, drop_status = try_drop_item(db, char, monster)

            elif escaped:
                # Monster fled — keep HP as-is from combat, no XP penalty, no heal
                char.current_hp = max(1, result["player_hp"])

            else:
                # Defeat: apply XP penalty (engine already mutated char_dict["xp"])
                char.xp = max(0, char_dict["xp"])
                # Auto-heal to FULL on defeat (respawn mechanic)
                char.current_hp = char.max_hp

            # Observer XP
            if observer_char and result["observer_xp"] > 0:
                observer_char.xp += result["observer_xp"]
                _check_level_up(observer_char)

            # Level-up check (after all HP and XP changes are applied)
            level_up_msg = _check_level_up(char)

            # Commit ALL changes atomically
            db.commit()
            db.refresh(char)  # Re-read from DB to verify persisted values

            # Story location for narrative
            story_state = db.query(models.StoryState).filter(
                models.StoryState.character_id == char.id
            ).first()
            location = story_state.location if story_state else "Unknown"

            # Build item message string
            item_msg = ""
            if dropped_weapon and drop_status == "equipped":
                old_name = char.weapon.name if char.weapon else "—"
                item_msg = t("item_auto_equipped", lang, item=dropped_weapon.name, old=old_name)
            elif dropped_weapon and drop_status == "added":
                item_msg = t("item_added_inventory", lang, item=dropped_weapon.name)
            elif dropped_weapon and drop_status == "full":
                item_msg = t("item_inventory_full", lang, max=INVENTORY_CAP, item=dropped_weapon.name)
            if dropped_weapon and drop_status in ("equipped", "added"):
                item_msg = t("item_dropped", lang, name=monster.name, item=dropped_weapon.name, tier=dropped_weapon.tier, dice=dropped_weapon.damage_dice) + "\n" + item_msg

            # Generate narrative
            narrative = _build_combat_narrative(monster, char, result, location, lang)

            # Build embed with final (post-commit) HP values
            embed = _build_hunt_embed(monster, result, char, lang, kill_heal, narrative, item_msg, observer_char)
            if level_up_msg:
                embed.add_field(name="\u200b", value=level_up_msg, inline=False)

            await interaction.followup.send(content=announcement, embed=embed)

        except Exception as e:
            import traceback
            traceback.print_exc()
            try:
                await interaction.followup.send(f"⚠️ Hunt failed: {e}", ephemeral=True)
            except Exception:
                pass
        finally:
            db.close()

    @app_commands.command(name="rest", description="Rest to fully restore your HP.")
    async def rest_cmd(self, interaction: discord.Interaction):
        discord_id = str(interaction.user.id)
        db: Session = SessionLocal()

        try:
            char = self._load_char(discord_id, db)
            if not char:
                await interaction.response.send_message(t("no_character"), ephemeral=True)
                return

            lang = char.language

            # Already at full HP?
            if char.current_hp >= char.max_hp:
                await interaction.response.send_message(t("rest_already_full", lang), ephemeral=True)
                return

            story_state = db.query(models.StoryState).filter(
                models.StoryState.character_id == char.id
            ).first()

            await interaction.response.defer()

            # Generate immersive rest narrative via LLM
            from services.llm_service import generate_rest_narrative
            import asyncio
            narrative = await asyncio.to_thread(generate_rest_narrative, char, story_state, lang)

            # Apply full heal
            char.current_hp = char.max_hp
            db.commit()

            embed = discord.Embed(
                title=t("rest_title", lang),
                description=f"*{narrative}*",
                color=discord.Color.teal()
            )
            embed.add_field(
                name=t("rest_hp_update", lang, current=char.current_hp, max=char.max_hp),
                value="",
                inline=False
            )

            await interaction.followup.send(embed=embed)

        except Exception as e:
            import traceback
            traceback.print_exc()
            try:
                await interaction.followup.send(f"⚠️ Rest failed: {e}", ephemeral=True)
            except Exception:
                pass
        finally:
            db.close()


async def setup(bot):
    await bot.add_cog(HuntCog(bot))
