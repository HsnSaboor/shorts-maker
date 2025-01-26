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

class VideoDownloader:
    def __init__(self):
        self.last_progress = 0

    def _execute_command(self, command: list, progress_prefix: str) -> bool:
        """Execute download command with single-line progress updates"""
        try:
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True
            )

            while True:
                line = process.stdout.readline()
                if not line:
                    break
                line = line.strip()
                if line and "[download]" in line and "%" in line:
                    parts = line.replace("[download]", "").strip().split()
                    progress = f"{progress_prefix}: {parts[0]} | Size: {parts[1]} | Speed: {parts[3]}/s | ETA: {parts[5]}"
                    print(f"\r{progress.ljust(80)}", end='', flush=True)

            process.wait()
            return process.returncode == 0

        except Exception as e:
            logger.error(f"Command execution failed: {str(e)}")
            return False

    def _merge_streams(self, base_path: Path, final_path: Path) -> None:
        """Merge separate audio/video streams using FFmpeg"""
        video_file = next(base_path.parent.glob(f"{base_path.name}_video.*"))
        audio_file = next(base_path.parent.glob(f"{base_path.name}_audio.*"))
        
        merge_command = [
            'ffmpeg',
            '-i', str(video_file),
            '-i', str(audio_file),
            '-c', 'copy',
            '-loglevel', 'error',
            '-y',
            str(final_path)
        ]
        
        subprocess.run(merge_command, check=True)
        video_file.unlink()
        audio_file.unlink()
        logger.info(f"Merged streams to {final_path.name}")

    def download_video(self, video_id: str) -> Optional[str]:
        """Download video using optimized separate audio/video streams"""
        try:
            logger.info(f"Starting download for video: {video_id}")
            output_dir = Path("temp_videos")
            output_dir.mkdir(exist_ok=True)
            base_path = output_dir / video_id
            final_path = base_path.with_suffix('.mkv')

            # Video download command
            video_command = [
                'yt-dlp',
                '-f', 'bestvideo[height<=1440]',
                '--concurrent-fragments', '256',
                '--http-chunk-size', '300M',
                '--no-simulate',
                '-o', f"{base_path}_video.%(ext)s",
                '--progress',
                f'https://www.youtube.com/watch?v={video_id}'
            ]

            # Audio download command
            audio_command = [
                'yt-dlp',
                '-f', 'bestaudio',
                '--concurrent-fragments', '8',
                '--no-simulate',
                '-o', f"{base_path}_audio.%(ext)s",
                '--progress',
                f'https://www.youtube.com/watch?v={video_id}'
            ]

            # Download video
            print()
            video_success = self._execute_command(video_command, "Video Progress")
            print()  # Newline after video progress
            
            # Download audio
            audio_success = self._execute_command(audio_command, "Audio Progress")
            print("\n")  # Newline after audio progress

            if not (video_success and audio_success):
                logger.error("Download failed for video or audio stream")
                return None

            # Merge streams
            self._merge_streams(base_path, final_path)
            
            if final_path.exists():
                size_mb = final_path.stat().st_size / (1024 * 1024)
                logger.info(f"Download completed successfully ({size_mb:.1f} MB)")
                return str(final_path)

            return None

        except Exception as e:
            logger.error(f"Download error: {str(e)}")
            return None
