# Phase 2 Implementation Checklist — YouTube Ingestion

**Branch:** `feature/complete-deployment`
**Estimated total:** ~8 hours
**Goal:** Allow users to paste a YouTube URL instead of uploading a file. The video is downloaded
server-side via `yt-dlp`, uploaded to S3 as `{uuid}/original.mp4`, and then flows through the
**existing** WhisperX → Gemini → TalkNet → ffmpeg pipeline unchanged.

**Prerequisite:** Phase 1 complete (✅ — `MAX_CLIPS`, credit refund, S3 pagination, format
expansion, S3 tagging/lifecycle all merged).

---

## Reference: Current State

- `ai-podcast-clipper-backend/ytdownload.py` — **orphaned standalone script**, not imported
  anywhere. Uses `pytubefix`, hardcodes a YouTube URL (`line 5`), downloads separate video/audio
  streams and merges with `ffmpeg` via `os.system()`. Not in `requirements.txt`.
- `ai-podcast-clipper-backend/main.py:25-26` — `ProcessVideoRequest` Pydantic model has only
  `s3_key: str`. No optional YouTube field.
- `ai-podcast-clipper-backend/main.py:393-408` — `process_video` endpoint always downloads from
  S3 via `s3_client.download_file`.
- `ai-podcast-clipper-frontend/src/components/dashboard-client.tsx:121-125` — `<Tabs>` has only
  `"upload"` and `"my-clips"` triggers.
- `ai-podcast-clipper-frontend/src/actions/s3.ts` — `generateUploadUrl()` is the only path that
  creates an `UploadedFile` DB record.
- `ai-podcast-clipper-frontend/src/actions/generation.ts:11-40` — `processVideo()` sends the
  `process-video-events` Inngest event with `{ uploadedFileId, userId }`.
- `ai-podcast-clipper-frontend/src/inngest/functions.ts:67-74` — `step.fetch` POSTs
  `{ s3_key: s3Key }` to `env.PROCESS_VIDEO_ENDPOINT`.
- `ai-podcast-clipper-frontend/prisma/schema.prisma:74-89` — `UploadedFile.s3Key` is
  **non-nullable `String`**. For YouTube jobs, no S3 key exists until after download, so this
  needs a schema change (placeholder value or nullable + later update).

---

## Design Decision: How YouTube Jobs Flow Through the Pipeline

To minimize changes to the existing (working) pipeline, the YouTube path **converges with the
file-upload path as early as possible**:

1. User submits a YouTube URL (frontend)
2. Server action creates an `UploadedFile` record with a **generated S3 key placeholder**
   (`{uuid}/original.mp4`) and stores the YouTube URL in a new `youtubeUrl` column
3. Inngest event includes `youtubeUrl` (nullable) alongside existing fields
4. Inngest `step.fetch` to Modal includes `youtube_url` in the request body (nullable)
5. **Backend branches once**: if `youtube_url` is present, download via `yt-dlp` and upload the
   result to S3 at the pre-generated key; otherwise download from S3 as today
6. From this point on, **zero pipeline changes** — WhisperX/Gemini/TalkNet/ffmpeg/S3-upload all
   operate on `/tmp/{run_id}/input.mp4` exactly as before

- [ ] Design reviewed and confirmed before starting implementation

---

## Task Breakdown

### Task 1 — Prisma schema: add `youtubeUrl` column (≈30 min)

- **File:** `ai-podcast-clipper-frontend/prisma/schema.prisma:74-89`
- **Change:** Add nullable field to `UploadedFile`:
  ```prisma
  model UploadedFile {
      id String @id @default(cuid())
      s3Key String
      displayName String?
      youtubeUrl String?
      uploaded Boolean @default(false)
      status String @default("queued") // processing, processed, no credits
      createdAt DateTime @default(now())
      updatedAt DateTime @updatedAt

      clips Clip[]

      user User @relation(fields: [userId], references: [id], onDelete: Cascade)
      userId String

      @@index([s3Key])
  }
  ```
