import os
import json
import requests
from typing import Dict, Any, List

def build_story_prompt(character: Any, current_state: Any, history_log: List[Any], memory_summary: str, custom_action: str = None, language: str = "en") -> Dict[str, Any]:
    system_instruction = (
        "Your Role: You are an AI Game Master running a persistent text RPG. Continue the story based on the current scene, player action, and memory.\n"
        "RULES:\n"
        "1. Respect Memory (CRITICAL): All memory is canon. Do NOT contradict previous facts. If a question was already answered, reuse that answer. Do NOT invent new explanations for the same question.\n"
        "2. Player Action = Attempt: Treat player input as an attempt, not a guaranteed result. Decide outcome based on logic and scene.\n"
        "3. Keep Consistency: If something was uncertain before, keep it uncertain. Only change facts if the story explicitly reveals new info.\n"
        "4. Stay Immersive: Write in a modern fantasy narrative style. Include character reactions, vivid sensory details, and atmospheric descriptions typical of contemporary fantasy literature.\n"
        "5. Focus on the Player: Do NOT invent random companion NPCs (like 'Lucas' or 'Kaelen') unless explicitly part of the story.\n"
        "OUTPUT FORMAT: Write ONLY the next scene. Do NOT explain rules. Do NOT break immersion. DO NOT write a 'Thinking Process'.\n"
        f"LANGUAGE: Respond ONLY in this language code: {language}. Do NOT switch languages. Do NOT translate proper nouns or character names.\n"
        "You MUST return ONLY valid JSON matching this exact structure:\n"
        "{\n"
        '  "narration": "[The story text for this step]",\n'
        '  "new_location": "[Updated or Same Location]",\n'
        '  "new_objective": "[Updated or Same Objective]",\n'
        '  "new_arc": "[Updated or Same Arc Name]",\n'
        '  "checkpoint_summary": "[A short 1-sentence summary of what just happened]",\n'
        '  "event_description": "[1 short phrase describing the most important action]",\n'
        '  "is_major": false,\n'
        '  "memory_updates": {\n'
        '     "new_scene_facts": ["Fact 1", "Fact 2"],\n'
        '     "new_canon_events": [],\n'
        '     "new_npc_statements": [{"npc_name": "Dan", "statement": "I didn\'t do it!"}],\n'
        '     "new_resolved_questions": [{"key": "what_happened", "answer": "Fire started.", "source": "Dan", "confidence": "low"}]\n'
        '  }\n'
        "}\n"
    )
    
    # Construct sequential history context securely
    history_strings = []
    for evt in reversed(history_log):
        history_strings.append(f"- {evt.description}")
    
    recent_history = "\n".join(history_strings) if history_strings else "No recent history."
    action_text = f"Player's Declared Action: {custom_action}\n" if custom_action else "Player's Declared Action: Continue the story naturally.\n"
    
    user_context = (
        f"World: {character.world_system}\n"
        f"Character: {character.name} the {character.class_name.value} (Level {character.level})\n"
        f"Current Arc: {current_state.current_arc}\n"
        f"Location: {current_state.location}\n"
        f"Objective: {current_state.objective}\n\n"
        f"--- MEMORY CONTEXT ---\n{memory_summary}\n\n"
        f"--- RECENT HISTORY ---\n{recent_history}\n\n"
        f"--- CURRENT ACTION ---\n{action_text}\n"
        "Write the next sequence as the Game Master and return ONLY the JSON dictionary."
    )
    
    payload = {
        "model": os.getenv("LM_STUDIO_MODEL", "qwen/qwen3.5-9b"),
        "messages": [
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": user_context}
        ],
        "temperature": 0.7,
        "max_tokens": 2048
    }
    return payload

def normalize_custom_action(raw_input: str, language: str = "en") -> str:
    """Sanitizes freeform player input without an LLM call.

    WHY no LLM: Small models (Nemotron 4B, etc.) cannot reliably produce
    JSON-only output — they use all tokens for reasoning and truncate before
    the JSON object. The story LLM already has a rule to prevent god-moding,
    so this function only needs to clean the surface-level input.

    Strategy: strip explicit outcome-forcing phrases, truncate to 300 chars,
    capitalize, and return. The Game Master LLM handles the rest.
    """
    import re

    text = raw_input.strip()

    # Remove explicit "and he/she/it dies/wins/loses" forced outcome suffixes
    outcome_patterns = [
        r"\s+and\s+(he|she|it|they)\s+(dies?|is killed|falls?|lose?s?|win?s?)\b.*$",
        r"\s+e\s+(ele|ela|eles|elas)\s+(morre[m]?|cai[u]?|perde[m]?|vence[m]?)\b.*$",
        r"\s+y\s+(él|ella|ellos|ellas)\s+(muere[n]?|cae[n]?|pierde[n]?|gana[n]?)\b.*$",
        r",?\s+killing\s+(him|her|it|them)\b.*$",
    ]
    for pattern in outcome_patterns:
        text = re.sub(pattern, "", text, flags=re.IGNORECASE)

    # Truncate to keep prompts clean
    text = text[:300].strip()

    if not text:
        return raw_input[:300].strip()

    # Capitalize first letter
    return text[0].upper() + text[1:]



