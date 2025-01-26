# streamlit_app.py (updated progress handling)
import streamlit as st
import asyncio
import json
import logging
import tempfile
import zipfile
from pathlib import Path
from typing import List
import io
import time
from bulk_processor import BulkProcessor

os.system("playwright install")

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    st.title("YouTube Bulk Video Processor")
    
    # Session state initialization
    if 'processing' not in st.session_state:
        st.session_state.processing = False
    if 'progress' not in st.session_state:
        st.session_state.progress = 0

    # Sidebar controls
    with st.sidebar:
        st.header("Processing Settings")
        concurrency = st.slider("Concurrent Downloads", 1, 5, 2)
        lang = st.selectbox("Transcript Language", ["en", "es", "fr", "de", "ja"])
        transcript_enabled = st.checkbox("Enable Transcripts", value=True)
        st.info("Note: Higher concurrency requires more system resources")

    # Main UI
    st.header("Video Input")
    video_ids = st.text_input("Enter YouTube Video IDs (comma-separated)")
    uploaded_file = st.file_uploader("Or upload TXT file with IDs", type=["txt"])
    
    # Progress bar
    progress_bar = st.progress(st.session_state.progress)
    
    # Processing control
    if st.button("Start Processing") and not st.session_state.processing:
        st.session_state.processing = True
        st.session_state.progress = 0
        
        try:
            # Get video IDs
            ids = []
            if video_ids:
                ids.extend([i.strip() for i in video_ids.split(",") if i.strip()])
            if uploaded_file:
                ids.extend([i.strip() for i in uploaded_file.read().decode().split(",")])
            
            if not ids:
                st.error("Please provide at least one valid Video ID")
                return
                
            # Process videos
            with tempfile.TemporaryDirectory() as temp_dir:
                processor = BulkProcessor(concurrency=concurrency)
                
                # Create wrapper for progress updates
                def update_progress(percent: float):
                    st.session_state.progress = percent / 100  # Convert to 0-1 scale
                    progress_bar.progress(st.session_state.progress)
                
                # Process videos (would need to modify BulkProcessor to accept progress callback)
                results = asyncio.run(processor.process_sources(
                    ids, lang, temp_dir, transcript_enabled
                ))
                
                # Create ZIP package
                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(zip_buffer, 'w') as zip_file:
                    for result in results['success']:
                        clip_dir = Path(result['clip_dir'])
                        for clip_file in clip_dir.glob("*.mp4"):
                            zip_file.write(clip_file, arcname=clip_file.name)
                            if transcript_enabled:
                                transcript_file = clip_file.with_suffix('.json')
                                if transcript_file.exists():
                                    zip_file.write(transcript_file, arcname=transcript_file.name)
                
                st.session_state.zip_data = zip_buffer.getvalue()
                st.success("Processing completed successfully!")
                
        except Exception as e:
            st.error(f"Processing failed: {str(e)}")
        finally:
            st.session_state.processing = False

    # Download section
    if 'zip_data' in st.session_state and st.session_state.zip_data:
        st.download_button(
            label="Download Processed Clips",
            data=st.session_state.zip_data,
            file_name="processed_clips.zip",
            mime="application/zip"
        )

if __name__ == "__main__":
    main()
