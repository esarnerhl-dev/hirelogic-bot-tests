FROM python:3.11-slim

# System deps: PulseAudio, sox, Playwright browser deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    pulseaudio \
    pulseaudio-utils \
    sox \
    libsox-fmt-mp3 \
    alsa-utils \
    libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 \
    libcups2 libdrm2 libxkbcommon0 libxcomposite1 \
    libxdamage1 libxfixes3 libxrandr2 libgbm1 \
    libasound2 libpango-1.0-0 libcairo2 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Playwright browsers
RUN playwright install chromium

# Copy source
COPY . .

# PulseAudio config: allow all users to connect
RUN mkdir -p /etc/pulse && echo "\
default-server = unix:/tmp/pulseaudio.socket\n\
autospawn = no\n\
daemon-binary = /bin/true\n\
enable-shm = false\n\
" > /etc/pulse/client.conf

# Entrypoint: start PulseAudio then run tests
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
CMD ["pytest", "tests/", "-v", "--tb=short"]
