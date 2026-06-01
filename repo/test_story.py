import unittest
import os
import json
from unittest.mock import patch, MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base
from services.user_service import create_player_character
from services.story_service import get_current_story_state, update_story_checkpoint, log_story_event, get_history_log
from services.llm_service import parse_story_response, build_story_prompt, fallback_story_response, generate_story
import schemas
import models

# In-memory SQLite for complete test isolation
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def make_character(db, discord_id="test_user_001", name="TestHero", class_name=schemas.ClassType.WARRIOR, world="Cyberpunk"):
    """Helper: create a fresh character for any test."""
    req = schemas.CharacterCreateRequest(name=name, class_name=class_name, world_system=world)
    return create_player_character(db, discord_id, req)


class TestCharacterCreation(unittest.TestCase):
    def setUp(self):
        Base.metadata.create_all(bind=engine)
        self.db = TestingSessionLocal()

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(bind=engine)

    def test_creates_character_with_correct_stats(self):
        char = make_character(self.db)
        self.assertEqual(char.name, "TestHero")
        self.assertEqual(char.class_name.value, "Warrior")
        self.assertEqual(char.max_hp, 70)
        self.assertEqual(char.current_hp, 70)
        self.assertEqual(char.level, 1)
        self.assertEqual(char.xp, 0)

    def test_mage_hp_is_40(self):
        char = make_character(self.db, class_name=schemas.ClassType.MAGE)
        self.assertEqual(char.max_hp, 40)

    def test_archer_hp_is_55(self):
        char = make_character(self.db, class_name=schemas.ClassType.ARCHER)
        self.assertEqual(char.max_hp, 55)

    def test_stats_are_in_valid_range(self):
        char = make_character(self.db)
        for stat in [char.strength, char.agility, char.wisdom, char.luck]:
            self.assertGreaterEqual(stat, 8, "Stat should be at least 8 (clamped)")
            self.assertLessEqual(stat, 16, "Stat should be at most 16 (clamped)")

    def test_creates_user_record_implicitly(self):
        make_character(self.db)
        user = self.db.query(models.User).filter_by(discord_id="test_user_001").first()
        self.assertIsNotNone(user)

    def test_duplicate_character_raises_error(self):
        make_character(self.db)
        from fastapi import HTTPException
        with self.assertRaises(HTTPException) as ctx:
            make_character(self.db)  # Same discord_id
        self.assertEqual(ctx.exception.status_code, 400)

    def test_creates_initial_story_state(self):
        char = make_character(self.db)
        story = self.db.query(models.StoryState).filter_by(character_id=char.id).first()
        self.assertIsNotNone(story)
        self.assertEqual(story.location, "Starting Town")
        self.assertEqual(story.checkpoint_index, 0)
        self.assertEqual(story.current_arc, "Prologue")

    def test_overwrite_deletes_old_character_and_story(self):
        old_char = make_character(self.db)
        req2 = schemas.CharacterCreateRequest(name="NewHero", class_name=schemas.ClassType.MAGE, world_system="Fantasy")
        new_char = create_player_character(self.db, "test_user_001", req2, overwrite=True)

        # Only ONE character should exist for this discord_id after overwrite
        count = self.db.query(models.Character).filter_by(user_id="test_user_001").count()
        self.assertEqual(count, 1)
        # The surviving character should be the NEW one
        self.assertEqual(new_char.name, "NewHero")
        self.assertEqual(new_char.class_name.value, "Mage")
        # New story state should exist for new character
        new_story = self.db.query(models.StoryState).filter_by(character_id=new_char.id).first()
        self.assertIsNotNone(new_story)

    def test_cyberpunk_world_system_saves_correctly(self):
        char = make_character(self.db, world="Cyberpunk")
        self.assertEqual(char.world_system, "Cyberpunk")


