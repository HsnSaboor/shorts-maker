import argparse
import logging
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound
from youtube_transcript_api.formatters import JSONFormatter
import yt_dlp
from typing import Optional, List, Dict

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def fetch_transcript(video_id: str, lang_code: str = 'en') -> Optional[str]:
    """Fetch YouTube transcript with comprehensive error handling."""
    logger.info(f"🎯 Starting transcript fetch for video: {video_id}")
    try:
        logger.info(f"📃 Listing available transcripts...")
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        
        # Attempt 1: Direct transcript fetch
        logger.info("🔍 Attempting direct transcript fetch...")
        try:
            transcript = YouTubeTranscriptApi.get_transcript(
                video_id, 
                languages=[lang_code, 'en'],
                preserve_formatting=True
            )
            logger.info("✅ Direct transcript fetch successful")
            return JSONFormatter().format_transcript(transcript)
        except (TranscriptsDisabled, NoTranscriptFound) as e:
            logger.warning(f"⚠️ Direct transcript fetch failed: {str(e)}")
            pass

        # Attempt 2: Auto-generated transcripts
        logger.info("🤖 Attempting to find auto-generated transcript...")
        try:
            generated = transcript_list.find_generated_transcript([lang_code, 'en'])
            transcript = generated.fetch()
            logger.info("✅ Auto-generated transcript fetch successful")
            return JSONFormatter().format_transcript(transcript)
        except Exception as e:
            logger.warning(f"⚠️ Auto-generated transcript fetch failed: {str(e)}")

        # Attempt 3: Any available transcript
        logger.info("🌍 Attempting to find any available transcript...")
        try:
            transcript = transcript_list.find_transcript(['*'])
            result = transcript.fetch()
            logger.info("✅ Alternative transcript fetch successful")
            return JSONFormatter().format_transcript(result)
        except Exception as e:
            logger.warning(f"⚠️ Alternative transcript fetch failed: {str(e)}")

        # Final fallback to yt-dlp
        logger.info("🔄 Attempting fallback to yt-dlp...")
        return fetch_transcript_yt_dlp(video_id, lang_code)

    except TranscriptsDisabled:
        logger.error(f"❌ Subtitles are disabled for video {video_id}")
        return None
    except NoTranscriptFound:
        logger.error(f"❌ No transcript found for video {video_id}")
        return None
    except Exception as e:
        logger.error(f"🔥 Unexpected error fetching transcript: {str(e)}", exc_info=True)
        return None

def fetch_transcript_yt_dlp(video_id: str, lang_code: str) -> Optional[str]:
    """Fallback transcript fetch using yt-dlp with improved error handling."""
    logger.info(f"📥 Starting yt-dlp fallback for video: {video_id}")
    try:
        logger.info("⚙️ Configuring yt-dlp options...")
        ydl_opts = {
            'writesubtitles': True,
            'subtitleslangs': [lang_code, 'en', 'a.en', 'a.*'],
            'skip_download': True,
            'quiet': True,
            'ignoreerrors': True
        }
        
        logger.info("🔄 Extracting video information...")
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(f"https://youtu.be/{video_id}", download=False)
            
            if not info:
                logger.error("❌ Failed to extract video information")
                return None
            
            if 'subtitles' not in info:
                logger.error("❌ No subtitles found in video information")
                return None

            logger.info("🔍 Searching for available subtitles...")
            # Check for both manual and auto-generated subtitles
            for lang in [lang_code, 'en']:
                for sub_type in ['', 'a.']:
                    key = f"{sub_type}{lang}"
                    if key in info['subtitles']:
                        logger.info(f"✅ Found subtitles: {key}")
                        subs = info['subtitles'][key][0]['data']
                        logger.info(f"📝 Processing {len(subs)} subtitle entries...")
                        formatted = JSONFormatter().format_transcript([
                            {
                                'text': entry['text'],
                                'start': entry['start'],
                                'duration': entry['end'] - entry['start']
                            } for entry in subs
                        ])
                        logger.info("✅ Successfully processed subtitles")
                        return formatted
            
            logger.warning(f"⚠️ No suitable subtitles found via yt-dlp for {video_id}")
            return None

    except Exception as e:
        logger.error(f"🔥 yt-dlp fallback failed: {str(e)}", exc_info=True)
        return None

def format_transcript(transcript: list) -> str:
    """Format transcript as JSON."""
    logger.info("📋 Formatting transcript as JSON...")
    try:
        result = JSONFormatter().format_transcript(transcript)
        logger.info("✅ Transcript formatting successful")
        return result
    except Exception as e:
        logger.error(f"❌ Transcript formatting failed: {str(e)}")
        return ""

def main():
    """Main function to fetch subtitles from command line."""
    logger.info("🚀 Starting transcript fetching tool...")
    parser = argparse.ArgumentParser(description='Fetch YouTube subtitles')
    parser.add_argument('video_id', help='YouTube video ID')
    parser.add_argument('-l', '--lang', default='en', 
                       help='Subtitle language code (default: en)')
    
    args = parser.parse_args()
    logger.info(f"📥 Processing video: {args.video_id} (Language: {args.lang})")
    
    transcript = fetch_transcript(args.video_id, args.lang)
    
    if transcript:
        logger.info("✅ Successfully retrieved transcript")
        print(transcript)
    else:
        logger.error("❌ Failed to retrieve transcript")

if __name__ == "__main__":
    main()
