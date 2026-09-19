#!/usr/bin/env bash
# Grab one frame from the FaceTime HD camera to $1 (default: scratch dir).
set -euo pipefail
out=${1:-/tmp/claude-1001/-home-mert-Work-omarchy-mac-external-monitor/22429b88-71d1-43e7-920b-d65b33d4708b/scratchpad/webcam-$(date +%H%M%S).jpg}
ffmpeg -hide_banner -loglevel error -y -f v4l2 -i /dev/video1 -ss 0.7 -frames:v 1 -vf scale=960:-1 -q:v 4 "$out"
echo "$out"
