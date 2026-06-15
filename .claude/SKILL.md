---
name: youtube-scraper
description: >
  Production-grade YouTube scraper and metadata extraction system using yt-dlp.
  Use this skill whenever the user wants to scrape YouTube content, extract video
  metadata, search YouTube by keyword, build a research pipeline (search → NotebookLM
  → analysis → deliverables), analyze playlists, process batch YouTube URLs,
  get subtitles/captions, or optionally download video/audio. Triggers on:
  "search YouTube for", "find videos about", "get info about this YouTube link",
  "scrape this YouTube video", "extract metadata from this URL", "analyze this playlist",
  "get subtitles from this video", "process these YouTube URLs", "download this video",
  "download only audio", "batch process YouTube links", "what are the stats on this video",
  "add YouTube videos to NotebookLM", "research [topic] using YouTube + NotebookLM".
  Use even when the user just pastes a YouTube URL and asks anything about it.
compatibility:
  tools:
    - Bash
    - Read
    - Write
  dependencies:
    - python3
    - yt-dlp
    - rich
    - tqdm
    - ffmpeg (system package, required only for --download-audio/--download-video)
---

# YouTube Scraper Skill

A production-style YouTube scraper using yt-dlp. Extracts rich structured metadata,
searches YouTube by keyword, and feeds results into NotebookLM for AI analysis.
Downloading is NEVER the default.

## Skill Location

The entry point is `scripts/youtube_scraper.py` in the skill directory. That is the only file you need to invoke.

## Setup (do this once per machine)

```bash
SKILL_DIR="$HOME/.claude/skills/youtube-scraper"
pip install yt-dlp
pip install -r "$SKILL_DIR/requirements.txt"
```

---

## Autonomy Rule

**When the user describes a research pipeline (search → NotebookLM → analysis), run ALL steps without stopping to ask for confirmation.**

Do NOT stop after search to ask "should I add these to NotebookLM?" or "which URLs do you want?" — proceed through the full 4-step pipeline. The user said research; that means the complete workflow. Only pause if a step fails with an error.

---

## How to Use This Skill

### Step 1: Understand the user's intent

| User says | Mode | CLI flags |
|-----------|------|-----------|
| "get info / scrape / metadata" | single video | `--url URL` |
| "search YouTube for X" | keyword search | `--search "X"` |
| "find top N videos about X" | search with limit | `--search "X" --search-limit N` |
| "research X, add to NotebookLM" | **search → NotebookLM** | `--search "X" --urls-only` then `notebooklm source add` loop |
| "analyze playlist" | playlist | `--playlist URL` |
| "batch / multiple URLs" | batch | `--batch file.txt` |
| "get subtitles / captions" | subtitles (local only) | `--url URL --subtitles` |
| "download video" | download | `--url URL --download-video` |
| "download audio / mp3" | audio | `--url URL --download-audio` |
| "generate report" | markdown report | `--url URL --report` |
| "save as JSON / CSV" | export | `--output out.json` / `--csv` |

### Step 2: Run the appropriate command

**Always use the full path:**

```bash
SKILL_DIR="$HOME/.claude/skills/youtube-scraper/scripts"
python3 "$SKILL_DIR/youtube_scraper.py" [flags]
```

On Windows (PowerShell):
```powershell
$SKILL_DIR = "$env:USERPROFILE\.claude\skills\youtube-scraper\scripts"
python "$SKILL_DIR\youtube_scraper.py" [flags]
```

### Step 3: Read and present results

- If `--output` was used, read the file and summarize key fields
- For search: highlight title, channel, views, duration, URL
- Always note any errors encountered

---

## NotebookLM Research Pipeline (PRIMARY WORKFLOW)

This is the highest-value use of this skill. The pattern: **search → get URLs → NotebookLM does the analysis**.

### CRITICAL: Never use `--subtitles` to feed NotebookLM

`--subtitles` extracts captions locally. That is NOT the right approach for NotebookLM.
NotebookLM ingests YouTube URLs directly and indexes the transcript itself — for free.

**Wrong:**
```bash
# DON'T DO THIS for NotebookLM feeding
python youtube_scraper.py --url "URL" --subtitles  # then paste text into NotebookLM
```

**Correct — pass the URL directly:**
```bash
notebooklm source add "https://www.youtube.com/watch?v=VIDEO_ID" --notebook NOTEBOOK_ID
```

### Full Research Pipeline (4 steps)

