#!/usr/bin/env python3
"""
Render all caption styles to blank video for preview.
"""
import subprocess
import os
from caption_templates import get_all_templates
from phase6_captions import generate_ass_subtitles, apply_captions_to_video

BLANK_VIDEO = "temp/blank_video.mp4"

SAMPLE_WORDS = [
    {"word": "This", "start": 0.0, "end": 0.3, "speaker": 0, "confidence": 1.0},
    {"word": "is", "start": 0.3, "end": 0.5, "speaker": 0, "confidence": 1.0},
    {"word": "how", "start": 0.5, "end": 0.7, "speaker": 0, "confidence": 1.0},
    {"word": "the", "start": 0.7, "end": 0.9, "speaker": 0, "confidence": 1.0},
    {"word": "caption", "start": 0.9, "end": 1.3, "speaker": 0, "confidence": 1.0},
    {"word": "style", "start": 1.3, "end": 1.7, "speaker": 0, "confidence": 1.0},
    {"word": "looks", "start": 1.7, "end": 2.0, "speaker": 0, "confidence": 1.0},
    {"word": "like!", "start": 2.0, "end": 2.5, "speaker": 0, "confidence": 1.0},
]

SAMPLE_WORDS2 = [
    {"word": "Make", "start": 0.0, "end": 0.4, "speaker": 0, "confidence": 1.0},
    {"word": "$1,000,000", "start": 0.4, "end": 1.0, "speaker": 0, "confidence": 1.0},
    {"word": "in", "start": 1.0, "end": 1.2, "speaker": 0, "confidence": 1.0},
    {"word": "1", "start": 1.2, "end": 1.4, "speaker": 0, "confidence": 1.0},
    {"word": "hour!", "start": 1.4, "end": 2.0, "speaker": 0, "confidence": 1.0},
]


def create_blank_video():
    """Create a 10-second blank video"""
    os.makedirs("temp", exist_ok=True)
    os.makedirs("output", exist_ok=True)
    
    if os.path.exists(BLANK_VIDEO):
        return BLANK_VIDEO
    
    cmd = [
        "ffmpeg", "-f", "lavfi", "-i", "color=c=black:s=1080x1920:d=10",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-y", BLANK_VIDEO
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    print(f"✓ Created blank video: {BLANK_VIDEO}")
    return BLANK_VIDEO


def render_all_styles():
    """Render each caption style to a separate video"""
    create_blank_video()
    
    templates = get_all_templates()
    results = []
    
    for name, template in templates.items():
        print(f"\n🎬 Rendering style: {name}")
        print(f"   {template.get('description', '')}")
        print(f"   Font: {template.get('font_family', 'Noto Sans')}")
        print(f"   Size: {template.get('font_size', 80)}")
        print(f"   Animation: {template.get('animation', 'none')}")
        
        ass_path = f"temp/captions_{name}.ass"
        
        generate_ass_subtitles(SAMPLE_WORDS2, ass_path, name)
        
        output_path = f"output/style_preview_{name}.mp4"
        
        apply_captions_to_video(BLANK_VIDEO, ass_path, output_path)
        
        results.append({
            "style": name,
            "output": output_path,
            "description": template.get("description", ""),
            "font": template.get("font_family", ""),
            "animation": template.get("animation", "")
        })
        print(f"   ✓ Saved: {output_path}")
    
    print("\n" + "=" * 70)
    print("🎉 All styles rendered!")
    print("=" * 70)
    
    print(f"\n{'Style':<12} {'Font':<25} {'Animation':<10} {'Output'}")
    print("-" * 70)
    for r in results:
        print(f"{r['style']:<12} {r['font']:<25} {r['animation']:<10} {r['output']}")
    
    return results


if __name__ == "__main__":
    render_all_styles()