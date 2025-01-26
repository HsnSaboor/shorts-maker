import asyncio
import json
import logging
from pathlib import Path
from typing import List, Dict, Optional, Callable, Awaitable
from transcript_utils import save_clip_transcripts, extract_clip_transcripts
from video_downloader import download_video

# Add missing imports (replace with your actual implementations)
from transcript import fetch_transcript
from heatmap import process_video
from video_splitter import cut_video_into_clips

class BulkProcessor:
    def __init__(self, 
                 concurrency: int = 4,
                 progress_callback: Optional[Callable[[str, int, int], Awaitable[None]]] = None):
        self.semaphore = asyncio.Semaphore(concurrency)
        self.progress_callback = progress_callback
        self.logger = logging.getLogger(__name__)

    async def _process_single_video(self, 
                                  video_id: str, 
                                  output_dir: str, 
                                  lang: str,
                                  total_videos: int,
                                  index: int) -> Optional[Dict]:

    async def process_sources(self, sources: List[str], lang: str, output_dir: str) -> Dict:
        video_ids = await self._resolve_sources(sources)
        tasks = [self._process_single_video(vid, output_dir, lang) for vid in video_ids]
        results = await asyncio.gather(*tasks)
        return self._format_results(results)

    async def _resolve_sources(self, sources: List[str]) -> List[str]:
        """Convert various source types to video IDs with emoji logging"""
        video_ids = []
        for source in sources:
            try:
                if "youtube.com/playlist" in source or "list=" in source:
                    self.logger.info(f"🎵 Processing playlist: {source}")
                    if ids := get_playlist_video_ids(source):
                        video_ids.extend(ids)
                elif "youtube.com/channel" in source or "youtube.com/user" in source or "youtube.com/c/" in source:
                    self.logger.info(f"📺 Processing channel: {source}")
                    if ids := get_channel_video_ids(source):
                        video_ids.extend(ids)
                elif len(source) == 11:
                    self.logger.info(f"🎥 Processing video ID: {source}")
                    video_ids.append(source)
                else:
                    self.logger.warning(f"🔍 Unrecognized source: {source}")
            except Exception as e:
                self.logger.error(f"⚠️ Error processing {source}: {str(e)}")
        return list(set(video_ids))

    def _format_results(self, results: List) -> Dict:
        """Generate processing report with emoji status"""
        report = {
            'success': [],
            'failed': [],
            'total_processed': len(results),
            'success_count': 0,
            'failure_count': 0,
            'success_rate': 0
        }
        
        for result in results:
            if result['status'] == 'success':
                report['success'].append(result)
                report['success_count'] += 1
            else:
                result['error'] = f"⚠️ {result.get('error', 'Unknown error')}"
                report['failed'].append(result)
                report['failure_count'] += 1
        
        if report['total_processed'] > 0:
            report['success_rate'] = round(
                (report['success_count'] / report['total_processed']) * 100, 2
            )
            
        self.logger.info(
            f"📊 Final report: {report['success_count']} ✅ | "
            f"{report['failure_count']} ❌ | "
            f"Success rate: {report['success_rate']}%"
        )
        return report