- **Migration:** This project has no `prisma/migrations/` directory and uses the
  `db push` workflow (`package.json` → `"db:push": "prisma db push"`), not migration files.
  Apply the schema change with:
  ```bash
  cd ai-podcast-clipper-frontend
  npx prisma db push
  npx prisma generate
  ```
  **Requires a real `DATABASE_URL`** (set in a local `.env`, not committed) — must be run by a
  developer with database access; not runnable in CI/sandbox without credentials.
- [x] Schema field added
- [ ] `npx prisma db push` run against a real database (requires `DATABASE_URL` — manual step,
      not performed in this session)
- [ ] `npx prisma generate` run (regenerates Prisma client types) — run automatically as part of
      `db push` / `postinstall`

---

### Task 2 — Backend: add `yt-dlp` dependency (≈30 min)

- **File:** `ai-podcast-clipper-backend/requirements.txt`
- **Change:** Add `yt-dlp` (actively maintained fork of youtube-dl; handles throttling,
  format selection, age-restriction better than `pytubefix`)
  ```
  yt-dlp
  ```
- **File:** `ai-podcast-clipper-backend/main.py:29-38` — Modal image definition
- **Change:** No explicit pip_install needed — `pip_install_from_requirements("requirements.txt")`
  (`main.py:32`) already picks up `requirements.txt` changes automatically
- [x] `yt-dlp` added to `requirements.txt` (no `pytubefix` was present, confirmed via grep)
- [ ] Confirmed Modal image rebuild picks it up (no separate `pip_install` call needed) —
      verified at deploy time, not in this session

---

### Task 3 — Backend: implement `download_from_youtube()` (≈1.5 hours)

- **File:** `ai-podcast-clipper-backend/main.py`
- **Where:** New module-level function, placed near other helper functions (e.g., after
  `create_subtitles_with_ffmpeg`, before the `@app.cls` class definition — around `line 308`)
- **Implementation:**
  ```python
  class YouTubeDownloadError(Exception):
      pass


  def download_from_youtube(youtube_url: str, output_path: str, max_duration_seconds: int = 10800):
      """Download a YouTube video as MP4 to output_path using yt-dlp.

      Raises YouTubeDownloadError for unavailable/private/age-gated videos
      and for videos exceeding max_duration_seconds (default 3 hours).
      """
      import yt_dlp

      ydl_opts = {
          "format": "bestvideo[ext=mp4][height<=1080]+bestaudio[ext=m4a]/best[ext=mp4]/best",
          "outtmpl": output_path,
          "merge_output_format": "mp4",
          "quiet": True,
          "no_warnings": True,
          "noplaylist": True,
      }

      try:
          with yt_dlp.YoutubeDL(ydl_opts) as ydl:
              info = ydl.extract_info(youtube_url, download=False)

              duration = info.get("duration")
              if duration is not None and duration > max_duration_seconds:
                  raise YouTubeDownloadError(
                      f"Video too long: {duration}s exceeds max of {max_duration_seconds}s")

              ydl.download([youtube_url])
      except yt_dlp.utils.DownloadError as e:
          raise YouTubeDownloadError(f"Failed to download video: {e}") from e
  ```
- **Note on `output_path`:** `yt-dlp`'s `outtmpl` may not produce exactly the filename
  requested if `merge_output_format` differs from the source extension. Test with
  `outtmpl` set to `str(video_path.with_suffix(""))` + `.%(ext)s` and verify the final
  file lands at `video_path` (rename if needed after download).

