# Hybrid Architecture Setup Guide

## Architecture Overview

```
Local Laptop (Command Center)
    ↓ submit job
Remote VPS (Harvester)
    ↓ process & upload
Google Drive
    ↓ sync
Local Laptop (CapCut)
```

## Prerequisites

### On Your Laptop
1. Python 3.8+
2. Google Drive Desktop app (for auto-sync)
3. rclone installed and configured

### On Your VPS
1. Python 3.8+
2. rclone installed and configured
3. ffmpeg with hardware acceleration support

---

## Step 1: Install rclone

### On Laptop (macOS/Linux)
```bash
# macOS
brew install rclone

# Linux
curl https://rclone.org/install.sh | sudo bash
```

### On VPS (Linux)
```bash
curl https://rclone.org/install.sh | sudo bash
```

---

## Step 2: Configure rclone OAuth (Laptop Only)

Run this on your **laptop** (where you have a browser):

```bash
rclone config
```

Follow these steps:
1. Choose `n` for new remote
2. Name it: `gdrive`
3. Storage type: `drive` (Google Drive)
4. Leave Client ID and Secret blank (use defaults)
5. Scope: `1` (Full access)
6. Leave root_folder_id blank
7. Leave service_account_file blank
8. Auto config: `y` (Yes)
9. Browser will open - log in with your Google account
10. Not a Shared Drive: `n`
11. Confirm: `y`

This creates `~/.config/rclone/rclone.conf` with your OAuth token.

---

## Step 3: Transfer rclone Config to VPS

Copy the config file from your laptop to the VPS:

```bash
# On your laptop
scp ~/.config/rclone/rclone.conf user@your-vps-ip:~/.config/rclone/
```

Or manually copy the contents:
```bash
# On laptop
cat ~/.config/rclone/rclone.conf

# On VPS
mkdir -p ~/.config/rclone
nano ~/.config/rclone/rclone.conf
# Paste the contents and save
```

---

## Step 4: Test rclone on VPS

```bash
# On VPS
rclone lsd gdrive:
```

You should see your Google Drive folders. If you get an error, the OAuth token may have expired - repeat Step 2 on your laptop and transfer again.

---

## Step 5: Install Python Dependencies

### On Laptop
```bash
cd /path/to/shorts-maker
pip install -r requirements.txt
```

### On VPS
```bash
cd /path/to/shorts-maker
pip install -r requirements.txt
```

---

## Step 6: Configure Environment Variables

### On Laptop
Create `.env` file:
```bash
# VPS endpoint
VPS_HOST=http://your-vps-ip:8000

# Local Google Drive sync folder
GDRIVE_LOCAL_SYNC_PATH=/Users/yourname/Google Drive/shorts-maker

# Deepgram API keys (comma-separated for rotation)
DEEPGRAM_API_KEYS=key1,key2,key3
```

### On VPS
Create `.env` file:
```bash
# rclone remote name (must match Step 2)
GDRIVE_REMOTE_NAME=gdrive

# Deepgram API keys (comma-separated for rotation)
DEEPGRAM_API_KEYS=key1,key2,key3

# Local LLM endpoint
LOCAL_LLM_URL=http://localhost:8317/v1/chat/completions
LOCAL_LLM_MODEL=your-model-name
```

---

## Step 7: Start the VPS Server

On your VPS:
```bash
cd /path/to/shorts-maker
python vps_server.py
```

The server will start on `http://0.0.0.0:8000`

To run in background:
```bash
nohup python vps_server.py > vps_server.log 2>&1 &
```

---

## Step 8: Configure Google Drive Desktop (Laptop)

1. Install Google Drive Desktop app
2. Sign in with your Google account
3. In settings, choose "Mirror files" mode
4. Create a folder called `shorts-maker` in your Google Drive
5. This folder will auto-sync to your laptop

Update your `.env` to point to the synced folder:
```bash
GDRIVE_LOCAL_SYNC_PATH=/Users/yourname/Google Drive/shorts-maker
```

---

## Usage

### Submit a Job
```bash
python cli.py submit https://youtube.com/watch?v=VIDEO_ID username
```

### Watch for Completed Jobs
```bash
python cli.py watch
```

This will:
1. Monitor your Google Drive sync folder
2. Display results when jobs complete
3. Ask if you want to move files to CapCut project folder

---

## Workflow

1. **Submit** a video from your laptop → VPS starts processing
2. **VPS** downloads, transcribes, scores, renders, and uploads to Google Drive
3. **Google Drive** syncs the results to your laptop automatically
4. **Watch** command detects new files and displays results
5. **Move** files to CapCut project folder for manual editing

---

## Troubleshooting

### "rclone: command not found" on VPS
Install rclone: `curl https://rclone.org/install.sh | sudo bash`

### "Failed to create file system for gdrive"
Your OAuth token expired. Re-run `rclone config` on laptop and transfer to VPS.

### "Connection refused" when submitting job
Check VPS_HOST in your `.env` and ensure vps_server.py is running.

### Files not appearing in watch command
Check GDRIVE_LOCAL_SYNC_PATH points to your Google Drive sync folder.

---

## Security Notes

- The rclone config contains OAuth tokens - keep it secure
- Use SSH key authentication for VPS access
- Consider using a VPN or firewall rules to restrict VPS API access
- Rotate Deepgram API keys regularly
