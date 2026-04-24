# Hybrid AI-Automated Viral Clipping Pipeline

Automated "Rough Cut Engine" for creating viral short-form content from long-form videos using Gemini, Whisper, and hardware-accelerated FFmpeg.

## Architecture

- **Phase 1**: Context Injection & The Miner (Gemini API)
- **Phase 2**: The Editor (Gemini API for filler detection)
- **Phase 3**: AV Extraction (yt-dlp + FFmpeg)
- **Phase 4**: Precision Syncing (Whisper API)
- **Phase 5**: Math Engine & Hardware Render (FFmpeg QSV/VAAPI)

## Requirements

- Python 3.11+
- FFmpeg with Intel Quick Sync (h264_qsv) or VAAPI support
- API Keys: Gemini, OpenAI (Whisper)

## Installation

See [INSTALL.md](INSTALL.md) for detailed setup instructions using `uv`.

## Configuration

Set environment variables:
```bash
export GEMINI_API_KEY="your_gemini_key"
export OPENAI_API_KEY="your_openai_key"
```

Create `rules/username.txt` with content guidelines for each creator.

Create `master_results.csv` with columns: `channel,hook,views` for historical data.

## Usage

```bash
python pipeline.py <youtube_url> <username>
```

Example:
```bash
python pipeline.py "https://youtube.com/watch?v=dQw4w9WgXcQ" john_doe
```

## Output

Raw 9:16 MP4 files in `output/` directory, ready for CapCut Desktop finishing:
- Auto-captions
- B-roll overlays
- Audio ducking
- Transitions & branding

## Hardware Acceleration

Automatically uses Intel Quick Sync (QSV) if available, falls back to software encoding.
