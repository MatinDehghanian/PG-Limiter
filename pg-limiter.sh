#!/usr/bin/env bash
set -e

# PG-Limiter Management Script
# https://github.com/MatinDehghanian/PG-Limiter

VERSION="0.7.7"

# Configuration
REPO_OWNER="MatinDehghanian"
REPO_NAME="PG-Limiter"
SERVICE_NAME="pg-limiter"
CONFIG_DIR="/etc/opt/pg-limiter"
DATA_DIR="/var/lib/pg-limiter"
DOCKER_IMAGE="ghcr.io/matindehghanian/pg-limiter:latest"
COMPOSE_FILE="$CONFIG_DIR/docker-compose.yml"
ENV_FILE="$CONFIG_DIR/.env"
SCRIPT_URL="https://raw.githubusercontent.com/$REPO_OWNER/$REPO_NAME/main/pg-limiter.sh"

# ═══════════════════════════════════════════════════════════════════════════════
# UTILITY FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════

colorized_echo() {
    local color=$1
    local text=$2
    
    case $color in
        "red")
            printf "\e[91m%s\e[0m\n" "$text"
            ;;
        "green")
            printf "\e[92m%s\e[0m\n" "$text"
            ;;
        "yellow")
            printf "\e[93m%s\e[0m\n" "$text"
            ;;
        "blue")
            printf "\e[94m%s\e[0m\n" "$text"
            ;;
        "magenta")
            printf "\e[95m%s\e[0m\n" "$text"
            ;;
        "cyan")
            printf "\e[96m%s\e[0m\n" "$text"
            ;;
        *)
            echo "$text"
            ;;
    esac
}

print_banner() {
    echo ""
    colorized_echo cyan "╔═══════════════════════════════════════════════════════════════╗"
    colorized_echo cyan "║                                                               ║"
    colorized_echo cyan "║   ██████╗  ██████╗       ██╗     ██╗███╗   ███╗██╗████████╗   ║"
    colorized_echo cyan "║   ██╔══██╗██╔════╝       ██║     ██║████╗ ████║██║╚══██╔══╝   ║"
    colorized_echo cyan "║   ██████╔╝██║  ███╗█████╗██║     ██║██╔████╔██║██║   ██║      ║"
    colorized_echo cyan "║   ██╔═══╝ ██║   ██║╚════╝██║     ██║██║╚██╔╝██║██║   ██║      ║"
    colorized_echo cyan "║   ██║     ╚██████╔╝      ███████╗██║██║ ╚═╝ ██║██║   ██║      ║"
    colorized_echo cyan "║   ╚═╝      ╚═════╝       ╚══════╝╚═╝╚═╝     ╚═╝╚═╝   ╚═╝      ║"
    colorized_echo cyan "║                                                               ║"
    colorized_echo cyan "║              IP Limiter for PasarGuard Panel                  ║"
    colorized_echo cyan "║                                                               ║"
    colorized_echo cyan "╚═══════════════════════════════════════════════════════════════╝"
    echo ""
}

# ═══════════════════════════════════════════════════════════════════════════════
# SYSTEM DETECTION
# ═══════════════════════════════════════════════════════════════════════════════

check_running_as_root() {
    if [ "$(id -u)" != "0" ]; then
        colorized_echo red "Error: This script must be run as root"
        exit 1
    fi
}

detect_os() {
    if [ -f /etc/lsb-release ]; then
        OS=$(lsb_release -si)
    elif [ -f /etc/os-release ]; then
        OS=$(awk -F= '/^NAME/{print $2}' /etc/os-release | tr -d '"')
    elif [ -f /etc/redhat-release ]; then
        OS=$(cat /etc/redhat-release | awk '{print $1}')
    elif [ -f /etc/arch-release ]; then
        OS="Arch Linux"
    else
        colorized_echo red "Unsupported operating system"
        exit 1
    fi
}

