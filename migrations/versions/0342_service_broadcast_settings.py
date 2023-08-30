"""

Revision ID: 0342_service_broadcast_settings
Revises: 0340_stub_training_broadcasts
Create Date: 2021-01-28 21:30:23.102340

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0342_service_broadcast_settings"
down_revision = "0340_stub_training_broadcasts"

CHANNEL_TYPES = ["test", "severe"]


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table(
        "broadcast_channel_types",
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.PrimaryKeyConstraint("name"),
    )
    op.create_table(
        "service_broadcast_settings",
        sa.Column("service_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("channel", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["channel"],
            ["broadcast_channel_types.name"],
        ),
        sa.ForeignKeyConstraint(
            ["service_id"],
            ["services.id"],
        ),
        sa.PrimaryKeyConstraint("service_id"),
    )
    # ### end Alembic commands ###

    for channel in CHANNEL_TYPES:
        op.execute(f"INSERT INTO broadcast_channel_types VALUES ('{channel}')")


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table("service_broadcast_settings")
    op.drop_table("broadcast_channel_types")
    # ### end Alembic commands ###
