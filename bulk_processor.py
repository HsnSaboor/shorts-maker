# bulk_processor.py
import asyncio
import json
import logging
from pathlib import Path
from typing import List, Dict, Optional, Callable, Awaitable
from transcript_utils import save_clip_transcripts, extract_clip_transcripts
from video_downloader import download_video
from transcript import fetch_transcript
from heatmap import process_video
from video_splitter import cut_video_into_clips

class BulkProcessor:
    def __init__(
        self, 
        concurrency: int = 4,
        progress_callback: Optional[Callable[[str, int, int], Awaitable[None]]] = None
    ):
        self.semaphore = asyncio.Semaphore(concurrency)
        self.progress_callback = progress_callback
        self.logger = logging.getLogger(__name__)

    async def _process_single_video(
        self, 
        video_id: str, 
        output_dir: str, 
        lang: str,
        total_videos: int,
        index: int
    ) -> Optional[Dict]:
        async with self.semaphore:
            try:
                video_dir = Path(output_dir) / video_id
                video_dir.mkdir(parents=True, exist_ok=True)

                # Download progress handler
                def download_progress(stream_type: str, progress: float):
                    if self.progress_callback:
                        asyncio.create_task(
                            self.progress_callback("download", index, progress)
                        )

                # Download video
                self.logger.info(f"Starting download for {video_id}")
                video_path = await asyncio.to_thread(
                    download_video, video_id, download_progress
                )
                if not video_path:
                    raise ValueError("Download failed")

                # Transcript processing
                if self.progress_callback:
                    await self.progress_callback("transcript", index, 0)
                self.logger.info(f"Fetching transcript for {video_id}")
                transcript = await asyncio.to_thread(fetch_transcript, video_id, lang)
                if self.progress_callback:
                    await self.progress_callback("transcript", index, 100)

                # Heatmap generation
                if self.progress_callback:
                    await self.progress_callback("heatmap", index, 0)
                self.logger.info(f"Analyzing heatmap for {video_id}")
                clips = await process_video(video_id)
                if self.progress_callback:
                    await self.progress_callback("heatmap", index, 100)

                # Clip processing
                valid_clips = [c for c in clips if c['end'] > c['start']][:10]
                if not valid_clips:
                    raise ValueError("No valid clips generated")

                # Create video clips
                if self.progress_callback:
                    await self.progress_callback("clips", index, 0)
                self.logger.info(f"Creating clips for {video_id}")
                clip_dir = video_dir / "clips"
                clip_paths = await asyncio.to_thread(
                    cut_video_into_clips, video_path, valid_clips, str(clip_dir)
                )
                if self.progress_callback:
                    await self.progress_callback("clips", index, 100)

                # Save transcripts
                processed_clips = extract_clip_transcripts(json.loads(transcript), valid_clips)
                transcript_path = video_dir / "clip_transcripts.json"
                await asyncio.to_thread(
                    save_clip_transcripts, processed_clips, str(transcript_path)
                )

                return {
                    'video_id': video_id,
                    'status': 'success',
                    'clips': clip_paths,
                    'clip_dir': str(clip_dir),
                    'transcript_path': str(transcript_path)
                }

            except Exception as e:
                self.logger.error(f"Processing failed: {str(e)}")
                return {
                    'video_id': video_id,
                    'status': 'failed',
                    'error': str(e)
                }

    async def process_sources(
        self, 
        sources: List[str], 
        lang: str, 
        output_dir: str
    ) -> Dict:
        video_ids = await self._resolve_sources(sources)
        total = len(video_ids)
        tasks = [
            self._process_single_video(vid, output_dir, lang, total, idx)
            for idx, vid in enumerate(video_ids)
        ]
        results = await asyncio.gather(*tasks)
        return self._format_results(results)

    async def _resolve_sources(self, sources: List[str]) -> List[str]:
        video_ids = []
        for source in sources:
            try:
                if "youtube.com/playlist" in source or "list=" in source:
                    self.logger.info(f"Processing playlist: {source}")
                    ids = get_playlist_video_ids(source)
                    if ids:
                        video_ids.extend(ids)
                elif "youtube.com/channel" in source or "youtube.com/user" in source or "youtube.com/c/" in source:
                    self.logger.info(f"Processing channel: {source}")
                    ids = get_channel_video_ids(source)
                    if ids:
                        video_ids.extend(ids)
                elif len(source) == 11:
                    self.logger.info(f"Processing video ID: {source}")
                    video_ids.append(source)
                else:
                    self.logger.warning(f"Unrecognized source: {source}")
            except Exception as e:
                self.logger.error(f"Error processing {source}: {str(e)}")
        return list(set(video_ids))

    def _format_results(self, results: List) -> Dict:
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
            f"Final report: {report['success_count']} ✅ | "
            f"{report['failure_count']} ❌ | "
            f"Success rate: {report['success_rate']}%"
        )
        return report
