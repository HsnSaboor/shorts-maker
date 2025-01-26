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
            
            # Format selection (prioritizes AV1 > VP9 > AVC)
            '-f', '(bestvideo[height<=1440][vcodec^=av01][fps>30]/'
                  'bestvideo[height<=1440][vcodec^=vp09][ext=webm]/'
                  'bestvideo[height<=1440][vcodec^=avc1])+bestaudio',
            
            # Merge settings
            '--merge-output-format', 'webm',
            
            # Turbo download parameters
            '--concurrent-fragments', '256',  # Max allowed fragments
            '--http-chunk-size', '200M',      # Larger chunks for big videos
            '--downloader', 'aria2c',
            '--downloader-args', 'aria2c:-x 64 -s 256 -k 500M -j 64 --file-allocation=falloc --optimize-concurrent-downloads=true',
            # Performance tweaks
            '--no-part',                      # Avoid partial files
            '--throttled-rate', '100M',       # Skip throttled fragments
            '--retries', 'infinite',
            '--fragment-retries', 'infinite',
            '--buffered-fragments', '256',    # Keep more in memory
            # Network optimizations
            '--socket-timeout', '60',
            '--source-address', '0.0.0.0',    # Bypass connection limits
            '--force-ipv4',
            '--limit-rate', '0',              # No rate limiting
            # Output control
            '-o', f'{output_path}.%(ext)s',
            '--no-simulate',
            '--no-playlist',
            
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
