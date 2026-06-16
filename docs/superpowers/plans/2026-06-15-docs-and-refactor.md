# Docs + Orchestration Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix 6 documentation inaccuracies and simplify `youtube_scraper.py` by extracting 4 helpers and splitting `build_parser()`, without changing any user-visible behavior.

**Architecture:** Documentation fixes are pure text edits with no code risk. Code refactors are pure structural moves — no logic changes. Every extracted helper produces identical results to the original inline code. Tests validate behavior before and after each structural change.

**Tech Stack:** Python 3.12, argparse, unittest (stdlib), pytest (test runner)

---

## File Map

**Modified:**
- `README.md` — 5 text fixes
- `.claude/SKILL.md` — maturity language
- `pyproject.toml` — add `[project.optional-dependencies]`
- `scripts/youtube_scraper.py` — all code refactors
- `scripts/reports/report_generator.py` — docstring fix
- `scripts/tests/test_cli_behaviors.py` — new tests for 3 helpers

---

## Task 1: Documentation fixes

**Files:** `README.md`, `.claude/SKILL.md`, `pyproject.toml`

### 1a — Standardize command location in README

The Usage section header (line ~150) says "All commands run from the `scripts/` directory" but Quickstart uses `python scripts/youtube_scraper.py` from repo root.

- [ ] Find this block in `README.md`:
```
## Usage

All commands run from the `scripts/` directory, or pass the full path:

```bash
cd youtube-scraper/scripts
```
```
Replace with:
```
## Usage

All commands run from the repo root. The entry point is `scripts/youtube_scraper.py`:
```
(Delete the `cd` code block entirely.)

### 1b — Fix wrong flag in channel example

Around line 225, `--search-limit 50` is used in a `--channel` command. Channels use `--max-videos`.

- [ ] Find:
```
  --search-limit 50 \
```
inside the channel example block. Replace with:
```
  --max-videos 50 \
```

### 1c — Update stale likes-filter limitation text

Around line 771, the text says filters "silently drop all results". The code now emits a WARNING and fails at parse time for `--search` mode.

- [ ] Find the paragraph starting "Search results are stubs — `like_count` is often `None`" through the end of its code block. Replace with:

```markdown
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
```

### 1d — Mark transcript as Done in roadmap

Around line 848, the roadmap table has:
```
| Transcript text extraction | Pending | Low | High |
```

- [ ] Replace with:
```
| Transcript text extraction (`--transcript`) | Done | — | — |
```

### 1e — Testing section: add pytest install step

Around line 700, the Running Tests section shows `python -m pytest` without explaining pytest must be installed.

- [ ] Replace the Running Tests section with:

```markdown
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
```

### 1f — Fix SKILL.md maturity language

In `.claude/SKILL.md` line 3, `description:` block says "Production-grade".

- [ ] Change `Production-grade` → `Feature-complete` in the description block.
- [ ] Change "A production-style YouTube scraper" in the body to "A feature-complete YouTube scraper".

### 1g — Add dev dependencies to pyproject.toml

`pytest` is not listed anywhere in `pyproject.toml`.

- [ ] After the `[project.urls]` block, add:
```toml
[project.optional-dependencies]
dev = [
    "pytest>=7.0",
]
```

