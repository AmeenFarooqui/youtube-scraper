# YouTube Scraper — Claude Code Skill

A production-grade YouTube metadata extractor and scraper built with Python and **yt-dlp**. Extracts rich structured data from videos, playlists, and batches of URLs. Downloading is **never** the default behavior.

---

## What This Does

- **Searches YouTube by keyword** and returns ranked results with full metadata
- **Feeds YouTube URLs into NotebookLM** via `--urls-only` — the primary research workflow
- Extracts **deep metadata** from any public YouTube video: stats, formats, subtitles, chapters, heatmap data, channel info, and more
- Analyzes **entire playlists** with summary statistics
- Processes **batches of URLs** from a text file, concurrently
- Checks **subtitle/caption availability** across all languages
- Optionally **downloads video (MP4) or audio (MP3)** when explicitly requested
- Outputs to **JSON** (default), **CSV**, or **Markdown report**

---

## Features

| Feature | Details |
|---------|---------|
| **YouTube search** | Search by keyword, filter by views/duration/age, get ranked results |
| **NotebookLM pipeline** | `--urls-only` outputs clean URLs for piping into `notebooklm source add` |
| **Pipeline mode** | Search → filter → fetch full metadata for top N results |
| Single video metadata | 30+ fields including stats, formats, subtitles |
| Playlist analysis | Total duration, avg length, view totals, date range |
| Batch processing | Concurrent, fault-tolerant, continues on failures |
| Subtitle extraction | Lists available languages, optionally downloads .srt/.vtt |
| Optional downloads | Video (MP4/MKV/WebM) or audio (MP3/M4A/WAV/FLAC) |
| Output formats | JSON, CSV, Markdown report, URLs-only |
| Error handling | Classifies: deleted, private, age-restricted, geo-blocked |
| Terminal UI | Rich colored output with tables and panels |

---

## Installation

### Prerequisites

- Python 3.10+
- pip

### Step 1: Create a virtual environment (recommended)

```bash
# Create a virtual environment in the skill directory
cd ~/.claude/skills/youtube-scraper
python3 -m venv venv

# Activate it
# Linux/Mac:
source venv/bin/activate
# Windows:
venv\Scripts\activate
```

### Step 2: Install Python dependencies

```bash
pip install -r requirements.txt
```

This installs:
- `yt-dlp` — the core YouTube data engine
- `rich` — colored terminal output with tables
- `tqdm` — progress bars for batch operations
- `pandas` — available for future data analysis

### Step 3: Install ffmpeg (optional, required for downloads)

ffmpeg is a separate tool (not a Python package) needed for:
- Converting audio to MP3 (`--download-audio`)
- Merging best video+audio streams (`--download-video`)

```bash
# Ubuntu/Debian
sudo apt install ffmpeg

# macOS
brew install ffmpeg

# Windows
# Download from https://ffmpeg.org/download.html
# Add ffmpeg.exe to your PATH
```

Verify installation:
```bash
ffmpeg -version
```

### Step 4: Verify yt-dlp

```bash
python3 -c "import yt_dlp; print('yt-dlp version:', yt_dlp.version.__version__)"
```

---

## Usage

All commands run from the `scripts/` directory, or pass the full path:

```bash
cd ~/.claude/skills/youtube-scraper/scripts
```

### Search YouTube by keyword

```bash
python youtube_scraper.py --search "claude code tutorial" --search-limit 10
```

### Search with filters (recent, high-engagement)

```bash
python youtube_scraper.py \
  --search "agentic AI" \
  --search-limit 20 \
  --filter-min-views 5000 \
  --filter-min-duration 300 \
  --filter-max-age-days 90
```

### Search → get URLs only (for NotebookLM)

```bash
python youtube_scraper.py \
  --search "autoresearch karpathy" \
  --search-limit 15 \
  --urls-only \
  --output urls.txt
```

This outputs one YouTube URL per line — nothing else. Pipe directly into `notebooklm source add`.

### NotebookLM Research Pipeline

The recommended end-to-end workflow:

```bash
# Step 1: search YouTube, save clean URL list
python youtube_scraper.py --search "topic" --search-limit 15 --urls-only --output urls.txt

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

### Pipeline mode (search → filter → full metadata)

```bash
python youtube_scraper.py \
  --search "claude code" \
  --search-limit 20 \
  --pipeline \
  --filter-min-views 10000 \
  --pipeline-top 5 \
  --urls-only
```

`--pipeline` fetches full metadata for the top results after filtering, so you can inspect
quality before sending to NotebookLM.

### Single video (default JSON output)

```bash
python youtube_scraper.py --url "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
```

### Save JSON to file

```bash
python youtube_scraper.py --url "URL" --output results.json
```

### Export CSV (for spreadsheets)

```bash
python youtube_scraper.py --url "URL" --csv --output results.csv
```

### Generate Markdown report

```bash
python youtube_scraper.py --url "URL" --report --output report.md
```

### Analyze a playlist

```bash
python youtube_scraper.py --playlist "https://www.youtube.com/playlist?list=PL..."
```

Fast mode (default) — gets title/duration/views per video without loading each page individually.

For full per-video metadata (slow):
```bash
python youtube_scraper.py --playlist "URL" --full-playlist
```

### Get only URLs from any mode

```bash
# From search:
python youtube_scraper.py --search "topic" --search-limit 10 --urls-only

