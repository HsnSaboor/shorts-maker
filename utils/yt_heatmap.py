import json
import re

import httpx


_MARKERS_REGEX = re.compile(
    r'"markers":\s*(\[.*?\])\s*,\s*"?markersMetadata"?',
    re.DOTALL,
)


def _parse_markers_from_html(html):
    match = _MARKERS_REGEX.search(html)
    if not match:
        return []

    raw = match.group(1)
    try:
        return json.loads(raw.replace('\\"', '"'))
    except Exception:
        return []


def fetch_normalized_heatmap(video_id, timeout=20.0):
    """
    Fetch normalized YouTube Most Replayed markers.

    Returns:
        [
          {
            "start": float,
            "end": float,
            "duration": float,
            "intensity_norm": float
          }
        ]
    """
    url = f"https://www.youtube.com/watch?v={video_id}"
    response = httpx.get(
        url,
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=timeout,
        follow_redirects=True,
    )
    response.raise_for_status()

    markers = _parse_markers_from_html(response.text)
    results = []

    for marker in markers:
        renderer = marker.get("heatMarkerRenderer", marker)

        start_ms = renderer.get("startMillis")
        duration_ms = renderer.get("durationMillis")
        if start_ms is None or duration_ms is None:
            continue

        try:
            start = float(start_ms) / 1000.0
            duration = max(float(duration_ms) / 1000.0, 0.0)
            intensity = float(renderer.get("intensityScoreNormalized", 0.0))
        except Exception:
            continue

        intensity = max(0.0, min(1.0, intensity))

        results.append(
            {
                "start": start,
                "end": start + duration,
                "duration": duration,
                "intensity_norm": intensity,
            }
        )

    results.sort(key=lambda x: x["start"])
    return results
