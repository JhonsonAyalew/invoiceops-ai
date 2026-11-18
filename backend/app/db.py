from __future__ import annotations

from decimal import Decimal

from sqlalchemy import Numeric, String, create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.types import TypeDecorator


class _DecimalText(TypeDecorator):
    """SQLite has no exact NUMERIC: store Decimal as text there so money is never a float."""

    impl, cache_ok = String, True

    def process_bind_param(self, v, dialect):
        return None if v is None else str(v)

    def process_result_value(self, v, dialect):
        return None if v is None else Decimal(v)


# NUMERIC in PostgreSQL (production); exact text fallback on SQLite (tests/dev only)
Money = Numeric(20, 4).with_variant(_DecimalText(40), "sqlite")


class Base(DeclarativeBase):
    pass


def make_session_factory(url: str):
    kw = {"connect_args": {"check_same_thread": False}} if url.startswith("sqlite") else {"pool_pre_ping": True}
    engine = create_engine(url, **kw)
    return engine, sessionmaker(engine, expire_on_commit=False)
