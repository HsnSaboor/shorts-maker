# app.py
import streamlit as st
import asyncio
import json
import logging
from pathlib import Path
import tempfile
import zipfile
import shutil
import base64
from typing import List, Dict
from bulk_processor import BulkProcessor

os.system("playwright install")

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Session state initialization
if 'processing' not in st.session_state:
    st.session_state.update({
        'processing': False,
        'results': None,
        'zip_path': None,
        'selected_clips': [],
        'all_checked': True
    })

def create_zip(output_dir: Path, selected_clips: List[Dict]) -> str:
    """Create ZIP archive of selected clips with metadata"""
    zip_path = output_dir.parent / "clips.zip"
    with zipfile.ZipFile(zip_path, 'w') as zipf:
        for clip in selected_clips:
            # Add video file
            zipf.write(clip['path'], arcname=Path(clip['path']).name)
            # Add metadata
            meta = {k: v for k, v in clip.items() if k != 'path'}
            zipf.writestr(f"{Path(clip['path']).stem}.json", json.dumps(meta))
    return str(zip_path)

async def async_processor(video_ids: List[str], lang: str, output_dir: str, transcript_enabled: bool, concurrency: int):
    """Async processing wrapper"""
    processor = BulkProcessor(concurrency=concurrency)
    return await processor.process_sources(video_ids, lang, output_dir, transcript_enabled)

def process_videos():
    """Main processing function"""
    with tempfile.TemporaryDirectory() as tmp_dir:
        output_dir = Path(tmp_dir) / "clips_output"
        output_dir.mkdir(exist_ok=True)
        
        try:
            # Run async processing
            results = asyncio.run(
                async_processor(
                    st.session_state.video_ids,
                    st.session_state.lang,
                    str(output_dir),
                    st.session_state.transcript_enabled,
                    st.session_state.concurrency
                )
            )
            
            # Collect all clips with metadata
            all_clips = []
            for success in results['success']:
                video_clips = json.loads((Path(success['clip_dir']) / "clip_metadata.json").read_text())
                for clip in video_clips:
                    clip['path'] = str(Path(success['clip_dir']) / clip['filename'])
                all_clips.extend(video_clips)
            
            # Store results in session state
            st.session_state.results = {
                'output_dir': output_dir,
                'clips': all_clips,
                'processing_report': results
            }
            
            # Create initial ZIP
            if all_clips:
                st.session_state.zip_path = create_zip(output_dir, all_clips)
                st.session_state.selected_clips = all_clips.copy()
            
        except Exception as e:
            st.error(f"Processing failed: {str(e)}")
            logger.error(f"Processing error: {str(e)}", exc_info=True)
        finally:
            st.session_state.processing = False

# UI Components
st.set_page_config(page_title="YouTube Bulk Clipper", layout="wide")
st.title("🎥 YouTube Bulk Video Clipper")

# Input Section
with st.expander("⚙️ Processing Settings", expanded=True):
    with st.form("input_form"):
        col1, col2 = st.columns(2)
        
        with col1:
            video_input = st.text_input(
                "Enter YouTube Video IDs (comma-separated):",
                help="Example: abc123,xYz456,qwe789"
            )
            uploaded_file = st.file_uploader(
                "Or upload TXT file with video IDs:",
                type=['txt']
            )
            
        with col2:
            st.session_state.concurrency = st.slider(
                "🚀 Concurrent Workers",
                1, 8, 4,
                help="Number of simultaneous processing jobs"
            )
            st.session_state.lang = st.selectbox(
                "🌍 Transcript Language",
                ['en', 'es', 'fr', 'de', 'ja', 'ko', 'zh'],
                index=0
            )
            st.session_state.transcript_enabled = st.checkbox(
                "📝 Enable Transcripts",
                value=True
            )
        
        if st.form_submit_button("🚀 Start Processing", disabled=st.session_state.processing):
            # Validate input
            video_ids = []
            if video_input:
                video_ids = [vid.strip() for vid in video_input.split(',') if vid.strip()]
            if uploaded_file:
                uploaded_ids = uploaded_file.getvalue().decode().splitlines()
                video_ids.extend([vid.strip() for vid in uploaded_ids if vid.strip()])
            
            if not video_ids:
                st.error("❌ No valid video IDs found")
                st.stop()
            
            # Update state
            st.session_state.update({
                'video_ids': video_ids,
                'processing': True,
                'results': None,
                'zip_path': None,
                'selected_clips': [],
                'all_checked': True
            })
            
            # Start processing
            process_videos()

