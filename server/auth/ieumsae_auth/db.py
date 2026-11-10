import importlib
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import DateTime, event
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.types import TypeDecorator

from .config import settings


class Base(DeclarativeBase):
    pass


class UTCDateTime(TypeDecorator):


    impl = DateTime
    cache_ok = True

    def __init__(self, timezone: bool = True):
        super().__init__(timezone=timezone)

    def process_bind_param(self, value: datetime | None, dialect):
        if value is not None and value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        if value is not None and dialect.name == "sqlite":
            value = value.astimezone(timezone.utc).replace(tzinfo=None)
        return value

    def process_result_value(self, value: datetime | None, dialect):
        if value is not None and value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value


def _url():
    url = make_url(settings.database_url)
    if settings.db_password_file:
        url = url.set(password=Path(settings.db_password_file).read_text().strip())
    return url


_u = _url()
if _u.get_backend_name() == "sqlite":

    engine = create_async_engine(_u, hide_parameters=True)

    @event.listens_for(engine.sync_engine, "connect")
    def _sqlite_pragmas(conn, _):
        cur = conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA journal_mode=WAL")
        cur.close()
else:
    engine = create_async_engine(_u, pool_pre_ping=True, pool_size=10, max_overflow=10, hide_parameters=True)

SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session


async def init_db() -> None:

    importlib.import_module(".models", __package__)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
