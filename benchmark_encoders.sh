#!/bin/bash

# Find a sample video to test with
SAMPLE_VIDEO=$(find output -name "*.mp4" -type f | head -1)

if [ -z "$SAMPLE_VIDEO" ]; then
    echo "No sample video found. Please run the pipeline first to generate test videos."
    exit 1
fi

echo "Testing encoders with: $SAMPLE_VIDEO"
echo "=================================="

TEST_OUTPUT="/tmp/ffmpeg_benchmark"
mkdir -p "$TEST_OUTPUT"

# Test configurations
declare -A CONFIGS=(
    ["h264_vaapi"]="h264_vaapi -vaapi_device /dev/dri/renderD128"
    ["h264_qsv"]="h264_qsv"
    ["libx264_ultrafast"]="libx264 -preset ultrafast"
    ["libx264_veryfast"]="libx264 -preset veryfast"
    ["libx264_fast"]="libx264 -preset fast"
    ["hevc_vaapi"]="hevc_vaapi -vaapi_device /dev/dri/renderD128"
    ["hevc_qsv"]="hevc_qsv"
)

for name in "${!CONFIGS[@]}"; do
    echo ""
    echo "Testing: $name"
    echo "Command: ${CONFIGS[$name]}"
    
    output_file="$TEST_OUTPUT/${name}.mp4"
    
    start=$(date +%s.%N)
    
    if [[ $name == *"vaapi"* ]]; then
        ffmpeg -y -hwaccel vaapi -hwaccel_device /dev/dri/renderD128 -hwaccel_output_format vaapi \
            -i "$SAMPLE_VIDEO" -c:v ${CONFIGS[$name]} -b:v 2M -c:a copy "$output_file" 2>&1 | grep -E "(frame=|error|failed)" | tail -5
    elif [[ $name == *"qsv"* ]]; then
        ffmpeg -y -hwaccel qsv -hwaccel_output_format qsv \
            -i "$SAMPLE_VIDEO" -c:v ${CONFIGS[$name]} -b:v 2M -c:a copy "$output_file" 2>&1 | grep -E "(frame=|error|failed)" | tail -5
    else
        ffmpeg -y -i "$SAMPLE_VIDEO" -c:v ${CONFIGS[$name]} -crf 23 -c:a copy "$output_file" 2>&1 | grep -E "(frame=|error|failed)" | tail -5
    fi
    
    end=$(date +%s.%N)
    duration=$(echo "$end - $start" | bc)
    
    if [ -f "$output_file" ]; then
        size=$(du -h "$output_file" | cut -f1)
        echo "✓ Success - Time: ${duration}s, Size: $size"
    else
        echo "✗ Failed"
    fi
done

echo ""
echo "=================================="
echo "Benchmark complete. Results in $TEST_OUTPUT"
