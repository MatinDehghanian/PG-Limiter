"""
CLI commands for configuration management
"""
from typing import Optional
import typer
from rich.table import Table

from cli.utils import (
    error,
    info,
    load_config,
    print_table,
    save_config,
    success,
    warning,
)

app = typer.Typer(no_args_is_help=True, help="Manage configuration")


@app.command(name="show")
def show_config():
    """Show current configuration"""
    config = load_config()
    
    # Panel info
    panel = config.get("panel", {})
    info("📡 Panel Configuration:")
    print(f"  Domain:   {panel.get('domain', 'Not set')}")
    print(f"  Username: {panel.get('username', 'Not set')}")
    print(f"  Password: {'*' * len(panel.get('password', '')) or 'Not set'}")
    print()
    
    # Limits
    limits = config.get("limits", {})
    info("🎯 Limits:")
    print(f"  General limit: {limits.get('general', 2)}")
    special = limits.get("special", {})
    if special:
        print(f"  Special limits: {len(special)} users")
    else:
        print("  Special limits: None")
    print()
    
    # Timing
    timing = config.get("timing", {})
    info("⏱️ Timing:")
    print(f"  Check interval:     {timing.get('check_interval', 120)}s")
    print(f"  Time to re-enable:  {timing.get('time_to_active_users', 300)}s")
    print()
    
    # Users
    users = config.get("users", {})
    except_users = users.get("except", [])
    info("👥 Users:")
    print(f"  Except users: {len(except_users)}")
    print()
    
    # Telegram
    telegram = config.get("telegram", {})
    info("📱 Telegram:")
    print(f"  Bot token: {'Set' if telegram.get('bot_token') else 'Not set'}")
    print(f"  Admins:    {len(telegram.get('admins', []))}")


@app.command(name="set-limit")
def set_general_limit(
    limit: int = typer.Option(..., "-l", "--limit", prompt=True, help="General IP limit"),
):
    """Set the general IP limit"""
    if limit < 1:
        error("Limit must be at least 1")
    
    config = load_config()
    
    if "limits" not in config:
        config["limits"] = {}
    
    config["limits"]["general"] = limit
    save_config(config)
    
    success(f"General limit set to {limit}")


@app.command(name="set-interval")
def set_check_interval(
    interval: int = typer.Option(..., "-i", "--interval", prompt=True, help="Check interval in seconds"),
):
    """Set the check interval"""
    if interval < 30:
        error("Interval must be at least 30 seconds")
    
    config = load_config()
    
    if "timing" not in config:
        config["timing"] = {}
    
    config["timing"]["check_interval"] = interval
    save_config(config)
    
    success(f"Check interval set to {interval} seconds")


@app.command(name="set-reenable-time")
def set_reenable_time(
    time: int = typer.Option(..., "-t", "--time", prompt=True, help="Time to re-enable users in seconds"),
):
    """Set the time to automatically re-enable disabled users"""
    if time < 60:
        error("Time must be at least 60 seconds")
    
    config = load_config()
    
    if "timing" not in config:
        config["timing"] = {}
    
    config["timing"]["time_to_active_users"] = time
    save_config(config)
    
    success(f"Re-enable time set to {time} seconds ({time // 60} minutes)")


@app.command(name="set-country")
def set_country_filter(
    code: Optional[str] = typer.Option(None, "-c", "--code", help="Country code to filter (e.g., IR, RU) or 'none' to disable"),
):
    """Set or disable country code filter"""
    config = load_config()
    
    if "settings" not in config:
        config["settings"] = {}
    
    if code is None or code.lower() == "none":
        config["settings"]["country_code"] = None
        save_config(config)
        success("Country filter disabled")
    else:
        code = code.upper()
        config["settings"]["country_code"] = code
        save_config(config)
        success(f"Country filter set to {code}")


@app.command(name="cleanup")
def cleanup_deleted_users():
    """Remove deleted users from limiter config (special limits, except users, disabled list)"""
    import asyncio
    from rich.progress import Progress, SpinnerColumn, TextColumn
    
    from utils.read_config import read_config
    from utils.types import PanelType
    from utils.panel_api import cleanup_deleted_users as do_cleanup
    
    async def run_cleanup():
        # Load config for panel data
        config = await read_config()
        panel_config = config.get("panel", {})
        
        if not panel_config.get("domain"):
            error("Panel not configured. Run the Telegram bot to set up panel config first.")
            return
        
        panel_data = PanelType(
            panel_username=panel_config.get("username", ""),
            panel_password=panel_config.get("password", ""),
            panel_domain=panel_config.get("domain", "")
        )
        
        info("🔍 Fetching users from panel...")
        result = await do_cleanup(panel_data)
        return result
    
    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            transient=True,
        ) as progress:
            progress.add_task(description="Cleaning up deleted users...", total=None)
            result = asyncio.run(run_cleanup())
        
        if result is None:
            return
        
        total_removed = (
            len(result["special_limits_removed"]) +
            len(result["except_users_removed"]) +
            len(result["disabled_users_removed"]) +
            len(result["user_groups_backup_removed"])
        )
        
        if total_removed == 0:
            success("✅ No deleted users found. Everything is clean!")
            return
        
        # Build result table
        table = Table(title="🧹 Cleanup Results")
        table.add_column("Category", style="cyan")
        table.add_column("Removed", style="green")
        table.add_column("Users", style="yellow")
        
        if result["special_limits_removed"]:
            users_str = ", ".join(result["special_limits_removed"][:5])
            if len(result["special_limits_removed"]) > 5:
                users_str += f" (+{len(result['special_limits_removed']) - 5} more)"
            table.add_row("Special Limits", str(len(result["special_limits_removed"])), users_str)
        
        if result["except_users_removed"]:
            users_str = ", ".join(result["except_users_removed"][:5])
            if len(result["except_users_removed"]) > 5:
                users_str += f" (+{len(result['except_users_removed']) - 5} more)"
            table.add_row("Except Users", str(len(result["except_users_removed"])), users_str)
        
        if result["disabled_users_removed"]:
            users_str = ", ".join(result["disabled_users_removed"][:5])
            if len(result["disabled_users_removed"]) > 5:
                users_str += f" (+{len(result['disabled_users_removed']) - 5} more)"
            table.add_row("Disabled Users", str(len(result["disabled_users_removed"])), users_str)
        
        if result["user_groups_backup_removed"]:
            users_str = ", ".join(result["user_groups_backup_removed"][:5])
            if len(result["user_groups_backup_removed"]) > 5:
                users_str += f" (+{len(result['user_groups_backup_removed']) - 5} more)"
            table.add_row("Groups Backup", str(len(result["user_groups_backup_removed"])), users_str)
        
        print_table(table)
        success(f"Total removed: {total_removed} user entries")
        
    except Exception as e:
        error(f"Cleanup failed: {e}")
