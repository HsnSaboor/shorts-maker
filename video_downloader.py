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
    """Download with enhanced retry logic and detailed logging"""
    for attempt in range(3):
        try:
            logger.info(f"Starting {stream_type} download (attempt {attempt+1}/3)")
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True
            )

            progress_pattern = re.compile(r'(\d+\.\d+)%')
            for line in process.stdout:
                if progress_callback and (match := progress_pattern.search(line)):
                    progress = float(match.group(1))
                    progress_callback(stream_type, progress)
                    logger.debug(f"{stream_type} progress: {progress}%")

            process.wait()
            
            if process.returncode != 0:
                raise subprocess.CalledProcessError(
                    process.returncode, 
                    command, 
                    output=process.stdout.read()
                )

            output_file = Path(command[-2].replace('%(ext)s', 'mp4' if stream_type == 'video' else 'm4a'))
            if not output_file.exists():
                raise FileNotFoundError(f"Output file missing: {output_file}")

            logger.info(f"{stream_type.capitalize()} download completed successfully")
            return output_file

        except Exception as e:
            logger.warning(f"{stream_type} download attempt {attempt+1} failed: {str(e)}")
            if attempt == 2:
                logger.error(f"Permanent {stream_type} download failure after 3 attempts")
                raise RuntimeError(f"Failed after 3 attempts: {str(e)}") from e

    raise RuntimeError("Unexpected error in download retry loop")

def _download_streams(video_id: str, progress_callback: Callable[[str, float], None]) -> Tuple[Path, Path]:
    """Download both video and audio streams with detailed tracking"""
    logger.info(f"Starting download streams for {video_id}")
    base_path = Path("temp_videos") / video_id
    base_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        video_file = _download_with_retry(
            command=[
                'yt-dlp',
                '-f', 'bestvideo[height<=1440][ext=mp4]',
                '--concurrent-fragments', '256',
                '--http-chunk-size', '300M',
                '-o', str(base_path) + '_video.%(ext)s',
                f'https://www.youtube.com/watch?v={video_id}'
            ],
            stream_type="video",
            progress_callback=progress_callback
        )

        audio_file = _download_with_retry(
            command=[
                'yt-dlp',
                '-f', 'bestaudio[ext=m4a]',
                '--concurrent-fragments', '8',
                '-o', str(base_path) + '_audio.%(ext)s',
                f'https://www.youtube.com/watch?v={video_id}'
            ],
            stream_type="audio",
            progress_callback=progress_callback
        )

        logger.info(f"Successfully downloaded both streams for {video_id}")
        return video_file, audio_file

    except Exception as e:
        logger.error(f"Failed to download streams for {video_id}: {str(e)}")
        raise

def _merge_streams(video_id: str, video_file: Path, audio_file: Path, final_file: Path) -> str:
    """Merge media streams with validation and cleanup"""
    logger.info(f"Starting stream merge for {video_id}")
    merge_command = [
        'ffmpeg',
        '-y', '-i', str(video_file),
        '-i', str(audio_file),
        '-c:v', 'copy',
        '-c:a', 'aac',
        '-loglevel', 'error',
        str(final_file)
    ]

    try:
        result = subprocess.run(merge_command, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"Merge failed: {result.stderr[:200]}")
        
        if not final_file.exists():
            raise FileNotFoundError(f"Merged file not created: {final_file}")

        logger.info(f"Successfully merged streams for {video_id}")
        return str(final_file)

    finally:
        video_file.unlink(missing_ok=True)
        audio_file.unlink(missing_ok=True)
        logger.debug("Cleaned up temporary stream files")

async def download_video(video_id: str, progress_callback: Optional[Callable[[str, float], None]] = None) -> Optional[str]:
    """Main video download entry point with cache handling"""
    try:
        output_dir = Path("temp_videos")
        output_dir.mkdir(exist_ok=True)
        final_file = output_dir / f"{video_id}.mp4"

        if final_file.exists():
            logger.info(f"Using cached video: {final_file}")
            if progress_callback:
                progress_callback("video", 100)
                progress_callback("audio", 100)
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

        logger.info(f"Completed video processing for {video_id}")
        return final_path

    except Exception as e:
        logger.error(f"Video processing failed for {video_id}: {str(e)}")
        return None
