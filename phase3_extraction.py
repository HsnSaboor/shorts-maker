import subprocess, os
from yt_dlp import YoutubeDL
from config import TEMP_DIR

def create_audio_chunks(audio_path, chunk_duration=3600, overlap=300):
    try: from pydub import AudioSegment
    except ImportError: return [{'path': audio_path, 'start': 0, 'end': None}]
    sound = AudioSegment.from_file(audio_path)
    total_ms, chunks, current_ms = len(sound), [], 0
    while current_ms < total_ms:
        start = current_ms
        end = min(current_ms + (chunk_duration * 1000), total_ms)
        if end - start < 30000: break
        path = f"{TEMP_DIR}/chunk_{len(chunks)}_{os.getpid()}.mp3"
        sound[start:end].export(path, format='mp3', bitrate='192k')
        chunks.append({'path': path, 'start': start/1000.0,
                       'end': end/1000.0, 'start_offset': start/1000.0})
        current_ms += (chunk_duration - overlap) * 1000
    return chunks

def download_video(video_id, skip_if_exists=False):
    out = f"{TEMP_DIR}/{video_id}.mp4"
    if skip_if_exists and os.path.exists(out): return out
    opts = {'format': 'bestvideo[height<=1080][vcodec^=avc1]+bestaudio[ext=m4a]/best[ext=mp4]',
            'outtmpl': out, 'merge_output_format': 'mp4', 'quiet': True}
    with YoutubeDL(opts) as ydl:
        ydl.download([f"https://www.youtube.com/watch?v={video_id}"])
    return out

def extract_segments(video_path, candidate, transcript, candidate_id):
    rough_cut = f"{TEMP_DIR}/rough_cut_{candidate_id}.mp4"
    audio_path = f"{TEMP_DIR}/audio_{candidate_id}.mp3"
    segments = []
    for seg in candidate['segments']:
        if '-' in str(seg): s_idx, e_idx = map(int, seg.split('-'))
        else: s_idx, e_idx = int(seg), int(seg)
        for idx in range(s_idx, e_idx + 1):
            if idx < len(transcript):
                segments.append((transcript[idx]['start'], transcript[idx]['end']))
    merged = []
    if segments:
        cur_s, cur_e = segments[0]
        for s, e in segments[1:]:
            if s <= cur_e + 0.5: cur_e = e
            else: merged.append((cur_s, cur_e)); cur_s, cur_e = s, e
        merged.append((cur_s, cur_e))
    
    # Software concat, then upload to VAAPI
    vf, af = [], []
    for i, (s, e) in enumerate(merged):
        vf.append(f"[0:v]trim=start={s}:end={e},setpts=PTS-STARTPTS[v{i}]")
        af.append(f"[0:a]atrim=start={s}:end={e},asetpts=PTS-STARTPTS[a{i}]")
    
    n = len(merged)
    v_con = "".join([f"[v{i}]" for i in range(n)])
    a_con = "".join([f"[a{i}]" for i in range(n)])
    
    # Concat in software, then upload to VAAPI in final step
    vf.append(f"{v_con}concat=n={n}:v=1:a=0,format=nv12,hwupload[vvout]")
    af.append(f"{a_con}concat=n={n}:v=0:a=1[outa]")

    # FFmpeg 8 fix: init_hw_device + filter_hw_device
    cmd = ["ffmpeg", "-y",
           "-init_hw_device", "vaapi=hw:/dev/dri/renderD128",
           "-filter_hw_device", "hw",
           "-i", video_path,
           "-filter_complex", ";".join(vf + af),
           "-map", "[vvout]", "-map", "[outa]",
           "-c:v", "h264_vaapi", "-qp", "24",
           "-c:a", "aac", "-b:a", "192k", rough_cut]
    
    subprocess.run(cmd, check=True)
    
    subprocess.run(["ffmpeg", "-y", "-i", rough_cut, "-vn", "-acodec", "libmp3lame",
                    "-b:a", "192k", audio_path], check=True, capture_output=True)
    return rough_cut, audio_path