import argparse
import logging
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound
from youtube_transcript_api.formatters import JSONFormatter
import yt_dlp

logging.basicConfig(level=logging.INFO)

def fetch_transcript(video_id: str, lang_code: str = 'en') -> Optional[str]:
    """Fetch YouTube transcript with comprehensive error handling."""
    try:
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        
        # Attempt 1: Direct transcript fetch
        try:
            transcript = YouTubeTranscriptApi.get_transcript(
                video_id, 
                languages=[lang_code, 'en'],
                preserve_formatting=True
            )
            return JSONFormatter().format_transcript(transcript)
        except (TranscriptsDisabled, NoTranscriptFound):
            pass

        # Attempt 2: Auto-generated transcripts
        try:
            generated = transcript_list.find_generated_transcript([lang_code, 'en'])
            return JSONFormatter().format_transcript(generated.fetch())
        except Exception as e:
            logging.debug(f"No auto-generated transcript: {str(e)}")

        # Attempt 3: Any available transcript
        try:
            transcript = transcript_list.find_transcript(['*'])
            return JSONFormatter().format_transcript(transcript.fetch())
        except Exception as e:
            logging.debug(f"No available transcripts: {str(e)}")

        # Final fallback to yt-dlp
        return fetch_transcript_yt_dlp(video_id, lang_code)

    except TranscriptsDisabled:
        logging.warning(f"Subtitles disabled for video {video_id}")
        return None
    except NoTranscriptFound:
        logging.warning(f"No transcript found for video {video_id}")
        return None
    except Exception as e:
        logging.error(f"Unexpected error fetching transcript: {str(e)}")
        return None

def fetch_transcript_yt_dlp(video_id: str, lang_code: str) -> Optional[str]:
    """Fallback transcript fetch using yt-dlp with improved error handling."""
    try:
        ydl_opts = {
            'writesubtitles': True,
            'subtitleslangs': [lang_code, 'en', 'a.en', 'a.*'],
            'skip_download': True,
            'quiet': True,
            'ignoreerrors': True
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(f"https://youtu.be/{video_id}", download=False)
            
            if not info or 'subtitles' not in info:
                return None

            # Check for both manual and auto-generated subtitles
            for lang in [lang_code, 'en']:
                for sub_type in ['', 'a.']:
                    key = f"{sub_type}{lang}"
                    if key in info['subtitles']:
                        subs = info['subtitles'][key][0]['data']
                        return JSONFormatter().format_transcript([
                            {
                                'text': entry['text'],
                                'start': entry['start'],
                                'duration': entry['end'] - entry['start']
                            } for entry in subs
                        ])
            
            logging.warning(f"No suitable subtitles found via yt-dlp for {video_id}")
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
