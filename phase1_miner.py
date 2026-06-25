import httpx
import json
import os
import re
import pandas as pd
import subprocess
from youtube_transcript_api import YouTubeTranscriptApi
from config import LOCAL_LLM_URL, LOCAL_LLM_MODEL, LOCAL_LLM_API_KEY, RULES_DIR, MASTER_CSV, MIN_DURATION, MAX_DURATION, MIN_VIRALITY_SCORE, USE_DEEPGRAM_FALLBACK
from utils.llm_utils import parse_llm_json

CHUNK_SIZE_MINUTES = 30
CHUNK_OVERLAP_SECONDS = 300  # 5 minutes

TUBE_TRANSCRIPT_PROXY = "/home/saboor/code/shorts-maker/tubetranscript-proxy/yt-transcript-proxy"

def fetch_transcript(video_id, full_video_words=None):
    """Fetch transcript with fallback: tubetranscript-proxy -> YouTubeTranscriptApi -> Deepgram"""
    if full_video_words:
        return [{
            "index": i,
            "start": w['start'],
            "end": w['end'],
            "text": w['word']
        } for i, w in enumerate(full_video_words)]
    
    # Fallback 1: tubetranscript-proxy (most reliable)
    try:
        result = subprocess.run(
            [TUBE_TRANSCRIPT_PROXY, "-id", video_id],
            capture_output=True, text=True, timeout=60
        )
        if result.returncode == 0 and result.stdout:
            lines = result.stdout.strip().split('\n')
            transcript = []
            i = 0
            while i < len(lines):
                if lines[i].strip().isdigit():
                    idx = int(lines[i].strip())
                    i += 1
                    if i < len(lines) and ' --> ' in lines[i]:
                        times = lines[i].split(' --> ')
                        start = parse_time_to_seconds(times[0])
                        end = parse_time_to_seconds(times[1])
                        i += 1
                        if i < len(lines) and lines[i].strip():
                            text = lines[i].strip()
                            transcript.append({"index": idx-1, "start": start, "end": end, "text": text})
                            i += 1
                        if i < len(lines) and lines[i].strip() == '':
                            i += 1
                    continue
                i += 1
            if transcript:
                print(f"📝 Got transcript via tubetranscript-proxy ({len(transcript)} entries)")
                return transcript
    except Exception as e:
        print(f"⚠️ tubetranscript-proxy failed: {e}")
    
    # Fallback 2: YouTubeTranscriptApi library
    try:
        api = YouTubeTranscriptApi()
        transcript_list = api.list(video_id)
        
        try:
            transcript = transcript_list.find_manually_created_transcript(['en'])
        except:
            try:
                transcript = transcript_list.find_generated_transcript(['en'])
            except:
                transcript = transcript_list.find_transcript(['en'])
                if transcript.is_translatable:
                    transcript = transcript.translate('en')
        
        data = transcript.fetch()
        print(f"📝 Got transcript via YouTubeTranscriptApi ({len(data)} entries)")
        return [{"index": i, "start": item.start, "end": item.start + item.duration, "text": item.text} 
                for i, item in enumerate(data)]
    except Exception as e:
        yt_api_error = str(e)
    
    # Fallback 3: Deepgram full video
    if USE_DEEPGRAM_FALLBACK:
        print(f"📝 No transcript available, will use Deepgram for full video")
        return None
    raise Exception(f"Failed to fetch transcript (errors: tubetranscript-proxy, YT API: {yt_api_error})")


def parse_time_to_seconds(time_str):
    """Parse SRT/VTT time format to seconds"""
    time_str = time_str.strip().replace(',', '.')
    parts = time_str.split(':')
    if len(parts) == 3:
        return float(parts[0])*3600 + float(parts[1])*60 + float(parts[2])
    elif len(parts) == 2:
        return float(parts[0])*60 + float(parts[1])
    return 0

