import os
import pytest
from fastapi.testclient import TestClient
from app.config import AppSettings
from app.db import Base
from app.main import create_app
from tests.make_samples import build


@pytest.fixture(scope="session")
def samples(tmp_path_factory):
    d = tmp_path_factory.mktemp("samples")
    build(d)
    return d


@pytest.fixture()
def make_client(tmp_path):
    made = []

    def _make(**over):
        url = os.environ.get("TEST_DATABASE_URL") or f"sqlite:///{tmp_path}/t.db"
        s = AppSettings(database_url=url, data_dir=str(tmp_path / "data"), sync_processing=True, **over)
        app = create_app(s, create_tables=False)
        eng = app.state.ctx.sf.kw["bind"]
        Base.metadata.drop_all(eng)
        Base.metadata.create_all(eng)
        made.append(eng)
        c = TestClient(app)
        c.app_ = app
        return c

    yield _make
    for e in made:
        e.dispose()