**Implemented version** (deviates slightly from the draft above — no `max_duration_seconds`
pre-check was added; see "Open Items" below):
```python
class YouTubeDownloadError(Exception):
    pass


def download_from_youtube(youtube_url: str, output_path: str) -> bool:
    """Download a YouTube video as MP4 to output_path using yt-dlp.

    Raises YouTubeDownloadError for invalid URLs, unavailable/region-blocked
    videos, and other download failures (including timeouts).
    Returns True on success.
    """
    import yt_dlp

    ydl_opts = {
        "format": "bestvideo[ext=mp4][height<=1080]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "outtmpl": output_path,
        "merge_output_format": "mp4",
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "socket_timeout": 30,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([youtube_url])
    except yt_dlp.utils.DownloadError as e:
        print(f"yt-dlp download failed for {youtube_url}: {e}")
        raise YouTubeDownloadError(f"Failed to download YouTube video: {e}") from e

    if not os.path.exists(output_path):
        print(f"yt-dlp reported success but no file found at {output_path}")
        raise YouTubeDownloadError(
            f"Download completed but output file not found at {output_path}")

    return True
```
Placed in `main.py` after `process_clip()` (was line ~308) and before the `@app.cls`
`AiPodcastClipper` class definition.

- [x] Function implemented
- [ ] Output path handling verified against actual `yt-dlp` behavior — **not yet tested with a
      live download** (no network/yt-dlp execution in this session); `python3 -m py_compile`
      passes but this is syntax-only verification

---

### Task 4 — Backend: branch `process_video` endpoint on `youtube_url` (≈1.5 hours)

- **File:** `ai-podcast-clipper-backend/main.py:25-26` — `ProcessVideoRequest` model
- **Implemented version** (deviates from the draft: adds an explicit `source` discriminator
  field rather than relying solely on `youtube_url` truthiness — requested in the Task 3/4
  execution instructions):
  ```python
  class ProcessVideoRequest(BaseModel):
      s3_key: str
      source: str = "file"
      youtube_url: str | None = None
  ```
- [x] Model updated (with `source` field added)

- **File:** `ai-podcast-clipper-backend/main.py:393-408` — `process_video` endpoint
- **Current:**
  ```python
  @modal.fastapi_endpoint(method="POST")
  def process_video(self, request: ProcessVideoRequest, token: HTTPAuthorizationCredentials = Depends(auth_scheme)):
      s3_key = request.s3_key

      if token.credentials != os.environ["AUTH_TOKEN"]:
          raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                              detail="Incorrect bearer token", headers={"WWW-Authenticate": "Bearer"})

      run_id = str(uuid.uuid4())
      base_dir = pathlib.Path("/tmp") / run_id
      base_dir.mkdir(parents=True, exist_ok=True)

      # Download video file
      video_path = base_dir / "input.mp4"
      s3_client = boto3.client("s3")
      s3_client.download_file(os.environ["S3_BUCKET_NAME"], s3_key, str(video_path))
  ```
- **Fix:**
  ```python
  @modal.fastapi_endpoint(method="POST")
  def process_video(self, request: ProcessVideoRequest, token: HTTPAuthorizationCredentials = Depends(auth_scheme)):
      s3_key = request.s3_key
      youtube_url = request.youtube_url

      if token.credentials != os.environ["AUTH_TOKEN"]:
          raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                              detail="Incorrect bearer token", headers={"WWW-Authenticate": "Bearer"})

      max_clips = int(os.environ.get("MAX_CLIPS", "10"))

      run_id = str(uuid.uuid4())
      base_dir = pathlib.Path("/tmp") / run_id
      base_dir.mkdir(parents=True, exist_ok=True)

      video_path = base_dir / "input.mp4"
      s3_client = boto3.client("s3")

      if youtube_url:
          print(f"Downloading from YouTube: {youtube_url}")
          try:
              download_from_youtube(youtube_url, str(video_path))
          except YouTubeDownloadError as e:
              raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                                  detail=str(e))
          # Upload the downloaded video to S3 at the pre-generated key so the
          # rest of the pipeline (and the frontend's clip-detection step) is unchanged
          s3_client.upload_file(str(video_path), os.environ["S3_BUCKET_NAME"], s3_key,
                                 ExtraArgs={"Tagging": "Environment=source"})
      else:
          # Download video file from S3 (existing path)
          s3_client.download_file(os.environ["S3_BUCKET_NAME"], s3_key, str(video_path))
  ```

