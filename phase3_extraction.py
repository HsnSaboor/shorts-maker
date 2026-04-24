import os
import subprocess
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

def download_video(video_id, skip_if_exists=False, cookies_file=None):
    out = f"{TEMP_DIR}/{video_id}.mp4"
    if skip_if_exists and os.path.exists(out): return out
    
    opts = {
        'format': 'bestvideo[height<=1080][vcodec^=avc1]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'outtmpl': out, 
        'merge_output_format': 'mp4', 
        'quiet': True,
        'verbose': False,
        'remote_components': 'ejs:npm',
    }
    if cookies_file and os.path.exists(cookies_file):
        opts['cookiefile'] = cookies_file
    
    with YoutubeDL(opts) as ydl:
        ydl.download([f"https://www.youtube.com/watch?v={video_id}"])
    return out


def resolve_candidate_segments(candidate, transcript, merge_gap=0.5):
    segments = []
    for seg in candidate["segments"]:
        if "-" in str(seg):
            s_idx, e_idx = map(int, str(seg).split("-"))
        else:
            s_idx, e_idx = int(seg), int(seg)

        for idx in range(s_idx, e_idx + 1):
            if 0 <= idx < len(transcript):
                segments.append((float(transcript[idx]["start"]), float(transcript[idx]["end"])))

    if not segments:
        return []

    segments.sort(key=lambda x: x[0])
    merged = []
    cur_s, cur_e = segments[0]
    for s, e in segments[1:]:
        if s <= cur_e + merge_gap:
            cur_e = max(cur_e, e)
        else:
            merged.append((cur_s, cur_e))
            cur_s, cur_e = s, e
    merged.append((cur_s, cur_e))

    timeline_segments = []
    timeline_pos = 0.0
    for src_start, src_end in merged:
        duration = max(src_end - src_start, 0.01)
        timeline_segments.append({
            "source_start": src_start,
            "source_end": src_end,
            "timeline_start": timeline_pos,
            "timeline_end": timeline_pos + duration,
        })
        timeline_pos += duration

    return timeline_segments


def extract_candidate_audio(video_path, source_segments, candidate_id, bitrate="192k"):
    if not source_segments:
        raise ValueError("No source segments provided for candidate audio extraction")

    audio_path = f"{TEMP_DIR}/audio_{candidate_id}.mp3"
    n = len(source_segments)

    af = []
    for i, seg in enumerate(source_segments):
        af.append(
            f"[0:a]atrim=start={seg['source_start']:.6f}:end={seg['source_end']:.6f},"
            f"asetpts=PTS-STARTPTS[a{i}]"
        )

    if n == 1:
        af.append("[a0]anull[outa]")
    else:
        a_inputs = "".join([f"[a{i}]" for i in range(n)])
        af.append(f"{a_inputs}concat=n={n}:v=0:a=1[outa]")

    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-filter_complex", ";".join(af),
        "-map", "[outa]",
        "-acodec", "libmp3lame",
        "-b:a", bitrate,
        audio_path,
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return audio_path

def extract_segments(video_path, candidate, transcript, candidate_id):
    rough_cut = f"{TEMP_DIR}/rough_cut_{candidate_id}.mp4"
    audio_path = f"{TEMP_DIR}/audio_{candidate_id}.mp3"
    source_segments = resolve_candidate_segments(candidate, transcript)
    merged = [(s["source_start"], s["source_end"]) for s in source_segments]
    
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
