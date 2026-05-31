import { useState, useCallback, useEffect } from "react"
import { JobCreation } from "@/components/JobCreation"
import { VncPanel } from "@/components/VncPanel"
import { JobInfoPanel } from "@/components/JobInfoPanel"
import { listJobs, type JobInfo } from "@/lib/api"

export function App() {
  const [activeJob, setActiveJob] = useState<JobInfo | null>(null)
  const [jobs, setJobs] = useState<JobInfo[]>([])
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

  const handleSelectJob = useCallback((job: JobInfo) => {
    setActiveJob(job)
  }, [])

  return (
    <div className="flex h-dvh w-screen flex-col bg-background text-foreground">
      {/* Top bar */}
      <header className="flex items-center justify-between border-b border-border px-4 py-2 bg-background">
        <div className="flex items-center gap-2">
          <svg className="size-5 text-primary" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M22 12h-4l-3 9L9 3l-3 9H2" />
          </svg>
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

      {/* Main content — 3 columns */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left column — Job Creation */}
        <div className="w-[400px] min-w-[320px] max-w-[480px] border-r border-border flex flex-col overflow-hidden">
          <JobCreation onJobCreated={handleJobCreated} />
        </div>

        {/* Middle column — VNC Viewer */}
        <div className="flex-1 overflow-hidden">
          <VncPanel />
        </div>

        {/* Right column — Job History + Job Progress */}
        <div className="w-[420px] min-w-[340px] max-w-[500px] border-l border-border flex flex-col overflow-hidden">
          <JobInfoPanel
            jobs={jobs}
            activeJob={activeJob}
            loadingJobs={loadingJobs}
            onSelectJob={handleSelectJob}
          />
        </div>
      </div>
    </div>
  )
}

export default App
