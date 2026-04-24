#!/usr/bin/env python3
"""Test JSON mode handling in phase2_editor"""
import json
from phase2_editor import call_local_llm_editor

# Mock word data
test_words = [
    {"word": "um", "start": 0.5, "end": 0.7, "speaker": 0},
    {"word": "hello", "start": 1.0, "end": 1.3, "speaker": 0},
    {"word": "uh", "start": 1.5, "end": 1.7, "speaker": 0},
    {"word": "world", "start": 2.0, "end": 2.5, "speaker": 0},
]

print("Testing LLM JSON mode with filler detection...")
print(f"Input: {len(test_words)} words")

try:
    result = call_local_llm_editor(test_words, candidate_id=1)
    print(f"\nRaw result: {json.dumps(result, indent=2)}")
    print(f"\nWord indices to remove: {result.get('word_indices_to_remove', [])}")
    print("\n✓ JSON parsing successful!")
except Exception as e:
    print(f"\n✗ Error: {e}")
    import traceback
    traceback.print_exc()
