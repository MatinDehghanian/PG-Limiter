"""
CLI utility functions
"""
import json
import os
from typing import List, Tuple

import typer
from rich.console import Console
from rich.table import Table

console = Console()

FLAGS = {
    "name": ["-n", "--name"],
    "limit": ["-l", "--limit"],
    "username": ["-u", "--username"],
    "ip": ["-i", "--ip"],
}

CONFIG_FILE = "config.json"
BACKUP_FILE = "backup.json"


def print_table(table: Table, rows: List[Tuple]):
    """Print a rich table with rows"""
    for row in rows:
        table.add_row(*row)
    console.print(table)


def success(message: str):
    """Print a success message"""
    console.print(f"[green]✓[/green] {message}")


def error(message: str):
    """Print an error message and exit"""
    console.print(f"[red]✗[/red] {message}")
    raise typer.Exit(1)


def warning(message: str):
    """Print a warning message"""
    console.print(f"[yellow]⚠[/yellow] {message}")


def info(message: str):
    """Print an info message"""
    console.print(f"[blue]ℹ[/blue] {message}")


def load_config() -> dict:
    """Load the config file"""
    if not os.path.exists(CONFIG_FILE):
        error(f"Config file '{CONFIG_FILE}' not found. Run the limiter first to create it.")
    
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_config(config: dict):
    """Save the config file"""
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)


def load_backup() -> dict:
    """Load the backup file (for special limits)"""
    if not os.path.exists(BACKUP_FILE):
        return {"special": {}, "except_users": []}
    
    with open(BACKUP_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_backup(backup: dict):
    """Save the backup file"""
    with open(BACKUP_FILE, "w", encoding="utf-8") as f:
        json.dump(backup, f, indent=2)
