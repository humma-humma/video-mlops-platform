from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings


class Base(DeclarativeBase):
    pass


engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def init_db() -> None:
    from pathlib import Path
    from alembic import command
    from alembic.config import Config

    cfg = Config()
    cfg.set_main_option("script_location", str(Path(__file__).parent / "migrations"))
    with engine.begin() as connection:
        if connection.dialect.name == "postgresql":
            # Serialize startup migrations across API replicas and the init job.
            connection.execute(text("SELECT pg_advisory_xact_lock(84192735)"))
        cfg.attributes["connection"] = connection
        command.upgrade(cfg, "head")


if __name__ == "__main__":
    init_db()