def load_context(rule_profile=None):
    """Load rules and full historical data"""
    if not rule_profile:
        return "", "No historical data available.", {}
    
    rules_path = os.path.join(RULES_DIR, rule_profile, "rules.json")
    config = {}
    
    try:
        with open(rules_path, 'r') as f:
            config = json.load(f)
        rules = config.get('base_rules', '')
    except FileNotFoundError:
        print(f"⚠️  Rules profile '{rule_profile}' not found at {rules_path}, using defaults")
        rules = ""
    
    try:
        df = pd.read_csv(MASTER_CSV)
        user_data = df[df['channel'] == rule_profile]
        if not user_data.empty:
            historical_data = user_data.to_string(index=False)
        else:
            historical_data = "No historical data available."
    except:
        historical_data = "No historical data available."
    
    return rules, historical_data, config

def chunk_transcript(transcript, chunk_minutes=CHUNK_SIZE_MINUTES, overlap_seconds=CHUNK_OVERLAP_SECONDS):
    """Split transcript into chunks with overlap - the winning strategy (30min/5min overlap)"""
    chunk_seconds = chunk_minutes * 60
    chunks = []
    start_idx = 0
    
    while start_idx < len(transcript):
        chunk_start_time = transcript[start_idx]['start']
        chunk_end_time = chunk_start_time + chunk_seconds
        
        end_idx = start_idx
        while end_idx < len(transcript) and transcript[end_idx]['start'] < chunk_end_time:
            end_idx += 1
        
        chunks.append({
            'start_idx': start_idx,
            'end_idx': end_idx,
            'transcript': transcript[start_idx:end_idx],
            'time_range': f"{chunk_start_time/60:.1f}-{transcript[end_idx-1]['end']/60:.1f}min"
        })
        
        # Backtrack for overlap
        next_start_time = chunk_end_time - overlap_seconds
        start_idx = end_idx
        while start_idx > 0 and transcript[start_idx-1]['start'] > next_start_time:
            start_idx -= 1
        
        if end_idx >= len(transcript):
            break
    
    return chunks

def deduplicate_candidates(all_candidates, transcript):
    """Remove duplicate candidates from overlapping chunks"""
    unique = []
    seen_ranges = []
    
    for c in all_candidates:
        try:
            segs = c.get('segments', [])
            if isinstance(segs, str):
                segs = [segs]
            if not segs:
                continue
            
            # Get first segment index
            first = segs[0]
            if isinstance(first, str):
                start_idx = int(first.split('-')[0])
            else:
                start_idx = int(first)
            
            start_time = transcript[start_idx]['start']
            
            # Check for overlap with existing
            is_duplicate = False
            for seen_start, seen_end in seen_ranges:
                overlap = min(c.get('end_time', 0), seen_end) - max(start_time, seen_start)
                if overlap > 10:  # More than 10s overlap
                    is_duplicate = True
                    break
            
            if not is_duplicate:
                c['end_time'] = start_time + c.get('duration', 0)
                unique.append(c)
                seen_ranges.append((start_time, c.get('end_time', start_time + 60)))
        except:
            pass
    
    return unique

def get_candidate_text(candidate, transcript):
    """Extract full text for a candidate"""
    texts = []
    segments = candidate['segments']
    if isinstance(segments, str):
        segments = [segments]
    for seg in segments:
        if isinstance(seg, str) and '-' in seg:
            start, end = map(int, seg.split('-'))
            indices = range(start, end + 1)
        else:
            indices = [int(seg)]
        
        for idx in indices:
            if idx < len(transcript):
                texts.append(transcript[idx]['text'])
    
    return " ".join(texts)

