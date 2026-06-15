# YouTube Scraper — Docker image
#
# Build:   docker build -t youtube-scraper .
# Run:     docker run --rm -v $(pwd)/outputs:/app/outputs youtube-scraper --search "claude code" --search-limit 5
# Compose: docker compose run --rm scraper --search "topic" --search-limit 10

FROM python:3.11-slim

# Install ffmpeg (required for audio/video conversion)
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first (better layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY scripts/ ./scripts/

# Outputs directory (mount here to get files on host)
RUN mkdir -p /app/scripts/outputs

# SQLite cache lives here — mount to persist across runs
RUN mkdir -p /root/.cache/youtube_scraper

ENTRYPOINT ["python", "scripts/youtube_scraper.py"]
CMD ["--help"]