def fallback_story_response() -> Dict[str, Any]:
    """Safe fallback if the LLM crashes or goes offline."""
    return {
        "narration": "A thick, unnatural silence falls over the world. Your connection to the narrative thread has temporarily faded, leaving you to gather your thoughts in the quiet.",
        "new_location": "The Silent Veil",
        "new_objective": "Wait for the narrative fabric to mend.",
        "new_arc": "Temporal Anomaly",
        "checkpoint_summary": "The world was suddenly paused by an unknown force.",
        "event_description": "Experienced a temporal disconnection.",
        "is_major": False
    }


def generate_rest_narrative(character: Any, story_state: Any, language: str = "en") -> str:
    """Generates a short, immersive resting scene in the player's language.
    
    The scene describes the character finding rest and recovering HP.
    Falls back to a templated description if the LLM is unavailable.
    """
    system_instruction = (
        "You are a narrative writer for a text RPG. "
        "Write a SHORT, immersive scene (2-4 sentences) where the character rests and recovers. "
        "Make it feel real — reference the location, the quest, or recent events if possible. "
        "The scene MUST describe the character finding a place to rest and recovering health. "
        "Do NOT invent random companions or NPC names (like 'Lucas' or 'Jax'). Focus solely on the player character. "
        f"Respond ONLY with a valid JSON format in language code: {language}. "
        "{\n"
        '  "scene": "The actual scene text here"\n'
        "}\n"
    )
    context = (
        f"Character: {character.name} the {character.class_name.value}\n"
        f"Current location: {story_state.location}\n"
        f"Current arc: {story_state.current_arc}\n"
        f"Objective: {story_state.objective}\n"
        "Output the JSON object now:"
    )
    payload = {
        "model": os.getenv("LM_STUDIO_MODEL", "qwen/qwen3.5-9b"),
        "messages": [
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": context}
        ],
        "temperature": 0.8,
        "max_tokens": 180,
    }
    base_url = os.getenv("LM_STUDIO_URL", "http://localhost:1234/v1")
    try:
        response = requests.post(
            f"{base_url}/chat/completions",
            headers={"Content-Type": "application/json"},
            data=json.dumps(payload),
            timeout=30
        )
        response.raise_for_status()
        raw = response.json()["choices"][0]["message"]["content"].strip()
        
        # Clean <think> tags natively used by models
        if "</think>" in raw:
            raw = raw.split("</think>")[-1].strip()
            
        # Isolate JSON block if it wrote markdown
        if "```json" in raw:
            parts = raw.split("```json")
            raw = parts[-1].split("```")[0].strip()
        elif "```" in raw:
            parts = raw.split("```")
            if len(parts) >= 3:
                raw = parts[-2].strip()
                
        # Fallback to brace extraction
        start_idx = raw.find("{")
        end_idx = raw.rfind("}")
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            raw = raw[start_idx:end_idx+1]
            
        data = json.loads(raw)
        scene_text = data.get("scene", "").strip()

        # Catch if the LLM echo's the system prompt inside the string block
        bad_phrases = ["we need to write", "let's produce", "let's write", "let's craft", "no json", "write a short, immersive"]
        if any(phrase in scene_text.lower() for phrase in bad_phrases):
            return _rest_fallback(character, story_state, language)

        return scene_text if scene_text else _rest_fallback(character, story_state, language)

    except Exception as e:
        print(f"Rest Narrative Error: {e}")
        return _rest_fallback(character, story_state, language)


def _rest_fallback(character: Any, story_state: Any, language: str) -> str:
    """Template-based rest narrative when LLM is unavailable."""
    templates = {
        "en": f"{character.name} found a sheltered spot near {story_state.location} and rested. The wounds slowly closed as fatigue faded away, strength returning with each passing hour.",
        "pt-BR": f"{character.name} encontrou um lugar abrigado perto de {story_state.location} e descansou. As feridas fecharam lentamente enquanto o cansaço desaparecia, a força retornando a cada hora que passava.",
        "es": f"{character.name} encontró un lugar resguardado cerca de {story_state.location} y descansó. Las heridas se cerraron lentamente mientras la fatiga desaparecía, la fuerza regresando con cada hora que pasaba.",
    }
    return templates.get(language, templates["en"])