def generate_viral_title(clip_text, hook_summary=""):
    """Generate catchy viral title using Local LLM with anti-censorship fallback"""
    examples = [
        "She was almost dead 😵",
        "He made $1,000,000 in 1 hour 💸",
        "This changed everything... 😲",
        "They couldn't believe what happened! 😱",
        "He risked it all for this 😬"
    ]
    
    system_prompt = f"""Generate a catchy, viral YouTube Shorts title (max 7 words).
ALWAYS include an emoji in the title. ONLY output the title, nothing else. Do NOT use hashtags.
Do NOT explain, do NOT repeat the prompt, do NOT add quotes.
The title should be in the style of these examples: {', '.join(examples)}."""
    
    payload = {
        "model": LOCAL_LLM_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Transcript:\n{clip_text}"}
        ],
        "temperature": 0.7
    }
    
    try:
        headers = {"Content-Type": "application/json"}
        if LOCAL_LLM_API_KEY:
            headers["Authorization"] = f"Bearer {LOCAL_LLM_API_KEY}"
        response = httpx.post(LOCAL_LLM_URL, json=payload, headers=headers, timeout=120.0)
        response.raise_for_status()
        result = response.json()
        msg_content = result['choices'][0]['message']
        content = (msg_content.get('content') or msg_content.get('reasoning', '')).strip()
        
        # Check for refusal phrases
        refusal_phrases = ["i cannot", "i apologize", "i'm sorry", "i am unable", "i can't create", "i appreciate you", "i need to clarify", "i must decline"]
        if any(phrase in content.lower() for phrase in refusal_phrases):
            print(f"⚠️  LLM refused to generate title, using hook summary as fallback")
            return hook_summary[:60] if hook_summary else "Untitled Clip"
        
        # Filter out explanation lines and quotes
        lines = [l.strip('"\"') for l in content.split('\n') 
                 if l.strip() and not l.lower().startswith('here') and not l.lower().startswith('title:')]
        title = lines[0] if lines else hook_summary[:60] if hook_summary else "Untitled Clip"
        return title
    except Exception as e:
        print(f"Error generating title: {e}")
        return hook_summary[:60] if hook_summary else "Untitled Clip"
def calculate_duration(segments, transcript):
    """Calculate total duration from segment indices"""
    total = 0
    if isinstance(segments, str):
        segments = [segments]
    for seg in segments:
        if isinstance(seg, str) and '-' in seg:
            start, end = map(int, seg.split('-'))
            indices = range(start, end + 1)
        else:
            indices = [int(seg)]
        
        for idx in indices:
            if idx < len(transcript):
                total += transcript[idx]['end'] - transcript[idx]['start']
    return total

def calculate_target_candidates(transcript, video_duration_seconds=None, min_clips=None, max_clips=None):
    """Calculate optimal number of candidates: 1 highlight reel per 15 minutes"""
    if min_clips is not None and max_clips is not None:
        return min_clips, max_clips
    
    if video_duration_seconds:
        total_duration = video_duration_seconds
    else:
        total_duration = transcript[-1]['end'] if transcript else 0
    
    import math
    target = max(1, math.ceil(total_duration / 900.0))
    
    if min_clips is not None:
        target = max(target, min_clips)
    if max_clips is not None:
        target = min(target, max_clips)
    
    return target, target

