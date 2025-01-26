import os
import re
import subprocess
import logging
from pathlib import Path
from typing import Optional, Tuple

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def format_size(size_bytes: int) -> str:
    """Convert bytes to human-readable format"""
    units = ["B", "KB", "MB", "GB", "TB"]
    unit_index = 0
    while size_bytes >= 1024 and unit_index < len(units)-1:
        size_bytes /= 1024
        unit_index += 1
    return f"{size_bytes:.2f} {units[unit_index]}"

def download_video(video_id: str, progress_callback: Optional[callable] = None) -> Optional[str]:
    """Download YouTube video with progress tracking"""
    try:
        output_dir = Path("temp_videos")
        output_dir.mkdir(exist_ok=True)
        final_file = output_dir / f"{video_id}.mp4"

        if final_file.exists():
            logger.info(f"⏩ Using cached video: {final_file}")
            if progress_callback:
                progress_callback("video", 100)
                progress_callback("audio", 100)
            return str(final_file)

        base_path = output_dir / video_id
        video_file = base_path.with_name(f"{base_path.name}_video.mp4")
        audio_file = base_path.with_name(f"{base_path.name}_audio.m4a")

        def run_command(command: list, stream_type: str) -> bool:
            """Run command with progress parsing"""
            try:
                process = subprocess.Popen(
                    command,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    universal_newlines=True
                )

                progress_pattern = re.compile(r'(\d+\.\d+)%')
                for line in iter(process.stdout.readline, ''):
                    line = line.strip()
                    match = progress_pattern.search(line)
                    if match and progress_callback:
                        progress = float(match.group(1))
                        progress_callback(stream_type, progress)
                        
                process.wait()
                return process.returncode == 0
            except Exception as e:
                logger.error(f"Command failed: {str(e)}")
                return False

        # Download video stream
        video_command = [
            'yt-dlp',
            '-f', 'bestvideo[height<=1440][ext=mp4]',
            '--concurrent-fragments', '256',
            '--http-chunk-size', '300M',
            '-o', str(video_file),
            f'https://www.youtube.com/watch?v={video_id}'
        ]
        if not run_command(video_command, "video"):
            logger.error("Video download failed")
            return None

        # Download audio stream
        audio_command = [
            'yt-dlp',
            '-f', 'bestaudio[ext=m4a]',
            '-o', str(audio_file),
            f'https://www.youtube.com/watch?v={video_id}'
        ]
        if not run_command(audio_command, "audio"):
            logger.error("Audio download failed")
            return None

        # Merge streams
        merge_command = [
            'ffmpeg',
            '-y', '-i', str(video_file),
            '-i', str(audio_file),
            '-c:v', 'copy', '-c:a', 'aac',
            '-loglevel', 'error', str(final_file)
        ]
        result = subprocess.run(merge_command, capture_output=True)
        if result.returncode != 0:
            logger.error(f"Merge failed: {result.stderr.decode()[:200]}")
            return None

        # Cleanup temporary files
        video_file.unlink(missing_ok=True)
        audio_file.unlink(missing_ok=True)
        logger.info(f"✅ Final file size: {format_size(final_file.stat().st_size)}")
        return str(final_file)

    except Exception as e:
        logger.error(f"Download error: {str(e)}")
        return None
