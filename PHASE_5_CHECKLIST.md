# Phase 5 Checklist — End-to-End Verification & Deployment Readiness

**Branch:** `feature/complete-deployment`
**Goal:** Confirm Phases 1-4 are fully wired together end-to-end, document every environment
variable the system now depends on, and define the manual test scenarios to run once live
infrastructure (AWS, Modal, Supabase, Google Drive, Inngest) is available.

**Note on scope:** `PROJECT_PLAN.md` §Phase 5 describes an automated test suite (Playwright +
Vitest + pytest + CI). That remains future work. This checklist is the **pre-automation manual
verification pass** — confirming the code is complete and correctly wired before infrastructure
is provisioned and automated tests are written.

---

## 1. Code Completeness Check

All three Phase 2-4 features must be fully wired from frontend → Inngest → Modal → S3 →
(optionally) Drive. This section maps each feature to its implementation points so they can be
spot-checked with `grep`/`git log`.

### 1.1 YouTube Ingestion (Phase 2)

| Step | File | Status |
|------|------|--------|
| `youtubeUrl` field on `UploadedFile` | `ai-podcast-clipper-frontend/prisma/schema.prisma` | ✅ done (commit c181a2a) |
| `processYoutubeVideo()` server action | `ai-podcast-clipper-frontend/src/actions/youtube.ts` | ✅ done (commit 0935a89) |
| YouTube tab + form in dashboard | `ai-podcast-clipper-frontend/src/components/dashboard-client.tsx` | ✅ done (commit 621d91b) |
| `source`/`youtube_url` passed through Inngest event → `step.fetch` body | `ai-podcast-clipper-frontend/src/inngest/functions.ts` | ✅ done (commit 923478d) |
| `ProcessVideoRequest.source` / `.youtube_url` | `ai-podcast-clipper-backend/main.py` (`ProcessVideoRequest`) | ✅ done (commit d381d59) |
| `download_from_youtube()` + `YouTubeDownloadError` | `ai-podcast-clipper-backend/main.py` | ✅ done (commit d381d59) |
| `process_video()` branches on `source == "youtube"` | `ai-podcast-clipper-backend/main.py` | ✅ done (commit d381d59) |
| `yt-dlp` dependency | `ai-podcast-clipper-backend/requirements.txt` | ✅ done (commit 0935a89) |

### 1.2 Watermarking (Phase 3)

| Step | File | Status |
|------|------|--------|
| `assets/` directory (Modal image bundling target) | `ai-podcast-clipper-backend/assets/.gitkeep` | ✅ created (commit 13b5e04) — **`watermark.png` and `assets/README.md` still missing** |
| `WATERMARK_*` env vars in Modal secret | `ai-podcast-clipper-backend/setup_modal_secret.py` | ✅ done (commit 13b5e04) |
| `apply_watermark()` + `WatermarkError` | `ai-podcast-clipper-backend/main.py` | ✅ done (commit fb02bb0) |
| Wired into `process_clip()` with graceful fallback | `ai-podcast-clipper-backend/main.py` | ✅ done (commit 0bf34b1) |
| Modal image bundles `assets/` via `add_local_dir` | `ai-podcast-clipper-backend/main.py` (image definition) | ❌ **NOT done — PHASE_3_CHECKLIST.md Task 2 still open** |
| Frontend "Watermarked" badge | `ai-podcast-clipper-frontend/src/components/clip-display.tsx` | ❌ **NOT done — PHASE_3_CHECKLIST.md Task 6 still open** |

### 1.3 Google Drive Delivery (Phase 4)

| Step | File | Status |
|------|------|--------|
| `google-api-python-client` + auth deps | `ai-podcast-clipper-backend/requirements.txt` | ✅ done (commit 8444c68) |
| `upload_to_drive()` + `DriveUploadError` | `ai-podcast-clipper-backend/main.py` | ✅ done (commit 8444c68) |
| `GOOGLE_DRIVE_*` env vars in Modal secret | `ai-podcast-clipper-backend/setup_modal_secret.py` | ✅ done (commits 8444c68, 0c2ca5d) |
| Wired into `process_clip()` with graceful fallback | `ai-podcast-clipper-backend/main.py` | ✅ done (commit 0c2ca5d) |
| Drive file ID persisted to DB / surfaced in UI | — | ❌ **NOT done — PHASE_4_CHECKLIST.md Task 3, deferred ("don't need to store it yet")** |

