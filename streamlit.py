import streamlit as st
import asyncio
import json
import logging
import zipfile
import os
from pathlib import Path
from typing import List, Dict, Optional
from bulk_processor import BulkProcessor

# Configure logging to show in Streamlit
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)


os.system("playwright install")

def ensure_directory(path: str) -> Path:
    """Create directory if it doesn't exist"""
    path_obj = Path(path)
    path_obj.mkdir(parents=True, exist_ok=True)
    return path_obj

def create_zip(output_dir: str) -> str:
    """Create ZIP archive with proper validation"""
    zip_path = os.path.join(output_dir, "clips_with_transcripts.zip")
    total_size = 0
    
    with zipfile.ZipFile(zip_path, 'w') as zipf:
        for root, _, files in os.walk(output_dir):
            for file in files:
                if file.endswith(('.mp4', '.json')):
                    file_path = os.path.join(root, file)
                    relative_path = os.path.relpath(file_path, output_dir)
                    zipf.write(file_path, relative_path)
                    total_size += os.path.getsize(file_path)
                    logger.info(f"Added to ZIP: {relative_path}")
    
    zip_size = os.path.getsize(zip_path)
    logger.info(f"ZIP creation complete. Size: {zip_size}")
    return zip_path

def format_size(size_bytes: int) -> str:
    """Convert bytes to human-readable format without external dependencies"""
    units = ["B", "KB", "MB", "GB", "TB"]
    unit_index = 0
    while size_bytes >= 1024 and unit_index < len(units)-1:
        size_bytes /= 1024
        unit_index += 1
    return f"{size_bytes:.2f} {units[unit_index]}"

def display_logs():
    """Show processing logs in Streamlit"""
    if st.session_state.get('logs'):
        with st.expander("Processing Logs"):
            st.code("\n".join(st.session_state.logs))

def main():
    st.title("YouTube Bulk Video Clipper")
    st.markdown("Extract high-attention clips with transcripts from multiple YouTube videos")
    
    # Session state initialization
    if 'processing' not in st.session_state:
        st.session_state.processing = False
    if 'results' not in st.session_state:
        st.session_state.results = None
    if 'zip_path' not in st.session_state:
        st.session_state.zip_path = None
    if 'logs' not in st.session_state:
        st.session_state.logs = []

    # Sidebar controls
    with st.sidebar:
        st.header("Settings")
        lang = st.text_input("Language Code", "en")
        concurrency = st.slider("Concurrency", 1, 8, 4)
        output_dir = st.text_input("Output Directory", "bulk_output")
        process_btn = st.button("Start Processing")

    # Main interface
    col1, col2 = st.columns([3, 1])
    
    with col1:
        st.subheader("Input Sources")
        text_input = st.text_input("Enter video IDs/URLs (comma-separated):")
        uploaded_file = st.file_uploader("Or upload text file", type=["txt"])

    # Processing logic
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

        try:
            # Setup directories
            output_path = ensure_directory(output_dir)
            processor = BulkProcessor(concurrency=concurrency)
            
            # Progress tracking
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            # Async processing
            results = asyncio.run(
                processor.process_sources(sources, lang, str(output_path))
            )
            
            # Create ZIP archive
            zip_path = create_zip(output_dir)
            st.session_state.zip_path = zip_path
            st.session_state.results = results
            
            # Final update
            progress_bar.progress(100)
            status_text.success("✅ Processing complete!")
            
        except Exception as e:
            logger.error(f"Processing failed: {str(e)}")
            st.error(f"Processing failed: {str(e)}")
        finally:
            st.session_state.processing = False

    # Results display
    if st.session_state.results:
        with col2:
            st.subheader("Summary")
            res = st.session_state.results
            st.metric("Total Videos", res['total_processed'])
            st.metric("Successful", res['success_count'])
            st.metric("Failed", res['failure_count'])
            st.metric("Success Rate", f"{res['success_rate']:.1f}%")
            
            if st.session_state.zip_path:
                zip_size = os.path.getsize(st.session_state.zip_path)
                st.metric("ZIP File Size", zip_size)
                with open(st.session_state.zip_path, "rb") as f:
                    st.download_button(
                        "📥 Download All",
                        data=f,
                        file_name="clips_with_transcripts.zip",
                        mime="application/zip"
                    )

        st.subheader("Generated Clips")
        for success in st.session_state.results['success']:
            video_dir = Path(success['clip_dir'])
            transcript_path = video_dir.parent / "clip_transcripts.json"
            
            with open(transcript_path) as f:
                transcripts = json.load(f)
            
            clips = list(video_dir.glob("*.mp4"))
            st.markdown(f"### Video ID: `{success['video_id']}`")
            
            cols = st.columns(3)
            for idx, (clip_path, transcript) in enumerate(zip(clips, transcripts)):
                with cols[idx % 3]:
                    # Clip metadata
                    start = transcript['start']
                    end = transcript['end']
                    duration = end - start
                    attention = transcript.get('average_attention', 'N/A')
                    
                    # Display card
                    with st.container(border=True):
                        st.video(str(clip_path))
                        st.caption(f"⏱️ {start:.1f}s - {end:.1f}s ({duration:.1f}s)")
                        st.caption(f"📈 Average Attention: {attention}%")
                        
                        # Download buttons
                        with open(clip_path, "rb") as f:
                            st.download_button(
                                f"📥 Clip {idx+1}",
                                data=f,
                                file_name=clip_path.name,
                                mime="video/mp4",
                                key=f"clip_{idx}"
                            )
                        
                        transcript_text = "\n".join(
                            [f"{t['start']:.1f}s: {t['text']}" for t in transcript['transcript']]
                        )
                        st.download_button(
                            f"📝 Transcript {idx+1}",
                            data=transcript_text,
                            file_name=f"transcript_{idx+1}.txt",
                            mime="text/plain",
                            key=f"trans_{idx}"
                        )

    # Display logs
    display_logs()

if __name__ == "__main__":
    main()
