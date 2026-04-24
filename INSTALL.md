# Installation Guide

## Prerequisites

- Python 3.10+
- FFmpeg with hardware acceleration support
- [uv](https://docs.astral.sh/uv/) package manager

## Install uv

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

## Setup

1. Create virtual environment:
```bash
uv venv
```

2. Activate virtual environment:
```bash
source .venv/bin/activate  # Linux/Mac
# or
.venv\Scripts\activate  # Windows
```

3. Install dependencies:
```bash
uv pip install -r requirements.txt
```

## Configuration

Set environment variables:
```bash
export GEMINI_API_KEY="your_gemini_key"
export OPENAI_API_KEY="your_openai_key"
```

Create `rules/username.json` with content guidelines for each creator.

Create `master_results.csv` with columns: `channel,hook,views` for historical data.

## Usage

```bash
python cli.py <youtube_url> [username]
```

Examples:
```bash
# Without username (no historical context)
python cli.py "https://youtube.com/watch?v=dQw4w9WgXcQ"

# With username (uses rules and historical data)
python cli.py "https://youtube.com/watch?v=dQw4w9WgXcQ" john_doe
```

## Output

Raw 9:16 MP4 files in `output/` directory with metadata JSON files for CapCut Desktop finishing.
