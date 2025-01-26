import streamlit as st
import asyncio
import json
import logging
import tempfile
import zipfile
from pathlib import Path
from typing import List
import io
import base64
import os
from bulk_processor import BulkProcessor

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize session state
if 'processed' not in st.session_state:
    st.session_state.processed = False
if 'clips' not in st.session_state:
    st.session_state.clips = []
if 'selected_clips' not in st.session_state:
    st.session_state.selected_clips = set()
if 'zip_data' not in st.session_state:
    st.session_state.zip_data = None

def get_video_ids(input_text, uploaded_file):
    """Extract video IDs from text input or uploaded file"""
    video_ids = []
    
    if uploaded_file:
        text = uploaded_file.read().decode()
        video_ids.extend([vid.strip() for vid in text.split(',') if vid.strip()])
    
    if input_text:
        video_ids.extend([vid.strip() for vid in input_text.split(',') if vid.strip()])
    
    return list(set(video_ids))

async def process_videos(video_ids, lang, output_dir, concurrency, transcript_enabled):
    """Async processing wrapper"""
    try:
        processor = BulkProcessor(concurrency=concurrency)
        return await processor.process_sources(
            video_ids, lang, str(output_dir), transcript_enabled
        )
    except Exception as e:
        logger.error(f"Processing error: {str(e)}")
        return None

def create_zip(clip_paths, transcript_paths):
    """Create in-memory ZIP file with selected clips and transcripts"""
    zip_buffer = io.BytesIO()
    
    with zipfile.ZipFile(zip_buffer, 'a', zipfile.ZIP_DEFLATED) as zip_file:
        for clip_path in clip_paths:
            if Path(clip_path).exists():
                zip_file.write(clip_path, arcname=Path(clip_path).name)
                if transcript_paths and Path(clip_path + '.json').exists():
                    zip_file.write(clip_path + '.json', 
                                 arcname=Path(clip_path + '.json').name)
    
    zip_buffer.seek(0)
    return zip_buffer

async def main_processing_flow():
    """Main async processing flow"""
    st.title("YouTube Bulk Video Clipper")
    
    # Sidebar controls
    with st.sidebar:
        st.header("Processing Options")
        concurrency = st.slider("Concurrency Level", 1, 10, 4)
        lang = st.selectbox("Language", ["en", "es", "fr", "de", "ja"], index=0)
        transcript_enabled = st.checkbox("Enable Transcripts", value=True)
    
    # Main input area
    st.header("Input Sources")
    input_text = st.text_input("Enter Video IDs (comma-separated)")
    uploaded_file = st.file_uploader("Or upload TXT file with Video IDs", 
                                   type=["txt"])
    
    # Process button
    if st.button("Process Videos"):
        video_ids = get_video_ids(input_text, uploaded_file)
        
        if not video_ids:
            st.error("Please provide at least one valid Video ID")
            return
            
        with tempfile.TemporaryDirectory() as temp_dir:
            with st.spinner("Processing videos..."):
                try:
                    results = await process_videos(
                        video_ids, lang, temp_dir, concurrency, transcript_enabled
                    )
                    
                    if not results:
                        st.error("Processing failed - check logs for details")
                        return
                    
                    # Collect all processed clips
                    all_clips = []
                    for result in results['success']:
                        clip_dir = Path(result['clip_dir'])
                        for clip_file in clip_dir.glob("*.mp4"):
                            all_clips.append({
                                'path': str(clip_file),
                                'start': "N/A",  # Update with actual data from results
                                'end': "N/A",
                                'attention': "N/A",
                                'transcript': str(clip_file.with_suffix('.json'))
                            })
                    
                    st.session_state.clips = all_clips
                    st.session_state.selected_clips = set(range(len(all_clips)))
                    st.session_state.processed = True
                    
                except Exception as e:
                    st.error(f"Processing failed: {str(e)}")
                    logger.exception("Processing error")

    # Results display
    if st.session_state.processed and st.session_state.clips:
        st.header("Processed Clips")
        
        # Select all checkbox
        col1, col2 = st.columns([1, 10])
        with col1:
            select_all = st.checkbox("Select All", value=True)
        with col2:
            if st.button("Create Download Package"):
                selected_paths = [
                    st.session_state.clips[i]['path']
                    for i in st.session_state.selected_clips
                ]
                transcript_paths = [
                    st.session_state.clips[i]['transcript']
                    for i in st.session_state.selected_clips
                    if transcript_enabled
                ]
                
                zip_buffer = create_zip(selected_paths, transcript_paths)
                st.session_state.zip_data = zip_buffer.getvalue()
        
        # Download button
        if st.session_state.zip_data:
            st.download_button(
                label="Download ZIP",
                data=st.session_state.zip_data,
                file_name="clips_package.zip",
                mime="application/zip"
            )
        
        # Clip display
        for idx, clip in enumerate(st.session_state.clips):
            with st.expander(f"Clip {idx+1}"):
                col1, col2 = st.columns([1, 4])
                
                with col1:
                    # Clip selection checkbox
                    selected = st.checkbox(
                        f"Include in package", 
                        value=select_all,
                        key=f"clip_{idx}"
                    )
                    if selected:
                        st.session_state.selected_clips.add(idx)
                    else:
                        st.session_state.selected_clips.discard(idx)
                
                with col2:
                    try:
                        with open(clip['path'], 'rb') as f:
                            video_bytes = f.read()
                        st.video(video_bytes)
                    except FileNotFoundError:
                        st.error("Clip video file not found")

if __name__ == "__main__":
    # Install Playwright dependencies
    os.system("playwright install")
    
    # Run the async app
    asyncio.run(main_processing_flow())
