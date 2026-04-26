#!/usr/bin/env python3
"""
Hybrid AI-Automated Viral Clipping Pipeline
REST + FFmpeg Edition for Arch Linux
"""
import sys
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
import traceback as tb_module
from phase1_miner import mine_candidates
from phase2_editor import identify_fillers
from phase3_extraction import create_audio_chunks, resolve_candidate_segments, extract_candidate_audio
from phase4_deepgram import transcribe_with_deepgram, merge_chunked_transcriptions
from phase5_render import render_final_video
from config import TEMP_DIR, OUTPUT_DIR
from checkpoint import save_checkpoint, load_checkpoint, checkpoint_exists


RENDER_LOCK = Lock()


def format_timestamp(seconds):
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def words_to_srt(words):
    srt_lines = []
    subtitle_idx = 1
    i = 0
    while i < len(words):
        w = words[i]
        start = w['start']
        text_parts = []
        j = i
        while j < len(words) and words[j]['start'] - words[i]['start'] < 2.5:
            text_parts.append(words[j]['word'])
            j += 1
        end = words[j - 1]['end'] if j > i else w['end']
        text = ' '.join(text_parts).strip()
        if text:
            srt_lines.append(f"{subtitle_idx}")
            srt_lines.append(f"{format_timestamp(start)} --> {format_timestamp(end)}")
            srt_lines.append(text)
            srt_lines.append("")
            subtitle_idx += 1
        i = j
    return '\n'.join(srt_lines)


def filter_words_to_clip(words, edit_result):
    """
    Filter words to only include those in final clip, adjusting timestamps.
    Removes filler words and applies trim boundaries.
    """
    if not words:
        return []
    
    indices_to_remove = set(edit_result.get('word_indices_to_remove', []))
    trim_start = edit_result.get('trim_start_index', 0)
    trim_end = edit_result.get('trim_end_index', len(words))
    
    kept = []
    for i, w in enumerate(words):
        if i < trim_start or i >= trim_end:
            continue
        if i in indices_to_remove:
            continue
        
        kept.append({
            'word': w['word'],
            'start': w['start'],
            'end': w['end'],
            'speaker': w.get('speaker', 0),
            'confidence': w.get('confidence', 1.0),
            'orig_idx': i
        })
    
    if not kept:
        return []
    
    for i, w in enumerate(kept):
        removed_before = sum(
            words[j]['end'] - words[j]['start']
            for j in range(trim_start, w['orig_idx'])
            if j in indices_to_remove
        )
        w['start'] = max(0, w['start'] - removed_before)
        w['end'] = max(0, w['end'] - removed_before)
    
    offset = kept[0]['start']
    for w in kept:
        w['start'] = max(0, w['start'] - offset)
        w['end'] = max(0, w['end'] - offset)
    
    for w in kept:
        del w['orig_idx']
    
    return kept


def truncate_words_to_video(words, video_duration, max_gap=1.0):
    """Truncate words to not exceed video duration (fallback for legacy data)"""
    if not words:
        return words
    
    if words[-1]['end'] <= video_duration + max_gap:
        return words
    
    truncated = []
    for w in words:
        if w['end'] > video_duration:
            break
        truncated.append(w)
    
    if not truncated:
        return [dict(words[0], start=0, end=video_duration)]
    
    return truncated


def extract_video_id(url_or_id):
    if 'youtube.com' in url_or_id or 'youtu.be' in url_or_id:
        if 'v=' in url_or_id:
            return url_or_id.split('v=')[1].split('&')[0]
        elif 'youtu.be/' in url_or_id:
            return url_or_id.split('youtu.be/')[1].split('?')[0]
    return url_or_id


