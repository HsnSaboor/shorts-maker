import asyncio
import json
import logging
from pathlib import Path
from typing import List, Dict, Optional
from youtube_searcher import get_playlist_video_ids, get_channel_video_ids
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
        
    async def _process_single_video(self, video_id: str, output_dir: str, lang: str, transcript_enabled: bool) -> Optional[Dict]:
        """End-to-end processing for a single video with detailed logging"""
        async with self.semaphore:
            try:
                self.logger.info(f"🚀 Starting processing pipeline for video: {video_id}")
                video_output_dir = Path(output_dir) / video_id
                
                # Stage 1: Directory setup
                self.logger.debug(f"📂 Creating output directory: {video_output_dir}")
                video_output_dir.mkdir(parents=True, exist_ok=True)

                # Stage 2: Video download
                self.logger.info(f"⬇️ Starting video download...")
                final_path = download_video(video_id)
                if not final_path or not Path(final_path).exists():
                    raise ValueError(f"❌ Video download failed for {video_id}")
                self.logger.info(f"✅ Successfully downloaded video to: {final_path}")

                # Stage 3: Transcript processing
                self.logger.info(f"📝 Fetching transcript for {video_id}")
                transcript = []
                if transcript_enabled:
                    transcript_json = fetch_transcript(video_id, lang)
                    if not transcript_json:
                        raise ValueError("Failed to fetch transcript")
                    transcript = json.loads(transcript_json)
                self.logger.debug(f"📄 Raw transcript received for {video_id}")
                
                self.logger.info(f"📊 Processed transcript with {len(transcript)} entries")

                # Stage 4: Heatmap analysis
                self.logger.info(f"🌡️ Analyzing heatmap for {video_id}")
                clips = await process_video(video_id)
                if not clips:
                    raise ValueError("❌ No significant clips detected")
                self.logger.info(f"🔍 Found {len(clips)} significant clips")

                # Stage 5: Transcript extraction (if enabled)
                self.logger.debug("✂️ Extracting clip-specific transcripts")
                if transcript_enabled:
                    processed_clips = extract_clip_transcripts(transcript, clips)
                else:
                    processed_clips = [{
                        **clip,
                        'transcript': [],
                        'word_count': 0
                    } for clip in clips]
                self.logger.info(f"📋 Processed {len(processed_clips)} clip transcripts")

                # Stage 6: Video clipping
                self.logger.info("🎬 Cutting video into clips")
                clip_dir = video_output_dir / "clips"
                clip_paths = cut_video_into_clips(final_path, clips, str(clip_dir))
                
                if not clip_paths:
                    raise ValueError("❌ Video clipping failed")
                self.logger.info(f"🎥 Created {len(clip_paths)} video clips")

                # Stage 7: Save results
                self.logger.debug("💾 Saving final results")
                transcript_path = video_output_dir / "clip_transcripts.json"
                save_clip_transcripts(processed_clips, str(transcript_path))
                
                # Add relative paths for portability
                for clip, path in zip(processed_clips, clip_paths):
                    clip['final_path'] = str(Path(path).relative_to(output_dir))

                self.logger.info(f"💡 Successfully processed {video_id}")
                return {
                    'video_id': video_id,
                    'status': 'success',
                    'clips': len(clip_paths),
                    'final_path': str(final_path),
                    'clip_dir': str(clip_dir),
                    'transcript_path': str(transcript_path)
                }

            except Exception as e:
                self.logger.error(f"🔥 Critical error processing {video_id}: {str(e)}", exc_info=True)
                return {
                    'video_id': video_id,
                    'status': 'failed',
                    'error': str(e)
                }

    async def process_sources(self, sources: List[str], lang: str, output_dir: str, transcript_enabled: bool) -> Dict:
        """Process multiple sources with concurrency control"""
        video_ids = await self._resolve_sources(sources)
        tasks = [self._process_single_video(vid, output_dir, lang, transcript_enabled) for vid in video_ids]
        results = await asyncio.gather(*tasks)
        return self._format_results(results)

    async def _resolve_sources(self, sources: List[str]) -> List[str]:
        """Convert various source types to video IDs"""
        video_ids = []
        for source in sources:
            try:
                if "youtube.com/playlist" in source or "list=" in source:
                    if ids := get_playlist_video_ids(source):
                        video_ids.extend(ids)
                elif "youtube.com/channel" in source or "youtube.com/user" in source or "youtube.com/c/" in source:
                    if ids := get_channel_video_ids(source):
                        video_ids.extend(ids)
                elif len(source) == 11:
                    video_ids.append(source)
                else:
                    logging.warning(f"Unrecognized source: {source}")
            except Exception as e:
                logging.error(f"Error processing {source}: {str(e)}")
        return list(set(video_ids))

    def _format_results(self, results: List) -> Dict:
        """Generate processing report"""
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
                report['failed'].append(result)
                report['failure_count'] += 1
        
        if report['total_processed'] > 0:
            report['success_rate'] = round(
                (report['success_count'] / report['total_processed']) * 100, 2
            )
            
        return report
