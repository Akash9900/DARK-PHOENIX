# Phase 3 Implementation Checklist — Watermarking

**Branch:** `feature/complete-deployment`
**Estimated total:** ~6.5 hours
**Goal:** Burn a configurable watermark (logo image and/or text) into every generated clip,
applied **after** the subtitle-burning ffmpeg pass and **before** the S3 upload, with
env-var-driven configuration (enable/disable, position, opacity, size/font).

**Prerequisite:** Phase 1 complete (✅). Phase 2 (YouTube ingestion) does not block this phase —
watermarking applies identically regardless of source (`file` or `youtube`), since both paths
converge at `process_clip()`.

---

## Reference: Current State

- `ai-podcast-clipper-backend/main.py:154-238` — `create_subtitles_with_ffmpeg()`. Burns ASS
  subtitles via:
  ```python
  ffmpeg_cmd = (f"ffmpeg -y -i {clip_video_path} -vf \"ass={subtitle_path}\" "
                f"-c:v h264 -preset fast -crf 23 {output_path}")
  ```
  Output written to `subtitle_output_path` (= `clip_dir / "pyavi" / "video_with_subtitles.mp4"`).
- `ai-podcast-clipper-backend/main.py:241-309` — `process_clip()`. Calls
  `create_subtitles_with_ffmpeg()` at line 303-304, then immediately uploads
  `subtitle_output_path` to S3 at lines 306-309:
  ```python
  s3_client = boto3.client("s3")
  s3_client.upload_file(
      subtitle_output_path, os.environ["S3_BUCKET_NAME"], output_s3_key,
      ExtraArgs={"Tagging": "Environment=clip"})
  ```
  **This is where the watermark step must be inserted** — between subtitle burning and S3 upload.
- `ai-podcast-clipper-backend/main.py:29-38` — Modal image definition. `add_local_dir("asd", "/asd", copy=True)`
  is the existing pattern for bundling local directories into the image; a new `assets/`
  directory will follow the same pattern.
- **No `assets/` directory exists yet** in `ai-podcast-clipper-backend/` — must be created.
- `ai-podcast-clipper-backend/setup_modal_secret.py` — existing pattern for adding env vars to
  the Modal secret (most recently extended in Phase 1 Task 2.3 with `MAX_CLIPS`).
- Output video resolution is **1080x1920** (vertical, 9:16) — confirmed via
  `subs.info["PlayResX"] = 1080` / `subs.info["PlayResY"] = 1920` at `main.py:206-207`.

---

## Design Decision: Image Watermark vs. Text Watermark

The user's request mentions both "logo/text watermark" generally, and `drawtext` specifically.
This checklist implements **both**, gated independently:

- `WATERMARK_ENABLED=true` + `WATERMARK_PATH=assets/watermark.png` → image overlay (`overlay`
  filter) — for a logo
- `WATERMARK_TEXT_ENABLED=true` + `WATERMARK_TEXT="Your Brand"` → text overlay (`drawtext`
  filter) — for a simple text watermark, no image asset required

Both can be enabled simultaneously (image in one corner, text in another), or independently.
This avoids forcing the user to provide a logo asset just to get a text watermark, while still
supporting the image-overlay design from `PROJECT_PLAN.md` §3.2.

- [ ] Design reviewed and confirmed before starting implementation

---

## Task Breakdown

### Task 1 — Create `assets/` directory + placeholder watermark asset (≈30 min)

- **Directory:** `ai-podcast-clipper-backend/assets/` (new)
- **File:** `ai-podcast-clipper-backend/assets/watermark.png` (new — placeholder transparent PNG;
  actual logo to be supplied later by user/design team — see "Open Items")
- **File:** `ai-podcast-clipper-backend/assets/README.md` (new) — documents expected format:
  PNG with alpha channel, recommended max width 200px (matches `scale=200:-1` in the ffmpeg
  filter below)
- [ ] `assets/` directory created
- [ ] Placeholder `watermark.png` added (or documented as a manual follow-up if no asset
      available — see Open Items)
- [ ] `assets/README.md` documents asset requirements

---

### Task 2 — Modal image: bundle `assets/` directory (≈20 min)

