#!/usr/bin/env python3
"""
Rich CLI for AI Shorts Generator
God-tier terminal interface for local video clipping
"""
import sys
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn, TaskProgressColumn
from rich.prompt import Confirm
from rich import print as rprint
from yt_dlp import YoutubeDL
import traceback as tb_module

console = Console()

from pipeline import mine_phase1, process_candidate, extract_video_id


def get_video_metadata(video_url):
    """Fetch video metadata using yt-dlp"""
    ydl_opts = {
        'quiet': True,
        'skip_download': True,
        'no_warnings': True,
    }
    
    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=False)
            return {
                'title': info.get('title'),
                'uploader': info.get('uploader'),
                'channel': info.get('channel'),
                'channel_id': info.get('channel_id'),
                'duration': info.get('duration'),
                'view_count': info.get('view_count'),
            }
    except Exception as e:
        console.print(f"[yellow]Warning: Could not fetch metadata: {e}[/yellow]")
        return None


def display_candidates(candidates, video_url, metadata=None):
    """Display Phase 1 results in a beautiful table"""
    
    info_lines = [f"[bold]Video:[/bold] {video_url}"]
    if metadata:
        if metadata.get('title'):
            info_lines.append(f"[bold]Title:[/bold] {metadata['title']}")
        if metadata.get('uploader'):
            info_lines.append(f"[bold]Username:[/bold] {metadata['uploader']}")
    info_lines.append(f"[bold]Found:[/bold] {len(candidates)} candidates")
    
    console.print(Panel("\n".join(info_lines), expand=False))
    
    table = Table(title="[bold cyan]⛏️  Mining Results[/bold cyan]", show_lines=True)
    table.add_column("ID", style="cyan bold", width=4)
    table.add_column("Hook Summary", style="white", width=40)
    table.add_column("Duration", justify="center", style="yellow")
    table.add_column("Virality", justify="center", style="green bold")
    table.add_column("Heatmap", justify="center", style="blue")
    table.add_column("Edit Mode", style="magenta")
    table.add_column("Viral Title", style="yellow bold")
    
    for c in candidates:
        virality = c.get('virality', {})
        heatmap = c.get('heatmap', {})
        edit_tech = c.get('edit_techniques', {})
        
        edit_mode = edit_tech.get('edit_mode', 'standard')
        if edit_mode == 'loop_hook':
            loop_meta = edit_tech.get('seamless_loop', {}).get('metadata', {})
            sentence = loop_meta.get('sentence', '')
            edit_display = f"Loop: {sentence[:25]}..." if len(sentence) > 25 else f"Loop: {sentence}"
        elif edit_mode == 'cold_open':
            cold_meta = edit_tech.get('cold_open_hook', {}).get('metadata', {})
            text = cold_meta.get('text', '') if cold_meta else ''
            edit_display = f"Cold Open: {text[:20]}..." if len(text) > 20 else f"Cold Open: {text}" if text else "Cold Open"
        else:
            edit_display = "Standard"
        
        table.add_row(
            str(c['candidate_id']),
            c.get('hook_summary', '')[:38] + '..' if len(c.get('hook_summary', '')) > 38 else c.get('hook_summary', ''),
            f"{c.get('duration', 0):.0f}s",
            f"{virality.get('total_score', 0)}/100",
            f"{heatmap.get('avg_norm', 0):.2f}" if heatmap.get('avg_norm') else "N/A",
            edit_display,
            c.get('viral_title', '')[:20]
        )
    
    console.print(table)
    
    broll_table = Table(title="[bold cyan]🎬 B-Roll Search Queries[/bold cyan]", show_lines=True)
    broll_table.add_column("Candidate", style="cyan")
    broll_table.add_column("Timestamp", style="yellow")
    broll_table.add_column("Search Query", style="white")
    
    for c in candidates:
        broll = c.get('broll_opportunities', [])
        for b in broll:
            broll_table.add_row(
                str(c['candidate_id']),
                b.get('timestamp_range', ''),
                b.get('search_query', '')
            )
    
    if broll:
        console.print(broll_table)


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='AI Shorts Generator CLI')
    parser.add_argument('video_url', help='YouTube video URL')
    parser.add_argument('--rules', dest='rule_profile', help='Rules profile name (e.g., abulayha)', default=None)
    parser.add_argument('-l', '--limit', type=int, help='Limit number of final clips to render', default=None)
    parser.add_argument('--min', type=float, help='Minimum clip duration in seconds', default=None)
    parser.add_argument('--max', type=float, help='Maximum clip duration in seconds', default=None)
    parser.add_argument('--min-clips', type=int, help='Minimum number of clips to generate (overrides duration formula)', default=None)
    parser.add_argument('--max-clips', type=int, help='Maximum number of clips to generate (overrides duration formula)', default=None)
    
    args = parser.parse_args()
    
    limit = args.limit
    if limit is not None and limit < 1:
        console.print("[bold red]❌ Error: --limit must be >= 1[/bold red]")
        sys.exit(1)
    
    if args.min is not None and args.min < 0:
        console.print("[bold red]❌ Error: --min must be >= 0[/bold red]")
        sys.exit(1)
    
    if args.max is not None and args.max < 0:
        console.print("[bold red]❌ Error: --max must be >= 0[/bold red]")
        sys.exit(1)
    
    if args.min is not None and args.max is not None and args.min > args.max:
        console.print("[bold red]❌ Error: --min cannot be greater than --max[/bold red]")
        sys.exit(1)
    
    if args.min_clips is not None and args.min_clips < 1:
        console.print("[bold red]❌ Error: --min-clips must be >= 1[/bold red]")
        sys.exit(1)
    
    if args.max_clips is not None and args.max_clips < 1:
        console.print("[bold red]❌ Error: --max-clips must be >= 1[/bold red]")
        sys.exit(1)
    
    if args.min_clips is not None and args.max_clips is not None and args.min_clips > args.max_clips:
        console.print("[bold red]❌ Error: --min-clips cannot be greater than --max-clips[/bold red]")
        sys.exit(1)
    
    os.makedirs("temp", exist_ok=True)
    os.makedirs("output", exist_ok=True)
    os.makedirs("rules", exist_ok=True)
    
    if args.rule_profile:
        rules_path = os.path.join("rules", args.rule_profile, "rules.json")
        if not os.path.exists(rules_path):
            console.print(f"[bold red]❌ Error: Rules profile '{args.rule_profile}' not found at {rules_path}[/bold red]")
            sys.exit(1)
    
    console.print(Panel.fit(
        "[bold green]🎬 AI Shorts Generator[/bold green]\n[dim]God-Tier CLI[/dim]",
        border_style="green"
    ))
    
    metadata = None
    if args.rule_profile:
        try:
            metadata = get_video_metadata(args.video_url)
        except Exception as e:
            print(f"Warning: Could not fetch video metadata: {e}")
            pass
    
    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(bar_width=40),
            TimeElapsedColumn(),
            console=console
        ) as progress:
            
            download_task = progress.add_task("[cyan]Downloading video...", total=None)
            candidates, transcript, campaign_config, full_video_words = mine_phase1(
                args.video_url,
                args.rule_profile,
                limit=limit,
                min_clips=args.min_clips,
                max_clips=args.max_clips,
            )
            progress.update(download_task, completed=True)
            
            if args.min is not None or args.max is not None:
                original_count = len(candidates)
                candidates = [c for c in candidates if 
                             (args.min is None or c.get('duration', 0) >= args.min) and
                             (args.max is None or c.get('duration', 0) <= args.max)]
                filtered_count = original_count - len(candidates)
                if filtered_count > 0:
                    console.print(f"[yellow]Filtered out {filtered_count} candidates by duration[/yellow]")
            
            display_candidates(candidates, args.video_url, metadata)
            
            if not candidates:
                console.print("[bold red]❌ No valid candidates found![/bold red]")
                sys.exit(1)
            
            proceed = Confirm.ask(
                "\n[bold yellow]Do you want to proceed with rendering these clips?[/bold yellow]"
            )
            
            if not proceed:
                console.print("[bold blue]👋 Cancelled. Run again when ready.[/bold blue]")
                sys.exit(0)
            
            render_candidates = candidates[:limit] if limit is not None else candidates
            render_count = len(render_candidates)
            use_parallel = render_count > 1
            
            if use_parallel:
                console.print(f"[cyan]⚙️  Parallel rendering enabled ({render_count} clips, workers=2)[/cyan]")
            
            task_ids = {}
            
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(bar_width=40),
                TaskProgressColumn(),
                TimeElapsedColumn(),
                console=console,
                transient=False,
            ) as progress:
                
                render_task = progress.add_task("[green]Rendering clips...", total=render_count)
                
                def _run_clip(c):
                    return process_candidate(
                        args.video_url,
                        args.rule_profile,
                        c,
                        full_video_words=full_video_words,
                        transcript=transcript,
                    )
                
                if use_parallel:
                    with ThreadPoolExecutor(max_workers=2) as executor:
                        futures = {
                            executor.submit(_run_clip, c): c 
                            for c in render_candidates
                        }
                        
                        for fut in as_completed(futures):
                            candidate = futures[fut]
                            cid = candidate.get('candidate_id', '?')
                            progress.update(
                                render_task,
                                description=f"[cyan]Rendering Candidate {cid}..."
                            )
                            try:
                                result = fut.result()
                                progress.advance(render_task)
                            except Exception as e:
                                progress.advance(render_task)
                                console.print(f"[red]❌ Candidate {cid} failed: {e}[/red]")
                else:
                    for i, c in enumerate(render_candidates):
                        cid = c.get('candidate_id', '?')
                        progress.update(
                            render_task,
                            description=f"[green]Rendering Candidate {cid}..."
                        )
                        try:
                            result = process_candidate(
                                args.video_url,
                                args.rule_profile,
                                c,
                                full_video_words=full_video_words,
                                transcript=transcript,
                            )
                            progress.advance(render_task)
                        except Exception as e:
                            progress.advance(render_task)
                            console.print(f"[red]❌ Candidate {cid} failed: {e}[/red]")
                
                progress.update(render_task, description="[bold green]✓ Complete!", completed=True)
            
            progress.update(render_task, description="[bold green]✓ Complete!", completed=True)
        
        console.print(Panel.fit(
            "[bold green]🎉 Pipeline Complete![/bold green]\n[dim]All clips rendered successfully[/dim]",
            border_style="green"
        ))
        
    except Exception as e:
        console.print(Panel(f"[bold red]❌ Error:[/bold red] {e}", border_style="red"))
        sys.exit(1)


if __name__ == "__main__":
    main()
