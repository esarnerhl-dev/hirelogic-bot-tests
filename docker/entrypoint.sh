#!/bin/bash
# docker/entrypoint.sh
set -e

# Start PulseAudio as a system daemon
pulseaudio --start \
  --exit-idle-time=-1 \
  --disallow-exit \
  --log-target=stderr \
  2>/dev/null || true

# Wait for PulseAudio to be ready
sleep 1
pactl info > /dev/null 2>&1 || echo "[Warning] PulseAudio not ready"

# Generate fixtures if not present
if [ ! -f "fixtures/audio/single_speaker_30s.wav" ]; then
  echo "[Setup] Generating audio fixtures..."
  python audio/generator.py --all
fi

# Execute the passed command (default: pytest)
exec "$@"
