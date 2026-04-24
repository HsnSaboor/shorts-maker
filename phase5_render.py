import os
import re
import subprocess

from config import OUTPUT_DIR, SILENCE_THRESHOLD_MAX, SILENCE_THRESHOLD_MIN


FADE_DURATION = 0.02


def calculate_silence_threshold(words):
    gaps = [
        words[i + 1]["start"] - words[i]["end"]
        for i in range(len(words) - 1)
        if words[i + 1]["start"] - words[i]["end"] > 0
    ]
    if not gaps:
        return SILENCE_THRESHOLD_MIN
    avg_gap = sum(gaps) / len(gaps)
    return max(SILENCE_THRESHOLD_MIN, min(SILENCE_THRESHOLD_MAX, avg_gap * 0.8))


def _build_keep_segments(words, edit_result):
    if isinstance(edit_result, dict):
        fillers = edit_result.get("word_indices_to_remove", [])
        trim_start = edit_result.get("trim_start_index", 0)
        trim_end = edit_result.get("trim_end_index", len(words))
        words = words[trim_start:trim_end]
    else:
        fillers = edit_result

    if not words:
        return []

    thresh = calculate_silence_threshold(words)
    cuts = set(fillers)
    for i in range(len(words) - 1):
        if (words[i + 1]["start"] - words[i]["end"]) > thresh:
            cuts.add(i)

    keep = []
    cur = 0
    for i in range(len(words)):
        if i in cuts:
            if i > cur:
                seg_end = max(words[cur]["start"] + 0.05, words[i]["end"] - FADE_DURATION)
                keep.append({"s": words[cur]["start"], "e": seg_end})
            cur = i + 1

    if cur < len(words):
        keep.append({"s": words[cur]["start"], "e": words[-1]["end"]})

    return keep


def _build_filter_complex(keep, use_vaapi):
    n = len(keep)
    v_filters = []
    a_filters = []

    for i, seg in enumerate(keep):
        start = float(seg["s"])
        end = float(seg["e"])
        duration = max(end - start, 0.01)
        fade_out_start = max(duration - FADE_DURATION, 0.0)

        v_filters.append(
            f"[0:v]trim=start={start:.6f}:end={end:.6f},setpts=PTS-STARTPTS[v{i}]"
        )
        a_filters.append(
            f"[0:a]atrim=start={start:.6f}:end={end:.6f},asetpts=PTS-STARTPTS,"
            f"afade=t=in:st=0:d={FADE_DURATION:.3f},"
            f"afade=t=out:st={fade_out_start:.6f}:d={FADE_DURATION:.3f}[a{i}]"
        )

    if n == 1:
        v_tail = [
            "[v0]format=nv12,hwupload=extra_hw_frames=64[vvout]"
            if use_vaapi
            else "[v0]format=yuv420p[vvout]"
        ]
        a_tail = ["[a0]loudnorm=I=-16[outa]"]
    else:
        v_inputs = "".join([f"[v{i}]" for i in range(n)])
        a_inputs = "".join([f"[a{i}]" for i in range(n)])

        v_tail = [f"{v_inputs}concat=n={n}:v=1:a=0[vcat]"]
        if use_vaapi:
            v_tail.append("[vcat]format=nv12,hwupload=extra_hw_frames=64[vvout]")
        else:
            v_tail.append("[vcat]format=yuv420p[vvout]")

        a_tail = [
            f"{a_inputs}concat=n={n}:v=0:a=1[acat]",
            "[acat]loudnorm=I=-16[outa]",
        ]

    return ";".join(v_filters + a_filters + v_tail + a_tail)


def render_final_video(
    rough_cut_path,
    words,
    edit_result,
    candidate_id,
    video_id=None,
    viral_title=None,
    video_output_dir=None,
    use_vaapi=True,
):
    output_base = video_output_dir or OUTPUT_DIR
    os.makedirs(output_base, exist_ok=True)

    if not os.path.exists(rough_cut_path):
        raise FileNotFoundError(f"Rough cut missing: {rough_cut_path}")

    keep = _build_keep_segments(words, edit_result)
    if not keep:
        raise ValueError("No keep segments generated from edit output")

    clean_title = re.sub(r"[^\w\s-]", "", viral_title or "clip").strip().replace(" ", "-").lower()[:40]
    output_filename = f"cid{candidate_id}_{clean_title}.mp4"
    out = f"{output_base}/{output_filename}"

    filter_complex = _build_filter_complex(keep, use_vaapi=use_vaapi)

    if use_vaapi:
        print("🚀 Rendering with VAAPI (h264_vaapi)")
        cmd = [
            "ffmpeg",
            "-y",
            "-init_hw_device",
            "vaapi=hw:/dev/dri/renderD128",
            "-filter_hw_device",
            "hw",
            "-i",
            rough_cut_path,
            "-filter_complex",
            filter_complex,
            "-map",
            "[vvout]",
            "-map",
            "[outa]",
            "-c:v",
            "h264_vaapi",
            "-qp",
            "24",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-movflags",
            "+faststart",
            out,
        ]
    else:
        print("🎛️ Rendering with software encoder (libx264)")
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            rough_cut_path,
            "-filter_complex",
            filter_complex,
            "-map",
            "[vvout]",
            "-map",
            "[outa]",
            "-c:v",
            "libx264",
            "-preset",
            "superfast",
            "-crf",
            "21",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-movflags",
            "+faststart",
            out,
        ]

    subprocess.run(cmd, check=True)
    return out