**Step 1 — Search YouTube and get URLs:**
```bash
python "$SKILL_DIR/youtube_scraper.py" \
  --search "autoresearch karpathy" \
  --search-limit 10 \
  --urls-only \
  --output urls.txt
```

**Step 2 — Create a NotebookLM notebook:**
```bash
notebooklm create "My Research Topic" --json
# → note the notebook ID
```

**Step 3 — Add each URL as a NotebookLM source:**
```bash
# For each URL in urls.txt:
notebooklm source add "https://www.youtube.com/watch?v=..." --notebook NOTEBOOK_ID
# NotebookLM fetches and indexes the transcript automatically
```

**Step 4 — Ask for analysis and deliverables:**
```bash
notebooklm ask "What are the top insights from these videos?" --notebook NOTEBOOK_ID
notebooklm generate infographic "Summary of key concepts" --notebook NOTEBOOK_ID --orientation portrait --style sketch-note
```

### Why this works better than local subtitle extraction

- NotebookLM's RAG system handles the analysis — zero Claude tokens spent
- Full transcript quality (not just auto-captions)
- Can ask follow-up questions, generate podcasts, infographics, study guides
- Up to 50 YouTube sources per notebook

---

## Common Commands

### Single video metadata
```bash
python3 "$SKILL_DIR/youtube_scraper.py" --url "https://www.youtube.com/watch?v=VIDEO_ID"
```

### Search YouTube by keyword
```bash
python3 "$SKILL_DIR/youtube_scraper.py" --search "claude code tutorial" --search-limit 10
```

### Search and get URLs only (for NotebookLM)
```bash
python3 "$SKILL_DIR/youtube_scraper.py" \
  --search "autoresearch machine learning" \
  --search-limit 15 \
  --urls-only \
  --output urls.txt
```

### Search with filters (recent, long-form)
```bash
python3 "$SKILL_DIR/youtube_scraper.py" \
  --search "claude code" \
  --search-limit 20 \
  --pipeline \
  --filter-min-views 10000 \
  --filter-min-duration 300 \
  --filter-max-age-days 90 \
  --pipeline-top 10 \
  --urls-only
```

### Batch from file
```bash
python3 "$SKILL_DIR/youtube_scraper.py" --batch urls.txt --output batch_results.json
```

### Get URLs from batch results
```bash
python3 "$SKILL_DIR/youtube_scraper.py" --batch urls.txt --urls-only
```

### Playlist analysis
```bash
python3 "$SKILL_DIR/youtube_scraper.py" --playlist "https://www.youtube.com/playlist?list=PL..."
```

### Subtitles (local use only — NOT for NotebookLM)
```bash
python3 "$SKILL_DIR/youtube_scraper.py" --url "URL" --subtitles --subtitle-lang en
```

### Save JSON output
```bash
python3 "$SKILL_DIR/youtube_scraper.py" --url "URL" --output results.json
```

### Markdown report
```bash
python3 "$SKILL_DIR/youtube_scraper.py" --url "URL" --report --output report.md
```

### Download audio (MP3)
```bash
python3 "$SKILL_DIR/youtube_scraper.py" --url "URL" --download-audio
```

### Download video (MP4)
```bash
python3 "$SKILL_DIR/youtube_scraper.py" --url "URL" --download-video
```

---

## Search & Pipeline Flags

| Flag | Default | Description |
|------|---------|-------------|
| `--search "query"` | — | Search YouTube by keyword |
| `--search-limit N` | 10 | Max results per query |
| `--pipeline` | off | After search, fetch full metadata for top results |
| `--pipeline-top N` | 3 | How many results to fully extract |
| `--filter-min-views N` | — | Minimum view count filter |
| `--filter-min-duration SECS` | — | Minimum duration filter |
| `--filter-max-duration SECS` | — | Maximum duration filter |
| `--filter-max-age-days N` | — | Only videos uploaded within N days |
| `--urls-only` | off | Output only URLs, one per line |

---

## Error Handling

| Error type | Meaning |
|------------|---------|
| `VideoUnavailable` | Video deleted or private |
| `AgeRestricted` | Needs authentication |
| `GeoBlocked` | Not available in region |
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

## Important Notes

- **Never download by default** — metadata only unless `--download-video` or `--download-audio`
- **For NotebookLM**: pass YouTube URLs directly, never extract subtitles locally
- **Public content only** — no authentication or cookies by default
- **Rate limiting** — yt-dlp handles retries automatically for large batches
- Downloads go to the `outputs/` directory by default
