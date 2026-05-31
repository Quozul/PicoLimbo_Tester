import { VncViewer } from "@/components/VncViewer"

export function VncPanel() {
  return (
    <div className="flex flex-col h-full overflow-hidden">
      <VncViewer />
    </div>
  )
}
