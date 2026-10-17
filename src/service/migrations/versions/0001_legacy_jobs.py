"""Create or adopt the previously unversioned jobs table without deleting data."""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = depends_on = None

def upgrade():
    if "jobs" in sa.inspect(op.get_bind()).get_table_names():
        required = {"id", "status", "input_path", "result_path", "attempts", "created_at", "started_at", "finished_at", "error_message"}
        columns = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("jobs")}
        if columns != required:
            raise RuntimeError("Legacy jobs schema differs; inspect it before adoption")
        return
    op.create_table("jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("input_path", sa.Text(), nullable=False),
        sa.Column("result_path", sa.Text()),
        sa.Column("error_message", sa.Text()),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_jobs_status", "jobs", ["status"])

def downgrade():
    op.drop_table("jobs")
