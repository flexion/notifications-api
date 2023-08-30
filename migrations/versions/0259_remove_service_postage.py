"""

Revision ID: 0259_remove_service_postage
Revises: 0258_service_postage_nullable
Create Date: 2019-02-11 17:12:22.341599

"""
from alembic import op
import sqlalchemy as sa


revision = "0259_remove_service_postage"
down_revision = "0258_service_postage_nullable"


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column("services", "postage")
    op.drop_column("services_history", "postage")
    op.execute("DELETE FROM service_permissions WHERE permission = 'choose_postage'")
    op.execute("DELETE FROM service_permission_types WHERE name = 'choose_postage'")
    op.execute(
        """UPDATE templates_history SET postage = templates.postage
        FROM templates WHERE templates_history.id = templates.id AND templates_history.template_type = 'letter'
        AND templates_history.postage is null"""
    )
    op.execute(
        """
        ALTER TABLE templates ADD CONSTRAINT "chk_templates_postage"
        CHECK (
            CASE WHEN template_type = 'letter' THEN
                postage is not null and postage in ('first', 'second')
            ELSE
                postage is null
            END
        )
    """
    )
    op.execute(
        """
        ALTER TABLE templates_history ADD CONSTRAINT "chk_templates_history_postage"
        CHECK (
            CASE WHEN template_type = 'letter' THEN
                postage is not null and postage in ('first', 'second')
            ELSE
                postage is null
            END
        )
    """
    )
    op.execute(
        """
        ALTER TABLE templates DROP CONSTRAINT "chk_templates_postage_null"
    """
    )
    op.execute(
        """
        ALTER TABLE templates_history DROP CONSTRAINT "chk_templates_history_postage_null"
    """
    )
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column(
        "services_history",
        sa.Column(
            "postage", sa.VARCHAR(length=255), autoincrement=False, nullable=True
        ),
    )
    op.add_column(
        "services",
        sa.Column(
            "postage", sa.VARCHAR(length=255), autoincrement=False, nullable=True
        ),
    )
    op.execute("INSERT INTO service_permission_types VALUES ('choose_postage')")
    op.execute(
        """
        ALTER TABLE templates ADD CONSTRAINT "chk_templates_postage_null"
        CHECK (
            CASE WHEN template_type = 'letter' THEN
                postage in ('first', 'second') OR
                postage is null
            ELSE
                postage is null
            END
        )
    """
    )
    op.execute(
        """
        ALTER TABLE templates_history ADD CONSTRAINT "chk_templates_history_postage_null"
        CHECK (
            CASE WHEN template_type = 'letter' THEN
                postage in ('first', 'second') OR
                postage is null
            ELSE
                postage is null
            END
        )
    """
    )
    op.execute(
        """
        ALTER TABLE templates DROP CONSTRAINT "chk_templates_postage"
    """
    )
    op.execute(
        """
        ALTER TABLE templates_history DROP CONSTRAINT "chk_templates_history_postage"
    """
    )
    # ### end Alembic commands ###
