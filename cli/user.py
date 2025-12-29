"""
CLI commands for user management (special limits)
"""
from typing import Optional
import typer
from rich.table import Table

from cli.utils import (
    FLAGS,
    error,
    info,
    load_backup,
    load_config,
    print_table,
    save_backup,
    save_config,
    success,
    warning,
)

app = typer.Typer(no_args_is_help=True, help="Manage user limits")


@app.command(name="list")
def list_users(
    name: Optional[str] = typer.Option(
        None, *FLAGS["name"], help="Filter by username"
    ),
):
    """List all users with special limits"""
    config = load_config()
    backup = load_backup()
    
    # Get special limits from both config and backup
    special_limits = {}
    
    # From config (new format)
    if "limits" in config and "special" in config["limits"]:
        special_limits.update(config["limits"]["special"])
    
    # From backup
    if "special" in backup:
        special_limits.update(backup["special"])
    
    if name:
        special_limits = {k: v for k, v in special_limits.items() if name.lower() in k.lower()}
    
    if not special_limits:
        info("No users with special limits found.")
        return
    
    print_table(
        table=Table("Username", "Limit"),
        rows=[
            (username, str(limit))
            for username, limit in sorted(special_limits.items())
        ],
    )


@app.command(name="add")
def add_user(
    name: str = typer.Option(..., *FLAGS["name"], prompt=True, help="Username"),
    limit: int = typer.Option(..., *FLAGS["limit"], prompt=True, help="IP limit"),
):
    """Add or update a special limit for a user"""
    config = load_config()
    backup = load_backup()
    
    # Ensure structure exists
    if "limits" not in config:
        config["limits"] = {}
    if "special" not in config["limits"]:
        config["limits"]["special"] = {}
    if "special" not in backup:
        backup["special"] = {}
    
    # Check if exists
    existing = config["limits"]["special"].get(name) or backup["special"].get(name)
    if existing:
        warning(f"User '{name}' already has limit {existing}. Updating...")
    
    # Update both config and backup
    config["limits"]["special"][name] = limit
    backup["special"][name] = limit
    
    save_config(config)
    save_backup(backup)
    
    success(f"User '{name}' limit set to {limit}")


@app.command(name="delete")
def delete_user(
    name: str = typer.Option(..., *FLAGS["name"], prompt=True, help="Username to remove"),
):
    """Remove a user's special limit"""
    config = load_config()
    backup = load_backup()
    
    removed = False
    
    # Remove from config
    if "limits" in config and "special" in config["limits"]:
        if name in config["limits"]["special"]:
            del config["limits"]["special"][name]
            save_config(config)
            removed = True
    
    # Remove from backup
    if "special" in backup and name in backup["special"]:
        del backup["special"][name]
        save_backup(backup)
        removed = True
    
    if removed:
        success(f"User '{name}' special limit removed")
    else:
        error(f"User '{name}' not found in special limits")


@app.command(name="update")
def update_user(
    name: str = typer.Option(..., *FLAGS["name"], prompt=True, help="Username"),
    limit: int = typer.Option(..., *FLAGS["limit"], prompt=True, help="New IP limit"),
):
    """Update a user's special limit"""
    config = load_config()
    backup = load_backup()
    
    # Check if exists
    exists = False
    if "limits" in config and "special" in config["limits"]:
        if name in config["limits"]["special"]:
            exists = True
    if "special" in backup and name in backup["special"]:
        exists = True
    
    if not exists:
        error(f"User '{name}' not found. Use 'add' command instead.")
    
    # Update both
    if "limits" not in config:
        config["limits"] = {}
    if "special" not in config["limits"]:
        config["limits"]["special"] = {}
    if "special" not in backup:
        backup["special"] = {}
    
    config["limits"]["special"][name] = limit
    backup["special"][name] = limit
    
    save_config(config)
    save_backup(backup)
    
    success(f"User '{name}' limit updated to {limit}")


@app.command(name="show")
def show_user(
    name: str = typer.Option(..., *FLAGS["name"], prompt=True, help="Username to show"),
):
    """Show a specific user's limit"""
    config = load_config()
    backup = load_backup()
    
    limit = None
    
    # Check config
    if "limits" in config and "special" in config["limits"]:
        limit = config["limits"]["special"].get(name)
    
    # Check backup
    if limit is None and "special" in backup:
        limit = backup["special"].get(name)
    
    if limit is not None:
        info(f"User '{name}' has special limit: {limit}")
    else:
        # Show general limit
        general = config.get("limits", {}).get("general", 2)
        info(f"User '{name}' has no special limit. Using general limit: {general}")
