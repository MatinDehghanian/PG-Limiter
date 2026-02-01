"""Add admin patterns table for prefix/postfix

Revision ID: 003_admin_patterns
Revises: 002_consolidate_users
Create Date: 2026-02-01

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '003_admin_patterns'
down_revision = '002_consolidate_users'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create admin_patterns table
    op.create_table(
        'admin_patterns',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('admin_username', sa.String(length=255), nullable=False),
        sa.Column('pattern_type', sa.String(length=50), nullable=False),
        sa.Column('pattern', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_admin_patterns_admin', 'admin_patterns', ['admin_username'], unique=False)
    op.create_index('ix_admin_patterns_type', 'admin_patterns', ['pattern_type'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_admin_patterns_type', table_name='admin_patterns')
    op.drop_index('ix_admin_patterns_admin', table_name='admin_patterns')
    op.drop_table('admin_patterns')
