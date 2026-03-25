import os
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# Use SQLite for simple setup & local testing, easy to swap to PostgreSQL later via env URL
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./monster_rpg.db")

engine = create_engine(
    DATABASE_URL, 
    # Check same thread is required for SQLite in FastAPI as it can be accessed across threads
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    """Dependency for FastAPI routers to get a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
