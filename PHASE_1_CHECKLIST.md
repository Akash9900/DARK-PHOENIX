# Phase 1 Implementation Checklist — Infrastructure Hardening

**Branch:** `feature/complete-deployment`  
**Estimated total:** ~9 hours  
**Goal:** Fix all known production gaps before building new features (YouTube, Watermark, Drive).

---

## Phase 1 Confirmation

### Work Items (from PROJECT_PLAN.md)
- [x] 5-clip ceiling removal (`main.py:432`)
- [x] Credit refund on failure (`functions.ts:131-139`)
- [x] S3 ListObjects pagination (`functions.ts:144-160`)
- [x] Expand accepted video formats (`dashboard-client.tsx:138`)
- [x] Fix 4 typos (`dashboard-client.tsx:84,273`, `billing/page.tsx:130`, `actions/auth.ts:61`)
- [x] S3 lifecycle policy (`infra/s3-lifecycle.json`)

### Dependencies Between Phases
```
Phase 1 (this) ──► Phases 2, 3, 4 (independent of each other, all require Phase 1)
                                     └──► Phase 5 (testing, continuous)
                                                └──► Phase 6 (docs)
```
- Phases 2/3/4 have **no dependency on each other** — can be parallelized
- Phase 5 tests should be added **alongside** each feature, not after
- Phase 6 is written last when all features are stable

### Success Criteria (Phase 1 Done When)
- [ ] Processing a podcast with >5 good moments generates all of them (no ceiling)
- [ ] User credits unchanged after a Modal GPU failure
- [ ] Clip detection works correctly regardless of how many objects are in the S3 folder
- [ ] User can upload `.mov`, `.mkv`, `.webm` files (not just `.mp4`)
- [ ] Zero spelling errors visible in any page of the UI
- [ ] `infra/s3-lifecycle.json` committed and applied to AWS bucket

---

## Chunk 1 — Typo Fixes (≈30 min)

**Why first:** Zero risk, confirms the files are editable, satisfies the "no visible bugs" baseline.

### Task 1.1 — Fix "Upload filed" → "failed"
- **File:** `ai-podcast-clipper-frontend/src/components/dashboard-client.tsx:84`
- **Current:** `` throw new Error(`Upload filed with status: ${uploadResponse.status}`); ``
- **Fix:** `` throw new Error(`Upload failed with status: ${uploadResponse.status}`); ``
- [ ] Edit made
- [ ] Verified line 84 reads "failed"

### Task 1.2 — Fix "minuntes" → "minutes"
- **File:** `ai-podcast-clipper-frontend/src/components/dashboard-client.tsx:273`
- **Current:** `few minuntes.`
- **Fix:** `few minutes.`
- [ ] Edit made

### Task 1.3 — Fix "credtis" → "credits"
- **File:** `ai-podcast-clipper-frontend/src/app/dashboard/billing/page.tsx:130`
- **Current:** `Purchase credits to generate more podcast clips. The more credtis`
- **Fix:** `Purchase credits to generate more podcast clips. The more credits`
- [ ] Edit made

### Task 1.4 — Fix "occured" → "occurred"
- **File:** `ai-podcast-clipper-frontend/src/actions/auth.ts:61`
- **Current:** `return { success: false, error: "An error occured during signup" };`
- **Fix:** `return { success: false, error: "An error occurred during signup" };`
- [ ] Edit made

**Verification:**
```bash
grep -rn "filed\|minuntes\|credtis\|occured" \
  ai-podcast-clipper-frontend/src/
# Expect: no output
```
- [ ] grep returns no results

---

## Chunk 2 — 5-Clip Ceiling Removal (≈1 hour)

**Why:** The hardcoded `[:5]` slice silently drops clips Gemini finds. A 90-min podcast should yield 10-15 clips.

### Task 2.1 — Add `MAX_CLIPS` env var to backend
- **File:** `ai-podcast-clipper-backend/main.py`
- **Where to add:** Near the top of `process_video` method, after auth check (`~line 401`)
- **Add:**
  ```python
  max_clips = int(os.environ.get("MAX_CLIPS", "10"))
  ```
