"""

Revision ID: 0386_remove_letter_rates_.py
Revises: 0385_remove postage_.py
Create Date: 2023-02-15 10:24:55.107467

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0386_remove_letter_rates_.py'
down_revision = '0385_remove postage_.py'


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table('letter_rates')
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('letter_rates',
        sa.Column('id', postgresql.UUID(), autoincrement=False, nullable=False),
        sa.Column('start_date', postgresql.TIMESTAMP(), autoincrement=False, nullable=False),
        sa.Column('end_date', postgresql.TIMESTAMP(), autoincrement=False, nullable=True),
        sa.Column('sheet_count', sa.INTEGER(), autoincrement=False, nullable=False),
        sa.Column('rate', sa.NUMERIC(), autoincrement=False, nullable=False),
        sa.Column('crown', sa.BOOLEAN(), autoincrement=False, nullable=False),
        sa.Column('post_class', sa.VARCHAR(), autoincrement=False, nullable=False),
        sa.PrimaryKeyConstraint('id', name='letter_rates_pkey')
    )
    # ### end Alembic commands ###
