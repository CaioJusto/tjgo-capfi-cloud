"""initial schema

Revision ID: 20260401_0001
Revises:
Create Date: 2026-04-01 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260401_0001"
down_revision = None
branch_labels = None
depends_on = None


job_type = sa.Enum("PLANILHA", "SERVENTIA", "NOME", "COMBINADA", name="job_type")
job_status = sa.Enum("PENDING", "RUNNING", "DONE", "FAILED", "CANCELED", name="job_status")


def upgrade() -> None:
    bind = op.get_bind()
    job_type.create(bind, checkfirst=True)
    job_status.create(bind, checkfirst=True)

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(length=50), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_users_id", "users", ["id"])
    op.create_index("ix_users_username", "users", ["username"], unique=True)
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("job_type", job_type, nullable=False),
        sa.Column("status", job_status, nullable=False, server_default="PENDING"),
        sa.Column("params", sa.JSON(), nullable=False),
        sa.Column("result_file_path", sa.String(length=500), nullable=True),
        sa.Column("total_items", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("processed_items", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.String(length=2000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_jobs_id", "jobs", ["id"])
    op.create_index("ix_jobs_user_id", "jobs", ["user_id"])
    op.create_index("ix_jobs_status", "jobs", ["status"])

    op.create_table(
        "process_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("job_id", sa.Integer(), sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("numero_processo", sa.String(length=50), nullable=True),
        sa.Column("nome_parte", sa.String(length=255), nullable=True),
        sa.Column("cpf_cnpj", sa.String(length=30), nullable=True),
        sa.Column("serventia", sa.String(length=255), nullable=True),
        sa.Column("advogados", sa.JSON(), nullable=True),
        sa.Column("status_rpv", sa.String(length=255), nullable=True),
        sa.Column("movimentacoes", sa.JSON(), nullable=True),
        sa.Column("raw_data", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_process_records_id", "process_records", ["id"])
    op.create_index("ix_process_records_job_id", "process_records", ["job_id"])
    op.create_index("ix_process_records_numero_processo", "process_records", ["numero_processo"])
    op.create_index("ix_process_records_nome_parte", "process_records", ["nome_parte"])
    op.create_index("ix_process_records_cpf_cnpj", "process_records", ["cpf_cnpj"])


def downgrade() -> None:
    op.drop_index("ix_process_records_cpf_cnpj", table_name="process_records")
    op.drop_index("ix_process_records_nome_parte", table_name="process_records")
    op.drop_index("ix_process_records_numero_processo", table_name="process_records")
    op.drop_index("ix_process_records_job_id", table_name="process_records")
    op.drop_index("ix_process_records_id", table_name="process_records")
    op.drop_table("process_records")

    op.drop_index("ix_jobs_status", table_name="jobs")
    op.drop_index("ix_jobs_user_id", table_name="jobs")
    op.drop_index("ix_jobs_id", table_name="jobs")
    op.drop_table("jobs")

    op.drop_index("ix_users_email", table_name="users")
    op.drop_index("ix_users_username", table_name="users")
    op.drop_index("ix_users_id", table_name="users")
    op.drop_table("users")

    bind = op.get_bind()
    job_status.drop(bind, checkfirst=True)
    job_type.drop(bind, checkfirst=True)
