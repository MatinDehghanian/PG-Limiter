#!/usr/bin/env python3
"""
Limiter CLI - Command Line Interface for IP Limiter management

Usage:
    python cli_main.py [COMMAND] [OPTIONS]
    
Commands:
    user        Manage user special limits
    except      Manage except (whitelisted) users
    disabled    Manage disabled users
    config      Manage configuration

Examples:
    python cli_main.py user list
    python cli_main.py user add -n username -l 3
    python cli_main.py except add -n username
    python cli_main.py disabled list
    python cli_main.py config show
"""

import os
import sys

# Add the project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import typer
from typer._completion_shared import Shells

import cli.user
import cli.except_user
import cli.disabled
import cli.config


# ASCII art banner
BANNER = """
╔═══════════════════════════════════════════╗
║         🛡️  LIMITER CLI  🛡️               ║
║     IP Connection Limiter Management      ║
╚═══════════════════════════════════════════╝
"""


app = typer.Typer(
    no_args_is_help=True, 
    add_completion=False,
    help="Limiter CLI - Manage IP limits, users, and configuration"
)

# Add subcommands
app.add_typer(cli.user.app, name="user", help="Manage user special limits")
app.add_typer(cli.except_user.app, name="except", help="Manage except (whitelisted) users")
app.add_typer(cli.disabled.app, name="disabled", help="Manage disabled users")
app.add_typer(cli.config.app, name="config", help="Manage configuration")


# Hidden completion app
app_completion = typer.Typer(
    no_args_is_help=True,
    help="Generate and install completion scripts.",
    hidden=True,
)
app.add_typer(app_completion, name="completion")


def get_default_shell() -> Shells:
    """Find the default shell"""
    shell = os.environ.get("SHELL")
    if shell:
        shell = shell.split("/")[-1]
        if shell in Shells.__members__:
            return getattr(Shells, shell)
    return Shells.bash


@app_completion.command(
    help="Show completion for the specified shell, to copy or customize it."
)
def show(
    ctx: typer.Context,
    shell: Shells = typer.Option(
        None, help="The shell to install completion for.", case_sensitive=False
    ),
) -> None:
    if shell is None:
        shell = get_default_shell()
    typer.completion.show_callback(ctx, None, shell)


@app_completion.command(help="Install completion for the specified shell.")
def install(
    ctx: typer.Context,
    shell: Shells = typer.Option(
        None, help="The shell to install completion for.", case_sensitive=False
    ),
) -> None:
    if shell is None:
        shell = get_default_shell()
    typer.completion.install_callback(ctx, None, shell)


@app.command(name="status")
def status():
    """Show current limiter status summary"""
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    import json
    import time
    
    console = Console()
    console.print(BANNER)
    
    # Load configs
    try:
        with open("config.json", "r") as f:
            config = json.load(f)
    except FileNotFoundError:
        console.print("[red]Config file not found. Run the limiter first.[/red]")
        return
    
    # Disabled users
    disabled_count = 0
    try:
        with open(".disable_users.json", "r") as f:
            data = json.load(f)
            if "disabled_users" in data:
                disabled_count = len(data["disabled_users"])
            elif "disable_user" in data:
                disabled_count = len(data["disable_user"])
    except FileNotFoundError:
        pass
    
    # Special limits
    special_count = 0
    if "limits" in config and "special" in config["limits"]:
        special_count = len(config["limits"]["special"])
    
    # Except users
    except_count = 0
    if "users" in config and "except" in config["users"]:
        except_count = len(config["users"]["except"])
    
    # Create status table
    table = Table(title="Limiter Status", show_header=False)
    table.add_column("Key", style="cyan")
    table.add_column("Value", style="green")
    
    general_limit = config.get("limits", {}).get("general", 2)
    check_interval = config.get("timing", {}).get("check_interval", 120)
    reenable_time = config.get("timing", {}).get("time_to_active_users", 300)
    
    table.add_row("General Limit", str(general_limit))
    table.add_row("Check Interval", f"{check_interval}s")
    table.add_row("Re-enable Time", f"{reenable_time}s ({reenable_time // 60}m)")
    table.add_row("─" * 20, "─" * 20)
    table.add_row("Special Limits", str(special_count))
    table.add_row("Except Users", str(except_count))
    table.add_row("Disabled Users", f"[red]{disabled_count}[/red]" if disabled_count else "0")
    
    console.print(table)
    
    # Quick tips
    console.print("\n[dim]Quick commands:[/dim]")
    console.print("  [cyan]python cli_main.py user list[/cyan]      - List special limits")
    console.print("  [cyan]python cli_main.py disabled list[/cyan]  - List disabled users")
    console.print("  [cyan]python cli_main.py config show[/cyan]    - Show configuration")


@app.command(name="version")
def version():
    """Show CLI version"""
    from rich.console import Console
    console = Console()
    console.print(BANNER)
    console.print("Version: 1.0.0")


if __name__ == "__main__":
    typer.completion.completion_init()
    app(prog_name=os.environ.get("CLI_PROG_NAME", "limiter"))