- [ ] Line added

### Task 2.2 — Remove the hardcoded `[:5]` slice
- **File:** `ai-podcast-clipper-backend/main.py:432`
- **Current:** `for index, moment in enumerate(clip_moments[:5]):`
- **Fix:** `for index, moment in enumerate(clip_moments[:max_clips]):`
- [ ] Edit made

### Task 2.3 — Add `MAX_CLIPS` to Modal secret / env
- **File:** `ai-podcast-clipper-backend/setup_modal_secret.py` (verify it exists and update)
- **Action:** Add `MAX_CLIPS=10` to the Modal secret dictionary so it's set in the GPU container
- [ ] Secret updated

### Task 2.4 — Update the Gemini prompt to request more clips
- **File:** `ai-podcast-clipper-backend/main.py:370`
- **Current prompt constraint:** `"a minimum of 30 and maximum of 60 seconds long"`
- **No change needed** — the prompt already asks for as many clips as valid; the `[:5]` was the limiter
- [x] Confirmed prompt is fine as-is

**Verification:**
```bash
grep -n "clip_moments\[" ai-podcast-clipper-backend/main.py
# Expect: clip_moments[:max_clips]  (NOT [:5])

grep -n "max_clips\|MAX_CLIPS" ai-podcast-clipper-backend/main.py
# Expect: both the os.environ.get line and the enumerate line
```
- [ ] grep output matches expectations

---

## Chunk 3 — S3 ListObjects Pagination Fix (≈1 hour)

**Why:** AWS returns max 1000 objects per `ListObjectsV2` call. A power user with many clips in one folder would silently get incomplete results. The fix uses `ContinuationToken` to page through all results.

### Task 3.1 — Rewrite `listS3ObjectsByPrefix` to paginate
- **File:** `ai-podcast-clipper-frontend/src/inngest/functions.ts:144-160`
- **Current code (lines 144-160):**
  ```typescript
  async function listS3ObjectsByPrefix(prefix: string) {
    const s3Client = new S3Client({ ... });
    const listCommand = new ListObjectsV2Command({
      Bucket: env.S3_BUCKET_NAME,
      Prefix: prefix,
    });
    const response = await s3Client.send(listCommand);
    return response.Contents?.map((item) => item.Key).filter(Boolean) ?? [];
  }
  ```
- **Replacement:**
  ```typescript
  async function listS3ObjectsByPrefix(prefix: string) {
    const s3Client = new S3Client({
      region: env.AWS_REGION,
      credentials: {
        accessKeyId: env.AWS_ACCESS_KEY_ID,
        secretAccessKey: env.AWS_SECRET_ACCESS_KEY,
      },
    });

    const keys: string[] = [];
    let continuationToken: string | undefined;

    do {
      const response = await s3Client.send(
        new ListObjectsV2Command({
          Bucket: env.S3_BUCKET_NAME,
          Prefix: prefix,
          ContinuationToken: continuationToken,
        }),
      );
      for (const item of response.Contents ?? []) {
        if (item.Key) keys.push(item.Key);
      }
      continuationToken = response.IsTruncated
        ? response.NextContinuationToken
        : undefined;
    } while (continuationToken);

    return keys;
  }
  ```
- [ ] Function replaced

**Verification:**
```bash
grep -n "ContinuationToken\|IsTruncated\|do {" \
  ai-podcast-clipper-frontend/src/inngest/functions.ts
# Expect: all three strings present
```
- [ ] grep finds all three

---

## Chunk 4 — Credit Refund on Failure (≈2 hours)

**Why:** The current `catch` block (`functions.ts:131-139`) only sets `status="failed"`. If the Modal job ran, clips were processed, and credits were deducted in the `"deduct-credits"` step — but then `"set-status-processed"` threw — the user loses credits for a failed job. The fix tracks whether deduction happened and refunds in the catch block.