# Processing Status
if st.session_state.processing:
    with st.status("🔨 Processing videos...", expanded=True) as status:
        st.write("Downloading and processing videos:")
        st.spinner(text="This might take several minutes depending on the number of videos")
    st.rerun()

# Results Display
if st.session_state.results and not st.session_state.processing:
    st.success("✅ Processing complete!")
    report = st.session_state.results['processing_report']
    
    # Statistics Cards
    with st.container():
        cols = st.columns(4)
        cols[0].metric("Total Videos", report['total_processed'])
        cols[1].metric("Successful Videos", report['success_count'])
        cols[2].metric("Generated Clips", len(st.session_state.results['clips']))
        cols[3].metric("Success Rate", f"{report['success_rate']:.1f}%")

    # Clip Selection
    st.subheader("🎬 Generated Clips")
    
    # Select all controls
    col1, col2 = st.columns([1, 3])
    with col1:
        new_all_checked = st.checkbox(
            "✔️ Select All Clips",
            value=st.session_state.all_checked,
            key='select_all'
        )
        if new_all_checked != st.session_state.all_checked:
            st.session_state.all_checked = new_all_checked
            st.session_state.selected_clips = st.session_state.results['clips'].copy() if new_all_checked else []
            st.rerun()
    
    # Clip Display Grid
    for idx, clip in enumerate(st.session_state.results['clips']):
        with st.container(border=True):
            cols = st.columns([1, 4, 1])
            
            # Video Preview
            with cols[0]:
                st.video(clip['path'])
            
            # Metadata
            with cols[1]:
                st.subheader(f"Clip {idx+1}")
                st.write(f"**Video ID:** {clip['video_id']}")
                st.write(f"**Start:** {clip['start']:.1f}s → **End:** {clip['end']:.1f}s")
                st.write(f"**Duration:** {clip['end'] - clip['start']:.1f}s")
                st.write(f"**Average Attention:** {clip['average_attention']:.1f}%")
                if st.session_state.transcript_enabled:
                    st.write(f"**Word Count:** {clip.get('word_count', 0)}")
            
            # Selection Checkbox
            with cols[2]:
                is_checked = clip in st.session_state.selected_clips
                checked = st.checkbox(
                    "Include in ZIP",
                    value=is_checked,
                    key=f"clip_{idx}",
                    disabled=st.session_state.all_checked
                )
                
                if checked != is_checked:
                    if checked:
                        st.session_state.selected_clips.append(clip)
                    else:
                        st.session_state.selected_clips.remove(clip)
                    st.rerun()

    # ZIP Download
    if st.session_state.zip_path and st.session_state.selected_clips:
        st.divider()
        with st.container():
            cols = st.columns(3)
            cols[1].subheader("📥 Download Results")
            
            # Create fresh ZIP with selected clips
            final_zip = create_zip(
                Path(st.session_state.results['output_dir']),
                st.session_state.selected_clips
            )
            
            with open(final_zip, "rb") as f:
                cols[1].download_button(
                    label=f"Download {len(st.session_state.selected_clips)} Selected Clips",
                    data=f,
                    file_name="youtube_clips.zip",
                    mime="application/zip",
                    use_container_width=True
                )
    else:
        st.warning("⚠️ No clips selected for download")
