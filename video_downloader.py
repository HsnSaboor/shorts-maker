import os
import subprocess
import logging
import sys
from pathlib import Path
from typing import Optional, Callable, Union

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('downloads.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

class VideoDownloader:
    def __init__(self, output_dir: Union[str, Path] = "temp_videos"):
        """Initialize downloader with output directory"""
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
    def _create_progress_handler(self, progress_callback: Optional[Callable] = None) -> Callable:
        """Create progress handler compatible with both CLI and GUI"""
        if progress_callback:
            return progress_callback
            
        # Default CLI progress handler
        class CLIProgress:
            def __init__(self):
                self.last_line_length = 0

            def __call__(self, percent: float):
                msg = f"Download progress: {percent:.1f}%"
                sys.stderr.write('\r' + ' ' * self.last_line_length + '\r')
                sys.stderr.write(msg)
                sys.stderr.flush()
                self.last_line_length = len(msg)

            def complete(self):
                sys.stderr.write('\n')
                sys.stderr.flush()

        return CLIProgress()

    def download_video(self, video_id: str, progress_callback: Optional[Callable] = None) -> Optional[Path]:
        """Download YouTube video with progress reporting
        
        Args:
            video_id: YouTube video ID
            progress_callback: Callback function accepting percentage (0-100)
            
        Returns:
            Path to downloaded video file or None if failed
        """
        progress = self._create_progress_handler(progress_callback)
        base_path = self.output_dir / video_id
        
        try:
            final_path = base_path.with_name(f"{base_path.name}.mp4")
            
            # Use cached file if available
            if final_path.exists():
                logger.info(f"Using cached video: {final_path}")
                return final_path

            # Configure yt-dlp command for best quality with merged audio
            command = [
                'yt-dlp',
                '-f', 'bestvideo[height<=1440][ext=mp4]+bestaudio[ext=m4a]/best[height<=1440][ext=mp4]',
                '--concurrent-fragments', '256',
                '--http-chunk-size', '300M',
                '-o', str(base_path) + ".%(ext)s",
                '--merge-output-format', 'mp4',
                '--progress',
                f'https://www.youtube.com/watch?v={video_id}'
            ]

            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                bufsize=1
            )

            # Process output in real-time
            for line in process.stdout:
                line = line.strip()
                if line:
                    self._process_line(line, progress)

            # Check completion status
            process.wait()
            if process.returncode != 0:
                logger.error(f"Download failed for {video_id}")
                return None

            # Find and rename output file
            return self._handle_output_file(video_id, final_path)

        except Exception as e:
            logger.error(f"Download error: {str(e)}")
            return None
        finally:
            # Cleanup progress display
            if callable(progress) and hasattr(progress, 'complete'):
                progress.complete()

    def _process_line(self, line: str, progress: Callable):
        """Parse yt-dlp output and update progress"""
        if "[download]" in line and "%" in line:
            try:
                percent_str = line.split("%")[0].split()[-1]
                percent = float(percent_str)
                progress(percent)
            except (ValueError, IndexError) as e:
                logger.debug(f"Progress parse error: {str(e)}")
        else:
            logger.info(f"yt-dlp: {line}")

    def _handle_output_file(self, video_id: str, final_path: Path) -> Optional[Path]:
        """Handle output file renaming and validation"""
        # Find any generated video files
        for f in self.output_dir.glob(f"{video_id}.*"):
            if f.suffix in ['.mp4', '.mkv', '.webm']:
                if f != final_path:
                    f.rename(final_path)
                logger.info(f"Successfully downloaded: {final_path}")
                return final_path
        
        logger.error(f"No video file found for {video_id}")
        return None

if __name__ == "__main__":
    # CLI Interface
    import argparse
    parser = argparse.ArgumentParser(description='YouTube Video Downloader')
    parser.add_argument('video_id', help='YouTube video ID')
    parser.add_argument('-o', '--output', help='Output directory', default='downloads')
    args = parser.parse_args()

    # Execute download
    downloader = VideoDownloader(args.output)
    result = downloader.download_video(args.video_id)
    
    # Output result
    if result:
        print(f"Download successful:\n{result}")
    else:
        print("❌ Download failed")
        sys.exit(1)
