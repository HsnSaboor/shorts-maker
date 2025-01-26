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
        output_base = output_dir / video_id  # Changed from .mp4

        logger.debug(f"📁 Target base path: {output_base}")
        logger.info("⚙️ Configuring yt-dlp parameters")

        command = [
            'yt-dlp',
            
            # More compatible format selection
            '-f', 'bestvideo[height<=1440]+bestaudio/best[height<=1440]',
            
            # Auto merge format
            '--merge-output-format', 'mkv',  # More container compatibility
            
            # Conservative download parameters
            '--concurrent-fragments', '16',
            '--http-chunk-size', '20M',
            '--downloader', 'aria2c',
            '--downloader-args', 'aria2c:-x 8 -s 16 -k 10M',
            
            # Essential parameters only
            '--retries', '10',
            '--fragment-retries', '10',
            '--socket-timeout', '30',
            '--force-ipv4',
            
            # Fixed output template
            '-o', f'{output_base}.%(ext)s',  # Correct output pattern
            
            f'https://www.youtube.com/watch?v={video_id}'
        ]

        logger.debug(f"🔧 Executing command: {' '.join(command)}")
        
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,  # Capture stderr separately
            universal_newlines=True
        )

        # Capture all output for debugging
        stdout_lines = []
        stderr_lines = []
        
        # Read both streams concurrently
        while True:
            stdout_line = process.stdout.readline()
            stderr_line = process.stderr.readline()
            
            if not stdout_line and not stderr_line:
                break
                
            if stdout_line:
                stdout_line = stdout_line.strip()
                stdout_lines.append(stdout_line)
                if "[download]" in stdout_line and "%" in stdout_line:
                    progress = stdout_line.split("[download]")[1].strip()
                    logger.info(f"📥 Download progress: {progress}")
                    if progress_callback:
                        try:
                            percent = float(progress.split("%")[0].strip())
                            progress_callback(percent)
                        except Exception as e:
                            logger.warning(f"⚠️ Could not parse progress: {str(e)}")
                            
            if stderr_line:
                stderr_line = stderr_line.strip()
                stderr_lines.append(stderr_line)
                logger.error(f"⛔ yt-dlp error: {stderr_line}")

        process.wait()

        # Check for actual output file with any extension
        downloaded_files = list(output_dir.glob(f"{video_id}.*"))
        if downloaded_files:
            output_path = downloaded_files[0]
            size_mb = output_path.stat().st_size / 1024 / 1024
            logger.info(f"✅ Successfully downloaded {output_path} ({size_mb:.2f} MB)")
            return str(output_path)

        # Detailed error diagnostics
        if process.returncode != 0:
            logger.error(f"❌ Download failed for {video_id}. Exit code: {process.returncode}")
            if stderr_lines:
                logger.error("🛠️ Last 5 error messages:")
                for line in stderr_lines[-5:]:
                    logger.error(f"    {line}")
            return None

        logger.error("❌ Downloaded file not found after successful download")
        return None

    except Exception as e:
        logger.error(f"🔥 Unexpected download error: {str(e)}", exc_info=True)
        return None