def mine_phase1(video_url, rule_profile, rerun=False, limit=None):
    """Execute Phase 1: Candidate mining only"""
    checkpoint_data = load_checkpoint(video_url, 'phase1')
    if checkpoint_data:
        checkpoint_limit = checkpoint_data.get('candidate_limit')
        can_use_checkpoint = True

        if limit is None and checkpoint_limit is not None:
            can_use_checkpoint = False
        elif limit is not None and checkpoint_limit is not None and checkpoint_limit < limit:
            can_use_checkpoint = False

        if can_use_checkpoint:
            print(f"⚡ Resuming from Phase 1 checkpoint")
            candidates = checkpoint_data['candidates']
            if limit is not None:
                candidates = candidates[:limit]
            return candidates, checkpoint_data['transcript'], checkpoint_data['campaign_config'], checkpoint_data.get('full_video_words')

        print("🔄 Existing Phase 1 checkpoint is incompatible with requested limit, regenerating...")
    
    print(f"⛏️  Mining candidates from: {video_url}")
    if rule_profile:
        print(f"📋 Rules profile: {rule_profile}")
    
    video_id = extract_video_id(video_url)
    full_video_words = None
    full_video_heatmap = None
    
    transcript = None
    try:
        from phase1_miner import fetch_transcript
        transcript = fetch_transcript(video_id)
    except:
        pass
    
    try:
        from utils.yt_heatmap import fetch_normalized_heatmap
        print("📊 Fetching YouTube heatmap data...")
        full_video_heatmap = fetch_normalized_heatmap(video_id)
        if full_video_heatmap:
            print(f"✓ Loaded {len(full_video_heatmap)} heatmap markers")
    except Exception as e:
        print(f"⚠️  Heatmap fetch failed: {e}")
    
    if transcript is None:
        print("📡 YouTube transcript unavailable, using Deepgram for full video")
        from phase3_extraction import download_video, create_audio_chunks
        from phase4_deepgram import transcribe_with_deepgram, merge_chunked_transcriptions
        from concurrent.futures import ThreadPoolExecutor
        import subprocess
        
        video_path = f"temp/{video_id}.mp4"
        audio_path = video_path.replace('.mp4', '_full.mp3')
        
        subprocess.run([
            'ffmpeg', '-i', video_path, '-vn', '-acodec', 'libmp3lame',
            '-q:a', '2', audio_path, '-y'
        ], check=True, capture_output=True)
        
        result = subprocess.run(
            ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
             '-of', 'default=noprint_wrappers=1:nokey=1', audio_path],
            capture_output=True, text=True, timeout=30
        )
        audio_duration = float(result.stdout.strip()) if result.stdout.strip() else 0
        
        if audio_duration > 3600:
            print(f"🎙️  Long audio ({audio_duration/60:.0f} min), chunking for transcription...")
            chunks = create_audio_chunks(audio_path)
            
            def transcribe_chunk(args):
                idx, chunk = args
                return idx, transcribe_with_deepgram(chunk['path'], chunk_info={'start_offset': chunk['start_offset']})
            
            with ThreadPoolExecutor(max_workers=min(len(chunks), 10)) as executor:
                futures = list(executor.map(transcribe_chunk, enumerate(chunks)))
            
            chunk_results = [None] * len(chunks)
            for idx, result in futures:
                chunk_results[idx] = result
            
            deepgram_result = merge_chunked_transcriptions([r for r in chunk_results if r])
        else:
            deepgram_result = transcribe_with_deepgram(audio_path)
        
        full_video_words = deepgram_result['words']
        print(f"✓ Transcribed {len(full_video_words)} words via Deepgram")
    
    candidates, transcript, campaign_config = mine_candidates(
        video_id,
        rule_profile,
        full_video_words=full_video_words,
        max_candidates=limit,
        transcript=transcript,
        full_video_heatmap=full_video_heatmap,
    )
    
    save_checkpoint(video_url, 'phase1', {
        'candidates': candidates,
        'transcript': transcript,
        'campaign_config': campaign_config,
        'full_video_words': full_video_words,
        'full_video_heatmap': full_video_heatmap,
        'candidate_limit': limit,
    })
    
    print(f"✓ Found {len(candidates)} highlight reels")
    return candidates, transcript, campaign_config, full_video_words


