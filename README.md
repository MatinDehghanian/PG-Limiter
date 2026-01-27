<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10+-blue?logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/License-AGPL--3.0-green" alt="License">
  <img src="https://img.shields.io/badge/Platform-Linux%20%7C%20macOS-lightgrey" alt="Platform">
  <img src="https://img.shields.io/badge/Version-0.8.1-orange" alt="Version">
</p>

<h1 align="center">🛡️ PG-Limiter</h1>

<p align="center">
  <b>Advanced IP Connection Limiter for <a href="https://github.com/PasarGuard/panel">PasarGuard</a> Panel</b>
  <br><br>
  Monitor and limit concurrent IP connections per user with real-time SSE log streaming,<br>
  Telegram bot control, REST API, CLI interface, Redis caching, and intelligent warning system.
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
- [Redis Caching](#-redis-caching)
- [Logging](#-logging)
- [Project Architecture](#-project-architecture)
- [FAQ](#-faq)
- [License](#-license)
- [Credits](#-credits)
- [Support](#-support)

---

## ✨ Features

### Core Features

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

### Advanced Features

| Feature | Description |
|---------|-------------|
| 🚀 **Redis Caching** | High-performance caching with Redis (with in-memory fallback) |
| 📝 **Enhanced Logging** | Comprehensive logging with file rotation and colored output |
| 🏗️ **Modular Architecture** | Clean, maintainable codebase with separated handlers |
| 👤 **Admin Filter** | Filter users by admin ownership |
| 👥 **Group Filter** | Only monitor specific user groups |
| ⚖️ **Punishment System** | Auto-escalate penalties for repeat violators |
| 🔍 **ISP Detection** | Detect and cache ISP information for IPs |
| 💿 **SQLite Database** | Fast persistent storage with async support |
| 🐳 **Docker + Redis** | Production-ready Docker Compose setup |

### Data Management

| Feature | Description |
|---------|-------------|
| 💾 **Backup/Restore** | Backup and restore all settings via Telegram |
| 🚫 **Exception List** | Exclude specific users from limiting |
| 🧹 **Auto Cleanup** | Remove deleted users from limiter config |
| 🔍 **Smart Skip** | Skip disabling users that don't exist in panel |

---

## 📋 Requirements

- **Python 3.10+**
- **PasarGuard Panel** (latest version)
- **Telegram Bot Token** (from [@BotFather](https://t.me/BotFather))
- **Redis** (optional, but recommended for production)

---

## 🚀 Installation

### Quick Install with Docker (Recommended)

```bash
# Download and run the installer
curl -sSL https://raw.githubusercontent.com/MatinDehghanian/PG-Limiter/main/pg-limiter.sh -o /tmp/pg-limiter.sh

sudo bash /tmp/pg-limiter.sh install
```

This will:
1. Install Docker (if not present)
2. Create configuration at `/etc/opt/pg-limiter/`
3. Store data at `/var/lib/pg-limiter/`
4. Guide you through interactive setup

### Management Commands

```bash
pg-limiter start      # Start the service
pg-limiter stop       # Stop the service
pg-limiter restart    # Restart the service
pg-limiter status     # Show service status
pg-limiter logs       # View logs (follow mode)
pg-limiter update     # Update to latest version
pg-limiter backup     # Create backup zip
pg-limiter restore    # Restore from backup
pg-limiter config     # Edit configuration
pg-limiter uninstall  # Remove PG-Limiter
```

### Manual Installation (Without Docker)

```bash
# Clone repository
git clone https://github.com/MatinDehghanian/PG-Limiter.git
cd PG-Limiter

# Install dependencies
pip install -r requirements.txt

# Copy example environment
cp .env.example .env

# Edit configuration
nano .env

# Run the limiter
python3 limiter.py
```

### Directory Structure

| Path | Description |
|------|-------------|
| `/etc/opt/pg-limiter/` | Configuration files (.env, docker-compose.yml) |
| `/var/lib/pg-limiter/` | Persistent data (database, logs) |
| `/var/lib/pg-limiter/data/` | SQLite database |

Docker volumes:
- `/var/lib/pg-limiter/` → Persistent storage for database and logs
- `redis-data` → Redis persistence (AOF enabled)

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

Configuration is split into two parts:
- **Environment variables (.env)**: Static settings like panel credentials, bot token, admin IDs
- **Database**: Dynamic settings that can be changed via Telegram bot

### Environment Variables (.env)

Edit `/etc/opt/pg-limiter/.env` or use `pg-limiter config`:

```bash
# Panel Settings (Required)
PANEL_DOMAIN=your-panel.com:PORT
PANEL_USERNAME=admin
PANEL_PASSWORD=your_password

# Telegram Bot (Required)
BOT_TOKEN=123456:ABC-YOUR-BOT-TOKEN
ADMIN_IDS=123456789,987654321

# Limiter Settings
GENERAL_LIMIT=2
CHECK_INTERVAL=60
TIME_TO_ACTIVE_USERS=900
COUNTRY_CODE=IR

# API Server (Optional)
API_ENABLED=false
API_HOST=0.0.0.0
API_PORT=8080
API_USERNAME=admin
API_PASSWORD=secret

# Redis Cache (Optional - falls back to in-memory if unavailable)
REDIS_URL=redis://localhost:6379/0
REDIS_PASSWORD=
REDIS_SSL=false

# Timezone
TZ=Asia/Tehran

# Database
DATABASE_URL=sqlite+aiosqlite:///./data/pg_limiter.db
```

### Configuration Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `PANEL_DOMAIN` | string | - | Panel address with port |
| `PANEL_USERNAME` | string | admin | Panel admin username |
| `PANEL_PASSWORD` | string | - | Panel admin password |
| `BOT_TOKEN` | string | - | Telegram bot token |
| `ADMIN_IDS` | string | - | Comma-separated admin chat IDs |
| `GENERAL_LIMIT` | int | 2 | Default IP limit for all users |
| `CHECK_INTERVAL` | int | 60 | Check interval in seconds |
| `TIME_TO_ACTIVE_USERS` | int | 900 | Re-enable timeout in seconds |
| `COUNTRY_CODE` | string | "" | Filter IPs by country (IR/RU/CN) |
| `REDIS_URL` | string | redis://localhost:6379/0 | Redis connection URL |
| `REDIS_PASSWORD` | string | "" | Redis password (optional) |
| `REDIS_SSL` | bool | false | Enable SSL for Redis |

### Dynamic Settings (via Telegram Bot)

These settings can be changed from the Telegram bot Settings menu:
- **Special Limits**: Per-user custom limits
- **Except Users**: Users excluded from limiting
- **Disable Method**: How to disable users (`status` or `group`)
- **Disabled Group ID**: Group ID for group-based disable
- **Enhanced Details**: Show detailed ISP info
- **Punishment System**: Auto-escalate repeat violators
- **Group Filter**: Only monitor specific user groups
- **Admin Filter**: Filter users by admin ownership

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

## 🚀 Redis Caching

PG-Limiter includes Redis caching for improved performance and persistence.

### Benefits

| Feature | Description |
|---------|-------------|
| ⚡ **Speed** | Sub-millisecond cache lookups |
| 💾 **Persistence** | Cache survives restarts |
| 🔄 **Shared State** | Multiple instances can share cache |
| 📉 **Reduced API Calls** | Cached tokens, nodes, config, and ISP data |

### Cache TTL Settings

| Cache Type | TTL | Description |
|------------|-----|-------------|
| Token | 30 min | Panel API access tokens |
| Nodes | 1 hour | Node list and status |
| Config | 5 min | Dynamic configuration |
| ISP | 7 days | IP-to-ISP mappings |
| Panel Users | 1 min | User list from panel |

### Docker Compose with Redis

The default `docker-compose.yml` includes Redis:

```yaml
services:
  pg-limiter:
    image: ghcr.io/matindehghanian/pg-limiter:latest
    depends_on:
      - redis
    environment:
      - REDIS_URL=redis://redis:6379
  
  redis:
    image: redis:7-alpine
    command: redis-server --appendonly yes --maxmemory 128mb --maxmemory-policy allkeys-lru
    volumes:
      - redis-data:/data
```

### Running Without Redis

Redis is optional. If Redis is unavailable, PG-Limiter automatically falls back to in-memory caching:

```bash
# In-memory cache will be used automatically if:
# - Redis is not installed
# - REDIS_URL is not set
# - Redis connection fails
```

---

## 📝 Logging

PG-Limiter includes comprehensive logging with multiple outputs.

### Log Outputs

| Output | Description |
|--------|-------------|
| Console | Colored output for easy reading |
| File | Rotating log files in `/var/lib/pg-limiter/logs/` |
| Telegram | Critical errors sent to admins |

### Log Levels

```bash
# Set log level via environment variable
LOG_LEVEL=DEBUG  # DEBUG, INFO, WARNING, ERROR
```

### Log Files

| File | Description |
|------|-------------|
| `limiter.log` | Main application logs |
| `api.log` | API request/response logs |
| `telegram.log` | Telegram bot logs |

---

## 🏗️ Project Architecture

PG-Limiter follows a modular architecture for maintainability:

```
PG-Limiter/
├── limiter.py              # Main entry point
├── api_server.py           # REST API server
├── cli_main.py             # CLI interface
├── run_telegram.py         # Telegram bot runner
│
├── telegram_bot/
│   ├── main.py            # Bot initialization
│   ├── keyboards.py       # Inline keyboards
│   └── handlers/          # Modular command handlers
│       ├── admin.py       # Admin management
│       ├── backup.py      # Backup/restore
│       ├── limits.py      # Limit management
│       ├── monitoring.py  # Connection monitoring
│       ├── punishment.py  # Punishment system
│       ├── reports.py     # Report generation
│       ├── settings.py    # Bot settings
│       └── users.py       # User management
│
├── utils/
│   ├── redis_cache.py     # Redis caching layer
│   ├── logs.py            # Logging configuration
│   ├── isp_detector.py    # ISP detection
│   ├── read_config.py     # Configuration management
│   └── panel_api/         # Panel API client
│       ├── auth.py        # Authentication
│       ├── users.py       # User operations
│       ├── nodes.py       # Node operations
│       └── groups.py      # Group operations
│
└── db/
    ├── database.py        # Database connection
    ├── models.py          # SQLAlchemy models
    └── crud/              # Database operations
        ├── config.py
        ├── users.py
        ├── limits.py
        └── violations.py
```

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

<details>
<summary><b>Is Redis required?</b></summary>

No, Redis is optional. PG-Limiter automatically falls back to in-memory caching if Redis is unavailable. However, Redis is recommended for production as it provides:
- Cache persistence across restarts
- Better performance for high-traffic scenarios
- Shared cache for multiple instances
</details>

<details>
<summary><b>How do I check cache status?</b></summary>

The limiter logs cache connection status on startup:
```
✓ Redis cache connected
```
or
```
⚠ Redis not available, using in-memory cache fallback
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
