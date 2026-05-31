import { useState, useCallback, useEffect, useRef } from "react"
import { Button } from "@/components/ui/button"
import { RefreshCw, Maximize2, Minimize2 } from "lucide-react"
import { cn } from "@/lib/utils"

interface VncViewerProps {
  vncUrl?: string
}

export function VncViewer({ vncUrl }: VncViewerProps) {
  const [isFullscreen, setIsFullscreen] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)

  const baseUrl = vncUrl || import.meta.env.VITE_VNC_URL || "http://localhost:6080/vnc.html?host=localhost&port=5900&encrypt=false"

  const toggleFullscreen = useCallback(() => {
    if (!containerRef.current) return
    if (!document.fullscreenElement) {
      containerRef.current.requestFullscreen()
      setIsFullscreen(true)
    } else {
      document.exitFullscreen()
      setIsFullscreen(false)
    }
  }, [])

  useEffect(() => {
    const handleChange = () => {
      setIsFullscreen(!!document.fullscreenElement)
    }
    document.addEventListener("fullscreenchange", handleChange)
    return () => document.removeEventListener("fullscreenchange", handleChange)
  }, [])

  return (
    <div
      ref={containerRef}
      className={cn(
        "flex h-full flex-col overflow-hidden bg-muted/20",
        isFullscreen ? "fixed inset-0 z-50" : "",
      )}
    >
      {/* Toolbar */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-border bg-background/80 backdrop-blur">
        <span className="text-xs font-medium text-muted-foreground">
          Live VNC Viewer
        </span>
        <div className="flex items-center gap-1">
          <Button
            variant="ghost"
            size="icon-sm"
            onClick={() => {
              const iframe = containerRef.current?.querySelector("iframe") as HTMLIFrameElement | null
              if (iframe) iframe.src = iframe.src
            }}
            title="Refresh"
            className="h-6 w-6"
          >
            <RefreshCw className="size-3.5" />
          </Button>
          <Button
            variant="ghost"
            size="icon-sm"
            onClick={toggleFullscreen}
            title={isFullscreen ? "Exit fullscreen" : "Fullscreen"}
            className="h-6 w-6"
          >
            {isFullscreen ? (
              <Minimize2 className="size-3.5" />
            ) : (
              <Maximize2 className="size-3.5" />
            )}
          </Button>
        </div>
      </div>

      {/* noVNC iframe */}
      <div className="flex-1 relative">
        <iframe
          src={baseUrl}
          className="absolute inset-0 w-full h-full border-0"
          title="noVNC Remote Desktop"
          allow="fullscreen"
          sandbox="allow-same-origin allow-scripts allow-popups"
        />
      </div>
    </div>
  )
}


