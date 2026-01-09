from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import Column, Integer, String, DateTime, Text
from datetime import datetime
import uuid

from .config import get_settings


class Base(DeclarativeBase):
    pass


class APIKey(Base):
    __tablename__ = "api_keys"

    id = Column(Integer, primary_key=True)
    key_hash = Column(String(64), unique=True, nullable=False)
    name = Column(String(100))
    created_at = Column(DateTime, default=datetime.utcnow)
    last_used = Column(DateTime)
    rate_limit = Column(Integer, default=100)


class Style(Base):
    __tablename__ = "styles"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), unique=True, nullable=False)
    filename = Column(String(255), nullable=False)
    uploaded_at = Column(DateTime, default=datetime.utcnow)


class Font(Base):
    __tablename__ = "fonts"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), unique=True, nullable=False)
    filename = Column(String(255), nullable=False)
    uploaded_at = Column(DateTime, default=datetime.utcnow)


class Job(Base):
    __tablename__ = "jobs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    api_key_id = Column(Integer)
    status = Column(String(20))
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime)
    error_log = Column(Text)


# Database engine and session
_engine = None
_session_factory = None


def get_database_url() -> str:
    """Convert postgres:// to postgresql+asyncpg:// for async support."""
    settings = get_settings()
    url = settings.database_url
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


async def init_db():
    """Initialize database connection and create tables."""
    global _engine, _session_factory

    _engine = create_async_engine(get_database_url(), echo=False)
    _session_factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)

    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncSession:
    """Get database session."""
    if _session_factory is None:
        await init_db()
    async with _session_factory() as session:
        yield session


async def close_db():
    """Close database connection."""
    global _engine
    if _engine:
        await _engine.dispose()
