"""empty message

Revision ID: 0095_migrate_existing_svc_perms
Revises: 0094_job_stats_update
Create Date: 2017-05-23 18:13:03.532095

"""

# revision identifiers, used by Alembic.
from sqlalchemy import text

revision = '0095_migrate_existing_svc_perms'
down_revision = '0094_job_stats_update'

from alembic import op
import sqlalchemy as sa

migration_date = '2017-05-26 17:30:00.000000'


def upgrade():
    def get_values(permission):
        return "SELECT id, '{0}', '{1}' FROM services WHERE "\
            "id NOT IN (SELECT service_id FROM service_permissions "\
            "WHERE service_id=id AND permission='{0}')".format(permission, migration_date)

    def get_values_if_flag(permission, flag):
        return "SELECT id, '{0}', '{1}' FROM services WHERE "\
            "{2} AND id NOT IN (SELECT service_id FROM service_permissions "\
            "WHERE service_id=id AND permission='{0}')".format(permission, migration_date, flag)

    conn = op.get_bind()
    conn.execute("""
    INSERT INTO service_permissions (service_id, permission, created_at)
    SELECT id, 'sms', '2017-05-26 17:30:00.000000' FROM services 
    WHERE id NOT IN (SELECT service_id FROM service_permissions 
    WHERE service_id=id AND permission='sms')
    """)

    conn.execute("""
        INSERT INTO service_permissions (service_id, permission, created_at)
        SELECT id, 'email', '2017-05-26 17:30:00.000000' FROM services 
        WHERE id NOT IN (SELECT service_id FROM service_permissions 
        WHERE service_id=id AND permission='email')
        """)

    conn.execute("""
    INSERT INTO service_permissions (service_id, permission, created_at)
    SELECT id, 'letter', '2017-05-26 17:30:00.000000' FROM services 
    WHERE can_send_letters AND id NOT IN (SELECT service_id FROM service_permissions
    WHERE service_id=id AND permission='letter')
    """)
    conn.execute("""
        INSERT INTO service_permissions (service_id, permission, created_at)
        SELECT id, 'international_sms', '2017-05-26 17:30:00.000000' FROM services 
        WHERE can_send_international_sms AND id NOT IN (SELECT service_id FROM service_permissions 
        WHERE service_id=id AND permission='international_sms')
        """)


def downgrade():
    op.execute("DELETE FROM service_permissions WHERE created_at = '2017-05-26 17:30:00.000000'::timestamp")
