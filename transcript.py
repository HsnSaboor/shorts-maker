import argparse
import logging
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound
from youtube_transcript_api.formatters import JSONFormatter
import yt_dlp

logging.basicConfig(level=logging.INFO)

def fetch_transcript(video_id: str, lang_code: str = 'en') -> str:
    """Fetch YouTube transcript with fallback and translation logic."""
    try:
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        
        # 1. Try requested language (manual first, then auto)
        if lang_code in transcript_list._manually_created_transcripts:
            transcript = transcript_list.find_manually_created_transcript([lang_code])
            logging.info(f"Found manual {lang_code} transcript")
            return format_transcript(transcript.fetch())
            
        if lang_code in transcript_list._generated_transcripts:
            transcript = transcript_list.find_generated_transcript([lang_code])
            logging.info(f"Found auto-generated {lang_code} transcript")
            return format_transcript(transcript.fetch())

        # 2. Fallback to English (manual first, then auto)
        if lang_code != 'en':
            if 'en' in transcript_list._manually_created_transcripts:
                transcript = transcript_list.find_manually_created_transcript(['en'])
                logging.info("Found manual English transcript")
                return format_transcript(transcript.fetch())
                
            if 'en' in transcript_list._generated_transcripts:
                transcript = transcript_list.find_generated_transcript(['en'])
                logging.info("Found auto-generated English transcript")
                return format_transcript(transcript.fetch())

        # 3. Fallback to any available transcript (manual first, then auto)
        if transcript_list._manually_created_transcripts:
            transcript = next(iter(transcript_list._manually_created_transcripts.values()))
            logging.info(f"Found manual transcript in {transcript.language_code}")
            if transcript.language_code != lang_code:
                translated = attempt_translation(transcript, lang_code)
                if translated:
                    return translated
                else:
                    logging.info(f"Returning manual transcript in {transcript.language_code}")
                    return format_transcript(transcript.fetch())
            else:
                return format_transcript(transcript.fetch())
            
        if transcript_list._generated_transcripts:
            transcript = next(iter(transcript_list._generated_transcripts.values()))
            logging.info(f"Found auto-generated transcript in {transcript.language_code}")
            if transcript.language_code != lang_code:
                translated = attempt_translation(transcript, lang_code)
                if translated:
                    return translated
                else:
                    logging.info(f"Returning auto-generated transcript in {transcript.language_code}")
                    return format_transcript(transcript.fetch())
            else:
                return format_transcript(transcript.fetch())

        # 4. Final fallback to yt-dlp
        return fetch_transcript_yt_dlp(video_id, lang_code)

    except Exception as e:
        logging.error(f"Error: {str(e)}")
        return None

def attempt_translation(transcript, target_lang):
    """Attempts to translate the transcript to the target language. Returns formatted transcript if successful, else None."""
    try:
        if not transcript.is_translatable:
            logging.warning(f"Transcript in {transcript.language_code} is not translatable.")
            return None

        available_langs = [tl['language_code'] for tl in transcript.translation_languages]
        if target_lang not in available_langs:
            logging.warning(f"Translation to {target_lang} not available. Available languages: {available_langs}")
            return None

        translated_transcript = transcript.translate(target_lang)
        logging.info(f"Translated transcript from {transcript.language_code} to {target_lang}")
        return format_transcript(translated_transcript.fetch())
    except Exception as e:
        logging.error(f"Translation failed: {str(e)}")
        return None

def fetch_transcript_yt_dlp(video_id: str, lang_code: str) -> str:
    """Fallback transcript fetch using yt-dlp."""
    try:
        ydl_opts = {
            'writesubtitles': True,
            'subtitleslangs': [lang_code, 'en'],
            'skip_download': True,
            'quiet': True
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(f"https://youtu.be/{video_id}", download=False)
            
            # Try requested language first, then English
            for lang in [lang_code, 'en']:
                if info.get('subtitles') and lang in info['subtitles']:
                    subs = info['subtitles'][lang][0]['data']
                    logging.info(f"Found {lang} subtitles via yt-dlp")
                    return JSONFormatter().format_transcript(subs)
            
            logging.error("No subtitles found via any method")
            return None

    except Exception as e:
        logging.error(f"yt-dlp fallback failed: {str(e)}")
        return None

def format_transcript(transcript: list) -> str:
    """Format transcript as JSON."""
    return JSONFormatter().format_transcript(transcript)

def main():
    parser = argparse.ArgumentParser(description='Fetch YouTube subtitles')
    parser.add_argument('video_id', help='YouTube video ID')
    parser.add_argument('-l', '--lang', default='en', 
                       help='Subtitle language code (default: en)')
    
    args = parser.parse_args()
    
    transcript = fetch_transcript(args.video_id, args.lang)
    
    if transcript:
        print(transcript)
    else:
        logging.error("Failed to retrieve subtitles")

if __name__ == "__main__":
    main()