import { useState, useEffect, useCallback } from "react"
import {
  getJob,
  listScreenshots,
  createJobPoller,
  type JobInfo,
  type ScreenshotItem,
} from "@/lib/api"
import { cn } from "@/lib/utils"
import { ALL_VERSIONS } from "@/lib/versions"
import {
  Eye,
  EyeOff,
  Loader2,
  X,
  Maximize2,
} from "lucide-react"

interface ScreenshotViewerProps {
  job: JobInfo
}

export function ScreenshotViewer({ job }: ScreenshotViewerProps) {
  const [screenshots, setScreenshots] = useState<Map<string, ScreenshotItem>>(new Map())
  const [visible, setVisible] = useState<Set<string>>(new Set())
  const [selectedScreenshot, setSelectedScreenshot] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  const fetchScreenshots = useCallback(async () => {
    try {
      const list = await listScreenshots(job.job_id)
      const map = new Map<string, ScreenshotItem>()
      list.forEach(s => map.set(s.screenshot_id, s))
      setScreenshots(map)
      setLoading(false)
    } catch {
      setLoading(false)
    }
  }, [job.job_id])

  useEffect(() => {
    fetchScreenshots()

    const poller = createJobPoller(
      job.job_id,
      async (updatedJob) => {
        if (updatedJob.status === "testing" || updatedJob.status === "building") {
          fetchScreenshots()
        }
      }
    )

    return () => poller.stop()
  }, [job.job_id, fetchScreenshots])

  const toggleVisible = useCallback((version: string) => {
    setVisible(prev => {
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
  const visibleItems = Array.from(screenshots.entries())
    .filter(([id]) => visible.has(id))
    .sort((a, b) => {
      const verA = ALL_VERSIONS.find(v => v.label === a[0])
      const verB = ALL_VERSIONS.find(v => v.label === b[0])
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

  if (screenshots.size === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-8 text-xs text-muted-foreground gap-2">
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
            No screenshots visible. Click the eye icon on test results to show them.
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-1.5">
            {visibleItems.map(([id, item]) => (
              <div
                key={id}
                className={cn(
                  "group relative overflow-hidden border border-border bg-muted/20 cursor-pointer transition-all hover:border-primary/50 hover:shadow-sm",
                  item.passed === false ? "border-destructive/30" : ""
                )}
                onClick={() => openModal(id)}
              >
                <img
                  src={getScreenshotUrl(job.job_id, id)}
                  alt={`Screenshot ${id}`}
                  className="w-full h-auto aspect-video object-cover"
                  loading="lazy"
                />
                {/* Overlay */}
                <div className="absolute inset-0 bg-black/0 group-hover:bg-black/30 transition-colors flex items-end">
                  <div className="w-full px-1.5 py-1 bg-gradient-to-t from-black/70 to-transparent">
                    <div className="flex items-center justify-between">
                      <span className="text-[10px] font-mono text-white/90">
                        {id}
                      </span>
                      {item.passed === false && (
                        <span className="text-[10px] text-destructive">FAIL</span>
                      )}
                    </div>
                  </div>
                </div>
                {/* Eye toggle */}
                <button
                  onClick={e => {
                    e.stopPropagation()
                    toggleVisible(id)
                  }}
                  className="absolute top-1 right-1 size-5 rounded-none bg-black/50 hover:bg-black/70 flex items-center justify-center transition-colors opacity-0 group-hover:opacity-100"
                >
                  <Eye className="size-3 text-white" />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Modal */}
      {selectedScreenshot && (
        <div
          className="fixed inset-0 z-50 bg-black/80 flex items-center justify-center p-4"
          onClick={closeModal}
        >
          <div
            className="relative max-w-5xl max-h-[90vh] w-full flex flex-col"
            onClick={e => e.stopPropagation()}
          >
            {/* Header */}
            <div className="flex items-center justify-between px-3 py-2 bg-background border-b border-border">
              <span className="text-xs font-mono">{selectedScreenshot}</span>
              <div className="flex items-center gap-2">
                <a
                  href={getScreenshotUrlLocal(job.job_id, selectedScreenshot)}
                  download
                  className="h-6 rounded-none border border-border bg-transparent px-2 text-[10px] text-muted-foreground hover:bg-muted hover:text-foreground transition-colors flex items-center gap-1"
                >
                  <Maximize2 className="size-3" />
                  Download
                </a>
                <button
                  onClick={closeModal}
                  className="h-6 rounded-none border border-border bg-transparent px-2 text-[10px] text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
                >
                  <X className="size-3" />
                </button>
              </div>
            </div>
            {/* Image */}
            <div className="flex-1 overflow-auto p-2">
              <img
                src={getScreenshotUrlLocal(job.job_id, selectedScreenshot)}
                alt={`Screenshot ${selectedScreenshot}`}
                className="max-w-full max-h-[80vh] object-contain"
              />
            </div>
          </div>
        </div>
      )}
    </>
  )
}

function getScreenshotUrlLocal(jobId: string, screenshotId: string): string {
  const API_BASE = import.meta.env.VITE_API_URL || "/api"
  return `${API_BASE}/jobs/${jobId}/screenshots/${screenshotId}`
}
