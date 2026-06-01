import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy.orm import Session
import models
import json
import asyncio

from database import SessionLocal
from services.story_service import get_current_story_state, update_story_checkpoint, log_story_event, get_history_log
import services.story_memory as story_mem
from services.locale_service import t


def _build_custom_action_modal(language: str) -> type:
    """Dynamically builds a translated CustomActionModal class."""
    class CustomActionModal(discord.ui.Modal):
        action_text = discord.ui.TextInput(
            label=t("modal_action_label", language),
            style=discord.TextStyle.paragraph,
            placeholder=t("modal_action_placeholder", language),
            required=True,
            max_length=300
        )

        def __init__(self, char_id: int, lang: str):
            super().__init__(title=t("modal_action_title", lang))
            self.char_id = char_id
            self.lang = lang

        async def on_submit(self, interaction: discord.Interaction):
            await interaction.response.defer()
            db: Session = SessionLocal()
            try:
                char = db.query(models.Character).filter(models.Character.id == self.char_id).first()
                story = db.query(models.StoryState).filter(models.StoryState.character_id == char.id).first()

                from services.llm_service import normalize_custom_action
                clean_action = await asyncio.to_thread(normalize_custom_action, self.action_text.value, self.lang)

                await process_story_turn(interaction, db, char, story, custom_action=clean_action, followup=True)

            except Exception as e:
                await interaction.followup.send(t("action_failed", self.lang, error=e), ephemeral=True)
            finally:
                db.close()

    return CustomActionModal


class StoryActionView(discord.ui.View):
    def __init__(self, char_id: int, language: str = "en"):
        super().__init__(timeout=None)
        self.char_id = char_id
        self.language = language
        # Create translated button dynamically
        btn = discord.ui.Button(
            label=t("custom_action_btn", language),
            style=discord.ButtonStyle.primary,
            emoji="✍️"
        )
        btn.callback = self._on_custom_action
        self.add_item(btn)

    async def _on_custom_action(self, interaction: discord.Interaction):
        Modal = _build_custom_action_modal(self.language)
        await interaction.response.send_modal(Modal(self.char_id, self.language))


async def process_story_turn(
    interaction: discord.Interaction,
    db: Session,
    char: models.Character,
    story: models.StoryState,
    custom_action: str = None,
    followup: bool = False,
    guest_char: models.Character = None  # v2: co-op second language
):
    lang = char.language
    history = get_history_log(db, char.id, limit=3)

    # 1. Unpack Memory — merge with defaults to guard against missing keys
    defaults = story_mem.create_story_memory("scene_0")
    try:
        loaded = json.loads(story.memory_state) if story.memory_state else {}
    except json.JSONDecodeError:
        loaded = {}
    mem_dict = {**defaults, **loaded}

    if custom_action:
        story_mem.add_recent_history(mem_dict, "Player", "Action", custom_action)

    mem_summary = story_mem.build_memory_summary(mem_dict)

    from services.llm_service import generate_story

    # v2: Co-op parallel generation when languages differ
    if guest_char and guest_char.language != lang:
        host_task = asyncio.to_thread(
            generate_story,
            character=char,
            current_state=story,
            history_log=history,
            memory_summary=mem_summary,
            custom_action=custom_action,
            language=lang
        )
        guest_task = asyncio.to_thread(
            generate_story,
            character=char,
            current_state=story,
            history_log=history,
            memory_summary=mem_summary,
            custom_action=custom_action,
            language=guest_char.language
        )
        generated_data, guest_data = await asyncio.gather(host_task, guest_task)
        # Only host data is used to update canonical state — guest result is for display only
        _send_guest_result(interaction, guest_char, guest_data, story)
    else:
        generated_data = await asyncio.to_thread(
            generate_story,
            character=char,
            current_state=story,
            history_log=history,
            memory_summary=mem_summary,
            custom_action=custom_action,
            language=lang
        )

    # 2. Extract Memory Updates from LLM
    mem_updates = generated_data.get("memory_updates", {})
    for fact in mem_updates.get("new_scene_facts", []):
        story_mem.add_scene_fact(mem_dict, fact)
    for evt in mem_updates.get("new_canon_events", []):
        story_mem.add_canon_event(mem_dict, evt)
    for npc_stmt in mem_updates.get("new_npc_statements", []):
        story_mem.remember_npc_statement(mem_dict, npc_stmt.get("npc_name", "Unknown"), npc_stmt.get("statement", ""))
    for q in mem_updates.get("new_resolved_questions", []):
        story_mem.resolve_question(mem_dict, q.get("key", ""), q.get("answer", ""), q.get("source", "System"), q.get("confidence", "low"), mem_dict["turn_index"])

    mem_dict["turn_index"] += 1
    story.memory_state = json.dumps(mem_dict)

    # 3. Persist updated checkpoint
    update_story_checkpoint(
        db=db,
        character_id=char.id,
        new_arc=generated_data.get("new_arc"),
        new_location=generated_data.get("new_location"),
        new_objective=generated_data.get("new_objective"),
        summary=generated_data.get("checkpoint_summary")
    )

    # 4. Log the event
    log_story_event(
        db=db,
        character_id=char.id,
        event_type="story",
        description=generated_data.get("event_description", "Story progressed."),
        is_major=generated_data.get("is_major", False)
    )
    db.commit()

    # 5. Send rich embed to Discord
    embed = discord.Embed(
        title=f"📍 {generated_data.get('new_location', t('embed_location_fallback', lang))}",
        description=generated_data.get("narration"),
        color=discord.Color.dark_purple()
    )
    embed.add_field(name=t("embed_objective", lang), value=generated_data.get("new_objective", "—"), inline=False)
    embed.add_field(name=t("embed_arc", lang), value=generated_data.get("new_arc", "—"), inline=True)
    embed.set_footer(text=t("checkpoint_footer", lang, index=story.checkpoint_index))

    await interaction.followup.send(embed=embed, view=StoryActionView(char.id, lang))


