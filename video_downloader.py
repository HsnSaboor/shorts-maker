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
        logger.info(f"📂 Created output directory: {output_dir}")
        
        # Base path for temp files
        base_path = output_dir / video_id

        # Define video and audio commands
        video_command = [
            'yt-dlp',
            '-f', 'bestvideo[height<=1440][ext=mp4]',  # 1440p max resolution
            '--concurrent-fragments', '256',
            '--http-chunk-size', '300M',
            '-o', str(base_path) + '_video.%(ext)s',
            '--progress-template', 'download:%(progress.downloaded_bytes)s/%(progress.total_bytes)s|%(progress._percent_str)s|%(progress.speed)s|%(progress._eta_str)s',
            f'https://www.youtube.com/watch?v={video_id}'
        ]

        audio_command = [
            'yt-dlp',
            '-f', 'bestaudio[ext=m4a]',
            '--concurrent-fragments', '8',
            '-o', str(base_path) + '_audio.%(ext)s',
            '--progress-template', 'download:%(progress.downloaded_bytes)s/%(progress.total_bytes)s|%(progress._percent_str)s|%(progress.speed)s|%(progress._eta_str)s',
            f'https://www.youtube.com/watch?v={video_id}'
        ]

        def execute_command(command: list) -> bool:
            """Execute a command and handle its output."""
            try:
                logger.info(f"⚡ Executing command: {' '.join(command)}")
                process = subprocess.Popen(
                    command,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    universal_newlines=True,
                    bufsize=1
                )

                while True:
                    line = process.stdout.readline()
                    if not line and process.poll() is not None:
                        break
                    line = line.strip()
                    if line:  # Log any non-empty output
                        if line.startswith('download:'):
                            try:
                                # Parse the progress information
                                parts = line.split('|')
                                bytes_info = parts[0].split(':')[1]
                                downloaded, total = bytes_info.split('/')
                                percent = parts[1].strip()
                                speed = parts[2]
                                eta = parts[3]

                                # Format bytes to appropriate unit
                                def format_size(bytes_size):
                                    if bytes_size == 'NA':
                                        return '0 MB'
                                    bytes_num = float(bytes_size)
                                    if bytes_num >= 1024 * 1024 * 1024:  # GB
                                        return f"{bytes_num / 1024 / 1024 / 1024:.2f} GB"
                                    else:  # MB
                                        return f"{bytes_num / 1024 / 1024:.2f} MB"

                                def format_speed(speed_str):
                                    if speed_str == 'NA':
                                        return 'NA'
                                    speed_num = float(speed_str)
                                    if speed_num >= 1024 * 1024 * 1024:  # GB/s
                                        return f"{speed_num / 1024 / 1024 / 1024:.2f} GB/s"
                                    else:  # MB/s
                                        return f"{speed_num / 1024 / 1024:.2f} MB/s"

                                # Format the values
                                downloaded_str = format_size(downloaded)
                                total_str = format_size(total)
                                speed_formatted = format_speed(speed)

                                # Create progress message
                                progress_msg = f"📥 Progress: {percent} ({downloaded_str} / {total_str}) at {speed_formatted} ETA: {eta}"
                                logger.info(progress_msg)

                                # Update progress callback
                                if progress_callback:
                                    try:
                                        percent_value = float(percent.rstrip('%'))
                                        progress_callback("download", percent_value)
                                    except ValueError:
                                        pass
                            except (ValueError, IndexError) as e:
                                logger.debug(f"Error parsing progress: {e}")
                        else:
                            logger.info(f"📝 {line}")

                stderr = process.stderr.read()
                if stderr:
                    logger.warning(f"⚠️ Process output: {stderr}")

                process.wait()
                success = process.returncode == 0
                if success:
                    logger.info("✅ Command executed successfully")
                else:
                    logger.error(f"❌ Command failed with return code {process.returncode}")
                return success

            except Exception as e:
                logger.error(f"🔥 Command execution failed: {str(e)}", exc_info=True)
                return False

        # Download video
        logger.info("⚙️ Starting video stream download...")
        if not execute_command(video_command):
            logger.error(f"❌ Video download failed for {video_id}")
            return None
        logger.info("✅ Video stream downloaded successfully")

        # Download audio
        logger.info("⚙️ Starting audio stream download...")
        if not execute_command(audio_command):
            logger.error(f"❌ Audio download failed for {video_id}")
            return None
        logger.info("✅ Audio stream downloaded successfully")

        # Merge video and audio using ffmpeg
        video_file = str(base_path) + "_video.mp4"
        audio_file = str(base_path) + "_audio.m4a"
        final_file = output_dir / f"{video_id}.mp4"

        # Verify files exist before merging
        if not Path(video_file).exists():
            logger.error(f"❌ Video file not found: {video_file}")
            return None
        if not Path(audio_file).exists():
            logger.error(f"❌ Audio file not found: {audio_file}")
            return None

        logger.info("🔧 Starting video and audio merge...")
        merge_command = [
            'ffmpeg',
            '-y',  # Overwrite output file if it exists
            '-i', video_file,
            '-i', audio_file,
            '-c:v', 'copy',  # Copy video codec
            '-c:a', 'aac',   # Encode audio in AAC
            str(final_file)
        ]

        logger.info(f"⚡ Executing merge command: {' '.join(merge_command)}")
        merge_process = subprocess.run(
            merge_command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True
        )

        if merge_process.returncode != 0:
            logger.error(f"❌ Failed to merge video and audio: {merge_process.stderr}")
            return None

        # Verify final file exists
        if not Path(final_file).exists():
            logger.error("❌ Final merged file not found")
            return None

        logger.info(f"✅ Successfully downloaded and merged: {final_file}")
        
        # Clean up temporary files
        try:
            os.remove(video_file)
            os.remove(audio_file)
            logger.info("🧹 Cleaned up temporary files")
        except Exception as e:
            logger.warning(f"⚠️ Failed to clean up temporary files: {str(e)}")

        return str(final_file)

    except Exception as e:
        logger.error(f"🔥 Unexpected error: {str(e)}", exc_info=True)
        return None
