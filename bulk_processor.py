import logging
import json
from pathlib import Path
from typing import List, Dict, Optional, Callable
from youtube_source_resolver import get_playlist_video_ids, get_channel_video_ids
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
        progress_callback: Optional[Callable[[str, int, float], None]] = None,
        include_transcripts: bool = True
    ):
        self.progress_callback = progress_callback
        self.include_transcripts = include_transcripts
        logger.info(f"🚀 Initializing BulkProcessor (concurrency: {concurrency}, transcripts: {'enabled' if include_transcripts else 'disabled'})")

    def _process_single_video(
        self, 
        video_id: str, 
        output_dir: str, 
        lang: str,
        total_videos: int,
        index: int
    ) -> Optional[Dict]:
        """Process a single video through the entire pipeline."""
        try:
            logger.info(f"🎥 Starting processing of video {index + 1}/{total_videos}: {video_id}")
            video_dir = Path(output_dir) / video_id
            
            logger.info(f"📁 Creating video directory: {video_dir}")
            video_dir.mkdir(parents=True, exist_ok=True)

            def handle_progress(stream_type: str, progress: float):
                if self.progress_callback:
                    self.progress_callback(stream_type, index, progress)
                logger.debug(f"📊 Progress update - {stream_type}: {progress:.1f}%")

            # Step 1: Download Video
            logger.info("📥 Starting video download...")
            video_path = download_video(video_id, handle_progress)
            if not video_path or not Path(video_path).exists():
                logger.error("❌ Video download failed")
                raise ValueError("Download failed")
            logger.info(f"✅ Video downloaded: {video_path}")

            # Step 2: Fetch Transcript (if enabled)
            transcript = None
            if self.include_transcripts:
                logger.info(f"📝 Fetching transcript (language: {lang})...")
                if self.progress_callback:
                    self.progress_callback("transcript", index, 0)
                transcript = fetch_transcript(video_id, lang)
                if self.progress_callback:
                    self.progress_callback("transcript", index, 100)
                if not transcript:
                    logger.error("❌ Failed to fetch transcript")
                    raise ValueError("No transcript available")
                logger.info("✅ Transcript fetched successfully")
            else:
                logger.info("📝 Skipping transcript (disabled)")
                if self.progress_callback:
                    self.progress_callback("transcript", index, 100)

            # Step 3: Generate Heatmap and Process Video
            logger.info("🔥 Generating heatmap analysis...")
            if self.progress_callback:
                self.progress_callback("heatmap", index, 0)
            clips = process_video(video_id)
            if self.progress_callback:
                self.progress_callback("heatmap", index, 100)
            if not clips:
                logger.error("❌ Failed to generate heatmap")
                raise ValueError("Heatmap generation failed")
            logger.info(f"✅ Heatmap analysis complete: {len(clips)} potential clips identified")

            # Step 4: Filter and Process Clips
            logger.info("✂️ Processing video clips...")
            if self.progress_callback:
                self.progress_callback("clips", index, 0)
            valid_clips = [c for c in clips if c['end'] > c['start']][:10]
            if not valid_clips:
                logger.error("❌ No valid clips generated")
                raise ValueError("No valid clips generated")
            logger.info(f"✅ Found {len(valid_clips)} valid clips")

            # Step 5: Cut Video into Clips
            clip_dir = video_dir / "clips"
            logger.info(f"🎬 Cutting video into clips... Output dir: {clip_dir}")
            clip_paths = cut_video_into_clips(video_path, valid_clips, str(clip_dir))
            if not clip_paths:
                logger.error("❌ Failed to create clips")
                raise ValueError("Clip creation failed")
            logger.info(f"✅ Successfully created {len(clip_paths)} clips")

            # Step 6: Process and Save Transcripts (if enabled)
            transcript_path = None
            if self.include_transcripts and transcript:
                logger.info("📝 Processing clip transcripts...")
                processed_clips = extract_clip_transcripts(json.loads(transcript), valid_clips)
                transcript_path = video_dir / "clip_transcripts.json"
                save_clip_transcripts(processed_clips, str(transcript_path))
                logger.info(f"✅ Saved clip transcripts to: {transcript_path}")
            else:
                logger.info("📝 Skipping clip transcripts (disabled)")

            if self.progress_callback:
                self.progress_callback("clips", index, 100)

            logger.info(f"🎉 Successfully completed processing for video: {video_id}")
            result = {
                'video_id': video_id,
                'status': 'success',
                'clips': clip_paths,
                'clip_dir': str(clip_dir)
            }
            if transcript_path:
                result['transcript_path'] = str(transcript_path)
            return result

        except Exception as e:
            logger.error(f"❌ Processing failed for video {video_id}: {str(e)}")
            return {
                'video_id': video_id,
                'status': 'failed',
                'error': str(e)
            }

    def process_sources(self, sources: List[str], lang: str, output_dir: str) -> Dict:
        """Process multiple video sources."""
        logger.info(f"🎯 Starting bulk processing of {len(sources)} sources")
        logger.info(f"📂 Output directory: {output_dir}")
        logger.info(f"🌍 Language: {lang}")

        video_ids = self._resolve_sources(sources)
        total = len(video_ids)
        logger.info(f"🎥 Resolved {total} unique video IDs")

        results = []
        for idx, vid in enumerate(video_ids):
            logger.info(f"⏳ Processing video {idx + 1}/{total}")
            result = self._process_single_video(vid, output_dir, lang, total, idx)
            results.append(result)
            
        return self._format_results(results)

    def _resolve_sources(self, sources: List[str]) -> List[str]:
        """Resolve different types of sources into video IDs."""
        logger.info("🔍 Resolving video sources...")
        video_ids = []
        for source in sources:
            try:
                logger.info(f"📌 Processing source: {source}")
                if "youtube.com/playlist" in source or "list=" in source:
                    logger.info("🎵 Detected playlist source")
                    ids = get_playlist_video_ids(source)
                    if ids:
                        logger.info(f"✅ Found {len(ids)} videos in playlist")
                        video_ids.extend(ids)
                elif "youtube.com/channel" in source or "youtube.com/user" in source or "youtube.com/c/" in source:
                    logger.info("📺 Detected channel source")
                    ids = get_channel_video_ids(source)
                    if ids:
                        logger.info(f"✅ Found {len(ids)} videos in channel")
                        video_ids.extend(ids)
                elif len(source) == 11:
                    logger.info("🎦 Detected single video ID")
                    video_ids.append(source)
                else:
                    logger.warning(f"⚠️ Unrecognized source format: {source}")
            except Exception as e:
                logger.error(f"❌ Error processing source {source}: {str(e)}")
        
        unique_ids = list(set(video_ids))
        logger.info(f"✅ Resolved {len(unique_ids)} unique video IDs")
        return unique_ids

    def _format_results(self, results: List) -> Dict:
        """Format processing results and generate report."""
        logger.info("📊 Formatting final results...")
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
            f"📈 Final report: {report['success_count']} ✅ | "
            f"{report['failure_count']} ❌ | "
            f"Success rate: {report['success_rate']}%"
        )
        return report
