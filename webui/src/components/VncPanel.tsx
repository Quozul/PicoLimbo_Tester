import { VncViewer } from "@/components/VncViewer"

export function VncPanel() {
  return (
    <div className="flex h-full flex-col overflow-hidden">
      <VncViewer />
    </div>
  )
}
