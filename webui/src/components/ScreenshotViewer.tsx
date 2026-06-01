import { useState, useEffect, useCallback } from "react"
import {
  createJobPoller,
  type JobInfo,
} from "@/lib/api"
import { cn } from "@/lib/utils"
import { ALL_VERSIONS } from "@/lib/versions"
import { Eye, EyeOff, Loader2, X, Maximize2 } from "lucide-react"

interface ScreenshotViewerProps {
  job: JobInfo
}

export function ScreenshotViewer({ job }: ScreenshotViewerProps) {
  const [screenshotUrls, setScreenshotUrls] = useState<Map<string, string>>(
    new Map()
  )
  const [visible, setVisible] = useState<Set<string>>(new Set())
  const [selectedScreenshot, setSelectedScreenshot] = useState<string | null>(
    null
  )
  const [loading, setLoading] = useState(true)

  const buildScreenshotMap = useCallback((jobData: JobInfo) => {
    const map = new Map<string, string>()
    Object.entries(jobData.test_results).forEach(([key, result]) => {
      if ((result as any).screenshot_path) {
        map.set(key, `/api/jobs/${jobData.job_id}/screenshots/${key}`)
      }
    })
    setScreenshotUrls(map)
  }, [])

  useEffect(() => {
    buildScreenshotMap(job)
    setLoading(false)

    const poller = createJobPoller(job.job_id, (updatedJob) => {
      buildScreenshotMap(updatedJob)
    })

    return () => poller.stop()
  }, [job.job_id, buildScreenshotMap])

  const toggleVisible = useCallback((version: string) => {
    setVisible((prev) => {
      const next = new Set(prev)
      if (next.has(version)) next.delete(version)
      else next.add(version)
      return next
    })
  }, [])

  const openModal = useCallback((version: string) => {
    setSelectedScreenshot(version)
  }, [])

  const closeModal = useCallback(() => {
    setSelectedScreenshot(null)
  }, [])

  // Filter to only visible screenshots, sorted by version
  const visibleItems = Array.from(screenshotUrls.entries())
    .filter(([id]) => visible.has(id))
    .sort((a, b) => {
      const verA = ALL_VERSIONS.find((v) => v.label === a[0])
      const verB = ALL_VERSIONS.find((v) => v.label === b[0])
      if (!verA && !verB) return 0
      if (!verA) return 1
      if (!verB) return -1
      return (
        verA.major - verB.major ||
        verA.minor - verB.minor ||
        verA.patch - verB.patch
      )
    })

  if (loading) {
    return (
      <div className="flex items-center justify-center py-8">
        <Loader2 className="size-5 animate-spin text-muted-foreground" />
      </div>
    )
  }

  if (screenshotUrls.size === 0) {
    return (
      <div className="flex flex-col items-center justify-center gap-2 py-8 text-xs text-muted-foreground">
        <EyeOff className="size-8 opacity-30" />
        <span>No screenshots yet</span>
        <span className="text-[10px]">
          Screenshots will appear as tests complete
        </span>
      </div>
    )
  }

  return (
    <>
      {/* Screenshot grid */}
      <div className="flex flex-col gap-1">
        {visibleItems.length === 0 ? (
          <div className="py-4 text-center text-xs text-muted-foreground">
            No screenshots visible. Click the eye icon on test results to show
            them.
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-1.5">
            {visibleItems.map(([id]) => {
              const result = job.test_results[id]
              const passed = result?.passed
              return (
                <div
                  key={id}
                  className={cn(
                    "group relative cursor-pointer overflow-hidden border border-border bg-muted/20 transition-all hover:border-primary/50 hover:shadow-sm",
                    passed === false ? "border-destructive/30" : ""
                  )}
                  onClick={() => openModal(id)}
                >
                  <img
                    src={`/api/jobs/${job.job_id}/screenshots/${id}`}
                    alt={`Screenshot ${id}`}
                    className="aspect-video h-auto w-full object-cover"
                    loading="lazy"
                  />
                {/* Overlay */}
                <div className="absolute inset-0 flex items-end bg-black/0 transition-colors group-hover:bg-black/30">
                  <div className="w-full bg-gradient-to-t from-black/70 to-transparent px-1.5 py-1">
                    <div className="flex items-center justify-between">
                      <span className="font-mono text-[10px] text-white/90">
                        {id}
                      </span>
                      {passed === false && (
                        <span className="text-[10px] text-destructive">
                          FAIL
                        </span>
                      )}
                    </div>
                  </div>
                </div>
                {/* Eye toggle */}
                <button
                  onClick={(e) => {
                    e.stopPropagation()
                    toggleVisible(id)
                  }}
                  className="absolute top-1 right-1 flex size-5 items-center justify-center rounded-none bg-black/50 opacity-0 transition-colors group-hover:opacity-100 hover:bg-black/70"
                >
                  <Eye className="size-3 text-white" />
                </button>
                </div>
              )
            })}
          </div>
        )}
      </div>

      {/* Modal */}
      {selectedScreenshot && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4"
          onClick={closeModal}
        >
          <div
            className="relative flex max-h-[90vh] w-full max-w-5xl flex-col"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Header */}
            <div className="flex items-center justify-between border-b border-border bg-background px-3 py-2">
              <span className="font-mono text-xs">{selectedScreenshot}</span>
              <div className="flex items-center gap-2">
                <a
                  href={`/api/jobs/${job.job_id}/screenshots/${selectedScreenshot}`}
                  download
                  className="flex h-6 items-center gap-1 rounded-none border border-border bg-transparent px-2 text-[10px] text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                >
                  <Maximize2 className="size-3" />
                  Download
                </a>
                <button
                  onClick={closeModal}
                  className="h-6 rounded-none border border-border bg-transparent px-2 text-[10px] text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                >
                  <X className="size-3" />
                </button>
              </div>
            </div>
            {/* Image */}
            <div className="flex-1 overflow-auto p-2">
              <img
                src={`/api/jobs/${job.job_id}/screenshots/${selectedScreenshot}`}
                alt={`Screenshot ${selectedScreenshot}`}
                className="max-h-[80vh] max-w-full object-contain"
              />
            </div>
          </div>
        </div>
      )}
    </>
  )
}
