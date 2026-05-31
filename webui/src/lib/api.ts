import { z } from "zod"

// ─── Zod Schemas ───────────────────────────────────────────────────────────────

export const JobCreateSchema = z.object({
  repo_url: z
    .string()
    .url()
    .optional()
    .default("https://github.com/Quozul/PicoLimbo.git"),
  ref: z.string().min(1).optional().default("master"),
  versions: z.array(z.string()).nullable().optional(),
  proxy: z.string().optional().default("none"),
  forwarding_method: z.string().optional().default("modern"),
  plugins: z.array(z.string()).optional(),
  login_wait_timeout: z.number().int().positive().optional().default(30),
})

export const TestResultSchema = z.object({
  version: z.string(),
  passed: z.boolean(),
  screenshot_path: z.string().nullable().optional(),
  duration_seconds: z.number().nullable().optional(),
  error: z.string().nullable().optional(),
})

export const JobInfoSchema = z.object({
  job_id: z.string(),
  status: z.enum(["queued", "building", "testing", "finished", "failed", "cancelled"]),
  repo_url: z.string(),
  ref: z.string(),
  owner: z.string(),
  commit_hash: z.string(),
  current_step: z.string().nullable().optional(),
  versions: z.array(z.string()),
  test_results: z.record(z.string(), TestResultSchema),
  artifact_path: z.string().nullable().optional(),
  error_message: z.string().nullable().optional(),
  eta_seconds: z.number().nullable().optional(),
  created_at: z.string(),
  updated_at: z.string(),
  plugins: z.array(z.string()).optional(),
  login_wait_timeout: z.number().int().positive().optional().default(30),
})

export const ScreenshotItemSchema = z.object({
  screenshot_id: z.string(),
  version: z.string(),
  path: z.string(),
  passed: z.boolean(),
})

export type JobCreateInput = z.infer<typeof JobCreateSchema>

export const ProxyOptions = [
  { value: "none", label: "None" },
  { value: "velocity", label: "Velocity" },
] as const
export type JobInfo = z.infer<typeof JobInfoSchema>
export type TestResult = z.infer<typeof TestResultSchema>
export type ScreenshotItem = z.infer<typeof ScreenshotItemSchema>

// ─── API Client ────────────────────────────────────────────────────────────────

const API_BASE = import.meta.env.VITE_API_URL || ""

async function request<T>(
  _method: string,
  path: string,
  options?: RequestInit
): Promise<T> {
  const url = `${API_BASE}${path}`
  const response = await fetch(url, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options?.headers,
    },
  })

  if (!response.ok) {
    const errorBody = await response.json().catch(() => ({}))
    throw new Error(errorBody.detail || `API error: ${response.status}`)
  }

  const data = await response.json()
  return data
}

// ─── Endpoints ─────────────────────────────────────────────────────────────────

/**
 * POST /jobs
 * Create a new build and test job.
 */
export async function createJob(input: JobCreateInput): Promise<JobInfo> {
  const parsed = JobCreateSchema.parse(input)
  const data = await request<JobInfo>("POST", "/jobs", {
    method: "POST",
    body: JSON.stringify(parsed),
  })
  return JobInfoSchema.parse(data)
}

/**
 * GET /jobs/{job_id}
 * Get job information with polling support.
 */
export async function getJob(jobId: string): Promise<JobInfo> {
  const data = await request<JobInfo>(`GET`, `/jobs/${jobId}`)
  return JobInfoSchema.parse(data)
}

/**
 * GET /jobs
 * List all jobs, optionally filtered by status.
 */
export async function listJobs(options?: {
  status?: string
  limit?: number
}): Promise<JobInfo[]> {
  const params = new URLSearchParams()
  if (options?.status) params.set("status", options.status)
  if (options?.limit) params.set("limit", String(options.limit))
  const query = params.toString() ? `?${params}` : ""
  const data = await request<JobInfo[]>(`GET`, `/jobs${query}`)
  return data.map((j) => JobInfoSchema.parse(j))
}

/**
 * GET /jobs/{job_id}/screenshots
 * List all screenshots for a job.
 */
export async function listScreenshots(
  jobId: string
): Promise<ScreenshotItem[]> {
  const data = await request<ScreenshotItem[]>(
    `GET`,
    `/jobs/${jobId}/screenshots`
  )
  return data.map((s) => ScreenshotItemSchema.parse(s))
}

/**
 * GET /jobs/{job_id}/screenshots/{screenshot_id}
 * Download a specific screenshot by version.
 */
export function getScreenshotUrl(jobId: string, screenshotId: string): string {
  return `${API_BASE}/jobs/${jobId}/screenshots/${screenshotId}`
}

/**
 * POST /jobs/{job_id}/retry
 * Retry a failed or finished build.
 */
export async function retryJob(jobId: string): Promise<JobInfo> {
  const data = await request<JobInfo>(`POST`, `/jobs/${jobId}/retry`, {
    method: "POST",
  })
  return JobInfoSchema.parse(data)
}

export async function cancelJob(jobId: string): Promise<JobInfo> {
  const data = await request<JobInfo>(`POST`, `/jobs/${jobId}/cancel`, {
    method: "POST",
  })
  return JobInfoSchema.parse(data)
}

/**
 * POST /plugins/upload
 * Upload a Velocity plugin .jar file.
 */
export async function uploadPlugin(
  file: File
): Promise<{ name: string; status: string }> {
  const formData = new FormData()
  formData.append("plugin", file)
  const url = `${API_BASE}/plugins/upload`
  const response = await fetch(url, {
    method: "POST",
    body: formData,
  })

  if (!response.ok) {
    const errorBody = await response.json().catch(() => ({}))
    throw new Error(errorBody.detail || `Upload error: ${response.status}`)
  }

  return response.json()
}

/**
 * GET /plugins
 * List all uploaded plugins.
 */
export async function listPlugins(): Promise<
  { name: string; status: string }[]
> {
  const data = await request<{ name: string; status: string }[]>(
    "GET",
    "/plugins"
  )
  return data
}

/**
 * DELETE /plugins/{name}
 * Delete an uploaded plugin.
 */
export async function deletePlugin(
  name: string
): Promise<{ deleted: boolean }> {
  const data = await request<{ deleted: boolean }>(`DELETE`, `/plugins/${name}`)
  return data
}

/**
 * GET /health
 * Health check.
 */
export async function healthCheck(): Promise<{ status: string }> {
  return request<{ status: string }>("GET", "/health")
}

// ─── Polling Utilities ─────────────────────────────────────────────────────────

export type JobStatusListener = (job: JobInfo) => void

export function createJobPoller(
  jobId: string,
  onStatusChange: JobStatusListener,
  options?: {
    intervalMs?: number
    onComplete?: (job: JobInfo) => void
  }
): { stop: () => void } {
  const { intervalMs = 2000, onComplete } = options ?? {}
  let running = true

  const poll = async () => {
    while (running) {
      try {
        const job = await getJob(jobId)
        onStatusChange(job)
        if (["finished", "failed", "cancelled"].includes(job.status)) {
          onComplete?.(job)
          running = false
          return
        }
      } catch {
        // Silently ignore poll errors (e.g., network issues)
      }
      await new Promise((resolve) => setTimeout(resolve, intervalMs))
    }
  }

  poll()

  return {
    stop: () => {
      running = false
    },
  }
}