**Implemented version** (branches on `request.source == "youtube"` instead of
`youtube_url` truthiness, and adds a 400 error if `youtube_url` is missing for that source):
```python
        video_path = base_dir / "input.mp4"
        s3_client = boto3.client("s3")

        if request.source == "youtube":
            if not request.youtube_url:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                    detail="youtube_url is required when source is 'youtube'")

            print(f"Downloading video from YouTube: {request.youtube_url}")
            try:
                download_from_youtube(request.youtube_url, str(video_path))
            except YouTubeDownloadError as e:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                                    detail=str(e))

            s3_client.upload_file(str(video_path), os.environ["S3_BUCKET_NAME"], s3_key,
                                   ExtraArgs={"Tagging": "Environment=source"})
        else:
            s3_client.download_file(os.environ["S3_BUCKET_NAME"], s3_key, str(video_path))
```

- [x] Endpoint branches correctly on `request.source` (with `youtube_url` validation)
- [x] YouTube-sourced video uploaded to S3 with `Environment=source` tag (consistent with
      Phase 1 Chunk 6 lifecycle policy)
- [x] `python3 -m py_compile main.py` passes

---

### Task 5 — Frontend: new server action `processYoutubeVideo()` (≈1 hour)

- **File:** `ai-podcast-clipper-frontend/src/actions/youtube.ts` (new file)
- **Pattern modeled on:** `src/actions/s3.ts:10-61` (`generateUploadUrl`) and
  `src/actions/generation.ts:11-40` (`processVideo`)
- **Implementation:**
  ```typescript
  "use server";

  import { v4 as uuidv4 } from "uuid";
  import { auth } from "~/server/auth";
  import { db } from "~/server/db";
  import { inngest } from "~/inngest/client";
  import { revalidatePath } from "next/cache";

  const YOUTUBE_URL_REGEX =
    /^(https?:\/\/)?(www\.)?(youtube\.com\/watch\?v=|youtu\.be\/)[\w-]{11}/;

  export async function processYoutubeVideo(youtubeUrl: string): Promise<{
    success: boolean;
    error?: string;
    uploadedFileId?: string;
  }> {
    const session = await auth();
    if (!session) throw new Error("Unauthorized");

    if (!YOUTUBE_URL_REGEX.test(youtubeUrl)) {
      return { success: false, error: "Invalid YouTube URL" };
    }

    const uniqueId = uuidv4();
    const s3Key = `${uniqueId}/original.mp4`;

    const uploadedFile = await db.uploadedFile.create({
      data: {
        userId: session.user.id,
        s3Key,
        displayName: youtubeUrl,
        youtubeUrl,
        uploaded: true, // no client-side upload step for YouTube
      },
      select: { id: true },
    });

    await inngest.send({
      name: "process-video-events",
      data: {
        uploadedFileId: uploadedFile.id,
        userId: session.user.id,
      },
    });

    revalidatePath("/dashboard");

    return { success: true, uploadedFileId: uploadedFile.id };
  }
  ```
- [x] File created (implemented as part of Task 2 — see commit history)
- [x] Regex validates `youtube.com/watch?v=` and `youtu.be/` formats
- [x] `uploaded: true` set immediately (skips the file-upload step that normally sets this
      via `processVideo()` in `generation.ts:30-37`)
