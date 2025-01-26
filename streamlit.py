import streamlit as st
import asyncio
import os
import io
import zipfile
import tempfile
import logging
from pathlib import Path
from typing import List, Dict
from bulk_processor import BulkProcessor

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Session state management
def init_session_state():
    if 'processing' not in st.session_state:
        st.session_state.processing = False
    if 'results' not in st.session_state:
        st.session_state.results = None
    if 'zip_data' not in st.session_state:
        st.session_state.zip_data = None
    if 'selected_clips' not in st.session_state:
        st.session_state.selected_clips = set()

init_session_state()

def create_zip(temp_dir: str) -> io.BytesIO:
    """Create ZIP file from processed clips"""
    zip_buffer = io.BytesIO()
    file_count = 0
    
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        for root, _, files in os.walk(temp_dir):
            for file in files:
                file_path = Path(root) / file
                relative_path = file_path.relative_to(temp_dir)
                
                # Skip temporary files
                if file.endswith(('.tmp', '.part', '.log')):
                    continue
                
                try:
                    zip_file.write(file_path, arcname=relative_path)
                    file_count += 1
                    logger.info(f"Added to ZIP: {relative_path}")
                except Exception as e:
                    logger.error(f"Failed to add {file_path}: {str(e)}")
    
    zip_buffer.seek(0)
    logger.info(f"Created ZIP with {file_count} files")
    return zip_buffer

def main():
    st.title("YouTube Video Clip Processor")
    
    # Sidebar controls
    with st.sidebar:
        st.header("Processing Settings")
        concurrency = st.slider("Concurrent Workers", 1, 5, 2)
        lang = st.selectbox("Transcript Language", ["en", "es", "fr", "de", "ja"])
        transcript_enabled = st.checkbox("Enable Transcripts", value=True)
    
    # Main UI
    st.header("Video Input")
    video_ids = st.text_input("Enter YouTube Video IDs (comma-separated)")
    uploaded_file = st.file_uploader("Or upload TXT file with IDs", type=["txt"])
    
    # Processing controls
    if st.button("Start Processing") and not st.session_state.processing:
        st.session_state.processing = True
        st.session_state.results = None
        st.session_state.zip_data = None
        
        try:
            # Get video IDs
            ids = [i.strip() for i in video_ids.split(",") if i.strip()]
            if uploaded_file:
                ids += [i.strip() for i in uploaded_file.read().decode().split(",")]
            
            if not ids:
                st.error("Please provide at least one valid Video ID")
                return
            
            # Process videos
            with tempfile.TemporaryDirectory() as temp_dir:
                processor = BulkProcessor(concurrency=concurrency)
                results = asyncio.run(
                    processor.process_sources(ids, lang, temp_dir, transcript_enabled)
                )
                
                # Create ZIP while temp directory exists
                zip_buffer = create_zip(temp_dir)
                st.session_state.zip_data = zip_buffer.getvalue()
                st.session_state.results = results
        
        except Exception as e:
            st.error(f"Processing failed: {str(e)}")
            logger.exception("Processing error")
        finally:
            st.session_state.processing = False

    # Results display
    if st.session_state.results and st.session_state.zip_data:
        st.header("Processed Clips")
        
        # Select all checkbox
        select_all = st.checkbox("Select All Clips", value=True)
        
        # Clip display and selection
        for idx, result in enumerate(st.session_state.results['success']):
            video_id = result['video_id']
            clip_dir = Path(result['clip_dir'])
            
            st.subheader(f"Video ID: {video_id}")
            for clip_file in clip_dir.glob("clips/*.mp4"):
                clip_name = clip_file.name
                clip_key = f"{video_id}_{clip_name}"
                
                col1, col2 = st.columns([1, 4])
                with col1:
                    selected = st.checkbox(
                        f"Include {clip_name}",
                        value=select_all,
                        key=clip_key
                    )
                    if selected:
                        st.session_state.selected_clips.add(clip_file)
                
                with col2:
                    try:
                        with open(clip_file, "rb") as f:
                            video_bytes = f.read()
                        st.video(video_bytes)
                    except FileNotFoundError:
                        st.error("Clip file not found")

        # Download button
        st.download_button(
            label="Download Selected Clips",
            data=st.session_state.zip_data,
            file_name="processed_clips.zip",
            mime="application/zip"
        )

if __name__ == "__main__":
    main()