def process_candidate(video_url, rule_profile, candidate, full_video_words=None, video_output_dir=None, rerun=False, transcript=None, cookies_file=None):
    """Process a single candidate through phases 2-6"""
    video_id = extract_video_id(video_url)
    
    cid = candidate['candidate_id']
    virality = candidate.get('virality', {})
    viral_title = candidate.get('viral_title', 'Untitled')
    source_segments = []
    
    print(f"📹 Processing Candidate {cid}: {candidate['hook_summary']}")
    print(f"   Duration: {candidate['duration']:.1f}s | Virality: {virality.get('total_score', 0)}/100")
    
    phase1_data = None
    if transcript is None:
        phase1_data = load_checkpoint(video_url, 'phase1')
        if not phase1_data:
            _, transcript, _, mined_full_video_words = mine_phase1(video_url, rule_profile)
            if full_video_words is None:
                full_video_words = mined_full_video_words
        else:
            transcript = phase1_data['transcript']
            if full_video_words is None:
                full_video_words = phase1_data.get('full_video_words')
    elif full_video_words is None:
        phase1_data = load_checkpoint(video_url, 'phase1')
        if phase1_data:
            full_video_words = phase1_data.get('full_video_words')
    
    phase2_checkpoint = load_checkpoint(video_url, f'phase2_c{cid}')
    if phase2_checkpoint:
        print(f"⚡ Resuming from Phase 2 checkpoint")
        video_path = phase2_checkpoint['video_path']
        audio_path = phase2_checkpoint['audio_path']
        source_segments = phase2_checkpoint.get('source_segments', [])

        if not source_segments:
            source_segments = resolve_candidate_segments(candidate, transcript)

        if not os.path.exists(audio_path):
            audio_path = extract_candidate_audio(video_path, source_segments, cid)

        save_checkpoint(video_url, f'phase2_c{cid}', {
            'video_path': video_path,
            'audio_path': audio_path,
            'source_segments': source_segments,
        })
    else:
        print(f"📥 Preparing candidate segments and targeted audio...")
        local_video = f"{TEMP_DIR}/{video_id}.mp4"
        if os.path.exists(local_video):
            video_path = local_video
            print(f"✓ Using existing video: {video_path}")
        else:
            from phase3_extraction import download_video
            print(f"📥 Downloading video...")
            video_path = download_video(video_id, cookies_file=cookies_file)
            print(f"✓ Downloaded: {video_path}")

        source_segments = resolve_candidate_segments(candidate, transcript)
        if not source_segments:
            raise ValueError(f"No source segments found for candidate {cid}")

        audio_path = extract_candidate_audio(video_path, source_segments, cid)

        save_checkpoint(video_url, f'phase2_c{cid}', {
            'video_path': video_path,
            'audio_path': audio_path,
            'source_segments': source_segments,
        })
        print(f"✓ Candidate segments resolved ({len(source_segments)} source span(s))")
    
    phase3_checkpoint = load_checkpoint(video_url, f'phase3_c{cid}')
    if phase3_checkpoint:
        print(f"⚡ Resuming from Phase 3 checkpoint")
        words = phase3_checkpoint['words']
        print(f"✓ Loaded {len(words)} transcribed words")
    else:
        if full_video_words:
            print(f"✂️  Extracting clip words from full video transcript...")
            from utils.transcript_utils import extract_clip_words_from_segments
            words = extract_clip_words_from_segments(full_video_words, source_segments)
            print(f"✓ Extracted {len(words)} words from full transcript")
        else:
            audio_duration = 0
            try:
                result = subprocess.run(
                    ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                     '-of', 'default=noprint_wrappers=1:nokey=1', audio_path],
                    capture_output=True, text=True, timeout=30
                )
                audio_duration = float(result.stdout.strip()) if result.stdout.strip() else 0
            except Exception as e:
                print(f"Warning: Could not determine audio duration: {e}")
            
            LONG_AUDIO_THRESHOLD = 60 * 60
            
            if audio_duration > LONG_AUDIO_THRESHOLD:
                print(f"🎙️  Long audio ({audio_duration/60:.0f} min), CONCURRENT transcription...")
                chunks = create_audio_chunks(audio_path)
                
                def transcribe_chunk(args):
                    idx, chunk = args
                    return idx, transcribe_with_deepgram(
                        chunk['path'],
                        chunk_info={'start_offset': chunk['start_offset']}
                    )
                
                with ThreadPoolExecutor(max_workers=min(len(chunks), 10)) as executor:
                    futures = list(executor.map(transcribe_chunk, enumerate(chunks)))
                
                chunk_results = [None] * len(chunks)
                for idx, result in futures:
                    chunk_results[idx] = result
                
                chunk_results = [r for r in chunk_results if r is not None]
                deepgram_result = merge_chunked_transcriptions(chunk_results)
                print(f"  ✓ Merged {len(deepgram_result['words'])} words from {len(chunks)} chunks")
            else:
                print(f"🎙️  Deepgram transcription...")
                deepgram_result = transcribe_with_deepgram(audio_path)
                print(f"✓ Transcribed {len(deepgram_result['words'])} words")
            
            words = deepgram_result['words']
        
        save_checkpoint(video_url, f'phase3_c{cid}', {'words': words})
    
    phase4_checkpoint = load_checkpoint(video_url, f'phase4_c{cid}')
    if phase4_checkpoint:
        print(f"⚡ Resuming from Phase 4 checkpoint")
        edit_result = phase4_checkpoint
        if 'word_indices_to_remove' not in edit_result:
            edit_result = {
                'word_indices_to_remove': phase4_checkpoint.get('filler_indices', []),
                'trim_start_index': 0,
                'trim_end_index': len(words)
            }
        print(f"✓ Loaded {len(edit_result['word_indices_to_remove'])} words for removal")
    else:
        print(f"✂️  Identifying filler words...")
        edit_result = identify_fillers(words, cid, rule_profile)
        save_checkpoint(video_url, f'phase4_c{cid}', edit_result)
        print(f"✓ Targeting {len(edit_result['word_indices_to_remove'])} words for removal, trim: [{edit_result['trim_start_index']}:{edit_result['trim_end_index']}]")
    
    phase5_checkpoint = load_checkpoint(video_url, f'phase5_c{cid}')
    if phase5_checkpoint:
        print(f"⚡ Resuming from Phase 5 checkpoint")
        output_path = phase5_checkpoint['output_path']
        print(f"✓ Loaded rendered video: {output_path}")
    else:
        print(f"🎨 Rendering final 16:9 video...")
        with RENDER_LOCK:
            output_path = render_final_video(
                video_path,
                words,
                edit_result,
                cid,
                video_id,
                viral_title,
                video_output_dir,
                source_segments=source_segments,
                unique_suffix=0,
                edit_techniques=candidate.get('edit_techniques'),
            )
        
        import json
        
        clip_words = filter_words_to_clip(words, edit_result)
        metadata = {
            'candidate_id': cid,
            'hook': candidate['hook_summary'],
            'duration': candidate['duration'],
            'virality': virality,
            'viral_title': viral_title,
            'heatmap': candidate.get('heatmap', {}),
            'edit_techniques': candidate.get('edit_techniques', {}),
            'words': words,
            'clip_words': clip_words,
            'filler_indices': edit_result['word_indices_to_remove'],
            'trim_start_index': edit_result['trim_start_index'],
            'trim_end_index': edit_result['trim_end_index']
        }
        metadata_path = output_path.replace('.mp4', '_metadata.json')
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f, indent=2)
        
        words_path = output_path.replace('.mp4', '_words.json')
        with open(words_path, 'w') as f:
            json.dump({'words': clip_words}, f, indent=2)
        
        srt_path = output_path.replace('.mp4', '.srt')
        with open(srt_path, 'w') as f:
            f.write(words_to_srt(clip_words))
        
        save_checkpoint(video_url, f'phase5_c{cid}', {
            'output_path': output_path,
            'metadata_path': metadata_path
        })
        
        print(f"✓ Rendered: {output_path}")
        print(f"✓ Exported metadata: {metadata_path}")
    
    clip_transcript = ' '.join([
        transcript[seg]['text'] if isinstance(seg, int) 
        else seg.get('text', '') if isinstance(seg, dict)
        else ''
        for seg in candidate['segments']
    ])
    
    return {
        'candidate_id': cid,
        'hook': candidate['hook_summary'],
        'duration': candidate['duration'],
        'virality_score': virality.get('total_score', 0),
        'virality': virality,
        'viral_title': viral_title,
        'transcript': clip_transcript,
        'output': output_path
    }


