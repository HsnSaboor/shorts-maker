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


def extract_clip_words_from_segments(full_video_words, source_segments):
    """
    Extract word timestamps using explicit source->timeline segment mapping.

    Args:
        full_video_words: List of word dicts with {word, start, end, speaker}
        source_segments: List of segment dicts with
            {source_start, source_end, timeline_start, timeline_end}

    Returns:
        List of words mapped into candidate timeline coordinates
    """
    if not source_segments:
        return []

    clip_words = []
    for seg in source_segments:
        src_start = float(seg["source_start"])
        src_end = float(seg["source_end"])
        timeline_start = float(seg["timeline_start"])

        for w in full_video_words:
            w_start = float(w["start"])
            if src_start <= w_start <= src_end:
                mapped = dict(w)
                mapped["start"] = timeline_start + (float(w["start"]) - src_start)
                mapped["end"] = timeline_start + (float(w["end"]) - src_start)
                clip_words.append(mapped)

    clip_words.sort(key=lambda x: x["start"])
    return clip_words
