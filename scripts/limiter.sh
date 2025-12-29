#!/bin/bash

# Limiter Installation Script
# https://github.com/MatinDehghanian/PG-Limiter

set -e

REPO_OWNER="MatinDehghanian"
REPO_NAME="PG-Limiter"

# Check required commands
check_dependencies() {
    local missing=()
    
    command -v screen &>/dev/null || missing+=("screen")
    command -v curl &>/dev/null || missing+=("curl")
    command -v jq &>/dev/null || missing+=("jq")
    
    if [ ${#missing[@]} -ne 0 ]; then
        echo "Missing required commands: ${missing[*]}"
        echo "Install with: sudo apt install ${missing[*]}"
        exit 1
    fi
}

# Detect architecture and set filename
get_binary_name() {
    local arch=$(uname -m)
    case "$arch" in
        x86_64) echo "limiter_amd64" ;;
        aarch64) echo "limiter_arm64" ;;
        *) echo ""; return 1 ;;
    esac
}

# Download the latest release binary
download_program() {
    local filename=$(get_binary_name)
    
    if [ -z "$filename" ]; then
        echo "Unsupported architecture: $(uname -m)"
        return 1
    fi
    
    if [ -f "$filename" ]; then
        echo "Binary already exists: $filename"
        return 0
    fi
    
    echo "Downloading $filename..."
    
    # Try to get the download URL from release assets
    local api_response=$(curl -s "https://api.github.com/repos/$REPO_OWNER/$REPO_NAME/releases/latest")
    
    # Check if we got a valid response
    if echo "$api_response" | jq -e '.assets' > /dev/null 2>&1; then
        local download_url=$(echo "$api_response" | jq -r ".assets[] | select(.name == \"$filename\") | .browser_download_url")
        
        if [ -n "$download_url" ] && [ "$download_url" != "null" ]; then
            curl -L "$download_url" -o "$filename"
            chmod +x "$filename"
            echo "Download complete: $filename"
            return 0
        fi
    fi
    
    echo "No pre-built binary found. Running from source instead."
    return 1
}

# Update the binary
update_program() {
    local filename=$(get_binary_name)
    [ -f "$filename" ] && rm "$filename"
    download_program
}

# Check if limiter is running
is_running() {
    screen -list 2>/dev/null | grep -q "Limiter"
}

# Start the limiter
start_program() {
    local filename=$(get_binary_name)
    
    # Check config
    if [ ! -f "config/config.json" ]; then
        echo "Config not found. Creating configuration..."
        create_config
    fi
    
    if is_running; then
        echo "Limiter is already running."
        return
    fi
    
    # Try binary first, fall back to Python
    if [ -f "$filename" ]; then
        screen -Sdm Limiter "./$filename"
        echo "Limiter started (binary mode)."
    elif [ -f "limiter.py" ]; then
        screen -Sdm Limiter python3 limiter.py
        echo "Limiter started (Python mode)."
    else
        echo "No executable found. Downloading..."
        if download_program; then
            screen -Sdm Limiter "./$filename"
            echo "Limiter started."
        else
            echo "Please clone the repository and run from source:"
            echo "  git clone https://github.com/$REPO_OWNER/$REPO_NAME.git"
            echo "  cd $REPO_NAME"
            echo "  pip install -r requirements.txt"
            echo "  python3 limiter.py"
        fi
    fi
}

# Stop the limiter
stop_program() {
    if is_running; then
        screen -S Limiter -X quit
        echo "Limiter stopped."
    else
        echo "Limiter is not running."
    fi
}

# Attach to the running screen session
attach_program() {
    if is_running; then
        echo "Attaching to Limiter... (Press Ctrl-A then D to detach)"
        screen -r Limiter
    else
        echo "Limiter is not running."
    fi
}

# Create or update configuration
create_config() {
    mkdir -p config
    
    echo "===== Limiter Configuration ====="
    
    read -p "Enter panel domain (e.g., panel.example.com:8443): " domain
    read -p "Enter panel username: " username
    read -sp "Enter panel password: " password
    echo
    read -p "Enter Telegram bot token: " bot_token
    read -p "Enter your Telegram chat ID (admin): " admin_id
    read -p "Enter general IP limit (default: 2): " limit
    limit=${limit:-2}
    
    cat > config/config.json << EOF
{
    "panel": {
        "domain": "$domain",
        "username": "$username",
        "password": "$password"
    },
    "telegram": {
        "bot_token": "$bot_token",
        "admins": [$admin_id]
    },
    "limits": {
        "general": $limit,
        "special": {}
    },
    "except_users": [],
    "check_interval": 60,
    "time_to_active_users": 900,
    "country_code": ""
}
EOF
    
    echo "Configuration saved to config/config.json"
}

# Update Telegram bot token
update_token() {
    if [ ! -f "config/config.json" ]; then
        echo "Config not found. Please create configuration first."
        return 1
    fi
    
    read -p "Enter new Telegram bot token: " token
    jq --arg token "$token" '.telegram.bot_token = $token' config/config.json > config/tmp.json
    mv config/tmp.json config/config.json
    echo "Bot token updated."
}

# Update admin list
update_admins() {
    if [ ! -f "config/config.json" ]; then
        echo "Config not found. Please create configuration first."
        return 1
    fi
    
    read -p "Enter admin Telegram chat ID: " admin_id
    jq --argjson admin "$admin_id" '.telegram.admins = [$admin]' config/config.json > config/tmp.json
    mv config/tmp.json config/config.json
    echo "Admin updated."
}

# Main menu
show_menu() {
    echo ""
    echo "========== Limiter =========="
    echo "1. Start"
    echo "2. Stop"
    echo "3. Attach to logs"
    echo "4. Update"
    echo "5. Create/Edit config"
    echo "6. Update bot token"
    echo "7. Update admins"
    echo "8. Exit"
    echo "============================="
}

# Main
check_dependencies

if [ $# -eq 0 ]; then
    while true; do
        show_menu
        read -p "Choice: " choice
        
        case $choice in
            1) start_program ;;
            2) stop_program ;;
            3) attach_program ;;
            4) update_program ;;
            5) create_config ;;
            6) update_token ;;
            7) update_admins ;;
            8) exit 0 ;;
            *) echo "Invalid choice" ;;
        esac
    done
else
    case $1 in
        start) start_program ;;
        stop) stop_program ;;
        update) update_program ;;
        attach) attach_program ;;
        *) echo "Usage: $0 {start|stop|update|attach}" ;;
    esac
fi
