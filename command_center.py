#!/usr/bin/env python3
"""
Local Command Center CLI - Submit jobs to VPS and watch for completed results
"""
import os
import sys
import json
import time
import shutil
import httpx
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Confirm
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from config import VPS_HOST, GDRIVE_LOCAL_SYNC_PATH, RULES_DIR

console = Console()

def load_campaign_config(username: str) -> dict:
    """Load campaign config from rules/{username}.json"""
    config_path = Path(RULES_DIR) / f"{username}.json"
    if config_path.exists():
        with open(config_path) as f:
            return json.load(f)
    return {}

def submit_job(video_url: str, username: str):
    """Submit a video processing job to the VPS"""
    console.print(f"\n[bold cyan]Submitting job to VPS...[/bold cyan]")
    
    # Load campaign config
    campaign_config = load_campaign_config(username)
    
    # Send request to VPS
    try:
        response = httpx.post(
            f"{VPS_HOST}/api/v1/process",
            json={
                "video_url": video_url,
                "username": username,
                "campaign_config": campaign_config
            },
            timeout=30.0
        )
        response.raise_for_status()
        result = response.json()
        
        # Display success panel
        panel = Panel(
            f"[green]Job ID:[/green] {result['job_id']}\n"
            f"[green]Status:[/green] {result['status']}\n"
            f"[green]Message:[/green] {result['message']}\n\n"
            f"[yellow]The VPS is now processing your video.[/yellow]\n"
            f"[yellow]Use 'python command_center.py watch' to monitor for completed jobs.[/yellow]",
            title="[bold green]Job Submitted Successfully[/bold green]",
            border_style="green"
        )
        console.print(panel)
        
    except httpx.HTTPError as e:
        console.print(f"[bold red]Error:[/bold red] Failed to submit job: {e}")
        sys.exit(1)

def parse_metadata(metadata_path: Path) -> dict:
    """Parse metadata.json file"""
    with open(metadata_path) as f:
        return json.load(f)

def display_job_results(job_folder: Path):
    """Display results from a completed job folder"""
    console.print(f"\n[bold green]New job completed:[/bold green] {job_folder.name}")
    
    # Find all metadata files
    metadata_files = list(job_folder.glob("*_metadata.json"))
    
    if not metadata_files:
        console.print("[yellow]No metadata files found in job folder[/yellow]")
        return
    
    # Create results table
    table = Table(title=f"Results: {job_folder.name}", show_header=True, header_style="bold magenta")
    table.add_column("Candidate ID", style="cyan")
    table.add_column("Viral Title", style="green")
    table.add_column("Virality Score", justify="right", style="yellow")
    table.add_column("Duration", justify="right")
    table.add_column("Hook", style="dim")
    
    candidates = []
    for metadata_file in metadata_files:
        metadata = parse_metadata(metadata_file)
        candidates.append(metadata)
        
        virality_score = metadata.get('virality', {}).get('total_score', 0)
        duration = metadata.get('duration', 0)
        
        table.add_row(
            str(metadata['candidate_id']),
            metadata['viral_title'][:40],
            f"{virality_score}/100",
            f"{duration:.1f}s",
            metadata['hook'][:50]
        )
    
    console.print(table)
    
    # Ask to move to CapCut project folder
    if Confirm.ask("\n[bold cyan]Move files to CapCut project folder?[/bold cyan]"):
        username = job_folder.name.split('_')[0]
        project_dir = Path("projects") / username / job_folder.name
        project_dir.mkdir(parents=True, exist_ok=True)
        
        # Move all files
        for file in job_folder.glob("*"):
            if file.is_file():
                shutil.move(str(file), str(project_dir / file.name))
        
        console.print(f"[green]Files moved to:[/green] {project_dir}")
    else:
        console.print("[yellow]Files remain in Google Drive sync folder[/yellow]")

class JobWatcher(FileSystemEventHandler):
    """Watch for new job folders in Google Drive sync directory"""
    
    def __init__(self):
        self.processed_folders = set()
    
    def on_created(self, event):
        if event.is_directory:
            job_folder = Path(event.src_path)
            
            # Wait for folder to finish syncing (check for metadata files)
            time.sleep(2)
            metadata_files = list(job_folder.glob("*_metadata.json"))
            
            if metadata_files and job_folder.name not in self.processed_folders:
                self.processed_folders.add(job_folder.name)
                display_job_results(job_folder)

def watch_for_jobs():
    """Watch Google Drive sync folder for completed jobs"""
    sync_path = Path(GDRIVE_LOCAL_SYNC_PATH)
    
    if not sync_path.exists():
        console.print(f"[bold red]Error:[/bold red] Google Drive sync path does not exist: {sync_path}")
        console.print("[yellow]Please update GDRIVE_LOCAL_SYNC_PATH in config.py[/yellow]")
        sys.exit(1)
    
    console.print(f"[bold cyan]Watching for completed jobs in:[/bold cyan] {sync_path}")
    console.print("[dim]Press Ctrl+C to stop[/dim]\n")
    
    # Check for existing folders first
    watcher = JobWatcher()
    for folder in sync_path.iterdir():
        if folder.is_dir() and list(folder.glob("*_metadata.json")):
            display_job_results(folder)
            watcher.processed_folders.add(folder.name)
    
    # Start watching for new folders
    observer = Observer()
    observer.schedule(watcher, str(sync_path), recursive=False)
    observer.start()
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        console.print("\n[yellow]Stopped watching[/yellow]")
    
    observer.join()

def main():
    if len(sys.argv) < 2:
        console.print("[bold red]Usage:[/bold red]")
        console.print("  python command_center.py submit <video_url> <username>")
        console.print("  python command_center.py watch")
        sys.exit(1)
    
    command = sys.argv[1]
    
    if command == "submit":
        if len(sys.argv) != 4:
            console.print("[bold red]Usage:[/bold red] python command_center.py submit <video_url> <username>")
            sys.exit(1)
        
        video_url = sys.argv[2]
        username = sys.argv[3]
        submit_job(video_url, username)
    
    elif command == "watch":
        watch_for_jobs()
    
    else:
        console.print(f"[bold red]Unknown command:[/bold red] {command}")
        console.print("[yellow]Available commands:[/yellow] submit, watch")
        sys.exit(1)

if __name__ == "__main__":
    main()
