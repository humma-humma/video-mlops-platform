"""Idempotent submission, dispatch generations, attempts, and audit events."""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = depends_on = None

def upgrade():
    with op.batch_alter_table("jobs") as batch:
        batch.add_column(sa.Column("idempotency_key", sa.String(128)))
        batch.add_column(sa.Column("request_hash", sa.String(64)))
        batch.add_column(sa.Column("generation", sa.Integer(), server_default="0", nullable=False))
        batch.add_column(sa.Column("dispatched_at", sa.DateTime(timezone=True)))
        batch.add_column(sa.Column("trace_id", sa.String(32)))
        batch.create_unique_constraint("uq_jobs_idempotency_key", ["idempotency_key"])
    op.create_table("job_attempts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("job_id", sa.String(36), sa.ForeignKey("jobs.id"), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("result_path", sa.Text()),
        sa.Column("error_code", sa.String(32)),
        sa.Column("error_message", sa.Text()),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("job_id", "number", name="uq_job_attempt_number"),
    )
    op.create_index("ix_job_attempts_job_id", "job_attempts", ["job_id"])
    op.create_table("job_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("job_id", sa.String(36), sa.ForeignKey("jobs.id"), nullable=False),
        sa.Column("event", sa.String(40), nullable=False),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("trace_id", sa.String(32)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_job_events_job_id", "job_events", ["job_id"])

def downgrade():
    op.drop_table("job_events")
    op.drop_table("job_attempts")
    with op.batch_alter_table("jobs") as batch:
        batch.drop_constraint("uq_jobs_idempotency_key", type_="unique")
        for column in ["trace_id", "dispatched_at", "generation", "request_hash", "idempotency_key"]:
            batch.drop_column(column)
