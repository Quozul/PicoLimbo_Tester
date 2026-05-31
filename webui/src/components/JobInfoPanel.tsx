import { type JobInfo } from "@/lib/api"
import { JobProgress } from "@/components/JobProgress"
import { JobHistoryList } from "@/components/JobHistoryList"

interface JobInfoPanelProps {
  jobs: JobInfo[]
  activeJob: JobInfo | null
  loadingJobs: boolean
  onSelectJob: (job: JobInfo) => void
}

export function JobInfoPanel({
  jobs,
  activeJob,
  loadingJobs,
  onSelectJob,
}: JobInfoPanelProps) {
  const latestJob = jobs.find(j => j.job_id === activeJob?.job_id)

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Job History */}
      <JobHistoryList
        jobs={jobs}
        activeJob={activeJob}
        onSelectJob={onSelectJob}
        loadingJobs={loadingJobs}
      />

      {/* Job Progress */}
      <div className="flex-1 overflow-y-auto px-4 py-4 border-t border-border">
        {latestJob ? (
          <JobProgress job={latestJob} />
        ) : (
          <div className="flex flex-col items-center justify-center py-16 text-center gap-3">
            <svg
              className="size-12 text-muted-foreground/30"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
            >
              <rect x="2" y="3" width="20" height="14" rx="2" ry="2" />
              <line x1="8" y1="21" x2="16" y2="21" />
              <line x1="12" y1="17" x2="12" y2="21" />
            </svg>
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
  )
}
