import os
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy.engine import make_url
from sqlalchemy.schema import CreateSchema, DropSchema

from apps.api.database import make_engine
from apps.api.main import create_app
from apps.api.settings import Settings


@pytest.fixture
def account_app(tmp_path):
    admin = None
    schema = None
    database_url = f"sqlite:///{(tmp_path / 'accounts.sqlite').as_posix()}"
    if postgres_url := os.getenv("GIGBID_TEST_DATABASE_URL"):
        # Every test owns a fresh schema; existing application tables are not touched.
        admin = make_engine(postgres_url)
        schema = "gigbid_test_" + uuid4().hex
        with admin.begin() as connection:
            connection.execute(CreateSchema(schema))
        url = make_url(postgres_url.replace("postgresql://", "postgresql+psycopg://", 1))
        database_url = url.update_query_dict(
            {"options": f"-csearch_path={schema}"}
        ).render_as_string(hide_password=False)
    settings = Settings(database_url=database_url)
    engine = make_engine(settings.database_url)
    cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    with engine.begin() as connection:
        cfg.attributes["connection"] = connection
        command.upgrade(cfg, "head")
    app = create_app(settings, engine=engine)
    try:
        yield app
    finally:
        engine.dispose()
        if admin is not None and schema is not None:
            with admin.begin() as connection:
                connection.execute(DropSchema(schema, cascade=True))
            admin.dispose()


@pytest.fixture
def client(account_app):
    with TestClient(account_app) as client:
        yield client
