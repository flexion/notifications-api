"""

Revision ID: 0164_add_organisation_to_service
Revises: 0163_add_new_org_model
Create Date: 2018-02-09 17:58:34.617206

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0164_add_organisation_to_service"
down_revision = "0163_add_new_org_model"


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table(
        "organisation_to_service",
        sa.Column("service_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organisation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["organisation_id"],
            ["organisation.id"],
        ),
        sa.ForeignKeyConstraint(
            ["service_id"],
            ["services.id"],
        ),
        sa.PrimaryKeyConstraint("service_id"),
    )
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table("organisation_to_service")
    # ### end Alembic commands ###
