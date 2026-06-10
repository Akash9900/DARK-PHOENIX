# Deployment Guide

This is the entry-point deployment guide for Dark Phoenix. It summarizes what the project does,
what you need before you start, and walks through deploying every piece of infrastructure. For
exhaustive detail on any single step, follow the links to `DEPLOYMENT_CHECKLIST.md`,
`INFRASTRUCTURE.md`, and `PHASE_5_CHECKLIST.md`.

---

## 1. What This Project Does

Dark Phoenix is an AI podcast clipper: it takes a long-form video (uploaded directly or pulled
from YouTube), finds the most engaging moments using AI, and produces short, vertical
(9:16), subtitled clips ready for social media — optionally watermarked and delivered to Google
Drive.

Three features were added in this submission, on top of an existing pipeline (upload → S3 →
WhisperX transcription → Gemini clip selection → TalkNet active-speaker detection → vertical
video + subtitle burn → S3):

1. **YouTube ingestion** — paste a YouTube URL instead of uploading a file. The backend
   downloads the video via `yt-dlp` and feeds it into the same pipeline as a file upload.
2. **Watermarking** — every generated clip can have a text watermark (e.g. a brand name) and/or
   an image/logo overlay burned in via ffmpeg, with configurable position, opacity, and size.
   Fully opt-in via env vars; failures don't block delivery.
3. **Google Drive delivery** — generated clips can additionally be uploaded to a Google Drive
   folder via a service account, in addition to S3. Opt-in; failures don't block S3 delivery.

---

## 2. Prerequisites

### Accounts
- AWS account (S3)
- Supabase account (Postgres database)
- Discord application (OAuth login — `discord.com/developers/applications`)
- Stripe account (credit pack purchases)
- Google AI Studio / Gemini API key
- Modal account (`modal.com`) — GPU serverless compute
- Inngest account (`inngest.com`) — event orchestration
- Vercel account — frontend hosting
- Google Cloud project (only if enabling Drive delivery) — Drive API + service account

### Local tooling
- Node.js (for the Next.js frontend, `ai-podcast-clipper-frontend/`)
- Python 3.11 + `pip` (for `setup_modal_secret.py` and local backend tooling)
- `modal` CLI (`pip install modal`, then `modal setup`)
- `aws` CLI (for applying S3 CORS/lifecycle configs)
- `npx prisma` (bundled with the frontend's `node_modules`)

---

## 3. Step-by-Step Deployment

These steps are in dependency order — each step's output feeds the next. Full detail for each
is in `DEPLOYMENT_CHECKLIST.md`.

### 3.1 AWS S3
1. Create a bucket (note its name and region).
2. Apply CORS so the browser can upload directly via presigned URLs:
   ```bash
   aws s3api put-bucket-cors --bucket <BUCKET> --cors-configuration file://infra/s3-cors.json
   ```
   Edit `infra/s3-cors.json` first and replace `https://<vercel-domain>` with your real Vercel
   domain (added once you know it from step 3.6 — you can re-apply this later).
3. Apply the lifecycle policy (auto-expires source videos after 7 days, clips after 30 days):
   ```bash
   aws s3api put-bucket-lifecycle-configuration --bucket <BUCKET> \
     --lifecycle-configuration file://infra/s3-lifecycle.json
   ```
4. Create an IAM user scoped to this bucket (`PutObject`, `GetObject`, `ListBucket`,
   `PutObjectTagging`). Save the access key pair.

→ See `DEPLOYMENT_CHECKLIST.md` §1.

### 3.2 Supabase Postgres
1. Create a project, copy the Postgres connection string into `DATABASE_URL`.
2. From `ai-podcast-clipper-frontend/`:
   ```bash
   npx prisma db push
   npx prisma generate
   ```
   (This project uses `db push`, not migration files — there is no `prisma/migrations/`
   directory.)

→ See `DEPLOYMENT_CHECKLIST.md` §2.

### 3.3 Google Cloud (Drive Delivery — optional)
1. Enable the Drive API on a GCP project, create a service account, download its JSON key.
2. Base64-encode the key file → `GOOGLE_DRIVE_CREDENTIALS_JSON`.
3. Create/choose a Drive folder, share it with the service account's `client_email`, copy the
   folder ID from the URL → `GOOGLE_DRIVE_FOLDER_ID`.
4. Leave `GOOGLE_DRIVE_ENABLED=false` until you've verified this works (Scenario D in
   `PHASE_5_CHECKLIST.md`).