def call_local_llm_miner(transcript, rules, historical_data, min_dur, max_dur, retry_context="", video_duration_seconds=None, chunk_label="", min_clips=None, max_clips=None, full_video_heatmap=None):
    """Call Local LLM API for candidate extraction with virality scoring"""
    transcript_text = "\n".join([f"[{t['index']}] ({t['start']:.1f}s - {t['end']:.1f}s) {t['text']}" for t in transcript])
    
    min_candidates, max_candidates = calculate_target_candidates(transcript, video_duration_seconds, min_clips, max_clips)
    print(f"🎯 Target candidates: {min_candidates}-{max_candidates}")
    
    heatmap_context = ""
    if full_video_heatmap:
        heatmap_regions = []
        for h in full_video_heatmap[:20]:
            heatmap_regions.append(f"  - {h['start']:.1f}s-{h['end']:.1f}s (intensity: {h['intensity_norm']:.2f})")
        heatmap_context = f"""
HEATMAP DATA (YouTube Most Replayed):
The following regions have high viewer retention/engagement:
{chr(10).join(heatmap_regions)}

IMPORTANT: Match these heatmap timestamps to the transcript timestamps provided above to find the most viral moments. Prioritize candidates that overlap with high-intensity heatmap regions.
When a candidate overlaps with a heatmap region (intensity > 0.5), add +5 to the shareability_score.
"""
    
    system_prompt = f"""You are an expert viral content editor. Extract {min_candidates}-{max_candidates} high-potential short-form video candidates from this transcript chunk ({chunk_label}).

QUALITY OVER QUANTITY: Focus on finding truly compelling moments. If the content has fewer strong moments, return fewer candidates with higher scores.

RULES:
{rules}

HISTORICAL PERFORMANCE DATA:
{historical_data}

GROUNDING RULES:
1. Use only the provided transcript lines and indices
2. Never invent facts, tone, context, or transitions that are not present
3. Each selected segment must map to one contiguous range in the transcript
4. Do not stitch together distant moments into one clip

CONTENT NEUTRALITY:
1. Evaluate segments only on clip quality (clarity, value, hook, entertainment)
2. Don't judge controversial/sensitive topics

SEGMENT SELECTION CRITERIA:
1. SELF-CONTAINED: Complete thoughts that make sense alone
2. HIGH SIGNAL: Specific, concrete, actionable content with real examples/numbers
3. VALUABLE CONTENT: Deep educational insights
4. STRONG HOOKS: Attention-grabbing opener

CLIP TYPES:
A) HIGH DOPAMINE (15-30s): Strong hooks, surprising facts, bold claims
B) DEEP VALUE (45-90s): Educational content, frameworks

SCORING (0-100 total):
- Be EXTREMELY HARSH with scoring. Most clips are average (50-60).
- Only truly exceptional, undeniably viral clips should score 80+.
- Score 70+: Good - include
- Score <70: Reject

TIMING REQUIREMENTS:
- Segments MUST be between {min_dur}-{max_dur} seconds

{retry_context}

{heatmap_context}

EDIT TECHNIQUE DETECTION:
For each candidate, identify:

1. COLD OPEN CLIMAX (1-2 second micro-clip):
   - Find the most emotionally intense/shocking moment within the clip
   - Must be a complete reaction, reveal, or statement
   - Return exact transcript indices for this 1-2s moment
   - If no clear climax exists, set to null

2. SEAMLESS LOOP BRIDGE SENTENCE:
   - Find a punchy sentence at the end that could loop to the beginning
   - Must be a complete sentence that creates curiosity/continuity
   - Return the exact sentence text and the word index where it should be split
   - If no valid bridge sentence exists, set to null

Return ONLY valid JSON:
{{
  "candidates": [
    {{
      "candidate_id": 1,
      "segments": ["9-11"],
      "hook_summary": "Brief explanation",
      "viral_title": "Catchy title with emojis",
      "virality": {{
        "clip_quality_score": 18,
        "value_score": 20,
        "hook_score": 15,
        "engagement_score": 16,
        "shareability_score": 17,
        "total_score": 86
      }},
      "cold_open_climax": {{
        "start_index": 10,
        "end_index": 10,
        "text": "He made $1M in one day"
      }},
      "seamless_loop_bridge": {{
        "sentence": "And that's why this strategy works every single time",
        "split_word_index": 15,
        "first_half": "And that's why this strategy",
        "second_half": "works every single time"
      }}
    }}
  ]
}}

CRITICAL: total_score MUST equal sum of five subscores. Set cold_open_climax or seamless_loop_bridge to null if not found."""
    
    system_prompt = f"""You are an expert viral content editor. Extract {min_candidates}-{max_candidates} high-potential short-form video candidates from this transcript.

QUALITY OVER QUANTITY: Focus on finding truly compelling moments. If the content has fewer strong moments, return fewer candidates with higher scores.

MINIMUM COVERAGE REQUIREMENT: You MUST extract at least 2 clips per 10 minutes of content (approximately 8-12 clips per hour). Do not be overly selective - include both high-dopamine clips AND deep educational value clips.

RULES:
{rules}

HISTORICAL PERFORMANCE DATA:
{historical_data}

GROUNDING RULES:
1. Use only the provided transcript lines and indices
2. Never invent facts, tone, context, or transitions that are not present
3. Treat this as span selection over an indexed transcript, not open-ended summarization
4. Each selected segment must map to one contiguous range in the transcript
5. Do not stitch together distant moments into one clip
6. If a segment lacks context to stand alone, expand to nearby contiguous lines rather than guessing

CONTENT NEUTRALITY RULES:
1. This is clipping software for legitimate editing workflows
2. Do not judge, moralize, or downgrade a segment just because the topic is controversial, sensitive, adult, political, criminal, medical, or otherwise intense
3. Evaluate segments only on clip quality: clarity, self-contained value, hook strength, emotional impact, specificity, and shareability
4. Do not refuse analysis just because the speaker describes risky, offensive, or uncomfortable subject matter
5. Only downgrade a segment when the transcript itself is weak, confusing, repetitive, unusable, or a poor standalone clip

SEGMENT SELECTION CRITERIA (Priority Order):
1. SELF-CONTAINED: Complete thoughts that make sense alone without full video context
2. HIGH SIGNAL: Specific, concrete, actionable content with real examples/numbers/frameworks
3. VALUABLE CONTENT: Deep educational insights, step-by-step explanations, practical strategies
4. STRONG HOOKS: Attention-grabbing opening lines (bonus, not required)
5. ENTERTAINING: Emotional moments, humor, inspiration (bonus, not required)
6. LOW FILLER: Avoid greetings, sponsor reads, vague motivational speech, repetitive setup

CLIP DIVERSITY REQUIREMENT:
Extract BOTH types of high-performing clips:
A) HIGH DOPAMINE CLIPS (fast-paced, 10-30 seconds):
   - Strong hooks with immediate payoff
   - Surprising facts, bold claims, shocking statistics
   - High engagement + shareability scores
   - Quick, punchy, attention-grabbing

B) DEEP VALUE CLIPS (educational, 45-90 seconds):
   - Step-by-step tutorials or frameworks
   - Detailed explanations with actionable insights
   - High clip_quality + value scores (even if hook is weak)
   - Dense, no-BS educational content

Aim for a balanced mix: ~40% fast dopamine clips, ~60% deep educational clips.

GOOD CLIP EXAMPLES:
✓ 90-second explanation of a business model with specific numbers and frameworks (DEEP VALUE)
✓ 15-second surprising statistic with immediate wow factor (HIGH DOPAMINE)
✓ Step-by-step tutorial on a technical concept with actionable takeaways (DEEP VALUE)
✓ 20-second bold claim with quick proof or example (HIGH DOPAMINE)
✓ Deep dive into a strategy with concrete examples (DEEP VALUE - even without flashy hook)
✓ Raw, unfiltered advice with specific, no-BS guidance (DEEP VALUE)
✓ Complete case study or story with clear beginning, middle, end (DEEP VALUE)

BAD CLIP EXAMPLES:
✗ Vague motivational speech without specifics or actionable advice
✗ Greeting/intro segments with no payoff or substance
✗ Repetitive setup without the actual insight or conclusion
✗ Incomplete thoughts that require full video context to understand
✗ Surface-level common knowledge without depth

VIRALITY SCORING (0-100 total, from five 0-20 subscores):
For each segment, provide a detailed breakdown:

1. CLIP QUALITY (0-20):
   - 16-20: Self-contained, clear context, dense information, no BS, works standalone
   - 11-15: Mostly complete, minor context needed
   - 6-10: Requires some external knowledge to fully understand
   - 0-5: Confusing without full video context

2. VALUE (0-20):
   - 16-20: Deep educational content, frameworks, actionable strategies, unique insights
   - 11-15: Useful information with practical application
   - 6-10: Interesting but not immediately actionable
   - 0-5: Surface-level or common knowledge

3. HOOK STRENGTH (0-20):
   - 16-20: Immediately grabs attention (surprising fact, bold claim, intriguing question)
   - 11-15: Good opener that creates curiosity
   - 6-10: Decent start but could be stronger
   - 0-5: Weak or no hook

4. ENGAGEMENT (0-20):
   - 16-20: Highly entertaining, emotional, or dramatic delivery
   - 11-15: Interesting and holds attention throughout
   - 6-10: Moderately engaging
   - 0-5: Flat or boring delivery

5. SHAREABILITY (0-20):
   - 16-20: "I need to send this to someone" content
   - 11-15: Content worth bookmarking or saving
   - 6-10: Nice but not particularly share-worthy
   - 0-5: Generic content

HOOK TYPES to identify:
- "question": Opens with a question that creates curiosity
- "statement": Bold claim or surprising statement
- "statistic": Uses compelling numbers or data
- "story": Starts with narrative/anecdote
- "contrast": Before/after or problem/solution framing
- "none": No clear hook pattern

TIMING REQUIREMENTS:
- Segments MUST be between {min_dur}-{max_dur} seconds for optimal engagement
- Each segment must have enough context to be understandable
- Start as late as possible while preserving the hook, end as early as possible after the payoff

B-ROLL OPPORTUNITIES:
For each candidate, identify 2-3 moments where stock footage would enhance the video:
- Provide timestamp range (e.g., "12-15" for seconds 12-15)
- Provide specific search query for stock footage (e.g., "falling stock market chart", "person typing on laptop")
- Focus on moments with abstract concepts, statistics, or visual metaphors

{retry_context}

Return ONLY valid JSON with this exact structure:
{{
  "candidates": [
    {{
      "candidate_id": 1,
      "segments": [6, 8, "9-11"],
      "hook_summary": "Brief explanation",
      "viral_title": "Catchy viral title with emojis that hooks viewers",
      "virality": {{
        "clip_quality_score": 18,
        "value_score": 20,
        "hook_score": 12,
        "engagement_score": 15,
        "shareability_score": 16,
        "total_score": 81,
        "hook_type": "question",
        "reasoning": "Self-contained explanation with actionable framework..."
      }},
      "broll_opportunities": [
        {{"timestamp_range": "12-15", "search_query": "falling stock market chart"}},
        {{"timestamp_range": "28-32", "search_query": "person celebrating success"}}
      ]
    }}
  ]
}}

Segments are transcript line indices. Use ranges like "9-11" for consecutive lines.
CRITICAL: total_score MUST equal the sum of the five subscores (clip_quality + value + hook + engagement + shareability)."""

    payload = {
        "model": LOCAL_LLM_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"TRANSCRIPT:\n{transcript_text}"}
        ],
        "temperature": 0.7
    }
    
    headers = {"Content-Type": "application/json"}
    if LOCAL_LLM_API_KEY:
        headers["Authorization"] = f"Bearer {LOCAL_LLM_API_KEY}"
    response = httpx.post(LOCAL_LLM_URL, json=payload, headers=headers, timeout=120.0)
    response.raise_for_status()
    result = response.json()
    message = result['choices'][0]['message']
    content = message.get('content') or message.get('reasoning', '')
    
    return parse_llm_json(content)

