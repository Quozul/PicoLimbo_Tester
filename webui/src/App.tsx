import { useState, useCallback } from "react"
import { JobCreation } from "@/components/JobCreation"
import { VncPanel } from "@/components/VncPanel"
import { JobInfoPanel } from "@/components/JobInfoPanel"
import { type JobInfo } from "@/lib/api"

export function App() {
  const [activeJob, setActiveJob] = useState<JobInfo | null>(null)

  const handleJobCreated = useCallback((job: JobInfo) => {
    setActiveJob(job)
  }, [])

  const handleSelectJob = useCallback((job: JobInfo) => {
    setActiveJob(job)
  }, [])

  const latestJob = activeJob

  return (
    <div className="flex h-dvh w-screen flex-col bg-background text-foreground">
      {/* Top bar */}
      <header className="flex items-center justify-between border-b border-border bg-background px-4 py-2">
        <div className="flex items-center gap-2">
          <svg
            className="size-5 text-primary"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
          >
            <path d="M22 12h-4l-3 9L9 3l-3 9H2" />
          </svg>
          <h1 className="text-sm font-medium">
            PicoLimbo <span className="text-muted-foreground">Test Runner</span>
          </h1>
        </div>
      </header>

      {/* Main content — 3 columns */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left column — Job Creation */}
        <div className="hidden md:flex w-[400px] max-w-[480px] min-w-[320px] flex-col overflow-hidden border-r border-border">
          <JobCreation onJobCreated={handleJobCreated} />
        </div>

        {/* Middle column — VNC Viewer */}
        <div className="hidden xl:block xl:flex-1 overflow-hidden">
          <VncPanel />
        </div>

        {/* Right column — Job History + Job Progress */}
        <div className="flex flex-1 flex-col overflow-hidden border-l border-border xl:w-[420px] xl:max-w-[500px] xl:min-w-[340px]">
          <JobInfoPanel activeJob={latestJob} onSelectJob={handleSelectJob} />
        </div>
      </div>
    </div>
  )
}

export default App