### Task 4.1 — Understand the existing error flow
- `step.fetch` at line 61: calls Modal; if this throws, credits were never deducted → **no refund needed**
- `"deduct-credits"` step at line 96: decrements credits; if this completes but the next step throws → **refund needed**
- Inngest `retries: 1` means the function runs twice max; after both fail, the outer `catch` fires
- With Inngest step memoization: on retry 2, already-completed steps (including `deduct-credits`) are skipped, so no double-deduction risk
- The bug window: both tries fail **after** `deduct-credits` completes but **before** `set-status-processed` completes
- [ ] Flow understood

### Task 4.2 — Add outer tracking variable for credits deducted
- **File:** `ai-podcast-clipper-frontend/src/inngest/functions.ts`
- **Where:** Add `let creditsDeducted = 0;` immediately before the `try {` block (line 22)
- **Update:** After the `"deduct-credits"` step body sets credits (line 103), add:
  `creditsDeducted = Math.min(credits, clipsFound);`
  (This requires `clipsFound` to be in scope — it is, via the destructured `{ clipsFound }` at line 70)
- [ ] Variable declared
- [ ] Variable assigned after deduct step

### Task 4.3 — Add refund logic to catch block
- **File:** `ai-podcast-clipper-frontend/src/inngest/functions.ts:131-139`
- **Current catch block:**
  ```typescript
  } catch (error: unknown) {
    await db.uploadedFile.update({
      where: { id: uploadedFileId },
      data: { status: "failed" },
    });
  }
  ```
- **Replacement:**
  ```typescript
  } catch (error: unknown) {
    await db.uploadedFile.update({
      where: { id: uploadedFileId },
      data: { status: "failed" },
    });

    if (creditsDeducted > 0) {
      await db.user.update({
        where: { id: userId },
        data: { credits: { increment: creditsDeducted } },
      });
    }
  }
  ```
  Note: `userId` is in scope because it's declared at line 23 inside the try block. Move the `const { userId, credits, s3Key }` declaration to **before** the try block so it's accessible in the catch:
  ```typescript
  let userId = "";
  let credits = 0;
  let creditsDeducted = 0;
  // ... inside check-credits step, assign: userId = ...; credits = ...;
  ```
- [ ] `userId` and `credits` moved to outer scope as `let`
- [ ] `creditsDeducted` tracked after deduct step
- [ ] Catch block refunds when `creditsDeducted > 0`

### Task 4.4 — Verify TypeScript compiles
```bash
cd ai-podcast-clipper-frontend && npx tsc --noEmit
# Expect: no errors
```
- [ ] `tsc --noEmit` exits 0

---

## Chunk 5 — Expand Accepted Video Formats (≈1 hour)

**Why:** The dropzone only accepts `video/mp4`. Many podcast recordings are `.mov` (macOS default), `.mkv`, or `.webm`. The backend pipeline only needs a valid video container — ffmpeg handles all of these.

### Task 5.1 — Update dropzone accept types
- **File:** `ai-podcast-clipper-frontend/src/components/dashboard-client.tsx:138`
- **Current:**
  ```tsx
  accept={{ "video/mp4": [".mp4"] }}
  ```
- **Fix:**
  ```tsx
  accept={{
    "video/mp4": [".mp4"],
    "video/quicktime": [".mov"],
    "video/x-matroska": [".mkv"],
    "video/webm": [".webm"],
  }}
  ```
- [ ] Edit made

### Task 5.2 — Update UI hint text
- **File:** `ai-podcast-clipper-frontend/src/components/dashboard-client.tsx:149`
- **Current:** `or click to browse (MP4 up to 500MB)`
- **Fix:** `or click to browse (MP4, MOV, MKV, WebM — up to 500MB)`
- [ ] Edit made

### Task 5.3 — Verify S3 action handles non-mp4 extensions
- **File:** `ai-podcast-clipper-frontend/src/actions/s3.ts:30`
- **Current:** `const fileExtension = fileInfo.filename.split(".").pop() ?? "";`
- **Review:** Extension is derived from filename — this already works for `.mov`, `.mkv`, `.webm`
- **Key format becomes:** `{uuid}/original.mov`, `{uuid}/original.mkv`, etc.
- **Backend concern:** `main.py` downloads to `input.mp4` regardless of format — ffmpeg handles it
- [ ] Confirmed no backend change needed (ffmpeg detects format from content, not extension)

