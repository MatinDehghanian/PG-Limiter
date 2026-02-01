"""Add limit patterns table for prefix/postfix IP limits

Revision ID: 004_limit_patterns
Revises: 003_admin_patterns
Create Date: 2026-02-01

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '004_limit_patterns'
down_revision = '003_admin_patterns'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create limit_patterns table
    op.create_table(
        'limit_patterns',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('pattern_type', sa.String(length=50), nullable=False),
        sa.Column('pattern', sa.String(length=255), nullable=False),
        sa.Column('ip_limit', sa.Integer(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_limit_patterns_type', 'limit_patterns', ['pattern_type'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_limit_patterns_type', table_name='limit_patterns')
    op.drop_table('limit_patterns')
