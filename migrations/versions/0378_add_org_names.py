"""

Revision ID: 0378_add_org_names
Revises: 0377_add_inbound_sms_number
Create Date: 2022-09-23 20:04:00.766980

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0378_add_org_names"
down_revision = "0377_add_inbound_sms_number"


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.get_bind()

    # bluntly swap out data
    op.execute(
        "INSERT INTO organisation_types VALUES ('state','f','250000'),('federal','f','250000');"
    )
    op.execute("UPDATE services SET organisation_type = 'federal';")
    op.execute("UPDATE organisation SET organisation_type = 'federal';")
    op.execute("UPDATE services_history SET organisation_type = 'federal';")

    # remove uk values
    service_delete = """DELETE FROM organisation_types WHERE name IN
                    ('central','local','nhs','nhs_central','nhs_local','emergency_service','school_or_college','nhs_gp')
                """
    op.execute(service_delete)

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    service_insert = """INSERT INTO organisation_types VALUES
                    ('central','','250000')
                    ('local','f','25000')
                    ('nhs','','25000')
                    ('nhs_central','t','250000')
                    ('nhs_local','f','25000')
                    ('emergency_service','f','25000')
                    ('school_or_college','f','25000')
                    ('nhs_gp','f','25000')
                """
    op.execute(service_insert)
    op.execute("UPDATE services SET organisation_type = 'central';")
    op.execute("UPDATE organisation SET organisation_type = 'central';")
    op.execute("UPDATE services_history SET organisation_type = 'central';")
    op.execute("DELETE FROM organisation_types WHERE name IN ('federal','state')")

    # ### end Alembic commands ###
