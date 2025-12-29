#!/bin/bash

# Simple installation script for httpx dependency
echo "📦 Installing httpx for new PasarGuard API..."
echo "========================================"

# Check if httpx is already installed
if python3 -c "import httpx" 2>/dev/null; then
    echo "✅ httpx is already installed"
    exit 0
fi

echo "🔧 Attempting to install httpx..."

# Method 1: Try regular pip install
echo "Method 1: Regular pip install..."
if pip3 install httpx 2>/dev/null; then
    echo "✅ Successfully installed httpx"
    exit 0
fi

# Method 2: Try with --break-system-packages (for PEP 668 environments)
echo "Method 2: Installing with --break-system-packages..."
if pip3 install httpx --break-system-packages 2>/dev/null; then
    echo "✅ Successfully installed httpx (with --break-system-packages)"
    exit 0
fi

# Method 3: Try user installation
echo "Method 3: User installation..."
if pip3 install httpx --user 2>/dev/null; then
    echo "✅ Successfully installed httpx (user install)"
    exit 0
fi

# Method 4: Try apt package manager (for Debian/Ubuntu)
if command -v apt &> /dev/null; then
    echo "Method 4: Installing via apt..."
    if apt update && apt install -y python3-httpx 2>/dev/null; then
        echo "✅ Successfully installed httpx via apt"
        exit 0
    fi
fi

# Method 5: Try yum/dnf for RHEL/CentOS/Fedora
if command -v dnf &> /dev/null; then
    echo "Method 5: Installing via dnf..."
    if dnf install -y python3-httpx 2>/dev/null; then
        echo "✅ Successfully installed httpx via dnf"
        exit 0
    fi
elif command -v yum &> /dev/null; then
    echo "Method 5: Installing via yum..."
    if yum install -y python3-httpx 2>/dev/null; then
        echo "✅ Successfully installed httpx via yum"
        exit 0
    fi
fi

echo "❌ Failed to install httpx automatically."
echo ""
echo "Please install httpx manually using one of these methods:"
echo ""
echo "🔧 Option 1: Override PEP 668 protection (if you understand the risks)"
echo "   pip3 install httpx --break-system-packages"
echo ""
echo "🔧 Option 2: Install in user directory"
echo "   pip3 install httpx --user"
echo ""
echo "🔧 Option 3: Use system package manager"
echo "   # For Debian/Ubuntu:"
echo "   sudo apt install python3-httpx"
echo "   # For RHEL/CentOS/Fedora:"
echo "   sudo dnf install python3-httpx"
echo ""
echo "🔧 Option 4: Use virtual environment (recommended)"
echo "   python3 -m venv venv"
echo "   source venv/bin/activate"
echo "   pip install httpx"
echo ""
echo "After installing httpx, you can run the limiter application normally."

exit 1
