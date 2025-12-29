#!/usr/bin/env python3
"""
Test script to verify that the new API endpoints work correctly
"""

import asyncio
import sys

# Check if httpx is available
try:
    import httpx
    print("✅ httpx dependency is available")
except ImportError:
    print("❌ httpx is not installed!")
    print("Please install it using one of these methods:")
    print("1. pip3 install httpx --break-system-packages")
    print("2. pip3 install httpx --user")
    print("3. sudo apt install python3-httpx (Ubuntu/Debian)")
    print("4. Run: bash install_httpx.sh")
    print("\nSee PEP668_INSTALLATION_GUIDE.md for detailed instructions.")
    sys.exit(1)

try:
    from utils.panel_api import get_token, get_nodes, all_user
    from utils.types import PanelType
except ImportError as e:
    print(f"❌ Import error: {e}")
    print("Make sure you're running this script from the limiter directory.")
    sys.exit(1)


async def test_new_api():
    """Test the new API endpoints"""
    
    # You should replace these with your actual panel credentials
    panel_data = PanelType(
        panel_username="admin",
        panel_password="admin", 
        panel_domain="your-panel-domain.com"
    )
    
    try:
        print("Testing token endpoint...")
        token_result = await get_token(panel_data)
        if isinstance(token_result, ValueError):
            print(f"❌ Token test failed: {token_result}")
            return False
        else:
            print("✅ Token endpoint working")
            
        print("\nTesting users endpoint...")
        users_result = await all_user(panel_data)
        if isinstance(users_result, ValueError):
            print(f"❌ Users test failed: {users_result}")
            return False
        else:
            print(f"✅ Users endpoint working - Found {len(users_result)} users")
            
        print("\nTesting nodes endpoint...")
        nodes_result = await get_nodes(panel_data)
        if isinstance(nodes_result, ValueError):
            print(f"❌ Nodes test failed: {nodes_result}")
            return False
        else:
            print(f"✅ Nodes endpoint working - Found {len(nodes_result)} nodes")
            
        print("\n🎉 All API endpoints are working correctly!")
        return True
        
    except Exception as e:
        print(f"❌ Test failed with exception: {e}")
        return False


if __name__ == "__main__":
    print("Testing new PasarGuard API endpoints...")
    print("=" * 50)
    
    success = asyncio.run(test_new_api())
    
    if success:
        print("\n✅ All tests passed! The app should work with the new API.")
        sys.exit(0)
    else:
        print("\n❌ Some tests failed. Please check your panel configuration.")
        sys.exit(1)