# From batch:
python youtube_scraper.py --batch existing_urls.txt --urls-only

# From playlist:
python youtube_scraper.py --playlist "https://www.youtube.com/playlist?list=PL..." --urls-only
```

### Batch process from a file

```bash
# urls.txt: one YouTube URL per line, # = comment
python youtube_scraper.py --batch examples/urls.txt --output batch.json
```

With concurrent workers (default: 3):
```bash
python youtube_scraper.py --batch urls.txt --workers 5
```

### Check subtitle availability

```bash
python youtube_scraper.py --url "URL" --subtitles
```

Download subtitle files (SRT format, English):
```bash
python youtube_scraper.py --url "URL" --subtitles --download-subs --subtitle-lang en
```

Other languages and formats:
```bash
python youtube_scraper.py --url "URL" --subtitles --subtitle-lang es --subtitle-format vtt
```

### Download audio only (MP3)

```bash
python youtube_scraper.py --url "URL" --download-audio
```

Custom format (WAV, FLAC, M4A, AAC):
```bash
python youtube_scraper.py --url "URL" --download-audio --audio-format wav
```

### Download video (MP4)

```bash
python youtube_scraper.py --url "URL" --download-video
```

Custom format and directory:
```bash
python youtube_scraper.py --url "URL" --download-video --video-format mkv --download-dir ~/Videos
```

### Verbose mode (see what yt-dlp is doing)

```bash
python youtube_scraper.py --url "URL" --verbose
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
  "tags": ["rick astley", "never gonna give you up"],
  "categories": ["Music"],
  "language": "en",
  "age_limit": 0,
  "availability": "public",
  "live_status": "not_live",
  "has_chapters": false,
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

## Project Architecture

Understanding how the code is organized:

```
scripts/
├── youtube_scraper.py      # ENTRY POINT — CLI, routing, output
├── config.py               # All settings and defaults in one place
│
├── extractor/              # DATA FETCHING layer (yt-dlp wrappers)
│   ├── video_extractor.py     # Single video metadata
│   ├── playlist_extractor.py  # Playlist + per-video data
│   ├── subtitle_extractor.py  # Subtitle availability + download
│   └── downloader.py          # File downloads (video/audio)
│
├── formatter/              # OUTPUT RENDERING layer
│   ├── json_formatter.py      # JSON serialization + file writing
│   ├── csv_formatter.py       # Flat CSV export
│   └── markdown_formatter.py  # Human-readable Markdown reports
│
├── reports/
│   └── report_generator.py    # Glue: orchestrates extraction + formatting + terminal display
│
└── utils/                  # SHARED UTILITIES
    ├── logger.py              # Centralized logging (rich + file)
    ├── validators.py          # URL validation, batch file validation
    ├── helpers.py             # Pure functions: format numbers, dates, durations
    └── error_handler.py       # Custom exceptions, yt-dlp error classification
```

**Data flow:**
```
User runs CLI
     ↓
youtube_scraper.py (parse args, route)
     ↓
extractor/*.py (call yt-dlp → shape data)
     ↓
formatter/*.py (render data → JSON/CSV/Markdown)
     ↓
Output to terminal or file
```

**Why this separation?**
- Each layer has one job and doesn't know about the others
- You can swap formatters without touching extractors
- Easy to add new extractors (e.g., channel_extractor.py) without changing existing code
- Utils are reusable everywhere without circular imports

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

For batch runs: failed URLs are recorded in the output but don't stop processing.

---

## Running Tests

```bash
cd ~/.claude/skills/youtube-scraper/scripts

# Run all tests
python -m pytest tests/ -v

# Run specific test file
python -m pytest tests/test_validators.py -v
python -m pytest tests/test_helpers.py -v
python -m pytest tests/test_formatters.py -v

# Or run directly (no pytest needed)
python tests/test_validators.py
python tests/test_helpers.py
python tests/test_formatters.py
```

Tests cover:
- URL validation (video, playlist, channel, invalid URLs)
- Helper functions (formatting, safe access)
- Formatters (JSON, CSV, Markdown output)

No network calls are made in tests — all use mock data.

---

## Troubleshooting

### "Module not found: yt_dlp"
```bash
pip install yt-dlp
```

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

---

## Future Roadmap

Suggested next improvements:

| Feature | Status | Complexity | Value |
|---------|--------|-----------|-------|
| YouTube search integration | ✅ Done | — | — |
| NotebookLM pipeline (`--urls-only`) | ✅ Done | — | — |
| Pipeline mode with filters | ✅ Done | — | — |
| Channel extractor | Pending | Medium | High |
| SQLite storage | Pending | Medium | High |
| Transcript text extraction | Pending | Low | High |
| Keyword/topic extraction (NLP) | Pending | Medium | Medium |
| Sentiment analysis on comments | Pending | High | Medium |
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
- Is intended for research, analysis, and content discovery

Do not use this to mass-download copyrighted content or violate YouTube's Terms of Service.
