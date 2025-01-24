import os
import logging
import subprocess
from pathlib import Path
from typing import List, Dict, Optional

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def cut_video_into_clips(video_path: str, clips: List[Dict], output_dir: str) -> Optional[List[str]]:
    """Split video into clips with detailed progress tracking"""
    try:
        logger.info("✂️ Starting video clipping process")
        logger.debug(f"📁 Source video: {video_path}")
        logger.debug(f"🎞️ Clips to create: {len(clips)}")
        
        output_dir = Path(output_dir)
        logger.info(f"📂 Creating output directory: {output_dir}")
        output_dir.mkdir(parents=True, exist_ok=True)
        
        clip_paths = []
        for idx, clip in enumerate(clips, 1):
            try:
                logger.info(f"🔪 Processing clip {idx}/{len(clips)}")
                output_path = output_dir / f"clip_{idx}.mp4"
                start = clip['start']
                duration = clip['end'] - start
                logger.debug(f"⏱️ Clip timing: {start}s - {clip['end']}s ({duration}s)")

                command = [
                    'ffmpeg',
                    '-ss', str(start),
                    '-i', video_path,
                    '-t', str(duration),
                    '-c:v', 'copy',
                    '-c:a', 'copy',
                    '-y',
                    '-hide_banner',
                    '-loglevel', 'error',
                    str(output_path)
                ]
                
                logger.debug(f"🔧 Executing: {' '.join(command)}")
                result = subprocess.run(
                    command,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True
                )

                if result.returncode != 0:
                    logger.error(f"❌ Clip {idx} creation failed")
                    logger.debug(f"🧠 FFmpeg error: {result.stderr[:500]}...")
                    continue
                    
                if output_path.exists():
                    size_mb = output_path.stat().st_size/1024/1024
                    logger.info(f"✅ Created clip: {output_path.name} ({size_mb:.2f} MB)")
                    clip_paths.append(str(output_path))
                else:
                    logger.error(f"❌ Missing output file: {output_path}")

            except Exception as e:
                logger.error(f"⚠️ Error processing clip {idx}: {str(e)}")
                continue

        if clip_paths:
            logger.info(f"🎉 Successfully created {len(clip_paths)}/{len(clips)} clips")
            return clip_paths
            
        logger.error("❌ Failed to create any clips")
        return None

    except Exception as e:
        logger.error(f"🔥 Critical clipping error: {str(e)}", exc_info=True)
        return None