def run_full_pipeline(video_url, rule_profile, rerun=False, clean=False, limit=None, cookies_file=None):
    """Execute the full pipeline"""
    import pandas as pd
    from datetime import datetime
    from yt_dlp import YoutubeDL
    import re
    import shutil
    
    video_id = extract_video_id(video_url)
    
    if clean:
        print("🧹 Clean mode: reprocessing from scratch + clearing output...")
        from checkpoint import clear_checkpoints
        clear_checkpoints(video_url)
        
        # Clear output directory for this video
        with YoutubeDL({'quiet': True}) as ydl:
            info = ydl.extract_info(video_url, download=False)
            video_title = re.sub(r'[^\w\s-]', '', info['title']).strip().replace(' ', '-').lower()[:50]
        video_output_dir = os.path.join(OUTPUT_DIR, video_title)
        if os.path.exists(video_output_dir):
            shutil.rmtree(video_output_dir)
            print(f"   Removed output directory: {video_output_dir}")
    elif rerun:
        print("🔄 Rerun mode: reprocessing from scratch, keeping video/transcript...")
        from checkpoint import clear_checkpoints
        clear_checkpoints(video_url)
    
    # Get video title
    ydl_opts = {'quiet': True}
    if cookies_file and os.path.exists(cookies_file):
        ydl_opts['cookiefile'] = cookies_file
        print(f"Using cookies from: {cookies_file}")
    
    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(video_url, download=False)
        video_title = re.sub(r'[^\w\s-]', '', info['title']).strip().replace(' ', '-').lower()[:50]
    
    # Create output directory for this video
    video_output_dir = os.path.join(OUTPUT_DIR, video_title)
    os.makedirs(video_output_dir, exist_ok=True)
    
    candidates, transcript, campaign_config, full_video_words = mine_phase1(
        video_url,
        rule_profile,
        rerun,
        limit=limit,
    )
    
    # Apply limit if specified
    if limit:
        candidates = candidates[:limit]
        print(f"📌 Limit: processing only {limit} candidate(s)")
    
    results = []
    failed_candidates = []
    worker_count = min(2, max(1, len(candidates)))
    if worker_count > 1:
        print(f"⚙️  Parallel candidate processing enabled (workers={worker_count})")

    for idx, candidate in enumerate(candidates, 1):
        candidate['_seq'] = idx
        candidate['candidate_id'] = idx  # Make globally unique (was resetting per chunk)

    def _run_candidate(candidate):
        return process_candidate(
            video_url,
            rule_profile,
            candidate,
            full_video_words=full_video_words,
            video_output_dir=video_output_dir,
            rerun=rerun,
            transcript=transcript,
            cookies_file=cookies_file,
        )

    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = {executor.submit(_run_candidate, candidate): candidate for candidate in candidates}
        for fut in futures:
            candidate = futures[fut]
            try:
                results.append(fut.result())
            except Exception as e:
                cid = candidate.get('candidate_id', 'unknown')
                hook = candidate.get('hook_summary', 'unknown')
                traceback_str = tb_module.format_exc()
                print(f"❌ Candidate {cid} failed: {e}")
                print(f"   Hook: {hook[:60]}...")
                print(f"   Traceback:\n{tb_module.format_exc()}")
                failed_candidates.append({
                    'candidate_id': cid,
                    'hook': hook,
                    'error': str(e),
                    'traceback': traceback_str,
                })

    results.sort(key=lambda x: x['candidate_id'])
    
    # Append to global CSV
    csv_path = os.path.join(OUTPUT_DIR, "all_clips.csv")
    new_rows = [{
        'timestamp': datetime.now().isoformat(),
        'video_id': video_id,
        'video_url': video_url,
        'clip_id': r['candidate_id'],
        'clip_file': r['output'],
        'viral_title': r['viral_title'],
        'hook': r['hook'],
        'duration_seconds': r['duration'],
        'virality_score': r['virality_score'],
        'clip_quality_score': r['virality'].get('clip_quality_score', 0),
        'value_score': r['virality'].get('value_score', 0),
        'hook_score': r['virality'].get('hook_score', 0),
        'engagement_score': r['virality'].get('engagement_score', 0),
        'shareability_score': r['virality'].get('shareability_score', 0)
    } for r in results]
    
    if os.path.exists(csv_path):
        existing = pd.read_csv(csv_path)
        df = pd.concat([existing, pd.DataFrame(new_rows)], ignore_index=True)
    else:
        df = pd.DataFrame(new_rows)
    df.to_csv(csv_path, index=False)
    
    print("=" * 60)
    print("Pipeline Complete!")
    print("=" * 60)
    print(f"Exported {len(new_rows)} clips to: {csv_path}")
    for r in results:
        print(f"  {os.path.basename(r['output'])}: {r['viral_title'][:60]}...")
    
    if failed_candidates:
        print("=" * 60)
        print("❌ Failed Candidates")
        print("=" * 60)
        for fc in failed_candidates:
            print(f"  [cid{fc['candidate_id']}] {fc['hook'][:50]}...")
            print(f"     Error: {fc['error']}")
        print(f"Total failed: {len(failed_candidates)}/{len(candidates)}")
    
    return results


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='AI Shorts Generator Pipeline')
    parser.add_argument('video_url', help='YouTube video URL')
    parser.add_argument('--rules', dest='rule_profile', help='Rules profile name (e.g., abulayha)', default=None)
    parser.add_argument('--rerun', action='store_true', help='Skip video download, reprocess from existing temp file')
    parser.add_argument('--clean', action='store_true', help='Clear checkpoints and output for this video before processing')
    parser.add_argument('-l', '--limit', type=int, help='Limit number of final clips to render', default=None)
    parser.add_argument('--cookies', dest='cookies_file', help='YouTube cookies file (Netscape format)', default=None)
    
    args = parser.parse_args()
    
    os.makedirs(TEMP_DIR, exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs("rules", exist_ok=True)
    
    if args.rule_profile:
        rules_path = os.path.join("rules", args.rule_profile, "rules.json")
        if not os.path.exists(rules_path):
            print(f"❌ Error: Rules profile '{args.rule_profile}' not found at {rules_path}")
            sys.exit(1)
    
    try:
        run_full_pipeline(args.video_url, args.rule_profile, args.rerun, args.clean, args.limit, args.cookies_file)
    except Exception as e:
        import traceback
        print(f"❌ Pipeline failed: {e}")
        traceback.print_exc()
        sys.exit(1)
