import os
import subprocess
import sys
from pathlib import Path
from sqlalchemy import create_engine, inspect

BACKEND = Path(__file__).resolve().parents[1]
EXPECTED = {"jobs", "documents", "invoices", "line_items", "corrections", "duplicate_candidates", "export_files", "app_settings"}


def _alembic(url, *args):
    env = {**os.environ, "DATABASE_URL": url}
    r = subprocess.run([sys.executable, "-m", "alembic", *args], cwd=BACKEND, env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_migration_upgrade_check_downgrade(tmp_path):
    url = os.environ.get("TEST_DATABASE_URL") or f"sqlite:///{tmp_path}/m.db"
    eng = create_engine(url)
    from app.db import Base

    Base.metadata.drop_all(eng)
    with eng.begin() as c:
        c.exec_driver_sql("DROP TABLE IF EXISTS alembic_version")
    _alembic(url, "upgrade", "head")
    assert EXPECTED <= set(inspect(eng).get_table_names())
    _alembic(url, "check")  # models and migration agree (no drift)
    if url.startswith("postgresql"):
        col = {c["name"]: c for c in inspect(eng).get_columns("invoices")}["total_amount"]
        assert "NUMERIC" in str(col["type"]).upper()  # exact money type on PostgreSQL
    _alembic(url, "downgrade", "base")
    assert not (EXPECTED & set(inspect(eng).get_table_names()))
    eng.dispose()
