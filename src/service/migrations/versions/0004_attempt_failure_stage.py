"""Persist the worker's bounded failure stage on each attempt."""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = depends_on = None


def upgrade():
    with op.batch_alter_table("job_attempts") as batch:
        batch.add_column(sa.Column("failure_stage", sa.String(32), nullable=True))


def downgrade():
    with op.batch_alter_table("job_attempts") as batch:
        batch.drop_column("failure_stage")
