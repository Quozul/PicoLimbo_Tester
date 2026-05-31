import { JobForm } from "@/components/JobForm"
import { type JobInfo } from "@/lib/api"
import { LayoutPanelLeft } from "lucide-react"

interface JobCreationProps {
  onJobCreated: (job: JobInfo) => void
}

export function JobCreation({ onJobCreated }: JobCreationProps) {
  return (
    <div className="flex h-full flex-col overflow-hidden">
      <div className="flex flex-shrink-0 items-center gap-2 border-b border-border px-4 py-3">
        <LayoutPanelLeft className="size-3.5 text-muted-foreground" />
        <h2 className="text-xs font-medium">Create Job</h2>
      </div>
      <div className="flex-1 overflow-y-hidden px-4 py-4">
        <JobForm onJobCreated={onJobCreated} />
      </div>
    </div>
  )
}
