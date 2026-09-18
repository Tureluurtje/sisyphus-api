from typing import Generator

from api.config import DATABASE_URL

from contextlib import contextmanager
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker, declarative_base

# Enable pool_pre_ping to avoid using stale/closed connections from the pool.
# pool_recycle helps reclaim long-lived connections that some servers close.
engine = create_engine(url=DATABASE_URL, pool_pre_ping=True, pool_recycle=3600)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


@contextmanager
def get_db_session():
    """Context manager for database sessions that ensures cleanup."""
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def get_db_session_dependency() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
