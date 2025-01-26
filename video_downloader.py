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
    """Download YouTube video with robust error handling"""
    try:
        logger.info(f"🎬 Starting download for video: {video_id}")
        output_dir = Path("temp_videos")
        output_dir.mkdir(exist_ok=True)
        output_template = output_dir / f"{video_id}.%(ext)s"

        logger.debug(f"📁 Output template: {output_template}")
        logger.info("⚙️ Configuring yt-dlp parameters")

        command = [
            'yt-dlp',
            '-f', 'bestvideo[height<=1440]+bestaudio/best',
            '--merge-output-format', 'mp4',
            '--concurrent-fragments', '8',
            '--http-chunk-size', '10M',
            '--retries', '10',
            '--fragment-retries', '10',
            '--socket-timeout', '30',
            '--force-overwrites',
            '-o', str(output_template),
            '--no-playlist',
            f'https://www.youtube.com/watch?v={video_id}'
        ]

        logger.debug(f"🔧 Executing: {' '.join(command)}")
        
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            bufsize=1
        )

        # Capture all output streams
        output = []
        while True:
            # Read stdout
            stdout_line = process.stdout.readline()
            if stdout_line:
                output.append(stdout_line)
                if "[download]" in stdout_line and "%" in stdout_line:
                    progress = stdout_line.split("[download]")[1].strip()
                    logger.info(f"📥 Progress: {progress}")
                    if progress_callback:
                        try:
                            percent = float(progress.split("%")[0].strip())
                            progress_callback(percent)
                        except Exception as e:
                            logger.warning(f"Progress parse error: {str(e)}")
            
            # Read stderr
            stderr_line = process.stderr.readline()
            if stderr_line:
                logger.error(f"⛔ yt-dlp error: {stderr_line.strip()}")
                output.append(f"ERROR: {stderr_line}")
            
            # Check process completion
            if process.poll() is not None:
                break

        # Final check after loop
        stdout, stderr = process.communicate()
        output.extend(stdout.splitlines())
        if stderr:
            logger.error(f"⛔ Final errors: {stderr.strip()}")
            output.extend(f"FINAL ERROR: {line}" for line in stderr.splitlines())

        # Verify successful download
        downloaded_files = list(output_dir.glob(f"{video_id}.*"))
        if downloaded_files:
            output_path = downloaded_files[0]
            if output_path.stat().st_size > 1024:  # Minimum 1KB file check
                size_mb = output_path.stat().st_size / 1024 / 1024
                logger.info(f"✅ Success: {output_path.name} ({size_mb:.2f}MB)")
                return str(output_path)
            else:
                logger.error("❌ Downloaded file is too small (corrupted?)")
                output_path.unlink()

        # Error diagnostics
        logger.error(f"❌ Download failed for {video_id}")
        logger.debug(f"Full yt-dlp output:\n{'\n'.join(output)}")
        
        return None

    except Exception as e:
        logger.error(f"🔥 Critical error: {str(e)}", exc_info=True)
        return None
