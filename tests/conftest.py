#!/usr/bin/env python3
"""
Pytest configuration and fixtures
Shared test fixtures and configuration for all tests.
"""

import os
import sys
import pytest
import asyncio
import json
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def sample_config():
    """Provide sample configuration for tests"""
    return {
        "panel_username": "test_admin",
        "panel_password": "test_password",
        "panel_domain": "test.panel.com",
        "telegram_bot_token": "123456789:ABCdefGHIjklMNOpqrsTUVwxyz",
        "telegram_chat_id": "-1001234567890",
        "ip_limit": 3,
        "check_interval": 60,
        "punishment": {
            "enabled": True,
            "window_hours": 72,
            "steps": [
                {"type": "warning", "duration": 0},
                {"type": "disable", "duration": 15},
                {"type": "disable", "duration": 60},
                {"type": "disable", "duration": 0}
            ]
        }
    }


@pytest.fixture
def sample_users():
    """Provide sample user data for tests"""
    return [
        {"name": "user1", "ip": ["1.1.1.1", "2.2.2.2"]},
        {"name": "user2", "ip": ["3.3.3.3"]},
        {"name": "user3", "ip": ["4.4.4.4", "5.5.5.5", "6.6.6.6"]}
    ]


@pytest.fixture
def sample_log_lines():
    """Provide sample log lines for parsing tests"""
    return [
        "2023/07/07 03:09:00 151.232.190.86:57288 accepted tcp:gateway.instagram.com:443 [REALITY TCP 4 -> IPv4] email: 22.User_22",
        "2023/07/07 03:08:59 [2a01:5ec0:5011:9962:d8ed:c723:c32:ac2a]:62316 accepted tcp:2.56.98.255:8000 [GRPC 6 >> DIRECT] email: 6.TEST_user",
        "2023/07/07 03:09:18 [2a01:5ec0:5013:4ca8:1:0:d554:7f0e]:45572 accepted udp:1.1.1.1:53 [REALITY TCP 6 >> DIRECT] email: 2.another_user"
    ]


@pytest.fixture
def mock_panel_type():
    """Provide a mock PanelType for tests"""
    from utils.types import PanelType
    return PanelType(
        panel_username="test_admin",
        panel_password="test_password",
        panel_domain="test.panel.com"
    )


@pytest.fixture
def mock_user_type():
    """Provide a mock UserType for tests"""
    from utils.types import UserType
    return UserType(name="test_user", ip=["1.1.1.1", "2.2.2.2"])


@pytest.fixture
def temp_config_dir(tmp_path):
    """Create a temporary config directory"""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    return config_dir


@pytest.fixture
def mock_telegram_bot():
    """Provide a mock Telegram bot"""
    bot = MagicMock()
    bot.send_message = AsyncMock(return_value=MagicMock(message_id=12345))
    bot.edit_message_text = AsyncMock()
    bot.answer_callback_query = AsyncMock()
    return bot


@pytest.fixture
def mock_httpx_client():
    """Provide a mock httpx client"""
    client = MagicMock()
    client.get = AsyncMock(return_value=MagicMock(
        status_code=200,
        json=MagicMock(return_value={"country": "US", "isp": "Test ISP"})
    ))
    client.post = AsyncMock(return_value=MagicMock(
        status_code=200,
        json=MagicMock(return_value={"access_token": "test_token"})
    ))
    return client


@pytest.fixture(autouse=True)
def reset_globals():
    """Reset global state before each test"""
    # Import and reset globals that might persist between tests
    try:
        from utils.handel_dis_users import DISABLED_USERS, DISABLED_USERS_TIMESTAMPS, DISABLED_USERS_ENABLE_AT
        DISABLED_USERS.clear()
        DISABLED_USERS_TIMESTAMPS.clear()
        DISABLED_USERS_ENABLE_AT.clear()
    except ImportError:
        pass
    
    try:
        from utils.check_usage import ACTIVE_USERS
        ACTIVE_USERS.clear()
    except ImportError:
        pass
    
    yield  # Run test
    
    # Cleanup after test if needed


# Markers for different test categories
def pytest_configure(config):
    """Configure custom markers"""
    config.addinivalue_line("markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')")
    config.addinivalue_line("markers", "integration: marks tests as integration tests")
    config.addinivalue_line("markers", "unit: marks tests as unit tests")


# Skip tests that require external services
def pytest_collection_modifyitems(config, items):
    """Modify test collection"""
    if not config.getoption("--run-integration", default=False):
        skip_integration = pytest.mark.skip(reason="need --run-integration option to run")
        for item in items:
            if "integration" in item.keywords:
                item.add_marker(skip_integration)


def pytest_addoption(parser):
    """Add custom command line options"""
    parser.addoption(
        "--run-integration",
        action="store_true",
        default=False,
        help="run integration tests"
    )