def _enrich_with_heatmap(candidates, transcript, full_video_heatmap):
    """Compute heatmap metrics per candidate and blend into combined score"""
    for candidate in candidates:
        segs = candidate.get('segments', [])
        if isinstance(segs, str):
            segs = [segs]
        if not segs:
            continue
        
        try:
            if isinstance(segs[0], str) and '-' in segs[0]:
                start_idx = int(segs[0].split('-')[0])
            else:
                start_idx = int(segs[0])
            
            if isinstance(segs[-1], str) and '-' in segs[-1]:
                end_idx = int(segs[-1].split('-')[1])
            else:
                end_idx = int(segs[-1])
            
            clip_start = transcript[start_idx]['start']
            clip_end = transcript[end_idx]['end']
        except:
            continue
        
        overlapping = [
            h for h in full_video_heatmap
            if h['end'] > clip_start and h['start'] < clip_end
        ]
        
        if overlapping:
            avg_norm = sum(h['intensity_norm'] for h in overlapping) / len(overlapping)
            peak = max(overlapping, key=lambda h: h['intensity_norm'])
            peak_norm = peak['intensity_norm']
            peak_time = peak['start'] + peak['duration'] / 2.0
        else:
            avg_norm = 0.0
            peak_norm = 0.0
            peak_time = clip_start
        
        candidate['heatmap'] = {
            'avg_norm': round(avg_norm, 3),
            'peak_norm': round(peak_norm, 3),
            'peak_time_sec': round(peak_time, 2)
        }
        
        virality_score = candidate.get('virality', {}).get('total_score', 0)
        heatmap_signal = avg_norm * 100.0
        combined = 0.75 * virality_score + 0.25 * heatmap_signal
        candidate['_combined_score'] = round(combined, 2)
    
    return candidates


