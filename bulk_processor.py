import asyncio
import json
import logging
from pathlib import Path
from typing import List, Dict, Optional, Callable, Awaitable
from youtube_search import get_playlist_video_ids, get_channel_video_ids
from transcript_utils import save_clip_transcripts, extract_clip_transcripts
from video_downloader import download_video
from transcript import fetch_transcript
from heatmap import process_video
from video_splitter import cut_video_into_clips

logger = logging.getLogger(__name__)

class BulkProcessor:
    def __init__(
        self, 
        concurrency: int = 4,
        progress_callback: Optional[Callable[[str, int, float], Awaitable[None]]] = None
    ):
        self.semaphore = asyncio.Semaphore(concurrency)
        self.progress_callback = progress_callback
        self._validate_dependencies()

    def _validate_dependencies(self):
        """Ensure required binaries are available"""
        try:
            subprocess.run(['yt-dlp', '--version'], check=True, capture_output=True)
            subprocess.run(['ffmpeg', '-version'], check=True, capture_output=True)
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            logger.error("Missing required dependency: %s", str(e))
            raise RuntimeError("Missing required binaries (yt-dlp/ffmpeg)") from e

    async def _process_single_video(
        self, 
        video_id: str, 
        output_dir: str, 
        lang: str,
        total_videos: int,
        index: int
    ) -> Optional[Dict]:
        """Full processing pipeline for a single video"""
        async with self.semaphore:
            try:
                logger.info(f"Starting processing pipeline for {video_id}")
                video_dir = Path(output_dir) / video_id
                video_dir.mkdir(parents=True, exist_ok=True)

                # Setup progress reporting
                def handle_progress(stream_type: str, progress: float):
                    if self.progress_callback:
                        asyncio.run_coroutine_threadsafe(
                            self.progress_callback(stream_type, index, progress),
                            loop=asyncio.get_running_loop()
                        )

                # Download phase
                logger.debug(f"Downloading {video_id}")
                video_path = await download_video(video_id, handle_progress)
                if not video_path or not Path(video_path).exists():
                    raise ValueError(f"Download failed for {video_id}")

                # Transcript phase
                logger.debug(f"Fetching transcript for {video_id}")
                if self.progress_callback:
                    await self.progress_callback("transcript", index, 0)
                
                transcript = await asyncio.to_thread(fetch_transcript, video_id, lang)
                
                if self.progress_callback:
                    await self.progress_callback("transcript", index, 100)

                # Analysis phase
                logger.debug(f"Analyzing {video_id}")
                if self.progress_callback:
                    await self.progress_callback("heatmap", index, 0)
                
                clips = await process_video(video_id)
                
                if self.progress_callback:
                    await self.progress_callback("heatmap", index, 100)

                # Clip processing
                logger.debug(f"Processing clips for {video_id}")
                valid_clips = [c for c in clips if c['end'] > c['start']][:10]
                if not valid_clips:
                    raise ValueError(f"No valid clips generated for {video_id}")

                if self.progress_callback:
                    await self.progress_callback("clips", index, 0)

                clip_dir = video_dir / "clips"
                clip_paths = await asyncio.to_thread(
                    cut_video_into_clips, video_path, valid_clips, str(clip_dir)
                )
                
                if self.progress_callback:
                    await self.progress_callback("clips", index, 100)

                # Save results
                logger.debug(f"Saving results for {video_id}")
                processed_clips = extract_clip_transcripts(json.loads(transcript), valid_clips)
                transcript_path = video_dir / "clip_transcripts.json"
                await asyncio.to_thread(
                    save_clip_transcripts, processed_clips, str(transcript_path)
                )

                logger.info(f"Successfully processed {video_id}")
                return {
                    'video_id': video_id,
                    'status': 'success',
                    'clips': clip_paths,
                    'clip_dir': str(clip_dir),
                    'transcript_path': str(transcript_path)
                }

            except Exception as e:
                logger.error(f"Processing failed for {video_id}: {str(e)}", exc_info=True)
                return {
                    'video_id': video_id,
                    'status': 'failed',
                    'error': str(e)
                }

    async def process_sources(self, sources: List[str], lang: str, output_dir: str) -> Dict:
        """Process multiple video sources"""
        logger.info(f"Starting processing for {len(sources)} sources")
        video_ids = await self._resolve_sources(sources)
        total = len(video_ids)
        
        if total == 0:
            logger.warning("No valid video IDs found")
            return {
                'success': [],
                'failed': [],
                'total_processed': 0,
                'success_count': 0,
                'failure_count': 0,
                'success_rate': 0
            }

        logger.info(f"Processing {total} videos")
        tasks = [
            self._process_single_video(vid, output_dir, lang, total, idx)
            for idx, vid in enumerate(video_ids)
        ]
        results = await asyncio.gather(*tasks)
        return self._format_results(results)

    async def _resolve_sources(self, sources: List[str]) -> List[str]:
        """Resolve various source types to video IDs"""
        video_ids = []
        logger.info(f"Resolving {len(sources)} input sources")
        
        for source in sources:
            try:
                source = source.strip()
                if not source:
                    continue

                logger.debug(f"Processing source: {source}")
                if "youtube.com/playlist" in source or "list=" in source:
                    ids = get_playlist_video_ids(source)
                    if ids:
                        logger.info(f"Found {len(ids)} videos in playlist")
                        video_ids.extend(ids)
                elif "youtube.com/channel" in source or "youtube.com/user" in source or "youtube.com/c/" in source:
                    ids = get_channel_video_ids(source)
                    if ids:
                        logger.info(f"Found {len(ids)} videos in channel")
                        video_ids.extend(ids)
                elif len(source) == 11:
                    logger.info(f"Processing single video ID: {source}")
                    video_ids.append(source)
                else:
                    logger.warning(f"Unrecognized source format: {source}")
            except Exception as e:
                logger.error(f"Error processing source {source}: {str(e)}", exc_info=True)

        return list(set(video_ids))

    def _format_results(self, results: List) -> Dict:
        """Generate final processing report"""
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

        logger.info(
            "Processing complete: "
            f"{report['success_count']} succeeded, "
            f"{report['failure_count']} failed "
            f"(Success rate: {report['success_rate']}%)"
        )
        return report