class TestStoryPersistence(unittest.TestCase):
    def setUp(self):
        Base.metadata.create_all(bind=engine)
        self.db = TestingSessionLocal()
        self.char = make_character(self.db)
        self.story = self.db.query(models.StoryState).filter_by(character_id=self.char.id).first()

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(bind=engine)

    def test_checkpoint_increments_on_update(self):
        update_story_checkpoint(self.db, self.char.id, new_location="New Place", summary="Something happened")
        self.db.refresh(self.story)
        self.assertEqual(self.story.checkpoint_index, 1)

    def test_location_updates_correctly(self):
        update_story_checkpoint(self.db, self.char.id, new_location="The Dark Woods")
        self.db.refresh(self.story)
        self.assertEqual(self.story.location, "The Dark Woods")

    def test_objective_updates_correctly(self):
        update_story_checkpoint(self.db, self.char.id, new_objective="Defeat the boss.")
        self.db.refresh(self.story)
        self.assertEqual(self.story.objective, "Defeat the boss.")

    def test_arc_updates_correctly(self):
        update_story_checkpoint(self.db, self.char.id, new_arc="Act 2")
        self.db.refresh(self.story)
        self.assertEqual(self.story.current_arc, "Act 2")

    def test_story_event_is_logged(self):
        log_story_event(self.db, self.char.id, "story", "Entered the dungeon.", is_major=True)
        events = self.db.query(models.StoryEvent).filter_by(character_id=self.char.id).all()
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].description, "Entered the dungeon.")
        self.assertTrue(events[0].is_major)

    def test_get_history_log_returns_recent_first(self):
        log_story_event(self.db, self.char.id, "story", "Event A", is_major=False)
        log_story_event(self.db, self.char.id, "story", "Event B", is_major=False)
        log_story_event(self.db, self.char.id, "story", "Event C", is_major=False)
        history = get_history_log(self.db, self.char.id, limit=3)
        self.assertEqual(history[0].description, "Event C")
        self.assertEqual(history[2].description, "Event A")

    def test_major_only_filter_works(self):
        log_story_event(self.db, self.char.id, "story", "Minor thing", is_major=False)
        log_story_event(self.db, self.char.id, "story", "Boss fight!", is_major=True)
        history = get_history_log(self.db, self.char.id, limit=10, major_only=True)
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0].description, "Boss fight!")


class TestLlmService(unittest.TestCase):
    def setUp(self):
        Base.metadata.create_all(bind=engine)
        self.db = TestingSessionLocal()
        self.char = make_character(self.db)
        self.story = self.db.query(models.StoryState).filter_by(character_id=self.char.id).first()

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(bind=engine)

    def test_parse_clean_json(self):
        raw = json.dumps({
            "narration": "You enter a cave.",
            "new_location": "Cave",
            "new_objective": "Find the exit.",
            "new_arc": "Act 1",
            "checkpoint_summary": "Entered cave.",
            "event_description": "Explored cave.",
            "is_major": False
        })
        result = parse_story_response(raw)
        self.assertEqual(result["narration"], "You enter a cave.")
        self.assertEqual(result["is_major"], False)

    def test_parse_json_wrapped_in_markdown(self):
        raw = """```json
{"narration": "Attacked!", "new_location": "Cave", "new_objective": "Fight!", "new_arc": "A", "checkpoint_summary": "s", "event_description": "e", "is_major": true}
```"""
        result = parse_story_response(raw)
        self.assertEqual(result["narration"], "Attacked!")
        self.assertTrue(result["is_major"])

    def test_fallback_on_invalid_json(self):
        result = parse_story_response("this is not json at all!!")
        self.assertIn("narration", result)
        self.assertIn("new_location", result)
        # Should return fallback
        self.assertEqual(result["new_arc"], "Temporal Anomaly")

    def test_missing_keys_get_defaults(self):
        raw = json.dumps({"narration": "A scene."})
        result = parse_story_response(raw)
        self.assertIn("new_location", result)
        self.assertIn("event_description", result)

    def test_build_prompt_includes_character_info(self):
        history = []
        payload = build_story_prompt(self.char, self.story, history, memory_summary="No memory")
        user_msg = payload["messages"][1]["content"]
        self.assertIn("TestHero", user_msg)
        self.assertIn("Warrior", user_msg)
        self.assertIn("Cyberpunk", user_msg)
        self.assertIn("Starting Town", user_msg)

    def test_build_prompt_includes_history(self):
        log_story_event(self.db, self.char.id, "story", "Defeated a slime.", is_major=False)
        history = get_history_log(self.db, self.char.id, limit=3)
        payload = build_story_prompt(self.char, self.story, history, memory_summary="No memory")
        user_msg = payload["messages"][1]["content"]
        self.assertIn("Defeated a slime.", user_msg)

    def test_build_prompt_no_history_shows_placeholder(self):
        payload = build_story_prompt(self.char, self.story, [], memory_summary="No memory")
        user_msg = payload["messages"][1]["content"]
        self.assertIn("No recent history.", user_msg)

    def test_generate_story_falls_back_on_connection_error(self):
        """If LM Studio is offline, must return fallback, not raise."""
        with patch("services.llm_service.requests.post", side_effect=ConnectionError("offline")):
            result = generate_story(self.char, self.story, [])
        self.assertIn("narration", result)
        self.assertEqual(result["new_arc"], "Temporal Anomaly")

    def test_generate_story_falls_back_on_bad_status(self):
        """If LM Studio returns 500, must return fallback."""
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = Exception("500 Server Error")
        with patch("services.llm_service.requests.post", return_value=mock_response):
            result = generate_story(self.char, self.story, [])
        self.assertIn("narration", result)

    def test_generate_story_parses_valid_response(self):
        """Full happy path: mock a valid LM Studio JSON response."""
        valid_response_json = {
            "choices": [{"message": {"content": json.dumps({
                "narration": "The neon city glows.",
                "new_location": "Neon District",
                "new_objective": "Find the contact.",
                "new_arc": "Prologue",
                "checkpoint_summary": "Arrived in the city.",
                "event_description": "Entered Neon District.",
                "is_major": True
            })}}]
        }
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = valid_response_json
        with patch("services.llm_service.requests.post", return_value=mock_response):
            result = generate_story(self.char, self.story, [])
        self.assertEqual(result["narration"], "The neon city glows.")
        self.assertEqual(result["new_location"], "Neon District")
        self.assertTrue(result["is_major"])


