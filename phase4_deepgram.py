"""
Phase 4: Deepgram Transcription & Diarization
Uses Deepgram API for word-level timestamps and speaker diarization
Supports multi-key rotation and chunking for long-form audio
"""
import httpx
import time
from pathlib import Path
from config import DEEPGRAM_API_KEYS

def transcribe_with_deepgram(audio_path: str, chunk_info: dict = None) -> dict:
    """
    Transcribe audio using Deepgram API with diarization and word-level timestamps
    Supports multi-key rotation for rate limiting
    
    Args:
        audio_path: Path to audio file
        chunk_info: Optional dict with 'start_offset' for chunked transcriptions
    
    Returns:
        dict with 'words' list containing {word, start, end, speaker}
    """
    if not DEEPGRAM_API_KEYS:
        raise Exception("No Deepgram API keys configured")
    
    url = "https://api.deepgram.com/v1/listen"
    
    with open(audio_path, 'rb') as f:
        audio_data = f.read()
    
    params = {
        'model': 'nova-3',
        'smart_format': 'true',
        'diarize': 'true',
        'punctuate': 'true',
        'utterances': 'true',
        'filler_words': 'false'
    }
    
    headers = {
        'Content-Type': 'audio/mpeg'
    }
    
    last_exception = None
    response = None
    
    for key_idx, api_key in enumerate(DEEPGRAM_API_KEYS):
        headers['Authorization'] = f'Token {api_key}'
        
        for retry in range(3):
            try:
                response = httpx.post(
                    url,
                    params=params,
                    headers=headers,
                    content=audio_data,
                    timeout=300.0
                )
                
                if response.status_code == 408:
                    if retry < 2:
                        print(f"  Timeout on key {key_idx}, retry {retry+1}/3...")
                        time.sleep(2)
                        continue
                    print(f"  Timeout on key {key_idx} after 3 retries, trying next...")
                    response = None
                    break
                
                if response.status_code == 429:
                    print(f"  Rate limited on key {key_idx}, trying next...")
                    response = None
                    break
                if response.status_code == 401:
                    print(f"  Invalid key {key_idx}, trying next...")
                    response = None
                    break
                    
                response.raise_for_status()
                break
                
            except Exception as e:
                last_exception = e
                response = None
                if key_idx < len(DEEPGRAM_API_KEYS) - 1:
                    print(f"  Error on key {key_idx}: {e}, trying next...")
                    break
                raise
        
        if response and response.status_code < 400:
            break
    
    if not response or response.status_code >= 400:
        raise Exception(f"All Deepgram keys failed: {last_exception}")
    
    result = response.json()
    
    words = []
    alternatives = result['results']['channels'][0]['alternatives'][0]
    
    start_offset = chunk_info.get('start_offset', 0) if chunk_info else 0
    
    for word_obj in alternatives.get('words', []):
        words.append({
            'word': word_obj['punctuated_word'],
            'start': word_obj['start'] + start_offset,
            'end': word_obj['end'] + start_offset,
            'speaker': word_obj.get('speaker', 0),
            'confidence': word_obj.get('confidence', 1.0)
        })
    
    return {
        'words': words,
        'full_transcript': alternatives['transcript']
    }


def merge_chunked_transcriptions(results: list, overlap_seconds: float = 300.0) -> dict:
    """
    Merge multiple chunked Deepgram results with overlap deduplication
    
    Args:
        results: List of dicts with 'words' arrays from each chunk
        overlap_seconds: Overlap window in seconds (default 5 minutes = 300s)
    
    Returns:
        Merged dict with deduplicated words array
    """
    if not results:
        return {'words': [], 'full_transcript': ''}
    
    if len(results) == 1:
        return results[0]
    
    merged_words = []
    
    for chunk_idx, chunk_result in enumerate(results):
        chunk_words = chunk_result.get('words', [])
        if not chunk_words:
            continue
        
        if chunk_idx == 0:
            merged_words.extend(chunk_words)
            continue
        
        cutoff_time = chunk_words[0]['start'] + overlap_seconds
        
        for word in chunk_words:
            if word['start'] >= cutoff_time:
                merged_words.append(word)
            else:
                text = word['word'].lower().strip()
                existing = next((w for w in merged_words[-10:] if w['word'].lower().strip() == text), None)
                if not existing:
                    merged_words.append(word)
    
    full_transcript = ' '.join([w['word'] for w in merged_words])
    
    return {
        'words': merged_words,
        'full_transcript': full_transcript
    }
