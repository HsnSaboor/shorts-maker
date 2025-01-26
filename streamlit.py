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

# Install Playwright dependencies first
os.system("playwright install")
os.system("playwright install-deps")

# Configure logging
class StreamlitHandler(logging.Handler):
    def emit(self, record):
        log_entry = self.format(record)
        st.code(log_entry, language="plaintext")

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

# Add handlers
handlers = [
    logging.FileHandler('processing.log'),
    StreamlitHandler()
]

for handler in handlers:
    handler.setFormatter(formatter)
    logger.addHandler(handler)

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
        logger.error(f"Processing error: {str(e)}", exc_info=True)
        return None

def create_zip(temp_dir: str):
    """Create in-memory ZIP file from processed files"""
    zip_buffer = io.BytesIO()
    try:
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for root, _, files in os.walk(temp_dir):
                for file in files:
                    file_path = Path(root) / file
                    if file_path.suffix in ('.mp4', '.json'):
                        zip_file.write(file_path, arcname=file_path.relative_to(temp_dir))
                        logger.info(f"Added to ZIP: {file_path.name}")
    except Exception as e:
        logger.error(f"ZIP creation failed: {str(e)}")
    return zip_buffer

async def main_async_flow():
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
    uploaded_file = st.file_uploader("Or upload TXT file", type=["txt"])
    
    # Process button
    if st.button("Process Videos"):
        video_ids = get_video_ids(input_text, uploaded_file)
        
        if not video_ids:
            st.error("Please provide at least one valid Video ID")
            return
            
        with tempfile.TemporaryDirectory() as temp_dir:
            with st.spinner("Processing videos..."):
                try:
                    logger.info(f"Starting processing for {len(video_ids)} videos")
                    
                    # Create new event loop for Streamlit compatibility
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    
                    results = await process_videos(
                        video_ids, lang, temp_dir, concurrency, transcript_enabled
                    )
                    
                    if not results:
                        st.error("Processing failed - check logs")
                        return
                    
                    # Collect processed clips
                    all_clips = []
                    for result in results['success']:
                        clip_dir = Path(result['clip_dir'])
                        for clip_file in clip_dir.glob("*.mp4"):
                            all_clips.append({
                                'path': str(clip_file),
                                'start': result.get('start', 0),
                                'end': result.get('end', 0),
                                'attention': result.get('average_attention', 0),
                                'transcript': str(clip_file.with_suffix('.json'))
                            })
                    
                    st.session_state.clips = all_clips
                    st.session_state.selected_clips = set(range(len(all_clips)))
                    st.session_state.processed = True
                    
                    # Create ZIP
                    zip_buffer = create_zip(temp_dir)
                    st.session_state.zip_data = zip_buffer.getvalue()
                    logger.info(f"Created ZIP package with {len(all_clips)} clips")
                    
                except Exception as e:
                    logger.error(f"Critical error: {str(e)}", exc_info=True)
                    st.error(f"Processing failed: {str(e)}")

    # Results display
    if st.session_state.processed and st.session_state.clips:
        st.header("Processed Clips")
        
        # Select all checkbox
        select_all = st.checkbox("Select All Clips", value=True)
        
        # Clip display
        for idx, clip in enumerate(st.session_state.clips):
            with st.expander(f"Clip {idx+1}: {clip['start']}-{clip['end']}s"):
                col1, col2 = st.columns([1, 4])
                
                with col1:
                    selected = st.checkbox(
                        f"Include clip {idx+1}",
                        value=select_all,
                        key=f"clip_{idx}"
                    )
                    if selected:
                        st.session_state.selected_clips.add(idx)
                    else:
                        st.session_state.selected_clips.discard(idx)
                    
                    st.write(f"**Attention:** {clip['attention']}%")
                    st.write(f"**Duration:** {clip['end'] - clip['start']}s")
                
                with col2:
                    try:
                        with open(clip['path'], "rb") as f:
                            st.video(f.read())
                    except Exception as e:
                        st.error(f"Failed to load clip: {str(e)}")
        
        # Download button
        if st.session_state.zip_data:
            st.download_button(
                label="Download Selected Clips",
                data=st.session_state.zip_data,
                file_name="video_clips.zip",
                mime="application/zip"
            )

if __name__ == "__main__":
    # Run async main flow
    asyncio.run(main_async_flow())
