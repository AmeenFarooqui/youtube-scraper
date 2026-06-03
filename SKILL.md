---
name: youtube-scraper
description: >
  Production-grade YouTube scraper and metadata extraction system using yt-dlp.
  Use this skill whenever the user wants to scrape YouTube content, extract video
  metadata, analyze playlists, get subtitles/captions, process batch YouTube URLs,
  or optionally download video/audio. Triggers on: "get info about this YouTube link",
  "scrape this YouTube video", "extract metadata from this URL", "analyze this playlist",
  "get subtitles from this video", "process these YouTube URLs", "download this video",
  "download only audio", "batch process YouTube links", "what are the stats on this video",
  "show me the formats available for this video". Use even when the user just pastes a
  YouTube URL and asks anything about it.
compatibility:
  tools:
    - Bash
    - Read
    - Write
  dependencies:
    - python3
    - yt-dlp (pip install yt-dlp)
---

# YouTube Scraper Skill

A production-style YouTube scraper using yt-dlp. Extracts rich structured metadata,
generates reports, and optionally downloads content. Downloading is NEVER the default.

## Skill Location

All scripts live in the `scripts/` directory next to this SKILL.md file:

```
~/.claude/skills/youtube-scraper/
├── SKILL.md
├── README.md
├── requirements.txt
├── examples/
│   └── urls.txt
└── scripts/
    ├── youtube_scraper.py      # Main CLI entry point
    ├── config.py               # All defaults and constants
    ├── extractor/              # yt-dlp wrappers (one concern per file)
    │   ├── video_extractor.py
    │   ├── playlist_extractor.py
    │   ├── subtitle_extractor.py
    │   └── downloader.py
    ├── formatter/              # Output formatters
    │   ├── json_formatter.py
    │   ├── csv_formatter.py
    │   └── markdown_formatter.py
    ├── reports/
    │   └── report_generator.py
    └── utils/
        ├── logger.py
        ├── validators.py
        ├── helpers.py
        └── error_handler.py
```

## Setup (do this once per machine)

```bash
# 1. Install yt-dlp
pip install yt-dlp

# 2. Optional but recommended: also install rich, tqdm, pandas
pip install -r ~/.claude/skills/youtube-scraper/requirements.txt

# 3. On Windows you may need ffmpeg for audio conversion
#    Download from https://ffmpeg.org/download.html and add to PATH
```

Check installation:
```bash
python3 -c "import yt_dlp; print(yt_dlp.version.__version__)"
```

## How to Use This Skill

### Step 1: Understand the user's intent

Map what the user wants to one of these modes:

| User says | Mode | CLI flag |
|-----------|------|----------|
| "get info / scrape / metadata / analyze" | metadata only | `--url URL` |
| "analyze playlist" | playlist mode | `--playlist URL` |
| "batch / multiple URLs / text file" | batch mode | `--batch file.txt` |
| "get subtitles / captions" | subtitle mode | `--url URL --subtitles` |
| "download video" | download video | `--url URL --download-video` |
| "download audio / mp3" | download audio | `--url URL --download-audio` |
| "generate report" | markdown report | `--url URL --report` |
| "save as JSON / CSV" | export | `--output out.json` / `--csv` |

### Step 2: Run the appropriate command

The script is at `~/.claude/skills/youtube-scraper/scripts/youtube_scraper.py`.

**Always use the full path when running:**

```bash
SKILL_DIR="$HOME/.claude/skills/youtube-scraper/scripts"
python3 "$SKILL_DIR/youtube_scraper.py" [flags]
```

### Step 3: Read and present results

After running:
- If `--output` was specified, read the output file and summarize key fields
- If `--report` was specified, display the markdown directly
- Always highlight: title, channel, views, duration, upload date, available formats
- Note any warnings or errors encountered

---

## Common Commands

### Single video metadata
```bash
python3 "$HOME/.claude/skills/youtube-scraper/scripts/youtube_scraper.py" \
  --url "https://www.youtube.com/watch?v=VIDEO_ID"
```

### Save JSON output
```bash
python3 "$HOME/.claude/skills/youtube-scraper/scripts/youtube_scraper.py" \
  --url "URL" --output results.json
```

### CSV export
```bash
python3 "$HOME/.claude/skills/youtube-scraper/scripts/youtube_scraper.py" \
  --url "URL" --csv --output results.csv
```

### Markdown report
```bash
python3 "$HOME/.claude/skills/youtube-scraper/scripts/youtube_scraper.py" \
  --url "URL" --report --output report.md
```

### Playlist analysis
```bash
python3 "$HOME/.claude/skills/youtube-scraper/scripts/youtube_scraper.py" \
  --playlist "https://www.youtube.com/playlist?list=PLAYLIST_ID"
```

### Batch from file
```bash
python3 "$HOME/.claude/skills/youtube-scraper/scripts/youtube_scraper.py" \
  --batch urls.txt --output batch_results.json
```

### Subtitles
```bash
python3 "$HOME/.claude/skills/youtube-scraper/scripts/youtube_scraper.py" \
  --url "URL" --subtitles --subtitle-lang en
```

### Download audio only (MP3)
```bash
python3 "$HOME/.claude/skills/youtube-scraper/scripts/youtube_scraper.py" \
  --url "URL" --download-audio
```

### Download video (MP4)
```bash
python3 "$HOME/.claude/skills/youtube-scraper/scripts/youtube_scraper.py" \
  --url "URL" --download-video
```

### Download with custom format
```bash
python3 "$HOME/.claude/skills/youtube-scraper/scripts/youtube_scraper.py" \
  --url "URL" --download-video --video-format mkv
```

---

## Error Handling

The scraper classifies errors automatically:

| Error type | Meaning |
|------------|---------|
| `VideoUnavailable` | Video was deleted or made private |
| `PrivateVideo` | Video is private |
| `AgeRestricted` | Age-restricted, needs authentication |
| `GeoBlocked` | Not available in current region |
| `NetworkError` | Connection issues |
| `RateLimited` | Too many requests |

For batch runs: failed URLs are logged but processing continues.

---

## Output Fields Reference

Key fields in the JSON output:

```
id, title, description, upload_date, duration, view_count, like_count,
comment_count, channel, channel_id, uploader, tags, categories,
thumbnail, formats (list), subtitles (dict), automatic_captions (dict),
chapters (list), availability, live_status, language, age_limit
```

---

## When ffmpeg Is Missing

Audio downloads (`--download-audio`) require ffmpeg for MP3 conversion.
Video merging (best quality) also requires ffmpeg.

If ffmpeg is missing, tell the user:
- Linux: `sudo apt install ffmpeg`
- Mac: `brew install ffmpeg`
- Windows: Download from ffmpeg.org, add to PATH

---

## Important Notes

- **Never download by default** — metadata extraction only unless `--download-video` or `--download-audio` is passed
- **Public content only** — this tool does not support authentication or cookies by default
- **Rate limiting** — for large playlists/batches, yt-dlp handles retries automatically
- Downloads go to the `outputs/` directory by default
- All operations are read-only with respect to YouTube (no mutations)