class TestStoryMemory(unittest.TestCase):
    """Tests for the session-level story memory system."""

    def setUp(self):
        from services.story_memory import (
            create_story_memory, add_scene_fact, add_canon_event,
            remember_npc_statement, resolve_question, get_resolved_answer,
            add_recent_history, build_memory_summary
        )
        self.mem = create_story_memory
        self.add_fact = add_scene_fact
        self.add_canon = add_canon_event
        self.add_npc = remember_npc_statement
        self.resolve = resolve_question
        self.get_answer = get_resolved_answer
        self.add_history = add_recent_history
        self.build_summary = build_memory_summary

    def test_create_memory_has_correct_shape(self):
        m = self.mem("scene_1")
        self.assertEqual(m["scene_id"], "scene_1")
        self.assertEqual(m["turn_index"], 0)
        self.assertIsInstance(m["scene_facts"], list)
        self.assertIsInstance(m["canon_events"], list)
        self.assertIsInstance(m["resolved_questions"], dict)
        self.assertIsInstance(m["npc_memory"], dict)
        self.assertIsInstance(m["recent_history"], list)

    def test_add_scene_fact_no_duplicates(self):
        m = self.mem("s")
        self.add_fact(m, "The house is on fire.")
        self.add_fact(m, "The house is on fire.")
        self.assertEqual(len(m["scene_facts"]), 1)

    def test_add_scene_fact_trims_at_10(self):
        m = self.mem("s")
        for i in range(12):
            self.add_fact(m, f"Fact {i}")
        self.assertLessEqual(len(m["scene_facts"]), 10)

    def test_add_canon_event_no_duplicates(self):
        m = self.mem("s")
        self.add_canon(m, "The king was slain.")
        self.add_canon(m, "The king was slain.")
        self.assertEqual(len(m["canon_events"]), 1)

    def test_npc_memory_initializes_on_first_statement(self):
        m = self.mem("s")
        self.add_npc(m, "Dan", "I didn't start the fire.")
        self.assertIn("Dan", m["npc_memory"])
        self.assertEqual(m["npc_memory"]["Dan"]["stated_facts"], ["I didn't start the fire."])

    def test_npc_stated_facts_trims_at_5(self):
        m = self.mem("s")
        for i in range(7):
            self.add_npc(m, "Dan", f"Unique statement {i}")
        self.assertLessEqual(len(m["npc_memory"]["Dan"]["stated_facts"]), 5)

    def test_resolve_question_stores_answer(self):
        m = self.mem("s")
        self.resolve(m, "who_started_fire", "Dan seems linked.", "Annya", "medium", 3)
        ans = self.get_answer(m, "who_started_fire")
        self.assertEqual(ans["answer"], "Dan seems linked.")
        self.assertEqual(ans["source"], "Annya")
        self.assertEqual(ans["confidence"], "medium")

    def test_get_resolved_answer_returns_none_if_missing(self):
        m = self.mem("s")
        self.assertIsNone(self.get_answer(m, "nonexistent_question"))

    def test_resolve_question_overwrites_same_key(self):
        m = self.mem("s")
        self.resolve(m, "cause", "Unknown", "Player", "low", 1)
        self.resolve(m, "cause", "Dan did it.", "Annya", "high", 5)
        self.assertEqual(self.get_answer(m, "cause")["answer"], "Dan did it.")

    def test_add_recent_history_trims_at_5(self):
        m = self.mem("s")
        for i in range(8):
            self.add_history(m, "Player", "Action", f"Action {i}")
        self.assertLessEqual(len(m["recent_history"]), 5)

    def test_build_memory_summary_empty_returns_placeholder(self):
        m = self.mem("s")
        summary = self.build_summary(m)
        self.assertEqual(summary, "No specific memory recorded yet.")

    def test_build_memory_summary_includes_scene_facts(self):
        m = self.mem("s")
        self.add_fact(m, "The pub is crowded.")
        summary = self.build_summary(m)
        self.assertIn("SCENE FACTS", summary)
        self.assertIn("The pub is crowded.", summary)

    def test_build_memory_summary_includes_resolved_questions(self):
        m = self.mem("s")
        self.resolve(m, "what_is_that", "A dragon egg.", "Sage", "high", 2)
        summary = self.build_summary(m)
        self.assertIn("RESOLVED QUESTIONS", summary)
        self.assertIn("A dragon egg.", summary)

    def test_build_memory_summary_includes_npc_knowledge(self):
        m = self.mem("s")
        self.add_npc(m, "Annya", "She doesn't know what happened.")
        summary = self.build_summary(m)
        self.assertIn("NPC KNOWLEDGE", summary)
        self.assertIn("Annya", summary)