### 1.4 Outstanding Items Before "Feature Complete"

These are not blockers for backend correctness, but should be tracked before calling Phase 2-4
done:

- [ ] `ai-podcast-clipper-backend/assets/watermark.png` (placeholder or real logo) +
      `assets/README.md` (PHASE_3 Task 1)
- [ ] Modal image `add_local_dir("assets", "/assets", copy=True)` (PHASE_3 Task 2) — **without
      this, `WATERMARK_IMAGE_ENABLED=true` will raise `WatermarkError` on Modal because
      `assets/watermark.png` won't exist in the deployed image** (graceful fallback means the
      clip still uploads un-watermarked, but the feature won't actually work)
- [ ] Frontend "Watermarked" badge (PHASE_3 Task 6)
- [ ] Drive file ID persistence/UI (PHASE_4 Task 3) — optional, nice-to-have

---

## 2. Environment Variable Reference (Full System)

All variables the system reads, across frontend (`ai-podcast-clipper-frontend/src/env.js`,
validated via `@t3-oss/env-nextjs`) and backend (`ai-podcast-clipper-backend/setup_modal_secret.py`
→ Modal secret `ai-podcast-clipper-secret`, read via `os.environ`/`os.getenv` in `main.py`).

Single source of truth for local dev: root `.env.example`. **Note:** `.env.example` does not yet
list the Phase 2-4 vars below (`WATERMARK_*`, `GOOGLE_DRIVE_*`) — see §5 Open Items.

### 2.1 Frontend (`ai-podcast-clipper-frontend/src/env.js`)

| Variable | Required | Description |
|----------|----------|-------------|
| `AUTH_SECRET` | prod only | NextAuth session secret (`npx auth secret`) |
| `AUTH_DISCORD_ID` / `AUTH_DISCORD_SECRET` | yes | Discord OAuth app credentials |
| `DATABASE_URL` | yes | Supabase Postgres connection string |
| `NODE_ENV` | auto | `development` / `test` / `production` |
| `AWS_ACCESS_KEY_ID` | yes | IAM user with S3 read/write on the bucket |
| `AWS_SECRET_ACCESS_KEY` | yes | — |
| `AWS_REGION` | yes | e.g. `us-east-1` |
| `S3_BUCKET_NAME` | yes | Bucket for source videos + clips |
| `PROCESS_VIDEO_ENDPOINT` | yes | Modal `process_video` HTTPS endpoint URL |
| `PROCESS_VIDEO_ENDPOINT_AUTH` | yes | Bearer token shared with Modal (`AUTH_TOKEN` on backend side) |
| `STRIPE_SECRET_KEY` | yes | Stripe API secret key |
| `STRIPE_WEBHOOK_SECRET` | yes | Stripe webhook signing secret |
| `STRIPE_SMALL_CREDIT_PACK` / `STRIPE_MEDIUM_CREDIT_PACK` / `STRIPE_LARGE_CREDIT_PACK` | yes | Stripe Price IDs for credit packs |
| `NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY` | yes | Stripe publishable key (client-exposed) |
| `BASE_URL` | yes | Public app URL (Stripe redirect/webhook base) |

### 2.2 Backend / Modal Secret (`ai-podcast-clipper-backend/setup_modal_secret.py`)