- **File:** `ai-podcast-clipper-backend/main.py:29-40` — Modal image definition
- **Before:**
  ```python
  image = (modal.Image.from_registry(
      "nvidia/cuda:12.4.0-devel-ubuntu22.04", add_python="3.11")
      .apt_install([...])
      .pip_install_from_requirements("requirements.txt")
      .run_commands([
          "mkdir -p /usr/share/fonts/truetype/custom",
          "wget -O /usr/share/fonts/truetype/custom/Anton-Regular.ttf https://github.com/google/fonts/raw/main/ofl/anton/Anton-Regular.ttf",
          "fc-cache -f -v",
      ])
      .add_local_dir("asd", "/asd", copy=True))
  ```
- **After:**
  ```python
  image = (modal.Image.from_registry(
      "nvidia/cuda:12.4.0-devel-ubuntu22.04", add_python="3.11")
      .apt_install([...])
      .pip_install_from_requirements("requirements.txt")
      .run_commands([
          "mkdir -p /usr/share/fonts/truetype/custom",
          "wget -O /usr/share/fonts/truetype/custom/Anton-Regular.ttf https://github.com/google/fonts/raw/main/ofl/anton/Anton-Regular.ttf",
          "fc-cache -f -v",
      ])
      .add_local_dir("asd", "/asd", copy=True)
      .add_local_dir("assets", "/assets", copy=True))
  ```
- [ ] `add_local_dir("assets", "/assets", copy=True)` added
- [ ] `python3 -m py_compile main.py` passes (syntax check only — actual image build requires
      Modal deploy)

---

### Task 3 — Add watermark env vars to `setup_modal_secret.py` (≈30 min)

- **File:** `ai-podcast-clipper-backend/setup_modal_secret.py`
- **Add to secret dict** (following the `MAX_CLIPS` pattern from Phase 1):
  ```python
  secret = modal.Secret.from_dict({
      "GEMINI_API_KEY": os.getenv("GEMINI_API_KEY"),
      "AUTH_TOKEN": os.getenv("PROCESS_VIDEO_ENDPOINT_AUTH"),
      "AWS_ACCESS_KEY_ID": os.getenv("AWS_ACCESS_KEY_ID"),
      "AWS_SECRET_ACCESS_KEY": os.getenv("AWS_SECRET_ACCESS_KEY"),
      "AWS_REGION": os.getenv("AWS_REGION"),
      "S3_BUCKET_NAME": os.getenv("S3_BUCKET_NAME"),
      "MAX_CLIPS": os.getenv("MAX_CLIPS", "10"),
      "WATERMARK_ENABLED": os.getenv("WATERMARK_ENABLED", "false"),
      "WATERMARK_PATH": os.getenv("WATERMARK_PATH", "/assets/watermark.png"),
      "WATERMARK_POSITION": os.getenv("WATERMARK_POSITION", "bottom-right"),
      "WATERMARK_OPACITY": os.getenv("WATERMARK_OPACITY", "0.8"),
      "WATERMARK_SCALE_WIDTH": os.getenv("WATERMARK_SCALE_WIDTH", "200"),
      "WATERMARK_TEXT_ENABLED": os.getenv("WATERMARK_TEXT_ENABLED", "false"),
      "WATERMARK_TEXT": os.getenv("WATERMARK_TEXT", ""),
      "WATERMARK_TEXT_POSITION": os.getenv("WATERMARK_TEXT_POSITION", "bottom-left"),
      "WATERMARK_TEXT_FONT_SIZE": os.getenv("WATERMARK_TEXT_FONT_SIZE", "36"),
      "WATERMARK_TEXT_OPACITY": os.getenv("WATERMARK_TEXT_OPACITY", "0.7"),
  })
  ```
- **Add status print lines** (matching existing pattern):
  ```python
  print(f"  - WATERMARK_ENABLED: {os.getenv('WATERMARK_ENABLED', 'false')}")
  print(f"  - WATERMARK_TEXT_ENABLED: {os.getenv('WATERMARK_TEXT_ENABLED', 'false')}")
  ```
