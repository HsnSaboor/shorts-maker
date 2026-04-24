#!/usr/bin/env python3
"""
Test script to verify the hybrid architecture setup
Run this on both laptop and VPS to ensure everything is configured correctly
"""
import os
import sys
import subprocess
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()

def check_rclone():
    """Check if rclone is installed and configured"""
    try:
        result = subprocess.run(['rclone', 'version'], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            console.print("[green]✓[/green] rclone is installed")
            
            # Check if gdrive remote exists
            result = subprocess.run(['rclone', 'listremotes'], capture_output=True, text=True, timeout=5)
            if 'gdrive:' in result.stdout:
                console.print("[green]✓[/green] gdrive remote is configured")
                return True
            else:
                console.print("[red]✗[/red] gdrive remote not found in rclone config")
                console.print("[yellow]Run: rclone config[/yellow]")
                return False
        else:
            console.print("[red]✗[/red] rclone is not working properly")
            return False
    except FileNotFoundError:
        console.print("[red]✗[/red] rclone is not installed")
        console.print("[yellow]Install: curl https://rclone.org/install.sh | sudo bash[/yellow]")
        return False
    except Exception as e:
        console.print(f"[red]✗[/red] Error checking rclone: {e}")
        return False

def check_python_deps():
    """Check if required Python packages are installed"""
    required = ['httpx', 'rich', 'fastapi', 'uvicorn', 'watchdog', 'deepgram']
    missing = []
    
    for pkg in required:
        try:
            __import__(pkg)
            console.print(f"[green]✓[/green] {pkg} is installed")
        except ImportError:
            console.print(f"[red]✗[/red] {pkg} is not installed")
            missing.append(pkg)
    
    if missing:
        console.print(f"\n[yellow]Install missing packages:[/yellow]")
        console.print(f"pip install {' '.join(missing)}")
        return False
    return True

def check_env_vars():
    """Check if required environment variables are set"""
    from config import VPS_HOST, GDRIVE_REMOTE_NAME, GDRIVE_LOCAL_SYNC_PATH, DEEPGRAM_API_KEYS
    
    table = Table(title="Environment Configuration", show_header=True)
    table.add_column("Variable", style="cyan")
    table.add_column("Value", style="yellow")
    table.add_column("Status", style="green")
    
    checks = [
        ("VPS_HOST", VPS_HOST, VPS_HOST != "http://localhost:8000"),
        ("GDRIVE_REMOTE_NAME", GDRIVE_REMOTE_NAME, GDRIVE_REMOTE_NAME == "gdrive"),
        ("GDRIVE_LOCAL_SYNC_PATH", GDRIVE_LOCAL_SYNC_PATH, Path(GDRIVE_LOCAL_SYNC_PATH).exists()),
        ("DEEPGRAM_API_KEYS", f"{len(DEEPGRAM_API_KEYS)} keys", len(DEEPGRAM_API_KEYS) > 0),
    ]
    
    all_ok = True
    for var, value, ok in checks:
        status = "[green]✓[/green]" if ok else "[red]✗[/red]"
        table.add_row(var, str(value)[:50], status)
        if not ok:
            all_ok = False
    
    console.print(table)
    return all_ok

def check_directories():
    """Check if required directories exist"""
    dirs = ['temp', 'output', 'rules', 'projects']
    all_ok = True
    
    for d in dirs:
        path = Path(d)
        if path.exists():
            console.print(f"[green]✓[/green] {d}/ directory exists")
        else:
            console.print(f"[yellow]![/yellow] {d}/ directory missing (will be created)")
            path.mkdir(exist_ok=True)
    
    return all_ok

def test_vps_connection():
    """Test connection to VPS server"""
    try:
        import httpx
        from config import VPS_HOST
        
        console.print(f"\n[cyan]Testing VPS connection to {VPS_HOST}...[/cyan]")
        response = httpx.get(f"{VPS_HOST}/health", timeout=5.0)
        
        if response.status_code == 200:
            console.print("[green]✓[/green] VPS server is reachable")
            return True
        else:
            console.print(f"[red]✗[/red] VPS returned status {response.status_code}")
            return False
    except Exception as e:
        console.print(f"[red]✗[/red] Cannot reach VPS: {e}")
        console.print("[yellow]Make sure vps_server.py is running on the VPS[/yellow]")
        return False

def main():
    console.print(Panel.fit(
        "[bold cyan]Hybrid Architecture Setup Verification[/bold cyan]\n"
        "[dim]Checking all components...[/dim]",
        border_style="cyan"
    ))
    
    results = {
        "rclone": check_rclone(),
        "python_deps": check_python_deps(),
        "env_vars": check_env_vars(),
        "directories": check_directories(),
    }
    
    # Only test VPS connection on laptop (not on VPS itself)
    if '--skip-vps' not in sys.argv:
        results["vps_connection"] = test_vps_connection()
    
    console.print("\n" + "="*60)
    
    if all(results.values()):
        console.print(Panel(
            "[bold green]All checks passed![/bold green]\n"
            "[dim]Your hybrid architecture is ready to use.[/dim]",
            border_style="green"
        ))
        console.print("\n[bold]Next steps:[/bold]")
        console.print("  • On VPS: python vps_server.py")
        console.print("  • On Laptop: python command_center.py submit <url> <username>")
        console.print("  • On Laptop: python command_center.py watch")
    else:
        console.print(Panel(
            "[bold red]Some checks failed[/bold red]\n"
            "[dim]Please fix the issues above before proceeding.[/dim]",
            border_style="red"
        ))
        sys.exit(1)

if __name__ == "__main__":
    main()
