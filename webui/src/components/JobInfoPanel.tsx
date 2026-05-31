import { type JobInfo } from "@/lib/api"
import { JobProgress } from "@/components/JobProgress"
import { JobHistoryList } from "@/components/JobHistoryList"

interface JobInfoPanelProps {
  activeJob: JobInfo | null
  onSelectJob: (job: JobInfo) => void
}

export function JobInfoPanel({ activeJob, onSelectJob }: JobInfoPanelProps) {
  const latestJob = activeJob

  return (
    <div className="flex h-full flex-col overflow-hidden">
      {/* Job History */}
      <JobHistoryList activeJob={activeJob} onSelectJob={onSelectJob} />

      {/* Job Progress */}
      <div className="flex-1 overflow-y-auto border-t border-border px-4 py-4">
        {latestJob ? (
          <JobProgress job={latestJob} />
        ) : (
          <div className="flex flex-col items-center justify-center gap-3 py-16 text-center">
            <svg
              className="size-12 text-muted-foreground"
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
              <p className="text-xs text-muted-foreground">No active job</p>
              <p className="mt-1 text-[10px] text-muted-foreground/60">
                Create a job above to start testing
              </p>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
