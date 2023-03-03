"""

Revision ID: 0384_remove_letter_branding_
Revises: 0383_update_default_templates.py
Create Date: 2023-02-09 22:24:07.187569

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0384_remove_letter_branding_'
down_revision = '0383_update_default_templates.py'


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_constraint('fk_organisation_letter_branding_id', 'organisation', type_='foreignkey')
    op.drop_column('organisation', 'letter_branding_id')
    op.drop_table('service_letter_branding')
    op.drop_table('letter_branding')
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('organisation', sa.Column('letter_branding_id', postgresql.UUID(), autoincrement=False, nullable=True))
    op.create_foreign_key('fk_organisation_letter_branding_id', 'organisation', 'letter_branding', ['letter_branding_id'], ['id'])
    op.create_table('service_letter_branding',
        sa.Column('service_id', postgresql.UUID(), autoincrement=False, nullable=False),
        sa.Column('letter_branding_id', postgresql.UUID(), autoincrement=False, nullable=False),
        sa.ForeignKeyConstraint(['letter_branding_id'], ['letter_branding.id'], name='service_letter_branding_letter_branding_id_fkey'),
        sa.ForeignKeyConstraint(['service_id'], ['services.id'], name='service_letter_branding_service_id_fkey'),
        sa.PrimaryKeyConstraint('service_id', name='service_letter_branding_pkey')
    )
    op.create_table('letter_branding',
        sa.Column('id', postgresql.UUID(), autoincrement=False, nullable=False),
        sa.Column('name', sa.VARCHAR(length=255), autoincrement=False, nullable=False),
        sa.Column('filename', sa.VARCHAR(length=255), autoincrement=False, nullable=False),
        sa.PrimaryKeyConstraint('id', name='letter_branding_pkey'),
        sa.UniqueConstraint('filename', name='letter_branding_filename_key'),
        sa.UniqueConstraint('name', name='letter_branding_name_key')
    )
    # ### end Alembic commands ###