detect_and_update_package_manager() {
    colorized_echo blue "Updating package manager..."
    if [[ "$OS" == "Ubuntu"* ]] || [[ "$OS" == "Debian"* ]]; then
        PKG_MANAGER="apt-get"
        $PKG_MANAGER update -qq
    elif [[ "$OS" == "CentOS"* ]] || [[ "$OS" == "AlmaLinux"* ]] || [[ "$OS" == "Rocky"* ]]; then
        PKG_MANAGER="yum"
        $PKG_MANAGER makecache -q
    elif [[ "$OS" == "Fedora"* ]]; then
        PKG_MANAGER="dnf"
        $PKG_MANAGER makecache -q
    elif [[ "$OS" == "Arch Linux"* ]]; then
        PKG_MANAGER="pacman"
        $PKG_MANAGER -Sy --noconfirm
    else
        colorized_echo red "Unsupported OS for automatic package installation"
        exit 1
    fi
}

install_package() {
    if [ -z "$PKG_MANAGER" ]; then
        detect_os
        detect_and_update_package_manager
    fi
    
    local PACKAGE=$1
    colorized_echo blue "Installing $PACKAGE..."
    
    if [[ "$OS" == "Ubuntu"* ]] || [[ "$OS" == "Debian"* ]]; then
        $PKG_MANAGER -y install "$PACKAGE" -qq
    elif [[ "$OS" == "CentOS"* ]] || [[ "$OS" == "AlmaLinux"* ]] || [[ "$OS" == "Rocky"* ]]; then
        $PKG_MANAGER install -y "$PACKAGE" -q
    elif [[ "$OS" == "Fedora"* ]]; then
        $PKG_MANAGER install -y "$PACKAGE" -q
    elif [[ "$OS" == "Arch Linux"* ]]; then
        $PKG_MANAGER -S --noconfirm "$PACKAGE"
    fi
}

# ═══════════════════════════════════════════════════════════════════════════════
# DOCKER FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════

install_docker() {
    colorized_echo blue "Installing Docker..."
    curl -fsSL https://get.docker.com | sh
    systemctl enable docker
    systemctl start docker
    colorized_echo green "Docker installed successfully"
}

detect_compose() {
    if docker compose version >/dev/null 2>&1; then
        COMPOSE='docker compose'
    elif docker-compose version >/dev/null 2>&1; then
        COMPOSE='docker-compose'
    else
        colorized_echo red "Docker Compose not found"
        exit 1
    fi
}

check_docker() {
    if ! command -v docker &> /dev/null; then
        colorized_echo yellow "Docker is not installed"
        read -p "Would you like to install Docker? (Y/n): " install_docker_confirm
        if [[ "$install_docker_confirm" != "n" && "$install_docker_confirm" != "N" ]]; then
            install_docker
        else
            colorized_echo red "Docker is required to run PG-Limiter"
            exit 1
        fi
    fi
    
    detect_compose
}

# ═══════════════════════════════════════════════════════════════════════════════
# SERVICE STATE
# ═══════════════════════════════════════════════════════════════════════════════

is_installed() {
    [[ -f "$COMPOSE_FILE" ]] && [[ -f "$ENV_FILE" ]]
}

is_running() {
    if is_installed; then
        $COMPOSE -f "$COMPOSE_FILE" ps --status running 2>/dev/null | grep -q "$SERVICE_NAME"
    else
        return 1
    fi
}

# ═══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════

create_compose_file() {
    cat > "$COMPOSE_FILE" <<'EOF'
services:
  pg-limiter:
    image: ghcr.io/matindehghanian/pg-limiter:latest
    container_name: pg-limiter
    restart: always
    env_file: .env
    depends_on:
      - redis
    networks:
      - pg-limiter-network
    ports:
      - "8080:8080"
    volumes:
      - /var/lib/pg-limiter:/var/lib/pg-limiter
      - /etc/opt/pg-limiter:/etc/opt/pg-limiter:ro
    environment:
      - TZ=${TZ:-UTC}
      - REDIS_URL=redis://redis:6379

  redis:
    image: redis:7-alpine
    container_name: pg-limiter-redis
    restart: always
    networks:
      - pg-limiter-network
    volumes:
      - redis-data:/data
    command: redis-server --appendonly yes --maxmemory 128mb --maxmemory-policy allkeys-lru
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5

networks:
  pg-limiter-network:
    driver: bridge

volumes:
  redis-data:
EOF
}

