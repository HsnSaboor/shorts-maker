import subprocess
import streamlit as st
import asyncio
import logging
import tempfile
import zipfile
import os
import io
from pathlib import Path
from typing import List
from bulk_processor import BulkProcessor

# --- Playwright Installation First ---
os.system("playwright install")

# --- Logging Configuration ---
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

class StreamlitLogHandler(logging.Handler):
    def emit(self, record):
        log_entry = self.format(record)
        st.code(log_entry, language="plaintext")

formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
file_handler = logging.FileHandler('processing.log')
streamlit_handler = StreamlitLogHandler()
file_handler.setFormatter(formatter)
streamlit_handler.setFormatter(formatter)
logger.addHandler(file_handler)
logger.addHandler(streamlit_handler)

# --- Session State Initialization ---
if 'processed' not in st.session_state:
    st.session_state.update({
        'processed': False,
        'clips': [],
        'selected_clips': set(),
        'zip_data': None,
        'temp_dir': None
    })

# --- Helper Functions ---
def get_video_ids(input_text, uploaded_file):
    """Extract video IDs from text input or uploaded file"""
    video_ids = []
    if uploaded_file:
        try:
            video_ids.extend(uploaded_file.read().decode().split(','))
        except Exception as e:
            logger.error(f"File read error: {str(e)}")
    if input_text:
        video_ids.extend(input_text.split(','))
    return list(set(filter(None, (vid.strip() for vid in video_ids))))

def create_zip(temp_dir: str) -> bytes:
    """Create ZIP from directory without cleanup"""
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        for root, _, files in os.walk(temp_dir):
            for file in files:
                file_path = Path(root) / file
                arcname = file_path.relative_to(temp_dir)
                zip_file.write(file_path, arcname=arcname)
                logger.info(f"Zipped: {arcname}")
    return zip_buffer.getvalue()

# --- Main Application ---
def main():
    st.title("YouTube Bulk Video Clipper")

    # --- Sidebar Controls ---
    with st.sidebar:
        st.header("Processing Options")
        concurrency = st.slider("Concurrency Level", 1, 10, 4)
        lang = st.selectbox("Language", ["en", "es", "fr", "de", "ja"], index=0)
        transcript_enabled = st.checkbox("Enable Transcripts", value=True)

    # --- Input Handling ---
    st.header("Input Sources")
    input_text = st.text_input("Enter Video IDs/URLs (comma-separated)")
    uploaded_file = st.file_uploader("Or upload TXT file", type=["txt"])

    # --- Processing Logic ---
    if st.button("Process Videos"):
        video_ids = get_video_ids(input_text, uploaded_file)
        
        if not video_ids:
            st.error("Please provide valid input")
            return

        # Cleanup previous temp directory
        if st.session_state.temp_dir:
            st.session_state.temp_dir.cleanup()
        
        # Create new temp directory for this session
        st.session_state.temp_dir = tempfile.TemporaryDirectory()
        temp_dir = st.session_state.temp_dir.name

        with st.spinner("Processing..."):
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                processor = BulkProcessor(concurrency=concurrency)
                results = loop.run_until_complete(
                    processor.process_sources(
                        video_ids, lang, temp_dir, transcript_enabled
                    )
                )

                # Collect processed clips
                all_clips = []
                for result in results['success']:
                    clip_dir = Path(temp_dir) / result['video_id'] / "clips"
                    for clip_file in clip_dir.glob("*.mp4"):
                        all_clips.append({
                            'path': str(clip_file),
                            'metadata': Path(clip_file).with_suffix('.json').read_text()
                        })

                st.session_state.update({
                    'processed': True,
                    'clips': all_clips,
                    'selected_clips': set(range(len(all_clips))),
                    'zip_data': create_zip(temp_dir)
                })
                st.success(f"Processed {len(all_clips)} clips")

            except Exception as e:
                logger.error(f"Processing failed: {str(e)}")
                st.error(f"Error: {str(e)}")

    # --- Results Display ---
    if st.session_state.processed:
        st.header("Results")
        
        # Clip selection
        select_all = st.checkbox("Select All", True)
        selected_indices = [
            idx for idx in range(len(st.session_state.clips))
            if select_all or idx in st.session_state.selected_clips
        ]

        # Clip previews
        for idx in selected_indices:
            clip = st.session_state.clips[idx]
            with st.expander(f"Clip {idx+1}"):
                st.video(clip['path'])
                st.json(clip['metadata'])

        # Download handling
        if st.session_state.zip_data:
            st.download_button(
                "Download Selected Clips",
                data=st.session_state.zip_data,
                file_name="clips.zip",
                mime="application/zip"
            )

if __name__ == "__main__":
    main()
