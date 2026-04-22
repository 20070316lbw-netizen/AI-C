import sys
from rich.console import Console

console = Console()

def print_error(message: str, hint: str = None) -> None:
    """Print an error message in a consistent format."""
    console.print(f"[bold red][✗] {message}[/bold red]")
    if hint:
        console.print(f"    [dim]hint: {hint}[/dim]")

def print_warning(message: str) -> None:
    """Print a warning message in a consistent format."""
    console.print(f"[bold yellow][!] {message}[/bold yellow]")

def print_ok(message: str) -> None:
    """Print a success message in a consistent format."""
    console.print(f"[bold green][✓] {message}[/bold green]")
