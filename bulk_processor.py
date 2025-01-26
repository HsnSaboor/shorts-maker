import argparse
import asyncio
import json
import logging
import random
import re
from typing import Dict, List, Optional, Any
from xml.etree import ElementTree as ET
from copy import deepcopy
from lxml import html, etree
from playwright.async_api import async_playwright

# Configure logging
logging.basicConfig(level=logging.INFO)

# Predefined configurations
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OeS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/91.0.864.59 Safari/537.36"
]

RESOLUTIONS = [
    {"width": 1024, "height": 768},
    {"width": 1280, "height": 720},
    {"width": 1366, "height": 768},
    {"width": 1440, "height": 900},
    {"width": 1600, "height": 900}
]

BROWSERS = ["chromium"]


async def extract_heatmap_svgs(page):
    """Extracts and combines heatmap SVGs from the YouTube player."""
    try:
        logging.info("Waiting for network idle state...")
        await page.wait_for_load_state("networkidle", timeout=30000)
        logging.info("Network idle state reached.")
    except Exception as e:
        logging.error(f"Timeout waiting for network idle: {e}")
        return None

    try:
        logging.info("Waiting for heatmap container...")
        await page.wait_for_selector("div.ytp-heat-map-container", state="attached", timeout=30000)
    except Exception as e:
        logging.error(f"Heatmap container not found: {e}")
        return None

    try:
        logging.info("Extracting heatmap container...")
        heatmap_container = await page.query_selector("div.ytp-heat-map-container")
        if not heatmap_container:
            logging.error("Heatmap container not found.")
            return None

        container_html = await heatmap_container.inner_html()
        tree = html.fromstring(container_html)
        heatmap_elements = tree.xpath('//div[@class="ytp-heat-map-chapter"]/svg')
        if not heatmap_elements:
            logging.error("No SVG elements found in heatmap.")
            return None

        logging.info(f"Found {len(heatmap_elements)} SVG elements.")
        total_width = sum(get_pixel_value(elem.attrib.get("width", "0")) for elem in heatmap_elements)
        total_height = max(get_pixel_value(elem.attrib.get("height", "0")) for elem in heatmap_elements)
        logging.info(f"Combined SVG dimensions: {total_width}x{total_height}")

        combined_svg = etree.Element("svg", {
            "xmlns": "http://www.w3.org/2000/svg",
            "width": f"{total_width}",
            "height": f"{total_height}",
            "viewBox": f"0 0 {total_width} {total_height}"
        })

        current_x = 0
        for elem in heatmap_elements:
            width = get_pixel_value(elem.attrib.get("width", "0"))
            group = etree.SubElement(combined_svg, "g", {"transform": f"translate({current_x}, 0)"})
            for child in elem.iterchildren():
                group.append(deepcopy(child))
            current_x += width

        logging.info("Successfully combined SVG elements.")
        return etree.tostring(combined_svg).decode("utf-8")
    except Exception as e:
        logging.error(f"Heatmap extraction failed: {e}")
        return None


def get_pixel_value(value: str) -> int:
    """Converts a pixel or percentage value to an integer."""
    try:
        if "px" in value:
            return int(value.replace("px", ""))
        if "%" in value:
            return int(float(value.replace("%", "")) * 10)
        return int(value)
    except ValueError:
        logging.warning(f"Invalid pixel value: {value}")
        return 0


