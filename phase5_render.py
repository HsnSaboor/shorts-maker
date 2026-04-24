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


def map_keep_to_source_segments(keep_segments, source_segments):
    """
    Map keep ranges from candidate timeline into source video timeline.
    """
    if not keep_segments:
        return []
    if not source_segments:
        return [
            {"s": float(seg["s"]), "e": float(seg["e"])}
            for seg in keep_segments
            if float(seg["e"]) > float(seg["s"])
        ]

    mapped = []
    for keep in keep_segments:
        keep_s = float(keep["s"])
        keep_e = float(keep["e"])
        if keep_e <= keep_s:
            continue

        for src in source_segments:
            t_s = float(src["timeline_start"])
            t_e = float(src["timeline_end"])
            overlap_s = max(keep_s, t_s)
            overlap_e = min(keep_e, t_e)
            if overlap_e <= overlap_s:
                continue

            mapped.append(
                {
                    "s": float(src["source_start"]) + (overlap_s - t_s),
                    "e": float(src["source_start"]) + (overlap_e - t_s),
                }
            )

    if not mapped:
        return []

    merged = []
    mapped.sort(key=lambda x: x["s"])
    cur = mapped[0]
    for seg in mapped[1:]:
        if seg["s"] <= cur["e"] + 0.001:
            cur["e"] = max(cur["e"], seg["e"])
        else:
            merged.append(cur)
            cur = seg
    merged.append(cur)
    return merged


def _build_filter_complex(keep, use_vaapi, decode_is_hw=False):
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
        if use_vaapi:
            if decode_is_hw:
                v_tail = ["[v0]null[vvout]"]
            else:
                v_tail = ["[v0]format=nv12,hwupload=extra_hw_frames=64[vvout]"]
        else:
            v_tail = ["[v0]format=yuv420p[vvout]"]
        a_tail = ["[a0]loudnorm=I=-16[outa]"]
    else:
        v_inputs = "".join([f"[v{i}]" for i in range(n)])
        a_inputs = "".join([f"[a{i}]" for i in range(n)])

        if use_vaapi:
            if decode_is_hw:
                v_tail = [f"{v_inputs}concat=n={n}:v=1:a=0[vvout]"]
            else:
                v_tail = [
                    f"{v_inputs}concat=n={n}:v=1:a=0[vcat]",
                    "[vcat]format=nv12,hwupload=extra_hw_frames=64[vvout]",
                ]
        else:
            v_tail = [
                f"{v_inputs}concat=n={n}:v=1:a=0[vcat]",
                "[vcat]format=yuv420p[vvout]",
            ]

        a_tail = [
            f"{a_inputs}concat=n={n}:v=0:a=1[acat]",
            "[acat]loudnorm=I=-16[outa]",
        ]

    return ";".join(v_filters + a_filters + v_tail + a_tail)


def render_final_video(
    input_video_path,
    words,
    edit_result,
    candidate_id,
    video_id=None,
    viral_title=None,
    video_output_dir=None,
    use_vaapi=True,
    source_segments=None,
    unique_suffix=0,
):
    output_base = video_output_dir or OUTPUT_DIR
    os.makedirs(output_base, exist_ok=True)

    if not os.path.exists(input_video_path):
        raise FileNotFoundError(f"Input video missing: {input_video_path}")

    keep_timeline = _build_keep_segments(words, edit_result)
    if not keep_timeline:
        raise ValueError("No keep segments generated from edit output")

    keep = map_keep_to_source_segments(keep_timeline, source_segments)
    if not keep:
        raise ValueError("No source-mapped keep segments generated from edit output")

    clean_title = re.sub(r"[^\w\s-]", "", viral_title or "clip").strip().replace(" ", "-").lower()[:40]
    suffix = f"-{unique_suffix}" if unique_suffix > 0 else ""
    output_filename = f"cid{candidate_id}{suffix}_{clean_title}.mp4"
    out = f"{output_base}/{output_filename}"

    decode_is_hw = use_vaapi
    filter_complex = _build_filter_complex(keep, use_vaapi=use_vaapi, decode_is_hw=decode_is_hw)

    if use_vaapi:
        print("🚀 Rendering with VAAPI (h264_vaapi)")
        cmd = [
            "ffmpeg",
            "-y",
            "-init_hw_device",
            "vaapi=hw:/dev/dri/renderD128",
            "-filter_hw_device",
            "hw",
            "-hwaccel",
            "vaapi",
            "-hwaccel_output_format",
            "vaapi",
            "-i",
            input_video_path,
            "-filter_complex",
            filter_complex,
            "-map",
            "[vvout]",
            "-map",
            "[outa]",
            "-c:v",
            "h264_vaapi",
            "-low_power",
            "1",
            "-compression_level",
            "1",
            "-rc_mode",
            "CQP",
            "-global_quality",
            "25",
            "-bf",
            "0",
            "-async_depth",
            "4",
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
            input_video_path,
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
