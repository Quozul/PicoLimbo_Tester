import { useCallback } from "react"
import { type JobInfo } from "@/lib/api"
import { cn } from "@/lib/utils"
import { getStatusIcon, getStatusColor, formatTimeAgo } from "@/lib/status-helpers"

interface JobHistoryListProps {
  jobs: JobInfo[]
  activeJob: JobInfo | null
  onSelectJob: (job: JobInfo) => void
  loadingJobs: boolean
}

export function JobHistoryList({
  jobs,
  activeJob,
  onSelectJob,
  loadingJobs,
}: JobHistoryListProps) {
  const handleSelect = useCallback(
    (job: JobInfo) => {
      onSelectJob(job)
    },
    [onSelectJob],
  )

  return (
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
            <svg
              className="size-4 animate-spin text-muted-foreground mx-auto"
              viewBox="0 0 24 24"
              fill="none"
            >
              <circle
                cx="12"
                cy="12"
                r="10"
                stroke="currentColor"
                strokeWidth="3"
                className="opacity-25"
              />
              <path
                d="M4 12a8 8 0 018-8"
                stroke="currentColor"
                strokeWidth="3"
                strokeLinecap="round"
              />
            </svg>
          </div>
        ) : jobs.length === 0 ? (
          <div className="py-4 text-center text-xs text-muted-foreground">
            No jobs yet
          </div>
        ) : (
          jobs.map(job => {
            const isLatest = job.job_id === activeJob?.job_id
            const testResults = Object.values(job.test_results)
            const passed = testResults.filter((r: { passed: boolean }) => r.passed).length
            const failed = testResults.filter((r: { passed: boolean }) => !r.passed).length

            return (
              <div
                key={job.job_id}
                onClick={() => handleSelect(job)}
                className={cn(
                  "flex items-center gap-2 rounded-none border px-2.5 py-1.5 text-xs cursor-pointer transition-all",
                  isLatest
                    ? "border-primary bg-primary/5"
                    : "border-border hover:bg-muted/50",
                  job.status === "failed" ? "border-destructive/30" : "",
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
              </div>
            )
          })
        )}
      </div>
    </div>
  )
}