def parse_svg_heatmap(heatmap_svg: str, video_duration: int) -> List[Dict[str, float]]:
    """Parses SVG with proper Bézier interpolation and normalization"""
    if not heatmap_svg:
        return []

    try:
        root = ET.fromstring(heatmap_svg)
        viewbox = [float(x) for x in root.attrib.get("viewBox", "0 0 6000 1000").split()]
        svg_width, svg_height = viewbox[2], viewbox[3]
        
        all_points = []
        
        # Process each chapter group with transform offsets
        for chapter in root.findall(".//{http://www.w3.org/2000/svg}g"):
            transform = chapter.attrib.get("transform", "")
            match = re.search(r"translate\((\d+),", transform)
            x_offset = float(match.group(1)) if match else 0

            for path in chapter.findall(".//{http://www.w3.org/2000/svg}path"):
                d_attr = path.attrib.get("d", "")
                commands = re.findall(r"([A-Z])([^A-Z]*)", d_attr)
                current_x, current_y = 0.0, 0.0
                
                for cmd, params in commands:
                    coords = [float(x) for x in re.findall(r"-?\d+\.?\d*", params)]
                    if not coords:
                        continue

                    if cmd == 'M':
                        current_x, current_y = coords[0], coords[1]
                        all_points.append((x_offset + current_x, current_y))
                    elif cmd == 'C' and len(coords) >= 6:
                        # Interpolate Bézier curve with 10 points
                        start = (current_x, current_y)
                        cp1 = (coords[0], coords[1])
                        cp2 = (coords[2], coords[3])
                        end = (coords[4], coords[5])
                        
                        for t in [i/10 for i in range(11)]:
                            x = (1-t)**3*start[0] + 3*(1-t)**2*t*cp1[0] + 3*(1-t)*t**2*cp2[0] + t**3*end[0]
                            y = (1-t)**3*start[1] + 3*(1-t)**2*t*cp1[1] + 3*(1-t)*t**2*cp2[1] + t**3*end[1]
                            all_points.append((x_offset + x, y))
                        
                        current_x, current_y = end

        if not all_points:
            return []

        # Normalize coordinates
        min_y = min(p[1] for p in all_points)
        max_y = max(p[1] for p in all_points)
        y_range = max(1, max_y - min_y)

        # Convert to attention values
        normalized = []
        for x, y in all_points:
            duration = (x / svg_width) * video_duration
            attention = 100 * (1 - ((y - min_y) / y_range))
            normalized.append({
                "duration": duration,
                "attention": max(0, min(100, attention))
            })

        # Create 1-second bins
        condensed = []
        for sec in range(video_duration):
            points_in_sec = [p for p in normalized if sec <= p["duration"] < sec + 1]
            if points_in_sec:
                avg = sum(p["attention"] for p in points_in_sec) / len(points_in_sec)
                condensed.append({"duration": sec, "Attention": round(avg, 2)})
            else:
                last = condensed[-1]["Attention"] if condensed else 50.0
                condensed.append({"duration": sec, "Attention": last})

        return condensed

    except Exception as e:
        logging.error(f"SVG parsing failed: {e}")
        return []


