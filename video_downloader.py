import os
import subprocess
import logging
from pathlib import Path
from typing import Optional

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def download_video(video_id: str) -> Optional[str]:
    """Download YouTube video with separate audio and video streams."""
    try:
        logger.info(f"🎬 Starting download for video: {video_id}")
        output_dir = Path("temp_videos")
        output_dir.mkdir(exist_ok=True)
        
        base_path = output_dir / video_id

        def execute_command(command: list, stream_type: str) -> bool:
            """Execute a command with single-line progress updates"""
            try:
                print(f"⚙️ Downloading {stream_type} stream... ", end="", flush=True)
                
                process = subprocess.Popen(
                    command,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    universal_newlines=True
                )

                last_progress = ""
                for line in process.stdout:
                    line = line.strip()
                    if "[download]" in line and "%" in line:
                        progress = line.split("[download]")[1].strip()
                        if progress != last_progress:
                            print(f"\r⚙️ Downloading {stream_type} stream... {progress}", end="", flush=True)
                            last_progress = progress

                process.wait()
                print()
                return process.returncode == 0
                
            except Exception as e:
                logger.error(f"Command execution failed: {str(e)}")
                return False

        # Video download command
        video_command = [
            'yt-dlp',
            '-f', 'bestvideo[height<=1440][ext=mp4]',  # 1440p max resolution
            '--concurrent-fragments', '256',
            '--http-chunk-size', '300M',
            '-o', str(base_path) + '_video.%(ext)s',
            '--progress',
            f'https://www.youtube.com/watch?v={video_id}'
        ]

        audio_command = [
            'yt-dlp',
            '-f', 'bestaudio[ext=m4a]',
            '--concurrent-fragments', '8',
            '-o', str(base_path) + '_audio.%(ext)s',
            '--progress',
            f'https://www.youtube.com/watch?v={video_id}'
        ]

        # Download video stream
        if not execute_command(video_command, "video"):
            logger.error(f"❌ Video download failed for {video_id}")
            return None

        # Download audio stream
        if not execute_command(audio_command, "audio"):
            logger.error(f"❌ Audio download failed for {video_id}")
            return None

        # Merge streams
        video_file = str(base_path) + "_video.mp4"
        audio_file = str(base_path) + "_audio.m4a"
        final_file = output_dir / f"{video_id}.mp4"

        if Path(video_file).exists() and Path(audio_file).exists():
            logger.info("🔧 Merging video and audio streams...")
            merge_command = [
                'ffmpeg',
                '-y',
                '-i', video_file,
                '-i', audio_file,
                '-c:v', 'copy',
                '-c:a', 'aac',
                '-loglevel', 'error',
                str(final_file)
            ]
            
            result = subprocess.run(merge_command, capture_output=True, text=True)
            if result.returncode != 0:
                logger.error(f"❌ Merge failed: {result.stderr[:200]}...")
                return None

            logger.info(f"✅ Successfully downloaded: {final_file}")
            return str(final_file)

        logger.error("❌ Video or audio files missing after download")
        return None

    except Exception as e:
        logger.error(f"🔥 Unexpected error: {str(e)}")
        return None
