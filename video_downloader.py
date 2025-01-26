import asyncio
import subprocess
import logging
from pathlib import Path
from typing import Optional, Tuple, Callable

logger = logging.getLogger(__name__)

async def download_video(video_id: str, 
                       progress_callback: Optional[Callable[[str, float], None]] = None) -> Optional[str]:
    """Async video download with proper progress handling"""
    try:
        output_dir = Path("temp_videos")
        output_dir.mkdir(exist_ok=True)
        final_file = output_dir / f"{video_id}.mp4"

        if final_file.exists():
            logger.info(f"Using cached video: {final_file}")
            return str(final_file)

        # Run download in executor
        loop = asyncio.get_running_loop()
        video_file, audio_file = await loop.run_in_executor(
            None, 
            lambda: _download_streams(video_id, progress_callback)
        )

        # Merge streams
        return await loop.run_in_executor(
            None,
            lambda: _merge_streams(video_id, video_file, audio_file, final_file)
        )

    except Exception as e:
        logger.error(f"Download failed: {str(e)}")
        return None

def _download_streams(video_id: str, progress_callback: Callable) -> Tuple[Path, Path]:
    """Synchronous download with progress reporting"""
    base_path = Path("temp_videos") / video_id
    
    # Video stream
    video_file = _download_with_retry(
        command=[
            'yt-dlp',
            '-f', 'bestvideo[height<=1440][ext=mp4]',
            '--concurrent-fragments', '256',
            '-o', str(base_path) + '_video.%(ext)s',
            f'https://www.youtube.com/watch?v={video_id}'
        ],
        stream_type="video",
        progress_callback=progress_callback
    )

    # Audio stream
    audio_file = _download_with_retry(
        command=[
            'yt-dlp',
            '-f', 'bestaudio[ext=m4a]',
            '-o', str(base_path) + '_audio.%(ext)s',
            f'https://www.youtube.com/watch?v={video_id}'
        ],
        stream_type="audio",
        progress_callback=progress_callback
    )

    return video_file, audio_file

# Keep existing _download_with_retry and _merge_streams implementations

def _merge_streams(video_id: str, video_file: Path, audio_file: Path, final_file: Path) -> str:
    """Merge streams with validation"""
    merge_command = [
        'ffmpeg',
        '-y', '-i', str(video_file),
        '-i', str(audio_file),
        '-c:v', 'copy',
        '-c:a', 'aac',
        '-loglevel', 'error',
        str(final_file)
    ]

    result = subprocess.run(merge_command, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Merge failed: {result.stderr[:200]}")

    # Cleanup temporary files
    video_file.unlink(missing_ok=True)
    audio_file.unlink(missing_ok=True)
    return str(final_file)

def download_video(video_id: str, progress_callback: Optional[callable] = None) -> Optional[str]:
    """Main download function"""
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

        video_file, audio_file = _download_streams(video_id, progress_callback)
        return _merge_streams(video_id, video_file, audio_file, final_file)

    except Exception as e:
        logger.error(f"Download failed: {str(e)}")
        return None