def _assign_edit_techniques(candidates, transcript):
    """Assign edit_mode based on LLM-detected bridge sentences and climaxes"""
    for candidate in candidates:
        bridge = candidate.get('seamless_loop_bridge')
        climax = candidate.get('cold_open_climax')
        
        if bridge and bridge.get('sentence') and bridge.get('split_word_index') is not None:
            edit_mode = 'loop_hook'
            cold_open_enabled = False
            seamless_loop_enabled = True
            cold_open_metadata = None
            seamless_loop_metadata = bridge
        elif climax and climax.get('start_index') is not None:
            edit_mode = 'cold_open'
            cold_open_enabled = True
            seamless_loop_enabled = False
            cold_open_metadata = climax
            seamless_loop_metadata = None
        else:
            edit_mode = 'cold_open'
            cold_open_enabled = False
            seamless_loop_enabled = False
            cold_open_metadata = None
            seamless_loop_metadata = None
        
        candidate['edit_techniques'] = {
            'edit_mode': edit_mode,
            'cold_open_hook': {
                'enabled': cold_open_enabled,
                'metadata': cold_open_metadata
            },
            'seamless_loop': {
                'enabled': seamless_loop_enabled,
                'metadata': seamless_loop_metadata
            }
        }
    
    return candidates


def calculate_math_engagement_score(clip_text, duration):
    """Calculate mathematical engagement score using ClippedAI formula"""
    words = clip_text.split()
    total_words = len(words)
    
    if total_words == 0 or duration == 0:
        return 0.0
    
    word_density = total_words / duration
    
    numbers = sum(1 for w in words if any(c.isdigit() for c in w))
    currency_symbols = sum(1 for w in words if '$' in w or '€' in w or '£' in w)
    exclamations = sum(1 for w in words if '!' in w)
    engagement_ratio = (numbers + currency_symbols + exclamations) / total_words
    
    duration_balance = 1 - abs(duration - 60) / 60
    
    math_score = (word_density * 0.45) + (engagement_ratio * 0.30) + (duration_balance * 0.25)
    return math_score * 100

