"""Disposable database/API for browser tests; never use as a deployment entry point."""

from pathlib import Path
from tempfile import TemporaryDirectory

import uvicorn
from alembic import command
from alembic.config import Config

from apps.api.database import make_engine
from apps.api.main import create_app
from apps.api.settings import Settings
from tests.portfolio_fixtures import portfolio_fixture

if __name__ == "__main__":
    work = Path(__file__).resolve().parents[1] / "work"
    work.mkdir(exist_ok=True)
    with TemporaryDirectory(prefix="browser-test-", dir=work) as temporary:
        settings = Settings(
            database_url=f"sqlite:///{(Path(temporary) / 'test.sqlite').as_posix()}",
            web_origin="http://127.0.0.1:3000",
        )
        engine = make_engine(settings.database_url)
        cfg = Config("alembic.ini")
        with engine.begin() as connection:
            cfg.attributes["connection"] = connection
            command.upgrade(cfg, "head")
        service = portfolio_fixture(engine)

        async def enqueue(tenant, document, revision):
            service.index_document(tenant, document)
            return True

        try:
            uvicorn.run(
                create_app(settings, engine=engine, portfolio_service=service, enqueue=enqueue),
                host="127.0.0.1",
                port=8000,
            )
        finally:
            service.index.client.close()
            engine.dispose()
