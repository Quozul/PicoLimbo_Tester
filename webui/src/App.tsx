import { useState, useCallback, useEffect } from "react"
import { JobForm } from "@/components/JobForm"
import { JobProgress } from "@/components/JobProgress"
import { ScreenshotViewer } from "@/components/ScreenshotViewer"
import { VncViewer } from "@/components/VncViewer"
import { createJob, listJobs, type JobInfo } from "@/lib/api"
import {
  Activity,
  Monitor,
  LayoutPanelLeft,
  Eye,
  MonitorCog,
  Clock,
  CheckCircle2,
  XCircle,
  Loader2,
  AlertTriangle,
  ChevronDown,
  ChevronUp,
} from "lucide-react"

type ViewMode = "progress" | "screenshots"

function getStatusIcon(status: string) {
  switch (status) {
    case "queued":
    case "building":
    case "testing":
      return <Loader2 className="size-3 animate-spin text-muted-foreground" />
    case "finished":
      return <CheckCircle2 className="size-3 text-green-500" />
    case "failed":
      return <AlertTriangle className="size-3 text-destructive" />
    default:
      return <Clock className="size-3 text-muted-foreground" />
  }
}

function getStatusColor(status: string): string {
  switch (status) {
    case "queued":
    case "building":
    case "testing":
      return "text-muted-foreground"
    case "finished":
      return "text-green-500"
    case "failed":
      return "text-destructive"
    default:
      return "text-muted-foreground"
  }
}

function formatTimeAgo(timestamp: string): string {
  const now = Date.now()
  const then = new Date(timestamp).getTime()
  const diff = now - then
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return "just now"
  if (mins < 60) return `${mins}m ago`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  return `${days}d ago`
}

