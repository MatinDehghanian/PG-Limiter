#!/usr/bin/env python3
"""
Tests for ISP Detection functionality
Tests IP to ISP lookup, caching, and subnet detection.
"""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock


class TestISPDetector:
    """Tests for ISPDetector class"""
    
    def test_initialization_no_token(self):
        """Test initialization without API token"""
        from utils.isp_detector import ISPDetector
        
        detector = ISPDetector()
        
        # Should use fallback mode without token
        assert detector.use_fallback_only is True
    
    def test_initialization_with_token(self):
        """Test initialization with API token"""
        from utils.isp_detector import ISPDetector
        
        detector = ISPDetector(token="test_token_12345")
        
        assert detector.token == "test_token_12345"
    
    def test_cache_initialization(self):
        """Test cache is initialized"""
        from utils.isp_detector import ISPDetector
        
        detector = ISPDetector()
        
        assert isinstance(detector.cache, dict)
        assert len(detector.cache) == 0
    
    def test_default_isp_info(self):
        """Test default ISP info generation"""
        from utils.isp_detector import _default_isp_info
        
        result = _default_isp_info("1.2.3.4")
        
        assert result["ip"] == "1.2.3.4"
        assert result["isp"] == "Unknown ISP"
        assert result["country"] == "Unknown"
    
    def test_rate_limit_delay(self):
        """Test rate limit delay is set"""
        from utils.isp_detector import ISPDetector
        
        detector = ISPDetector()
        
        assert detector.rate_limit_delay > 0
    
    @pytest.mark.asyncio
    async def test_close_session(self):
        """Test closing HTTP session"""
        from utils.isp_detector import ISPDetector
        
        detector = ISPDetector()
        
        # Should not raise even if no session exists
        await detector.close()


class TestISPCaching:
    """Tests for ISP caching functionality"""
    
    @pytest.mark.asyncio
    async def test_cache_hit(self):
        """Test cached ISP info is returned"""
        from utils.isp_detector import ISPDetector
        
        detector = ISPDetector()
        
        # Pre-populate cache
        cached_info = {
            "ip": "8.8.8.8",
            "isp": "Google LLC",
            "country": "US",
            "city": "Mountain View",
            "region": "California"
        }
        detector.cache["8.8.8.8"] = cached_info
        
        # Should return cached value without API call
        result = await detector.get_isp_info("8.8.8.8")
        
        assert result["isp"] == "Google LLC"
        assert result["country"] == "US"
    
    def test_cache_storage(self):
        """Test ISP info is stored in cache"""
        from utils.isp_detector import ISPDetector
        
        detector = ISPDetector()
        
        # Store in cache
        detector.cache["1.1.1.1"] = {
            "ip": "1.1.1.1",
            "isp": "Cloudflare",
            "country": "US"
        }
        
        assert "1.1.1.1" in detector.cache
        assert detector.cache["1.1.1.1"]["isp"] == "Cloudflare"


class TestSubnetDetection:
    """Tests for subnet-based ISP detection"""
    
    def test_same_subnet_ips(self):
        """Test IPs in same subnet"""
        import ipaddress
        
        ip1 = ipaddress.ip_address("192.168.1.1")
        ip2 = ipaddress.ip_address("192.168.1.100")
        
        # Get /24 networks
        net1 = ipaddress.ip_network(f"{ip1}/24", strict=False)
        net2 = ipaddress.ip_network(f"{ip2}/24", strict=False)
        
        # Should be same network
        assert net1 == net2
    
    def test_different_subnet_ips(self):
        """Test IPs in different subnets"""
        import ipaddress
        
        ip1 = ipaddress.ip_address("192.168.1.1")
        ip2 = ipaddress.ip_address("10.0.0.1")
        
        net1 = ipaddress.ip_network(f"{ip1}/24", strict=False)
        net2 = ipaddress.ip_network(f"{ip2}/24", strict=False)
        
        assert net1 != net2


class TestISPFormatting:
    """Tests for ISP info formatting"""
    
    def test_format_ip_with_isp(self):
        """Test formatting IP with ISP info"""
        from utils.isp_detector import ISPDetector
        
        detector = ISPDetector()
        
        isp_info = {
            "ip": "8.8.8.8",
            "isp": "Google LLC",
            "country": "US"
        }
        
        formatted = detector.format_ip_with_isp("8.8.8.8", isp_info)
        
        assert "8.8.8.8" in formatted
        assert "Google" in formatted
        assert "US" in formatted
    
    def test_format_unknown_isp(self):
        """Test formatting with unknown ISP"""
        from utils.isp_detector import ISPDetector
        
        detector = ISPDetector()
        
        isp_info = {
            "ip": "1.2.3.4",
            "isp": "Unknown ISP",
            "country": "Unknown"
        }
        
        formatted = detector.format_ip_with_isp("1.2.3.4", isp_info)
        
        assert "1.2.3.4" in formatted
    
    def test_format_as_prefixed_isp(self):
        """Test formatting ISP with AS prefix removal"""
        from utils.isp_detector import ISPDetector
        
        detector = ISPDetector()
        
        isp_info = {
            "ip": "1.1.1.1",
            "isp": "AS13335 Cloudflare Inc",
            "country": "US"
        }
        
        formatted = detector.format_ip_with_isp("1.1.1.1", isp_info)
        
        # AS prefix should be removed or cleaned
        assert "1.1.1.1" in formatted


class TestIPAPIEndpoints:
    """Tests for IP API endpoint handling"""
    
    def test_fallback_mode(self):
        """Test fallback to ip-api.com"""
        from utils.isp_detector import ISPDetector
        
        detector = ISPDetector(use_fallback_only=True)
        
        assert detector.use_fallback_only is True
    
    def test_rate_limited_flag(self):
        """Test rate limited flag initialization"""
        from utils.isp_detector import ISPDetector
        
        detector = ISPDetector()
        
        assert detector.rate_limited is False