| Variable | Default | Description |
|----------|---------|-------------|
| `GEMINI_API_KEY` | — | Google Gemini API key (clip selection/transcription analysis) |
| `AUTH_TOKEN` (= `PROCESS_VIDEO_ENDPOINT_AUTH`) | — | Bearer token Modal endpoint requires |
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` / `AWS_REGION` | — | S3 access for download/upload |
| `S3_BUCKET_NAME` | — | Bucket for source videos + clips |
| `MAX_CLIPS` | `10` | Max clips generated per video |
| `WATERMARK_ENABLED` | `false` | Enables text watermark (`drawtext`) |
| `WATERMARK_TEXT` | `LUNARTECH.AI` | Watermark text content |
| `WATERMARK_POSITION` | `lower-right` | `lower-right`/`lower-left`/`upper-right`/`upper-left` (shared by text + image) |
| `WATERMARK_OPACITY` | `0.7` | Text alpha, `0.0`-`1.0` |
| `WATERMARK_FONT_SIZE` | `30` | Text font size in px |
| `WATERMARK_IMAGE_ENABLED` | `false` | Enables image (logo) watermark overlay |
| `WATERMARK_IMAGE_PATH` | `assets/watermark.png` | Path to watermark PNG inside the Modal image |
| `WATERMARK_IMAGE_SCALE` | `0.1` | Watermark image width as fraction of 1080px output width |
| `GOOGLE_DRIVE_CREDENTIALS_JSON` | — | Base64-encoded service account JSON key |
| `GOOGLE_DRIVE_ENABLED` | `false` | Enables Drive upload step in `process_clip()` |
| `GOOGLE_DRIVE_FOLDER_ID` | — | Destination Drive folder ID (must be shared with service account) |

**Total: 14 frontend vars + 17 backend vars = 31 distinct variable names** (4 are shared/mirrored
between frontend and backend: AWS creds × 3, `S3_BUCKET_NAME`, and the
`PROCESS_VIDEO_ENDPOINT_AUTH`/`AUTH_TOKEN` pair — so **~26 unique secrets** to provision).

---

## 3. Integration Point Verification (Pipeline Flow)

End-to-end data flow, confirming each handoff is wired (per §1 above):

```
1. User submits YouTube URL or uploads file (dashboard-client.tsx)
   ├─ File path: generateUploadUrl() → S3 PUT (presigned) → processVideo(uploadedFileId)
   └─ YouTube path: processYoutubeVideo(youtubeUrl)
        → creates UploadedFile { youtubeUrl, uploaded: true }
        → inngest.send({ uploadedFileId, userId, source: "youtube", youtubeUrl })

2. Inngest function `processVideo` (functions.ts)
   → step.fetch(PROCESS_VIDEO_ENDPOINT, {
       body: { s3_key, source, youtube_url },
       headers: { Authorization: Bearer PROCESS_VIDEO_ENDPOINT_AUTH }
     })

3. Modal `process_video()` endpoint (main.py)
   ├─ source == "youtube" → download_from_youtube() → upload original to S3 (Tagging: source)
   └─ source == "file"    → download original from S3
   → runs WhisperX → Gemini clip selection → TalkNet → create_vertical_video()
   → for each clip, process_clip():
       1. create_subtitles_with_ffmpeg()      → subtitle_output_path
       2. apply_watermark() [try/except]      → clip_path (watermarked or fallback)
       3. s3_client.upload_file(clip_path, ..., Tagging: clip)
       4. upload_to_drive() [try/except, opt-in via GOOGLE_DRIVE_ENABLED]

