import json
import re

def parse_llm_json(response_text):
    """Parse JSON from LLM response with robust error handling"""
    text = response_text.strip()
    
    # Handle markdown code blocks
    if '```json' in text:
        text = text.split('```json')[1].split('```')[0].strip()
    elif '```' in text:
        text = text.split('```')[1].split('```')[0].strip()
    
    if not text:
        return {}
    
    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    
    # Try to find JSON object using regex
    match = re.search(r'\{[\s\S]*\}', text)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            # Try cleanup and retry
            clean = match.group()
            clean = re.sub(r'^[^{]*', '', clean)
            clean = re.sub(r'[^}]*$', '', clean)
            try:
                return json.loads(clean)
            except:
                pass
    
    return {}