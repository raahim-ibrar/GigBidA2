from logging.config import fileConfig

from alembic import context

from apps.api.database import make_engine
from apps.api.models import Base
from apps.api.settings import Settings

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)
target_metadata = Base.metadata


def run(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    url = Settings().database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
elif config.attributes.get("connection") is not None:
    run(config.attributes["connection"])
else:
    engine = make_engine(Settings().database_url)
    with engine.connect() as connection:
        run(connection)
    engine.dispose()