- [ ] All 9 watermark env vars added with safe defaults (watermark **off** by default — matches
      `PROJECT_PLAN.md` §3.5: "`WATERMARK_ENABLED` unset → default to `false`")
- [ ] Status print lines added
- [ ] `python3 -m py_compile setup_modal_secret.py` passes

---

### Task 4 — Implement `apply_watermark()` function (≈2 hours)

- **File:** `ai-podcast-clipper-backend/main.py`
- **Where:** New module-level function, placed immediately after `create_subtitles_with_ffmpeg()`
  (after line 238), before `process_clip()` (line 241)
- **Position mapping** (for 1080x1920 output, per `PROJECT_PLAN.md` §3.2):
  ```python
  WATERMARK_POSITIONS = {
      "top-left": "10:10",
      "top-right": "W-w-10:10",
      "bottom-left": "10:H-h-10",
      "bottom-right": "W-w-10:H-h-10",
  }

  WATERMARK_TEXT_POSITIONS = {
      "top-left": "x=20:y=20",
      "top-right": "x=w-tw-20:y=20",
      "bottom-left": "x=20:y=h-th-20",
      "bottom-right": "x=w-tw-20:y=h-th-20",
  }
  ```
- **Implementation:**
  ```python
  def apply_watermark(input_path: str, output_path: str) -> str:
      """Apply image and/or text watermark overlays via ffmpeg.

      Reads configuration from environment variables (WATERMARK_ENABLED,
      WATERMARK_TEXT_ENABLED, etc.). If neither is enabled, copies
      input_path to output_path unchanged. If watermarking is enabled but
      the configured asset/filter fails, logs a warning and falls back to
      the un-watermarked input (degraded gracefully, per PROJECT_PLAN.md §3.5).

      Returns the path to the (possibly watermarked) output video.
      """
      image_enabled = os.environ.get("WATERMARK_ENABLED", "false").lower() == "true"
      text_enabled = os.environ.get("WATERMARK_TEXT_ENABLED", "false").lower() == "true"

      if not image_enabled and not text_enabled:
          shutil.copy(input_path, output_path)
          return output_path

      filter_parts = []
      input_args = ["-i", str(input_path)]
      video_label = "[0:v]"

      if image_enabled:
          watermark_path = os.environ.get("WATERMARK_PATH", "/assets/watermark.png")
          if not os.path.exists(watermark_path):
              print(f"WARNING: WATERMARK_ENABLED=true but {watermark_path} not found; "
                    f"skipping image watermark")
              image_enabled = False

      if image_enabled:
          position = os.environ.get("WATERMARK_POSITION", "bottom-right")
          overlay_xy = WATERMARK_POSITIONS.get(
              position, WATERMARK_POSITIONS["bottom-right"])
          opacity = os.environ.get("WATERMARK_OPACITY", "0.8")
          scale_width = os.environ.get("WATERMARK_SCALE_WIDTH", "200")

          input_args += ["-i", watermark_path]
          filter_parts.append(
              f"[1:v]scale={scale_width}:-1,format=rgba,"
              f"colorchannelmixer=aa={opacity}[wm]"
          )
          filter_parts.append(
              f"{video_label}[wm]overlay={overlay_xy}[v_img]"
          )
          video_label = "[v_img]"

      if text_enabled:
          text = os.environ.get("WATERMARK_TEXT", "")
          if not text:
              print("WARNING: WATERMARK_TEXT_ENABLED=true but WATERMARK_TEXT is empty; "
                    "skipping text watermark")
              text_enabled = False

      if text_enabled:
          position = os.environ.get("WATERMARK_TEXT_POSITION", "bottom-left")
          xy = WATERMARK_TEXT_POSITIONS.get(
              position, WATERMARK_TEXT_POSITIONS["bottom-left"])
          font_size = os.environ.get("WATERMARK_TEXT_FONT_SIZE", "36")
          opacity = os.environ.get("WATERMARK_TEXT_OPACITY", "0.7")
          escaped_text = text.replace("'", "\\'").replace(":", "\\:")

          filter_parts.append(
              f"{video_label}drawtext=text='{escaped_text}':fontsize={font_size}:"
              f"fontcolor=white@{opacity}:{xy}:"
              f"font='Anton'[v_out]"
          )
          video_label = "[v_out]"

      if not filter_parts:
          # Both watermarks were disabled due to missing asset/text after validation
          shutil.copy(input_path, output_path)
          return output_path

      # Map the final labeled output to the output file
      filter_complex = ";".join(filter_parts)
      map_label = video_label.strip("[]")

      ffmpeg_cmd = (
          f"ffmpeg -y {' '.join(input_args)} "
          f"-filter_complex \"{filter_complex}\" "
          f"-map \"[{map_label}]\" -map 0:a? "
          f"-c:v h264 -preset fast -crf 23 -c:a copy {output_path}"
      )

      try:
          subprocess.run(ffmpeg_cmd, shell=True, check=True, capture_output=True, text=True)
      except subprocess.CalledProcessError as e:
          print(f"WARNING: watermark ffmpeg command failed: {e.stderr}")
          print("Falling back to un-watermarked clip")
          shutil.copy(input_path, output_path)

      return output_path
  ```
