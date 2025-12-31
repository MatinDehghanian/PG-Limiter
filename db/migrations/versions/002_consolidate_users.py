"""Consolidate users table - merge except_users, user_limits, disabled_users into users

Revision ID: 002_consolidate_users
Revises: 001_initial
Create Date: 2024-12-31

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '002_consolidate_users'
down_revision: Union[str, None] = '001_initial'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add new consolidated columns to users table
    
    # Exception/Whitelist fields (from except_users)
    op.add_column('users', sa.Column('is_excepted', sa.Boolean(), nullable=True, default=False))
    op.add_column('users', sa.Column('exception_reason', sa.Text(), nullable=True))
    op.add_column('users', sa.Column('excepted_by', sa.String(length=255), nullable=True))
    op.add_column('users', sa.Column('excepted_at', sa.DateTime(), nullable=True))
    
    # Special IP limit (from user_limits)
    op.add_column('users', sa.Column('special_limit', sa.Integer(), nullable=True))
    op.add_column('users', sa.Column('special_limit_updated_at', sa.DateTime(), nullable=True))
    
    # Disable status (from disabled_users)
    op.add_column('users', sa.Column('is_disabled_by_limiter', sa.Boolean(), nullable=True, default=False))
    op.add_column('users', sa.Column('disabled_at', sa.Float(), nullable=True))
    op.add_column('users', sa.Column('enable_at', sa.Float(), nullable=True))
    op.add_column('users', sa.Column('original_groups', sa.JSON(), nullable=True))
    op.add_column('users', sa.Column('disable_reason', sa.Text(), nullable=True))
    op.add_column('users', sa.Column('punishment_step', sa.Integer(), nullable=True, default=0))
    
    # Create indexes for new fields
    op.create_index('ix_users_is_excepted', 'users', ['is_excepted'], unique=False)
    op.create_index('ix_users_is_disabled_by_limiter', 'users', ['is_disabled_by_limiter'], unique=False)
    
    # Migrate data from except_users to users
    op.execute("""
        UPDATE users 
        SET is_excepted = TRUE,
            exception_reason = except_users.reason,
            excepted_by = except_users.created_by,
            excepted_at = except_users.created_at
        FROM except_users 
        WHERE users.username = except_users.username
    """)
    
    # Migrate data from user_limits to users
    op.execute("""
        UPDATE users 
        SET special_limit = user_limits."limit",
            special_limit_updated_at = user_limits.updated_at
        FROM user_limits 
        WHERE users.username = user_limits.username
    """)
    
    # Migrate data from disabled_users to users
    op.execute("""
        UPDATE users 
        SET is_disabled_by_limiter = TRUE,
            disabled_at = disabled_users.disabled_at,
            enable_at = disabled_users.enable_at,
            original_groups = disabled_users.original_groups,
            disable_reason = disabled_users.reason,
            punishment_step = disabled_users.punishment_step
        FROM disabled_users 
        WHERE users.username = disabled_users.username
    """)
    
    # Set default values for boolean columns
    op.execute("UPDATE users SET is_excepted = FALSE WHERE is_excepted IS NULL")
    op.execute("UPDATE users SET is_disabled_by_limiter = FALSE WHERE is_disabled_by_limiter IS NULL")
    op.execute("UPDATE users SET punishment_step = 0 WHERE punishment_step IS NULL")
    
    # Remove foreign key constraints from old tables
    # Drop FK from user_limits
    try:
        op.drop_constraint('user_limits_username_fkey', 'user_limits', type_='foreignkey')
    except Exception:
        pass  # Constraint may not exist
    
    # Drop FK from disabled_users
    try:
        op.drop_constraint('disabled_users_username_fkey', 'disabled_users', type_='foreignkey')
    except Exception:
        pass  # Constraint may not exist
    
    # Drop FK from violation_history
    try:
        op.drop_constraint('violation_history_username_fkey', 'violation_history', type_='foreignkey')
    except Exception:
        pass  # Constraint may not exist


def downgrade() -> None:
    # Remove new indexes
    op.drop_index('ix_users_is_excepted', table_name='users')
    op.drop_index('ix_users_is_disabled_by_limiter', table_name='users')
    
    # Remove new columns from users
    op.drop_column('users', 'is_excepted')
    op.drop_column('users', 'exception_reason')
    op.drop_column('users', 'excepted_by')
    op.drop_column('users', 'excepted_at')
    op.drop_column('users', 'special_limit')
    op.drop_column('users', 'special_limit_updated_at')
    op.drop_column('users', 'is_disabled_by_limiter')
    op.drop_column('users', 'disabled_at')
    op.drop_column('users', 'enable_at')
    op.drop_column('users', 'original_groups')
    op.drop_column('users', 'disable_reason')
    op.drop_column('users', 'punishment_step')