def parse_story_response(response_text: str) -> Dict[str, Any]:
    """Parses LLM response payload safely ensuring standard JSON."""
    text = response_text.strip()
    
    # Clean <think> tags natively used by Qwen/DeepSeek
    if "</think>" in text:
        text = text.split("</think>")[-1].strip()
        
    # Isolate markdown json blocks if present
    if "```json" in text:
        parts = text.split("```json")
        text = parts[-1].split("```")[0].strip()
    elif "```" in text:
        parts = text.split("```")
        # In odd number of splits, the middle is usually the code block
        if len(parts) >= 3:
            text = parts[-2].strip()
            
    # Fallback to brace extraction for the final JSON block just in case
    start_idx = text.find("{")
    end_idx = text.rfind("}")
    if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
        text = text[start_idx:end_idx+1]
        
    try:
        data = json.loads(text)
        
        # Validations defaults
        required_keys = ["narration", "new_location", "new_objective", "checkpoint_summary", "event_description"]
        for key in required_keys:
            if key not in data:
                data[key] = f"[{key.capitalize()} Missing]"
                
        data["new_arc"] = data.get("new_arc", "Unknown")
        data["is_major"] = bool(data.get("is_major", False))
        data["memory_updates"] = data.get("memory_updates", {})
            
        return data
        
    except json.JSONDecodeError as e:
        print(f"LLM json parsing error: {e}. Raw response: {text}")
        return fallback_story_response()

def fallback_character_response() -> Dict[str, str]:
    import random
    names = ["Kaelen", "Elara", "Jax", "Torin"]
    worlds = ["Cyberpunk", "High Fantasy", "Post-Apocalyptic", "Sci-Fi"]
    classes = ["Mage", "Warrior", "Archer"]
    return {
        "name": random.choice(names),
        "class_name": random.choice(classes),
        "world_system": random.choice(worlds)
    }

def generate_random_character() -> Dict[str, str]:
    """Generates a random character concept from LM Studio."""
    system_instruction = (
        "You are an AI Game Master. Invent a highly unique RPG character concept. "
        "DO NOT write a 'Thinking Process' or any explanations. Output raw JSON immediately.\n"
        "You MUST return ONLY valid JSON matching this exact structure and nothing else:\n"
        "{\n"
        '  "name": "A creative fictional name",\n'
        '  "class_name": "Must be exactly Mage, Warrior, or Archer",\n'
        '  "world_system": "A creative universe setting (e.g., Cyberpunk, Dark Fantasy)"\n'
        "}\n"
    )
    payload = {
        "model": os.getenv("LM_STUDIO_MODEL", "qwen/qwen3.5-9b"),
        "messages": [
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": "Create a random character."}
        ],
        "temperature": 0.9,
        "max_tokens": 2048
    }
    
    base_url = os.getenv("LM_STUDIO_URL", "http://localhost:1234/v1")
    try:
        response = requests.post(f"{base_url}/chat/completions", headers={"Content-Type": "application/json"}, data=json.dumps(payload), timeout=600)
        response.raise_for_status()
        raw_text = response.json()["choices"][0]["message"]["content"].strip()
        
        # Clean <think> tags natively used by Qwen/DeepSeek
        if "</think>" in raw_text:
            raw_text = raw_text.split("</think>")[-1].strip()
            
        # Isolate markdown json blocks if present
        if "```json" in raw_text:
            parts = raw_text.split("```json")
            raw_text = parts[-1].split("```")[0].strip()
        elif "```" in raw_text:
            parts = raw_text.split("```")
            if len(parts) >= 3:
                raw_text = parts[-2].strip()
                
        # Fallback to brace extraction
        start_idx = raw_text.find("{")
        end_idx = raw_text.rfind("}")
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            raw_text = raw_text[start_idx:end_idx+1]
        
        data = json.loads(raw_text.strip())
        
        # Enforce valid class natively
        if data.get("class_name") not in ["Mage", "Warrior", "Archer"]:
            import random
            data["class_name"] = random.choice(["Mage", "Warrior", "Archer"])
            
        return data
    except Exception as e:
        print(f"LLM Random Gen Error: {e}")
        return fallback_character_response()

def generate_story(character: Any, current_state: Any, history_log: List[Any], memory_summary: str = "", custom_action: str = None, language: str = "en") -> Dict[str, Any]:
    """Main execution function coordinating the HTTP call to LM Studio."""
    base_url = os.getenv("LM_STUDIO_URL", "http://localhost:1234/v1")
    payload = build_story_prompt(character, current_state, history_log, memory_summary, custom_action, language)
    
    try:
        response = requests.post(
            f"{base_url}/chat/completions",
            headers={"Content-Type": "application/json"},
            data=json.dumps(payload),
            timeout=600
        )
        response.raise_for_status()
        
        response_json = response.json()
        raw_text = response_json["choices"][0]["message"]["content"]
        
        return parse_story_response(raw_text)
        
    except Exception as e:
        print(f"LLM Generation connection Error: {e}")
        return fallback_story_response()
