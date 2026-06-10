# Infrastructure Reference

Reference document for all external services, accounts, and credential formats this project
depends on. Pairs with `DEPLOYMENT_CHECKLIST.md` (step-by-step setup) and
`PHASE_5_CHECKLIST.md` (verification).

---

## 1. Required Services & Accounts

| Service | Used for | Consumed by |
|---------|----------|-------------|
| AWS S3 | Source video + clip storage | Frontend (`actions/s3.ts`) + Backend (`main.py`) |
| Supabase (Postgres) | App database (Prisma) | Frontend only |
| Discord (OAuth) | User authentication (NextAuth) | Frontend only |
| Stripe | Credit pack purchases | Frontend only |
| Google Gemini API | Clip selection / transcript analysis | Backend only |
| Modal | GPU serverless video processing | Backend deployment target |
| Inngest | Event-driven orchestration (upload → process → DB update) | Frontend (`/api/inngest`) |
| Google Cloud (Drive API + service account) | Optional clip delivery to Drive | Backend only |
| Vercel | Frontend hosting | — |

---

## 2. Complete Environment Variable List (31 names, ~26 unique secrets)

### 2.1 Frontend-only (`ai-podcast-clipper-frontend/src/env.js`)

```
AUTH_SECRET
AUTH_DISCORD_ID
AUTH_DISCORD_SECRET
DATABASE_URL
NODE_ENV
STRIPE_SECRET_KEY
STRIPE_WEBHOOK_SECRET
STRIPE_SMALL_CREDIT_PACK
STRIPE_MEDIUM_CREDIT_PACK
STRIPE_LARGE_CREDIT_PACK
NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY
BASE_URL
```

### 2.2 Shared (frontend `env.js` AND backend `setup_modal_secret.py` — same value in both places)

```
AWS_ACCESS_KEY_ID
AWS_SECRET_ACCESS_KEY
AWS_REGION
S3_BUCKET_NAME
PROCESS_VIDEO_ENDPOINT_AUTH   (= AUTH_TOKEN on the backend side — names differ, value must match)
```

`PROCESS_VIDEO_ENDPOINT` is frontend-only (it's the Modal-generated URL; the backend doesn't
need to know its own URL).

### 2.3 Backend-only (Modal secret `ai-podcast-clipper-secret`, via `setup_modal_secret.py`)

```
GEMINI_API_KEY
MAX_CLIPS                      (default "10")
WATERMARK_ENABLED               (default "false")
WATERMARK_TEXT                  (default "LUNARTECH.AI")
WATERMARK_POSITION              (default "lower-right")
WATERMARK_OPACITY               (default "0.7")
WATERMARK_FONT_SIZE             (default "30")
WATERMARK_IMAGE_ENABLED         (default "false")
WATERMARK_IMAGE_PATH            (default "assets/watermark.png")
WATERMARK_IMAGE_SCALE           (default "0.1")
GOOGLE_DRIVE_CREDENTIALS_JSON
GOOGLE_DRIVE_ENABLED             (default "false")
GOOGLE_DRIVE_FOLDER_ID
```

### 2.4 Inngest (Vercel env, not in `env.js` — read directly via `process.env` by the Inngest SDK)

```
INNGEST_SIGNING_KEY
INNGEST_EVENT_KEY
```

---

## 3. Credential Formats

| Variable | Format | Example shape |
|----------|--------|----------------|
| `DATABASE_URL` | `postgresql://USER:PASSWORD@HOST:PORT/DATABASE`, password URL-encoded (`@`→`%40`, etc.) | `postgresql://postgres:p%40ss@db.xxxx.supabase.co:5432/postgres` |
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` | IAM access key pair, scoped to one bucket | `AKIA...` / `40-char secret` |
| `S3_BUCKET_NAME` | Bucket name only (no `s3://` prefix, no region) | `dark-phoenix-clips-prod` |
| `PROCESS_VIDEO_ENDPOINT` | Full HTTPS URL emitted by `modal deploy` | `https://<workspace>--ai-podcast-clipper-process-video.modal.run` |
| `PROCESS_VIDEO_ENDPOINT_AUTH` / `AUTH_TOKEN` | Arbitrary shared-secret bearer token (generate with `openssl rand -hex 32`); **must be identical on both sides** | `a3f5...` |
| `WATERMARK_POSITION` | One of exactly: `lower-right`, `lower-left`, `upper-right`, `upper-left` (used for both `drawtext` and `overlay` filters, with different coordinate variables internally) | `lower-right` |
| `WATERMARK_OPACITY` | Float string, `0.0`-`1.0` | `0.7` |
| `WATERMARK_IMAGE_SCALE` | Float string — fraction of 1080px output width, NOT a pixel value | `0.1` → 108px wide |
| `GOOGLE_DRIVE_CREDENTIALS_JSON` | **Base64-encoded** full JSON service account key file (the whole file, then base64'd as a single line) | `eyJ0eXBlIjogInNlcnZpY2VfYWNjb3VudCIsIC4uLn0=` |
| `GOOGLE_DRIVE_FOLDER_ID` | The ID segment from a Drive folder URL `.../folders/<THIS_PART>` | `1A2b3C4d5E6f...` |
| `STRIPE_*_CREDIT_PACK` | Stripe Price IDs (not Product IDs) | `price_1AbC...` |

---

## 4. S3 Bucket Structure & Lifecycle Rules

### Object key layout

```
<uuid>/original.mp4              # source video (uploaded file OR downloaded YouTube video)
<uuid>/clip_0.mp4                # generated clip 0
<uuid>/clip_1.mp4                # generated clip 1
...
<uuid>/clip_N.mp4
```

`<uuid>` = `UploadedFile.s3Key`'s directory component (set at `processYoutubeVideo()` /
`generateUploadUrl()` time as `${uuidv4()}/original.mp4`); clip keys are derived in
`process_clip()` as `f"{s3_key_dir}/clip_{clip_index}.mp4"`.