export function App() {
  const [activeJob, setActiveJob] = useState<JobInfo | null>(null)
  const [jobs, setJobs] = useState<JobInfo[]>([])
  const [expandedJobs, setExpandedJobs] = useState<Set<string>>(new Set())
  const [viewMode, setViewMode] = useState<ViewMode>("progress")
  const [loadingJobs, setLoadingJobs] = useState(true)

  const fetchJobs = useCallback(async () => {
    try {
      const list = await listJobs({ limit: 50 })
      // Sort by created_at descending (newest first)
      list.sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
      setJobs(list)
      setLoadingJobs(false)
    } catch {
      setLoadingJobs(false)
    }
  }, [])

  useEffect(() => {
    fetchJobs()
    const interval = setInterval(fetchJobs, 5000)
    return () => clearInterval(interval)
  }, [fetchJobs])

  const handleJobCreated = useCallback((job: JobInfo) => {
    setActiveJob(job)
    fetchJobs()
  }, [fetchJobs])

  const toggleJobExpand = useCallback((jobId: string) => {
    setExpandedJobs(prev => {
      const next = new Set(prev)
      if (next.has(jobId)) next.delete(jobId)
      else next.add(jobId)
      return next
    })
  }, [])

  const handleSelectJob = useCallback((job: JobInfo) => {
    setActiveJob(job)
    setViewMode("progress")
  }, [])

  // Find the most recent job that matches the active job
  const latestJob = jobs.find(j => j.job_id === activeJob?.job_id)

  return (
    <div className="flex h-dvh w-screen flex-col bg-background text-foreground">
      {/* Top bar */}
      <header className="flex items-center justify-between border-b border-border px-4 py-2 bg-background">
        <div className="flex items-center gap-2">
          <Activity className="size-5 text-primary" />
          <h1 className="text-sm font-medium">
            PicoLimbo <span className="text-muted-foreground">Test Runner</span>
          </h1>
        </div>
        <div className="flex items-center gap-2 text-[10px] text-muted-foreground">
          <span>API: {import.meta.env.VITE_API_URL || "localhost:8000"}</span>
          <span className="text-border">|</span>
          <span>VNC: {import.meta.env.VITE_VNC_URL || "localhost:6080"}</span>
        </div>
      </header>

      {/* Main content */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left panel */}
        <div className="flex w-[480px] min-w-[360px] max-w-[560px] flex-col border-r border-border overflow-hidden">
          {/* Job creation form */}
          <div className="flex-shrink-0 overflow-y-auto px-4 py-4">
            <div className="flex items-center gap-2 mb-3">
              <LayoutPanelLeft className="size-4 text-muted-foreground" />
              <h2 className="text-xs font-medium">Create Job</h2>
            </div>
            <JobForm onJobCreated={handleJobCreated} />
          </div>

          {/* Job history */}
          <div className="flex-shrink-0 border-t border-border px-4 py-3">
            <div className="flex items-center justify-between mb-2">
              <h2 className="text-xs font-medium">Job History</h2>
              <span className="text-[10px] text-muted-foreground">
                {jobs.length} jobs
              </span>
            </div>
            <div className="flex flex-col gap-1 max-h-[200px] overflow-y-auto scrollbar-thin">
              {loadingJobs ? (
                <div className="py-4 text-center">
                  <Loader2 className="size-4 animate-spin text-muted-foreground mx-auto" />
                </div>
              ) : jobs.length === 0 ? (
                <div className="py-4 text-center text-xs text-muted-foreground">
                  No jobs yet
                </div>
              ) : (
                jobs.map(job => {
                  const isExpanded = expandedJobs.has(job.job_id)
                  const isLatest = job.job_id === activeJob?.job_id
                  const testResults = job.test_results || {}
                  const passed = Object.values(testResults).filter(r => r.passed).length
                  const failed = Object.values(testResults).filter(r => !r.passed).length

                  return (
                    <div
                      key={job.job_id}
                      onClick={() => handleSelectJob(job)}
                      className={cn(
                        "flex items-center gap-2 rounded-none border px-2.5 py-1.5 text-xs cursor-pointer transition-all",
                        isLatest
                          ? "border-primary bg-primary/5"
                          : "border-border hover:bg-muted/50",
                        job.status === "failed" ? "border-destructive/30" : ""
                      )}
                    >
                      {getStatusIcon(job.status)}
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="font-mono truncate text-[10px]">
                            {job.job_id.slice(0, 8)}
                          </span>
                          <span className={cn("text-[10px]", getStatusColor(job.status))}>
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
                        </div>
                      </div>
                      {isExpanded ? (
                        <ChevronUp className="size-3 text-muted-foreground shrink-0" />
                      ) : (
                        <ChevronDown className="size-3 text-muted-foreground shrink-0" />
                      )}
                    </div>
                  )
                })
              )}
            </div>
          </div>

          {/* Job progress / screenshots */}
          <div className="flex-1 overflow-y-auto px-4 py-4 border-t border-border">
            {latestJob ? (
              <>
                {/* View mode tabs */}
                <div className="flex items-center gap-1 mb-3">
                  <button
                    onClick={() => setViewMode("progress")}
                    className={cn(
                      "flex items-center gap-1.5 rounded-none border px-2.5 py-1 text-xs transition-colors",
                      viewMode === "progress"
                        ? "border-primary bg-primary text-primary-foreground"
                        : "border-border bg-transparent text-muted-foreground hover:bg-muted/50"
                    )}
                  >
                    <Monitor className="size-3.5" />
                    Progress
                  </button>
                  <button
                    onClick={() => setViewMode("screenshots")}
                    className={cn(
                      "flex items-center gap-1.5 rounded-none border px-2.5 py-1 text-xs transition-colors",
                      viewMode === "screenshots"
                        ? "border-primary bg-primary text-primary-foreground"
                        : "border-border bg-transparent text-muted-foreground hover:bg-muted/50"
                    )}
                  >
                    <Eye className="size-3.5" />
                    Screenshots
                  </button>
                </div>

                {viewMode === "progress" && <JobProgress job={latestJob} />}
                {viewMode === "screenshots" && <ScreenshotViewer job={latestJob} />}
              </>
            ) : (
              <div className="flex flex-col items-center justify-center py-16 text-center gap-3">
                <MonitorCog className="size-12 text-muted-foreground/30" />
                <div>
                  <p className="text-xs text-muted-foreground">
                    No active job
                  </p>
                  <p className="text-[10px] text-muted-foreground/60 mt-1">
                    Create a job above to start testing
                  </p>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Right panel - noVNC */}
        <div className="flex-1 overflow-hidden">
          <VncViewer />
        </div>
      </div>
    </div>
  )
}

function cn(...classes: (string | undefined | false | null)[]) {
  return classes.filter(Boolean).join(" ")
}

export default App
