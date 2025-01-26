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

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

class StreamlitLogHandler(logging.Handler):
    def emit(self, record):
        log_entry = self.format(record)
        st.code(log_entry, language="plaintext")

formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

# Add handlers
file_handler = logging.FileHandler('processing.log')
streamlit_handler = StreamlitLogHandler()

file_handler.setFormatter(formatter)
streamlit_handler.setFormatter(formatter)

logger.addHandler(file_handler)
logger.addHandler(streamlit_handler)

# Initialize session state
if 'processed' not in st.session_state:
    st.session_state.update({
        'processed': False,
        'clips': [],
        'selected_clips': set(),
        'zip_data': None,
        'log_messages': []
    })

def get_video_ids(input_text, uploaded_file):
    """Extract video IDs from text input or uploaded file"""
    video_ids = []
    if uploaded_file:
        try:
            text = uploaded_file.read().decode()
            video_ids.extend([vid.strip() for vid in text.split(',') if vid.strip()])
        except Exception as e:
            logger.error(f"File read error: {str(e)}")
    if input_text:
        video_ids.extend([vid.strip() for vid in input_text.split(',') if vid.strip()])
    return list(set(video_ids))

def create_zip(temp_dir):
    """Create in-memory ZIP file from processed files"""
    zip_buffer = io.BytesIO()
    try:
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for root, _, files in os.walk(temp_dir):
                for file in files:
                    file_path = Path(root) / file
                    if file_path.suffix in ('.mp4', '.json'):
                        arcname = file_path.relative_to(temp_dir)
                        zip_file.write(file_path, arcname=arcname)
                        logger.info(f"Added to ZIP: {arcname}")
    except Exception as e:
        logger.error(f"ZIP creation failed: {str(e)}")
    return zip_buffer.getvalue()

def main():
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
            with st.spinner("Processing videos..."), st.empty() as status_container:
                try:
                    # Create new event loop for async processing
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    
                    processor = BulkProcessor(concurrency=concurrency)
                    results = loop.run_until_complete(
                        processor.process_sources(
                            video_ids, lang, temp_dir, transcript_enabled
                        )
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
                    st.session_state.zip_data = create_zip(temp_dir)
                    st.session_state.processed = True
                    
                    logger.info(f"Processed {len(all_clips)} clips successfully")
                    status_container.success("Processing completed!")

                except Exception as e:
                    logger.error(f"Processing failed: {str(e)}", exc_info=True)
                    st.error(f"Processing error: {str(e)}")

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
    main()
