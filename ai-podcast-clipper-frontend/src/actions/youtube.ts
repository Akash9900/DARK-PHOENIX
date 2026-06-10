"use server";

import { revalidatePath } from "next/cache";
import { v4 as uuidv4 } from "uuid";
import { inngest } from "~/inngest/client";
import { auth } from "~/server/auth";
import { db } from "~/server/db";

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
      uploaded: true,
    },
    select: { id: true },
  });

  await inngest.send({
    name: "process-video-events",
    data: {
      uploadedFileId: uploadedFile.id,
      userId: session.user.id,
      source: "youtube",
      youtubeUrl,
    },
  });

  revalidatePath("/dashboard");

  return { success: true, uploadedFileId: uploadedFile.id };
}
