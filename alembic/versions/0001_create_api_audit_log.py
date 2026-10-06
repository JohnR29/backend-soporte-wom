"""create api_audit_log

Revision ID: 0001
Revises:
Create Date: 2026-10-06
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "api_audit_log",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("ts", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("request_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("client_ip", postgresql.INET(), nullable=True),
        sa.Column("x_forwarded_for", sa.Text(), nullable=True),
        sa.Column("method", sa.String(10), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("route_template", sa.Text(), nullable=True),
        sa.Column("query_params", postgresql.JSONB(), nullable=True),
        sa.Column("request_body", postgresql.JSONB(), nullable=True),
        sa.Column("request_size", sa.Integer(), nullable=True),
        sa.Column("status_code", sa.SmallInteger(), nullable=False),
        sa.Column("error_type", sa.Text(), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("response_size", sa.Integer(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("upstream_service", sa.Text(), nullable=True),
        sa.Column("upstream_status", sa.SmallInteger(), nullable=True),
        sa.Column("upstream_duration_ms", sa.Integer(), nullable=True),
        sa.Column("upstream_calls", sa.Integer(), nullable=True),
        sa.Column("ne_names", postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column("mml_command", sa.Text(), nullable=True),
    )
    op.create_index("ix_api_audit_log_ts", "api_audit_log", [sa.text("ts DESC")])
    op.create_index("ix_api_audit_log_client_ip_ts", "api_audit_log", ["client_ip", sa.text("ts DESC")])
    op.create_index(
        "ix_api_audit_log_errors",
        "api_audit_log",
        ["status_code"],
        postgresql_where=sa.text("status_code >= 400"),
    )


def downgrade() -> None:
    op.drop_table("api_audit_log")
