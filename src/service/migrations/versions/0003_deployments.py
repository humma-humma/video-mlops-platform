"""Pin the selected deployment on every durable job."""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = depends_on = None


def upgrade():
    with op.batch_alter_table("jobs") as batch:
        batch.add_column(sa.Column("deployment_id", sa.String(64), nullable=False,
                                   server_default="video-summary-v1"))


def downgrade():
    with op.batch_alter_table("jobs") as batch:
        batch.drop_column("deployment_id")
