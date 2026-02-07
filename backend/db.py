"""
Database setup (SQLAlchemy)
"""

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./app.db")

# SQLite needs this for multi-thread access (FastAPI + background tasks)
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def init_db() -> None:
    """
    Create tables.
    IMPORTANT: Import models BEFORE create_all so SQLAlchemy registers them.
    """
    import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
