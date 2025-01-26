import streamlit as st
import asyncio
import logging
import zipfile
import os
import nest_asyncio
from pathlib import Path
from typing import List, Dict
from bulk_processor import BulkProcessor

nest_asyncio.apply()

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
    
    session_defaults = {
        'processing': False,
        'progress': {'total': 0, 'steps': {}, 'zip': False},
        'logs': [],
        'results': None,
        'zip_path': None
    }
    
    for key, value in session_defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

    with st.sidebar:
        st.header("Settings")
        lang = st.text_input("Language Code", "en")
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
            sources += [s.strip() for s in text_input.split(',')]
        sources = [s.strip() for s in sources if s.strip()]

        if not sources:
            st.error("Please provide valid input sources")
            st.session_state.processing = False
            return

        log_handler = SessionStateHandler()
        log_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        logging.getLogger().addHandler(log_handler)

        try:
            # Create an async wrapper function
            async def async_wrapper():
                async def process():
                    processor = BulkProcessor(
                        concurrency=concurrency,
                        progress_callback=update_progress
                    )
                    results = await processor.process_sources(sources, lang, output_dir)
                    st.session_state.progress['total'] = results['total_processed']
                    zip_path = create_zip(output_dir)
                    st.session_state.progress['zip'] = True
                    st.session_state.results = results
                    st.session_state.zip_path = zip_path

                async def update_progress(step_type: str, index: int, progress: float):
                    try:
                        if step_type in ('video', 'audio'):
                            key = 'download'
                            current = st.session_state.progress['steps'].get(key, {}).get(index, {})
                            current[step_type] = progress
                            total_progress = (current.get('video', 0) + current.get('audio', 0)) / 2
                            if current.get('video', 0) >= 100 and current.get('audio', 0) >= 100:
                                total_progress = 100.0
                        else:
                            key = step_type
                            total_progress = progress

                        st.session_state.progress['steps'].setdefault(key, {})[index] = total_progress
                        st.experimental_rerun()
                    except Exception as e:
                        logging.error(f"Progress update failed: {str(e)}")

                await process()

            # Run the async wrapper with asyncio
            asyncio.run(async_wrapper())

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
                current_data = st.session_state.progress['steps'].get(step, {})
                if step == 'download':
                    completed = sum(1 for v in current_data.values() if v >= 100)
                    total = st.session_state.progress['total']
                    progress = completed / total if total > 0 else 0
                    label = f"📥 Download\n({completed}/{total} videos)"
                else:
                    completed = sum(1 for v in current_data.values() if v >= 100)
                    total = st.session_state.progress['total']
                    progress = completed / total if total > 0 else 0
                    label = f"📊 {step.capitalize()}\n({completed}/{total} videos)"
                
                st.progress(progress, text=label)

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
