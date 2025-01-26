import json
import logging
from typing import List, Dict

logging.basicConfig(level=logging.INFO)

def extract_clip_transcripts(transcript: List[Dict], clips: List[Dict]) -> List[Dict]:
    """
    Extract transcript segments corresponding to video clips based on time ranges.
    
    Args:
        transcript: List of transcript entries with 'text', 'start', and 'duration'
        clips: List of clips with 'start' and 'end' times
        
    Returns:
        List of clip dictionaries with added 'transcript' containing matching entries
    """
    processed_clips = []
    
    for clip in clips:
        clip_start = clip['start']
        clip_end = clip['end']
        clip_entries = []
        
        for entry in transcript:
            entry_start = entry['start']
            entry_end = entry_start + entry['duration']
            
            # Check for time overlap between entry and clip
            if (entry_start < clip_end) and (entry_end > clip_start):
                clip_entries.append(entry)
        
        processed_clips.append({
            **clip,
            'transcript': clip_entries,
            'word_count': sum(len(entry['text'].split()) for entry in clip_entries)
        })
        
        logging.info(f"Clip {clip_start}-{clip_end}: Found {len(clip_entries)} transcript entries")
    
    return processed_clips

def save_clip_transcripts(clips: List[Dict], filename: str = "clip_transcripts.json"):
    """Save clip transcripts to a JSON file"""
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(clips, f, indent=2, ensure_ascii=False)
        logging.info(f"Saved clip transcripts to {filename}")
    except Exception as e:
        logging.error(f"Failed to save clip transcripts: {str(e)}")

if __name__ == "__main__":
    # This file is intended to be used as a module, not standalone
    logging.warning("This module is not designed to run standalone. Use it with main.py.")
