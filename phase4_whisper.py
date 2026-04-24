import httpx
import json
from config import OPENAI_API_KEY, WHISPER_API_URL

def transcribe_with_whisper(audio_path):
    """Call Whisper API for word-level timestamps"""
    with open(audio_path, 'rb') as audio_file:
        files = {
            'file': ('audio.mp3', audio_file, 'audio/mpeg')
        }
        data = {
            'model': 'whisper-1',
            'response_format': 'verbose_json',
            'timestamp_granularities[]': 'word'
        }
        
        response = httpx.post(
            WHISPER_API_URL,
            headers={'Authorization': f'Bearer {OPENAI_API_KEY}'},
            files=files,
            data=data,
            timeout=120.0
        )
        response.raise_for_status()
        
        return response.json()

def extract_word_timestamps(whisper_result):
    """Extract word-level timestamps from Whisper response"""
    words = []
    for word_data in whisper_result.get('words', []):
        words.append({
            'word': word_data['word'].strip().lower(),
            'start': word_data['start'],
            'end': word_data['end']
        })
    return words
