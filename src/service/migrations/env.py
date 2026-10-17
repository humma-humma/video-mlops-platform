from alembic import context

from src.service.db import Base, engine
from src.service import models  # noqa: F401

config = context.config

def migrate(connection):
    context.configure(connection=connection, target_metadata=Base.metadata)
    with context.begin_transaction():
        context.run_migrations()

if context.is_offline_mode():
    raise RuntimeError("Use an online connection for legacy schema adoption")
elif config.attributes.get("connection") is not None:
    migrate(config.attributes["connection"])
else:
    with engine.connect() as connection:
        migrate(connection)
