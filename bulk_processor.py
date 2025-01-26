import asyncio
import json
import logging
from pathlib import Path
from typing import List, Dict, Optional
from youtube_search import get_playlist_video_ids, get_channel_video_ids
from transcript_utils import save_clip_transcripts, extract_clip_transcripts
from transcript import fetch_transcript
from heatmap import process_video, fallback_clip_detection
from video_downloader import download_video, get_video_info
from video_splitter import cut_video_into_clips

class BulkProcessor:
    def __init__(self, concurrency: int = 4):
        self.semaphore = asyncio.Semaphore(concurrency)
        self.logger = logging.getLogger(__name__)
        self.progress = 0
        
    async def _process_single_video(self, video_id: str, output_dir: str, lang: str) -> Optional[Dict]:
        async with self.semaphore:
            try:
                self.logger.info(f"🚀 Starting processing for {video_id}")
                video_dir = Path(output_dir) / video_id
                video_dir.mkdir(parents=True, exist_ok=True)

                # 1. Download video
                self.logger.info(f"⬇️ Downloading {video_id}")
                video_path = download_video(video_id)
                if not video_path or not Path(video_path).exists():
                    raise ValueError(f"❌ Download failed: {video_id}")

                # 2. Get transcript
                self.logger.info(f"📄 Fetching transcript for {video_id}")
                transcript_json = fetch_transcript(video_id, lang)
                if not transcript_json:
                    raise ValueError("📭 No transcript available")
                transcript = json.loads(transcript_json)

                # 3. Analyze content
                self.logger.info(f"🌡️ Analyzing heatmap for {video_id}")
                clips = await process_video(video_id)
                if not clips:
                    self.logger.warning("⚠️ Using fallback clip detection")
                    video_info = get_video_info(video_id)
                    clips = await fallback_clip_detection(video_id, video_info.get('duration', 600))

                # 4. Process clips
                valid_clips = [c for c in clips if c['end'] > c['start']][:10]
                if not valid_clips:
                    raise ValueError("🎬 No valid clips generated")
                
                processed_clips = extract_clip_transcripts(transcript, valid_clips)
                clip_dir = video_dir / "clips"
                clip_paths = cut_video_into_clips(video_path, valid_clips, str(clip_dir))

                # 5. Save results
                transcript_path = video_dir / "clip_transcripts.json"
                save_clip_transcripts(processed_clips, str(transcript_path))
                self.logger.info(f"✅ Successfully processed {video_id}")

                return {
                    'video_id': video_id,
                    'status': 'success',
                    'clips': len(clip_paths),
                    'clip_dir': str(clip_dir),
                    'transcript_path': str(transcript_path),
                    'metadata': valid_clips
                }

            except Exception as e:
                self.logger.error(f"❌ Error processing {video_id}: {str(e)}")
                return {
                    'video_id': video_id,
                    'status': 'failed',
                    'error': str(e)
                }

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