create_env_file() {
    cat > "$ENV_FILE" <<'EOF'
# ═══════════════════════════════════════════════════════════════
# PG-Limiter Configuration
# ═══════════════════════════════════════════════════════════════

# Panel Configuration (Required)
PANEL_DOMAIN=your-panel-domain.com:8443
PANEL_USERNAME=admin
PANEL_PASSWORD=your_password

# Telegram Bot (Required)
BOT_TOKEN=YOUR_BOT_TOKEN
ADMIN_IDS=

# ═══════════════════════════════════════════════════════════════
# Limiter Settings
# ═══════════════════════════════════════════════════════════════

GENERAL_LIMIT=2
CHECK_INTERVAL=60
TIME_TO_ACTIVE_USERS=900
COUNTRY_CODE=

# ═══════════════════════════════════════════════════════════════
# API Server (Optional)
# ═══════════════════════════════════════════════════════════════
# API_ENABLED=false
# API_HOST=0.0.0.0
# API_PORT=8080
# API_USERNAME=admin
# API_PASSWORD=secure_password

# ═══════════════════════════════════════════════════════════════
# Advanced Settings
# ═══════════════════════════════════════════════════════════════

TZ=UTC
DATABASE_URL=sqlite+aiosqlite:////var/lib/pg-limiter/data/pg_limiter.db
EOF
}

replace_or_append_env_var() {
    local key="$1"
    local value="$2"
    local target_file="${3:-$ENV_FILE}"
    
    if grep -q "^$key=" "$target_file"; then
        sed -i "s|^$key=.*|$key=$value|" "$target_file"
    else
        printf '%s=%s\n' "$key" "$value" >> "$target_file"
    fi
}

configure_interactive() {
    echo ""
    colorized_echo blue "====================================="
    colorized_echo blue "      Interactive Configuration      "
    colorized_echo blue "====================================="
    echo ""
    
    # Panel domain
    while true; do
        read -p "Panel domain (e.g., panel.example.com:8443): " panel_domain
        if [[ -n "$panel_domain" ]]; then
            break
        fi
        colorized_echo red "Panel domain is required"
    done
    
    # Panel username
    read -p "Panel username [admin]: " panel_username
    panel_username=${panel_username:-admin}
    
    # Panel password
    while true; do
        read -sp "Panel password: " panel_password
        echo ""
        if [[ -n "$panel_password" ]]; then
            break
        fi
        colorized_echo red "Panel password is required"
    done
    
    # Bot token
    echo ""
    while true; do
        read -p "Telegram Bot Token (from @BotFather): " bot_token
        if [[ -n "$bot_token" ]]; then
            break
        fi
        colorized_echo red "Bot token is required"
    done
    
    # Admin IDs
    while true; do
        read -p "Admin Chat IDs (comma-separated, get from @userinfobot): " admin_ids
        if [[ -n "$admin_ids" ]]; then
            break
        fi
        colorized_echo red "At least one admin ID is required"
    done
    
    # General limit
    read -p "Default IP limit per user [2]: " general_limit
    general_limit=${general_limit:-2}
    
    # Check interval
    read -p "Check interval in seconds [60]: " check_interval
    check_interval=${check_interval:-60}
    
    # Time to active users
    read -p "Time to consider user active in seconds [900]: " time_to_active
    time_to_active=${time_to_active:-900}
    
    # Country code
    read -p "Country code filter (IR/RU/CN or empty for all) []: " country_code
    
    # Timezone
    read -p "Timezone [UTC]: " timezone
    timezone=${timezone:-UTC}
    
    # Update .env file
    replace_or_append_env_var "PANEL_DOMAIN" "$panel_domain"
    replace_or_append_env_var "PANEL_USERNAME" "$panel_username"
    replace_or_append_env_var "PANEL_PASSWORD" "$panel_password"
    replace_or_append_env_var "BOT_TOKEN" "$bot_token"
    replace_or_append_env_var "ADMIN_IDS" "$admin_ids"
    replace_or_append_env_var "GENERAL_LIMIT" "$general_limit"
    replace_or_append_env_var "CHECK_INTERVAL" "$check_interval"
    replace_or_append_env_var "TIME_TO_ACTIVE_USERS" "$time_to_active"
    replace_or_append_env_var "COUNTRY_CODE" "$country_code"
    replace_or_append_env_var "TZ" "$timezone"
    
    colorized_echo green "✓ Configuration saved to $ENV_FILE"
}

