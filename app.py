import nest_asyncio
nest_asyncio.apply()
import streamlit as st
import asyncio
import logging
import zipfile
import os
from pathlib import Path
from typing import List, Dict
from bulk_processor import BulkProcessor

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

class SessionStateHandler(logging.Handler):
    def emit(self, record):
        log_entry = self.format(record)
        if 'logs' not in st.session_state:
            st.session_state.logs = []
        st.session_state.logs.append(log_entry)

def format_size(size_bytes: int) -> str:
    """Convert bytes to human-readable format"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.2f} GB"

def create_zip(output_dir: str) -> str:
    """Create ZIP archive with progress tracking"""
    zip_path = os.path.join(output_dir, "clips_with_transcripts.zip")
    total_size = 0
    
    with zipfile.ZipFile(zip_path, 'w') as zipf:
        for root, _, files in os.walk(output_dir):
            for file in files:
                if file.endswith(('.mp4', '.json', '.svg')):
                    file_path = os.path.join(root, file)
                    relative_path = os.path.relpath(file_path, output_dir)
                    zipf.write(file_path, relative_path)
                    file_size = os.path.getsize(file_path)
                    total_size += file_size
                    logger.info(f"Added {relative_path} ({format_size(file_size)})")
    
    zip_size = os.path.getsize(zip_path)
    logger.info(f"ZIP created: {format_size(zip_size)}")
    return zip_path

def main():
    st.title("YouTube Bulk Video Processor")
    
    # Initialize session state
    if 'processing' not in st.session_state:
        st.session_state.processing = False
    if 'progress' not in st.session_state:
        st.session_state.progress = {
            'total': 0,
            'steps': {},
            'zip': False
        }
    if 'logs' not in st.session_state:
        st.session_state.logs = []

    # Sidebar controls
    with st.sidebar:
        st.header("Settings")
        lang = st.text_input("Language Code", "en")
        concurrency = st.slider("Concurrency Level", 1, 8, 4)
        output_dir = st.text_input("Output Directory", "processed_videos")
        process_btn = st.button("Start Processing")

    # Main interface
    col1, col2 = st.columns([3, 1])
    
    with col1:
        st.subheader("Input Sources")
        text_input = st.text_input("Enter YouTube URLs/IDs (comma-separated):")
        uploaded_file = st.file_uploader("Or upload text file", type=["txt"])

    # Processing controls
    if process_btn and not st.session_state.processing:
        st.session_state.processing = True
        st.session_state.logs = []
        sources = []
        
        if uploaded_file:
            sources += uploaded_file.read().decode().splitlines()
        if text_input:
            sources += text_input.split(',')
        sources = [s.strip() for s in sources if s.strip()]

        if not sources:
            st.error("Please provide valid input sources")
            st.session_state.processing = False
            return

        # Setup progress tracking
        st.session_state.progress = {
            'total': 0,
            'steps': {},
            'zip': False
        }

        # Add custom logging handler
        log_handler = SessionStateHandler()
        log_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        logging.getLogger().addHandler(log_handler)

        try:
            async def process_wrapper():
                processor = BulkProcessor(
                    concurrency=concurrency,
                    progress_callback=update_progress
                )
                results = await processor.process_sources(sources, lang, output_dir)
                zip_path = await asyncio.to_thread(create_zip, output_dir)
                st.session_state.progress['zip'] = True
                st.session_state.results = results
                st.session_state.zip_path = zip_path
            
            # Run the async loop correctly
            if process_btn and not st.session_state.processing:
                st.session_state.processing = True
                try:
                    asyncio.run(process_wrapper())
                finally:
                    st.session_state.processing = False

            async def update_progress(step_type: str, index: int, progress: float):
                """Update progress for individual video steps"""
                if step_type not in st.session_state.progress['steps']:
                    st.session_state.progress['steps'][step_type] = {}
                st.session_state.progress['steps'][step_type][index] = progress
                st.experimental_rerun()

            asyncio.run(process_wrapper())

        except Exception as e:
            logger.error(f"Processing failed: {str(e)}")
            st.error(f"Processing failed: {str(e)}")
        finally:
            logging.getLogger().removeHandler(log_handler)
            st.session_state.processing = False

    # Display progress
    if st.session_state.progress['total'] > 0:
        st.subheader("Processing Progress")
        
        # Individual step progress
        steps = ['download', 'transcript', 'heatmap', 'clips']
        cols = st.columns(len(steps))
        for idx, step in enumerate(steps):
            with cols[idx]:
                current = sum(1 for v in st.session_state.progress['steps'].get(step, {}).values() if v >= 100)
                total = st.session_state.progress['total']
                progress = current / total if total > 0 else 0
                st.progress(
                    progress,
                    text=f"📊 {step.capitalize()}\n({current}/{total} videos)"
                )

        # ZIP packaging
        st.progress(
            1.0 if st.session_state.progress['zip'] else 0,
            text="📦 ZIP Packaging: " + ("Done" if st.session_state.progress['zip'] else "Pending")
        )

    # Display logs
    if st.session_state.logs:
        with st.expander("Processing Logs"):
            st.code("\n".join(st.session_state.logs[-50:]))

    # Results display and download
    if st.session_state.get('zip_path'):
        st.subheader("Results")
        zip_size = format_size(os.path.getsize(st.session_state.zip_path))
        st.metric("Final ZIP Size", zip_size)
        
        with open(st.session_state.zip_path, "rb") as f:
            st.download_button(
                "📥 Download All Clips",
                data=f,
                file_name="clips_with_transcripts.zip",
                mime="application/zip"
            )

if __name__ == "__main__":
    main()
