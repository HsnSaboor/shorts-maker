# main.py (updated with folder creation)
import streamlit as st
import asyncio
import json
import logging
import zipfile
from pathlib import Path
from typing import List, Dict, Optional, Callable
import shutil
import os

from bulk_processor import BulkProcessor

os.system("playwright install")

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def ensure_directory_exists(path: str) -> Path:
    """Ensure directory exists, create if it doesn't"""
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    return path

def get_sources_from_input(text_input: str, uploaded_file) -> List[str]:
    """Extract sources from both text input and uploaded file"""
    sources = []
    
    if uploaded_file is not None:
        file_contents = uploaded_file.read().decode()
        sources += [line.strip() for line in file_contents.split('\n') if line.strip()]
    
    if text_input:
        sources += [src.strip() for src in text_input.split(',') if src.strip()]
    
    return list(set(sources))  # Remove duplicates

async def async_process_sources(processor, sources, lang, output_dir):
    """Wrapper for async processing"""
    return await processor.process_sources(sources, lang, output_dir)

def create_zip(output_dir: str) -> str:
    """Create zip file of all processed content"""
    zip_dir = ensure_directory_exists(os.path.join(output_dir, "zips"))
    zip_path = os.path.join(zip_dir, "clips_with_transcripts.zip")
    
    with zipfile.ZipFile(zip_path, 'w') as zipf:
        for root, _, files in os.walk(output_dir):
            for file in files:
                if file.endswith(('.mp4', '.json')):
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, output_dir)
                    zipf.write(file_path, arcname)
    return zip_path

def main():
    st.title("YouTube Bulk Video Clipper")
    st.markdown("Process multiple YouTube videos to extract high-attention clips with transcripts")

    # Sidebar for inputs
    with st.sidebar:
        st.header("Processing Settings")
        lang = st.text_input("Language Code", value="en")
        concurrency = st.slider("Concurrency Level", 1, 8, 4)
        output_dir = st.text_input("Output Directory", value="bulk_output")

    # Main content area
    col1, col2 = st.columns([3, 1])
    
    with col1:
        st.subheader("Input Sources")
        text_input = st.text_input("Enter comma-separated video IDs/URLs:")
        uploaded_file = st.file_uploader("Or upload a text file", type=["txt"])
        
        process_btn = st.button("Start Processing")

    # Initialize session state
    if 'processing' not in st.session_state:
        st.session_state.processing = False
    if 'results' not in st.session_state:
        st.session_state.results = None
    if 'zip_path' not in st.session_state:
        st.session_state.zip_path = None

    if process_btn and not st.session_state.processing:
        st.session_state.processing = True
        st.session_state.results = None
        st.session_state.zip_path = None
        
        sources = get_sources_from_input(text_input, uploaded_file)
        if not sources:
            st.error("Please provide valid input sources")
            st.session_state.processing = False
            return

        # Ensure output directory exists
        try:
            output_path = ensure_directory_exists(output_dir)
            temp_dir = ensure_directory_exists(os.path.join(output_dir, "temp"))
            logs_dir = ensure_directory_exists(os.path.join(output_dir, "logs"))
        except Exception as e:
            st.error(f"Failed to create directories: {str(e)}")
            st.session_state.processing = False
            return

        processor = BulkProcessor(concurrency=concurrency)

        # Create progress bars
        overall_progress = st.progress(0)
        status_text = st.empty()

        try:
            results = asyncio.run(
                async_process_sources(processor, sources, lang, str(output_path))
            )
            
            st.session_state.results = results
            zip_path = create_zip(output_dir)
            st.session_state.zip_path = zip_path
            
            status_text.success("Processing complete!")
            overall_progress.progress(100)
            
        except Exception as e:
            st.error(f"Processing failed: {str(e)}")
        finally:
            st.session_state.processing = False

    if st.session_state.results:
        with col2:
            st.subheader("Processing Summary")
            st.metric("Total Processed", st.session_state.results['total_processed'])
            st.metric("Success Count", st.session_state.results['success_count'])
            st.metric("Failure Count", st.session_state.results['failure_count'])
            st.metric("Success Rate", f"{st.session_state.results['success_rate']:.1f}%")
            
            if st.session_state.zip_path:
                with open(st.session_state.zip_path, "rb") as f:
                    st.download_button(
                        label="Download All Clips + Transcripts",
                        data=f,
                        file_name="clips_with_transcripts.zip",
                        mime="application/zip"
                    )

        st.subheader("Processed Clips")
        for success in st.session_state.results['success']:
            video_dir = Path(success['clip_dir'])
            clips = list(video_dir.glob("*.mp4"))
            
            st.markdown(f"### Video ID: {success['video_id']}")
            st.caption(f"Clips created: {len(clips)}")
            
            cols = st.columns(3)
            for idx, clip_path in enumerate(clips):
                with cols[idx % 3]:
                    st.video(str(clip_path))
                    
                    transcript_path = video_dir.parent / "clip_transcripts.json"
                    with open(transcript_path) as f:
                        transcripts = json.load(f)
                    
                    clip_transcript = transcripts[idx]['transcript']
                    transcript_text = "\n".join(
                        [f"{t['start']:.1f}s: {t['text']}" for t in clip_transcript]
                    )
                    
                    # Download buttons
                    with open(clip_path, "rb") as f:
                        st.download_button(
                            label=f"Download Clip {idx+1}",
                            data=f,
                            file_name=clip_path.name,
                            mime="video/mp4"
                        )
                    
                    st.download_button(
                        label=f"Download Transcript {idx+1}",
                        data=transcript_text,
                        file_name=f"transcript_{idx+1}.txt",
                        mime="text/plain"
                    )

if __name__ == "__main__":
    main()
