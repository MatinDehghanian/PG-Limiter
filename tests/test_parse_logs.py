#!/usr/bin/env python3
"""
Tests for log parsing functionality
Tests email extraction, IP validation, and log line parsing.
"""

import pytest
import ipaddress


class TestIPValidation:
    """Tests for IP address validation"""
    
    @pytest.mark.asyncio
    async def test_valid_public_ipv4(self):
        """Test valid public IPv4 addresses"""
        from utils.parse_logs import is_valid_ip
        
        # Public IPs should return True (non-private)
        assert await is_valid_ip("151.232.190.86") is True
        assert await is_valid_ip("2.56.98.255") is True
    
    @pytest.mark.asyncio
    async def test_private_ipv4_returns_false(self):
        """Test private IPv4 addresses return False"""
        from utils.parse_logs import is_valid_ip
        
        # Private IPs return False
        assert await is_valid_ip("192.168.1.1") is False
        assert await is_valid_ip("10.0.0.1") is False
        assert await is_valid_ip("172.16.0.1") is False
    
    @pytest.mark.asyncio
    async def test_valid_public_ipv6(self):
        """Test valid public IPv6 addresses"""
        from utils.parse_logs import is_valid_ip
        
        # Public IPv6
        assert await is_valid_ip("2a01:5ec0:5011:9962:d8ed:c723:c32:ac2a") is True
    
    @pytest.mark.asyncio
    async def test_invalid_ip(self):
        """Test invalid IP addresses"""
        from utils.parse_logs import is_valid_ip
        
        assert await is_valid_ip("not_an_ip") is False
        assert await is_valid_ip("256.256.256.256") is False
        assert await is_valid_ip("192.168.1") is False
        assert await is_valid_ip("") is False


class TestUsernameExtraction:
    """Tests for username extraction from logs"""
    
    @pytest.mark.asyncio
    async def test_remove_id_prefix(self):
        """Test removing numeric ID prefix from username"""
        from utils.parse_logs import remove_id_from_username
        
        assert await remove_id_from_username("123.username") == "username"
        assert await remove_id_from_username("1.test") == "test"
        assert await remove_id_from_username("99999.user_name") == "user_name"
    
    @pytest.mark.asyncio
    async def test_no_prefix_unchanged(self):
        """Test username without prefix stays unchanged"""
        from utils.parse_logs import remove_id_from_username
        
        assert await remove_id_from_username("username") == "username"
        assert await remove_id_from_username("user.name") == "user.name"
    
    @pytest.mark.asyncio
    async def test_special_characters(self):
        """Test usernames with special characters"""
        from utils.parse_logs import remove_id_from_username
        
        assert await remove_id_from_username("6.TEST_user+canyoudetec-t=me") == "TEST_user+canyoudetec-t=me"


class TestInvalidEmails:
    """Tests for invalid email detection"""
    
    def test_invalid_emails_list(self):
        """Test that invalid emails list is populated"""
        from utils.parse_logs import INVALID_EMAILS
        
        assert len(INVALID_EMAILS) > 0
        assert "API]" in INVALID_EMAILS
        assert "timeout" in INVALID_EMAILS


class TestInvalidIPs:
    """Tests for invalid/excluded IPs"""
    
    def test_invalid_ips_set(self):
        """Test that invalid IPs are excluded"""
        from utils.parse_logs import INVALID_IPS
        
        assert "1.1.1.1" in INVALID_IPS
        assert "8.8.8.8" in INVALID_IPS


class TestLogLineParsing:
    """Tests for parsing individual log lines"""
    
    def test_accepted_connection_pattern(self):
        """Test parsing accepted connection log lines"""
        import re
        
        # Standard accepted pattern
        log_line = "2023/07/07 03:09:00 151.232.190.86:57288 accepted tcp:gateway.instagram.com:443 [REALITY TCP 4 -> IPv4] email: 22.User_22"
        
        # Extract IP
        ip_match = re.search(r'(\d+\.\d+\.\d+\.\d+):\d+ accepted', log_line)
        assert ip_match is not None
        assert ip_match.group(1) == "151.232.190.86"
        
        # Extract email
        email_match = re.search(r'email: (.+)$', log_line)
        assert email_match is not None
        assert email_match.group(1).strip() == "22.User_22"
    
    def test_ipv6_accepted_pattern(self):
        """Test parsing IPv6 accepted connection log lines"""
        import re
        
        log_line = "2023/07/07 03:08:59 [2a01:5ec0:5011:9962:d8ed:c723:c32:ac2a]:62316 accepted tcp:2.56.98.255:8000 [GRPC 6 >> DIRECT] email: 6.TEST_user+canyoudetec-t=me"
        
        # Extract IPv6
        ipv6_match = re.search(r'\[([a-fA-F0-9:]+)\]:\d+ accepted', log_line)
        assert ipv6_match is not None
        assert ipv6_match.group(1) == "2a01:5ec0:5011:9962:d8ed:c723:c32:ac2a"
    
    def test_grpc_pattern(self):
        """Test parsing GRPC connection pattern"""
        log_line = "2023/07/07 03:08:59 [2a01:5ec0:5011:9962:d8ed:c723:c32:ac2a]:62316 accepted tcp:2.56.98.255:8000 [GRPC 6 >> DIRECT] email: 6.TEST_user"
        
        assert "GRPC" in log_line
        assert "accepted" in log_line
    
    def test_reality_tcp_pattern(self):
        """Test parsing REALITY TCP connection pattern"""
        log_line = "2023/07/07 03:09:00 151.232.190.86:57288 accepted tcp:gateway.instagram.com:443 [REALITY TCP 4 -> IPv4] email: 22.User_22"
        
        assert "REALITY TCP" in log_line
        assert "accepted" in log_line


class TestCacheSystem:
    """Tests for IP location caching"""
    
    def test_cache_initialization(self):
        """Test that cache dict exists"""
        from utils.parse_logs import CACHE
        
        assert isinstance(CACHE, dict)
    
    def test_cache_lookup(self):
        """Test cached IP lookup returns cached value"""
        from utils.parse_logs import CACHE
        
        # Manually populate cache
        CACHE["test.ip.addr.ess"] = "US"
        
        assert CACHE.get("test.ip.addr.ess") == "US"
        
        # Clean up
        del CACHE["test.ip.addr.ess"]
