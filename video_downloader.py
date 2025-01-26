# video_downloader.py
import os
import subprocess
import logging
from pathlib import Path
from typing import Optional, Callable

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def download_video(video_id: str, progress_callback: Optional[Callable] = None) -> Optional[str]:
    """Download YouTube video with separate audio/video streams and merge them"""
    try:
        logger.info(f"🎬 Starting download for video: {video_id}")
        output_dir = Path("temp_videos")
        output_dir.mkdir(exist_ok=True)
        base_path = output_dir / video_id

        # Define paths
        video_path = base_path.with_name(f"{base_path.name}_video.mp4")
        audio_path = base_path.with_name(f"{base_path.name}_audio.m4a")
        final_path = base_path.with_name(f"{base_path.name}.mp4")

        # Download video stream
        video_command = [
            'yt-dlp',
            '-f', 'bestvideo[height<=1440][ext=mp4]',
            '--concurrent-fragments', '256',
            '--http-chunk-size', '300M',
            '-o', str(video_path),
            '--progress',
            f'https://www.youtube.com/watch?v={video_id}'
        ]
        if not run_download_command(video_command, progress_callback, 0, 50):
            return None

        # Download audio stream
        audio_command = [
            'yt-dlp',
            '-f', 'bestaudio[ext=m4a]',
            '--concurrent-fragments', '8',
            '-o', str(audio_path),
            '--progress',
            f'https://www.youtube.com/watch?v={video_id}'
        ]
        if not run_download_command(audio_command, progress_callback, 50, 50):
            return None

        # Merge streams
        logger.info("🔗 Merging video and audio streams")
        ffmpeg_command = [
            'ffmpeg',
            '-i', str(video_path),
            '-i', str(audio_path),
            '-c:v', 'copy',
            '-c:a', 'aac',
            '-strict', 'experimental',
            '-y',
            str(final_path)
        ]
        result = subprocess.run(
            ffmpeg_command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        if result.returncode != 0:
            logger.error(f"❌ Merge failed: {result.stderr[:500]}...")
            return None

        # Cleanup temporary files
        video_path.unlink(missing_ok=True)
        audio_path.unlink(missing_ok=True)

        if final_path.exists():
            size_mb = final_path.stat().st_size / 1024 / 1024
            logger.info(f"✅ Successfully downloaded {final_path} ({size_mb:.2f} MB)")
            return str(final_path)
            
        logger.error("❌ Merged file not found")
        return None

    except Exception as e:
        logger.error(f"🔥 Unexpected download error: {str(e)}", exc_info=True)
        return None

def run_download_command(command: list, progress_callback: Callable, 
                        start: float, range: float) -> bool:
    """Run a download command with progress tracking"""
    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True
        )

        for line in process.stdout:
            line = line.strip()
            if line and "[download]" in line and "%" in line:
                try:
                    percent = float(line.split("%")[0].split()[-1])
                    scaled = start + (percent * range / 100)
                    if progress_callback:
                        progress_callback(scaled)
                except Exception as e:
                    logger.warning(f"⚠️ Progress parse error: {str(e)}")

        process.wait()
        return process.returncode == 0
    except Exception as e:
        logger.error(f"❌ Command failed: {str(e)}")
        return False
