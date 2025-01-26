# video_downloader.py (updated)
import subprocess
from typing import Optional, Tuple
import re

def download_video(video_id: str, progress_callback: Optional[callable] = None) -> Optional[str]:
    """Download YouTube video with enhanced error handling"""
    try:
        # Validate video ID format
        if not re.match(r'^[a-zA-Z0-9_-]{11}$', video_id):
            raise ValueError(f"Invalid YouTube video ID: {video_id}")

        output_dir = Path("temp_videos")
        output_dir.mkdir(exist_ok=True)
        final_file = output_dir / f"{video_id}.mp4"

        if final_file.exists():
            logger.info(f"⏩ Using cached video: {final_file}")
            return str(final_file)

        # Test YouTube access
        if not _check_youtube_access():
            raise ConnectionError("Could not connect to YouTube")

        # Download streams with retries
        video_file, audio_file = _download_streams(video_id, progress_callback)
        
        # Merge streams
        return _merge_streams(video_id, video_file, audio_file, final_file)

    except Exception as e:
        logger.error(f"🔥 Download failed for {video_id}: {str(e)}")
        return None

def _check_youtube_access() -> bool:
    """Verify YouTube connectivity"""
    try:
        test_command = ['yt-dlp', '--dump-json', '--quiet', 'https://youtu.be/BaW_jenozKc']
        result = subprocess.run(test_command, capture_output=True, timeout=10)
        return result.returncode == 0
    except Exception as e:
        logger.error(f"YouTube connection test failed: {str(e)}")
        return False

def _download_streams(video_id: str, progress_callback: callable) -> Tuple[Path, Path]:
    """Download video and audio streams with retries"""
    base_path = Path("temp_videos") / video_id
    max_retries = 3

    # Download video stream
    video_file = _download_with_retry(
        command=[
            'yt-dlp',
            '-f', 'bestvideo[height<=1440][ext=mp4]',
            '--concurrent-fragments', '4',  # Reduced for stability
            '--socket-timeout', '30',
            '-o', str(base_path) + '_video.%(ext)s',
            f'https://www.youtube.com/watch?v={video_id}'
        ],
        stream_type="video",
        progress_callback=progress_callback,
        max_retries=max_retries
    )

    # Download audio stream
    audio_file = _download_with_retry(
        command=[
            'yt-dlp',
            '-f', 'bestaudio[ext=m4a]',
            '--concurrent-fragments', '2',
            '-o', str(base_path) + '_audio.%(ext)s',
            f'https://www.youtube.com/watch?v={video_id}'
        ],
        stream_type="audio",
        progress_callback=progress_callback,
        max_retries=max_retries
    )

    return video_file, audio_file

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

def _merge_streams(video_id: str, video_file: Path, audio_file: Path, final_file: Path) -> str:
    """Merge streams with validation"""
    # Verify input files
    if not video_file.exists():
        raise FileNotFoundError(f"Video file missing: {video_file}")
    if not audio_file.exists():
        raise FileNotFoundError(f"Audio file missing: {audio_file}")

    # Check ffmpeg availability
    if subprocess.run(['ffmpeg', '-version'], capture_output=True).returncode != 0:
        raise RuntimeError("ffmpeg not installed or not in PATH")

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
