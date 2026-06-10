# Deployment Checklist — Phase 6 Prep

**Branch:** `feature/complete-deployment`
**Goal:** Step-by-step checklist for standing up every piece of infrastructure this project
depends on, in the order needed so each step's outputs are available for the next. Pairs with
`PHASE_5_CHECKLIST.md` (what to verify) and `INFRASTRUCTURE.md` (reference details/formats).

**Nothing in this checklist has been executed** — it is a planning document. All credentials,
bucket names, folder IDs, etc. below are placeholders to be filled in during deployment.

---

## 1. AWS S3

- [ ] Create S3 bucket (e.g. `dark-phoenix-clips-prod`), note region
- [ ] **CORS configuration** — required for presigned PUT uploads from the browser
      (`generateUploadUrl()` in `src/actions/s3.ts`). No CORS file currently exists in the repo
      (`infra/` only has `s3-lifecycle.json`) — needs to be created and applied:
  ```json
  [
    {
      "AllowedOrigins": ["https://<your-vercel-domain>", "http://localhost:3000"],
      "AllowedMethods": ["PUT", "GET"],
      "AllowedHeaders": ["*"],
      "ExposeHeaders": ["ETag"],
      "MaxAgeSeconds": 3000
    }
  ]
  ```
  Apply with: `aws s3api put-bucket-cors --bucket <BUCKET> --cors-configuration file://infra/s3-cors.json`
- [ ] **Lifecycle policy** — `infra/s3-lifecycle.json` already exists (Phase 1 Task 6), apply it:
  ```bash
  aws s3api put-bucket-lifecycle-configuration \
    --bucket <BUCKET> \
    --lifecycle-configuration file://infra/s3-lifecycle.json
  aws s3api get-bucket-lifecycle-configuration --bucket <BUCKET>   # verify
  ```
  (rules: `Environment=source` objects expire after 7 days, `Environment=clip` after 30 days)
- [ ] Create an IAM user (or role) with a policy scoped to this bucket only:
      `s3:PutObject`, `s3:GetObject`, `s3:ListBucket`, `s3:PutObjectTagging` on
      `arn:aws:s3:::<BUCKET>` and `arn:aws:s3:::<BUCKET>/*`
- [ ] Record `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`, `S3_BUCKET_NAME` — used
      by **both** frontend (`env.js`) and backend (Modal secret)

---

## 2. Supabase Postgres

- [ ] Create a Supabase project, note the Postgres connection string
      (`postgresql://USER:PASSWORD@HOST:PORT/DATABASE`, URL-encode special characters in the
      password — e.g. `@` → `%40`)
- [ ] Set `DATABASE_URL` locally (or in CI) and run:
  ```bash
  cd ai-podcast-clipper-frontend
  npx prisma db push      # pushes schema.prisma to Supabase (no migrations dir — db push workflow)
  npx prisma generate     # regenerates the Prisma client
  ```
- [ ] Verify `UploadedFile.youtubeUrl` column exists (Phase 2 Task 1 schema change) —
      `npx prisma studio` or `\d "UploadedFile"` in `psql`
- [ ] Seed at least one test user with credits (see §7)

---

## 3. Google Cloud (Drive Service Account)

- [ ] Create/select a GCP project, enable the **Google Drive API**
- [ ] Create a service account (e.g. `dark-phoenix-drive-uploader@<project>.iam.gserviceaccount.com`)
- [ ] Generate a JSON key for the service account, download it
- [ ] Base64-encode the key file:
  ```bash
  base64 -i service-account-key.json | tr -d '\n' > drive-creds-b64.txt
  ```
  Set the contents of `drive-creds-b64.txt` as `GOOGLE_DRIVE_CREDENTIALS_JSON`
- [ ] Create (or choose) a Drive folder for clip delivery, **share it with the service
      account's `client_email`** (Editor access) — service accounts have minimal personal Drive
      storage, so this should ideally be a folder inside a Shared Drive or owned by a
      human user with sufficient quota (see `INFRASTRUCTURE.md` §4)
- [ ] Copy the folder ID from its URL
      (`https://drive.google.com/drive/folders/<FOLDER_ID>`) → `GOOGLE_DRIVE_FOLDER_ID`
- [ ] Set `GOOGLE_DRIVE_ENABLED=true` only once the above is verified working (Scenario D in
      `PHASE_5_CHECKLIST.md`)

---

## 4. Modal (Backend)

- [ ] `modal token new` (or `modal setup`) to authenticate the deploy environment
- [ ] Populate root `.env` with **all** backend vars (see `INFRASTRUCTURE.md` §1 for the full
      list — includes AWS, Gemini, watermark, and Drive vars)
- [ ] Run `python ai-podcast-clipper-backend/setup_modal_secret.py` to construct the secret
      object, then create the persistent secret named `ai-podcast-clipper-secret` at
      https://modal.com/secrets with the printed key/value pairs
- [ ] **If using image watermarking** (`WATERMARK_IMAGE_ENABLED=true`): ensure
      `ai-podcast-clipper-backend/assets/watermark.png` exists before deploying — the Modal
      image bundles `assets/` via `add_local_dir` (PHASE_3 Task 2 — confirm this is implemented
      before relying on it)
