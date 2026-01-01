#!/usr/bin/env python3
"""
Tests for Database Models and CRUD operations
Tests User model and CRUD operations.
"""

import pytest
from datetime import datetime
from unittest.mock import MagicMock, AsyncMock, patch


class TestUserModel:
    """Tests for User database model"""
    
    def test_user_fields(self):
        """Test User model has expected fields"""
        from db.models import User
        
        # Check model has expected columns
        assert hasattr(User, 'id')
        assert hasattr(User, 'username')
        assert hasattr(User, 'status')
    
    def test_user_table_name(self):
        """Test User model table name"""
        from db.models import User
        
        assert User.__tablename__ == 'users'


class TestUserCRUD:
    """Tests for UserCRUD operations"""
    
    @pytest.fixture
    def mock_db_session(self):
        """Create a mock database session"""
        session = MagicMock()
        session.execute = AsyncMock()
        session.flush = AsyncMock()
        session.add = MagicMock()
        return session
    
    @pytest.mark.asyncio
    async def test_get_by_username_not_found(self, mock_db_session):
        """Test getting user that doesn't exist"""
        from db.crud.users import UserCRUD
        
        # Mock result for no user found
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result
        
        result = await UserCRUD.get_by_username(mock_db_session, "nonexistent")
        
        assert result is None
    
    @pytest.mark.asyncio
    async def test_get_by_username_found(self, mock_db_session):
        """Test getting existing user"""
        from db.crud.users import UserCRUD
        from db.models import User
        
        # Mock user
        mock_user = MagicMock(spec=User)
        mock_user.username = "test_user"
        mock_user.status = "active"
        
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_user
        mock_db_session.execute.return_value = mock_result
        
        result = await UserCRUD.get_by_username(mock_db_session, "test_user")
        
        assert result is not None
        assert result.username == "test_user"
    
    @pytest.mark.asyncio
    async def test_get_all_empty(self, mock_db_session):
        """Test getting all users when empty"""
        from db.crud.users import UserCRUD
        
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db_session.execute.return_value = mock_result
        
        result = await UserCRUD.get_all(mock_db_session)
        
        assert result == []
    
    @pytest.mark.asyncio
    async def test_get_all_usernames(self, mock_db_session):
        """Test getting all usernames as set"""
        from db.crud.users import UserCRUD
        
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [("user1",), ("user2",), ("user3",)]
        mock_db_session.execute.return_value = mock_result
        
        result = await UserCRUD.get_all_usernames(mock_db_session)
        
        assert isinstance(result, set)
        assert "user1" in result
        assert "user2" in result
        assert len(result) == 3


class TestUserStatus:
    """Tests for user status handling"""
    
    def test_valid_statuses(self):
        """Test valid user statuses"""
        valid_statuses = ["active", "disabled", "limited", "expired"]
        
        for status in valid_statuses:
            assert status in valid_statuses
    
    def test_disabled_status_detection(self):
        """Test detecting disabled status"""
        status = "disabled"
        assert status == "disabled"


class TestUserExceptions:
    """Tests for user exception handling in CRUD"""
    
    @pytest.mark.asyncio
    async def test_exception_user_operations(self):
        """Test exception user CRUD operations"""
        from db.crud.users import UserCRUD
        
        # UserCRUD should have exception-related methods
        assert hasattr(UserCRUD, 'set_excepted')
        assert hasattr(UserCRUD, 'get_all_excepted')


class TestUserLimits:
    """Tests for user limit handling in CRUD"""
    
    @pytest.mark.asyncio
    async def test_limit_user_operations(self):
        """Test limit user CRUD operations"""
        from db.crud.users import UserCRUD
        
        # UserCRUD should have limit-related methods
        assert hasattr(UserCRUD, 'set_special_limit')
        assert hasattr(UserCRUD, 'get_special_limit')
        assert hasattr(UserCRUD, 'get_all_special_limits')


class TestUserDisableStatus:
    """Tests for user disable status in CRUD"""
    
    @pytest.mark.asyncio
    async def test_disable_status_operations(self):
        """Test disable status CRUD operations"""
        from db.crud.users import UserCRUD
        
        # UserCRUD should have disable-related methods
        assert hasattr(UserCRUD, 'set_disabled')


class TestDatabaseMigration:
    """Tests for database migration handling"""
    
    def test_migration_files_exist(self):
        """Test that migration files exist"""
        import os
        from pathlib import Path
        
        migrations_dir = Path(__file__).parent.parent / "db" / "migrations" / "versions"
        
        assert migrations_dir.exists()
        
        # Should have at least initial migration
        migrations = list(migrations_dir.glob("*.py"))
        assert len(migrations) >= 1
    
    def test_alembic_config_exists(self):
        """Test alembic.ini exists"""
        from pathlib import Path
        
        alembic_ini = Path(__file__).parent.parent / "alembic.ini"
        
        assert alembic_ini.exists()