# ═══════════════════════════════════════════════════════════════════════════════
# INSTALL / UNINSTALL
# ═══════════════════════════════════════════════════════════════════════════════

install_script() {
    colorized_echo blue "Installing pg-limiter script..."
    curl -sSL "$SCRIPT_URL" | install -m 755 /dev/stdin /usr/local/bin/pg-limiter
    colorized_echo green "✓ pg-limiter script installed"
}

cmd_install() {
    check_running_as_root
    check_docker
    
    print_banner
    
    if is_installed; then
        colorized_echo yellow "PG-Limiter is already installed"
        read -p "Do you want to reinstall? (y/N): " confirm
        if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
            exit 0
        fi
        cmd_stop 2>/dev/null || true
    fi
    
    colorized_echo blue "Installing PG-Limiter..."
    
    # Create directories
    mkdir -p "$CONFIG_DIR"
    mkdir -p "$DATA_DIR/data"
    mkdir -p "$DATA_DIR/logs"
    
    # Create config files
    create_compose_file
    create_env_file
    
    # Interactive configuration
    configure_interactive
    
    # Pull latest image
    colorized_echo blue "Pulling latest Docker image..."
    docker pull "$DOCKER_IMAGE"
    
    # Install CLI command globally
    install_script
    
    # Start service
    cmd_start
    
    echo ""
    colorized_echo green "====================================="
    colorized_echo green "  PG-Limiter installed successfully! "
    colorized_echo green "====================================="
    echo ""
    colorized_echo cyan "Configuration: $CONFIG_DIR"
    colorized_echo cyan "Data:          $DATA_DIR"
    echo ""
    colorized_echo blue "Commands:"
    echo "  pg-limiter start    - Start the service"
    echo "  pg-limiter stop     - Stop the service"
    echo "  pg-limiter restart  - Restart the service"
    echo "  pg-limiter status   - Show service status"
    echo "  pg-limiter logs     - Show service logs"
    echo "  pg-limiter backup   - Backup configuration and data"
    echo "  pg-limiter restore  - Restore from backup"
    echo "  pg-limiter update   - Update to latest version"
    echo ""
}

cmd_uninstall() {
    check_running_as_root
    
    print_banner
    
    if ! is_installed; then
        colorized_echo yellow "PG-Limiter is not installed"
        exit 0
    fi
    
    colorized_echo red "⚠️  WARNING: This will remove PG-Limiter and all its data!"
    read -p "Are you sure? (y/N): " confirm
    if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
        exit 0
    fi
    
    read -p "Do you want to create a backup before uninstalling? (Y/n): " backup_confirm
    if [[ "$backup_confirm" != "n" && "$backup_confirm" != "N" ]]; then
        cmd_backup
    fi
    
    colorized_echo blue "Stopping service..."
    cmd_stop 2>/dev/null || true
    
    colorized_echo blue "Removing Docker container and image..."
    $COMPOSE -f "$COMPOSE_FILE" down --rmi local 2>/dev/null || true
    docker rmi "$DOCKER_IMAGE" 2>/dev/null || true
    
    colorized_echo blue "Removing configuration..."
    rm -rf "$CONFIG_DIR"
    
    read -p "Remove data directory ($DATA_DIR)? (y/N): " remove_data
    if [[ "$remove_data" == "y" || "$remove_data" == "Y" ]]; then
        rm -rf "$DATA_DIR"
        colorized_echo green "✓ Data directory removed"
    fi
    
    # Remove CLI symlink
    rm -f /usr/local/bin/pg-limiter
    
    colorized_echo green "✓ PG-Limiter uninstalled successfully!"
}

# ═══════════════════════════════════════════════════════════════════════════════
# SERVICE MANAGEMENT
# ═══════════════════════════════════════════════════════════════════════════════