- [ ] Deploy: `modal deploy ai-podcast-clipper-backend/main.py`
- [ ] Note the emitted HTTPS endpoint URL → `PROCESS_VIDEO_ENDPOINT` (frontend env)
- [ ] Confirm `AUTH_TOKEN` (Modal secret) and `PROCESS_VIDEO_ENDPOINT_AUTH` (frontend env) are
      the **same value** — this is the shared bearer token between Inngest and Modal

---

## 5. Inngest

- [ ] Create an Inngest account/app (or use existing) for production
- [ ] Generate **production signing key** and **event key** from the Inngest dashboard
- [ ] Add `INNGEST_SIGNING_KEY` and `INNGEST_EVENT_KEY` to the Vercel project's environment
      variables — **note:** these are NOT currently declared in
      `ai-podcast-clipper-frontend/src/env.js`; the Inngest SDK reads them directly from
      `process.env` (standard Inngest convention), so no `env.js` change is needed, but they
      must still be set in Vercel
- [ ] In the Inngest dashboard, register the production app pointing at
      `https://<your-vercel-domain>/api/inngest`
- [ ] Verify the `process-video-events` function (`ai-podcast-clipper-frontend/src/inngest/functions.ts`)
      shows up registered in the Inngest dashboard after first deploy

---

## 6. Vercel (Frontend Deployment)

- [ ] Connect the GitHub repo to a new Vercel project, root directory =
      `ai-podcast-clipper-frontend`
- [ ] Set **Build Command** to include Prisma generate if not automatic:
      `npx prisma generate && next build` (or rely on `postinstall` if configured)
- [ ] Add the following environment variables in Vercel (Production + Preview as appropriate):

  | # | Variable | Source |
  |---|----------|--------|
  | 1 | `AUTH_SECRET` | `npx auth secret` |
  | 2 | `AUTH_DISCORD_ID` | Discord Developer Portal |
  | 3 | `AUTH_DISCORD_SECRET` | Discord Developer Portal |
  | 4 | `DATABASE_URL` | §2 Supabase |
  | 5 | `AWS_ACCESS_KEY_ID` | §1 AWS |
  | 6 | `AWS_SECRET_ACCESS_KEY` | §1 AWS |
  | 7 | `AWS_REGION` | §1 AWS |
  | 8 | `S3_BUCKET_NAME` | §1 AWS |
  | 9 | `PROCESS_VIDEO_ENDPOINT` | §4 Modal |
  | 10 | `PROCESS_VIDEO_ENDPOINT_AUTH` | §4 Modal (`AUTH_TOKEN`) |
  | 11 | `STRIPE_SECRET_KEY` | Stripe Dashboard |
  | 12 | `STRIPE_WEBHOOK_SECRET` | Stripe Dashboard (webhook endpoint) |
  | 13 | `STRIPE_SMALL_CREDIT_PACK` / `STRIPE_MEDIUM_CREDIT_PACK` / `STRIPE_LARGE_CREDIT_PACK` | Stripe Price IDs |
  | 14 | `NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY` | Stripe Dashboard |
  | — | `BASE_URL` | `https://<your-vercel-domain>` |
  | — | `INNGEST_SIGNING_KEY` / `INNGEST_EVENT_KEY` | §5 Inngest |

  (Table numbered 1-14 per the user's "14 env vars" framing — `BASE_URL` and the two Inngest
  keys are listed separately since they're additive to the 14 in `env.js`'s `server` block;
  see `INFRASTRUCTURE.md` §1 for the complete unified list.)

- [ ] Trigger first deploy, confirm build succeeds (env validation via `@t3-oss/env-nextjs`
      will fail the build if any required var above is missing)
- [ ] Set up Stripe webhook endpoint pointing at
      `https://<your-vercel-domain>/api/webhooks/stripe`, copy signing secret into
      `STRIPE_WEBHOOK_SECRET`

---

## 7. Testing Credentials (Seeded Test User)

- [ ] Sign in once via Discord OAuth on the deployed app to create a `User` row
- [ ] Manually bump that user's `credits` in Supabase (default is `10` per
      `prisma/schema.prisma`, should be enough for a few test clips — top up if running many
      Phase 5 scenarios)
- [ ] Record the test user's email/Discord handle for repeatable testing
- [ ] (Optional) Create a second test user with `credits: 0` to test the "no credits" status
      path (`UploadedFile.status == "no credits"`)

---

## 8. Post-Deployment Smoke Test

Run `PHASE_5_CHECKLIST.md` §4 Scenario A (baseline file upload, no watermark, no Drive) first.
Only proceed to Scenarios B/C/D once A passes cleanly.

---

## Open Items Carried Forward

- `infra/s3-cors.json` does not exist yet — needs to be created (§1)
- `infra/s3-lifecycle.json` exists but has not been applied to a real bucket yet
  (`PHASE_1_CHECKLIST.md` Task 6.4 still `[ ]`)
- `INNGEST_SIGNING_KEY`/`INNGEST_EVENT_KEY` are not in `.env.example` or `env.js` — add to
  `.env.example` for completeness even though `env.js` doesn't need to validate them
- PHASE_3 Task 2 (Modal image bundles `assets/`) must land before
  `WATERMARK_IMAGE_ENABLED=true` can be used in production (§4)
