"""add api clients and authorization attribution

Revision ID: 99434b40d6e5
Revises: ed054bd95378
Create Date: 2026-08-31 05:04:28.301460

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "99434b40d6e5"
down_revision: str | Sequence[str] | None = "ed054bd95378"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "api_clients",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("api_key_hash", sa.String(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index(op.f("ix_api_clients_api_key_hash"), "api_clients", ["api_key_hash"], unique=True)

    # batch_alter_table: SQLite can't ALTER TABLE ADD CONSTRAINT directly — this
    # is Alembic's copy-and-move strategy for it, and a harmless passthrough to
    # plain ALTER statements on databases (Postgres) that support it natively.
    with op.batch_alter_table("authorizations") as batch_op:
        batch_op.add_column(sa.Column("created_by_client_id", sa.String(), nullable=True))
        batch_op.create_index(
            op.f("ix_authorizations_created_by_client_id"), ["created_by_client_id"], unique=False
        )
        batch_op.create_foreign_key(
            "fk_authorizations_created_by_client_id_api_clients",
            "api_clients",
            ["created_by_client_id"],
            ["id"],
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("authorizations") as batch_op:
        batch_op.drop_constraint(
            "fk_authorizations_created_by_client_id_api_clients", type_="foreignkey"
        )
        batch_op.drop_index(op.f("ix_authorizations_created_by_client_id"))
        batch_op.drop_column("created_by_client_id")

    op.drop_index(op.f("ix_api_clients_api_key_hash"), table_name="api_clients")
    op.drop_table("api_clients")
