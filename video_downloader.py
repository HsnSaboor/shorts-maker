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
        base_path = output_dir / video_id
        final_path = base_path.with_suffix('.mp4')

        # Video download command with high concurrency
        video_command = [
            'yt-dlp',
            '-f', 'bestvideo[height<=1440][ext=mp4]',  # 1440p max resolution
            '--concurrent-fragments', '256',
            '--http-chunk-size', '300M',
            '-o', str(base_path) + '_video.%(ext)s',
            '--progress',
            f'https://www.youtube.com/watch?v={video_id}'
        ]

        # Audio download command with lower concurrency
        audio_command = [
            'yt-dlp',
            '-f', 'bestaudio[ext=m4a]',
            '--concurrent-fragments', '8',
            '-o', str(base_path) + '_audio.%(ext)s',
            '--progress',
            f'https://www.youtube.com/watch?v={video_id}'
        ]

        # Download video
        logger.info("⬇️ Starting video download")
        if not _execute_command(video_command, progress_callback, "Video"):
            logger.error("❌ Video download failed")
            return None

        # Download audio
        logger.info("🔊 Starting audio download")
        if not _execute_command(audio_command, progress_callback, "Audio"):
            logger.error("❌ Audio download failed")
            return None

        # Merge streams
        logger.info("🔀 Merging audio and video")
        _merge_streams(base_path, final_path)

        if final_path.exists():
            size_mb = final_path.stat().st_size / 1024 / 1024
            logger.info(f"✅ Successfully downloaded {final_path} ({size_mb:.2f} MB)")
            return str(final_path)
            
        logger.error("❌ Merged file not found after successful download")
        return None

    except Exception as e:
        logger.error(f"🔥 Unexpected download error: {str(e)}", exc_info=True)
        return None

def _execute_command(command: list, progress_callback: Optional[Callable], label: str) -> bool:
    """Execute download command with real-time progress handling"""
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
                progress = line.split("[download]")[1].strip()
                print(f"\r📥 {label} Progress: {progress}", end='', flush=True)
                if progress_callback:
                    try:
                        percent = float(progress.split("%")[0].strip())
                        progress_callback(percent)
                    except Exception as e:
                        logger.warning(f"⚠️ Could not parse progress: {str(e)}")

        process.wait()
        print()  # New line after progress completes
        return process.returncode == 0

    except Exception as e:
        logger.error(f"Command execution failed: {str(e)}")
        return False

def _merge_streams(base_path: Path, final_path: Path) -> None:
    """Merge separate audio/video streams using FFmpeg"""
    video_file = next(base_path.parent.glob(f"{base_path.name}_video.*"))
    audio_file = next(base_path.parent.glob(f"{base_path.name}_audio.*"))
    
    merge_command = [
        'ffmpeg',
        '-i', str(video_file),
        '-i', str(audio_file),
        '-c', 'copy',
        '-y',  # Overwrite without prompting
        str(final_path)
    ]
    
    subprocess.run(merge_command, check=True)
    video_file.unlink()
    audio_file.unlink()
