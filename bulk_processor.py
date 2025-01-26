import logging
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
        progress_callback: Optional[Callable[[str, int, float], None]] = None
    ):
        self.progress_callback = progress_callback

    def _process_single_video(
        self, 
        video_id: str, 
        output_dir: str, 
        lang: str,
        total_videos: int,
        index: int
    ) -> Optional[Dict]:
        try:
            video_dir = Path(output_dir) / video_id
            video_dir.mkdir(parents=True, exist_ok=True)

            def handle_progress(stream_type: str, progress: float):
                if self.progress_callback:
                    self.progress_callback(stream_type, index, progress)

            video_path = download_video(video_id, handle_progress)
            if not video_path or not Path(video_path).exists():
                raise ValueError("Download failed")

            if self.progress_callback:
                self.progress_callback("transcript", index, 0)
            
            transcript = fetch_transcript(video_id, lang)
            
            if self.progress_callback:
                self.progress_callback("transcript", index, 100)
                self.progress_callback("heatmap", index, 0)
            
            clips = process_video(video_id)
            
            if self.progress_callback:
                self.progress_callback("heatmap", index, 100)
                self.progress_callback("clips", index, 0)
            
            valid_clips = [c for c in clips if c['end'] > c['start']][:10]
            if not valid_clips:
                raise ValueError("No valid clips generated")

            clip_dir = video_dir / "clips"
            clip_paths = cut_video_into_clips(video_path, valid_clips, str(clip_dir))
            
            if self.progress_callback:
                self.progress_callback("clips", index, 100)

            processed_clips = extract_clip_transcripts(json.loads(transcript), valid_clips)
            transcript_path = video_dir / "clip_transcripts.json"
            save_clip_transcripts(processed_clips, str(transcript_path))

            return {
                'video_id': video_id,
                'status': 'success',
                'clips': clip_paths,
                'clip_dir': str(clip_dir),
                'transcript_path': str(transcript_path)
            }

        except Exception as e:
            logger.error(f"Processing failed: {str(e)}")
            return {
                'video_id': video_id,
                'status': 'failed',
                'error': str(e)
            }

    def process_sources(self, sources: List[str], lang: str, output_dir: str) -> Dict:
        video_ids = self._resolve_sources(sources)
        total = len(video_ids)
        results = []
        
        for idx, vid in enumerate(video_ids):
            result = self._process_single_video(vid, output_dir, lang, total, idx)
            results.append(result)
            
        return self._format_results(results)

    def _resolve_sources(self, sources: List[str]) -> List[str]:
        video_ids = []
        for source in sources:
            try:
                if "youtube.com/playlist" in source or "list=" in source:
                    ids = get_playlist_video_ids(source)
                    if ids:
                        video_ids.extend(ids)
                elif "youtube.com/channel" in source or "youtube.com/user" in source or "youtube.com/c/" in source:
                    ids = get_channel_video_ids(source)
                    if ids:
                        video_ids.extend(ids)
                elif len(source) == 11:
                    video_ids.append(source)
                else:
                    logger.warning(f"Unrecognized source: {source}")
            except Exception as e:
                logger.error(f"Error processing {source}: {str(e)}")
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
            
        logger.info(
            f"Final report: {report['success_count']} ✅ | "
            f"{report['failure_count']} ❌ | "
            f"Success rate: {report['success_rate']}%"
        )
        return report