### Object tagging (drives lifecycle expiration)

| Tag | Applied to | Set by |
|-----|-----------|--------|
| `Environment=source` | `original.mp4` | `actions/s3.ts` (file upload path) and `main.py` `process_video()` (YouTube download path) |
| `Environment=clip` | `clip_N.mp4` | `main.py` `process_clip()` S3 upload |

### Lifecycle rules (`infra/s3-lifecycle.json`, Phase 1)

| Rule ID | Tag filter | Expiration |
|---------|-----------|------------|
| `expire-source-videos-7d` | `Environment=source` | 7 days |
| `expire-clips-30d` | `Environment=clip` | 30 days |

**Status:** file exists in repo but has not been applied to a real bucket
(`aws s3api put-bucket-lifecycle-configuration`) — see `DEPLOYMENT_CHECKLIST.md` §1.

### CORS

No `infra/s3-cors.json` exists yet. Required because `generateUploadUrl()` returns a presigned
PUT URL that the browser uploads to directly — the bucket must allow `PUT` from the frontend's
origin. See `DEPLOYMENT_CHECKLIST.md` §1 for the config to create.

---

## 5. Google Drive Folder Sharing Setup

The backend uses a **service account** (not per-user OAuth — see `PHASE_4_CHECKLIST.md`
"Architecture Deviation" for why this differs from `PROJECT_PLAN.md`'s original per-user OAuth
design).

1. Service account JSON key → base64 → `GOOGLE_DRIVE_CREDENTIALS_JSON`
2. Service account has an email like
   `<name>@<project>.iam.gserviceaccount.com` — found in the `client_email` field of the JSON
   key
3. **The destination Drive folder must be shared with this email** (Editor permission), or
   uploads will fail with a 404/403 from the Drive API (`upload_to_drive()` raises
   `DriveUploadError` in this case, but `process_clip()` catches it and the clip remains
   available in S3 — see graceful fallback)
4. **Storage quota caveat:** service accounts have very limited personal Drive storage. For any
   real volume of clips, the target folder should be:
   - a folder inside a **Shared Drive** (Shared Drives have pooled org storage, not tied to the
     service account), or
   - a folder owned by a human Workspace user with available quota, shared with the service
     account
5. `GOOGLE_DRIVE_FOLDER_ID` is the path segment from the folder's URL:
   `https://drive.google.com/drive/folders/<GOOGLE_DRIVE_FOLDER_ID>`
6. Scope used: `https://www.googleapis.com/auth/drive.file` (the service account can only
   access files/folders it created or that have been explicitly shared with it — minimal
   privilege)

---

## 6. Modal Secret Structure

Secret name: **`ai-podcast-clipper-secret`** (referenced by name in `main.py`'s Modal app
definition — must match exactly).

Built by `ai-podcast-clipper-backend/setup_modal_secret.py`, which:
1. Loads `../​.env` (project-root `.env`) via `python-dotenv`
2. Constructs a `modal.Secret.from_dict({...})` with all 13 backend-only vars (§2.3) plus the
   5 shared vars (§2.2, using `AUTH_TOKEN` as the key name for
   `PROCESS_VIDEO_ENDPOINT_AUTH`'s value)
3. Prints a ✓/✗ status table for each var (✓ Set / ✗ Missing) so you can confirm `.env` is
   complete before creating the secret in the Modal dashboard at https://modal.com/secrets

**To update the secret after changing `.env`:** re-run `setup_modal_secret.py` to see the
status table, then update the values in the Modal dashboard (the script prints values for
review but the actual `modal.Secret.from_dict(...)` object it builds is local — creating a
*persistent* named secret is a manual dashboard step, per the script's final printed
instructions).

---

## 7. Known Gaps (cross-referenced from PHASE_5_CHECKLIST.md / DEPLOYMENT_CHECKLIST.md)

- `.env.example` does not list the 8 `WATERMARK_*` or 3 `GOOGLE_DRIVE_*` vars from §2.3
- `infra/s3-cors.json` does not exist
- `infra/s3-lifecycle.json` exists but is unapplied
- `ai-podcast-clipper-backend/assets/watermark.png` does not exist (placeholder only —
  `.gitkeep`); `WATERMARK_IMAGE_ENABLED=true` will fail gracefully (no watermark, clip still
  uploads) until this + Modal image bundling (PHASE_3 Task 2) are done
