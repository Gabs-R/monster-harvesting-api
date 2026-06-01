import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy.orm import Session

from database import SessionLocal
import models
from services.locale_service import t

class InventoryCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="inventory", description="View your equipped and stashed items.")
    async def inventory_cmd(self, interaction: discord.Interaction):
        discord_id = str(interaction.user.id)
        db: Session = SessionLocal()

        try:
            char = db.query(models.Character).filter(models.Character.user_id == discord_id).first()
            if not char:
                # Need to use the generic no_character since we can't invoke NoSessionView here easily 
                # without circular imports or copying it over.
                await interaction.response.send_message(t("no_character", "en"), ephemeral=True)
                return

            lang = char.language
            
            # Fetch inventory items with weapon joined
            inventory_items = (
                db.query(models.InventoryItem)
                .join(models.Weapon)
                .filter(models.InventoryItem.character_id == char.id)
                .order_by(models.InventoryItem.is_equipped.desc(), models.Weapon.tier.desc())
                .all()
            )

            embed = discord.Embed(
                title=t("inventory_title", lang),
                color=discord.Color.gold()
            )

            if not inventory_items:
                embed.description = f"*{t('inventory_empty', lang)}*"
                await interaction.response.send_message(embed=embed)
                return

            # Group them simply
            equipped_str = ""
            stash_str = ""

            for idx, item in enumerate(inventory_items, 1):
                w = item.weapon
                line = t("inventory_item_line", lang, name=w.name, tier=w.tier, dice=w.damage_dice)
                
                if item.is_equipped:
                    equipped_str += f"⚔️ **{line}**\n"
                else:
                    stash_str += f"{idx}. {line}\n"

            if equipped_str:
                embed.add_field(name=t("inventory_equipped", lang), value=equipped_str, inline=False)
            
            if stash_str:
                embed.add_field(name="Stash", value=stash_str, inline=False)

            await interaction.response.send_message(embed=embed)

        except Exception as e:
            import traceback
            traceback.print_exc()
            await interaction.response.send_message(f"⚠️ Failed to load inventory: {e}", ephemeral=True)
        finally:
            db.close()


async def setup(bot):
    await bot.add_cog(InventoryCog(bot))
