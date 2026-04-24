import httpx
import json
import os
from config import LOCAL_LLM_URL, LOCAL_LLM_MODEL, LOCAL_LLM_API_KEY, RULES_DIR
from utils.llm_utils import parse_llm_json

def load_creator_rules(rule_profile=None):
    """Load creator-specific editing rules"""
    if not rule_profile:
        return ""
    
    rules_path = os.path.join(RULES_DIR, rule_profile, "rules.json")
    try:
        with open(rules_path, 'r') as f:
            config = json.load(f)
        return config.get('base_rules', '')
    except FileNotFoundError:
        print(f"⚠️  Rules profile '{rule_profile}' not found at {rules_path}, using defaults")
        return ""

def call_local_llm_editor(words, candidate_id, rule_profile=None):
    """Call Local LLM API to identify specific word indices to remove and boundary trimming"""
    words_text = "\n".join([f"[{i}] {w['word']} ({w['start']:.2f}s - {w['end']:.2f}s) [Speaker {w.get('speaker', 0)}]" for i, w in enumerate(words)])
    
    creator_rules = load_creator_rules(rule_profile)
    rules_section = f"\n\nCREATOR-SPECIFIC RULES:\n{creator_rules}\n" if creator_rules else ""
    
    system_prompt = f"""You are a precision video editor. Analyze this word-level transcript with speaker labels and identify:
1. Filler words (um, uh, like, you know, etc.)
2. Stutters and false starts
3. Repetitive words that disrupt flow
4. Dead air or awkward pauses

CRITICAL SPEAKER-AWARE EDITING RULES:
- NEVER cut in the middle of a speaker's sentence
- Preserve at least a 0.5-second buffer around speaker transitions
- Use the [Speaker X] tags to ensure you don't splice two different speakers' half-sentences together
- Only remove words within a single speaker's continuous segment

BOUNDARY TRIMMING:
Analyze the first 5-10 words and last 5-10 words for weak content:
- Weak openings: incomplete thoughts, mid-sentence starts, references to missing context
- Weak endings: channel branding, generic CTAs, trailing off-topic remarks, incomplete thoughts
- Add weak boundary words directly to word_indices_to_remove
- Respect creator rules about preserving or removing specific content types{rules_section}

Return ONLY valid JSON with this exact structure:
{{
  "candidate_id": 1,
  "word_indices_to_remove": [0, 1, 2, 5, 12, 23, 98, 99, 100]
}}

word_indices_to_remove contains ALL words to cut: boundary trims + fillers + silence gaps.
Be conservative - only flag words that truly disrupt flow."""

    payload = {
        "model": LOCAL_LLM_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"WORD-LEVEL TRANSCRIPT:\n{words_text}"}
        ],
        "temperature": 0.3
    }
    
    headers = {"Content-Type": "application/json"}
    if LOCAL_LLM_API_KEY:
        headers["Authorization"] = f"Bearer {LOCAL_LLM_API_KEY}"
    
    try:
        response = httpx.post(LOCAL_LLM_URL, json=payload, headers=headers, timeout=30.0)
        response.raise_for_status()
    except httpx.HTTPStatusError as e:
        print(f"⚠️  LLM error: {e.response.text}")
        raise
    
    result = response.json()
    text = result['choices'][0]['message']['content'].strip()
    
    parsed = parse_llm_json(text)
    if not parsed:
        return {"candidate_id": candidate_id, "word_indices_to_remove": [], "trim_start_index": 0, "trim_end_index": len(words)}
    
    if 'trim_start_index' not in parsed:
        parsed['trim_start_index'] = 0
    if 'trim_end_index' not in parsed:
        parsed['trim_end_index'] = len(words)
    
    return parsed

def identify_fillers(words, candidate_id, rule_profile=None):
    """Phase 2: Identify word indices to remove and boundary trimming"""
    result = call_local_llm_editor(words, candidate_id, rule_profile)
    return {
        'word_indices_to_remove': result.get('word_indices_to_remove', []),
        'trim_start_index': result.get('trim_start_index', 0),
        'trim_end_index': result.get('trim_end_index', len(words))
    }