def mine_candidates(video_id, rule_profile=None, max_retries=3, full_video_words=None, max_candidates=None, min_clips=None, max_clips=None, transcript=None, full_video_heatmap=None):
    """Phase 1: Extract candidates with validation and virality scoring"""
    from yt_dlp import YoutubeDL
    
    video_duration_seconds = None
    try:
        with YoutubeDL({'quiet': True}) as ydl:
            info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
            video_duration_seconds = info.get('duration')
            if video_duration_seconds:
                print(f"📊 Video duration: {video_duration_seconds//60}m {video_duration_seconds%60}s")
    except:
        pass
    
    if transcript is None:
        transcript = fetch_transcript(video_id, full_video_words)
    rules, historical_data, config = load_context(rule_profile)
    
    min_dur = config.get('min_duration', MIN_DURATION)
    max_dur = config.get('max_duration', MAX_DURATION)
    
    chunks = chunk_transcript(transcript)
    print(f"📑 Split transcript into {len(chunks)} chunks ({CHUNK_SIZE_MINUTES}min/{CHUNK_OVERLAP_SECONDS}s overlap)")
    
    all_candidates = []
    for chunk in chunks:
        print(f"  Processing {chunk['time_range']}...")
        try:
            result = call_local_llm_miner(
                chunk['transcript'], rules, historical_data, min_dur, max_dur, 
                "", video_duration_seconds, chunk['time_range'], min_clips, max_clips, full_video_heatmap
            )
            
            for candidate in result.get('candidates', []):
                try:
                    duration = calculate_duration(candidate['segments'], transcript)
                except Exception as e:
                    print(f"  ⚠️  Bad segments in candidate {candidate.get('candidate_id', '?' )}: {candidate.get('segments')} - {e}")
                    continue
                
                virality = candidate.get('virality') or candidate.get('virality_scores') or {}
                if isinstance(virality, dict):
                    calculated_total = (virality.get('clip_quality_score', 0) + 
                               virality.get('value_score', 0) + 
                               virality.get('hook_score', 0) + 
                               virality.get('engagement_score', 0) + 
                               virality.get('shareability_score', 0))
                    if calculated_total == 0:
                        calculated_total = virality.get('total_score', 0)
                    if calculated_total == 0:
                        calculated_total = 60
                    if virality.get('total_score', 0) != calculated_total:
                        virality['total_score'] = calculated_total
                    candidate['virality'] = virality
                
                if min_dur <= duration <= max_dur:
                    candidate['duration'] = duration
                    virality_score = candidate.get('virality', {}).get('total_score', 60)
                    if virality_score >= MIN_VIRALITY_SCORE:
                        all_candidates.append(candidate)

            if max_candidates is not None and len(all_candidates) >= max_candidates * 3:
                print(f"  🎯 Reached sufficient candidate pool for limit={max_candidates}, stopping early")
                break
        except Exception as e:
            print(f"  ⚠️  Error processing chunk: {e}")
    
    valid_candidates = deduplicate_candidates(all_candidates, transcript)
    
    if valid_candidates:
        for candidate in valid_candidates:
            if 'viral_title' not in candidate or not candidate['viral_title']:
                candidate['viral_title'] = candidate.get('hook_summary', 'Untitled')
        
        if full_video_heatmap:
            valid_candidates = _enrich_with_heatmap(valid_candidates, transcript, full_video_heatmap)
        
        valid_candidates.sort(key=lambda x: x.get('_combined_score', x.get('virality', {}).get('total_score', 0)), reverse=True)
        
        min_target, max_target = calculate_target_candidates(transcript, video_duration_seconds, min_clips, max_clips)
        if max_candidates is not None:
            max_target = min(max_target, max_candidates)
        
        valid_candidates = valid_candidates[:max_target]
        
        valid_candidates = _assign_edit_techniques(valid_candidates, transcript)
        
        print(f"✅ Found {len(valid_candidates)} highlight reels (quota: {min_target}-{max_target})")
        return valid_candidates, transcript, config
    
    raise Exception("Failed to extract valid candidates")
