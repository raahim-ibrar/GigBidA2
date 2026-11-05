"""Disposable database/API for browser tests; never use as a deployment entry point."""

import asyncio
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

import uvicorn
from alembic import command
from alembic.config import Config
from sqlalchemy.engine import make_url
from sqlalchemy.schema import CreateSchema, DropSchema

from agent.runtime import process_bid
from apps.api.database import make_engine
from apps.api.main import create_app
from apps.api.settings import Settings
from tests.portfolio_fixtures import portfolio_fixture
from tests.proposal_fixtures import BrowserModels

if __name__ == "__main__":
    work = Path(__file__).resolve().parents[1] / "work"
    work.mkdir(exist_ok=True)
    with TemporaryDirectory(prefix="browser-test-", dir=work) as temporary:
        admin, schema = None, None
        database_url = f"sqlite:///{(Path(temporary) / 'test.sqlite').as_posix()}"
        if postgres := os.getenv("GIGBID_TEST_DATABASE_URL"):
            admin, schema = make_engine(postgres), "gigbid_browser_" + uuid4().hex
            with admin.begin() as connection:
                connection.execute(CreateSchema(schema))
            url = make_url(postgres.replace("postgresql://", "postgresql+psycopg://", 1))
            database_url = url.update_query_dict(
                {"options": f"-csearch_path={schema}"}
            ).render_as_string(hide_password=False)
            (work / "browser-test-schema.txt").write_text(schema, encoding="utf-8")
        settings = Settings(
            database_url=database_url,
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

        tasks = set()

        async def queue_run(tenant, run_id):
            if schema is None:
                return False  # Durable proposal browser tests require Postgres.

            class Reader:
                async def search(self, query, **kwargs):
                    from rag.contracts import PortfolioSearch

                    result = service.search(tenant, PortfolioSearch(query=query, **kwargs))
                    return [hit.evidence for hit in result.items]

                async def read(self, id):
                    return service.evidence(tenant, id)

            def run():
                with asyncio.Runner(loop_factory=asyncio.SelectorEventLoop) as runner:
                    return runner.run(
                        process_bid(
                            engine,
                            settings,
                            tenant,
                            run_id,
                            models_factory=BrowserModels,
                            portfolio_reader=Reader(),
                        )
                    )

            task = asyncio.create_task(asyncio.to_thread(run))
            tasks.add(task)
            task.add_done_callback(tasks.discard)
            return True

        try:
            app = create_app(settings, engine=engine, portfolio_service=service, enqueue=enqueue)
            app.state.enqueue_run = queue_run
            uvicorn.run(
                app,
                host="127.0.0.1",
                port=8000,
            )
        finally:
            service.index.client.close()
            engine.dispose()
            if admin is not None:
                with admin.begin() as connection:
                    connection.execute(DropSchema(schema, cascade=True))
                admin.dispose()