def _send_guest_result(interaction, guest_char, guest_data, story):
    """Placeholder for v2 guest DM/channel delivery — extend when co-op channels are wired."""
    # TODO v2: Send guest_data embed to guest's channel or via DM
    pass


class NoSessionView(discord.ui.View):
    def __init__(self, lang: str = "en"):
        super().__init__(timeout=120)
        
        btn_start = discord.ui.Button(
            label=t("go_to_start_btn", lang),
            style=discord.ButtonStyle.primary,
            emoji="🌟"
        )
        btn_retry = discord.ui.Button(
            label=t("retry_btn", lang),
            style=discord.ButtonStyle.secondary,
            emoji="🔄"
        )
        
        # We can't natively redirect to /start, so we instruct them.
        async def start_callback(interaction: discord.Interaction):
            await interaction.response.send_message(t("no_session_detail", lang), ephemeral=True)
            
        async def retry_callback(interaction: discord.Interaction):
            # Simulated retry check to satisfy the "try again" button requirement
            db = SessionLocal()
            char = db.query(models.Character).filter(models.Character.user_id == str(interaction.user.id)).first()
            if not char:
                await interaction.response.send_message(t("session_error", lang, error="Still no character found."), ephemeral=True)
            else:
                await interaction.response.send_message("Session found! Please run the command again.", ephemeral=True)
            db.close()
            
        btn_start.callback = start_callback
        btn_retry.callback = retry_callback
        
        self.add_item(btn_start)
        self.add_item(btn_retry)

def _send_no_session_embed(lang: str) -> tuple[discord.Embed, discord.ui.View]:
    embed = discord.Embed(
        title=t("no_session", lang),
        description=t("no_session_detail", lang),
        color=discord.Color.red()
    )
    return embed, NoSessionView(lang)


class RpgCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def _get_char(self, interaction: discord.Interaction, db: Session) -> models.Character:
        return db.query(models.Character).filter(
            models.Character.user_id == str(interaction.user.id)
        ).first()

    @app_commands.command(name="resume", description="Resume your adventure from where you left off.")
    async def resume_cmd(self, interaction: discord.Interaction):
        db: Session = SessionLocal()
        try:
            char = self._get_char(interaction, db)
            if not char:
                embed, view = _send_no_session_embed("en")
                await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
                return

            lang = char.language
            story = db.query(models.StoryState).filter(models.StoryState.character_id == char.id).first()
            if not story:
                embed, view = _send_no_session_embed(lang)
                await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
                return

            embed = discord.Embed(title=t("welcome_back", lang, name=char.name), color=discord.Color.green())
            embed.add_field(name=t("embed_location_label", lang), value=story.location, inline=True)
            embed.add_field(name=t("embed_objective_resume", lang), value=story.objective, inline=True)
            embed.add_field(name=t("embed_arc_resume", lang), value=story.current_arc, inline=True)
            embed.set_footer(text=t("resume_footer", lang))
            await interaction.response.send_message(embed=embed, view=StoryActionView(char.id, lang))
        except Exception as e:
            await interaction.response.send_message(t("session_error", "en", error=e), ephemeral=True)
        finally:
            db.close()

    @app_commands.command(name="story", description="Progress the story. Optionally describe what you do.")
    @app_commands.describe(action="(Optional) What does your character do? e.g. 'I talk to the blacksmith'")
    async def story_cmd(self, interaction: discord.Interaction, action: str = None):
        db: Session = SessionLocal()
        try:
            char = self._get_char(interaction, db)
            if not char:
                embed, view = _send_no_session_embed("en")
                await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
                return

            lang = char.language
            story = db.query(models.StoryState).filter(models.StoryState.character_id == char.id).first()
            if not story:
                embed, view = _send_no_session_embed(lang)
                await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
                return


            await interaction.response.defer()

            normalized_action = None
            if action:
                from services.llm_service import normalize_custom_action
                normalized_action = await asyncio.to_thread(normalize_custom_action, action, lang)

            await process_story_turn(interaction, db, char, story, custom_action=normalized_action, followup=True)

        except Exception as e:
            lang = "en"
            try:
                await interaction.followup.send(t("story_failed", lang, error=e), ephemeral=True)
            except Exception:
                pass
        finally:
            db.close()

    @app_commands.command(name="recap", description="Recall your recent major story events.")
    async def recap_cmd(self, interaction: discord.Interaction):
        db: Session = SessionLocal()
        try:
            char = self._get_char(interaction, db)
            if not char:
                await interaction.response.send_message(t("no_char_found"), ephemeral=True)
                return

            lang = char.language
            events = get_history_log(db, char.id, limit=5, major_only=True)
            if not events:
                await interaction.response.send_message(t("recap_empty", lang), ephemeral=True)
                return

            embed = discord.Embed(title=t("chronicles_title", lang), color=discord.Color.purple())
            for idx, event in enumerate(reversed(events), 1):
                embed.add_field(name=t("event_label", lang, n=idx), value=event.description, inline=False)

            await interaction.response.send_message(embed=embed)
        finally:
            db.close()


async def setup(bot):
    await bot.add_cog(RpgCog(bot))
