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
    """Download YouTube video with real-time progress tracking"""
    try:
        logger.info(f"🎬 Starting download for video: {video_id}")
        output_dir = Path("temp_videos")
        output_dir.mkdir(exist_ok=True)
        output_path = output_dir / f"{video_id}.mp4"

        logger.debug(f"📁 Target path: {output_path}")
        logger.info("⚙️ Configuring yt-dlp parameters")

        command = [
    'yt-dlp',
    '-f', 'bestvideo[height<=1440][vcodec^=vp09][ext=webm]+bestaudio[ext=webm]/'
          'bestvideo[height<=1440][ext=webm]+bestaudio[ext=webm]/'
          'bestvideo[height<=1440]+bestaudio',
    '--merge-output-format', 'webm',
    '--concurrent-fragments', '64',
    '--http-chunk-size', '64M',
    '--no-simulate',
    '--no-playlist',
    '-o', str(output_path),
    f'https://www.youtube.com/watch?v={video_id}'
]

        logger.debug(f"🔧 Executing command: {' '.join(command)}")
        
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True
        )

        # Process output in real-time
        for line in process.stdout:
            line = line.strip()
            if line:
                # Extract progress information
                if "[download]" in line and "%" in line:
                    progress = line.split("[download]")[1].strip()
                    logger.info(f"📥 Download progress: {progress}")
                    if progress_callback:
                        try:
                            # Extract percentage (e.g., "45.2%")
                            percent = float(progress.split("%")[0].strip())
                            progress_callback(percent)
                        except Exception as e:
                            logger.warning(f"⚠️ Could not parse progress: {str(e)}")

        # Wait for process to complete
        process.wait()

        if process.returncode != 0:
            logger.error(f"❌ Download failed for {video_id}")
            return None

        if output_path.exists():
            size_mb = output_path.stat().st_size / 1024 / 1024
            logger.info(f"✅ Successfully downloaded {output_path} ({size_mb:.2f} MB)")
            return str(output_path)
            
        logger.error("❌ Downloaded file not found after successful download")
        return None

    except Exception as e:
        logger.error(f"🔥 Unexpected download error: {str(e)}", exc_info=True)
        return None
