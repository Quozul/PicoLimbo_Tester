import { useState, useEffect, useCallback, useRef } from "react"
import {
  createJobPoller,
  retryJob,
  cancelJob,
  listScreenshots,
  getScreenshotUrl,
  type JobInfo,
  type TestResult,
} from "@/lib/api"
import { Button } from "@/components/ui/button"
import { ALL_VERSIONS } from "@/lib/versions"
import {
  CheckCircle2,
  Circle,
  Loader2,
  XCircle,
  Clock,
  RotateCcw,
  Square,
  AlertTriangle,
  Download,
  ExternalLink,
} from "lucide-react"
import { cn } from "@/lib/utils"

interface JobProgressProps {
  job: JobInfo
}

function getTestResultForVersion(
  job: JobInfo,
  versionLabel: string
): TestResult | undefined {
  return job.test_results[versionLabel] as TestResult | undefined
}

function getOverallProgress(job: JobInfo): number {
  if (job.status === "finished") return 100
  if (job.status === "failed") {
    const tested = Object.keys(job.test_results).length
    const total = job.versions.length
    return total > 0 ? Math.round((tested / total) * 100) : 0
  }
  if (job.versions.length === 0) return 0

  const tested = Object.keys(job.test_results).length
  return Math.round((tested / job.versions.length) * 100)
}

function getStatusIcon(status: string) {
  switch (status) {
    case "queued":
      return <Clock className="size-4 text-muted-foreground" />
    case "building":
      return <Loader2 className="size-4 animate-spin text-primary" />
    case "testing":
      return <Loader2 className="size-4 animate-spin text-amber-500" />
    case "finished":
      return <CheckCircle2 className="size-4 text-green-500" />
    case "failed":
      return <AlertTriangle className="size-4 text-destructive" />
    default:
      return <Circle className="size-4 text-muted-foreground" />
  }
}

function getStatusColor(status: string): string {
  switch (status) {
    case "queued":
      return "text-muted-foreground"
    case "building":
      return "text-primary"
    case "testing":
      return "text-amber-500"
    case "finished":
      return "text-green-500"
    case "failed":
      return "text-destructive"
    default:
      return "text-muted-foreground"
  }
}

function formatDuration(seconds?: number | null): string {
  if (seconds == null) return "-"
  const m = Math.floor(seconds / 60)
  const s = Math.floor(seconds % 60)
  return `${m}m ${s}s`
}

function formatEta(seconds?: number | null): string {
  if (seconds == null) return "-"
  if (seconds < 60) return `${seconds}s`
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  return `${m}m ${s}s`
}