def analyze_heatmap_data(heatmap_points: List[Dict[str, float]], video_duration: int) -> Dict[str, Any]:
    """Detects clips, calculates average attention (0-100%), and sorts by attention."""
    if not heatmap_points:
        return {}

    # Calculate global average attention (already a percentage)
    avg = sum(p["Attention"] for p in heatmap_points) / len(heatmap_points)
    threshold = avg * 1.15
    logging.info(f"Using threshold: {threshold:.2f}% (Average: {avg:.2f}%)")
    
    clips = []
    current_clip = None
    peak_value = 0
    peak_time = 0
    
    for i, point in enumerate(heatmap_points):
        attention = point["Attention"]
        time = point["duration"]

        if attention > threshold:
            if not current_clip:
                # Start new clip, look back up to 5 seconds for rise start
                start_idx = max(0, i - 5)
                current_clip = {
                    "start": heatmap_points[start_idx]["duration"],
                    "peak": time,
                    "end": time,
                    "points": []  # Track attention points for averaging
                }
                peak_value = attention
                peak_time = time
            else:
                # Update clip end and track peak
                current_clip["end"] = time
                if attention > peak_value:
                    peak_value = attention
                    peak_time = time
            current_clip["points"].append(attention)
        elif current_clip:
            # Check for sustained fall (3 consecutive below threshold)
            fall_detected = all(p["Attention"] < threshold 
                              for p in heatmap_points[i:min(i+3, len(heatmap_points))])
            
            if fall_detected:
                # Look forward up to 5 seconds for final end
                end_idx = min(i + 5, len(heatmap_points) - 1)
                current_clip["end"] = heatmap_points[end_idx]["duration"]
                current_clip["peak"] = peak_time
                
                # Add buffer to clip ends
                clips.append(current_clip)
                current_clip = None
                peak_value = 0
                peak_time = 0

    # Add any ongoing clip
    if current_clip:
        current_clip["end"] = current_clip["end"] + 60  # Extend by 1 minute
        clips.append(current_clip)

    # Merge overlapping clips and calculate averages
    merged = []
    for clip in sorted(clips, key=lambda x: x["start"]):
        if not merged:
            merged.append(clip)
        else:
            last = merged[-1]
            if clip["start"] <= last["end"]:
                # Merge and keep highest peak
                last["end"] = max(last["end"], clip["end"])
                last["points"].extend(clip["points"])
                if clip["peak"] > last["peak"]:
                    last["peak"] = clip["peak"]
            else:
                merged.append(clip)

    # Calculate average attention for each clip (values are 0-100)
    final_clips = []
    for clip in merged:
        clip_attention = sum(clip["points"]) / len(clip["points"])
        final_clips.append({
            "start": clip["start"],
            "end": clip["end"] + 60,  # Extended end time
            "average_attention": round(clip_attention, 2)  # Percentage (0-100)
        })
    # Sort clips by average attention (descending)
    final_clips.sort(key=lambda x: x["average_attention"], reverse=True)

    return {
        "average_attention": round(avg, 2),
        "clips": final_clips,
        "total_clips": len(final_clips)
    }


def duration_to_seconds(duration: str) -> int:
    """Converts a duration string (HH:MM:SS or MM:SS) to seconds."""
    try:
        parts = list(map(int, duration.split(":")))
        if len(parts) == 2:
            return parts[0] * 60 + parts[1]
        if len(parts) == 3:
            return parts[0] * 3600 + parts[1] * 60 + parts[2]
        return 0
    except ValueError:
        logging.error(f"Invalid duration format: {duration}")
        return 0


async def process_video(video_id: str) -> Optional[List[Dict]]:
    """Processes a YouTube video to extract high-attention clips."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=random.choice(USER_AGENTS),
            viewport=random.choice(RESOLUTIONS),
            java_script_enabled=True
        )

        try:
            page = await context.new_page()
            await page.goto(f"https://youtube.com/watch?v={video_id}", timeout=60000)

            # Extract video duration
            try:
                duration_str = await page.eval_on_selector(".ytp-time-duration", "el => el.textContent")
                video_duration = duration_to_seconds(duration_str)
                logging.info(f"Video duration: {video_duration} seconds")
            except Exception as e:
                logging.error(f"Failed to extract video duration: {e}")
                return None

            # Extract heatmap SVG
            heatmap_svg = await extract_heatmap_svgs(page)
            if not heatmap_svg:
                logging.error("Failed to extract heatmap SVG.")
                return None

            # Parse heatmap data
            heatmap_points = parse_svg_heatmap(heatmap_svg, video_duration)
            if not heatmap_points:
                logging.error("No heatmap points found.")
                return None

            # Analyze heatmap data
            heatmap_analysis = analyze_heatmap_data(heatmap_points, video_duration)

            # Extract significant rises
            clips = heatmap_analysis.get("clips", [])
            return clips

        except Exception as e:
            logging.error(f"Video processing error: {e}")
            return None
        finally:
            await browser.close()


def main():
    """Main function to handle command-line input and output."""
    parser = argparse.ArgumentParser(description="Extract high-attention clips from a YouTube video.")
    parser.add_argument("video_id", help="YouTube video ID")
    args = parser.parse_args()

    # Process the video and output results
    result = asyncio.run(process_video(args.video_id))
    print(json.dumps(result if result else [], indent=2))


if __name__ == "__main__":
    main()
