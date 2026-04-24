"""
Checkpoint/Resume System for Pipeline
Saves state at each stage to enable resuming from any point
"""
import json
import hashlib
from pathlib import Path
from datetime import datetime
from config import TEMP_DIR

CHECKPOINT_DIR = Path(TEMP_DIR) / "checkpoints"
CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)

def get_video_id(video_url):
    """Extract video ID from URL"""
    if 'v=' in video_url:
        return video_url.split('v=')[1].split('&')[0]
    return video_url

def get_checkpoint_path(video_url, stage):
    """Get checkpoint file path for a specific stage"""
    video_id = get_video_id(video_url)
    return CHECKPOINT_DIR / f"{video_id}_{stage}.json"

def save_checkpoint(video_url, stage, data):
    """Save checkpoint data for a stage"""
    checkpoint_path = get_checkpoint_path(video_url, stage)
    checkpoint_data = {
        'video_url': video_url,
        'stage': stage,
        'timestamp': datetime.now().isoformat(),
        'data': data
    }
    with open(checkpoint_path, 'w') as f:
        json.dump(checkpoint_data, f, indent=2)
    return checkpoint_path

def load_checkpoint(video_url, stage):
    """Load checkpoint data for a stage, returns None if not found"""
    checkpoint_path = get_checkpoint_path(video_url, stage)
    if not checkpoint_path.exists():
        return None
    
    with open(checkpoint_path, 'r') as f:
        checkpoint_data = json.load(f)
    
    return checkpoint_data['data']

def checkpoint_exists(video_url, stage):
    """Check if checkpoint exists for a stage"""
    return get_checkpoint_path(video_url, stage).exists()

def list_checkpoints(video_url):
    """List all available checkpoints for a video"""
    video_id = get_video_id(video_url)
    checkpoints = []
    for cp_file in CHECKPOINT_DIR.glob(f"{video_id}_*.json"):
        with open(cp_file, 'r') as f:
            data = json.load(f)
            checkpoints.append({
                'stage': data['stage'],
                'timestamp': data['timestamp'],
                'path': str(cp_file)
            })
    return sorted(checkpoints, key=lambda x: x['timestamp'])

def clear_checkpoints(video_url, stage=None):
    """Clear checkpoints for a video (all or specific stage)"""
    video_id = get_video_id(video_url)
    if stage:
        checkpoint_path = get_checkpoint_path(video_url, stage)
        if checkpoint_path.exists():
            checkpoint_path.unlink()
    else:
        for cp_file in CHECKPOINT_DIR.glob(f"{video_id}_*.json"):
            cp_file.unlink()
