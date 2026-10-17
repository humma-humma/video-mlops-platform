"""Exercise real Alembic upgrades, legacy adoption, and data-preserving rollback."""
from pathlib import Path

from alembic import command
from alembic.config import Config
import pytest
from sqlalchemy import create_engine, inspect, text

ROOT = Path(__file__).resolve().parents[1]


def migrate(engine, revision, downgrade=False):
    cfg = Config()
    cfg.set_main_option("script_location", str(ROOT / "src/service/migrations"))
    with engine.begin() as connection:
        cfg.attributes["connection"] = connection
        (command.downgrade if downgrade else command.upgrade)(cfg, revision)


@pytest.fixture
def database(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'migration.db'}")
    yield engine
    engine.dispose()


def test_fresh_upgrade_is_repeatable(database):
    migrate(database, "head")
    migrate(database, "head")
    assert {"jobs", "job_attempts", "job_events", "alembic_version"} <= set(inspect(database).get_table_names())
    assert {"generation", "idempotency_key", "trace_id", "deployment_id"} <= {c["name"] for c in inspect(database).get_columns("jobs")}


def test_unversioned_legacy_rows_survive_upgrade_and_lifecycle_rollback(database):
    # Revision 0001 is the exact old create_all schema. Remove only its version marker.
    migrate(database, "0001")
    with database.begin() as connection:
        connection.execute(text("INSERT INTO jobs (id,status,input_path,attempts) VALUES ('old','SUCCEEDED','legacy.mp4',1)"))
        connection.execute(text("DROP TABLE alembic_version"))
    migrate(database, "head")
    with database.connect() as connection:
        assert connection.execute(text("SELECT status,generation,deployment_id FROM jobs WHERE id='old'")).one() == ("SUCCEEDED", 0, "video-summary-v1")
    migrate(database, "0001", downgrade=True)
    with database.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM jobs WHERE id='old'")) == 1
    migrate(database, "head")


def test_unknown_legacy_schema_is_refused(database):
    with database.begin() as connection:
        connection.execute(text("CREATE TABLE jobs (id TEXT PRIMARY KEY, secret TEXT)"))
    with pytest.raises(RuntimeError, match="differs"):
        migrate(database, "head")
    assert "secret" in {c["name"] for c in inspect(database).get_columns("jobs")}