cmd_start() {
    check_running_as_root
    check_docker
    
    if ! is_installed; then
        colorized_echo red "PG-Limiter is not installed. Run 'pg-limiter install' first."
        exit 1
    fi
    
    if is_running; then
        colorized_echo yellow "PG-Limiter is already running"
        exit 0
    fi
    
    colorized_echo blue "Starting PG-Limiter..."
    cd "$CONFIG_DIR"
    $COMPOSE -f "$COMPOSE_FILE" up -d
    
    colorized_echo green "✓ PG-Limiter started!"
}

cmd_stop() {
    check_running_as_root
    check_docker
    
    if ! is_installed; then
        colorized_echo red "PG-Limiter is not installed"
        exit 1
    fi
    
    colorized_echo blue "Stopping PG-Limiter..."
    $COMPOSE -f "$COMPOSE_FILE" down
    
    colorized_echo green "✓ PG-Limiter stopped!"
}

cmd_restart() {
    check_running_as_root
    check_docker
    
    if ! is_installed; then
        colorized_echo red "PG-Limiter is not installed"
        exit 1
    fi
    
    colorized_echo blue "Restarting PG-Limiter..."
    # Stop, clear logs, and start fresh
    $COMPOSE -f "$COMPOSE_FILE" down
    # Clear container logs by recreating
    $COMPOSE -f "$COMPOSE_FILE" up -d
    
    colorized_echo green "✓ PG-Limiter restarted!"
}

cmd_status() {
    if ! is_installed; then
        colorized_echo red "PG-Limiter is not installed"
        exit 1
    fi
    
    detect_compose
    
    echo ""
    colorized_echo blue "====================================="
    colorized_echo blue "        PG-Limiter Status            "
    colorized_echo blue "====================================="
    echo ""
    
    if is_running; then
        colorized_echo green "● Service: Running"
    else
        colorized_echo red "○ Service: Stopped"
    fi
    
    echo ""
    colorized_echo cyan "Configuration: $CONFIG_DIR"
    colorized_echo cyan "Data:          $DATA_DIR"
    echo ""
    
    # Show container status
    $COMPOSE -f "$COMPOSE_FILE" ps 2>/dev/null || true
    
    echo ""
}

cmd_logs() {
    if ! is_installed; then
        colorized_echo red "PG-Limiter is not installed"
        exit 1
    fi
    
    detect_compose
    $COMPOSE -f "$COMPOSE_FILE" logs -f --tail=100
}

cmd_update() {
    check_running_as_root
    check_docker
    
    print_banner
    
    if ! is_installed; then
        colorized_echo red "PG-Limiter is not installed. Run 'pg-limiter install' first."
        exit 1
    fi
    
    colorized_echo blue "Updating PG-Limiter..."
    
    # Update script
    colorized_echo blue "Updating pg-limiter script..."
    curl -sSL "$SCRIPT_URL" -o /usr/local/bin/pg-limiter
    chmod +x /usr/local/bin/pg-limiter
    
    # Pull latest image
    colorized_echo blue "Pulling latest Docker image..."
    docker pull "$DOCKER_IMAGE"
    
    # Restart with new image (removes old container to clear logs)
    colorized_echo blue "Restarting service..."
    $COMPOSE -f "$COMPOSE_FILE" down --remove-orphans
    $COMPOSE -f "$COMPOSE_FILE" up -d
    
    colorized_echo green "✓ PG-Limiter updated successfully!"
}

# ═══════════════════════════════════════════════════════════════════════════════
# BACKUP / RESTORE
# ═══════════════════════════════════════════════════════════════════════════════

ensure_zip_installed() {
    if ! command -v zip &> /dev/null; then
        colorized_echo blue "Installing zip utility..."
        if [[ "$PKG_MANAGER" == "apt-get" ]]; then
            apt-get update -qq && apt-get install -y -qq zip unzip
        elif [[ "$PKG_MANAGER" == "yum" ]]; then
            yum install -y -q zip unzip
        elif [[ "$PKG_MANAGER" == "dnf" ]]; then
            dnf install -y -q zip unzip
        else
            apt-get update -qq && apt-get install -y -qq zip unzip 2>/dev/null || \
            yum install -y -q zip unzip 2>/dev/null || \
            dnf install -y -q zip unzip 2>/dev/null
        fi
    fi
}

