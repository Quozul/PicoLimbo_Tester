import {
  Loader2,
  Clock,
  CheckCircle2,
  XCircle,
  AlertTriangle,
} from "lucide-react"

export function getStatusIcon(status: string) {
  switch (status) {
    case "queued":
    case "building":
    case "testing":
      return <Loader2 className="size-3 animate-spin text-muted-foreground" />
    case "finished":
      return <CheckCircle2 className="size-3 text-green-500" />
    case "failed":
      return <AlertTriangle className="size-3 text-destructive" />
    default:
      return <Clock className="size-3 text-muted-foreground" />
  }
}

export function getStatusColor(status: string): string {
  switch (status) {
    case "queued":
    case "building":
    case "testing":
      return "text-muted-foreground"
    case "finished":
      return "text-green-500"
    case "failed":
      return "text-destructive"
    default:
      return "text-muted-foreground"
  }
}

export function formatTimeAgo(timestamp: string): string {
  const now = Date.now()
  const then = new Date(timestamp).getTime()
  const diff = now - then
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return "just now"
  if (mins < 60) return `${mins}m ago`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  return `${days}d ago`
}