export function JobProgress({ job }: JobProgressProps) {
  const [currentJob, setCurrentJob] = useState<JobInfo>(job)
  const [screenshotUrls, setScreenshotUrls] = useState<Map<string, string>>(
    new Map()
  )
  const [loading, setLoading] = useState(false)

  const pollerRef = useRef<ReturnType<typeof createJobPoller> | null>(null)

  // Sync internal state when the job prop changes
  useEffect(() => {
    setCurrentJob(job)
  }, [job])

  // Poll for updates
  useEffect(() => {
    pollerRef.current = createJobPoller(
      currentJob.job_id,
      (updated) => {
        setCurrentJob(updated)
        // Fetch screenshots when new test results appear
        listScreenshots(updated.job_id)
          .then((screenshotItems) => {
            const urlMap = new Map<string, string>()
            screenshotItems.forEach((s) => {
              urlMap.set(
                s.screenshot_id,
                getScreenshotUrl(updated.job_id, s.screenshot_id)
              )
            })
            setScreenshotUrls(urlMap)
          })
          .catch(() => {})
      },
      {
        intervalMs: 2000,
        onComplete: (finalJob) => {
          setCurrentJob(finalJob)
        },
      }
    )

    // Initial screenshot fetch
    listScreenshots(job.job_id)
      .then((screenshotItems) => {
        const urlMap = new Map<string, string>()
        screenshotItems.forEach((s) => {
          urlMap.set(
            s.screenshot_id,
            getScreenshotUrl(job.job_id, s.screenshot_id)
          )
        })
        setScreenshotUrls(urlMap)
      })
      .catch(() => {})

    return () => {
      pollerRef.current?.stop()
    }
  }, [currentJob.job_id])

  // Determine which versions have been tested
  const testedVersions = new Set(Object.keys(currentJob.test_results))

  // Build ordered list of versions to display
  const displayVersions =
    currentJob.versions.length > 0
      ? currentJob.versions
      : ALL_VERSIONS.map((v) => v.label)

  // Group by minor version for display
  const groupedByMajor = displayVersions.reduce<Record<string, string[]>>(
    (acc, label) => {
      const ver = ALL_VERSIONS.find((v) => v.label === label)
      if (!ver) return acc
      const group =
        ver.major === 1 ? `1.${ver.minor}` : `${ver.major}.${ver.minor}`
      if (!acc[group]) acc[group] = []
      acc[group].push(label)
      return acc
    },
    {}
  )

  const handleRetry = useCallback(async () => {
    setLoading(true)
    try {
      const updated = await retryJob(currentJob.job_id)
      setCurrentJob(updated)
      // Restart polling
      pollerRef.current?.stop()
      pollerRef.current = createJobPoller(updated.job_id, (newJob) => {
        setCurrentJob(newJob)
      })
    } catch {
      // Error handling via UI
    } finally {
      setLoading(false)
    }
  }, [currentJob.job_id])

  const handleCancel = useCallback(async () => {
    setLoading(true)
    try {
      const updated = await cancelJob(currentJob.job_id)
      setCurrentJob(updated)
      // Restart polling for the cancelled job
      pollerRef.current?.stop()
      pollerRef.current = createJobPoller(updated.job_id, (newJob) => {
        setCurrentJob(newJob)
      })
    } catch {
      // Error handling via UI
    } finally {
      setLoading(false)
    }
  }, [currentJob.job_id])

  const overallProgress = getOverallProgress(currentJob)
  const passed = (
    Object.values(currentJob.test_results) as { passed: boolean }[]
  ).filter((r) => r.passed).length
  const failed = (
    Object.values(currentJob.test_results) as { passed: boolean }[]
  ).filter((r) => !r.passed).length
  const pending = displayVersions.length - testedVersions.size

  return (
    <div className="flex flex-col gap-3">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          {getStatusIcon(currentJob.status)}
          <span
            className={cn(
              "text-xs font-medium",
              getStatusColor(currentJob.status)
            )}
          >
            {currentJob.status.charAt(0).toUpperCase() +
              currentJob.status.slice(1)}
          </span>
          {currentJob.current_step && (
            <span className="text-[10px] text-muted-foreground">
              — {currentJob.current_step}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <span className="font-mono text-[10px] text-muted-foreground">
            {currentJob.job_id}
          </span>
          {["queued", "building", "testing"].includes(currentJob.status) && (
            <Button
              variant="outline"
              size="xs"
              onClick={handleCancel}
              disabled={loading}
              className="h-5 gap-1 px-1.5 text-[10px] text-destructive hover:bg-destructive/10"
            >
              {loading ? (
                <Loader2 className="size-3 animate-spin" />
              ) : (
                <Square className="size-3" />
              )}
              Cancel
            </Button>
          )}
          {["finished", "failed"].includes(currentJob.status) && (
            <Button
              variant="outline"
              size="xs"
              onClick={handleRetry}
              disabled={loading}
              className="h-5 gap-1 px-1.5 text-[10px]"
            >
              {loading ? (
                <Loader2 className="size-3 animate-spin" />
              ) : (
                <RotateCcw className="size-3" />
              )}
              Retry
            </Button>
          )}
        </div>
      </div>

      {/* Progress bar */}
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
        <div
          className={cn(
            "h-full transition-all duration-500",
            currentJob.status === "failed" ? "bg-destructive" : "bg-primary"
          )}
          style={{ width: `${overallProgress}%` }}
        />
      </div>

      {/* Stats row */}
      <div className="flex items-center gap-4 text-[10px]">
        <span className="text-muted-foreground">
          ETA: {formatEta(currentJob.eta_seconds)}
        </span>
        {Object.keys(currentJob.test_results).length > 0 && (
          <>
            <span className="flex items-center gap-1 text-green-500">
              <CheckCircle2 className="size-3" />
              {passed}
            </span>
            {failed > 0 && (
              <span className="flex items-center gap-1 text-destructive">
                <XCircle className="size-3" />
                {failed}
              </span>
            )}
            {pending > 0 && (
              <span className="flex items-center gap-1 text-muted-foreground">
                <Clock className="size-3" />
                {pending} pending
              </span>
            )}
          </>
        )}
      </div>

      {/* Error message */}
      {currentJob.error_message && (
        <div className="rounded-none border border-destructive/50 bg-destructive/10 px-3 py-2 text-xs text-destructive">
          {currentJob.error_message}
        </div>
      )}

      {/* Version results with inline screenshots */}
      {Object.keys(currentJob.test_results).length > 0 && (
        <div className="flex flex-col gap-1">
          {Object.entries(groupedByMajor).map(([group, versions]) => (
            <div key={group} className="flex flex-col gap-0.5">
              <div className="bg-muted/20 px-2 py-1 text-[10px] font-medium text-muted-foreground">
                {group}
              </div>
              {versions.map((label) => {
                const result = getTestResultForVersion(currentJob, label)
                const screenshotUrl = screenshotUrls.get(label)
                const hasScreenshot = !!screenshotUrl
                const isPending = !result

                return (
                  <div
                    key={label}
                    className={cn(
                      "flex flex-col border border-border",
                      result?.passed === false ? "border-destructive/30" : ""
                    )}
                  >
                    {/* Row: status + version + duration */}
                    <div className="flex items-center gap-2 px-2 py-1 text-xs">
                      <span className="size-3 shrink-0">
                        {isPending ? (
                          <Loader2 className="size-3 animate-spin text-muted-foreground" />
                        ) : result?.passed ? (
                          <CheckCircle2 className="size-3 text-green-500" />
                        ) : (
                          <XCircle className="size-3 text-destructive" />
                        )}
                      </span>
                      <span className="font-mono">{label}</span>
                      <span className="ml-auto text-[10px] text-muted-foreground">
                        {result?.duration_seconds != null
                          ? formatDuration(result.duration_seconds)
                          : "—"}
                      </span>
                    </div>

                    {/* Screenshot */}
                    {hasScreenshot && (
                      <div className="border-t border-border px-2 py-2">
                        <div className="relative overflow-hidden rounded-none border border-border bg-muted/20">
                          <img
                            src={screenshotUrl}
                            alt={`${label} screenshot`}
                            className="max-h-[240px] w-full object-contain"
                            loading="lazy"
                          />
                          <div className="absolute right-1 bottom-1 flex gap-1">
                            <a
                              href={screenshotUrl}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="flex h-5 items-center gap-1 rounded-none border border-border bg-background/80 px-1.5 text-[9px] text-muted-foreground backdrop-blur transition-colors hover:bg-background hover:text-foreground"
                            >
                              <ExternalLink className="size-2.5" />
                              Open
                            </a>
                            <a
                              href={screenshotUrl}
                              download={`${label}.png`}
                              className="flex h-5 items-center gap-1 rounded-none border border-border bg-background/80 px-1.5 text-[9px] text-muted-foreground backdrop-blur transition-colors hover:bg-background hover:text-foreground"
                            >
                              <Download className="size-2.5" />
                              Save
                            </a>
                          </div>
                        </div>
                      </div>
                    )}

                    {/* Error message */}
                    {result?.error && (
                      <div className="border-t border-border px-2 py-1 text-[10px] text-destructive">
                        {result.error}
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
