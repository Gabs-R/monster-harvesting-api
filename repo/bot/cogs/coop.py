import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy.orm import Session

from database import SessionLocal
import models
from services.locale_service import t

class CoopCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def _get_lang(self, discord_id: str) -> str:
        db = SessionLocal()
        try:
            char = db.query(models.Character).filter(models.Character.user_id == discord_id).first()
            return char.language if char else "en"
        finally:
            db.close()

    @app_commands.command(name="joinworld", description="Join a friend's world in observer mode.")
    async def joinworld_cmd(self, interaction: discord.Interaction, friend_discord_id: str):
        lang = self._get_lang(str(interaction.user.id))
        await interaction.response.send_message(t("coop_in_development", lang), ephemeral=True)

    @app_commands.command(name="leaveworld", description="Leave the current world session.")
    async def leaveworld_cmd(self, interaction: discord.Interaction):
        lang = self._get_lang(str(interaction.user.id))
        await interaction.response.send_message(t("coop_in_development", lang), ephemeral=True)

    @app_commands.command(name="fightcoop", description="Activate active co-op mode for the fights.")
    async def fightcoop_cmd(self, interaction: discord.Interaction):
        lang = self._get_lang(str(interaction.user.id))
        await interaction.response.send_message(t("coop_in_development", lang), ephemeral=True)

    @app_commands.command(name="cohunt", description="Start a co-op hunt with the host.")
    async def cohunt_cmd(self, interaction: discord.Interaction):
        lang = self._get_lang(str(interaction.user.id))
        await interaction.response.send_message(t("coop_in_development", lang), ephemeral=True)


async def setup(bot):
    await bot.add_cog(CoopCog(bot))
