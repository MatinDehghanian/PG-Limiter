"""
CLI commands for disabled users management
"""
import json
import os
from typing import Optional
import typer
from rich.table import Table
import time

from cli.utils import (
    FLAGS,
    console,
    error,
    info,
    print_table,
    success,
    warning,
)

app = typer.Typer(no_args_is_help=True, help="Manage disabled users")

DISABLED_USERS_FILE = ".disable_users.json"


def load_disabled_users() -> dict:
    """Load disabled users from file"""
    if not os.path.exists(DISABLED_USERS_FILE):
        return {}
    
    try:
        with open(DISABLED_USERS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            # Support both old and new format
            if "disabled_users" in data:
                return data["disabled_users"]
            elif "disable_user" in data:
                # Old format - convert
                old_users = data.get("disable_user", [])
                if isinstance(old_users, list):
                    return {user: time.time() for user in old_users}
                return old_users
            return {}
    except Exception as e:
        error(f"Failed to load disabled users: {e}")


def save_disabled_users(users: dict):
    """Save disabled users to file"""
    with open(DISABLED_USERS_FILE, "w", encoding="utf-8") as f:
        json.dump({"disabled_users": users}, f, indent=2)


@app.command(name="list")
def list_disabled_users(
    name: Optional[str] = typer.Option(
        None, *FLAGS["name"], help="Filter by username"
    ),
):
    """List all currently disabled users"""
    users = load_disabled_users()
    
    if name:
        users = {k: v for k, v in users.items() if name.lower() in k.lower()}
    
    if not users:
        info("No disabled users found.")
        return
    
    current_time = time.time()
    rows = []
    
    for username, disabled_time in sorted(users.items(), key=lambda x: x[1], reverse=True):
        elapsed = int(current_time - disabled_time)
        minutes = elapsed // 60
        seconds = elapsed % 60
        disabled_at = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(disabled_time))
        rows.append((username, disabled_at, f"{minutes}m {seconds}s"))
    
    print_table(
        table=Table("Username", "Disabled At", "Elapsed"),
        rows=rows,
    )
    
    info(f"Total: {len(users)} disabled users")


@app.command(name="enable")
def enable_user(
    name: str = typer.Option(..., *FLAGS["name"], prompt=True, help="Username to enable"),
):
    """Enable a specific disabled user (remove from disabled list)
    
    Note: This only removes from the local tracking file.
    You may need to manually enable the user on the panel if needed.
    """
    users = load_disabled_users()
    
    if name not in users:
        error(f"User '{name}' is not in the disabled list")
    
    del users[name]
    save_disabled_users(users)
    
    success(f"User '{name}' removed from disabled list")
    warning("Note: If the user is disabled on the panel, you may need to enable them manually.")


@app.command(name="enable-all")
def enable_all_users():
    """Enable all disabled users (clear the disabled list)"""
    users = load_disabled_users()
    
    if not users:
        info("No disabled users to enable.")
        return
    
    count = len(users)
    save_disabled_users({})
    
    success(f"Cleared {count} users from disabled list")
    warning("Note: If users are disabled on the panel, you may need to enable them manually.")


@app.command(name="info")
def show_user_info(
    name: str = typer.Option(..., *FLAGS["name"], prompt=True, help="Username to show"),
):
    """Show info about a specific disabled user"""
    users = load_disabled_users()
    
    if name not in users:
        info(f"User '{name}' is not in the disabled list")
        return
    
    disabled_time = users[name]
    current_time = time.time()
    elapsed = int(current_time - disabled_time)
    
    disabled_at = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(disabled_time))
    hours = elapsed // 3600
    minutes = (elapsed % 3600) // 60
    seconds = elapsed % 60
    
    console.print(f"\n[bold]User Info: {name}[/bold]")
    console.print(f"  Status:      [red]Disabled[/red]")
    console.print(f"  Disabled at: {disabled_at}")
    console.print(f"  Elapsed:     {hours}h {minutes}m {seconds}s")
