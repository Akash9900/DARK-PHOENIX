# Setup Guide — Provisioning All 6 Services

This is a concrete, click-by-click / command-by-command walkthrough for provisioning every
service Dark Phoenix depends on, in dependency order. Follow it top to bottom — each section's
output feeds later sections.

For the *why* behind each variable, see `INFRASTRUCTURE.md`. For the high-level overview, see
`DEPLOYMENT.md`. For what to test once everything is live, see `PHASE_5_CHECKLIST.md`.

**Conventions used below:**
- `<PLACEHOLDER>` — a value you choose or that's generated for you; replace it everywhere it
  appears.
- "Save as `VAR_NAME`" — add this to your project-root `.env` file (create it by copying
  `.env.example` if you haven't already: `cp .env.example .env`).
- All commands assume you're in the repo root (`/Users/akash/Desktop/project/lunar/DARK-PHOENIX`)
  unless a `cd` is shown.

---

## 1. AWS S3

### 1.1 Account creation
- If you don't have an AWS account: https://aws.amazon.com/ → "Create an AWS Account"
- Once signed in, go to the **S3 console**: https://s3.console.aws.amazon.com/s3/home

### 1.2 Create the bucket
1. In the S3 console, click **"Create bucket"**.
2. **Bucket name:** choose a globally-unique name, e.g. `dark-phoenix-clips-<yourname>` →
   save as `<S3_BUCKET_NAME>`.
3. **AWS Region:** pick one close to you, e.g. `us-east-1` → save as `<AWS_REGION>`.
4. Leave "Block all public access" **enabled** (the app uses presigned URLs, not public
   objects).
5. Click **"Create bucket"**.

### 1.3 Create an IAM user with scoped access
1. Go to the **IAM console**: https://console.aws.amazon.com/iam/home
2. Left sidebar → **Users** → **"Create user"**.
3. User name: `dark-phoenix-app` → click **Next**.
4. Permissions options → **"Attach policies directly"** → click **"Create policy"** (opens a
   new tab).
5. In the policy editor, switch to the **JSON** tab and paste (replace `<S3_BUCKET_NAME>` with
   your real bucket name from 1.2):
   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       {
         "Effect": "Allow",
         "Action": [
           "s3:PutObject",
           "s3:GetObject",
           "s3:ListBucket",
           "s3:PutObjectTagging"
         ],
         "Resource": [
           "arn:aws:s3:::<S3_BUCKET_NAME>",
           "arn:aws:s3:::<S3_BUCKET_NAME>/*"
         ]
       }
     ]
   }
   ```
6. Click **Next** → name it `dark-phoenix-s3-policy` → **Create policy**.
7. Back in the "Create user" tab, refresh the policy list, check `dark-phoenix-s3-policy` →
   **Next** → **Create user**.
8. Click into the new user → **Security credentials** tab → **"Create access key"** → choose
   **"Application running outside AWS"** → **Create access key**.
9. **Save immediately** (shown only once):
   - Access key → save as `<AWS_ACCESS_KEY_ID>`
   - Secret access key → save as `<AWS_SECRET_ACCESS_KEY>`

### 1.4 Configure your local AWS CLI (needed for steps 1.5/1.6)
```bash
aws configure
```
Enter the access key, secret, region from above, and `json` as output format.

### 1.5 Apply CORS configuration
The repo already has `infra/s3-cors.json`. Open it and replace `https://<vercel-domain>` with
`http://localhost:3000` for now (you'll add your real Vercel domain after step 6 and re-apply):

```bash
aws s3api put-bucket-cors --bucket <S3_BUCKET_NAME> \
  --cors-configuration file://infra/s3-cors.json
```

### 1.6 Apply lifecycle policy
```bash
aws s3api put-bucket-lifecycle-configuration --bucket <S3_BUCKET_NAME> \
  --lifecycle-configuration file://infra/s3-lifecycle.json
```
This makes objects tagged `Environment=source` expire after 7 days, and `Environment=clip`
after 30 days (already implemented in the app's upload code).

### 1.7 Verify
```bash
# CORS
aws s3api get-bucket-cors --bucket <S3_BUCKET_NAME>

# Lifecycle
aws s3api get-bucket-lifecycle-configuration --bucket <S3_BUCKET_NAME>

# Upload permission test
echo "test" > /tmp/test.txt
aws s3 cp /tmp/test.txt s3://<S3_BUCKET_NAME>/test.txt
aws s3 rm s3://<S3_BUCKET_NAME>/test.txt
```
All three commands should succeed without errors.

### 1.8 Environment variable mapping

| Value | Env var | Used by |
|-------|---------|---------|
| Access key from 1.3 | `AWS_ACCESS_KEY_ID` | Vercel + Modal secret |
| Secret key from 1.3 | `AWS_SECRET_ACCESS_KEY` | Vercel + Modal secret |
| Region from 1.2 | `AWS_REGION` | Vercel + Modal secret |
| Bucket name from 1.2 | `S3_BUCKET_NAME` | Vercel + Modal secret |

Add all four to your project-root `.env` now.

---

## 2. Supabase (Postgres Database)

### 2.1 Account creation
- https://supabase.com/dashboard → sign up / sign in
- Click **"New project"**

### 2.2 Create the project
1. **Organization:** pick or create one.
2. **Name:** `dark-phoenix` (or anything).
3. **Database Password:** generate a strong password and **save it somewhere safe** — you'll
   need it for the connection string. Avoid characters that need URL-encoding if possible
   (stick to letters/digits), to simplify step 2.3.
4. **Region:** pick one close to you.
5. Click **"Create new project"** and wait ~2 minutes for provisioning.

### 2.3 Get the connection string
1. In the project, go to **Project Settings** (gear icon) → **Database**.
2. Under **"Connection string"**, select the **URI** tab, and choose the **"Transaction"**
   pooler connection (recommended for serverless/Vercel) — it looks like:
   ```
   postgresql://postgres.<project-ref>:[YOUR-PASSWORD]@aws-0-<region>.pooler.supabase.com:6543/postgres
   ```
3. Replace `[YOUR-PASSWORD]` with your actual password from 2.2. If your password contains
   special characters, URL-encode them (e.g. `@` → `%40`, `#` → `%23`, `/` → `%2F`).
4. Save the full string as `<DATABASE_URL>`.

### 2.4 Push the Prisma schema
```bash
cd ai-podcast-clipper-frontend
echo 'DATABASE_URL="<DATABASE_URL>"' >> .env   # or set it in your shell
npx prisma db push
npx prisma generate
```

### 2.5 Verify
1. In the Supabase dashboard, go to **Table Editor**.
2. Confirm tables exist: `User`, `Account`, `Session`, `UploadedFile`, `Clip`, etc.
3. Click into `UploadedFile` and confirm a `youtubeUrl` column exists (nullable text).

### 2.6 Environment variable mapping

| Value | Env var | Used by |
|-------|---------|---------|
| Connection string from 2.3 | `DATABASE_URL` | Vercel only |

Add `DATABASE_URL` to your project-root `.env`.

---

## 3. Google Cloud (Drive Delivery — Optional but Recommended)

This step is only needed if you want clips automatically uploaded to Google Drive
(`GOOGLE_DRIVE_ENABLED=true`). You can skip this section and come back later — the app works
fully without it (clips are always delivered via S3).

### 3.1 Account / project creation
1. Go to https://console.cloud.google.com/
2. Top-left project dropdown → **"New Project"** → name it `dark-phoenix` → **Create**.
3. Make sure the new project is selected in the dropdown.

### 3.2 Enable the Drive API
1. Go to https://console.cloud.google.com/apis/library/drive.googleapis.com
2. Confirm the `dark-phoenix` project is selected → click **"Enable"**.

### 3.3 Create a service account
1. Go to https://console.cloud.google.com/iam-admin/serviceaccounts
2. Click **"Create service account"**.
3. **Name:** `dark-phoenix-drive-uploader`. Note the auto-generated email, e.g.
   `dark-phoenix-drive-uploader@dark-phoenix-XXXXXX.iam.gserviceaccount.com` → save this as
   `<SERVICE_ACCOUNT_EMAIL>`.
4. Click **"Create and Continue"** → skip the optional role/access steps → **Done**.

### 3.4 Generate a JSON key
1. Click into the service account you just created.
2. Go to the **"Keys"** tab → **"Add Key"** → **"Create new key"** → format **JSON** → **Create**.
3. A file downloads automatically, e.g. `dark-phoenix-XXXXXX-abc123.json`. **Keep this file
   safe — it's a credential.**

### 3.5 Base64-encode the key
```bash
base64 -i ~/Downloads/dark-phoenix-XXXXXX-abc123.json | tr -d '\n' > /tmp/drive-creds-b64.txt
cat /tmp/drive-creds-b64.txt
```
Copy the entire output (one long line) → save as `<GOOGLE_DRIVE_CREDENTIALS_JSON>`.

### 3.6 Create and share a Drive folder
1. Go to https://drive.google.com/ (your personal/Workspace account).
2. Create a new folder, e.g. "Dark Phoenix Clips".
3. Right-click the folder → **"Share"** → add `<SERVICE_ACCOUNT_EMAIL>` (from 3.3) as
   **Editor** → **Send/Share** (you can ignore the "no notification" warning for service
   accounts).
4. Open the folder and copy the ID from the URL:
   ```
   https://drive.google.com/drive/folders/<THIS_PART_IS_THE_FOLDER_ID>
   ```
   Save as `<GOOGLE_DRIVE_FOLDER_ID>`.

> **Quota note:** service accounts have very limited personal storage. A folder owned by your
> regular Google account (shared with the service account) works fine for moderate volume. For
> heavy production use, consider a Shared Drive instead — see `INFRASTRUCTURE.md` §5.

### 3.7 Verify (optional, requires Python locally)
```bash
python3 -c "
import base64, json
from google.oauth2 import service_account
from googleapiclient.discovery import build

creds_json = base64.b64decode(open('/tmp/drive-creds-b64.txt').read())
info = json.loads(creds_json)
creds = service_account.Credentials.from_service_account_info(
    info, scopes=['https://www.googleapis.com/auth/drive.file'])
service = build('drive', 'v3', credentials=creds)
result = service.files().list(q=\"'<GOOGLE_DRIVE_FOLDER_ID>' in parents\", fields='files(id,name)').execute()
print('Folder accessible. Files:', result.get('files'))
"
```
(Requires `pip install google-auth google-api-python-client` locally.) An empty `files: []`
list with no error means the service account can see the folder.

### 3.8 Environment variable mapping

| Value | Env var | Used by |
|-------|---------|---------|
| Base64 key from 3.5 | `GOOGLE_DRIVE_CREDENTIALS_JSON` | Modal secret only |
| Folder ID from 3.6 | `GOOGLE_DRIVE_FOLDER_ID` | Modal secret only |
| — | `GOOGLE_DRIVE_ENABLED` | Modal secret only — set to `true` once verified, otherwise leave `false`/unset |

Add `GOOGLE_DRIVE_CREDENTIALS_JSON`, `GOOGLE_DRIVE_FOLDER_ID`, and `GOOGLE_DRIVE_ENABLED` to
your project-root `.env`.

---

## 4. Modal (GPU Backend)

### 4.1 Account creation
- https://modal.com/signup

### 4.2 Authenticate the CLI
```bash
pip install modal
modal setup
```
This opens a browser to link your CLI to your Modal account.

### 4.3 Make sure your `.env` is complete
By this point your project-root `.env` should have (from sections 1-3 above, plus your own
Gemini key and a generated shared auth token):

```
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_REGION=...
S3_BUCKET_NAME=...
DATABASE_URL=...
GOOGLE_DRIVE_CREDENTIALS_JSON=...      (optional)
GOOGLE_DRIVE_FOLDER_ID=...             (optional)
GOOGLE_DRIVE_ENABLED=true|false        (optional, default false)
GEMINI_API_KEY=...                     (from https://aistudio.google.com/apikey)
PROCESS_VIDEO_ENDPOINT_AUTH=...        (generate: openssl rand -hex 32)
```

Generate the shared auth token now if you haven't:
```bash
openssl rand -hex 32
```
Save the output as `<PROCESS_VIDEO_ENDPOINT_AUTH>` — add it to `.env` as
`PROCESS_VIDEO_ENDPOINT_AUTH=<that value>`.

(Optional — watermarking. If you want watermarks, also add to `.env`:)
```
WATERMARK_ENABLED=true
WATERMARK_TEXT="Your Brand"
WATERMARK_POSITION=lower-right
```
(All other `WATERMARK_*` vars have working defaults — see `INFRASTRUCTURE.md` §2.3.)

### 4.4 Build and review the secret
```bash
cd ai-podcast-clipper-backend
python3 setup_modal_secret.py
```
This prints a ✓/✗ status table for every variable. **Fix any `✗ Missing` for required vars**
(`GEMINI_API_KEY`, `AUTH_TOKEN`/`PROCESS_VIDEO_ENDPOINT_AUTH`, AWS×3, `S3_BUCKET_NAME`) before
continuing. Watermark/Drive vars can stay at defaults if you're not using those features yet.

### 4.5 Create the persistent Modal secret
1. Go to https://modal.com/secrets
2. Click **"Create new secret"** → choose **"Custom"**.
3. Name it exactly: `ai-podcast-clipper-secret`
4. Add each key/value pair printed by `setup_modal_secret.py` in step 4.4 (use the actual
   values from your `.env`, not the ✓/✗ display).
5. Click **"Create"**.

### 4.6 Deploy the backend
```bash
# still in ai-podcast-clipper-backend/
modal deploy main.py
```
This will take a while the first time (building the CUDA image, installing requirements,
downloading the Anton font, bundling `asd/` and `assets/`).

### 4.7 Verify
1. The deploy output prints a URL like:
   ```
   ✓ Created web function process_video =>
     https://<your-workspace>--ai-podcast-clipper-process-video.modal.run
   ```
   Save this as `<PROCESS_VIDEO_ENDPOINT>`.
2. Test it responds (should return 401/403 without auth, NOT a connection error):
   ```bash
   curl -i https://<your-workspace>--ai-podcast-clipper-process-video.modal.run
   ```
3. Check https://modal.com/apps for your app showing as deployed.

### 4.8 Environment variable mapping

| Value | Env var | Used by |
|-------|---------|---------|
| Endpoint URL from 4.7 | `PROCESS_VIDEO_ENDPOINT` | Vercel only |
| Token from 4.3 | `PROCESS_VIDEO_ENDPOINT_AUTH` (Vercel) / `AUTH_TOKEN` (Modal secret) | Both — **must be identical value** |
| All vars from 4.4 | — | Modal secret `ai-podcast-clipper-secret` (already done in 4.5) |

Add `PROCESS_VIDEO_ENDPOINT` to your project-root `.env`.

---

## 5. Inngest

### 5.1 Account creation
- https://app.inngest.com/sign-up

### 5.2 Create an app
1. After signing in, go to https://app.inngest.com/env/production/apps
2. Click **"Sync new app"** (you'll point this at your Vercel deployment's `/api/inngest`
   route — you can do this now and it'll show "unreachable" until step 6 is deployed, or come
   back after step 6).
3. App URL will be: `https://<your-vercel-domain>/api/inngest`

### 5.3 Generate signing key and event key
1. Go to https://app.inngest.com/env/production/manage/signing-key
   - Copy the **Signing Key** → save as `<INNGEST_SIGNING_KEY>`
2. Go to https://app.inngest.com/env/production/manage/keys
   - Copy (or create) an **Event Key** → save as `<INNGEST_EVENT_KEY>`

### 5.4 Verify
This can only be fully verified after Vercel deployment (step 6) — once deployed, return to
https://app.inngest.com/env/production/apps and confirm:
- Your app shows as **"Active"** / synced
- The function `process-video-events` (or similarly named, from
  `ai-podcast-clipper-frontend/src/inngest/functions.ts`) is listed

### 5.5 Environment variable mapping

| Value | Env var | Used by |
|-------|---------|---------|
| Signing key from 5.3 | `INNGEST_SIGNING_KEY` | Vercel only (not in `env.js`, not in Modal secret) |
| Event key from 5.3 | `INNGEST_EVENT_KEY` | Vercel only |

These are **not** added to your project-root `.env` for the backend — they go directly into
Vercel's environment variable settings in step 6.

---

## 6. Vercel (Frontend Deployment)

### 6.1 Account creation / GitHub connection
1. https://vercel.com/signup → sign up with GitHub (recommended, simplifies the next step).
2. If your Dark Phoenix repo isn't already on GitHub, push it there first.

### 6.2 Import the project
1. https://vercel.com/new
2. Find and **Import** your Dark Phoenix repository.
3. **Root Directory:** click "Edit" and set it to `ai-podcast-clipper-frontend`.
4. **Framework Preset:** should auto-detect "Next.js".
5. Don't deploy yet — first add environment variables (next step).

### 6.3 Add environment variables
In the import screen (or later under **Project → Settings → Environment Variables**), add each
of the following for **Production** (and Preview, if you want preview deployments to work too).
Values come from earlier sections as noted:

| # | Variable | Value source |
|---|----------|--------------|
| 1 | `AUTH_SECRET` | Run `npx auth secret` in `ai-podcast-clipper-frontend/`, copy output |
| 2 | `AUTH_DISCORD_ID` | See 6.4 below |
| 3 | `AUTH_DISCORD_SECRET` | See 6.4 below |
| 4 | `DATABASE_URL` | §2.6 |
| 5 | `AWS_ACCESS_KEY_ID` | §1.8 |
| 6 | `AWS_SECRET_ACCESS_KEY` | §1.8 |
| 7 | `AWS_REGION` | §1.8 |
| 8 | `S3_BUCKET_NAME` | §1.8 |
| 9 | `PROCESS_VIDEO_ENDPOINT` | §4.8 |
| 10 | `PROCESS_VIDEO_ENDPOINT_AUTH` | §4.8 (same value as Modal secret's `AUTH_TOKEN`) |
| 11 | `STRIPE_SECRET_KEY` | See 6.5 below |
| 12 | `STRIPE_WEBHOOK_SECRET` | See 6.5 below (added after first deploy) |
| 13 | `STRIPE_SMALL_CREDIT_PACK` | See 6.5 below |
| 14 | `STRIPE_MEDIUM_CREDIT_PACK` | See 6.5 below |
| 15 | `STRIPE_LARGE_CREDIT_PACK` | See 6.5 below |
| 16 | `NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY` | See 6.5 below |
| 17 | `BASE_URL` | `https://<your-vercel-domain>` (you'll know this after first deploy — use a placeholder like `https://dark-phoenix.vercel.app` for first deploy, update after) |
| 18 | `INNGEST_SIGNING_KEY` | §5.5 |
| 19 | `INNGEST_EVENT_KEY` | §5.5 |

#### 6.4 Discord OAuth (for #2, #3)
1. https://discord.com/developers/applications → **"New Application"** → name it `Dark Phoenix`.
2. Left sidebar → **OAuth2** → copy **Client ID** → `AUTH_DISCORD_ID`, and **Client Secret**
   (click "Reset Secret" if needed) → `AUTH_DISCORD_SECRET`.
3. Under **OAuth2 → Redirects**, add (after first deploy, update with real domain):
   ```
   https://<your-vercel-domain>/api/auth/callback/discord
   ```

#### 6.5 Stripe (for #11-16)
1. https://dashboard.stripe.com/register → create account (test mode is fine initially).
2. **API keys**: https://dashboard.stripe.com/test/apikeys
   - Secret key → `STRIPE_SECRET_KEY`
   - Publishable key → `NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY`
3. **Products**: https://dashboard.stripe.com/test/products → create 3 products (e.g. "Small
   Credit Pack", "Medium Credit Pack", "Large Credit Pack"), each with a one-time price. Copy
   each price's ID (`price_...`) → `STRIPE_SMALL_CREDIT_PACK` / `STRIPE_MEDIUM_CREDIT_PACK` /
   `STRIPE_LARGE_CREDIT_PACK` respectively.
4. **Webhook** (`STRIPE_WEBHOOK_SECRET`): do this *after* first deploy (step 6.7) since it
   needs your live URL — see 6.7.

### 6.6 Deploy
1. With variables 1-18 set (use a placeholder `BASE_URL` and skip `STRIPE_WEBHOOK_SECRET` for
   now — you'll redeploy after 6.7), click **"Deploy"**.
2. Wait for the build. If it fails on env validation (`@t3-oss/env-nextjs` Zod error), the
   error message names the missing variable — add it and redeploy.
3. Once deployed, copy your real domain, e.g. `dark-phoenix-xyz.vercel.app`.

### 6.7 Post-deploy fixups
1. **Update `BASE_URL`** in Vercel env vars to `https://<real-domain>` → redeploy (Vercel →
   Deployments → "..." → Redeploy).
2. **Stripe webhook**: https://dashboard.stripe.com/test/webhooks → "Add endpoint" → URL =
   `https://<real-domain>/api/webhooks/stripe` → select relevant checkout/payment events →
   create → copy the **Signing secret** → add as `STRIPE_WEBHOOK_SECRET` in Vercel → redeploy.
3. **Discord redirect URI**: update to `https://<real-domain>/api/auth/callback/discord`
   (from 6.4).
4. **S3 CORS**: re-run step 1.5 with the real domain in `infra/s3-cors.json`'s
   `AllowedOrigins` (replace or add alongside `localhost:3000`):
   ```bash
   aws s3api put-bucket-cors --bucket <S3_BUCKET_NAME> \
     --cors-configuration file://infra/s3-cors.json
   ```
5. **Inngest app sync**: go back to https://app.inngest.com/env/production/apps and confirm
   your app at `https://<real-domain>/api/inngest` shows as Active with the
   `process-video-events` function registered (per §5.4).

### 6.8 Final verification — seed a test user
1. Visit `https://<real-domain>` and sign in via Discord.
2. In Supabase **Table Editor** → `User` table, find your row, confirm `credits` is `10`
   (the default). Bump it higher manually if you plan to run many test clips.
3. Run **Scenario A** from `PHASE_5_CHECKLIST.md` §4: upload a short MP4 via the "Upload File"
   tab and confirm a clip appears under "My Clips" within a few minutes.
4. If Scenario A passes, proceed to Scenarios B (YouTube), C (watermark), D (Drive) as desired.

### 6.9 Environment variable mapping summary

All 19 variables above are Vercel-only **except**:
- `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`, `S3_BUCKET_NAME` — also in the
  Modal secret (§4.5)
- `PROCESS_VIDEO_ENDPOINT_AUTH` — also in the Modal secret, as `AUTH_TOKEN` (§4.5)

---

## Done — What You Should Have Now

- [ ] An S3 bucket with CORS + lifecycle policy applied, and an IAM user's keys saved
- [ ] A Supabase Postgres database with the Prisma schema pushed
- [ ] (Optional) A Google service account + shared Drive folder, base64 credentials saved
- [ ] A deployed Modal backend with the `ai-podcast-clipper-secret` populated, and its
      endpoint URL
- [ ] An Inngest app synced to your Vercel deployment's `/api/inngest`
- [ ] A live Vercel deployment with all 19 environment variables set
- [ ] A signed-in test user with credits, and a passing Scenario A test

If something doesn't work, check `DEPLOYMENT.md` §6 (Troubleshooting) before re-checking
individual steps above.
