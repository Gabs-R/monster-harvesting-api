import json
from typing import Dict, Any

def create_story_memory(scene_id: str) -> Dict[str, Any]:
    """Initializes a blank memory block for a new session or scene."""
    return {
        "scene_id": scene_id,
        "turn_index": 0,
        "scene_facts": [],
        "canon_events": [],
        "resolved_questions": {},
        "npc_memory": {},
        "recent_history": []
    }

def add_scene_fact(memory: Dict[str, Any], fact: str):
    if fact not in memory["scene_facts"]:
        memory["scene_facts"].append(fact)
        # Keep trimmed to avoid bloat
        if len(memory["scene_facts"]) > 10:
            memory["scene_facts"].pop(0)

def add_canon_event(memory: Dict[str, Any], event: str):
    if event not in memory["canon_events"]:
        memory["canon_events"].append(event)

def remember_npc_statement(memory: Dict[str, Any], npc_name: str, statement: str):
    if npc_name not in memory["npc_memory"]:
        memory["npc_memory"][npc_name] = {
            "known_facts": [],
            "stated_facts": [],
            "open_questions": [],
            "relationship_state": "Neutral"
        }
    
    npc_data = memory["npc_memory"][npc_name]
    if statement not in npc_data["stated_facts"]:
        npc_data["stated_facts"].append(statement)
        if len(npc_data["stated_facts"]) > 5:
            npc_data["stated_facts"].pop(0)

def resolve_question(memory: Dict[str, Any], question_key: str, answer: str, source: str, confidence: str, turn_index: int):
    memory["resolved_questions"][question_key] = {
        "answer": answer,
        "source": source,
        "confidence": confidence,
        "turn_index": turn_index
    }

def get_resolved_answer(memory: Dict[str, Any], question_key: str) -> Dict[str, Any]:
    return memory["resolved_questions"].get(question_key)

def add_recent_history(memory: Dict[str, Any], speaker: str, type_: str, text: str):
    memory["recent_history"].append({
        "speaker": speaker,
        "type": type_,
        "text": text
    })
    # Keep only the last 5 items to prevent context overflow
    if len(memory["recent_history"]) > 5:
        memory["recent_history"].pop(0)

def build_memory_summary(memory: Dict[str, Any]) -> str:
    """Builds a deterministic summary string to inject into the LLM prompt."""
    summary_blocks = []
    
    if memory.get("scene_facts"):
        lines = "\n".join(f"- {f}" for f in memory["scene_facts"])
        summary_blocks.append(f"SCENE FACTS:\n{lines}")
        
    if memory.get("canon_events"):
        lines = "\n".join(f"- {e}" for e in memory["canon_events"])
        summary_blocks.append(f"CANON EVENTS (Immutable):\n{lines}")
        
    if memory.get("resolved_questions"):
        lines = []
        for k, v in memory["resolved_questions"].items():
            lines.append(f"- {k.replace('_', ' ').capitalize()}? A: {v['answer']} (Source: {v['source']}, Confidence: {v['confidence']})")
        summary_blocks.append(f"RESOLVED QUESTIONS (You MUST reuse these exact answers):\n" + "\n".join(lines))
            
    if memory.get("npc_memory"):
        npc_blocks = []
        for npc, data in memory["npc_memory"].items():
            if data["stated_facts"]:
                npc_blocks.append(f"- {npc} stated: " + " | ".join(data["stated_facts"]))
        if npc_blocks:
            summary_blocks.append("NPC KNOWLEDGE:\n" + "\n".join(npc_blocks))
            
    if memory.get("recent_history"):
        lines = "\n".join(f"- [{h['type']}] {h['speaker']}: {h['text']}" for h in memory["recent_history"])
        summary_blocks.append(f"RECENT HISTORY:\n{lines}")
        
    if not summary_blocks:
        return "No specific memory recorded yet."
        
    return "\n\n".join(summary_blocks)
