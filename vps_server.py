#!/usr/bin/env python3
"""
VPS Harvester Server - FastAPI endpoint for remote video processing
Handles: Download -> Transcribe -> Score -> Upload to GDrive -> Cleanup
"""
import os
import json
import shutil
import subprocess
from pathlib import Path
from typing import Dict, Any
from fastapi import FastAPI, BackgroundTasks, HTTPException
from pydantic import BaseModel
from phase1_miner import mine_candidates
from phase2_editor import identify_fillers
from phase3_extraction import download_video, extract_segments
from phase4_deepgram import transcribe_with_deepgram, merge_chunked_transcriptions
from config import TEMP_DIR, OUTPUT_DIR, GDRIVE_REMOTE_NAME

app = FastAPI(title="Shorts Maker VPS Harvester")

class ProcessRequest(BaseModel):
    video_url: str
    username: str
    campaign_config: Dict[str, Any] = {}

class ProcessResponse(BaseModel):
    job_id: str
    status: str
    message: str

def extract_video_id(url_or_id: str) -> str:
    if 'youtube.com' in url_or_id or 'youtu.be' in url_or_id:
        if 'v=' in url_or_id:
            return url_or_id.split('v=')[1].split('&')[0]
        elif 'youtu.be/' in url_or_id:
            return url_or_id.split('youtu.be/')[1].split('?')[0]
    return url_or_id

def upload_to_gdrive(local_path: str, remote_folder: str) -> bool:
    """Upload file/folder to Google Drive using rclone"""
    try:
        cmd = [
            'rclone', 'copy',
            local_path,
            f'{GDRIVE_REMOTE_NAME}:{remote_folder}',
            '--progress'
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        return result.returncode == 0
    except Exception as e:
        print(f"Upload failed: {e}")
        return False

def process_video_job(video_url: str, username: str, campaign_config: Dict[str, Any]):
    """Background task: Full pipeline execution"""
    video_id = extract_video_id(video_url)
    job_folder = f"{username}_{video_id}"
    
    try:
        print(f"[JOB START] {job_folder}")
        
        # Phase 1: Mine candidates
        print(f"[PHASE 1] Mining candidates from {video_id}")
        candidates, transcript, config = mine_candidates(video_id, username)
        print(f"[PHASE 1] Found {len(candidates)} candidates")
        
        if not candidates:
            print(f"[JOB FAILED] No candidates found")
            return
        
        # Process each candidate
        for candidate in candidates:
            cid = candidate['candidate_id']
            print(f"[CANDIDATE {cid}] Processing...")
            
            # Phase 3: Download and extract
            print(f"[PHASE 3] Downloading video")
            video_path = download_video(video_id)
            rough_cut, audio_path = extract_segments(video_path, candidate, transcript, cid)
            
            # Phase 4: Transcribe with Deepgram
            print(f"[PHASE 4] Transcribing audio")
            deepgram_result = transcribe_with_deepgram(audio_path)
            words = deepgram_result['words']
            
            # Phase 2: Identify fillers
            print(f"[PHASE 2] Identifying filler words")
            edit_result = identify_fillers(words, cid, username=None)
            
            # Phase 5: Render final video (16:9 raw)
            print(f"[PHASE 5] Rendering final video")
            from phase5_render import render_final_video
            output_path = render_final_video(
                rough_cut, words, edit_result, cid, 
                candidate.get('viral_title', 'Untitled')
            )
            
            # Export metadata
            metadata = {
                'candidate_id': cid,
                'hook': candidate['hook_summary'],
                'duration': candidate['duration'],
                'virality': candidate.get('virality', {}),
                'viral_title': candidate.get('viral_title', 'Untitled'),
                'words': words,
                'filler_indices': filler_indices
            }
            
            metadata_path = output_path.replace('.mp4', '_metadata.json')
            with open(metadata_path, 'w') as f:
                json.dump(metadata, f, indent=2)
            
            words_path = output_path.replace('.mp4', '_words.json')
            with open(words_path, 'w') as f:
                json.dump({'words': words}, f, indent=2)
            
            print(f"[CANDIDATE {cid}] Rendered: {output_path}")
        
        # Upload to Google Drive
        print(f"[UPLOAD] Uploading to Google Drive: {job_folder}")
        success = upload_to_gdrive(OUTPUT_DIR, job_folder)
        
        if success:
            print(f"[UPLOAD] Success!")
            # Cleanup local files
            print(f"[CLEANUP] Removing local files")
            shutil.rmtree(TEMP_DIR, ignore_errors=True)
            shutil.rmtree(OUTPUT_DIR, ignore_errors=True)
            os.makedirs(TEMP_DIR, exist_ok=True)
            os.makedirs(OUTPUT_DIR, exist_ok=True)
            print(f"[JOB COMPLETE] {job_folder}")
        else:
            print(f"[UPLOAD FAILED] Files remain in {OUTPUT_DIR}")
            
    except Exception as e:
        print(f"[JOB FAILED] {job_folder}: {e}")
        import traceback
        traceback.print_exc()

@app.post("/api/v1/process", response_model=ProcessResponse)
async def process_video(request: ProcessRequest, background_tasks: BackgroundTasks):
    """
    Submit a video for processing on the VPS.
    Returns immediately with job_id. Processing happens in background.
    """
    video_id = extract_video_id(request.video_url)
    job_id = f"{request.username}_{video_id}"
    
    # Validate inputs
    if not request.video_url:
        raise HTTPException(status_code=400, detail="video_url is required")
    if not request.username:
        raise HTTPException(status_code=400, detail="username is required")
    
    # Queue background task
    background_tasks.add_task(
        process_video_job,
        request.video_url,
        request.username,
        request.campaign_config
    )
    
    return ProcessResponse(
        job_id=job_id,
        status="queued",
        message=f"Job {job_id} queued for processing"
    )

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "vps-harvester"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
