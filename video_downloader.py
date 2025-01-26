import asyncio
import re
import subprocess
import logging
from pathlib import Path
from typing import Optional, Tuple, Callable

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def _download_with_retry(command: list, stream_type: str, progress_callback: Callable[[str, float], None]) -> Path:
    """Download with retry mechanism"""
    output_path = Path(command[-2].replace('%(ext)s', 'mp4' if stream_type == 'video' else 'm4a'))
    
    for attempt in range(3):
        try:
            if output_path.exists():
                logger.info(f"Found existing {stream_type} file: {output_path}")
                return output_path

            logger.info(f"Starting {stream_type} download (attempt {attempt + 1}/3)")
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True
            )

            progress_pattern = re.compile(r'(\d+\.\d+)%')
            for line in process.stdout:
                if progress_callback and (match := progress_pattern.search(line)):
                    progress_callback(stream_type, float(match.group(1)))

            process.wait()
            if process.returncode != 0:
                raise subprocess.CalledProcessError(
                    process.returncode, 
                    command, 
                    output=process.stdout.read()
                )

            if not output_path.exists():
                raise FileNotFoundError(f"Output file missing: {output_path}")

            logger.info(f"{stream_type.capitalize()} download successful")
            return output_path

        except Exception as e:
            logger.warning(f"{stream_type.capitalize()} download attempt {attempt + 1} failed: {str(e)}")
            if attempt == 2:
                raise RuntimeError(f"Failed after 3 attempts: {str(e)}") from e
            logger.info(f"Retrying {stream_type} download...")

def _download_streams(video_id: str, progress_callback: Callable[[str, float], None]) -> Tuple[Path, Path]:
    """Download video and audio streams"""
    base_path = Path("temp_videos") / video_id
    base_path.parent.mkdir(parents=True, exist_ok=True)

    logger.info(f"Starting video download for {video_id}")
    video_file = _download_with_retry(
        command=[
            'yt-dlp',
            '-f', 'bestvideo[height<=1440][ext=mp4]',
            '--concurrent-fragments', '256',
            '-o', f'{base_path}_video.%(ext)s',
            f'https://www.youtube.com/watch?v={video_id}'
        ],
        stream_type="video",
        progress_callback=progress_callback
    )

    logger.info(f"Starting audio download for {video_id}")
    audio_file = _download_with_retry(
        command=[
            'yt-dlp',
            '-f', 'bestaudio[ext=m4a]',
            '-o', f'{base_path}_audio.%(ext)s',
            f'https://www.youtube.com/watch?v={video_id}'
        ],
        stream_type="audio",
        progress_callback=progress_callback
    )

    return video_file, audio_file

def _merge_streams(video_id: str, video_file: Path, audio_file: Path, final_file: Path) -> str:
    """Merge streams with validation"""
    logger.info(f"Merging streams for {video_id}")
    final_file.parent.mkdir(parents=True, exist_ok=True)

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
        error_msg = result.stderr[:200] if result.stderr else "Unknown error"
        raise RuntimeError(f"Merge failed: {error_msg}")

    video_file.unlink(missing_ok=True)
    audio_file.unlink(missing_ok=True)
    logger.info(f"Merge completed for {video_id}")
    return str(final_file)

async def download_video(video_id: str, progress_callback: Optional[Callable[[str, float], None]] = None) -> Optional[str]:
    """Main async download function"""
    try:
        output_dir = Path("temp_videos")
        output_dir.mkdir(exist_ok=True)
        final_file = output_dir / f"{video_id}.mp4"

        if final_file.exists():
            logger.info(f"Using cached video: {final_file}")
            if progress_callback:
                progress_callback("video", 100.0)
                progress_callback("audio", 100.0)
            return str(final_file)

        loop = asyncio.get_running_loop()
        video_file, audio_file = await loop.run_in_executor(
            None, 
            lambda: _download_streams(video_id, progress_callback)
        )

        final_path = await loop.run_in_executor(
            None,
            lambda: _merge_streams(video_id, video_file, audio_file, final_file)
        )

        return final_path

    except Exception as e:
        logger.error(f"Download failed: {str(e)}")
        return None
