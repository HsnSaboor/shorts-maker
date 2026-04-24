"""Utilities for extracting clip-level transcripts from full video transcripts"""

def extract_clip_words(full_video_words, candidate, transcript):
    """
    Extract word-level timestamps for a specific clip from full video transcript
    
    Args:
        full_video_words: List of word dicts with {word, start, end, speaker}
        candidate: Candidate dict with segments
        transcript: YouTube transcript for timing reference
    
    Returns:
        List of words for the clip with timestamps adjusted to clip start
    """
    segments = candidate['segments']
    
    # Get clip boundaries from segments
    first_seg = segments[0]
    last_seg = segments[-1]
    
    if isinstance(first_seg, dict):
        clip_start = first_seg['start']
    else:
        seg_str = str(first_seg)
        idx = int(seg_str.split('-')[0]) if '-' in seg_str else int(seg_str)
        clip_start = transcript[idx]['start']
    
    if isinstance(last_seg, dict):
        clip_end = last_seg['end']
    else:
        seg_str = str(last_seg)
        idx = int(seg_str.split('-')[-1]) if '-' in seg_str else int(seg_str)
        clip_end = transcript[idx]['end']
    
    # Extract words within clip boundaries
    clip_words = [
        {**w, 'start': w['start'] - clip_start, 'end': w['end'] - clip_start}
        for w in full_video_words
        if clip_start <= w['start'] <= clip_end
    ]
    
    return clip_words
