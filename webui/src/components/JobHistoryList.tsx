import { useState, useEffect, useCallback } from "react"
import { listJobs, type JobInfo } from "@/lib/api"
import { cn } from "@/lib/utils"
import { CheckCircle2, AlertTriangle, Loader2, Circle } from "lucide-react"

interface JobHistoryListProps {
  activeJob: JobInfo | null
  onSelectJob: (job: JobInfo) => void
}

function getStatusIcon(status: string) {
  switch (status) {
    case "queued":
      return <Loader2 className="size-3 animate-spin text-muted-foreground" />
    case "building":
      return <Loader2 className="size-3 animate-spin text-primary" />
    case "testing":
      return <Loader2 className="size-3 animate-spin text-amber-500" />
    case "finished":
      return <CheckCircle2 className="size-3 text-green-500" />
    case "failed":
      return <AlertTriangle className="size-3 text-destructive" />
    default:
      return <Circle className="size-3 text-muted-foreground" />
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

function formatTimeAgo(dateString: string): string {
  const now = Date.now()
  const date = new Date(dateString).getTime()
  const diff = now - date

  const seconds = Math.floor(diff / 1000)
  if (seconds < 60) return "just now"

  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes}m ago`

  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`

  const days = Math.floor(hours / 24)
  return `${days}d ago`
}

function formatDuration(ms: number): string {
  const totalMinutes = Math.floor(ms / 60000)
  if (totalMinutes < 1) return "<1m"
  if (totalMinutes < 60) return `${totalMinutes}m`
  const hours = Math.floor(totalMinutes / 60)
  const minutes = totalMinutes % 60
  if (minutes === 0) return `${hours}h`
  return `${hours}h ${minutes}m`
}

export function JobHistoryList({
  activeJob,
  onSelectJob,
}: JobHistoryListProps) {
  const [jobs, setJobs] = useState<JobInfo[]>([])
  const [loading, setLoading] = useState(true)

  const fetchJobs = useCallback(async () => {
    try {
      const list = await listJobs({ limit: 50 })
      list.sort(
        (a, b) =>
          new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
      )
      setJobs(list)
      setLoading(false)
    } catch {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchJobs()
    const interval = setInterval(fetchJobs, 5000)
    return () => clearInterval(interval)
  }, [fetchJobs])

  const handleSelect = useCallback(
    (job: JobInfo) => {
      onSelectJob(job)
    },
    [onSelectJob]
  )

  return (
    <div className="flex-shrink-0 border-border px-4 py-3">
      <div className="mb-2 flex items-center justify-between">
        <h2 className="text-xs font-medium">Job History</h2>
        <span className="text-[10px] text-muted-foreground">
          {jobs.length} jobs
        </span>
      </div>
      <div className="flex max-h-[200px] scrollbar-thin flex-col gap-1 overflow-y-auto">
        {loading ? (
          <div className="py-4 text-center">
            <Loader2 className="mx-auto size-4 animate-spin text-muted-foreground" />
          </div>
        ) : jobs.length === 0 ? (
          <div className="py-4 text-center text-xs text-muted-foreground">
            No jobs yet
          </div>
        ) : (
          jobs.map((job) => {
            const isLatest = job.job_id === activeJob?.job_id
            const testResults = Object.values(job.test_results) as {
              passed: boolean
            }[]
            const passed = testResults.filter((r) => r.passed).length
            const failed = testResults.filter((r) => !r.passed).length

            return (
              <div
                key={job.job_id}
                onClick={() => handleSelect(job)}
                className={cn(
                  "flex cursor-pointer items-center gap-2 rounded-none border px-2.5 py-1.5 text-xs transition-all",
                  isLatest
                    ? "border-primary bg-primary/5"
                    : "border-border hover:bg-muted/50",
                  job.status === "failed" ? "border-destructive/30" : ""
                )}
              >
                {getStatusIcon(job.status)}
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="truncate font-mono text-[10px]">
                      {job.job_id.slice(0, 8)}
                    </span>
                    <span
                      className={cn("text-[10px]", getStatusColor(job.status))}
                    >
                      {job.status}
                    </span>
                  </div>
                  <div className="flex items-center gap-2 text-[10px] text-muted-foreground">
                    <span>{job.ref}</span>
                    <span>•</span>
                    <span>{formatTimeAgo(job.created_at)}</span>
                    {testResults.length > 0 && (
                      <>
                        <span>•</span>
                        <span className="text-green-500">{passed}</span>
                        {failed > 0 && (
                          <>
                            <span>/</span>
                            <span className="text-destructive">{failed}</span>
                          </>
                        )}
                      </>
                    )}
                    {(job.status === "finished" || job.status === "failed") &&
                      job.created_at &&
                      job.updated_at && (
                        <>
                          <span>•</span>
                          <span>
                            took {formatDuration(
                              new Date(job.updated_at).getTime() -
                                new Date(job.created_at).getTime()
                            )}
                          </span>
                        </>
                      )}
                  </div>
                </div>
              </div>
            )
          })
        )}
      </div>
    </div>
  )
}
