<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10+-blue?logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/License-AGPL--3.0-green" alt="License">
  <img src="https://img.shields.io/badge/Platform-Linux%20%7C%20macOS-lightgrey" alt="Platform">
</p>

<h1 align="center">🛡️ PG-Limiter</h1>

<p align="center">
  <b>Advanced IP Connection Limiter for <a href="https://github.com/PasarGuard/panel">PasarGuard</a> Panel</b>
  <br><br>
  Monitor and limit concurrent IP connections per user with real-time SSE log streaming,<br>
  Telegram bot control, REST API, CLI interface, and intelligent warning system.
</p>

---

## 📑 Table of Contents

- [Features](#-features)
- [Requirements](#-requirements)
- [Installation](#-installation)
- [Configuration](#-configuration)
- [Telegram Bot](#-telegram-bot)
- [CLI Interface](#-cli-interface)
- [REST API](#-rest-api)
- [Disable Methods](#-disable-methods)
- [FAQ](#-faq)
- [License](#-license)
- [Credits](#-credits)
- [Support](#-support)

---

## ✨ Features

| Feature | Description |
|---------|-------------|
| 🔒 **IP Limiting** | Limit concurrent connections per user (global or per-user) |
| 📊 **Real-time Monitoring** | SSE-based log streaming from all nodes |
| 🤖 **Telegram Bot** | Full control with inline keyboards and buttons |
| 🖥️ **CLI Interface** | Manage everything from command line |
| 🌐 **REST API** | HTTP API for external integrations |
| 🌍 **Country Filtering** | Count only IPs from specific countries (IR, RU, CN) |
| ⚠️ **Warning System** | Monitor period before disabling users |
| 🔄 **Auto Recovery** | Automatic user re-enabling after timeout |
| 📁 **Group-based Disable** | Move users to restricted group instead of disabling |
| 📱 **Multi-node Support** | Monitor all connected PasarGuard nodes |
| 💾 **Backup/Restore** | Backup and restore all settings |
| 🚫 **Exception List** | Exclude specific users from limiting |
| 🧹 **Auto Cleanup** | Remove deleted users from limiter config |
| 🔍 **Smart Skip** | Skip disabling users that don't exist in panel |

---

## 📋 Requirements

- **Python 3.10+**
- **PasarGuard Panel** (latest version)
- **Telegram Bot Token** (from [@BotFather](https://t.me/BotFather))

---

## 🚀 Installation

### Quick Install (Recommended)

```bash
bash <(curl -sSL https://raw.githubusercontent.com/MatinDehghanian/PG-Limiter/master/scripts/limiter.sh)
```

### Manual Installation

```bash
# Clone repository
git clone https://github.com/MatinDehghanian/PG-Limiter.git
cd PG-Limiter

# Install dependencies
pip install -r requirements.txt

# Copy example config
cp config.example.json config.json

# Run the limiter
python3 limiter.py
```

### Fixing "externally-managed-environment" Error

```bash
# Option 1: Use system package (Ubuntu/Debian)
sudo apt install python3-httpx python3-aiohttp

# Option 2: Use --break-system-packages
pip3 install -r requirements.txt --break-system-packages

# Option 3: Use virtual environment (recommended)
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

---

## ⚙️ Configuration

### Config File Structure

Edit `config.json` or use Telegram bot/CLI:

```json
{
  "panel": {
    "domain": "your-panel.com:PORT",
    "username": "admin",
    "password": "your_password"
  },
  "telegram": {
    "bot_token": "123456:ABC-YOUR-BOT-TOKEN",
    "admins": [123456789]
  },
  "limits": {
    "general": 2,
    "special": {
      "vip_user": 5,
      "premium_user": 10
    }
  },
  "except_users": ["unlimited_user", "test_user"],
  "check_interval": 60,
  "time_to_active_users": 900,
  "country_code": "IR",
  "disable_method": "status",
  "disabled_group_id": null
}
```

### Configuration Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `panel.domain` | string | - | Panel address with port |
| `panel.username` | string | - | Panel admin username |
| `panel.password` | string | - | Panel admin password |
| `telegram.bot_token` | string | - | Telegram bot token |
| `telegram.admins` | array | [] | List of admin chat IDs |
| `limits.general` | int | 2 | Default IP limit for all users |
| `limits.special` | object | {} | Per-user custom limits |
| `except_users` | array | [] | Users excluded from limiting |
| `check_interval` | int | 60 | Check interval in seconds |
| `time_to_active_users` | int | 900 | Re-enable timeout in seconds |
| `country_code` | string | "" | Filter IPs by country (IR/RU/CN) |
| `disable_method` | string | "status" | How to disable users: `status` or `group` |
| `disabled_group_id` | int | null | Group ID for group-based disable |

---

## 🤖 Telegram Bot

### Main Menu

The bot features an interactive menu with inline keyboards:

```
🏠 Main Menu
├── ⚙️ Settings      → Configure bot settings
├── 🎯 Limits        → Manage IP limits
├── 👥 Users         → Manage users & disabled list
├── 📡 Monitoring    → View connection status
├── 📊 Reports       → Generate reports
└── 👑 Admin         → Manage bot admins
```

### Settings Menu

| Option | Description |
|--------|-------------|
| 🔧 Panel Config | Set panel domain, username, password |
| 🌍 Country Code | Filter IPs by country (IR, RU, CN, None) |
| 🔑 IPInfo Token | Set IPInfo API token for location data |
| ⏱️ Check Interval | How often to check connections (60-300s) |
| ⏰ Active Time | Time before re-enabling users (300-1800s) |
| 📋 Enhanced Details | Show detailed node/protocol info |
| 1️⃣ Single IP Users | Show/hide single IP users in logs |
| 🚫 Disable Method | Choose between status or group-based disable |

### Limits Menu

| Option | Description |
|--------|-------------|
| 🎯 Set Special Limit | Set custom limit for specific user |
| 📋 Show Special Limits | View all users with custom limits |
| 🔢 Set General Limit | Set default limit for all users |

### Users Menu

| Option | Description |
|--------|-------------|
| ➕ Add Except User | Add user to exception list |
| ➖ Remove Except User | Remove user from exceptions |
| 📋 Show Except Users | View exception list |
| 🚫 Disabled Users | View/manage disabled users |
| ✅ Enable All | Re-enable all disabled users |
| 🧹 Cleanup Deleted | Remove users deleted from panel |

### Commands

| Command | Description |
|---------|-------------|
| `/start` | Show main menu |
| `/help` | Show all commands |
| `/backup` | Download config backup |
| `/restore` | Restore from backup file |

---

## 🖥️ CLI Interface

Run CLI commands with `python cli_main.py`:

### User Limits

```bash
# List all special limits
python cli_main.py user list

# Add special limit for user
python cli_main.py user add USERNAME 5

# Remove special limit
python cli_main.py user delete USERNAME

# Update existing limit
python cli_main.py user update USERNAME 10
```

### Exception Users

```bash
# List except users
python cli_main.py except list

# Add to exception list
python cli_main.py except add USERNAME

# Remove from exception list
python cli_main.py except delete USERNAME

# Check if user is excepted
python cli_main.py except check USERNAME
```

### Disabled Users

```bash
# List disabled users
python cli_main.py disabled list

# Enable a disabled user
python cli_main.py disabled enable USERNAME

# Enable all disabled users
python cli_main.py disabled enable-all
```

### Configuration

```bash
# Show current config
python cli_main.py config show

# Set general limit
python cli_main.py config set-limit 3

# Set check interval
python cli_main.py config set-interval 120

# Set re-enable time
python cli_main.py config set-reenable-time 1800

# Set country filter
python cli_main.py config set-country IR

# Cleanup deleted users from limiter config
python cli_main.py config cleanup
```

---

## 🌐 REST API

Start the API server:

```bash
python api_server.py
```

The API runs on port `8307` by default. Access docs at `http://localhost:8307/docs`

### Authentication

All endpoints require HTTP Basic Auth using Telegram admin credentials:
- Username: `admin`
- Password: First admin's chat ID from config

### Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Welcome message |
| GET | `/status` | Get limiter status |
| **User Limits** | | |
| GET | `/users/limits` | List all special limits |
| POST | `/users/limits` | Add special limit |
| PUT | `/users/limits/{username}` | Update limit |
| DELETE | `/users/limits/{username}` | Remove limit |
| **Exception Users** | | |
| GET | `/users/except` | List except users |
| POST | `/users/except` | Add except user |
| DELETE | `/users/except/{username}` | Remove except user |
| **Disabled Users** | | |
| GET | `/users/disabled` | List disabled users |
| POST | `/users/disabled/{username}/enable` | Enable user |
| POST | `/users/disabled/enable-all` | Enable all users |
| **Configuration** | | |
| GET | `/config` | Get full config |
| PUT | `/config/limit` | Set general limit |
| PUT | `/config/interval` | Set check interval |
| PUT | `/config/reenable-time` | Set re-enable time |
| PUT | `/config/country` | Set country filter |
| **Maintenance** | | |
| POST | `/cleanup` | Remove deleted users from config |

### Example Requests

```bash
# Get status
curl -u admin:123456789 http://localhost:8307/status

# Add special limit
curl -u admin:123456789 -X POST \
  http://localhost:8307/users/limits \
  -H "Content-Type: application/json" \
  -d '{"username": "vip_user", "limit": 5}'

# Enable disabled user
curl -u admin:123456789 -X POST \
  http://localhost:8307/users/disabled/john_doe/enable

# Cleanup deleted users
curl -u admin:123456789 -X POST \
  http://localhost:8307/cleanup
```

---

## 🚫 Disable Methods

### Status-based (Default)

Traditional method - changes user status to `disabled`:
- User cannot connect at all
- Status shows as "disabled" in panel

```json
{
  "disable_method": "status",
  "disabled_group_id": null
}
```

### Group-based (New)

Moves user to a restricted group instead:
- User remains "active" but with limited access
- Original groups are saved and restored on re-enable
- Useful for keeping users connected but restricted

```json
{
  "disable_method": "group",
  "disabled_group_id": 5
}
```

**Setup via Telegram:**
1. Go to `Settings → 🚫 Disable Method`
2. Click `📁 Use Group`
3. Select a group from the list

**How it works:**
1. When user exceeds limit → Original groups saved → Moved to disabled group
2. After timeout (or manual enable) → Original groups restored

---

## ❓ FAQ

<details>
<summary><b>Why do IP counts decrease over time?</b></summary>

The SSE implementation is stable. If issues occur:
- Check node connectivity
- Verify panel logs are enabled
- Try restarting the limiter
</details>

<details>
<summary><b>Why do connections persist after disabling?</b></summary>

This is Xray core behavior. Active connections remain until:
- Client reconnects
- Connection times out
- Client closes the connection
</details>

<details>
<summary><b>Do I need to restart after config changes?</b></summary>

No, changes apply automatically within seconds.
</details>

<details>
<summary><b>Can I run on a different server?</b></summary>

Yes, the limiter works on any server with network access to your panel.
</details>

<details>
<summary><b>No logs appearing?</b></summary>

1. Ensure xray log level is set to `info`:
```json
{
  "log": {
    "loglevel": "info"
  }
}
```

2. For HAProxy, add `option forwardfor` to config.
</details>

<details>
<summary><b>How to run as a service?</b></summary>

Create systemd service:
```bash
sudo nano /etc/systemd/system/pg-limiter.service
```

```ini
[Unit]
Description=PG-Limiter Service
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/path/to/limiter
ExecStart=/usr/bin/python3 limiter.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable pg-limiter
sudo systemctl start pg-limiter
```
</details>

<details>
<summary><b>How to use cron for auto-restart?</b></summary>

```bash
crontab -e
```

Add:
```bash
# Restart every 6 hours
0 */6 * * * cd /path/to/limiter && python3 limiter.py

# Run on reboot
@reboot cd /path/to/limiter && python3 limiter.py
```
</details>

---

## 📄 License

This project is licensed under the **AGPL-3.0 License** - see the [LICENSE](LICENSE) file for details.

---

## 🙏 Credits

Based on [V2IpLimit](https://github.com/houshmand-2005/V2IpLimit) by [houshmand-2005](https://github.com/houshmand-2005), adapted and enhanced for PasarGuard panel.

---

## ⭐ Support

If you find this project useful, please give it a ⭐!

[![Donate](https://img.shields.io/badge/Donate-Crypto-blue?logo=bitcoin)](https://nowpayments.io/donation/MattDev)

---

<p align="center">
  Made with ❤️ for the PasarGuard community
</p>
