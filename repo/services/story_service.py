from sqlalchemy.orm import Session
from fastapi import HTTPException
import models
from typing import List

def get_current_story_state(db: Session, character_id: int) -> models.StoryState:
    story = db.query(models.StoryState).filter(models.StoryState.character_id == character_id).first()
    if not story:
        raise HTTPException(status_code=404, detail="Story state not found.")
    return story

def update_story_checkpoint(db: Session, character_id: int, new_arc: str = None, new_location: str = None, new_objective: str = None, summary: str = None) -> models.StoryState:
    story = get_current_story_state(db, character_id)
    
    if new_arc:
        story.current_arc = new_arc
    if new_location:
        story.location = new_location
    if new_objective:
        story.objective = new_objective
    if summary is not None:
        story.checkpoint_summary = summary
        
    story.checkpoint_index += 1
    
    db.commit()
    db.refresh(story)
    return story

def log_story_event(db: Session, character_id: int, event_type: str, description: str, is_major: bool = False) -> models.StoryEvent:
    event = models.StoryEvent(
        character_id=character_id,
        event_type=event_type,
        description=description,
        is_major=is_major
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event

def get_history_log(db: Session, character_id: int, limit: int = 5, major_only: bool = False) -> List[models.StoryEvent]:
    query = db.query(models.StoryEvent).filter(models.StoryEvent.character_id == character_id)
    if major_only:
        query = query.filter(models.StoryEvent.is_major.is_(True))
    
    # Return chronologically descending (latest 5)
    return query.order_by(models.StoryEvent.created_at.desc(), models.StoryEvent.id.desc()).limit(limit).all()