**Verification:**
```bash
grep -n 'accept=' ai-podcast-clipper-frontend/src/components/dashboard-client.tsx
# Expect: 4 MIME types listed
```
- [ ] grep shows all 4 types

---

## Chunk 6 — S3 Lifecycle Policy (≈1 hour)

**Why:** Originals accumulate forever — a 500MB video per user per upload adds up fast. Clips are only needed for 30 days (users download within days). No S3 lifecycle = runaway storage cost.

### Task 6.1 — Create infra directory and lifecycle JSON
- **File:** `infra/s3-lifecycle.json` (new file at repo root)
- **Content:**
  ```json
  {
    "Rules": [
      {
        "ID": "expire-original-uploads",
        "Status": "Enabled",
        "Filter": {
          "Prefix": ""
        },
        "Expiration": {
          "Days": 7
        },
        "NoncurrentVersionExpiration": {
          "NoncurrentDays": 1
        },
        "Filter": {
          "And": {
            "Prefix": "",
            "Tags": []
          },
          "ObjectSizeGreaterThan": 0
        }
      }
    ]
  }
  ```
  **Simpler approach — two rules by suffix pattern:**
  ```json
  {
    "Rules": [
      {
        "ID": "expire-originals-after-7-days",
        "Status": "Enabled",
        "Filter": { "Prefix": "" },
        "Expiration": { "Days": 7 },
        "_comment": "Applies to all objects — tighten with object tagging if needed"
      }
    ]
  }
  ```
  **Recommended approach (tag-based, precise):**
  - Tag original uploads with `type=original` in `s3.ts` PutObject command
  - Tag clip uploads with `type=clip` in `main.py` upload_file call
  - Lifecycle rules filter by tag

- **Recommended rule file:**
  ```json
  {
    "Rules": [
      {
        "ID": "expire-original-uploads-7d",
        "Status": "Enabled",
        "Filter": {
          "Tag": { "Key": "type", "Value": "original" }
        },
        "Expiration": { "Days": 7 }
      },
      {
        "ID": "expire-clips-30d",
        "Status": "Enabled",
        "Filter": {
          "Tag": { "Key": "type", "Value": "clip" }
        },
        "Expiration": { "Days": 30 }
      }
    ]
  }
  ```
- [ ] `infra/s3-lifecycle.json` created with tag-based rules

### Task 6.2 — Tag originals at upload time
- **File:** `ai-podcast-clipper-frontend/src/actions/s3.ts:35-39`
- **Current `PutObjectCommand`:**
  ```typescript
  const command = new PutObjectCommand({
    Bucket: env.S3_BUCKET_NAME,
    Key: key,
    ContentType: fileInfo.contentType,
  });
  ```
- **Fix:**
  ```typescript
  const command = new PutObjectCommand({
    Bucket: env.S3_BUCKET_NAME,
    Key: key,
    ContentType: fileInfo.contentType,
    Tagging: "type=original",
  });
  ```
- [ ] `Tagging` field added

### Task 6.3 — Tag clips at upload time (backend)
- **File:** `ai-podcast-clipper-backend/main.py:304-306`
- **Current:**
  ```python
  s3_client.upload_file(subtitle_output_path, os.environ["S3_BUCKET_NAME"], output_s3_key)
  ```
- **Fix:**
  ```python
  s3_client.upload_file(
      subtitle_output_path,
      os.environ["S3_BUCKET_NAME"],
      output_s3_key,
      ExtraArgs={"Tagging": "type=clip"},
  )
  ```
- [ ] `ExtraArgs` with tagging added

### Task 6.4 — Apply lifecycle policy to AWS bucket
- **Action:** Run AWS CLI command (requires AWS credentials with `s3:PutLifecycleConfiguration` permission):
  ```bash
  aws s3api put-bucket-lifecycle-configuration \
    --bucket <YOUR_BUCKET_NAME> \
    --lifecycle-configuration file://infra/s3-lifecycle.json
  ```