4. Inngest polls S3 (ListObjectsV2) for clip_*.mp4 → creates Clip rows, deducts credits
5. Frontend dashboard polls/refreshes → ClipDisplay renders clips from S3 signed URLs
```

- [ ] Confirm step 1→2: `youtube_url`/`source` actually arrive in the Inngest event payload
      (add a temporary `console.log(event.data)` in `functions.ts` during first live test)
- [ ] Confirm step 2→3: Modal endpoint receives `source`/`youtube_url` in request body (check
      Modal logs for `Downloading video from YouTube: ...` print)
- [ ] Confirm step 3 watermark: with `WATERMARK_ENABLED=true`, output clip visibly has
      watermark; with it `false`, no watermark and no `WatermarkError` warnings in logs
- [ ] Confirm step 3 Drive: with `GOOGLE_DRIVE_ENABLED=true` + valid folder, file appears in
      Drive folder; with it `false`, no Drive-related log lines at all
- [ ] Confirm step 4: `Clip` rows created in DB with correct `s3Key` for each `clip_N.mp4`

---

## 4. Manual Test Scenarios

These require live AWS, Modal, Supabase, and (for scenario 4) Google Drive credentials. None of
these can run in this sandbox.

### Scenario A — File upload, no watermark, no Drive (baseline regression)
1. Set `WATERMARK_ENABLED=false`, `GOOGLE_DRIVE_ENABLED=false`.
2. Upload a short (~60s) MP4 via the "Upload File" tab.
3. **Expect:** job completes, 1+ clips appear in "My Clips", clips playable, no watermark
   visible, no Drive-related log entries on Modal.

### Scenario B — YouTube ingestion end-to-end
1. Paste a public, short (<3 min) YouTube URL into the "YouTube URL" tab.
2. **Expect:** `UploadedFile` row created with `youtubeUrl` set and `uploaded: true`
   immediately; Modal logs show `Downloading video from YouTube: ...`; original uploads to S3
   tagged `Environment=source`; clips generated as in Scenario A.
3. **Error case:** submit a private/age-restricted/deleted video URL → Modal should return
   HTTP 422 with the `YouTubeDownloadError` message; job should surface as "failed" in the UI
   (not silently hang).

### Scenario C — Watermark on/off + text vs. image
1. Set `WATERMARK_ENABLED=true`, `WATERMARK_TEXT="TEST WATERMARK"`,
   `WATERMARK_POSITION=lower-right`. Run Scenario A again.
   **Expect:** "TEST WATERMARK" visible in lower-right of every clip.
2. Set `WATERMARK_IMAGE_ENABLED=true` (requires `assets/watermark.png` to exist in the deployed
   Modal image — see §1.4). **Expect:** logo overlay visible.
3. **Error case:** set `WATERMARK_IMAGE_ENABLED=true` but do NOT bundle `assets/watermark.png`
   (current state). **Expect:** Modal logs show `WARNING: watermark failed, uploading clip
   without watermark: ...WATERMARK_IMAGE_ENABLED=true but image not found...`; clip still
   uploads successfully without watermark (graceful fallback).

### Scenario D — Google Drive delivery + failure fallback
1. Provision a service account, base64-encode its key into `GOOGLE_DRIVE_CREDENTIALS_JSON`,
   share a Drive folder with the service account's `client_email`, set
   `GOOGLE_DRIVE_FOLDER_ID` and `GOOGLE_DRIVE_ENABLED=true`. Run Scenario A.
   **Expect:** Modal logs `Uploaded clip_N to Google Drive (file ID: ...)`; file appears in the
   shared Drive folder.
2. **Error case:** set `GOOGLE_DRIVE_ENABLED=true` but `GOOGLE_DRIVE_FOLDER_ID` unset.
   **Expect:** Drive step skipped silently (no log line), S3 upload still succeeds.
3. **Error case:** set an invalid/expired `GOOGLE_DRIVE_CREDENTIALS_JSON`.
   **Expect:** `WARNING: Google Drive upload failed, clip remains available in S3: ...`; job
   still completes successfully.

---

## 5. Deployment Readiness Checklist

High-level gate before Phase 6 deployment. Each item links to `DEPLOYMENT_CHECKLIST.md` for the
detailed steps.

- [ ] All §1.4 outstanding items resolved (or explicitly deferred with sign-off)
- [ ] All §2 environment variables provisioned in both Vercel (frontend) and Modal secret
      (backend) — see `DEPLOYMENT_CHECKLIST.md` §6 and §4
- [ ] `.env.example` updated to include `WATERMARK_*` and `GOOGLE_DRIVE_*` vars (currently
      missing — flagged in §6 below)
- [ ] `npx prisma db push && npx prisma generate` run against the real Supabase DB (Phase 2
      Task 1 — still pending real credentials)
- [ ] S3 lifecycle policy applied (`infra/s3-lifecycle.json` — Phase 1 Task 6.4, still `[ ]`
      per `PHASE_1_CHECKLIST.md`)
- [ ] At least Scenario A (baseline) passes against live infra before attempting B/C/D
- [ ] Scenarios B, C, D run and results recorded in this file (append a "Results" section)

---

## 6. Open Items / Risks Carried Forward

1. **`.env.example` is stale** — does not list `WATERMARK_*` (8 vars) or `GOOGLE_DRIVE_*`
   (3 vars) added in Phases 3-4. A new developer following `.env.example` alone would not know
   these exist. Recommend updating `.env.example` (and `env.js` if any need frontend
   visibility — currently none do, they're backend-only/Modal-secret).
2. **`assets/watermark.png` + Modal image bundling (PHASE_3 Tasks 1/2) are prerequisites for
   `WATERMARK_IMAGE_ENABLED=true` to actually work** — without them, Scenario C.2 cannot pass.
3. **Drive file IDs are not persisted** — if per-clip "Open in Drive" links are wanted later,
   this needs a `Clip.driveFileId` column + Inngest update step (PHASE_4 Task 3, deferred).
4. **Phase 2 Task 8 (E2E YouTube test) and Phase 1 Task 6.4 (lifecycle policy applied)** were
   already flagged as pending real credentials in their respective checklists — both are
   re-surfaced here as blockers for full Phase 5 sign-off.
