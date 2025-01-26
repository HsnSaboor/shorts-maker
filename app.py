import streamlit as st
import logging
import zipfile
import os
from pathlib import Path
from typing import List, Dict
from bulk_processor import BulkProcessor

class SessionStateHandler(logging.Handler):
    def emit(self, record):
        log_entry = self.format(record)
        if 'logs' not in st.session_state:
            st.session_state.logs = []
        st.session_state.logs.append(log_entry)

def format_size(size_bytes: int) -> str:
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.2f} GB"

def create_zip(output_dir: str) -> str:
    zip_path = os.path.join(output_dir, "clips_with_transcripts.zip")
    with zipfile.ZipFile(zip_path, 'w') as zipf:
        for root, _, files in os.walk(output_dir):
            for file in files:
                if file.endswith(('.mp4', '.json', '.svg')):
                    file_path = os.path.join(root, file)
                    relative_path = os.path.relpath(file_path, output_dir)
                    zipf.write(file_path, relative_path)
    return zip_path

def main():
    st.title("YouTube Bulk Video Processor")
    
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

    with st.sidebar:
        st.header("Settings")
        include_transcripts = st.checkbox("Include Transcripts", value=True, help="Generate transcripts for video clips")
        lang = st.text_input("Language Code", "en", disabled=not include_transcripts)
        concurrency = st.slider("Concurrency Level", 1, 8, 4)
        output_dir = st.text_input("Output Directory", "processed_videos")
        process_btn = st.button("Start Processing")

    col1, col2 = st.columns([3, 1])
    
    with col1:
        st.subheader("Input Sources")
        text_input = st.text_input("Enter YouTube URLs/IDs (comma-separated):")
        uploaded_file = st.file_uploader("Or upload text file", type=["txt"])

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

        log_handler = SessionStateHandler()
        log_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        logging.getLogger().addHandler(log_handler)

        try:
            def update_progress(step_type: str, index: int, progress: float):
                if step_type not in st.session_state.progress['steps']:
                    st.session_state.progress['steps'][step_type] = {}
                st.session_state.progress['steps'][step_type][index] = progress
                st.rerun()
processor = BulkProcessor(
    concurrency=concurrency,
    progress_callback=update_progress,
    include_transcripts=include_transcripts
)
results = processor.process_sources(sources, lang if include_transcripts else None, output_dir)
            results = processor.process_sources(sources, lang, output_dir)
            zip_path = create_zip(output_dir)
            st.session_state.progress['zip'] = True
            st.session_state.results = results
            st.session_state.zip_path = zip_path

        except Exception as e:
            logging.error(f"Processing failed: {str(e)}")
            st.error(f"Processing failed: {str(e)}")
        finally:
            logging.getLogger().removeHandler(log_handler)
            st.session_state.processing = False

    if st.session_state.progress['total'] > 0:
        st.subheader("Processing Progress")
        
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

        st.progress(
            1.0 if st.session_state.progress['zip'] else 0,
            text="📦 ZIP Packaging: " + ("Done" if st.session_state.progress['zip'] else "Pending")
        )

    if st.session_state.logs:
        with st.expander("Processing Logs"):
            st.code("\n".join(st.session_state.logs[-50:]))

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