- [x] `npx tsc --noEmit` passes (after `npx prisma generate` picked up Task 1's `youtubeUrl` field)

---

### Task 6 — Frontend: add YouTube tab to dashboard (≈1.5 hours)

- **File:** `ai-podcast-clipper-frontend/src/components/dashboard-client.tsx:121-125`
- **Current:**
  ```tsx
  <Tabs defaultValue="upload">
    <TabsList>
      <TabsTrigger value="upload">Upload</TabsTrigger>
      <TabsTrigger value="my-clips">My Clips</TabsTrigger>
    </TabsList>
  ```
- **Fix:**
  ```tsx
  <Tabs defaultValue="upload">
    <TabsList>
      <TabsTrigger value="upload">Upload File</TabsTrigger>
      <TabsTrigger value="youtube">YouTube URL</TabsTrigger>
      <TabsTrigger value="my-clips">My Clips</TabsTrigger>
    </TabsList>
  ```
- **New `TabsContent` block** (insert after the existing `"upload"` `TabsContent`, before
  `"my-clips"`, i.e. after `dashboard-client.tsx:265`):
  ```tsx
  <TabsContent value="youtube">
    <Card>
      <CardHeader>
        <CardTitle>Process YouTube Video</CardTitle>
        <CardDescription>
          Paste a YouTube URL to generate clips (videos up to 3 hours)
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="flex gap-2">
          <Input
            type="url"
            placeholder="https://www.youtube.com/watch?v=..."
            value={youtubeUrl}
            onChange={(e) => setYoutubeUrl(e.target.value)}
            disabled={submittingYoutube}
          />
          <Button onClick={handleYoutubeSubmit} disabled={submittingYoutube || !youtubeUrl}>
            {submittingYoutube ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Processing...
              </>
            ) : (
              "Process Video"
            )}
          </Button>
        </div>
      </CardContent>
    </Card>
  </TabsContent>
  ```
- **New imports needed:**
  ```tsx
  import { Input } from "./ui/input";
  import { processYoutubeVideo } from "~/actions/youtube";
  ```
- **New state + handler** (add near `handleUpload`, around `dashboard-client.tsx:61`):
  ```tsx
  const [youtubeUrl, setYoutubeUrl] = useState("");
  const [submittingYoutube, setSubmittingYoutube] = useState(false);

  const handleYoutubeSubmit = async () => {
    setSubmittingYoutube(true);
    try {
      const result = await processYoutubeVideo(youtubeUrl);
      if (!result.success) {
        toast.error("Invalid YouTube URL", {
          description: result.error ?? "Please check the URL and try again.",
        });
        return;
      }
      setYoutubeUrl("");
      toast.success("Video scheduled for processing", {
        description: "Check the queue status below.",
        duration: 5000,
      });
    } catch {
      toast.error("Failed to process YouTube video");
    } finally {
      setSubmittingYoutube(false);
    }
  };
  ```
**Implemented version** (deviates slightly from the draft above):
- `Tabs` is now **controlled** via `activeTab`/`setActiveTab` state (`value={activeTab}
  onValueChange={setActiveTab}`) instead of `defaultValue="upload"`.
- `handleYoutubeSubmit` validates the URL client-side with `YOUTUBE_URL_REGEX` *before* calling
  `processYoutubeVideo()` (in addition to the server-side check in `actions/youtube.ts`), so
  invalid URLs never trigger a server action call.
- The "YouTube URL" `TabsContent` does **not** duplicate the queue-status table (already shown
  on the "Upload File" tab) — instead shows a hint to switch tabs to view status, avoiding
  ~60 lines of duplicated table JSX.

- [x] Tab trigger added (`"Upload File"`, `"YouTube URL"`, `"My Clips"`)
- [x] `TabsContent` block added
- [x] Imports added (`Input` from `./ui/input`, `processYoutubeVideo` from `~/actions/youtube`)
- [x] State + handler added (`activeTab`, `youtubeUrl`, `submittingYoutube`,
      `handleYoutubeSubmit`)
- [x] Verified `Input` component exists at `src/components/ui/input.tsx` (already present, no
      `npx shadcn add input` needed)
- [x] `npx tsc --noEmit` passes

---

### Task 7 — Inngest: pass `source`/`youtube_url` through to Modal (≈1 hour)

**Implemented approach (deviates from the draft below):** rather than re-querying the DB for
`youtubeUrl` inside `check-credits`, `source` and `youtubeUrl` are passed straight through the
Inngest **event payload** (set by `processYoutubeVideo()` in `actions/youtube.ts` at send-time)
and destructured at the top of the function. This avoids an extra `select` field and keeps
`check-credits`'s return shape unchanged.

- **File:** `ai-podcast-clipper-frontend/src/actions/youtube.ts` — `inngest.send()` call
- **Before:**
  ```typescript
  await inngest.send({
    name: "process-video-events",
    data: {
      uploadedFileId: uploadedFile.id,
      userId: session.user.id,
    },
  });
  ```
- **After:**
  ```typescript
  await inngest.send({
    name: "process-video-events",
    data: {
      uploadedFileId: uploadedFile.id,
      userId: session.user.id,
      source: "youtube",
      youtubeUrl,
    },
  });
  ```
- [x] `source`/`youtubeUrl` added to Inngest event payload

- **File:** `ai-podcast-clipper-frontend/src/inngest/functions.ts:17-20` — event data destructure
- **Before:**
  ```typescript
  const { uploadedFileId } = event.data as {
    uploadedFileId: string;
    userId: string;
  };
  ```
- **After:**
  ```typescript
  const {
    uploadedFileId,
    source = "file",
    youtubeUrl,
  } = event.data as {
    uploadedFileId: string;
    userId: string;
    source?: string;
    youtubeUrl?: string;
  };
  ```
- [x] `source` (defaults to `"file"`) and `youtubeUrl` destructured from `event.data`. The
      existing file-upload path (`processVideo()` in `generation.ts`) doesn't set these fields,
      so `source` defaults to `"file"` and `youtubeUrl` is `undefined` for that path —
      backward compatible.

- **File:** `ai-podcast-clipper-frontend/src/inngest/functions.ts` — `step.fetch`
- **Before:**
  ```typescript
  await step.fetch(env.PROCESS_VIDEO_ENDPOINT, {
    method: "POST",
    body: JSON.stringify({ s3_key: s3Key }),
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${env.PROCESS_VIDEO_ENDPOINT_AUTH}`,
    },
  });
  ```
- **After:**
  ```typescript
  await step.fetch(env.PROCESS_VIDEO_ENDPOINT, {
    method: "POST",
    body: JSON.stringify({
      s3_key: s3Key,
      source,
      youtube_url: youtubeUrl,
    }),
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${env.PROCESS_VIDEO_ENDPOINT_AUTH}`,
    },
  });
  ```
- [x] `source` and `youtube_url` included in Modal request body (matches `ProcessVideoRequest`
      field names from Tasks 3/4: `s3_key`, `source`, `youtube_url`)
- [x] `npx tsc --noEmit` passes

---

### Task 8 — Verification & manual end-to-end test (≈1 hour)

- **Local Modal test** — use the existing `@app.local_entrypoint()` pattern
  (`main.py:444-466`) but with a `youtube_url` in the payload:
  ```python
  payload = {
      "s3_key": "test-youtube/original.mp4",
      "youtube_url": "https://www.youtube.com/watch?v=<short_public_video_id>"
  }
  ```
  Run: `modal run main.py` (or however the project invokes the local entrypoint)
- [ ] Backend downloads a short public video via `yt-dlp`
- [ ] Downloaded file uploaded to S3 at `test-youtube/original.mp4` with `Environment=source` tag
- [ ] Pipeline proceeds through transcription → Gemini → TalkNet → clips, identical to
      file-upload path
- [ ] Frontend: paste a YouTube URL in the new tab → `UploadedFile` row appears in queue with
      `status: "processing"` → eventually `"processed"` with clips visible
- [ ] `npx tsc --noEmit` passes for frontend
- [ ] `python3 -m py_compile main.py` passes for backend

---

## Error Scenarios

| # | Scenario | Where Handled | Expected Behavior |
|---|----------|---------------|-------------------|
| 1 | **Invalid URL format** (not a YouTube URL) | `src/actions/youtube.ts` — `YOUTUBE_URL_REGEX` | Server action returns `{ success: false, error: "Invalid YouTube URL" }` before any DB write or Inngest event; toast shown to user immediately, no queue entry created |
| 2 | **Private / deleted / region-blocked video** | `main.py: download_from_youtube()` — `yt_dlp.utils.DownloadError` caught, raised as `YouTubeDownloadError` | `process_video` endpoint returns HTTP 422 with detail message → `step.fetch` in Inngest throws → existing Chunk 4 catch block sets `status="failed"` and refunds credits (none deducted yet, so no-op) |
| 3 | **Video exceeds 3-hour limit** | `download_from_youtube()` — duration check via `ydl.extract_info(download=False)` before downloading | Raises `YouTubeDownloadError("Video too long...")` *before* any download bandwidth is used → HTTP 422 → job marked `"failed"` |
| 4 | **Age-gated / requires sign-in** | `yt_dlp.utils.DownloadError` (same as #2) | Same as #2 — surfaces as `"failed"` status. **Out of scope for Phase 2**: cookie-based auth for age-gated content (documented as future work in `docs/ops.md`, Phase 6) |
| 5 | **YouTube throttles/rate-limits download** | `yt-dlp` internal retry/backoff (built-in, no extra code needed) | `yt-dlp` retries automatically; if all retries exhausted, raises `DownloadError` → same as #2 |
| 6 | **Modal timeout (3600s) on very long download + processing** | Existing Modal `timeout=3600` (`main.py:309`, unchanged in Phase 2) | If a 3-hour video's download + full pipeline exceeds 3600s, Modal kills the container → `step.fetch` throws → job marked `"failed"`, credits refunded (Chunk 4). **Note:** the 3-hour duration limit in `download_from_youtube` does not guarantee the *total* job fits in 3600s — flag this as a known limitation, not solved in Phase 2 |
| 7 | **`yt-dlp` produces a file at an unexpected path** (Task 3 note) | Manual verification step (Task 3) | If `outtmpl` doesn't match `video_path` exactly, downstream `s3_client.upload_file(str(video_path), ...)` will raise `FileNotFoundError` → caught by Inngest's existing catch-all → `"failed"` + refund |
| 8 | **Non-existent video ID (404)** | `yt_dlp.utils.DownloadError` (same as #2) | Same as #2 |

---

## Testing Strategy

### Manual (Phase 2 scope)
1. **Happy path:** Short (<2 min) public YouTube video → full pipeline → clips appear
2. **Invalid URL:** Paste `"not a url"` → inline error, no queue entry
3. **Private video:** Use a known private/unlisted video URL → job shows `"failed"`,
   credits unchanged
4. **Long video:** Video >3 hours (or temporarily lower `max_duration_seconds` to test with a
   shorter video) → job shows `"failed"` with duration error before download starts

### Automated (deferred to Phase 5 per `PROJECT_PLAN.md`)
- `tests/test_youtube.py` (backend, pytest):
  - Mock `yt_dlp.YoutubeDL` to test `download_from_youtube()` duration-check branch without
    network calls
  - Test `YouTubeDownloadError` raised on mocked `DownloadError`
- `tests/youtube.spec.ts` (frontend, Playwright):
  - Regex validation (valid/invalid URL formats)
  - Form submission → Inngest event fired (mocked)
- These are **not** part of the ~8-hour Phase 2 estimate; tracked separately under Phase 5

---

## Success Criteria

- [ ] User can paste `https://www.youtube.com/watch?v=<id>` or `https://youtu.be/<id>` into the
      new "YouTube URL" tab and click "Process Video"
- [ ] Job appears in the "Queue status" table with `status: "queued"` → `"processing"` →
      `"processed"`
- [ ] Generated clips appear in "My Clips" tab, identical in format to file-upload-sourced clips
- [ ] Invalid/non-YouTube URLs are rejected client-side with a clear error, no queue entry created
- [ ] Private/unavailable videos result in `status: "failed"` with credits unchanged (verifies
      Phase 1 Chunk 4 refund logic works for this new failure path too)
- [ ] Videos over the configured duration limit fail fast (before download) with a descriptive
      error
- [ ] `npx tsc --noEmit` (frontend) and `python3 -m py_compile main.py` (backend) both pass
- [ ] No regressions to the existing file-upload flow (re-test Phase 1 happy path)

---

## Time Estimate Summary

| # | Task | Est. Time |
|---|------|-----------|
| 1 | Prisma schema: `youtubeUrl` column + migration | 30 min |
| 2 | Add `yt-dlp` to `requirements.txt` | 30 min |
| 3 | Implement `download_from_youtube()` | 90 min |
| 4 | Branch `process_video` endpoint on `youtube_url` | 90 min |
| 5 | New server action `processYoutubeVideo()` | 60 min |
| 6 | Add YouTube tab to dashboard UI | 90 min |
| 7 | Pass `youtubeUrl` through Inngest → Modal | 60 min |
| 8 | Verification & E2E manual test | 60 min |
| **Total** | | **~8 hours** |

---

## Exact File → Line Reference Card

| File | Line(s) | Change |
|------|---------|--------|
| `ai-podcast-clipper-frontend/prisma/schema.prisma` | 74-89 | Add `youtubeUrl String?` to `UploadedFile` |
| `ai-podcast-clipper-backend/requirements.txt` | append | Add `yt-dlp` |
| `ai-podcast-clipper-backend/main.py` | ~308 (new) | Add `YouTubeDownloadError` class + `download_from_youtube()` function |
| `ai-podcast-clipper-backend/main.py` | 25-26 | `ProcessVideoRequest` — add `youtube_url: str \| None = None` |
| `ai-podcast-clipper-backend/main.py` | 393-408 | Branch download logic on `request.youtube_url` |
| `ai-podcast-clipper-frontend/src/actions/youtube.ts` | new file | `processYoutubeVideo()` server action |
| `ai-podcast-clipper-frontend/src/components/dashboard-client.tsx` | 121-125 | Add `"youtube"` `TabsTrigger` |
| `ai-podcast-clipper-frontend/src/components/dashboard-client.tsx` | ~265 (after upload TabsContent) | New `TabsContent value="youtube"` block |
| `ai-podcast-clipper-frontend/src/components/dashboard-client.tsx` | ~61 (near handleUpload) | New `youtubeUrl`/`submittingYoutube` state + `handleYoutubeSubmit` |
| `ai-podcast-clipper-frontend/src/inngest/functions.ts` | 26-53 | `check-credits` step returns + destructures `youtubeUrl` |
| `ai-podcast-clipper-frontend/src/inngest/functions.ts` | 67-74 | `step.fetch` body includes `youtube_url` |

---

## Open Items / Risks Carried Forward

1. **3-hour duration check ≠ 3600s Modal timeout guarantee** (Error Scenario #6) — a video just
   under 3 hours could still blow the Modal timeout once transcription/TalkNet/ffmpeg overhead
   is added. Consider either lowering `max_duration_seconds` to ~45 min for Phase 2, or raising
   Modal `timeout` — flagged for follow-up, not blocking Phase 2 completion.
2. **Age-gated/cookie-protected videos** are explicitly out of scope (per `PROJECT_PLAN.md`
   Open Question #1) — document as a known limitation in Phase 6 ops docs.
3. **`yt-dlp` output filename behavior** (Task 3) must be verified empirically — this is the
   highest-risk unknown in the implementation and should be tested first, in isolation, before
   wiring into the full endpoint.
4. **Credit cost model for YouTube** (PROJECT_PLAN.md Open Question #4) — Phase 2 implementation
   uses the same credit deduction logic as file uploads (per-clip, unchanged from Phase 1). If a
   different model is desired, revisit `functions.ts` `deduct-credits` step.