- [ ] **Commit:**
```bash
git add README.md .claude/SKILL.md pyproject.toml
git commit -m "docs: fix 6 README/SKILL/pyproject inaccuracies

- Standardize commands to repo-root style (python scripts/...)
- Fix channel example: --search-limit -> --max-videos
- Update likes-filter text (warns + parse-time error, no longer silent)
- Mark transcript extraction as Done in roadmap
- Add pytest install step + unittest alternative to testing docs
- Fix SKILL.md: production-grade -> feature-complete
- Add [project.optional-dependencies] dev = [pytest>=7.0]

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

- [ ] **Verify:** `python -m pytest scripts/tests/ -v` → 94 passed

---

## Task 2: Extract `_validate_args(parser, args)`

**Files:** `scripts/youtube_scraper.py`

The ~130-line validation block inside `main()` becomes a standalone function, making `main()` scannable. No logic changes — identical checks, identical error messages.

- [ ] **Add function** immediately before `def main() -> None:`:

```python
def _validate_args(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    """
    Validate parsed CLI arguments and call parser.error() for any invalid combination.

    Groups:
      1. Mutually exclusive flags
      2. Dependency rules (X requires Y)
      3. Numeric range bounds
      4. Mode-specific flag restrictions
    """
    # ── 1. Mutually exclusive ─────────────────────────────────────────────────
    if getattr(args, "download_video", False) and getattr(args, "download_audio", False):
        parser.error("--download-video and --download-audio are mutually exclusive. Use one at a time.")
    if getattr(args, "subtitles", False) and (getattr(args, "download_video", False) or getattr(args, "download_audio", False)):
        parser.error("--subtitles cannot be combined with --download-video or --download-audio. Use separate commands.")
    if args.search and args.subtitles:
        parser.error("--search and --subtitles are incompatible. Subtitles require a single video URL (use --url).")
    if args.search and args.url:
        parser.error("--search and --url are mutually exclusive. Use one input mode at a time.")
    if args.batch and args.search:
        parser.error("--batch and --search are mutually exclusive. --batch takes a file of URLs; --search takes a keyword.")
    _output_modes = sum([
        bool(getattr(args, "report", False)),
        bool(getattr(args, "csv", False)),
        bool(getattr(args, "urls_only", False)),
    ])
    if _output_modes > 1:
        parser.error("--report, --csv, and --urls-only are mutually exclusive. Use only one.")

    # ── 2. Dependency rules ───────────────────────────────────────────────────
    if getattr(args, "sentiment", False) and not getattr(args, "comments", False):
        parser.error("--sentiment requires --comments to be enabled.")
    if getattr(args, "transcript", False) and not (args.search or args.search_batch):
        parser.error("--transcript requires --search or --search-batch.")
    if getattr(args, "transcript", False) and (args.search or args.search_batch) and not args.pipeline:
        parser.error("--transcript requires --pipeline (e.g. --search --pipeline --transcript).")
    if getattr(args, "download_subs", False) and not getattr(args, "subtitles", False):
        parser.error("--download-subs requires --subtitles.")
    if getattr(args, "sort_by", None) == "dislikes" and not getattr(args, "dislikes", False):
        parser.error("--sort-by dislikes requires --dislikes.")
    if getattr(args, "sort_by", None) in ("positive_ratio", "negative_ratio"):
        if not getattr(args, "sentiment", False):
            parser.error(f"--sort-by {args.sort_by} requires --comments and --sentiment.")
    if getattr(args, "filter_min_dislikes", None) is not None and not getattr(args, "dislikes", False):
        parser.error("--filter-min-dislikes requires --dislikes.")
    if getattr(args, "filter_max_dislikes", None) is not None and not getattr(args, "dislikes", False):
        parser.error("--filter-max-dislikes requires --dislikes.")
    for _ratio_arg in ("filter_min_positive_ratio", "filter_min_negative_ratio"):
        _val = getattr(args, _ratio_arg, None)
        if _val is not None:
            if not (0.0 <= _val <= 1.0):
                parser.error(f"--{_ratio_arg.replace('_', '-')} must be between 0.0 and 1.0, got {_val}")
            if not getattr(args, "sentiment", False):
                parser.error(f"--{_ratio_arg.replace('_', '-')} requires --comments and --sentiment.")

    # ── 3. Numeric range bounds ───────────────────────────────────────────────
    for _count_arg, _flag in (
        ("search_limit", "--search-limit"),
        ("pipeline_top", "--pipeline-top"),
        ("comments_max", "--comments-max"),
        ("max_videos",   "--max-videos"),
    ):
        _val = getattr(args, _count_arg, None)
        if _val is not None and _val < 1:
            parser.error(f"{_flag} must be >= 1, got {_val}")
    if args.cache_ttl <= 0:
        parser.error(f"--cache-ttl must be > 0, got {args.cache_ttl}")
    for _attr, _flag in [
        ("filter_min_views",       "--filter-min-views"),
        ("filter_max_views",       "--filter-max-views"),
        ("filter_min_likes",       "--filter-min-likes"),
        ("filter_max_likes",       "--filter-max-likes"),
        ("filter_min_subscribers", "--filter-min-subscribers"),
        ("filter_max_subscribers", "--filter-max-subscribers"),
        ("filter_min_dislikes",    "--filter-min-dislikes"),
        ("filter_max_dislikes",    "--filter-max-dislikes"),
    ]:
        _val = getattr(args, _attr, None)
        if _val is not None and _val < 0:
            parser.error(f"{_flag} must be >= 0")
    for _vmin_attr, _vmax_attr, _flag_min, _flag_max in [
        ("filter_min_views",       "filter_max_views",       "--filter-min-views",       "--filter-max-views"),
        ("filter_min_likes",       "filter_max_likes",       "--filter-min-likes",       "--filter-max-likes"),
        ("filter_min_subscribers", "filter_max_subscribers", "--filter-min-subscribers", "--filter-max-subscribers"),
        ("filter_min_dislikes",    "filter_max_dislikes",    "--filter-min-dislikes",    "--filter-max-dislikes"),
    ]:
        _vmin = getattr(args, _vmin_attr, None)
        _vmax = getattr(args, _vmax_attr, None)
        if _vmin is not None and _vmax is not None and _vmin > _vmax:
            parser.error(f"{_flag_min} ({_vmin}) must be <= {_flag_max} ({_vmax})")
    if getattr(args, "filter_max_age_days", None) is not None and args.filter_max_age_days < 1:
        parser.error("--filter-max-age-days must be >= 1")
    _min_dur = getattr(args, "filter_min_duration", None)
    _max_dur = getattr(args, "filter_max_duration", None)
    if _min_dur is not None and _min_dur < 0:
        parser.error("--filter-min-duration must be >= 0")
    if _max_dur is not None and _max_dur < 0:
        parser.error("--filter-max-duration must be >= 0")
    if _min_dur is not None and _max_dur is not None and _min_dur > _max_dur:
        parser.error(f"--filter-min-duration ({_min_dur}) must be <= --filter-max-duration ({_max_dur})")

    # ── 4. Mode-specific restrictions ─────────────────────────────────────────
    if args.search and not getattr(args, "pipeline", False):
        for _attr, _flag in [
            ("filter_min_likes",       "--filter-min-likes"),
            ("filter_max_likes",       "--filter-max-likes"),
            ("filter_min_subscribers", "--filter-min-subscribers"),
            ("filter_max_subscribers", "--filter-max-subscribers"),
        ]:
            if getattr(args, _attr, None) is not None:
                parser.error(
                    f"{_flag} requires --pipeline in search mode: flat search stubs lack "
                    "like_count and channel_follower_count. Add --pipeline to get full metadata."
                )
    _list_mode = any([
        args.search, getattr(args, "search_batch", None),
        args.batch, args.channel, args.playlist,
    ])
    if not _list_mode and args.url:
        for _attr, _flag in [
            ("filter_min_views",          "--filter-min-views"),
            ("filter_max_age_days",       "--filter-max-age-days"),
            ("filter_min_duration",       "--filter-min-duration"),
            ("filter_max_duration",       "--filter-max-duration"),
            ("filter_min_likes",          "--filter-min-likes"),
            ("filter_max_likes",          "--filter-max-likes"),
            ("filter_min_subscribers",    "--filter-min-subscribers"),
            ("filter_max_subscribers",    "--filter-max-subscribers"),
            ("filter_min_dislikes",       "--filter-min-dislikes"),
            ("filter_max_dislikes",       "--filter-max-dislikes"),
            ("filter_min_positive_ratio", "--filter-min-positive-ratio"),
            ("filter_min_negative_ratio", "--filter-min-negative-ratio"),
            ("no_shorts",                 "--no-shorts"),
            ("sort_by",                   "--sort-by"),
        ]:
            if getattr(args, _attr, None) not in (None, False):
                parser.error(
                    f"{_flag} is only valid in list-producing modes "
                    "(--search, --batch, --channel, --playlist, --search-batch)."
                )
```

- [ ] **Replace the validation block in `main()`** — find the comment `# ── Fast-fail: incompatible flag combinations` through the last `parser.error(...)` call before `logger = get_logger(...)`. Replace the entire block with:
```python
    _validate_args(parser, args)
```

- [ ] **Verify:** `python -m pytest scripts/tests/test_cli_behaviors.py -v` → all 9 existing tests pass

- [ ] **Commit:**
```bash
git add scripts/youtube_scraper.py
git commit -m "refactor: extract _validate_args(parser, args) from main()

Moves ~130 lines of parser.error() validation into a standalone function.
No behavior change — identical checks and error messages.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 3: Add `_result_items(data)` helper, use in `handle_output`

**Files:** `scripts/youtube_scraper.py`, `scripts/tests/test_cli_behaviors.py`

Both the Markdown branch and CSV branch of `handle_output` independently duplicate item-extraction logic (checking `_ext`, calling `.get("results")` or `.get("videos")`). One pure function replaces both.

- [ ] **Write tests first** — add class to `test_cli_behaviors.py`:

```python
class TestResultItems(unittest.TestCase):
    """Tests for the _result_items(data) shape-normalizer."""

    def test_list_returned_as_is(self):
        items = [{"id": "a"}, {"id": "b"}]
        self.assertEqual(youtube_scraper._result_items(items), items)

    def test_search_extractor(self):
        data = {"_extractor": "SearchExtractor", "results": [{"id": "x"}]}
        self.assertEqual(youtube_scraper._result_items(data), [{"id": "x"}])

    def test_pipeline_extractor(self):
        data = {"_extractor": "PipelineExtractor", "videos": [{"id": "y"}]}
        self.assertEqual(youtube_scraper._result_items(data), [{"id": "y"}])

    def test_channel_extractor(self):
        data = {"_extractor": "ChannelExtractor", "videos": [{"id": "z"}]}
        self.assertEqual(youtube_scraper._result_items(data), [{"id": "z"}])

    def test_playlist_extractor(self):
        data = {"_extractor": "PlaylistExtractor", "videos": [{"id": "p"}]}
        self.assertEqual(youtube_scraper._result_items(data), [{"id": "p"}])

    def test_batch_queries_flattened(self):
        data = {
            "total_queries": 2,
            "queries": [
                {"results": [{"id": "a"}, {"id": "b"}]},
                {"videos": [{"id": "c"}]},
            ],
        }
        self.assertEqual([i["id"] for i in youtube_scraper._result_items(data)], ["a", "b", "c"])

    def test_single_video_dict(self):
        data = {"_extractor": "VideoExtractor", "id": "abc", "title": "T"}
        self.assertEqual(youtube_scraper._result_items(data), [data])

    def test_empty_list(self):
        self.assertEqual(youtube_scraper._result_items([]), [])
```

- [ ] **Run to confirm failure:** `python -m pytest scripts/tests/test_cli_behaviors.py::TestResultItems -v`
  Expected: `AttributeError: module 'youtube_scraper' has no attribute '_result_items'`

- [ ] **Implement** above `_extract_urls` in `youtube_scraper.py`:

```python
def _result_items(data: dict | list) -> list[dict]:
    """
    Extract the flat list of video/result items from any result shape.

    Covers all extractor output shapes so callers don't repeat shape-detection.
    """
    if isinstance(data, list):
        return data
    if "queries" in data:          # search-batch or pipeline-batch
        items: list[dict] = []
        for q in data.get("queries", []):
            items.extend(q.get("videos") or q.get("results") or [])
        return items
    return (
        data.get("results")        # SearchExtractor
        or data.get("videos")      # Pipeline/Channel/Playlist
        or ([data] if data.get("id") or data.get("title") else [])
    )
```

- [ ] **Run to confirm pass:** `python -m pytest scripts/tests/test_cli_behaviors.py::TestResultItems -v`
  Expected: 8 passed

- [ ] **Use in `handle_output`** — replace the Markdown branch item-extraction:

Old:
```python
        if is_search:
            content = fmt.format_batch(data.get("results", []))
        elif is_pipeline:
            content = fmt.format_batch(data.get("videos", []))
        elif is_channel:
            content = fmt.format_batch(data.get("videos", []))
        elif is_batch_res:
            all_videos = []
            for q in data.get("queries", []):
                all_videos.extend(q.get("videos") or q.get("results") or [])
            content = fmt.format_batch(all_videos)
        elif is_playlist:
            content = fmt.format_playlist(data)
        elif is_batch:
            content = fmt.format_batch(data)
        else:
            content = fmt.format_video(data)
```

New:
```python
        if is_playlist:
            content = fmt.format_playlist(data)
        elif not (is_search or is_pipeline or is_channel or is_batch_res or is_batch):
            content = fmt.format_video(data)
        else:
            content = fmt.format_batch(_result_items(data))
```

Replace the CSV branch item-extraction:

Old:
```python
        if is_search:
            rows = data.get("results", [])
            _csv_out(fmt.format_many(rows), rows)
        elif is_pipeline:
            rows = data.get("videos", [])
            _csv_out(fmt.format_many(rows), rows)
        elif is_channel:
            rows = data.get("videos", [])
            _csv_out(fmt.format_many(rows), rows)
        elif is_batch_res:
            rows = []
            for q in data.get("queries", []):
                rows.extend(q.get("videos") or q.get("results") or [])
            _csv_out(fmt.format_many(rows), rows)
        elif is_playlist:
            _csv_out(fmt.format_playlist(data), data)
        elif is_batch:
            _csv_out(fmt.format_many(data), data)
        else:
            _csv_out(fmt.format(data), data)
```

New:
```python
        if is_playlist:
            _csv_out(fmt.format_playlist(data), data)
        elif not (is_search or is_pipeline or is_channel or is_batch_res or is_batch):
            _csv_out(fmt.format(data), data)
        else:
            rows = _result_items(data)
            _csv_out(fmt.format_many(rows), rows)
```

- [ ] **Run all tests:** `python -m pytest scripts/tests/ -v` → 102 passed

- [ ] **Commit:**
```bash
git add scripts/youtube_scraper.py scripts/tests/test_cli_behaviors.py
git commit -m "refactor: add _result_items(), deduplicate handle_output item-extraction

Both Markdown and CSV output branches independently extracted items from
each result shape. _result_items(data) centralizes this in one place.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 4: Add `_run_ordered` helper, use in batch handlers

**Files:** `scripts/youtube_scraper.py`, `scripts/tests/test_cli_behaviors.py`

`handle_search_batch` and `handle_pipeline_batch` use the identical ThreadPoolExecutor + preallocated-list + as_completed ordered-map pattern.

- [ ] **Write tests first** — add class to `test_cli_behaviors.py`:

```python
class TestRunOrdered(unittest.TestCase):
    """Tests for the _run_ordered concurrent ordered-map helper."""

    def test_results_in_original_order(self):
        import time, random

        def slow_fn(index_item):
            i, val = index_item
            time.sleep(random.uniform(0, 0.02))
            return i, val * 10

        results = youtube_scraper._run_ordered([1, 2, 3, 4, 5], workers=5, fn=slow_fn)
        self.assertEqual(results, [10, 20, 30, 40, 50])

    def test_all_items_processed(self):
        def identity(index_item):
            i, val = index_item
            return i, val

        results = youtube_scraper._run_ordered(["a", "b", "c"], workers=2, fn=identity)
        self.assertEqual(results, ["a", "b", "c"])

    def test_empty_input(self):
        results = youtube_scraper._run_ordered([], workers=4, fn=lambda x: x)
        self.assertEqual(results, [])
```

- [ ] **Run to confirm failure:** `python -m pytest scripts/tests/test_cli_behaviors.py::TestRunOrdered -v`
  Expected: `AttributeError: module 'youtube_scraper' has no attribute '_run_ordered'`

- [ ] **Implement** above `handle_search_batch` in `youtube_scraper.py`:

```python
def _run_ordered(items: list, workers: int, fn) -> list:
    """
    Run fn(i, item) concurrently for each item, returning results in original order.

    fn must accept a (int, Any) tuple and return a (int, result) tuple.
    The integer index is used to reassemble results in submission order
    regardless of which futures complete first.
    """
    if not items:
        return []
    results = [None] * len(items)
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(fn, (i, item)): i for i, item in enumerate(items)}
        for future in as_completed(futures):
            i, result = future.result()
            results[i] = result
    return results
```

- [ ] **Run to confirm pass:** `python -m pytest scripts/tests/test_cli_behaviors.py::TestRunOrdered -v`
  Expected: 3 passed

- [ ] **Use in `handle_search_batch`** — replace the boilerplate:

Old:
```python
    results: list[dict | None] = [None] * len(queries)

    def _search(index_query: tuple[int, str]) -> tuple[int, dict]:
        i, q = index_query
        try:
            return i, extractor.search(q)
        except ScraperError as e:
            logger.warning(f"Search failed for {q!r}: {e.user_message}")
            return i, {"query": q, "error": e.user_message, "results": []}

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(_search, (i, q)): i for i, q in enumerate(queries)}
        for future in as_completed(futures):
            i, result = future.result()
            results[i] = result
```

New:
```python
    def _search(index_query: tuple[int, str]) -> tuple[int, dict]:
        i, q = index_query
        try:
            return i, extractor.search(q)
        except ScraperError as e:
            logger.warning(f"Search failed for {q!r}: {e.user_message}")
            return i, {"query": q, "error": e.user_message, "results": []}

    results = _run_ordered(queries, workers=args.workers, fn=_search)
```

- [ ] **Use in `handle_pipeline_batch`** — replace the boilerplate:

Old:
```python
    results: list[dict | None] = [None] * len(queries)

    def _run(index_query: tuple[int, str]) -> tuple[int, dict]:
        i, q = index_query
        try:
            return i, pipeline.run(q)
        except ScraperError as e:
            logger.warning(f"Pipeline failed for {q!r}: {e.user_message}")
            return i, {"query": q, "error": e.user_message, "videos": []}

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(_run, (i, q)): i for i, q in enumerate(queries)}
        for future in as_completed(futures):
            i, result = future.result()
            results[i] = result
```

New:
```python
    def _run(index_query: tuple[int, str]) -> tuple[int, dict]:
        i, q = index_query
        try:
            return i, pipeline.run(q)
        except ScraperError as e:
            logger.warning(f"Pipeline failed for {q!r}: {e.user_message}")
            return i, {"query": q, "error": e.user_message, "videos": []}

    results = _run_ordered(queries, workers=args.workers, fn=_run)
```

- [ ] **Run all tests:** `python -m pytest scripts/tests/ -v` → 105 passed

- [ ] **Commit:**
```bash
git add scripts/youtube_scraper.py scripts/tests/test_cli_behaviors.py
git commit -m "refactor: add _run_ordered(), deduplicate concurrent batch executor boilerplate

handle_search_batch and handle_pipeline_batch both had identical
ThreadPoolExecutor + preallocated-list + as_completed ordered-map code.
_run_ordered() centralizes it. No change to concurrency or output shape.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 5: Add `_post_process_items` helper, use in all list handlers

**Files:** `scripts/youtube_scraper.py`, `scripts/tests/test_cli_behaviors.py`

> **Highest-risk task** — touches 7 handlers. Read the behavior matrix carefully before editing any handler.

**Verified behavior matrix (from current code):**

| Handler | `apply_shorts` | `fetch_comments` | `shorts_first` | result key | count key |
|---------|:---:|:---:|:---:|---|---|
| `handle_playlist` | ✓ | ✓ | ✓ (first) | `"videos"` | `"total_videos"` |
| `handle_channel` | ✓ | ✓ | ✓ (first) | `"videos"` | `"total_videos"` |
| `handle_search` | ✓ | ✓ | ✓ (first) | `"results"` | `"total_results"` |
| `handle_search_batch` (per q) | ✓ | ✓ | ✓ (first) | `"results"` | `"total_results"` |
| `handle_pipeline` | ✗ | ✗ | — | `"videos"` | none |
| `handle_pipeline_batch` (per q) | ✓ | ✗ | ✗ (after enrichment) | `"videos"` | none |
| `handle_batch` (post-extraction) | ✓ | ✗ | ✗ (after enrichment) | list | N/A |

`shorts_first=False` preserves the existing behavior of `handle_batch` and `handle_pipeline_batch`, which filter shorts **after** dislikes+sentiment (the current code already does this).

- [ ] **Write tests first** — add class to `test_cli_behaviors.py`:

```python
class TestPostProcessItems(unittest.TestCase):
    """Tests for _post_process_items — verifies call order and parameter routing."""

    def _args(self, **kwargs):
        defaults = dict(
            comments=False, dislikes=False, sentiment=False,
            no_shorts=False, shorts_only=False, workers=2,
            filter_min_views=None, filter_max_views=None,
            filter_min_likes=None, filter_max_likes=None,
            filter_min_subscribers=None, filter_max_subscribers=None,
            filter_min_dislikes=None, filter_max_dislikes=None,
            filter_min_positive_ratio=None, filter_min_negative_ratio=None,
            sort_by=None, sort_order="desc",
        )
        defaults.update(kwargs)
        return argparse.Namespace(**defaults)

    @patch("youtube_scraper._apply_sort", side_effect=lambda items, _: items)
    @patch("youtube_scraper._apply_engagement_filters", side_effect=lambda items, _: items)
    @patch("youtube_scraper._apply_shorts_filter", side_effect=lambda items, _: items)
    def test_defaults_run_shorts_filter_and_pass_through(self, mock_s, mock_f, mock_sort):
        items = [{"id": "a"}]
        result = youtube_scraper._post_process_items(items, self._args())
        mock_s.assert_called_once()
        mock_f.assert_called_once()
        mock_sort.assert_called_once()
        self.assertEqual(result, items)

    @patch("youtube_scraper._apply_sort", side_effect=lambda items, _: items)
    @patch("youtube_scraper._apply_engagement_filters", side_effect=lambda items, _: items)
    @patch("youtube_scraper._apply_shorts_filter", side_effect=lambda items, _: items)
    @patch("youtube_scraper._fetch_full_metadata", side_effect=lambda items, _: items)
    def test_fetch_comments_true_with_comments_calls_fetch(self, mock_fetch, *_):
        youtube_scraper._post_process_items([{"id": "a"}], self._args(comments=True), fetch_comments=True)
        mock_fetch.assert_called_once()

    @patch("youtube_scraper._apply_sort", side_effect=lambda items, _: items)
    @patch("youtube_scraper._apply_engagement_filters", side_effect=lambda items, _: items)
    @patch("youtube_scraper._apply_shorts_filter", side_effect=lambda items, _: items)
    @patch("youtube_scraper._fetch_full_metadata", side_effect=lambda items, _: items)
    def test_fetch_comments_false_never_fetches(self, mock_fetch, *_):
        youtube_scraper._post_process_items([{"id": "a"}], self._args(comments=True), fetch_comments=False)
        mock_fetch.assert_not_called()

    @patch("youtube_scraper._apply_sort", side_effect=lambda items, _: items)
    @patch("youtube_scraper._apply_engagement_filters", side_effect=lambda items, _: items)
    @patch("youtube_scraper._apply_shorts_filter", side_effect=lambda items, _: items)
    @patch("youtube_scraper._enrich_dislikes", side_effect=lambda items, **kw: items)
    def test_dislikes_enabled_calls_enrich(self, mock_enrich, *_):
        youtube_scraper._post_process_items([{"id": "a"}], self._args(dislikes=True))
        mock_enrich.assert_called_once()

    @patch("youtube_scraper._apply_sort", side_effect=lambda items, _: items)
    @patch("youtube_scraper._apply_engagement_filters", side_effect=lambda items, _: items)
    @patch("youtube_scraper._apply_shorts_filter", side_effect=lambda items, _: items)
    def test_apply_shorts_false_skips_filter(self, mock_s, *_):
        youtube_scraper._post_process_items([{"id": "a"}], self._args(), apply_shorts=False)
        mock_s.assert_not_called()

    @patch("youtube_scraper._apply_sort", side_effect=lambda items, _: items)
    @patch("youtube_scraper._apply_engagement_filters", side_effect=lambda items, _: items)
    @patch("youtube_scraper._enrich_dislikes", side_effect=lambda items, **kw: items)
    @patch("youtube_scraper._apply_shorts_filter", side_effect=lambda items, _: items)
    def test_shorts_first_false_runs_after_dislikes(self, mock_s, mock_enrich, *_):
        """shorts_first=False means shorts filter executes after enrichment."""
        call_order = []
        mock_s.side_effect = lambda items, _: (call_order.append("shorts"), items)[1]
        mock_enrich.side_effect = lambda items, **kw: (call_order.append("dislikes"), items)[1]

        youtube_scraper._post_process_items(
            [{"id": "a"}], self._args(dislikes=True),
            apply_shorts=True, shorts_first=False,
        )
        self.assertEqual(call_order, ["dislikes", "shorts"])
```

- [ ] **Run to confirm failure:** `python -m pytest scripts/tests/test_cli_behaviors.py::TestPostProcessItems -v`
  Expected: `AttributeError: module 'youtube_scraper' has no attribute '_post_process_items'`

- [ ] **Implement** above `handle_playlist` in `youtube_scraper.py`:

```python
def _post_process_items(
    items: list[dict],
    args: argparse.Namespace,
    *,
    apply_shorts: bool = True,
    fetch_comments: bool = False,
    shorts_first: bool = True,
) -> list[dict]:
    """
    Shared post-processing pipeline for all list-producing handlers.

    Step order (all options, shorts_first=True):
      1. Shorts filter
      2. Full metadata + comments fetch
      3. Dislike enrichment (RYD API)
      4. Comment sentiment (VADER)
      5. Engagement filters
      6. Sort

    Parameters:
        apply_shorts:    Apply --no-shorts / --shorts-only. False for handle_pipeline
                         (pipeline already filters internally).
        fetch_comments:  Upgrade stubs to full metadata when --comments is set.
                         False for pipeline/batch (already full metadata).
        shorts_first:    True = shorts filter before enrichment (default).
                         False = shorts filter after enrichment (batch modes).
    """
    if apply_shorts and shorts_first:
        items = _apply_shorts_filter(items, args)
    if fetch_comments and getattr(args, "comments", False):
        logger.info(f"Fetching full metadata + comments for {len(items)} items...")
        items = _fetch_full_metadata(items, args)
    if getattr(args, "dislikes", False):
        items = _enrich_dislikes(items, workers=args.workers)
    if getattr(args, "sentiment", False):
        analyzer = SentimentAnalyzer()
        for item in items:
            if item.get("comments"):
                summary = analyzer.analyze(item["comments"])
                if summary:
                    item["sentiment_summary"] = summary
    if apply_shorts and not shorts_first:
        items = _apply_shorts_filter(items, args)
    items = _apply_engagement_filters(items, args)
    items = _apply_sort(items, args)
    return items
```

- [ ] **Run new tests:** `python -m pytest scripts/tests/test_cli_behaviors.py::TestPostProcessItems -v` → 6 passed

- [ ] **Refactor `handle_playlist`** — replace the `if result.get("videos"):` block body:

Old:
```python
    if result.get("videos"):
        items = result["videos"]
        items = _apply_shorts_filter(items, args)
        if getattr(args, "comments", False):
            logger.info(f"Fetching full metadata + comments for {len(items)} playlist videos...")
            items = _fetch_full_metadata(items, args)
        if getattr(args, "dislikes", False):
            items = _enrich_dislikes(items, workers=args.workers)
        if getattr(args, "sentiment", False):
            analyzer = SentimentAnalyzer()
            for item in items:
                if item.get("comments"):
                    summary = analyzer.analyze(item["comments"])
                    if summary:
                        item["sentiment_summary"] = summary
        items = _apply_engagement_filters(items, args)
        items = _apply_sort(items, args)
        result["videos"] = items
        result["total_videos"] = len(items)
```

New:
```python
    if result.get("videos"):
        result["videos"] = _post_process_items(
            result["videos"], args, apply_shorts=True, fetch_comments=True
        )
        result["total_videos"] = len(result["videos"])
```

- [ ] **Refactor `handle_channel`** — same replacement pattern as playlist (also uses `"videos"` / `"total_videos"`).

- [ ] **Refactor `handle_search`** — replace its `if result.get("results"):` block body:

Old:
```python
    if result.get("results"):
        items = result["results"]
        items = _apply_shorts_filter(items, args)
        if getattr(args, "comments", False):
            logger.info(f"Fetching full metadata + comments for {len(items)} search results...")
            items = _fetch_full_metadata(items, args)
        if getattr(args, "dislikes", False):
            items = _enrich_dislikes(items, workers=args.workers)
        if getattr(args, "sentiment", False):
            analyzer = SentimentAnalyzer()
            for item in items:
                if item.get("comments"):
                    summary = analyzer.analyze(item["comments"])
                    if summary:
                        item["sentiment_summary"] = summary
        items = _apply_engagement_filters(items, args)
        items = _apply_sort(items, args)
        result["results"] = items
        result["total_results"] = len(items)
```

New:
```python
    if result.get("results"):
        result["results"] = _post_process_items(
            result["results"], args, apply_shorts=True, fetch_comments=True
        )
        result["total_results"] = len(result["results"])
```

- [ ] **Refactor `handle_search_batch`** — replace the per-query post-processing loop:

Old:
```python
    analyzer = SentimentAnalyzer() if getattr(args, "sentiment", False) else None
    for result in results:
        if not result or not result.get("results"):
            continue
        items = result["results"]
        items = _apply_shorts_filter(items, args)
        if getattr(args, "comments", False):
            items = _fetch_full_metadata(items, args)
        if getattr(args, "dislikes", False):
            items = _enrich_dislikes(items, workers=args.workers)
        if analyzer:
            for item in items:
                if item.get("comments"):
                    summary = analyzer.analyze(item["comments"])
                    if summary:
                        item["sentiment_summary"] = summary
        items = _apply_engagement_filters(items, args)
        items = _apply_sort(items, args)
        result["results"] = items
        result["total_results"] = len(items)
```

New:
```python
    for result in results:
        if not result or not result.get("results"):
            continue
        result["results"] = _post_process_items(
            result["results"], args, apply_shorts=True, fetch_comments=True
        )
        result["total_results"] = len(result["results"])
```

- [ ] **Refactor `handle_pipeline`** — replace its `if result.get("videos"):` block body:

Old:
```python
    if result.get("videos"):
        items = result["videos"]
        if getattr(args, "dislikes", False):
            items = _enrich_dislikes(items, workers=args.workers)
        if getattr(args, "sentiment", False):
            analyzer = SentimentAnalyzer()
            for item in items:
                if item.get("comments"):
                    summary = analyzer.analyze(item["comments"])
                    if summary:
                        item["sentiment_summary"] = summary
        items = _apply_engagement_filters(items, args)
        items = _apply_sort(items, args)
        result["videos"] = items
```

New:
```python
    if result.get("videos"):
        result["videos"] = _post_process_items(
            result["videos"], args, apply_shorts=False, fetch_comments=False
        )
```

- [ ] **Refactor `handle_pipeline_batch`** — replace its per-result loop:

Old:
```python
    analyzer = SentimentAnalyzer() if getattr(args, "sentiment", False) else None
    for result in results:
        if not result or not result.get("videos"):
            continue
        items = result["videos"]
        if getattr(args, "dislikes", False):
            items = _enrich_dislikes(items, workers=args.workers)
        if analyzer:
            for item in items:
                if item.get("comments"):
                    summary = analyzer.analyze(item["comments"])
                    if summary:
                        item["sentiment_summary"] = summary
        items = _apply_shorts_filter(items, args)
        items = _apply_engagement_filters(items, args)
        items = _apply_sort(items, args)
        result["videos"] = items
```

New:
```python
    for result in results:
        if not result or not result.get("videos"):
            continue
        result["videos"] = _post_process_items(
            result["videos"], args, apply_shorts=True, fetch_comments=False, shorts_first=False
        )
```

- [ ] **Refactor `handle_batch`** — replace the post-extraction block:

Old:
```python
    # Post-processing: enrich, filter, sort
    if getattr(args, "dislikes", False):
        items = _enrich_dislikes(items, workers=args.workers)

    if getattr(args, "sentiment", False):
        sentiment_analyzer = SentimentAnalyzer()
        for item in items:
            if item.get("comments"):
                summary = sentiment_analyzer.analyze(item["comments"])
                if summary:
                    item["sentiment_summary"] = summary

    items = _apply_shorts_filter(items, args)
    items = _apply_engagement_filters(items, args)
    items = _apply_sort(items, args)
```

New:
```python
    # Post-processing: enrich, filter, sort
    items = _post_process_items(
        items, args, apply_shorts=True, fetch_comments=False, shorts_first=False
    )
```

- [ ] **Run all tests:** `python -m pytest scripts/tests/ -v` → 111 passed

- [ ] **Commit:**
```bash
git add scripts/youtube_scraper.py scripts/tests/test_cli_behaviors.py
git commit -m "refactor: extract _post_process_items(), dedup 7 handler post-processing blocks

shorts->comments->dislikes->sentiment->filter->sort was copy-pasted in
handle_playlist, handle_channel, handle_search, handle_search_batch,
handle_pipeline, handle_pipeline_batch, and handle_batch.

_post_process_items(items, args, *, apply_shorts, fetch_comments, shorts_first)
centralizes this. shorts_first=False preserves the existing step ordering in
batch modes (filter after enrichment). No behavior change in any handler.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 6: Split `build_parser()` into sub-functions

**Files:** `scripts/youtube_scraper.py`

`build_parser()` is ~540 lines. Extract 8 `_add_*_args(parser)` functions, one per logical argument group. `build_parser()` becomes a ~30-line coordinator.

Also promote `_positive_int` from a nested function to module level (it was trapped inside `build_parser`, making it untestable).

- [ ] **Move `_positive_int` to module level** — find this nested function inside `build_parser()`:

```python
    def _positive_int(value: str) -> int:
        try:
            n = int(value)
        except ValueError:
            raise argparse.ArgumentTypeError(f"--workers must be an integer, got {value!r}")
        if n < 1:
            raise argparse.ArgumentTypeError(f"--workers must be >= 1, got {n}")
        return n
```

Move it (unindented) to just before `build_parser()`, keeping it as-is:

```python
def _positive_int(value: str) -> int:
    """argparse type: integer >= 1. Used for --workers."""
    try:
        n = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"--workers must be an integer, got {value!r}")
    if n < 1:
        raise argparse.ArgumentTypeError(f"--workers must be >= 1, got {n}")
    return n
```

- [ ] **Add 8 `_add_*_args` functions** before `build_parser()`. Copy the exact `add_argument` calls from the current `build_parser()` into these functions — do not paraphrase or rewrite them:

```python
def _add_input_args(parser: argparse.ArgumentParser) -> None:
    """--url, --search, --playlist, --batch, --channel, --search-batch."""
    input_group = parser.add_argument_group("Input (choose one)")
    source = input_group.add_mutually_exclusive_group()
    # [exact add_argument calls from "Input source" section of current build_parser]


def _add_search_pipeline_args(parser: argparse.ArgumentParser) -> None:
    """--search-limit, --pipeline, --pipeline-top, --transcript."""
    search_group = parser.add_argument_group("Search options")
    # [exact add_argument calls from "Search & pipeline options" section]
    filter_group = parser.add_argument_group(
        "Filters",
        "Narrow results by view count, duration, or upload age.",
    )
    # [exact add_argument calls from "Filter options" section]


def _add_output_args(parser: argparse.ArgumentParser) -> None:
    """--output, --report, --csv, --urls-only, --no-print, --detailed-formats,
    subtitles (--subtitles, --subtitle-lang, --subtitle-format, --download-subs),
    downloads (--download-video, --download-audio, --download-dir, --download-quality)."""
    output_group = parser.add_argument_group("Output")
    # [exact add_argument calls from "Output options" section]
    subtitle_group = parser.add_argument_group("Subtitles")
    # [exact add_argument calls from "Subtitle options" section]
    download_group = parser.add_argument_group("Downloads (disabled by default)")
    # [exact add_argument calls from "Download options" section]


def _add_collection_args(parser: argparse.ArgumentParser) -> None:
    """--max-videos, --full-playlist, --workers, --channel-tab, --no-shorts, --shorts-only."""
    playlist_group = parser.add_argument_group("Playlist options")
    # [exact add_argument calls from "Playlist options" section]
    batch_group = parser.add_argument_group("Batch options")
    batch_group.add_argument("--workers", ..., type=_positive_int, ...)  # exact copy
    channel_group = parser.add_argument_group("Channel options", ...)
    # [exact add_argument calls from "Channel options" section]
    shorts_group = parser.add_argument_group("Content-type filters", ...)
    shorts_ex = shorts_group.add_mutually_exclusive_group()
    # [exact add_argument calls from "Shorts / content-type filters" section]


def _add_comments_args(parser: argparse.ArgumentParser) -> None:
    """--comments, --comments-max."""
    comments_group = parser.add_argument_group("Comments")
    # [exact add_argument calls from "Comments options" section]


def _add_cache_failure_args(parser: argparse.ArgumentParser) -> None:
    """--no-cache, --cache-ttl, --cache-dir, --cache-clear, --failure-log."""
    cache_group = parser.add_argument_group("Cache options", ...)
    # [exact add_argument calls from "Cache options" section]
    fail_group = parser.add_argument_group("Failure tracking", ...)
    # [exact add_argument calls from "Failure log" section]


def _add_engagement_sort_args(parser: argparse.ArgumentParser) -> None:
    """--dislikes, --sentiment, --sort-by, --sort-order, all --filter-*-likes/subscribers/
    dislikes/positive-ratio/negative-ratio, --verbose."""
    engage_group = parser.add_argument_group("Engagement", ...)
    # [exact add_argument calls from "Engagement options" section]
    sort_group = parser.add_argument_group("Sorting", ...)
    # [exact add_argument calls from "Sorting" section]
    eng_filter_group = parser.add_argument_group("Engagement filters", ...)
    # [exact add_argument calls from "Engagement filters" section]
    global_group = parser.add_argument_group("Global options")
    # [exact add_argument calls from "Global options" section]
```

- [ ] **Rewrite `build_parser()`** as a coordinator:

```python
def build_parser() -> argparse.ArgumentParser:
    """
    Build and return the CLI argument parser.

    Each _add_*_args() function owns one logical section.
    Edit argument definitions there, not here.
    """
    parser = argparse.ArgumentParser(
        prog="youtube_scraper",
        description=(
            "YouTube Scraper — extract rich metadata, reports, and optional downloads "
            "from YouTube videos, playlists, and batch URL files.\n\n"
            "Default behavior: metadata extraction only (no downloads)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  Single video:  python scripts/youtube_scraper.py --url "URL"
  Save JSON:     python scripts/youtube_scraper.py --url "URL" --output out.json
  Playlist:      python scripts/youtube_scraper.py --playlist "URL"
  Batch:         python scripts/youtube_scraper.py --batch urls.txt
  Search:        python scripts/youtube_scraper.py --search "topic" --search-limit 10
  Pipeline:      python scripts/youtube_scraper.py --search "topic" --pipeline --pipeline-top 5
""",
    )
    _add_input_args(parser)
    _add_search_pipeline_args(parser)
    _add_output_args(parser)
    _add_collection_args(parser)
    _add_comments_args(parser)
    _add_cache_failure_args(parser)
    _add_engagement_sort_args(parser)
    return parser
```

- [ ] **Verify:** `python -m pytest scripts/tests/ -v` → 111 passed
- [ ] **Verify help renders:** `python scripts/youtube_scraper.py --help > /dev/null`

- [ ] **Commit:**
```bash
git add scripts/youtube_scraper.py
git commit -m "refactor: split build_parser() into 7 _add_*_args() sub-functions

build_parser() was ~540 lines. It now delegates to focused helpers and is
~30 lines. No argument definitions changed. _positive_int() promoted to
module level (was trapped as a nested function).

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 7: Fix `ReportGenerator` docstring

**Files:** `scripts/reports/report_generator.py`

The module docstring claims the class "decides which extractor to use" and "handles the output path" — that is done in `youtube_scraper.py`. The class only prints terminal summaries.

- [ ] **Replace module docstring** at top of file:

Old:
```python
"""
report_generator.py
-------------------
High-level orchestrator that ties extractors and formatters together
to produce complete output reports.

WHY A SEPARATE REPORT GENERATOR?
  The CLI (youtube_scraper.py) handles argument parsing.
  The extractors handle data fetching.
  The formatters handle rendering.

  But someone has to:
    - Decide which extractor to use based on URL type
    - Decide which formatter to use based on --output / --csv / --report flags
    - Print a summary to the terminal (separate from saved output)
    - Handle the output path

  That's what this module does. It's the glue layer.

TERMINAL SUMMARY:
  After any operation, we print a concise human-readable summary to the
  terminal using rich (if available) or plain text. This is separate from
  the saved output and is always shown regardless of output format.
"""
```

New:
```python
"""
report_generator.py
-------------------
Terminal display layer — prints concise human-readable summaries to the
console after each extraction operation.

WHAT THIS MODULE DOES:
  - Prints a video summary panel (title, stats, available formats)
  - Prints a playlist summary table
  - Prints download result confirmation
  - Prints save-to-file confirmation with path

WHAT THIS MODULE DOES NOT DO:
  Routing, extractor selection, formatter selection, and file I/O are all
  handled in youtube_scraper.py. This class only handles the terminal-display
  side — shown after every run regardless of --output format.
"""
```

- [ ] **Fix class docstring** — find:
```python
class ReportGenerator:
    """
    Orchestrates extraction + formatting + terminal display.

    Usage:
        gen = ReportGenerator()
        gen.run_video(url, output_path="out.json", fmt="json")
        gen.run_playlist(url, output_path="playlist.md", fmt="markdown")
    """
```

Replace with:
```python
class ReportGenerator:
    """
    Prints terminal summaries for completed extraction operations.

    Usage:
        gen = ReportGenerator()
        gen.print_video_summary(data)
        gen.print_playlist_summary(data)
        gen.print_save_confirmation(path, fmt)
        gen.print_download_result(data)
    """
```

- [ ] **Verify:** `python -m pytest scripts/tests/ -v` → 111 passed

- [ ] **Commit:**
```bash
git add scripts/reports/report_generator.py
git commit -m "docs: fix ReportGenerator docstring to match actual responsibilities

The module claimed to 'decide which extractor to use' and 'handle the output
path' - that routing is done in youtube_scraper.py. ReportGenerator only
prints terminal summaries. Updated module and class docstrings accordingly.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Self-Review

**Coverage check:**

| Finding | Task |
|---------|------|
| README command location inconsistency | 1a |
| Channel example `--search-limit` → `--max-videos` | 1b |
| Likes filter text stale ("silently drop") | 1c |
| Roadmap: transcript marked Pending | 1d |
| pytest not in dependencies | 1e + 1g |
| SKILL.md "Production-grade" | 1f |
| Post-processing duplicated (7 handlers) | 5 |
| Sentiment loop duplicated | 5 (absorbed) |
| Concurrent ordered-map repeats | 4 |
| Output flattening repeats | 3 |
| Validation inline wall | 2 |
| `build_parser()` too long | 6 |
| `ReportGenerator` docstring misleading | 7 |

All 13 findings covered. ✓

**Test count progression:**
- Start: 94
- After Task 3: 102 (+8 `_result_items`)
- After Task 4: 105 (+3 `_run_ordered`)
- After Task 5: 111 (+6 `_post_process_items`)
- Tasks 6–7: structural/docs, no new tests
- **End: 111**

**Behavior preservation notes:**
- `_validate_args`: identical logic, identical `parser.error()` messages
- `_result_items`: covers all 7 extractor shapes including single-video fallback
- `_run_ordered`: preserves submission-order output via preallocated list
- `_post_process_items`: `shorts_first=False` exactly preserves the existing batch/pipeline_batch behavior (shorts after enrichment)
- `build_parser()`: all argument definitions moved verbatim, zero changes to flags/types/defaults
