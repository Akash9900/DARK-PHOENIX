# Phase 4 Implementation Checklist — Google Drive Delivery

**Branch:** `feature/complete-deployment`
**Goal:** After a clip is uploaded to S3 in `process_clip()`, also upload it to a
Google Drive folder, so users get clips delivered to Drive automatically.

---

## Architecture Deviation from `PROJECT_PLAN.md` §Phase 4

`PROJECT_PLAN.md` §4.1-4.4 describes a **per-user OAuth 2.0** flow: users connect their own
Google Drive account from the Next.js frontend (`src/actions/google-drive.ts`,
`GoogleDriveCredential` Prisma model, `drive.file` scope, OAuth consent screen, token refresh).

**Task 1's explicit instructions specify a different architecture**: a single **service account**
used directly from the Modal Python backend (`main.py`), uploading every clip to one
admin-configured Drive folder. This is simpler (no per-user OAuth, no token storage/refresh, no
new Prisma model) but means:

- All clips go to **one shared Drive folder/account** (the service account's Drive, or a folder
  shared with it), not a per-user folder.
- No "Connect Google Drive" UX, no `GoogleDriveCredential` table, no OAuth routes.
- `folder_id` is a single configured value (env var), not per-user.

This checklist documents the **service-account architecture as actually implemented**, since it
supersedes the OAuth design in `PROJECT_PLAN.md` for this phase. If per-user OAuth delivery is
needed later, it can be layered on top (e.g., service account uploads to a staging folder, then
a separate per-user "Export to Drive" step copies/shares from there) — out of scope for now.

---

## Reference: Current State

- `ai-podcast-clipper-backend/main.py` — `process_clip()` (after Phase 3) ends with:
  ```python
  try:
      apply_watermark(str(subtitle_output_path), str(watermarked_path))
      clip_path = watermarked_path
  except WatermarkError as e:
      print(f"WARNING: watermark failed, uploading clip without watermark: {e}")
      clip_path = subtitle_output_path

  s3_client = boto3.client("s3")
  s3_client.upload_file(
      clip_path, os.environ["S3_BUCKET_NAME"], output_s3_key,
      ExtraArgs={"Tagging": "Environment=clip"})
  ```
  **This is where the Drive upload step will be inserted (Task 2)** — after the S3 upload, using
  `clip_path` as the local file to upload.
- `ai-podcast-clipper-backend/setup_modal_secret.py` — existing pattern for adding env vars to
  the Modal secret (most recently extended in Phase 3 with the `WATERMARK_*` vars).
- Error-handling pattern established in Phase 2/3: custom `XxxError(Exception)` classes
  (`YouTubeDownloadError`, `WatermarkError`), raised with descriptive messages on failure.

---

## Task Breakdown

### Task 1 — Set up Google Drive credentials and `upload_to_drive()` (DONE — this task)

- **File:** `ai-podcast-clipper-backend/requirements.txt` — add:
  - `google-auth`
  - `google-auth-httplib2`
  - `google-auth-oauthlib`
  - `google-api-python-client`
- **File:** `ai-podcast-clipper-backend/main.py` — add:
  - `class DriveUploadError(Exception): pass`
  - `def upload_to_drive(file_path: str, folder_id: str, file_name: str) -> str`
    - Reads `GOOGLE_DRIVE_CREDENTIALS_JSON` (base64-encoded service account JSON key) from env
    - Decodes + parses JSON, builds `google.oauth2.service_account.Credentials` with scope
      `https://www.googleapis.com/auth/drive.file`
    - Uses `googleapiclient.discovery.build("drive", "v3", credentials=...)` and
      `MediaFileUpload` to upload `file_path` into `folder_id` as `file_name`
    - Returns the uploaded file's Drive file ID
    - Raises `DriveUploadError` on: missing env var, invalid base64/JSON, or any API/auth
      exception during build/upload
- **File:** `ai-podcast-clipper-backend/setup_modal_secret.py` — add `GOOGLE_DRIVE_CREDENTIALS_JSON`
  to the secret dict and status print block, following the `WATERMARK_*` pattern from Phase 3.
