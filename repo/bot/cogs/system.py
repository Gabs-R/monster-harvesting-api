import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy.orm import Session

from database import SessionLocal
from services.user_service import create_player_character
from services.locale_service import t, SUPPORTED_LANGUAGES, resolve_language
import schemas


# ─── Language Selection ───────────────────────────────────────────────────────

class LanguageSelectView(discord.ui.View):
    """First step in /start — user picks their adventure language."""

    def __init__(self, discord_id: str, discord_locale: str, has_character: bool):
        super().__init__(timeout=120)
        self.discord_id = discord_id
        self.has_character = has_character
        self.detected_lang = resolve_language(discord_locale)

        for code, name in SUPPORTED_LANGUAGES.items():
            btn = discord.ui.Button(
                label=name,
                style=discord.ButtonStyle.primary if code == self.detected_lang else discord.ButtonStyle.secondary,
                custom_id=f"lang_{code}"
            )
            btn.callback = self._make_callback(code)
            self.add_item(btn)

    def _make_callback(self, lang_code: str):
        async def callback(interaction: discord.Interaction):
            await interaction.response.edit_message(
                content=t("start_prompt", lang_code),
                view=StartCommandView(self.discord_id, self.has_character, lang_code),
                embed=None
            )
        return callback


# ─── Character Creation Views ─────────────────────────────────────────────────

class ManualCreationModal(discord.ui.Modal):
    char_name = discord.ui.TextInput(
        label="Character Name",
        placeholder="Enter your hero's name...",
        required=True
    )
    world_system = discord.ui.TextInput(
        label="World System",
        placeholder="e.g., Cyberpunk, High Fantasy, Sci-Fi",
        required=True
    )

    def __init__(self, class_name: str, discord_id: str, overwrite: bool, language: str):
        super().__init__(title="Create Character")
        self.class_name = class_name
        self.discord_id = discord_id
        self.overwrite = overwrite
        self.language = language

    async def on_submit(self, interaction: discord.Interaction):
        db: Session = SessionLocal()
        try:
            req = schemas.CharacterCreateRequest(
                name=self.char_name.value,
                class_name=schemas.ClassType(self.class_name),
                world_system=self.world_system.value,
                language=self.language
            )
            char = create_player_character(db, self.discord_id, req, overwrite=self.overwrite)
            await interaction.response.edit_message(
                content=t("character_created", self.language, name=char.name, cls=char.class_name.value, world=char.world_system),
                view=None, embed=None
            )
        except Exception as e:
            err_msg = getattr(e, "detail", str(e))
            await interaction.response.edit_message(content=f"⚠️ Could not create character: {err_msg}", view=None, embed=None)
        finally:
            db.close()


class ManualClassSelect(discord.ui.Select):
    def __init__(self, discord_id: str, overwrite: bool, language: str):
        self.discord_id = discord_id
        self.overwrite = overwrite
        self.language = language
        options = [
            discord.SelectOption(label="Mage", description="40 HP | Wisdom Focused", emoji="🧙"),
            discord.SelectOption(label="Warrior", description="70 HP | Strength Focused", emoji="⚔️"),
            discord.SelectOption(label="Archer", description="55 HP | Agility Focused", emoji="🏹")
        ]
        super().__init__(placeholder="Choose your Class...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(
            ManualCreationModal(self.values[0], self.discord_id, self.overwrite, self.language)
        )


class ManualClassView(discord.ui.View):
    def __init__(self, discord_id: str, overwrite: bool, language: str):
        super().__init__(timeout=120)
        self.add_item(ManualClassSelect(discord_id, overwrite, language))