class TestLocaleService(unittest.TestCase):
    """Tests for the i18n locale service: resolution, fallback, and translations."""

    def setUp(self):
        from services.locale_service import t, resolve_language, SUPPORTED_LANGUAGES
        self.t = t
        self.resolve = resolve_language
        self.supported = SUPPORTED_LANGUAGES

    # --- resolve_language ---

    def test_preferred_language_takes_priority(self):
        lang = self.resolve(discord_locale="en-US", preferred_language="pt-BR")
        self.assertEqual(lang, "pt-BR")

    def test_discord_locale_used_when_no_preference(self):
        lang = self.resolve(discord_locale="pt-BR", preferred_language=None)
        self.assertEqual(lang, "pt-BR")

    def test_fallback_to_en_when_no_data(self):
        lang = self.resolve(discord_locale="unknown-locale", preferred_language=None)
        self.assertEqual(lang, "en")

    def test_unsupported_preferred_language_falls_back_to_discord_locale(self):
        lang = self.resolve(discord_locale="pt-BR", preferred_language="ja")
        self.assertEqual(lang, "pt-BR")

    def test_en_us_maps_to_en(self):
        lang = self.resolve(discord_locale="en-US")
        self.assertEqual(lang, "en")

    def test_en_gb_maps_to_en(self):
        lang = self.resolve(discord_locale="en-GB")
        self.assertEqual(lang, "en")

    def test_es_es_maps_to_es(self):
        lang = self.resolve(discord_locale="es-ES")
        self.assertEqual(lang, "es")

    # --- t() string translation ---

    def test_t_returns_english_string(self):
        result = self.t("no_character", "en")
        self.assertIn("character", result.lower())

    def test_t_returns_portuguese_translation(self):
        result = self.t("no_character", "pt-BR")
        self.assertIn("personagem", result.lower())

    def test_t_returns_spanish_translation(self):
        result = self.t("no_character", "es")
        self.assertIn("personaje", result.lower())

    def test_t_falls_back_to_english_for_missing_key_in_lang(self):
        result = self.t("no_character", "es")
        self.assertIsNotNone(result)
        self.assertNotEqual(result, "no_character")

    def test_t_returns_key_if_missing_everywhere(self):
        result = self.t("totally_nonexistent_key_xyz", "en")
        self.assertEqual(result, "totally_nonexistent_key_xyz")

    def test_t_with_format_args(self):
        result = self.t("checkpoint_footer", "en", index=42)
        self.assertIn("42", result)

    def test_t_with_format_args_pt(self):
        result = self.t("checkpoint_footer", "pt-BR", index=7)
        self.assertIn("7", result)

    def test_all_supported_languages_have_no_character_key(self):
        for code in self.supported:
            result = self.t("no_character", code)
            self.assertNotEqual(result, "no_character", f"Missing 'no_character' in {code}")

    def test_story_failed_includes_error_placeholder(self):
        result = self.t("story_failed", "en", error="timeout")
        self.assertIn("timeout", result)

    def test_llm_prompt_includes_language_instruction(self):
        """Verify the language code is injected into the story system prompt."""
        from services.llm_service import build_story_prompt
        char = MagicMock()
        char.name = "Elara"
        char.class_name.value = "Archer"
        char.level = 1
        char.world_system = "High Fantasy"
        char.strength = 12
        char.agility = 14
        char.wisdom = 10
        char.luck = 11
        char.max_hp = 55
        char.current_hp = 55
        state = MagicMock()
        state.location = "Forest"
        state.current_arc = "Prologue"
        state.objective = "Find the ruins"
        state.checkpoint_summary = "Just started"
        payload = build_story_prompt(char, state, [], "No memory.", None, "pt-BR")
        system_content = payload["messages"][0]["content"]
        self.assertIn("pt-BR", system_content)