- **Not done in this task** (deferred to Task 2): wiring `upload_to_drive()` into
  `process_clip()`, and adding `GOOGLE_DRIVE_FOLDER_ID` (the destination folder, also via env var).

- [x] `requirements.txt` updated with 4 Google API packages
- [x] `DriveUploadError` exception class added
- [x] `upload_to_drive()` implemented (service account auth, returns Drive file ID, raises on failure)
- [x] `GOOGLE_DRIVE_CREDENTIALS_JSON` added to `setup_modal_secret.py`
- [x] `python3 -m py_compile main.py` passes
- [x] `python3 -m py_compile setup_modal_secret.py` passes

---

### Task 2 — Wire `upload_to_drive()` into `process_clip()` (not started)

- Add `GOOGLE_DRIVE_FOLDER_ID` env var (target folder ID) and `GOOGLE_DRIVE_ENABLED` toggle
  (default `false`, so Drive upload is opt-in like watermarking).
- After the S3 upload in `process_clip()`, if enabled, call
  `upload_to_drive(str(clip_path), folder_id, f"{clip_name}.mp4")` in a try/except
  `DriveUploadError`, log a warning on failure, and **do not fail the job** — S3 upload already
  succeeded, per the graceful-fallback requirement in this task's context.
- Decide whether to store the returned Drive file ID anywhere (e.g., return it from
  `process_clip()` for the caller to persist to the DB) — needs a DB field if so (out of scope
  unless requested).

- [ ] `GOOGLE_DRIVE_ENABLED` / `GOOGLE_DRIVE_FOLDER_ID` env vars added to `setup_modal_secret.py`
- [ ] `upload_to_drive()` called after S3 upload, gated by `GOOGLE_DRIVE_ENABLED`
- [ ] `DriveUploadError` caught, logged, does not fail the clip/job
- [ ] `python3 -m py_compile main.py` passes

---

### Task 3 — Frontend: surface Drive upload status (not started)

- TBD once Task 2's return-value/persistence design is decided. Likely a `Clip.driveFileId`
  field + "Open in Drive" link, mirroring the watermark badge from Phase 3 Task 6.

---

### Task 4 — Verification & manual testing (not started)

- Manual test: set `GOOGLE_DRIVE_CREDENTIALS_JSON` (base64 of a real service account key) and
  `GOOGLE_DRIVE_FOLDER_ID` (a folder shared with that service account's email), run a clip
  through `process_clip()`, confirm the file appears in the Drive folder.
- Error-path test: unset/invalid `GOOGLE_DRIVE_CREDENTIALS_JSON` → confirm `DriveUploadError` is
  raised by `upload_to_drive()` directly, and (after Task 2) that `process_clip()` still
  completes the S3 upload successfully.

---

## Environment Variable Reference

| Variable | Default | Description |
|----------|---------|-------------|
| `GOOGLE_DRIVE_CREDENTIALS_JSON` | *(none)* | Base64-encoded JSON service account key. Required for any Drive upload. |
| `GOOGLE_DRIVE_ENABLED` | `false` *(Task 2)* | Enables the Drive upload step in `process_clip()`. |
| `GOOGLE_DRIVE_FOLDER_ID` | *(none)* *(Task 2)* | Destination Drive folder ID. The service account must have write access (folder shared with its `client_email`). |

---

## Open Items / Risks Carried Forward

1. **Single shared Drive destination** (service account architecture) vs. the per-user OAuth
   design in `PROJECT_PLAN.md` §4.1-4.4 — see "Architecture Deviation" above. Revisit if
   per-user delivery becomes a requirement.
2. **Service account storage quota**: service accounts have their own (small) Drive storage
   unless uploading into a folder owned by a regular user/Shared Drive. For production, the
   target folder should be a **Shared Drive** folder or a folder shared with the service account
   by a user with sufficient quota.
3. No retry/backoff on Drive API calls (PROJECT_PLAN.md §4.6 mentions retry-with-backoff for
   network interruptions) — `upload_to_drive()` raises immediately on any exception. Can be
   added in Task 2 if needed.