class RandomCharacterConfirmView(discord.ui.View):
    def __init__(self, char_data: dict, discord_id: str, overwrite: bool, language: str):
        super().__init__(timeout=120)
        self.char_data = char_data
        self.discord_id = discord_id
        self.overwrite = overwrite
        self.language = language

    @discord.ui.button(label="Accept Destiny", style=discord.ButtonStyle.green, emoji="✅")
    async def btn_accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        db: Session = SessionLocal()
        try:
            req = schemas.CharacterCreateRequest(
                name=self.char_data["name"],
                class_name=schemas.ClassType(self.char_data["class_name"]),
                world_system=self.char_data["world_system"],
                language=self.language
            )
            char = create_player_character(db, self.discord_id, req, overwrite=self.overwrite)
            await interaction.response.edit_message(
                content=t("destiny_sealed", self.language, name=char.name, cls=char.class_name.value, world=char.world_system),
                view=None, embed=None
            )
        except Exception as e:
            err_msg = getattr(e, "detail", str(e))
            await interaction.response.edit_message(content=f"⚠️ Could not create character: {err_msg}", view=None, embed=None)
        finally:
            db.close()

    @discord.ui.button(label="Reroll", style=discord.ButtonStyle.blurple, emoji="🎲")
    async def btn_reroll(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        from services.llm_service import generate_random_character
        new_data = generate_random_character()

        embed = discord.Embed(title="A new destiny forms...", color=discord.Color.purple())
        embed.add_field(name="Name", value=new_data.get("name", "Unknown"))
        embed.add_field(name="Class", value=new_data.get("class_name", "Unknown"))
        embed.add_field(name="World System", value=new_data.get("world_system", "Unknown"))

        await interaction.edit_original_response(
            embed=embed,
            view=RandomCharacterConfirmView(new_data, self.discord_id, self.overwrite, self.language)
        )


class StartCommandView(discord.ui.View):
    def __init__(self, discord_id: str, has_character: bool, language: str = "en"):
        super().__init__(timeout=120)
        self.discord_id = discord_id
        self.has_character = has_character
        self.language = language

        if has_character:
            resume_btn = discord.ui.Button(label="Resume Play", style=discord.ButtonStyle.green)
            resume_btn.callback = self.resume_callback
            self.add_item(resume_btn)

        random_btn = discord.ui.Button(label="Generate Randomly", style=discord.ButtonStyle.blurple, emoji="🔮")
        random_btn.callback = self.random_callback
        self.add_item(random_btn)

        manual_btn = discord.ui.Button(label="Create Manually", style=discord.ButtonStyle.gray, emoji="✍️")
        manual_btn.callback = self.manual_callback
        self.add_item(manual_btn)

    async def resume_callback(self, interaction: discord.Interaction):
        db: Session = SessionLocal()
        try:
            from services.story_service import get_current_story_state
            import models
            char = db.query(models.Character).filter(models.Character.user_id == self.discord_id).first()
            story = get_current_story_state(db, char.id)
            lang = char.language
            msg = t("welcome_back", lang, name=char.name) + f"! You are at **{story.location}**. Objective: {story.objective}"
            await interaction.response.edit_message(content=msg, view=None)
        finally:
            db.close()

    async def manual_callback(self, interaction: discord.Interaction):
        await interaction.response.edit_message(
            content="Pick a class to begin your creation process:",
            view=ManualClassView(self.discord_id, self.has_character, self.language)
        )

    async def random_callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        from services.llm_service import generate_random_character
        data = generate_random_character()

        embed = discord.Embed(title="The weave spun a destiny...", color=discord.Color.purple())
        embed.add_field(name="Name", value=data.get("name", "Unknown"))
        embed.add_field(name="Class", value=data.get("class_name", "Unknown"))
        embed.add_field(name="World System", value=data.get("world_system", "Unknown"))

        await interaction.edit_original_response(
            content=None, embed=embed,
            view=RandomCharacterConfirmView(data, self.discord_id, self.has_character, self.language)
        )


# ─── System Cog ──────────────────────────────────────────────────────────────

class SystemCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="help", description="Explains all commands, classes, and world systems")
    async def help_cmd(self, interaction: discord.Interaction):
        embed = discord.Embed(title="Monster Harvesting RPG - Guide", color=discord.Color.blue())
        embed.description = (
            "Welcome to the adventure! Here are your Core mechanics:\n\n"
            "**/start** - Create your character (Choose Language → World → Class)\n"
            "**/hunt** - Initiate a solo monster encounter\n"
            "**/rest** - Rest to fully restore your HP (immersive scene)\n"
            "**/inventory** - View your equipped weapon and extra items\n"
            "**/story** - Generate an AI scenario in your world\n"
            "**/resume** - Jump back into your active story\n"
            "**/recap** - Review your major story milestones\n"
            "**/joinW** - Join another player's world as an Observer\n"
            "**/leaveW** - Leave the world. Beware the Deserter Curse if mid-fight!"
        )

        embed.add_field(
            name="Classes",
            value="**Mage**: 40 HP | WIS\n**Warrior**: 70 HP | STR\n**Archer**: 55 HP | AGI",
            inline=False
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="start", description="Create your initial character")
    async def start_cmd(self, interaction: discord.Interaction):
        discord_id = str(interaction.user.id)
        discord_locale = str(interaction.locale)
        db: Session = SessionLocal()

        try:
            import models
            char_check = db.query(models.Character).filter(models.Character.user_id == discord_id).first()

            warning = ""
            if char_check:
                warning = t("start_warning")

            detected_lang = resolve_language(discord_locale)
            prompt = f"{warning}{t('lang_select_prompt', detected_lang)}"

            await interaction.response.send_message(
                prompt,
                view=LanguageSelectView(discord_id, discord_locale, bool(char_check)),
                ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(f"⚠️ Error starting prompt: {e}", ephemeral=True)
        finally:
            db.close()


async def setup(bot):
    await bot.add_cog(SystemCog(bot))