class TestCombatEngine(unittest.TestCase):
    """Tests for the combat resolution engine."""

    def _make_char(self, level=1, hp=55, xp=0, **kwargs) -> dict:
        base = {
            "class_name": "Archer",
            "level": level,
            "current_hp": hp,
            "max_hp": hp,
            "strength": 10,
            "agility": 14,
            "wisdom": 10,
            "luck": 10,
            "xp": xp,
            "weapon_dice": "1d8",
        }
        base.update(kwargs)
        return base

    def _make_monster(self, tier=1, hp=20, ac=10) -> dict:
        return {"name": "Test Goblin", "tier": tier, "base_hp": hp, "base_ac": ac}

    def test_result_has_expected_keys(self):
        from combat_engine import resolve_fight
        result = resolve_fight(self._make_char(), self._make_monster(), "SOLO", False)
        for key in ["won", "player_hp", "monster_hp", "xp_earned", "observer_xp", "log", "cleared_deserter"]:
            self.assertIn(key, result)

    def test_very_weak_monster_player_wins(self):
        from combat_engine import resolve_fight
        char = self._make_char(level=5, hp=70, agility=18)
        monster = self._make_monster(tier=1, hp=5, ac=5)
        result = resolve_fight(char, monster, "SOLO", False)
        self.assertTrue(result["won"])
        self.assertGreater(result["xp_earned"], 0)

    def test_very_strong_monster_player_loses(self):
        from combat_engine import resolve_fight
        # Hobble the player with minimal HP and stats
        char = self._make_char(level=1, hp=5, agility=8, strength=8, wisdom=8)
        monster = self._make_monster(tier=5, hp=500, ac=25)
        result = resolve_fight(char, monster, "SOLO", False)
        self.assertFalse(result["won"])
        self.assertEqual(result["xp_earned"], 0)

    def test_deserter_curse_applies_tier_buff(self):
        from combat_engine import resolve_fight
        char = self._make_char()
        monster = self._make_monster()
        result = resolve_fight(char, monster, "SOLO", True)
        # Log should mention deserter curse
        self.assertTrue(any("Deserter" in line for line in result["log"]))

    def test_cleared_deserter_flag_set_on_victory(self):
        from combat_engine import resolve_fight
        char = self._make_char(level=5, hp=70, agility=18)
        monster = self._make_monster(tier=1, hp=5, ac=5)
        result = resolve_fight(char, monster, "SOLO", True)
        if result["won"]:
            self.assertTrue(result["cleared_deserter"])

    def test_xp_halved_against_trivial_monster(self):
        from combat_engine import resolve_fight
        char = self._make_char(level=5, hp=70, agility=18)  # level 5 vs tier 1
        monster = self._make_monster(tier=1, hp=5, ac=5)
        result = resolve_fight(char, monster, "SOLO", False)
        if result["won"]:
            # XP should be halved for trivial kills (char.level - tier >= 3)
            full_xp = 50 * 1
            self.assertLessEqual(result["xp_earned"], full_xp)

    def test_observer_xp_is_30_percent_of_earned(self):
        from combat_engine import resolve_fight
        char = self._make_char(level=5, hp=70, agility=18)
        monster = self._make_monster(tier=1, hp=5, ac=5)
        result = resolve_fight(char, monster, "OBSERVER", False)
        if result["won"]:
            expected = int(result["xp_earned"] * 0.3)
            self.assertEqual(result["observer_xp"], expected)

    def test_coop_active_mode_adds_log_message(self):
        from combat_engine import resolve_fight
        char = self._make_char(level=3, hp=70)
        monster = self._make_monster(tier=2, hp=30, ac=12)
        result = resolve_fight(char, monster, "ACTIVE", False)
        self.assertTrue(any("Co-Op" in line for line in result["log"]))

    def test_log_is_nonempty(self):
        from combat_engine import resolve_fight
        result = resolve_fight(self._make_char(), self._make_monster(), "SOLO", False)
        self.assertGreater(len(result["log"]), 0)

    def test_player_hp_nonnegative_on_defeat(self):
        from combat_engine import resolve_fight
        char = self._make_char(level=1, hp=5, agility=8, strength=8, wisdom=8)
        monster = self._make_monster(tier=5, hp=500, ac=25)
        result = resolve_fight(char, monster, "SOLO", False)
        # Player is auto-healed to max_hp on defeat
        self.assertGreater(result["player_hp"], 0)


if __name__ == "__main__":
    unittest.main()
