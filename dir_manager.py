import os
import tempfile
import zipfile
from pathlib import Path
from typing import List, Dict
import logging

logger = logging.getLogger(__name__)

class DirectoryManager:
    def __init__(self):
        self.temp_dir = None
        self.clip_data = []

    def create_temp_dir(self) -> str:
        """Create and return a temporary directory"""
        self.temp_dir = tempfile.TemporaryDirectory()
        logger.info(f"Created temp directory: {self.temp_dir.name}")
        return self.temp_dir.name

    def get_clip_dir(self, video_id: str) -> Path:
        """Get directory path for a video's clips"""
        path = Path(self.temp_dir.name) / video_id / "clips"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def create_zip(self) -> bytes:
        """Create ZIP file from processed files"""
        zip_buffer = io.BytesIO()
        try:
            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                for root, _, files in os.walk(self.temp_dir.name):
                    for file in files:
                        file_path = Path(root) / file
                        if file_path.suffix in ('.mp4', '.json'):
                            arcname = file_path.relative_to(self.temp_dir.name)
                            zip_file.write(file_path, arcname=arcname)
                            logger.info(f"Added to ZIP: {arcname}")
        except Exception as e:
            logger.error(f"ZIP creation failed: {str(e)}")
        return zip_buffer.getvalue()

    def cleanup(self):
        """Clean up temporary resources"""
        if self.temp_dir:
            self.temp_dir.cleanup()
            logger.info("Cleaned up temporary directory")