cmd_backup() {
    check_running_as_root
    detect_os
    detect_and_update_package_manager
    ensure_zip_installed
    
    if ! is_installed; then
        colorized_echo red "PG-Limiter is not installed"
        exit 1
    fi
    
    local timestamp=$(date +%Y%m%d-%H%M%S)
    local backup_name="pg-limiter-backup-$timestamp.zip"
    local backup_path="${1:-$HOME/$backup_name}"
    
    colorized_echo blue "Creating backup..."
    
    # Create temp directory for backup
    local temp_dir=$(mktemp -d)
    
    # Copy config files
    mkdir -p "$temp_dir/config"
    cp -r "$CONFIG_DIR"/* "$temp_dir/config/" 2>/dev/null || true
    
    # Copy data files
    mkdir -p "$temp_dir/data"
    cp -r "$DATA_DIR"/* "$temp_dir/data/" 2>/dev/null || true
    
    # Create backup info file
    cat > "$temp_dir/backup_info.txt" <<EOF
PG-Limiter Backup
═════════════════════════════════════════
Created: $(date)
Hostname: $(hostname)
Config Directory: $CONFIG_DIR
Data Directory: $DATA_DIR

To restore:
  pg-limiter restore <this-file.zip>
EOF
    
    # Create zip file
    cd "$temp_dir"
    zip -r "$backup_path" . -x "*.zip" >/dev/null
    
    # Cleanup
    rm -rf "$temp_dir"
    
    colorized_echo green "✓ Backup created: $backup_path"
    echo ""
    echo "To restore: pg-limiter restore $backup_path"
}

cmd_restore() {
    check_running_as_root
    detect_os
    detect_and_update_package_manager
    ensure_zip_installed
    
    local backup_file="$1"
    
    if [[ -z "$backup_file" ]]; then
        colorized_echo red "Usage: pg-limiter restore <backup-file.zip>"
        exit 1
    fi
    
    if [[ ! -f "$backup_file" ]]; then
        colorized_echo red "Backup file not found: $backup_file"
        exit 1
    fi
    
    colorized_echo red "⚠️  WARNING: This will overwrite current configuration and data!"
    read -p "Are you sure? (y/N): " confirm
    if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
        exit 0
    fi
    
    # Stop service if running
    detect_compose 2>/dev/null || true
    if is_running; then
        colorized_echo blue "Stopping service..."
        cmd_stop
    fi
    
    colorized_echo blue "Restoring from backup..."
    
    # Create temp directory
    local temp_dir=$(mktemp -d)
    
    # Extract backup
    unzip -q "$backup_file" -d "$temp_dir"
    
    # Restore config
    if [[ -d "$temp_dir/config" ]]; then
        mkdir -p "$CONFIG_DIR"
        cp -r "$temp_dir/config"/* "$CONFIG_DIR/"
        colorized_echo green "✓ Configuration restored"
    fi
    
    # Restore data
    if [[ -d "$temp_dir/data" ]]; then
        mkdir -p "$DATA_DIR"
        cp -r "$temp_dir/data"/* "$DATA_DIR/"
        colorized_echo green "✓ Data restored"
    fi
    
    # Cleanup
    rm -rf "$temp_dir"
    
    colorized_echo green "✓ Backup restored successfully!"
    
    # Start service
    read -p "Start the service now? (Y/n): " start_confirm
    if [[ "$start_confirm" != "n" && "$start_confirm" != "N" ]]; then
        check_docker
        cmd_start
    fi
}

# ═══════════════════════════════════════════════════════════════════════════════
# UTILITY COMMANDS
# ═══════════════════════════════════════════════════════════════════════════════

check_editor() {
    if command -v nano &> /dev/null; then
        EDITOR="nano"
    elif command -v vim &> /dev/null; then
        EDITOR="vim"
    elif command -v vi &> /dev/null; then
        EDITOR="vi"
    else
        colorized_echo red "No editor found (nano, vim, vi)"
        exit 1
    fi
}

cmd_config() {
    check_running_as_root
    
    if ! is_installed; then
        colorized_echo red "PG-Limiter is not installed"
        exit 1
    fi
    
    check_editor
    $EDITOR "$ENV_FILE"
    
    colorized_echo yellow "Restart the service to apply changes: pg-limiter restart"
}

cmd_edit() {
    check_running_as_root
    
    if ! is_installed; then
        colorized_echo red "PG-Limiter is not installed"
        exit 1
    fi
    
    check_editor
    $EDITOR "$COMPOSE_FILE"
    
    colorized_echo yellow "Restart the service to apply changes: pg-limiter restart"
}

cmd_shell() {
    check_running_as_root
    
    if ! is_running; then
        colorized_echo red "PG-Limiter is not running"
        exit 1
    fi
    
    detect_compose
    $COMPOSE -f "$COMPOSE_FILE" exec pg-limiter /bin/bash
}

cmd_cli() {
    check_running_as_root
    
    if ! is_running; then
        colorized_echo red "PG-Limiter is not running"
        exit 1
    fi
    
    detect_compose
    shift
    $COMPOSE -f "$COMPOSE_FILE" exec pg-limiter python cli_main.py "$@"
}

# ═══════════════════════════════════════════════════════════════════════════════
# BASH COMPLETION
# ═══════════════════════════════════════════════════════════════════════════════

generate_completion() {
    cat <<'EOF'
_pg_limiter_completions() {
    local cur="${COMP_WORDS[COMP_CWORD]}"
    local commands="install uninstall update start stop restart status logs backup restore config edit shell cli help"
    COMPREPLY=($(compgen -W "$commands" -- "$cur"))
}
complete -F _pg_limiter_completions pg-limiter
EOF
}

install_completion() {
    generate_completion > /etc/bash_completion.d/pg-limiter
    colorized_echo green "✓ Bash completion installed"
}

# ═══════════════════════════════════════════════════════════════════════════════
# HELP
# ═══════════════════════════════════════════════════════════════════════════════

cmd_help() {
    print_banner
    echo "PG-Limiter v$VERSION"
    echo ""
    echo "Usage: pg-limiter <command> [options]"
    echo ""
    colorized_echo blue "Installation:"
    echo "  install       Install PG-Limiter"
    echo "  uninstall     Uninstall PG-Limiter"
    echo "  update        Update to latest version"
    echo ""
    colorized_echo blue "Service Management:"
    echo "  start         Start the service"
    echo "  stop          Stop the service"
    echo "  restart       Restart the service"
    echo "  status        Show service status"
    echo "  logs          Show service logs (follow mode)"
    echo ""
    colorized_echo blue "Backup & Restore:"
    echo "  backup        Create backup of config and data"
    echo "  restore       Restore from backup file"
    echo ""
    colorized_echo blue "Configuration:"
    echo "  config        Edit environment configuration (.env)"
    echo "  edit          Edit docker-compose.yml"
    echo ""
    colorized_echo blue "Advanced:"
    echo "  shell         Open shell in container"
    echo "  cli           Run CLI commands in container"
    echo "  completion    Install bash completion"
    echo ""
    colorized_echo blue "Examples:"
    echo "  pg-limiter install"
    echo "  pg-limiter start"
    echo "  pg-limiter backup ~/my-backup.zip"
    echo "  pg-limiter restore ~/my-backup.zip"
    echo "  pg-limiter cli --help"
    echo ""
}

# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

case "${1:-help}" in
    version|--version|-v)
        echo "PG-Limiter v$VERSION"
        ;;
    install)
        cmd_install
        ;;
    uninstall)
        cmd_uninstall
        ;;
    update)
        cmd_update
        ;;
    start|up)
        cmd_start
        ;;
    stop|down)
        cmd_stop
        ;;
    restart)
        cmd_restart
        ;;
    status)
        cmd_status
        ;;
    logs)
        cmd_logs
        ;;
    backup)
        cmd_backup "$2"
        ;;
    restore)
        cmd_restore "$2"
        ;;
    config|edit-env)
        cmd_config
        ;;
    edit)
        cmd_edit
        ;;
    shell)
        cmd_shell
        ;;
    cli)
        cmd_cli "$@"
        ;;
    completion)
        install_completion
        ;;
    install-script)
        check_running_as_root
        install_script
        ;;
    help|--help|-h)
        cmd_help
        ;;
    *)
        colorized_echo red "Unknown command: $1"
        cmd_help
        exit 1
        ;;
esac
