import asyncio
import json
import logging
from pathlib import Path
from typing import List, Dict, Optional
from youtube_search import get_playlist_video_ids, get_channel_video_ids
from transcript_utils import save_clip_transcripts, extract_clip_transcripts
from transcript import fetch_transcript
from heatmap import process_video
from video_downloader import download_video
from video_splitter import cut_video_into_clips

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('processing.log'),
        logging.StreamHandler()
    ]
)

class BulkProcessor:
    def __init__(self, concurrency: int = 4):
        self.semaphore = asyncio.Semaphore(concurrency)
        self.logger = logging.getLogger(__name__)
        
    async def _process_single_video(self, video_id: str, output_dir: str, 
                                  lang: str, transcript_enabled: bool) -> Optional[Dict]:
        """Process single video with configurable transcript handling"""
        async with self.semaphore:
            try:
                video_output_dir = Path(output_dir) / video_id
                video_output_dir.mkdir(parents=True, exist_ok=True)

                # Download video
                if not (video_path := await self._download_video(video_id)):
                    return self._error_result(video_id, "Download failed")

                # Process transcript if enabled
                transcript, transcript_error = await self._handle_transcript(
                    video_id, lang, transcript_enabled
                )
                if transcript_enabled and transcript_error:
                    return self._error_result(video_id, transcript_error)

                # Analyze heatmap and generate clips
                if not (clips := await process_video(video_id)):
                    return self._error_result(video_id, "No clips detected")

                # Process clips with/without transcripts
                processed_clips = self._process_clips(
                    clips, transcript, transcript_enabled
                )

                # Cut video into clips
                clip_dir, clip_paths = await self._cut_video_clips(
                    video_path, clips, video_output_dir
                )
                if not clip_paths:
                    return self._error_result(video_id, "Clipping failed")

                # Save results and metadata
                metadata = self._save_results(
                    processed_clips, clip_paths, video_output_dir, 
                    output_dir, transcript_enabled
                )

                return {
                    'video_id': video_id,
                    'status': 'success',
                    'metadata': metadata,
                    'clips': processed_clips
                }

            except Exception as e:
                self.logger.error(f"Processing failed {video_id}: {str(e)}", exc_info=True)
                return self._error_result(video_id, str(e))

    async def _download_video(self, video_id: str) -> Optional[str]:
        """Handle video download with retries"""
        self.logger.info(f"Downloading {video_id}")
        for attempt in range(3):
            try:
                if path := download_video(video_id):
                    if Path(path).exists():
                        return path
                if attempt == 2:
                    return None
                await asyncio.sleep(2 ** attempt)
            except Exception as e:
                self.logger.warning(f"Download attempt {attempt+1} failed: {str(e)}")
        return None

    async def _handle_transcript(self, video_id: str, lang: str, 
                               enabled: bool) -> tuple:
        """Handle transcript processing with fallbacks"""
        if not enabled:
            return [], None
            
        try:
            if transcript_json := fetch_transcript(video_id, lang):
                return json.loads(transcript_json), None
            return [], "Transcript unavailable"
        except Exception as e:
            self.logger.error(f"Transcript error {video_id}: {str(e)}")
            return [], str(e)

    def _process_clips(self, clips: List[Dict], transcript: List[Dict],
                     enabled: bool) -> List[Dict]:
        """Process clips with transcript integration"""
        return (
            extract_clip_transcripts(transcript, clips) 
            if enabled 
            else [{
                **clip,
                'transcript': [],
                'word_count': 0
            } for clip in clips]
        )

    async def _cut_video_clips(self, video_path: str, clips: List[Dict],
                             output_dir: Path) -> tuple:
        """Handle video clipping process"""
        clip_dir = output_dir / "clips"
        clip_paths = cut_video_into_clips(video_path, clips, str(clip_dir))
        return clip_dir, clip_paths or []

    def _save_results(self, clips: List[Dict], clip_paths: List[str],
                    output_dir: Path, base_dir: str, 
                    transcript_enabled: bool) -> Dict:
        """Save all processing artifacts"""
        metadata = {
            'video_path': str(output_dir / "source.mp4"),
            'clip_dir': str(output_dir / "clips"),
            'clip_count': len(clip_paths)
        }

        if transcript_enabled:
            transcript_path = output_dir / "clip_transcripts.json"
            save_clip_transcripts(clips, str(transcript_path))
            metadata['transcript_path'] = str(transcript_path)

        # Add relative paths for portability
        for clip, path in zip(clips, clip_paths):
            clip['video_path'] = str(Path(path).relative_to(base_dir))

        return metadata

    def _error_result(self, video_id: str, error: str) -> Dict:
        """Generate standardized error response"""
        self.logger.error(f"Failed processing {video_id}: {error}")
        return {
            'video_id': video_id,
            'status': 'failed',
            'error': error
        }

    async def process_sources(self, sources: List[str], lang: str, 
                            output_dir: str, transcript_enabled: bool) -> Dict:
        """Main processing entry point"""
        video_ids = await self._resolve_sources(sources)
        tasks = [self._process_single_video(
            vid, output_dir, lang, transcript_enabled
        ) for vid in video_ids]
        
        results = await asyncio.gather(*tasks)
        return self._format_results(results)

    async def _resolve_sources(self, sources: List[str]) -> List[str]:
        """Resolve input sources to video IDs"""
        video_ids = []
        for source in sources:
            try:
                if "youtube.com/playlist" in source:
                    video_ids.extend(get_playlist_video_ids(source) or [])
                elif "youtube.com/channel" in source:
                    video_ids.extend(get_channel_video_ids(source) or [])
                elif len(source) == 11:
                    video_ids.append(source)
            except Exception as e:
                self.logger.error(f"Source resolution error: {str(e)}")
        return list(set(video_ids))

    def _format_results(self, results: List) -> Dict:
        """Generate comprehensive processing report"""
        success = [r for r in results if r['status'] == 'success']
        return {
            'total_processed': len(results),
            'success_count': len(success),
            'failure_count': len(results) - len(success),
            'success_rate': round((len(success)/len(results))*100, 2) if results else 0,
            'successful_videos': success,
            'failed_videos': [r for r in results if r['status'] == 'failed']
        }
