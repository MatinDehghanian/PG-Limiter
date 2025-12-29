# PEP 668 Installation Guide

On newer Linux distributions (Ubuntu 23.04+, Fedora 38+), you might encounter "externally-managed-environment" errors when installing Python packages with pip.

## Solutions

### Option 1: System Package (Recommended for Ubuntu/Debian)

```bash
sudo apt update
sudo apt install python3-httpx python3-aiohttp python3-requests
```

### Option 2: Break System Packages Flag

```bash
pip3 install -r requirements.txt --break-system-packages
```

### Option 3: Virtual Environment

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Option 4: pipx (For CLI Tools)

```bash
sudo apt install pipx
pipx install httpx
```

## Why This Happens

PEP 668 was introduced to prevent conflicts between system Python packages and user-installed packages. This is a safety feature to protect your system.

## Troubleshooting

If you still have issues:

1. Check Python version: `python3 --version`
2. Check pip version: `pip3 --version`
3. Try updating pip: `pip3 install --upgrade pip`