- **Verify:**
  ```bash
  aws s3api get-bucket-lifecycle-configuration --bucket <YOUR_BUCKET_NAME>
  ```
- [ ] Policy applied to bucket
- [ ] Verified with `get-bucket-lifecycle-configuration`

---

## Final Phase 1 Verification Checklist

Run all of these before marking Phase 1 complete:

```bash
# 1. No typos remain
grep -rn "filed\b\|minuntes\|credtis\|occured" ai-podcast-clipper-frontend/src/
# Expect: no output

# 2. No hardcoded [:5] clip ceiling
grep -n "\[:5\]" ai-podcast-clipper-backend/main.py
# Expect: no output

# 3. Pagination is in place
grep -n "IsTruncated\|ContinuationToken" ai-podcast-clipper-frontend/src/inngest/functions.ts
# Expect: both strings found

# 4. All 4 video formats accepted
grep -A5 "accept=" ai-podcast-clipper-frontend/src/components/dashboard-client.tsx | grep -c "video/"
# Expect: 4

# 5. S3 tagging in place
grep -n "Tagging" ai-podcast-clipper-frontend/src/actions/s3.ts ai-podcast-clipper-backend/main.py
# Expect: one hit per file

# 6. TypeScript compiles
cd ai-podcast-clipper-frontend && npx tsc --noEmit
# Expect: exit 0

# 7. Lifecycle file committed
ls infra/s3-lifecycle.json
# Expect: file exists
```

### Summary Scorecard

| # | Task | Est. Time | Status |
|---|------|-----------|--------|
| 1 | Typo fixes (4 files) | 30 min | [ ] |
| 2 | 5-clip ceiling → `MAX_CLIPS` env var | 60 min | [ ] |
| 3 | S3 `ListObjectsV2` pagination | 60 min | [ ] |
| 4 | Credit refund on failure (Inngest catch) | 90 min | [ ] |
| 5 | Expand accepted video formats | 45 min | [ ] |
| 6 | S3 lifecycle policy + object tagging | 60 min | [ ] |
| **Total** | | **~7.5 hours** | |

---

## Exact File → Line Reference Card

| File | Line(s) | Change |
|------|---------|--------|
| `ai-podcast-clipper-backend/main.py` | 401 (new) | `max_clips = int(os.environ.get("MAX_CLIPS", "10"))` |
| `ai-podcast-clipper-backend/main.py` | 432 | `clip_moments[:5]` → `clip_moments[:max_clips]` |
| `ai-podcast-clipper-backend/main.py` | 304–306 | Add `ExtraArgs={"Tagging": "type=clip"}` to `upload_file` |
| `ai-podcast-clipper-frontend/src/inngest/functions.ts` | 22 (before try) | Add `let userId = ""; let credits = 0; let creditsDeducted = 0;` |
| `ai-podcast-clipper-frontend/src/inngest/functions.ts` | 144–160 | Replace with paginated `do/while` loop using `ContinuationToken` |
| `ai-podcast-clipper-frontend/src/inngest/functions.ts` | 131–139 | Add refund logic to catch block |
| `ai-podcast-clipper-frontend/src/components/dashboard-client.tsx` | 84 | `"Upload filed"` → `"Upload failed"` |
| `ai-podcast-clipper-frontend/src/components/dashboard-client.tsx` | 138 | Add MOV, MKV, WebM to `accept` |
| `ai-podcast-clipper-frontend/src/components/dashboard-client.tsx` | 149 | Update hint text to list all formats |
| `ai-podcast-clipper-frontend/src/components/dashboard-client.tsx` | 273 | `"minuntes"` → `"minutes"` |
| `ai-podcast-clipper-frontend/src/app/dashboard/billing/page.tsx` | 130 | `"credtis"` → `"credits"` |
| `ai-podcast-clipper-frontend/src/actions/auth.ts` | 61 | `"occured"` → `"occurred"` |
| `ai-podcast-clipper-frontend/src/actions/s3.ts` | 35–39 | Add `Tagging: "type=original"` to `PutObjectCommand` |
| `infra/s3-lifecycle.json` | new file | Tag-based lifecycle rules (7d originals, 30d clips) |