- [ ] `apply_watermark()` function implemented
- [ ] `WATERMARK_POSITIONS` and `WATERMARK_TEXT_POSITIONS` dicts defined
- [ ] Graceful fallback on missing asset, empty text, and ffmpeg failure (copies input
      unchanged — per `PROJECT_PLAN.md` §3.5)
- [ ] `python3 -m py_compile main.py` passes

---

### Task 5 — Wire `apply_watermark()` into `process_clip()` (≈45 min)

- **File:** `ai-podcast-clipper-backend/main.py:241-309` — `process_clip()`
- **Add new path variable** near the other `clip_dir`-relative paths (around line 252):
  ```python
  subtitle_output_path = clip_dir / "pyavi" / "video_with_subtitles.mp4"
  watermarked_output_path = clip_dir / "pyavi" / "video_final.mp4"
  ```
- **Before:**
  ```python
  create_subtitles_with_ffmpeg(transcript_segments, start_time,
                               end_time, vertical_mp4_path, subtitle_output_path, max_words=5)

  s3_client = boto3.client("s3")
  s3_client.upload_file(
      subtitle_output_path, os.environ["S3_BUCKET_NAME"], output_s3_key,
      ExtraArgs={"Tagging": "Environment=clip"})
  ```
- **After:**
  ```python
  create_subtitles_with_ffmpeg(transcript_segments, start_time,
                               end_time, vertical_mp4_path, subtitle_output_path, max_words=5)

  final_output_path = apply_watermark(str(subtitle_output_path), str(watermarked_output_path))

  s3_client = boto3.client("s3")
  s3_client.upload_file(
      final_output_path, os.environ["S3_BUCKET_NAME"], output_s3_key,
      ExtraArgs={"Tagging": "Environment=clip"})
  ```
- [ ] `watermarked_output_path` variable added
- [ ] `apply_watermark()` called between subtitle burn and S3 upload
- [ ] S3 upload now uploads `final_output_path` instead of `subtitle_output_path`
- [ ] `python3 -m py_compile main.py` passes

---

### Task 6 — Frontend: expose watermark status + "Watermarked" badge (≈1 hour)

- **File:** `ai-podcast-clipper-frontend/src/env.js` — add `WATERMARK_ENABLED` as a
  client-exposed env var (or server-only, surfaced via a server component prop — see below)
