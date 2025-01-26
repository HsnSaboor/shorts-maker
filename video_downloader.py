# video_downloader.py
import os
import re
import subprocess
import logging
from pathlib import Path
from typing import Optional, Tuple

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def _download_with_retry(command: list, stream_type: str, progress_callback: callable, max_retries: int = 3) -> Path:
    """Download with retry mechanism"""
    for attempt in range(max_retries):
        try:
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
            if process.returncode == 0:
                output_file = Path(command[-2].replace('%(ext)s', 'mp4' if stream_type == 'video' else 'm4a'))
                if output_file.exists():
                    return output_file
                raise FileNotFoundError(f"Output file missing: {output_file}")

            raise subprocess.CalledProcessError(
                process.returncode, 
                command, 
                output=process.stdout.read()
            )

        except Exception as e:
            if attempt == max_retries - 1:
                raise RuntimeError(
                    f"Failed after {max_retries} attempts: {str(e)}"
                ) from e
            logger.warning(f"Retrying {stream_type} download (attempt {attempt + 1})...")

def _download_streams(video_id: str, progress_callback: callable) -> Tuple[Path, Path]:
    """Download video and audio streams"""
    base_path = Path("temp_videos") / video_id

    # Download video stream
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

    # Download audio stream
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

    return video_file, audio_file

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
