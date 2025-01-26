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
    """Download YouTube video with separate audio and video streams."""
    try:
        logger.info(f"🎬 Starting download for video: {video_id}")
        output_dir = Path("temp_videos")
        output_dir.mkdir(exist_ok=True)
        
        # Base path for temp files
        base_path = output_dir / video_id

        # Define video and audio commands
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

        def execute_command(command: list) -> bool:
            """Execute a command and handle its output."""
            try:
                process = subprocess.Popen(
                    command,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    universal_newlines=True
                )

                for line in process.stdout:
                    line = line.strip()
                    if "[download]" in line and "%" in line:
                        progress = line.split("[download]")[1].strip()
                        # Print progress on the same line
                        print(f"\r📥 {progress}", end="")
                        if progress_callback:
                            try:
                                percent = float(progress.split('%')[0].strip())
                                progress_callback("download", percent)
                            except ValueError:
                                pass

                process.wait()
                return process.returncode == 0
            except Exception as e:
                logger.error(f"🔥 Command execution failed: {str(e)}", exc_info=True)
                return False

        # Download video
        logger.info("⚙️ Downloading video stream...")
        if not execute_command(video_command):
            logger.error(f"❌ Video download failed for {video_id}")
            return None

        # Download audio
        logger.info("⚙️ Downloading audio stream...")
        if not execute_command(audio_command):
            logger.error(f"❌ Audio download failed for {video_id}")
            return None

        # Merge video and audio using ffmpeg
        video_file = str(base_path) + "_video.mp4"
        audio_file = str(base_path) + "_audio.m4a"
        final_file = output_dir / f"{video_id}.mp4"

        if Path(video_file).exists() and Path(audio_file).exists():
            logger.info("🔧 Merging video and audio streams...")
            merge_command = [
                'ffmpeg',
                '-y',  # Overwrite output file if it exists
                '-i', video_file,
                '-i', audio_file,
                '-c:v', 'copy',  # Copy video codec
                '-c:a', 'aac',   # Encode audio in AAC
                str(final_file)
            ]

            merge_process = subprocess.run(merge_command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            if merge_process.returncode != 0:
                logger.error(f"❌ Failed to merge video and audio for {video_id}")
                return None

            logger.info(f"✅ Successfully downloaded and merged: {final_file}")
            return str(final_file)

        logger.error("❌ Video or audio files missing after download")
        return None

    except Exception as e:
        logger.error(f"🔥 Unexpected error: {str(e)}", exc_info=True)
        return None
