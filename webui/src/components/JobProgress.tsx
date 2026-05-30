import { useState, useEffect, useCallback, useRef } from "react"
import {
  getJob,
  createJobPoller,
  retryJob,
  listScreenshots,
  type JobInfo,
  type TestResult,
} from "@/lib/api"
import { Button } from "@/components/ui/button"
import {
  ALL_VERSIONS,
  type MinecraftVersion,
} from "@/lib/versions"
import {
  CheckCircle2,
  Circle,
  Loader2,
  XCircle,
  Clock,
  RotateCcw,
  AlertTriangle,
  ChevronDown,
  ChevronUp,
} from "lucide-react"
import { cn } from "@/lib/utils"

interface JobProgressProps {
  job: JobInfo
}

function getTestResultForVersion(
  job: JobInfo,
  versionLabel: string
): TestResult | undefined {
  return job.test_results[versionLabel]
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
      return <Loader2 className="size-4 text-primary animate-spin" />
    case "testing":
      return <Loader2 className="size-4 text-amber-500 animate-spin" />
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
  const [expandedVersions, setExpandedVersions] = useState<Set<string>>(new Set())
  const [screenshots, setScreenshots] = useState<Map<string, string>>(new Map())
  const [loading, setLoading] = useState(false)

  const pollerRef = useRef<ReturnType<typeof createJobPoller> | null>(null)

  // Poll for updates
  useEffect(() => {
    pollerRef.current = createJobPoller(
      currentJob.job_id,
      (updated) => {
        setCurrentJob(updated)
        // Fetch screenshots when new test results appear
        listScreenshots(updated.job_id)
          .then(screenshots => {
            const screenshotMap = new Map<string, string>()
            screenshots.forEach(s => {
              screenshotMap.set(s.screenshot_id, s.path)
            })
            setScreenshots(screenshotMap)
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
      .then(screenshots => {
        const screenshotMap = new Map<string, string>()
        screenshots.forEach(s => {
          screenshotMap.set(s.screenshot_id, s.path)
        })
        setScreenshots(screenshotMap)
      })
      .catch(() => {})

    return () => {
      pollerRef.current?.stop()
    }
  }, [currentJob.job_id])

  // Determine which versions have been tested
  const testedVersions = new Set(Object.keys(currentJob.test_results))

  // Build ordered list of versions to display
  const displayVersions = currentJob.versions.length > 0
    ? currentJob.versions
    : ALL_VERSIONS.map(v => v.label)

  // Group by major version for display
  const groupedByMajor = displayVersions.reduce<Record<string, string[]>>((acc, label) => {
    const ver = ALL_VERSIONS.find(v => v.label === label)
    if (!ver) return acc
    const group = ver.major >= 20 ? `26.x` : `1.${ver.minor}`
    if (!acc[group]) acc[group] = []
    acc[group].push(label)
    return acc
  }, {})

  const toggleVersion = useCallback((label: string) => {
    setExpandedVersions(prev => {
      const next = new Set(prev)
      if (next.has(label)) next.delete(label)
      else next.add(label)
      return next
    })
  }, [])

  const handleRetry = useCallback(async () => {
    setLoading(true)
    try {
      const updated = await retryJob(currentJob.job_id)
      setCurrentJob(updated)
      // Restart polling
      pollerRef.current?.stop()
      pollerRef.current = createJobPoller(
        updated.job_id,
        (newJob) => {
          setCurrentJob(newJob)
        }
      )
    } catch {
      // Error handling via UI
    } finally {
      setLoading(false)
    }
  }, [currentJob.job_id])

  const overallProgress = getOverallProgress(currentJob)
  const passed = Object.values(currentJob.test_results).filter(r => r.passed).length
  const failed = Object.values(currentJob.test_results).filter(r => !r.passed).length
  const pending = displayVersions.length - testedVersions.size

  return (
    <div className="flex flex-col gap-3">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          {getStatusIcon(currentJob.status)}
          <span className={cn("text-xs font-medium", getStatusColor(currentJob.status))}>
            {currentJob.status.charAt(0).toUpperCase() + currentJob.status.slice(1)}
          </span>
          {currentJob.current_step && (
            <span className="text-[10px] text-muted-foreground">
              — {currentJob.current_step}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <span className="text-[10px] text-muted-foreground font-mono">
            {currentJob.job_id}
          </span>
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

      {/* Version test results */}
      {Object.keys(currentJob.test_results).length > 0 && (
        <div className="flex flex-col gap-0.5">
          {Object.entries(groupedByMajor).map(([group, versions]) => (
            <div key={group} className="border border-border">
              <div className="px-2 py-1.5 text-[10px] font-medium text-muted-foreground bg-muted/20">
                {group}
              </div>
              {versions.map(label => {
                const result = getTestResultForVersion(currentJob, label)
                const isExpanded = expandedVersions.has(label)
                const hasScreenshot = screenshots.has(label)

                return (
                  <div key={label}>
                    <button
                      onClick={() => toggleVersion(label)}
                      className={cn(
                        "flex w-full items-center gap-2 px-2 py-1 text-xs transition-colors hover:bg-muted/30",
                        result?.passed === false ? "bg-destructive/5" : ""
                      )}
                    >
                      <span className="size-3 shrink-0">
                        {result ? (
                          result.passed ? (
                            <CheckCircle2 className="size-3 text-green-500" />
                          ) : (
                            <XCircle className="size-3 text-destructive" />
                          )
                        ) : (
                          <Loader2 className="size-3 text-muted-foreground animate-spin" />
                        )}
                      </span>
                      <span className="font-mono">{label}</span>
                      <span className="ml-auto text-[10px] text-muted-foreground">
                        {result?.duration_seconds != null
                          ? formatDuration(result.duration_seconds)
                          : ""}
                      </span>
                      {hasScreenshot && (
                        isExpanded ? (
                          <ChevronUp className="size-3 text-muted-foreground" />
                        ) : (
                          <ChevronDown className="size-3 text-muted-foreground" />
                        )
                      )}
                    </button>

                    {isExpanded && result && (
                      <div className="px-2 py-2 pl-5 text-[10px]">
                        {result.error && (
                          <div className="text-destructive mb-1">{result.error}</div>
                        )}
                        {hasScreenshot && (
                          <a
                            href={getScreenshotUrl(currentJob.job_id, label)}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-primary underline-offset-2 hover:underline"
                          >
                            View screenshot
                          </a>
                        )}
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

function getScreenshotUrl(jobId: string, screenshotId: string): string {
  const API_BASE = import.meta.env.VITE_API_URL || "/api"
  return `${API_BASE}/jobs/${jobId}/screenshots/${screenshotId}`
}
