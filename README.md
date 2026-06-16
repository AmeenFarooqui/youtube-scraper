# YouTube Scraper — Python CLI for YouTube Data Extraction

[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)
[![License](https://img.shields.io/github/license/AmeenFarooqui/youtube-scraper)](LICENSE)
[![Powered by yt-dlp](https://img.shields.io/badge/powered%20by-yt--dlp-red)](https://github.com/yt-dlp/yt-dlp)
[![No API Key](https://img.shields.io/badge/YouTube%20API%20key-not%20required-brightgreen)](#)

> Open-source Python CLI to scrape YouTube video metadata, comments, subtitles, channels, and playlists — powered by **yt-dlp**. No YouTube API key required. A fast, scriptable alternative to the YouTube Data API.

## Quickstart

```bash
git clone https://github.com/AmeenFarooqui/youtube-scraper.git
cd youtube-scraper
pip install -r requirements.txt

# Search YouTube
python scripts/youtube_scraper.py --search "your topic" --search-limit 10

# Single video metadata
python scripts/youtube_scraper.py --url "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
```

Or with Docker (zero setup):
```bash
docker compose up --build
docker compose run --rm scraper --search "your topic"
```

---

A feature-complete YouTube metadata extractor built with Python and **yt-dlp**. Extracts rich structured data from videos, playlists, channels, and batches of URLs. Downloading is **never** the default behavior.

---

## What This Does

- **Searches YouTube by keyword** and returns ranked results with full metadata
- **Feeds YouTube URLs into NotebookLM** via `--urls-only` — the primary research workflow
- Extracts **deep metadata** from any public YouTube video: stats, formats, subtitles, chapters, heatmap data, channel info, and more
- **Scrapes entire channels** across videos, Shorts, and live stream tabs
- Fetches **comments** and runs **VADER sentiment analysis** on them
- Enriches results with **dislike counts** from the Return YouTube Dislike API
- **Filters and sorts** by views, likes, dislikes, subscribers, duration, date, or sentiment ratio
- Analyzes **entire playlists** with summary statistics
- Processes **batches of URLs** from a text file, concurrently
- Caches metadata in **SQLite** to avoid redundant network requests
- Tracks failures persistently in a **JSONL failure log**
- Optionally **downloads video (MP4) or audio (MP3)** when explicitly requested
- Outputs to **JSON** (default), **CSV**, or **Markdown report**
- Ships with a **Docker image** for zero-install deployment

---

## Features

| Feature | Details |
|---------|---------|
| **YouTube search** | Search by keyword, filter by views/duration/age/likes/subs, get ranked results |
| **NotebookLM pipeline** | `--urls-only` outputs clean URLs for piping into `notebooklm source add` |
| **Pipeline mode** | Search → filter → fetch full metadata for top N results |
| **Channel scraper** | Scrape `/videos`, `/shorts`, `/streams`, or all tabs via `--channel` |
| **Comments** | Fetch top comments with `--comments` |
| **Dislike counts** | Estimated dislikes via Return YouTube Dislike API (`--dislikes`) |
| **Sentiment analysis** | VADER-based positive/negative/neutral breakdown on comments (`--sentiment`) |
| **Sorting** | Sort results by views, likes, dislikes, subscribers, date, duration, or sentiment ratio |
| **Engagement filters** | Filter by min/max likes, dislikes, subscribers, positive ratio, negative ratio |
| **SQLite cache** | Metadata cached 24h per video ID — avoids redundant fetches |
| **Failure tracking** | Permanent JSONL log of every failed URL with error classification |
| Single video metadata | 30+ fields including stats, formats, subtitles, Shorts detection |
| Playlist analysis | Total duration, avg length, view totals, date range |
| Batch processing | Concurrent, fault-tolerant, continues on failures |
| Subtitle extraction | Lists available languages, optionally downloads .srt/.vtt |
| Optional downloads | Video (MP4/MKV/WebM) or audio (MP3/M4A/WAV/FLAC) |
| Output formats | JSON, CSV, Markdown report, URLs-only |
| Error handling | Classifies: deleted, private, age-restricted, geo-blocked |
| Terminal UI | Rich colored output with tables and panels |
| Docker | `docker compose up` — no local Python setup required |

---

## Installation

### Option A: Docker (recommended — zero setup)

```bash
cd youtube-scraper
docker compose up --build
```

Outputs land in `./outputs/`, cache in a named Docker volume.

To run a one-off command:
```bash
docker compose run --rm scraper --search "topic" --search-limit 10
```

### Option B: Local Python

#### Prerequisites

- Python 3.10+
- pip

#### Step 1: Create a virtual environment (recommended)

```bash
cd youtube-scraper
python3 -m venv venv

# Linux/Mac:
source venv/bin/activate
# Windows:
venv\Scripts\activate
```

#### Step 2: Install Python dependencies

```bash
pip install -r requirements.txt
```

This installs:
- `yt-dlp` — the core YouTube data engine
- `rich` — colored terminal output with tables
- `tqdm` — progress bars for batch operations
- `vaderSentiment` — lexicon-based comment sentiment analysis

#### Step 3: Install ffmpeg (optional, required for downloads)

ffmpeg is needed for:
- Converting audio to MP3 (`--download-audio`)
- Merging best video+audio streams (`--download-video`)

```bash
# Ubuntu/Debian
sudo apt install ffmpeg

# macOS
brew install ffmpeg

# Windows — download from https://ffmpeg.org/download.html, add to PATH
```

#### Step 4: Verify

```bash
python3 -c "import yt_dlp; print('yt-dlp version:', yt_dlp.version.__version__)"
```

---

## Usage

All commands run from the repo root. The entry point is `scripts/youtube_scraper.py`:

---

### Search YouTube by keyword

```bash
python scripts/youtube_scraper.py --search "claude code tutorial" --search-limit 10
```

### Search with filters (recent, high-engagement)

```bash
python scripts/youtube_scraper.py \
  --search "agentic AI" \
  --search-limit 20 \
  --filter-min-views 5000 \
  --filter-min-duration 300 \
  --filter-max-age-days 90
```

### Search → get URLs only (for NotebookLM)

```bash
python scripts/youtube_scraper.py \
  --search "autoresearch karpathy" \
  --search-limit 15 \
  --urls-only \
  --output urls.txt
```

This outputs one YouTube URL per line — nothing else. Pipe directly into `notebooklm source add`.

---

### NotebookLM Research Pipeline

The recommended end-to-end workflow:

```bash
# Step 1: search YouTube, save clean URL list
python scripts/youtube_scraper.py --search "topic" --search-limit 15 --urls-only --output urls.txt

# Step 2: create a NotebookLM notebook
notebooklm create "Topic Research" --json   # note the notebook ID

# Step 3: add each URL as a source (NotebookLM indexes transcripts itself)
notebooklm source add "https://www.youtube.com/watch?v=..." --notebook NOTEBOOK_ID

# Step 4: ask for analysis — all computation offloaded to Google (zero Claude tokens)
notebooklm ask "What are the top insights?" --notebook NOTEBOOK_ID
notebooklm generate infographic "Summary" --notebook NOTEBOOK_ID --orientation portrait
```

> **Never use `--subtitles` to feed NotebookLM.** Pass the YouTube URL directly to
> `notebooklm source add` — NotebookLM fetches and indexes the transcript itself.

---

### Channel scraping

Scrape a channel's video tab:
```bash
python scripts/youtube_scraper.py --channel "https://www.youtube.com/@channelname"
```

Specify which tab (`videos`, `shorts`, `streams`, `all`):
```bash
python scripts/youtube_scraper.py --channel "https://www.youtube.com/@channelname" --channel-tab shorts
python scripts/youtube_scraper.py --channel "https://www.youtube.com/@channelname" --channel-tab all
```

Limit results and save:
```bash
python scripts/youtube_scraper.py \
  --channel "https://www.youtube.com/@channelname" \
  --channel-tab videos \
  --max-videos 50 \
  --output channel.json
```

---

### Comments

Fetch top comments for a video:
```bash
python scripts/youtube_scraper.py --url "URL" --comments
```

Control how many:
```bash
python scripts/youtube_scraper.py --url "URL" --comments --comments-max 100
```

---

### Dislike counts (Return YouTube Dislike API)

Enrich results with estimated dislikes:
```bash
python scripts/youtube_scraper.py --url "URL" --dislikes
```

Works in search and batch modes too:
```bash
python scripts/youtube_scraper.py --search "topic" --search-limit 10 --dislikes
```

---

### Sentiment analysis on comments

Run VADER sentiment on fetched comments:
```bash
python scripts/youtube_scraper.py --url "URL" --comments --sentiment
```

Returns `positive_pct`, `negative_pct`, `neutral_pct`, `compound_avg`, `total_analyzed` in the output.

---

### Sorting results

Sort by any engagement metric:
```bash
# Sort search results by view count (descending, default)
python scripts/youtube_scraper.py --search "topic" --search-limit 20 --sort-by views

# Sort by like count, ascending
python scripts/youtube_scraper.py --search "topic" --search-limit 20 --sort-by likes --sort-order asc

# Sort by estimated dislikes (requires --dislikes)
python scripts/youtube_scraper.py --search "topic" --dislikes --sort-by dislikes

# Sort by positive comment ratio (requires --comments --sentiment)
python scripts/youtube_scraper.py --search "topic" --comments --sentiment --sort-by positive_ratio
```

Available sort fields: `views`, `likes`, `dislikes`, `subscribers`, `date`, `duration`, `positive_ratio`, `negative_ratio`

---

### Engagement filters

Filter by subscriber count:
```bash
python scripts/youtube_scraper.py \
  --search "topic" \
  --filter-min-subscribers 100000 \
  --filter-max-subscribers 5000000
```

Filter by like count:
```bash
python scripts/youtube_scraper.py --search "topic" --filter-min-likes 1000
```

Filter by dislike count (requires `--dislikes`):
```bash
python scripts/youtube_scraper.py --search "topic" --dislikes --filter-max-dislikes 500
```

Filter by comment sentiment ratio (requires `--comments --sentiment`, values 0.0–1.0):
```bash
python scripts/youtube_scraper.py \
  --search "topic" \
  --comments --sentiment \
  --filter-min-positive-ratio 0.7
```

---

### Pipeline mode (search → filter → full metadata)

```bash
python scripts/youtube_scraper.py \
  --search "claude code" \
  --search-limit 20 \
  --pipeline \
  --filter-min-views 10000 \
  --pipeline-top 5 \
  --urls-only
```

`--pipeline` fetches full metadata for the top results after filtering, so you can inspect quality before sending to NotebookLM.

---

### Single video (default JSON output)

```bash
python scripts/youtube_scraper.py --url "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
```

### Save JSON to file

```bash
python scripts/youtube_scraper.py --url "URL" --output results.json
```

### Export CSV (for spreadsheets)

```bash
python scripts/youtube_scraper.py --url "URL" --csv --output results.csv
```

### Generate Markdown report

```bash
python scripts/youtube_scraper.py --url "URL" --report --output report.md
```

### Analyze a playlist

```bash
python scripts/youtube_scraper.py --playlist "https://www.youtube.com/playlist?list=PL..."
```

Fast mode (default) — gets title/duration/views per video without loading each page individually.

For full per-video metadata (slow):
```bash
python scripts/youtube_scraper.py --playlist "URL" --full-playlist
```

### Get only URLs from any mode

```bash
# From search:
python scripts/youtube_scraper.py --search "topic" --search-limit 10 --urls-only

# From batch:
python scripts/youtube_scraper.py --batch existing_urls.txt --urls-only

# From playlist:
python scripts/youtube_scraper.py --playlist "https://www.youtube.com/playlist?list=PL..." --urls-only
```

### Batch process from a file

```bash
# urls.txt: one YouTube URL per line, # = comment
python scripts/youtube_scraper.py --batch examples/urls.txt --output batch.json
```

With concurrent workers (default: 3):
```bash
python scripts/youtube_scraper.py --batch urls.txt --workers 5
```

Log failures to a file:
```bash
python scripts/youtube_scraper.py --batch urls.txt --failure-log failures.jsonl
```

### Cache control

Results are cached in SQLite for 24 hours by default. To bypass:
```bash
python scripts/youtube_scraper.py --url "URL" --no-cache
```

### Check subtitle availability

```bash
python scripts/youtube_scraper.py --url "URL" --subtitles
```

Download subtitle files (SRT format, English):
```bash
python scripts/youtube_scraper.py --url "URL" --subtitles --download-subs --subtitle-lang en
```

Other languages and formats:
```bash
python scripts/youtube_scraper.py --url "URL" --subtitles --subtitle-lang es --subtitle-format vtt
```

### Download audio only (MP3)

```bash
python scripts/youtube_scraper.py --url "URL" --download-audio
```

Custom format (WAV, FLAC, M4A, AAC):
```bash
python scripts/youtube_scraper.py --url "URL" --download-audio --audio-format wav
```

### Download video (MP4)

```bash
python scripts/youtube_scraper.py --url "URL" --download-video
```

Custom format and directory:
```bash
python scripts/youtube_scraper.py --url "URL" --download-video --video-format mkv --download-dir ~/Videos
```

### Verbose mode (see what yt-dlp is doing)

```bash
python scripts/youtube_scraper.py --url "URL" --verbose
```

---

## Output Example (JSON)

```json
{
  "id": "dQw4w9WgXcQ",
  "title": "Rick Astley - Never Gonna Give You Up (Official Video)",
  "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
  "upload_date_formatted": "October 24, 2009",
  "duration_string": "3:33",
  "channel": "RickAstleyVEVO",
  "channel_follower_count_formatted": "3.10M",
  "view_count_formatted": "1.50B",
  "like_count_formatted": "15.00M",
  "comment_count_formatted": "2.50M",
  "dislike_count": 42000,
  "dislike_count_formatted": "42.00K",
  "dislike_count_estimated": true,
  "is_short": false,
  "content_type": "video",
  "tags": ["rick astley", "never gonna give you up"],
  "categories": ["Music"],
  "language": "en",
  "age_limit": 0,
  "availability": "public",
  "live_status": "not_live",
  "has_chapters": false,
  "sentiment_summary": {
    "positive_pct": 0.724,
    "negative_pct": 0.081,
    "neutral_pct": 0.195,
    "compound_avg": 0.61,
    "total_analyzed": 100
  },
  "formats_summary": {
    "total_formats": 20,
    "video_only_count": 8,
    "audio_only_count": 5,
    "best_video_format": {
      "resolution": "1920x1080",
      "fps": 30,
      "vcodec": "avc1",
      "ext": "mp4"
    }
  },
  "subtitles_summary": {
    "manual_languages": ["en"],
    "auto_caption_languages": ["en", "es", "fr"],
    "total_languages": 3
  }
}
```

---

## CLI Reference

### Core flags

| Flag | Description |
|------|-------------|
| `--url URL` | Single video metadata |
| `--search "query"` | Search YouTube by keyword |
| `--search-limit N` | Max search results (default: 10) |
| `--playlist URL` | Playlist analysis |
| `--full-playlist` | Fetch full metadata per video (slow) |
| `--batch FILE` | Batch URLs from a text file |
| `--channel URL` | Scrape a channel |
| `--channel-tab TAB` | `videos` / `shorts` / `streams` / `all` (default: videos) |
| `--workers N` | Concurrent workers for batch (default: 3, min: 1) |

### Enrichment flags

| Flag | Description |
|------|-------------|
| `--comments` | Fetch top comments |
| `--comments-max N` | Max comments to include in output (default: 500) |
| `--dislikes` | Enrich with Return YouTube Dislike API |
| `--sentiment` | Run VADER sentiment on comments (requires `--comments`) |
| `--subtitles` | Check subtitle/caption availability |
| `--download-subs` | Download subtitle files |
| `--subtitle-lang LANG` | Language code (default: en) |
| `--subtitle-format FMT` | `srt` / `vtt` (default: srt) |

### Sorting flags

| Flag | Default | Description |
|------|---------|-------------|
| `--sort-by FIELD` | — | Sort field: `views`, `likes`, `dislikes`, `subscribers`, `date`, `duration`, `positive_ratio`, `negative_ratio` |
| `--sort-order ORDER` | `desc` | `asc` or `desc` |

### Filter flags

| Flag | Description |
|------|-------------|
| `--filter-min-views N` | Minimum view count |
| `--filter-max-views N` | Maximum view count |
| `--filter-min-duration SECS` | Minimum duration in seconds |
| `--filter-max-duration SECS` | Maximum duration in seconds |
| `--filter-max-age-days N` | Only videos uploaded within N days |
| `--filter-min-likes N` | Minimum like count |
| `--filter-max-likes N` | Maximum like count |
| `--filter-min-dislikes N` | Minimum dislike count (requires `--dislikes`) |
| `--filter-max-dislikes N` | Maximum dislike count (requires `--dislikes`) |
| `--filter-min-subscribers N` | Minimum channel subscriber count |
| `--filter-max-subscribers N` | Maximum channel subscriber count |
| `--filter-min-positive-ratio R` | Min positive comment ratio 0.0–1.0 (requires `--comments --sentiment`) |
| `--filter-min-negative-ratio R` | Min negative comment ratio 0.0–1.0 (requires `--comments --sentiment`) |

### Output flags

| Flag | Description |
|------|-------------|
| `--output FILE` | Save output to file (.json, .csv, .md, .txt) |
| `--csv` | Export as CSV |
| `--report` | Generate Markdown report |
| `--urls-only` | Output only URLs, one per line |
| `--detailed-formats` | Include every stream in `formats_summary` (compact counts and best format are the default) |
| `--pipeline` | After search, fetch full metadata for top results |
| `--pipeline-top N` | How many results to fully extract (default: 3) |
| `--no-cache` | Bypass SQLite cache |
| `--failure-log FILE` | Append failed URLs to a JSONL file |
| `--verbose` | Show yt-dlp debug output |

### Download flags

| Flag | Description |
|------|-------------|
| `--download-audio` | Download audio only |
| `--audio-format FMT` | `mp3` / `m4a` / `wav` / `flac` / `aac` (default: mp3) |
| `--download-video` | Download video |
| `--video-format FMT` | `mp4` / `mkv` / `webm` (default: mp4) |
| `--download-dir DIR` | Download destination (default: `outputs/`) |

---

## Project Architecture

```
youtube-scraper/
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
│
└── scripts/
    ├── youtube_scraper.py      # ENTRY POINT — CLI, routing, output
    ├── config.py               # All settings and defaults in one place
    │
    ├── extractor/              # DATA FETCHING layer (yt-dlp wrappers)
    │   ├── video_extractor.py     # Single video metadata
    │   ├── playlist_extractor.py  # Playlist + per-video data
    │   ├── channel_extractor.py   # Channel tab scraping (videos/shorts/streams/all)
    │   ├── subtitle_extractor.py  # Subtitle availability + download
    │   └── downloader.py          # File downloads (video/audio)
    │
    ├── formatter/              # OUTPUT RENDERING layer
    │   ├── json_formatter.py      # JSON serialization + file writing
    │   ├── csv_formatter.py       # Flat CSV export
    │   └── markdown_formatter.py  # Human-readable Markdown reports
    │
    ├── reports/
    │   └── report_generator.py    # Terminal display layer — prints concise human-readable summaries
    │
    ├── cache/                  # SQLITE CACHE layer
    │   └── cache_manager.py       # 24h TTL cache, lazy eviction, mode 0o700
    │
    └── utils/                  # SHARED UTILITIES
        ├── logger.py              # Centralized logging (rich + file)
        ├── validators.py          # URL validation, batch file validation
        ├── helpers.py             # Pure functions: format numbers, dates, durations
        ├── error_handler.py       # Custom exceptions, yt-dlp error classification
        ├── failure_tracker.py     # JSONL failure log with permanent/transient classification
        ├── ryd_client.py          # Return YouTube Dislike API client (stdlib urllib only)
        └── sentiment_analyzer.py  # VADER comment sentiment analysis
```

**Data flow:**
```
User runs CLI
     |
youtube_scraper.py (parse args, route)
     |
cache/cache_manager.py (check SQLite — return hit or proceed)
     |
extractor/*.py (call yt-dlp => shape data)
     |
utils/ryd_client.py (optional — enrich with dislike counts)
utils/sentiment_analyzer.py (optional — VADER on comments)
     |
_apply_engagement_filters() + _apply_sort()
     |
formatter/*.py (render => JSON/CSV/Markdown)
     |
Output to terminal or file
```

---

## How yt-dlp Works (Beginner Explanation)

yt-dlp is a command-line tool that can also be used as a Python library.

When you call `yt_dlp.YoutubeDL(options)`, you get an object that:
1. Connects to YouTube's servers
2. Parses the video page (HTML, JavaScript, and internal APIs)
3. Returns a big Python dictionary with everything about the video

The key option is `download=False` in `extract_info()` — this tells yt-dlp to **fetch metadata only** without downloading any files. That's what makes our scraper fast and non-destructive.

```python
import yt_dlp

opts = {"quiet": True}
with yt_dlp.YoutubeDL(opts) as ydl:
    # This fetches data but does NOT download the video
    info = ydl.extract_info("https://youtube.com/watch?v=...", download=False)

    # sanitize_info converts everything to JSON-safe types
    data = ydl.sanitize_info(info)
```

The returned `data` dict has 100+ fields covering every aspect of the video.

---

## Error Handling

The scraper catches and classifies errors automatically:

| Error | Meaning | What to do |
|-------|---------|------------|
| `VideoUnavailableError` | Deleted/removed | Nothing — video is gone |
| `PrivateVideoError` | Set to private | Cannot access without auth |
| `AgeRestrictedError` | Age-gated content | Requires sign-in |
| `GeoBlockedError` | Region-restricted | Use a VPN or different region |
| `NetworkError` | Connection failed | Check internet connection |
| `RateLimitedError` | Too many requests | Wait and retry |

For batch runs: failed URLs are recorded in the output and optionally written to `--failure-log`. Processing continues regardless.

---

## Running Tests

Install dev dependencies first (pytest is not in the default install):

```bash
pip install pytest
```

Run all tests:
```bash
# From repo root
python -m pytest scripts/tests/ -v

# Or without pytest (stdlib only):
python -m unittest discover -s scripts/tests -p "test_*.py" -v
```

Run a specific file:
```bash
python -m pytest scripts/tests/test_validators.py -v
python -m pytest scripts/tests/test_helpers.py -v
python -m pytest scripts/tests/test_formatters.py -v
python -m pytest scripts/tests/test_cli_behaviors.py -v
```

Tests cover:
- URL validation (video, playlist, channel, invalid URLs)
- Helper functions (formatting, safe access)
- Formatters (JSON, CSV, Markdown output)
- CLI internal helpers (`_result_items`, `_run_ordered`, `_post_process_items`)

No network calls are made in tests — all use mock data.

---

## Known Limitations

### `--search --comments` fetches full metadata per result (slower)

When `--comments` is combined with `--search`, the scraper automatically upgrades each search stub to full metadata by making one additional yt-dlp call per video. This is necessary because search results are lightweight stubs that don't include comments or like counts.

This means the one-command version works, but is slower than a plain search:

```bash
# Works — fetches full metadata + comments for all 10 results concurrently
python scripts/youtube_scraper.py \
  --search "web scraper tutorial python" \
  --search-limit 10 \
  --dislikes \
  --comments \
  --sentiment \
  --sort-by positive_ratio \
  --output results.json
```

For large search limits, use `--pipeline` with `--pipeline-top` to limit full fetches to only the top N after filtering:

```bash
# More efficient: search 20, filter by views, fully extract top 5 with comments
python scripts/youtube_scraper.py \
  --search "web scraper tutorial python" \
  --search-limit 20 \
  --pipeline \
  --pipeline-top 5 \
  --filter-min-views 5000 \
  --dislikes \
  --comments \
  --sentiment \
  --sort-by positive_ratio \
  --output results.json
```

---

### Like count is missing from search results

Search results are stubs — `like_count` is often `None`. If you use
`--filter-min-likes` without `--pipeline` in `--search` mode, the CLI
rejects the combination at startup with a clear error message. In
channel/playlist/batch mode where the field may be `None`, a `WARNING`
is logged listing how many items were excluded.

**Fix:** Use `--pipeline` to populate `like_count` before filtering:

```bash
python scripts/youtube_scraper.py \
  --search "topic" \
  --pipeline \
  --pipeline-top 10 \
  --filter-min-likes 1000
```

---

### Dislike counts are estimates, not official

YouTube removed public dislike counts in November 2021. The `--dislikes` flag fetches crowdsourced estimates from [returnyoutubedislikeapi.com](https://returnyoutubedislikeapi.com). These are approximations based on extension users and ML modeling — treat them as directional signals, not exact figures.

The field `"dislike_count_estimated": true` in the output marks this.

---

---

## Troubleshooting

### "Module not found: yt_dlp"
```bash
pip install yt-dlp
```

### "Module not found: vaderSentiment"
```bash
pip install vaderSentiment
```
Sentiment analysis is optional — it's skipped gracefully if the package is absent.

### "ffmpeg not found" during download
Install ffmpeg (see Installation section). Metadata extraction works fine without ffmpeg.

### "Video unavailable"
The video may be deleted, private, or geo-blocked in your region.

### Slow playlist extraction
Use default flat mode (no `--full-playlist`). Full mode makes one network request per video.

### Rate limiting on large batches
Reduce `--workers` to 1 for sequential processing, or add delays between runs.

### yt-dlp is outdated (YouTube changes often)
```bash
pip install -U yt-dlp
```
YouTube's internal APIs change frequently. Keeping yt-dlp up to date is important.

### Dislike counts show `null`
The Return YouTube Dislike API may be unavailable or the video may be too new. Failures are silent — the rest of the metadata is unaffected.

---

## Future Roadmap

| Feature | Status | Complexity | Value |
|---------|--------|-----------|-------|
| YouTube search integration | Done | — | — |
| NotebookLM pipeline (`--urls-only`) | Done | — | — |
| Pipeline mode with filters | Done | — | — |
| Channel extractor (`--channel`, `--channel-tab`) | Done | — | — |
| SQLite metadata cache | Done | — | — |
| Comment extraction (`--comments`) | Done | — | — |
| Sentiment analysis on comments (`--sentiment`) | Done | — | — |
| Dislike counts via RYD API (`--dislikes`) | Done | — | — |
| Engagement filtering + sorting | Done | — | — |
| Failure tracking (`--failure-log`) | Done | — | — |
| Docker support | Done | — | — |
| Transcript text extraction (`--transcript`) | Done | — | — |
| Keyword/topic extraction (NLP) | Pending | Medium | Medium |
| FastAPI REST API wrapper | Pending | Medium | High |
| Streamlit web UI | Pending | Medium | Medium |
| HTML report output | Pending | Low | Medium |
| Cookie/auth support (optional) | Pending | Medium | Medium |
| AI-powered video summarization | Pending | High | High |
| Export to Postgres/Supabase | Pending | Medium | Medium |
| Scheduled scraping (cron) | Pending | Low | Medium |
| Duplicate URL detection | Pending | Low | Low |

---

## Security & Ethics

This tool:
- Only accesses **public** YouTube content
- Never uses authentication or cookies by default
- Does not bypass any protections
- Respects YouTube's public data access
- Cache directory is created with mode `0o700` (owner-only access)
- Video IDs are URL-encoded before being sent to external APIs
- Is intended for research, analysis, and content discovery

Do not use this to mass-download copyrighted content or violate YouTube's Terms of Service.