- **Simplest approach (no new env plumbing):** Since `clip-display.tsx` is rendered from a
  server component (`dashboard-client.tsx`'s parent page), pass a `watermarkEnabled: boolean`
  prop computed server-side from `process.env.WATERMARK_ENABLED === "true"`.
- **File:** `ai-podcast-clipper-frontend/src/components/clip-display.tsx`
  - Add `watermarkEnabled` to the component's props type
  - Render a small `<Badge variant="secondary">Watermarked</Badge>` on each clip card when
    `watermarkEnabled` is `true`
- **File:** wherever `<ClipDisplay clips={clips} />` is rendered (likely
  `dashboard-client.tsx` and/or its parent page) — pass the new prop through
- [ ] `watermarkEnabled` prop threaded from server-side env check to `ClipDisplay`
- [ ] "Watermarked" badge rendered conditionally on clip cards
- [ ] `npx tsc --noEmit` passes

---

### Task 7 — Verification & manual testing (≈1.5 hours)

- **Local ffmpeg filter test** (no Modal needed — validates filter syntax against a sample
  vertical video):
  ```bash
  # Image watermark only
  WATERMARK_ENABLED=true WATERMARK_PATH=assets/watermark.png \
    WATERMARK_POSITION=bottom-right WATERMARK_OPACITY=0.8 \
    python3 -c "from main import apply_watermark; apply_watermark('test_input.mp4', 'test_output_img.mp4')"

  # Text watermark only
  WATERMARK_TEXT_ENABLED=true WATERMARK_TEXT="My Podcast" \
    WATERMARK_TEXT_POSITION=bottom-left \
    python3 -c "from main import apply_watermark; apply_watermark('test_input.mp4', 'test_output_text.mp4')"

  # Both enabled
  WATERMARK_ENABLED=true WATERMARK_TEXT_ENABLED=true WATERMARK_TEXT="My Podcast" \
    python3 -c "from main import apply_watermark; apply_watermark('test_input.mp4', 'test_output_both.mp4')"

  # Disabled (default) — output should be byte-identical to input
  python3 -c "from main import apply_watermark; apply_watermark('test_input.mp4', 'test_output_off.mp4')"
  diff test_input.mp4 test_output_off.mp4 && echo "IDENTICAL"
  ```
  *Note: `apply_watermark()` is defined inside `main.py`, which has Modal-specific top-level
  code (`modal.Image.from_registry(...)`) that runs at import time. For local testing without
  Modal, this function may need to be temporarily extracted to a standalone module, or tested
  via `modal run` against a deployed image.*
- **Visual verification:** `ffprobe` + manual playback of `test_output_*.mp4` to confirm:
  - Watermark visible in the configured corner
  - Opacity looks correct (not fully opaque, not invisible)
  - Audio track preserved (`-c:a copy` + `-map 0:a?`)
- **Full pipeline test:** Run one end-to-end job (file upload or YouTube, per Phase 2) with
  `WATERMARK_ENABLED=true` and confirm the final clip in S3 has the watermark
- [ ] Filter syntax validated locally against a sample clip
- [ ] Visual confirmation: watermark appears in correct position/opacity
- [ ] Audio preserved in watermarked output
- [ ] `WATERMARK_ENABLED=false` (default) produces output identical to pre-Phase-3 behavior
- [ ] Full pipeline E2E test with watermark enabled (requires Modal deploy)

---

## Error Scenarios

| # | Scenario | Where Handled | Expected Behavior |
|---|----------|---------------|-------------------|
| 1 | `WATERMARK_ENABLED`/`WATERMARK_TEXT_ENABLED` both unset or `false` | `apply_watermark()` — early return | `shutil.copy(input_path, output_path)` — output identical to input, zero ffmpeg overhead |
| 2 | `WATERMARK_ENABLED=true` but `WATERMARK_PATH` file missing | `apply_watermark()` — `os.path.exists()` check before building filter | Logs `WARNING: ... not found; skipping image watermark`, proceeds with text-only (if enabled) or unchanged copy — degraded gracefully per `PROJECT_PLAN.md` §3.5 |
| 3 | `WATERMARK_TEXT_ENABLED=true` but `WATERMARK_TEXT` empty/unset | `apply_watermark()` — empty-string check | Logs warning, skips text watermark, proceeds with image-only or unchanged copy |
| 4 | ffmpeg `filter_complex` syntax error (e.g. malformed position string from bad env var) | `apply_watermark()` — `subprocess.run(..., check=True)` raises `CalledProcessError`, caught | Logs `WARNING: watermark ffmpeg command failed: {stderr}`, falls back to `shutil.copy` of un-watermarked input — **job does not fail**, clip still uploads |
| 5 | Watermark image larger than 1080px frame width | `scale={scale_width}:-1` filter (default 200px) | Image scaled down to `WATERMARK_SCALE_WIDTH` (default 200px) regardless of source size — matches `PROJECT_PLAN.md` §3.5 |
| 6 | Corrupt/zero-byte output from ffmpeg (disk full, killed process) | Not explicitly checked in `apply_watermark()` — **gap, flagged below** | `s3_client.upload_file()` would upload a corrupt/empty file; no integrity check exists today (pre-existing gap, not introduced by Phase 3) — recommend adding a file-size sanity check in Task 5 if time allows |
| 7 | `WATERMARK_POSITION` / `WATERMARK_TEXT_POSITION` set to an invalid value (typo) | `WATERMARK_POSITIONS.get(position, <bottom-right/bottom-left default>)` | Falls back to `bottom-right` (image) / `bottom-left` (text) silently — no crash |
| 8 | Watermark text contains characters that break ffmpeg `drawtext` syntax (`'`, `:`) | `escaped_text = text.replace("'", "\\'").replace(":", "\\:")` | Basic escaping applied; **not exhaustive** — complex Unicode or other special chars (`%`, `\`) could still break the filter. Flagged as a known limitation, not fully solved in Phase 3 |

---

## Testing Strategy

### Manual (Phase 3 scope)
1. **Default (off):** No env vars set → clip output unchanged from current behavior (Task 7
   diff check)
2. **Image watermark:** `WATERMARK_ENABLED=true` with valid `watermark.png` → logo visible in
   `bottom-right` (default)
3. **Text watermark:** `WATERMARK_TEXT_ENABLED=true WATERMARK_TEXT="Test"` → text visible in
   `bottom-left` (default)
4. **Both enabled:** confirm both render without overlapping (default positions are diagonal
   corners)
5. **Missing asset:** `WATERMARK_ENABLED=true` with `WATERMARK_PATH` pointing to nonexistent
   file → job completes successfully, clip has no image watermark, warning logged
6. **Position variants:** test all 4 corners for both image and text positioning dicts

### Automated (deferred to Phase 5 per `PROJECT_PLAN.md`)
- `tests/test_watermark.py` (per `PROJECT_PLAN.md` line 293):
  - Mock `subprocess.run` to verify the constructed `ffmpeg` command string contains expected
    `filter_complex` fragments for each config combination (image-only, text-only, both, neither)
  - Verify `apply_watermark()` returns `output_path` and calls `shutil.copy` when disabled
  - Verify fallback-to-copy behavior when `subprocess.run` raises `CalledProcessError`
- Not part of the ~6.5-hour Phase 3 estimate; tracked under Phase 5

---

## Success Criteria

- [ ] `WATERMARK_ENABLED=false` and `WATERMARK_TEXT_ENABLED=false` (or unset) → clips identical
      to pre-Phase-3 output (verified via diff)
- [ ] `WATERMARK_ENABLED=true` with valid `watermark.png` → every clip has the logo in the
      configured corner at the configured opacity
- [ ] `WATERMARK_TEXT_ENABLED=true` with `WATERMARK_TEXT` set → every clip has the text overlay
      in the configured corner
- [ ] Watermark(s) applied **after** subtitle burn-in (subtitles + watermark both visible,
      watermark on top)
- [ ] Missing watermark asset does not fail the job — degrades gracefully with a logged warning
- [ ] All 4 position options (`top-left`, `top-right`, `bottom-left`, `bottom-right`) work for
      both image and text watermarks
- [ ] Audio track preserved in watermarked output
- [ ] `python3 -m py_compile main.py` and `python3 -m py_compile setup_modal_secret.py` pass
- [ ] `npx tsc --noEmit` passes (frontend badge change)
- [ ] No regression to Phase 1/2 functionality (file upload + YouTube ingestion still work)

---

## Time Estimate Summary

| # | Task | Est. Time |
|---|------|-----------|
| 1 | Create `assets/` directory + placeholder watermark | 30 min |
| 2 | Modal image: bundle `assets/` directory | 20 min |
| 3 | Add watermark env vars to `setup_modal_secret.py` | 30 min |
| 4 | Implement `apply_watermark()` function | 120 min |
| 5 | Wire `apply_watermark()` into `process_clip()` | 45 min |
| 6 | Frontend: "Watermarked" badge | 60 min |
| 7 | Verification & manual testing | 90 min |
| **Total** | | **~6.5 hours** |

---

## Exact File → Line Reference Card

| File | Line(s) | Change |
|------|---------|--------|
| `ai-podcast-clipper-backend/assets/watermark.png` | new file | Placeholder/default watermark image |
| `ai-podcast-clipper-backend/assets/README.md` | new file | Asset format documentation |
| `ai-podcast-clipper-backend/main.py` | 29-40 | Modal image: `.add_local_dir("assets", "/assets", copy=True)` |
| `ai-podcast-clipper-backend/main.py` | ~239 (new, after `create_subtitles_with_ffmpeg`) | `WATERMARK_POSITIONS`, `WATERMARK_TEXT_POSITIONS`, `apply_watermark()` |
| `ai-podcast-clipper-backend/main.py` | 252 (new var) | `watermarked_output_path = clip_dir / "pyavi" / "video_final.mp4"` |
| `ai-podcast-clipper-backend/main.py` | 303-309 | Call `apply_watermark()`; upload `final_output_path` instead of `subtitle_output_path` |
| `ai-podcast-clipper-backend/setup_modal_secret.py` | secret dict | Add 9 `WATERMARK_*` env vars with safe defaults |
| `ai-podcast-clipper-frontend/src/components/clip-display.tsx` | TBD | `watermarkEnabled` prop + "Watermarked" badge |

---

## Environment Variable Reference

| Variable | Default | Description |
|----------|---------|-------------|
| `WATERMARK_ENABLED` | `false` | Enables image (logo) watermark overlay |
| `WATERMARK_PATH` | `/assets/watermark.png` | Path to watermark PNG (in Modal container, bundled via `add_local_dir`) |
| `WATERMARK_POSITION` | `bottom-right` | One of `top-left`, `top-right`, `bottom-left`, `bottom-right` |
| `WATERMARK_OPACITY` | `0.8` | Image alpha multiplier, `0.0`–`1.0` |
| `WATERMARK_SCALE_WIDTH` | `200` | Watermark image width in px (height auto-scaled) |
| `WATERMARK_TEXT_ENABLED` | `false` | Enables text watermark overlay (`drawtext`) |
| `WATERMARK_TEXT` | `""` | Text content to overlay (required if `WATERMARK_TEXT_ENABLED=true`) |
| `WATERMARK_TEXT_POSITION` | `bottom-left` | One of `top-left`, `top-right`, `bottom-left`, `bottom-right` |
| `WATERMARK_TEXT_FONT_SIZE` | `36` | Font size in px (uses bundled "Anton" font, same as subtitles) |
| `WATERMARK_TEXT_OPACITY` | `0.7` | Text alpha, `0.0`–`1.0` |

---

## Open Items / Risks Carried Forward

1. **No watermark asset currently exists.** `PROJECT_PLAN.md` Open Question #2 ("What logo/image
   file should be used? Who owns it?") is unresolved. Task 1 creates the directory/structure but
   the actual `watermark.png` content must come from the user/design team — until then,
   `WATERMARK_ENABLED` should remain `false` (its default), and only text watermarking
   (`WATERMARK_TEXT_ENABLED`) is usable out of the box.
2. **`apply_watermark()` is hard to unit-test in isolation** because it lives in `main.py`,
   which has Modal-decorated top-level code that requires the `modal` package and image context
   at import time. Consider extracting pure ffmpeg-command-building logic into a separate module
   (e.g. `watermark.py`) in a future refactor — not required for Phase 3 but would simplify
   Phase 5 automated testing.
3. **Corrupt/zero-byte ffmpeg output is not validated** (Error Scenario #6) — this is a
   pre-existing gap in `process_clip()`'s upload step, not introduced by Phase 3, but watermarking
   adds a second ffmpeg pass where it could occur. Optional hardening: check
   `os.path.getsize(final_output_path) > 0` before upload.
4. **`drawtext` text escaping is basic** (Error Scenario #8) — sufficient for simple ASCII brand
   names but not exhaustive for all special characters.
