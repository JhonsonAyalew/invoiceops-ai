from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401  (register tables)
from app.api import router
from app.config import AppSettings, load_dotenv
from app.db import Base, make_session_factory
from app.services.processing import Processor, purge_expired
from app.storage import Storage


@dataclass
class Ctx:
    settings: AppSettings
    sf: sessionmaker
    storage: Storage
    processor: Processor


def create_app(settings: AppSettings | None = None, create_tables: bool | None = None) -> FastAPI:
    if settings is None:
        load_dotenv()
        settings = AppSettings.from_env()
    Path(settings.data_dir).mkdir(parents=True, exist_ok=True)
    engine, sf = make_session_factory(settings.database_url)
    if create_tables or (create_tables is None and settings.database_url.startswith("sqlite")):
        Base.metadata.create_all(engine)  # PostgreSQL uses Alembic: `alembic upgrade head`
    storage = Storage(settings.data_dir)
    app = FastAPI(title="InvoiceOps AI", version="1.0.0")
    app.state.ctx = Ctx(settings, sf, storage, Processor(settings, sf, storage))
    app.add_middleware(CORSMiddleware, allow_origins=list(settings.cors_origins), allow_methods=["*"], allow_headers=["*"])
    app.include_router(router)
    if settings.retention_days > 0:
        try:
            with sf() as s:
                purge_expired(s, storage, settings.retention_days)
        except SQLAlchemyError:
            pass  # schema not migrated yet; purge runs on the next start
    dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
    if dist.is_dir():
        app.mount("/", StaticFiles(directory=dist, html=True), name="ui")
    return app


def app_factory() -> FastAPI:  # uvicorn app.main:app_factory --factory
    return create_app()
