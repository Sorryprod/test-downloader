export type JobProgress = {
  job_id: number;
  status: string;
  started_at: string | null;
  started_at_nsk: string | null;
  names_received: number;
  downloaded_in_batch: number;
  total_downloaded: number;
  message: string;
  error: string | null;
};

export type FileItem = {
  id: number;
  filename: string;
  downloaded_at: string;
  job_id: number | null;
};

export type FileListResponse = {
  items: FileItem[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
};

export type CalculateResponse = {
  overall: Record<string, number>;
  per_file: Array<{
    file_id: number;
    filename: string;
    counts: Record<string, number>;
  }>;
  files_processed: number;
};

async function parseError(response: Response): Promise<string> {
  try {
    const data = await response.json();
    if (typeof data.detail === "string") {
      return data.detail;
    }
    return JSON.stringify(data.detail ?? data);
  } catch {
    return response.statusText || "Неизвестная ошибка";
  }
}

export async function startDownloadJob(): Promise<{ job_id: number; status: string }> {
  const response = await fetch("/api/jobs/download", { method: "POST" });
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  return response.json();
}

export async function pauseDownloadJob(jobId: number): Promise<JobProgress> {
  const response = await fetch(`/api/jobs/${jobId}/pause`, { method: "POST" });
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  return response.json();
}

export async function resumeDownloadJob(jobId: number): Promise<JobProgress> {
  const response = await fetch(`/api/jobs/${jobId}/resume`, { method: "POST" });
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  return response.json();
}

export async function getJob(jobId: number): Promise<JobProgress> {
  const response = await fetch(`/api/jobs/${jobId}`);
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  return response.json();
}

export function subscribeJobEvents(
  jobId: number,
  onProgress: (progress: JobProgress) => void,
  onError?: (error: Error) => void,
): () => void {
  const source = new EventSource(`/api/jobs/${jobId}/events`);

  source.addEventListener("progress", (event) => {
    try {
      const data = JSON.parse((event as MessageEvent).data) as JobProgress;
      onProgress(data);
      if (
        data.status === "completed" ||
        data.status === "failed" ||
        data.status === "paused"
      ) {
        source.close();
      }
    } catch (error) {
      onError?.(error instanceof Error ? error : new Error(String(error)));
    }
  });

  source.onerror = () => {
    // Браузер сам переподключается; при терминальном статусе закрываем вручную выше
  };

  return () => source.close();
}

export async function listFiles(page: number, pageSize: number): Promise<FileListResponse> {
  const params = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
  });
  const response = await fetch(`/api/files?${params}`);
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  return response.json();
}

export async function calculateStats(payload: {
  file_ids: number[];
  select_all: boolean;
  select_session?: boolean;
  job_id?: number | null;
}): Promise<CalculateResponse> {
  const response = await fetch("/api/files/calculate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  return response.json();
}