→ See `DEPLOYMENT_CHECKLIST.md` §3 and `INFRASTRUCTURE.md` §5.

### 3.4 Modal (Backend)
1. `modal setup` to authenticate.
2. Fill in the project-root `.env` with all backend variables (see §4 below).
3. Run `python ai-podcast-clipper-backend/setup_modal_secret.py` — it prints a ✓/✗ status table
   for every required variable and constructs the secret payload.
4. Create the persistent Modal secret named `ai-podcast-clipper-secret` in the
   [Modal dashboard](https://modal.com/secrets) using the values printed in step 3.
5. Deploy:
   ```bash
   modal deploy ai-podcast-clipper-backend/main.py
   ```
6. Copy the emitted HTTPS endpoint URL → `PROCESS_VIDEO_ENDPOINT`.

**Note:** if `WATERMARK_IMAGE_ENABLED=true`, ensure
`ai-podcast-clipper-backend/assets/watermark.png` exists before deploying — the Modal image now
bundles the `assets/` directory automatically (`add_local_dir("assets", "/assets", copy=True)`).

→ See `DEPLOYMENT_CHECKLIST.md` §4.

### 3.5 Inngest
1. Generate production signing + event keys from the Inngest dashboard.
2. Add `INNGEST_SIGNING_KEY` and `INNGEST_EVENT_KEY` as Vercel environment variables (the
   Inngest SDK reads these directly from `process.env` — they are not part of `env.js` or the
   Modal secret).
3. After your first Vercel deploy, register the app in Inngest pointing at
   `https://<your-domain>/api/inngest` and confirm the `process-video-events` function appears.

→ See `DEPLOYMENT_CHECKLIST.md` §5.

### 3.6 Vercel (Frontend)
1. Import the repo, set the project root to `ai-podcast-clipper-frontend`.
2. Add all environment variables listed in §4 below.
3. Deploy. The build will fail fast (via `@t3-oss/env-nextjs` validation in `src/env.js`) if a
   required variable is missing — read the error to find which one.
4. Set up the Stripe webhook endpoint (`/api/webhooks/stripe`) and put its signing secret into
   `STRIPE_WEBHOOK_SECRET`.
5. Go back to step 3.1 and re-apply the S3 CORS config with your real Vercel domain.

→ See `DEPLOYMENT_CHECKLIST.md` §6.

### 3.7 Seed a Test User
Sign in once via Discord, then bump that user's `credits` in Supabase if needed (default is 10).

→ See `DEPLOYMENT_CHECKLIST.md` §7.

---

## 4. Environment Variables — Quick Reference

The full list (31 variable names, ~26 unique secrets, with formats and examples) lives in
**`INFRASTRUCTURE.md`**. Summary:

| Group | Count | Where it lives |
|-------|-------|----------------|
| Frontend-only (auth, DB, Stripe, app URL) | 12 | Vercel env vars (`src/env.js`) |
| Shared (AWS creds, S3 bucket, shared auth token) | 5 | Both Vercel **and** Modal secret |
| Backend-only (Gemini, watermark, Drive) | 13 | Modal secret only (`setup_modal_secret.py`) |
| Inngest | 2 | Vercel env vars only (not in `env.js`) |

All backend-only and shared variables are managed through
`ai-podcast-clipper-backend/setup_modal_secret.py`, which loads them from the project-root
`.env` and prints a status table — run it any time to check what's missing.

**Note:** `.env.example` predates the watermark and Drive features and does not yet list those
variable names. Use `INFRASTRUCTURE.md` §2.3 as the authoritative list for those.

---

## 5. Testing Checklist

Once steps 3.1-3.6 are complete, run the manual scenarios in `PHASE_5_CHECKLIST.md` §4, in
order:

1. **Scenario A** — baseline file upload, watermark and Drive both disabled. Confirms the core
   pipeline (upload → S3 → transcription → clip generation → DB → UI) still works.
2. **Scenario B** — YouTube URL ingestion, including the error path (private/deleted video
   should surface as a failed job, not hang).
3. **Scenario C** — watermarking on/off, text and image variants, including the graceful
   fallback when `assets/watermark.png` is missing.
4. **Scenario D** — Google Drive delivery, including failure fallback (S3 still succeeds even
   if Drive credentials are bad).

Only proceed to B/C/D once A passes cleanly.

---

## 6. Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| Vercel build fails with a Zod validation error | A required var in `src/env.js` is missing | Check the error message for the variable name, add it in Vercel project settings |
| Browser upload (`PUT` to S3) fails with a CORS error | `infra/s3-cors.json` not applied, or `AllowedOrigins` doesn't include your domain | Re-apply `aws s3api put-bucket-cors` with the correct domain |
| Inngest function never fires after upload | `INNGEST_SIGNING_KEY`/`INNGEST_EVENT_KEY` missing, or app not registered with Inngest pointing at `/api/inngest` | Verify both env vars are set in Vercel and the app shows up in the Inngest dashboard |
| Modal endpoint returns 401 | `PROCESS_VIDEO_ENDPOINT_AUTH` (Vercel) and `AUTH_TOKEN` (Modal secret) don't match | Ensure both sides have the identical bearer token string |
| YouTube ingestion fails immediately | `download_from_youtube()` raised `YouTubeDownloadError` (private/age-restricted/deleted video) | Check Modal logs for the exact `yt-dlp` error; this is expected behavior for unavailable videos (returns HTTP 422) |
| Clips upload but have no watermark despite `WATERMARK_ENABLED=true` | Check Modal logs for `WARNING: watermark failed, uploading clip without watermark: ...` | If the warning mentions a missing image file, confirm `assets/watermark.png` exists and was bundled (`add_local_dir("assets", "/assets", copy=True)` in `main.py`) |
| Clips don't appear in Google Drive | `GOOGLE_DRIVE_ENABLED=false`, `GOOGLE_DRIVE_FOLDER_ID` unset, or folder not shared with the service account | Check Modal logs for `WARNING: Google Drive upload failed, ...` — S3 delivery is unaffected either way |
| `npx prisma db push` fails to connect | `DATABASE_URL` malformed (special characters in password must be URL-encoded) | Re-encode the password (`@` → `%40`, etc.) |

---

## 7. Known Limitations

- **No automated test suite yet.** `PROJECT_PLAN.md` §Phase 5 specifies Playwright + Vitest +
  pytest + CI; this submission instead provides a manual verification checklist
  (`PHASE_5_CHECKLIST.md`). Automated coverage is future work.
- **Google Drive delivery uses a single shared service account**, not per-user OAuth. All
  clips (across all users) go to one configured Drive folder. See `WRITE_UP.md` for the
  rationale.
- **Drive file IDs are not persisted or surfaced in the UI** — uploads happen, but there's no
  "Open in Drive" link per clip yet (logged to Modal output only).
- **No "Watermarked" badge in the UI** — watermarking is fully functional on the backend, but
  there's no visual indicator in the dashboard that a clip was watermarked.
- **`.env.example` is stale** relative to the watermark/Drive variables — use
  `INFRASTRUCTURE.md` as the source of truth until it's updated.

---

## 8. Future Improvements

- Build out the automated test suite per `PROJECT_PLAN.md` §Phase 5 (Playwright, Vitest,
  pytest, CI pipeline).
- Per-user Google Drive OAuth (per `PROJECT_PLAN.md` §Phase 4 original design), layered on top
  of or replacing the current service-account approach.
- Persist `Clip.driveFileId` and surface "Open in Drive" links + a "Watermarked" badge in
  `clip-display.tsx`.
- Update `.env.example` and consider a startup-time validation step for the backend (mirroring
  `env.js`'s frontend validation) so missing watermark/Drive vars fail fast with a clear
  message instead of a graceful-fallback warning at clip time.
- Retry/backoff for Google Drive uploads (per `PROJECT_PLAN.md` §4.6).
