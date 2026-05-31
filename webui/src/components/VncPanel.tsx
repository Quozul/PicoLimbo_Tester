import { VncViewer } from "@/components/VncViewer"

export function VncPanel() {
  return (
    <div className="flex flex-col h-full overflow-hidden">
      <div className="flex items-center gap-2 px-4 py-3 border-b border-border flex-shrink-0">
        <h2 className="text-xs font-medium">Live VNC Viewer</h2>
      </div>
      <div className="flex-1 overflow-hidden">
        <VncViewer />
      </div>
    </div>
  )
}
