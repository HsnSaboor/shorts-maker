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
import os
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
    
    # In your Streamlit app code (modified section)
    if st.button("Start Processing") and not st.session_state.processing:
        st.session_state.processing = True
        st.session_state.progress = 0
        
        try:
            # Get video IDs
            ids = [i.strip() for i in video_ids.split(",") if i.strip()]
            if uploaded_file:
                ids += [i.strip() for i in uploaded_file.read().decode().split(",")]
            
            if not ids:
                st.error("Please enter at least one video ID")
                return
                
            # Processing pipeline
            with tempfile.TemporaryDirectory() as temp_dir:
                processor = BulkProcessor(concurrency=concurrency)
                results = asyncio.run(processor.process_sources(
                    ids, lang, temp_dir, transcript_enabled
                ))
                
                # Create ZIP package while still in temp directory context
                zip_buffer = io.BytesIO()
                file_count = 0
                
                with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                    # Collect all successful clips
                    for result in results['success']:
                        clip_dir = Path(result['clip_dir'])
                        
                        # Recursive search for all clip files
                        for clip_file in clip_dir.glob('**/*'):
                            if clip_file.is_file():
                                arcname = clip_file.relative_to(temp_dir)
                                zip_file.write(clip_file, arcname=arcname)
                                file_count += 1
                                logger.info(f"Added to ZIP: {arcname}")
                
                if file_count == 0:
                    st.error("No clips found to zip!")
                    return
                    
                st.session_state.zip_buffer = zip_buffer.getvalue()
                logger.info(f"Created ZIP with {file_count} files ({len(st.session_state.zip_buffer)} bytes)")
                
                st.session_state.processing = False
    
        except Exception as e:
            st.error(f"Processing failed: {str(e)}")
            logger.exception("Processing error")
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
