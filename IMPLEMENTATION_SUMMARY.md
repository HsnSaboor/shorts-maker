# Hybrid Architecture - Implementation Summary

## ✅ What Was Built

### Architecture Decision: **rclone** (Recommended)

After researching Google Workspace CLI (gws), rclone, gdrive, and the Traditional Google Python API, **rclone** was selected for these reasons:

- **Battle-tested**: 10+ years, millions of users
- **Perfect for 50-200MB uploads**: Built-in chunking, retry, resume
- **Zero maintenance**: Single binary, no boilerplate code
- **Headless-friendly**: OAuth token transfer is seamless
- **Simple integration**: `subprocess.run(['rclone', 'copy', ...])`

### Files Created

1. **`vps_server.py`** - FastAPI server for VPS
   - Endpoint: `POST /api/v1/process`
   - Background task processing
   - Full pipeline: Download → Transcribe → Score → Render → Upload → Cleanup
   - Uses rclone for Google Drive uploads

2. **`command_center.py`** - Local command center CLI
   - `submit` command: Send jobs to VPS
   - `watch` command: Monitor Google Drive for completed jobs
   - Rich tables and interactive prompts
   - Auto-move files to CapCut project folder

3. **`config.py`** - Updated configuration
   - Added `VPS_HOST`
   - Added `GDRIVE_REMOTE_NAME`
   - Added `GDRIVE_LOCAL_SYNC_PATH`

4. **`test_setup.py`** - Setup verification script
   - Checks rclone installation
   - Validates Python dependencies
   - Verifies environment variables
   - Tests VPS connectivity

5. **`SETUP.md`** - Complete setup guide
   - Step-by-step rclone configuration
   - OAuth setup and credential transfer
   - Environment variable configuration
   - Usage examples and troubleshooting

6. **`.env.example`** - Environment template
   - All required variables documented

7. **`requirements.txt`** - Updated dependencies
   - Added fastapi, uvicorn, watchdog

### Files Modified

1. **`config.py:21-28`** - Added VPS and Google Drive configuration
2. **`requirements.txt:8-10`** - Added new dependencies
3. **`phase5_render.py:1-188`** - Already simplified (no smart crop, no captions)
4. **`pipeline.py:1-176`** - Already exports metadata and words JSON

---

## 📋 Setup Checklist

### Test Results (from `python test_setup.py --skip-vps`)

**✅ Working:**
- rclone is installed
- Python packages: httpx, rich, fastapi, uvicorn
- Directories: temp/, output/, rules/, projects/

**❌ Needs Configuration:**
1. **rclone gdrive remote** - Run `rclone config` to set up OAuth
2. **watchdog package** - Run `pip install watchdog`
3. **deepgram package** - Run `pip install deepgram-sdk` (already in requirements.txt)
4. **VPS_HOST** - Set in `.env` file (currently localhost)
5. **GDRIVE_LOCAL_SYNC_PATH** - Set to your Google Drive sync folder
6. **DEEPGRAM_API_KEYS** - Add your API keys to `.env`

---

## 🚀 Quick Start

### On Laptop:

```bash
# 1. Configure rclone (one-time setup)
rclone config
# Choose: n (new), name: gdrive, type: drive, scope: 1 (full access)
# Browser will open for OAuth login

# 2. Install missing dependencies
pip install watchdog deepgram-sdk

# 3. Create .env file
cp .env.example .env
# Edit .env:
#   VPS_HOST=http://your-vps-ip:8000
#   GDRIVE_LOCAL_SYNC_PATH=/Users/yourname/Google Drive/shorts-maker
#   DEEPGRAM_API_KEYS=key1,key2,key3

# 4. Verify setup
python test_setup.py

# 5. Submit a job
python command_center.py submit https://youtube.com/watch?v=VIDEO_ID username

# 6. Watch for results
python command_center.py watch
```

### On VPS:

```bash
# 1. Copy rclone config from laptop
scp ~/.config/rclone/rclone.conf user@vps:~/.config/rclone/

# 2. Install dependencies
pip install -r requirements.txt

# 3. Create .env file
cp .env.example .env
# Edit .env:
#   GDRIVE_REMOTE_NAME=gdrive
#   DEEPGRAM_API_KEYS=key1,key2,key3
#   LOCAL_LLM_URL=http://localhost:8317/v1/chat/completions

# 4. Verify setup
python test_setup.py --skip-vps

# 5. Start server
python vps_server.py
# Or background: nohup python vps_server.py > vps.log 2>&1 &
```

---

## 🔄 Workflow

```
1. SUBMIT (Laptop)
   python command_center.py submit <url> <username>
   ↓
2. PROCESS (VPS)
   Download → Transcribe → Score → Render → Upload
   ↓
3. SYNC (Google Drive)
   Files appear in ~/Google Drive/shorts-maker/
   ↓
4. WATCH (Laptop)
   python command_center.py watch
   Displays results, prompts to move to CapCut folder
   ↓
5. EDIT (CapCut)
   Manual captions, face tracking, 9:16 cropping
```

---

## 📦 Output Structure

Each job creates a folder in Google Drive:

```
{username}_{video_id}/
├── candidate_1_viral-title.mp4      # Raw 16:9 video
├── candidate_1_viral-title_metadata.json  # Virality scores, hook, duration
├── candidate_1_viral-title_words.json     # Deepgram transcription
├── candidate_2_viral-title.mp4
├── candidate_2_viral-title_metadata.json
└── candidate_2_viral-title_words.json
```

---

## 🎯 Key Features

✅ **Lean Pipeline** - No captions, no face detection, no 9:16 cropping  
✅ **Decoupled Processing** - Submit multiple jobs, VPS processes asynchronously  
✅ **Zero Boilerplate** - rclone handles OAuth, retry, upload  
✅ **Audit-Ready Metadata** - Every clip has virality scores and reasoning  
✅ **Auto-Cleanup** - VPS deletes local files after upload  
✅ **Beautiful CLI** - Rich tables, panels, interactive prompts  
✅ **Watchdog Monitoring** - Auto-detects new jobs in Google Drive  

---

## 📖 Documentation

- **`SETUP.md`** - Complete setup guide with troubleshooting
- **`test_setup.py`** - Run to verify your configuration
- **`.env.example`** - Template for environment variables

---

## ⚠️ Important Notes

1. **rclone OAuth expires** - If uploads fail, re-run `rclone config` on laptop and transfer to VPS
2. **Google Drive Desktop** - Must be installed and syncing for `watch` command to work
3. **VPS firewall** - Ensure port 8000 is accessible from your laptop
4. **Deepgram keys** - Use comma-separated list for automatic rotation
5. **Pipeline is lean** - All visual editing (captions, cropping) done manually in CapCut

---

## 🔧 Next Steps

1. Run `rclone config` on your laptop
2. Install missing packages: `pip install watchdog deepgram-sdk`
3. Create `.env` file with your settings
4. Run `python test_setup.py` to verify
5. Transfer rclone config to VPS
6. Start VPS server: `python vps_server.py`
7. Submit your first job!

For detailed instructions, see **SETUP.md**.
