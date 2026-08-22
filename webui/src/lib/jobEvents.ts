import { JobInfoSchema, type JobInfo } from "@/lib/api"

export type JobUpdateHandler = (job: JobInfo) => void
export type JobSnapshotHandler = (jobs: JobInfo[]) => void

type JobEventMessage =
  | { type: "snapshot"; jobs: unknown[] }
  | { type: "job_update"; job: unknown }

const API_BASE: string = import.meta.env.VITE_API_URL || ""

const INITIAL_RECONNECT_DELAY_MS = 1000
const MAX_RECONNECT_DELAY_MS = 30000

function buildSocketUrl(): string {
  const base = API_BASE
    ? new URL(API_BASE, window.location.origin)
    : new URL(window.location.origin)
  const protocol = base.protocol === "https:" ? "wss:" : "ws:"
  return `${protocol}//${base.host}/ws/jobs`
}

let socket: WebSocket | null = null
let reconnectTimer: number | undefined
let reconnectDelayMs = INITIAL_RECONNECT_DELAY_MS
const updateHandlers = new Set<JobUpdateHandler>()
const snapshotHandlers = new Set<JobSnapshotHandler>()

function dispatch(message: JobEventMessage): void {
  if (message.type === "snapshot") {
    const jobs = message.jobs.flatMap((job) => {
      const parsed = JobInfoSchema.safeParse(job)
      return parsed.success ? [parsed.data] : []
    })
    snapshotHandlers.forEach((handler) => handler(jobs))
  } else if (message.type === "job_update") {
    const parsed = JobInfoSchema.safeParse(message.job)
    if (parsed.success) {
      updateHandlers.forEach((handler) => handler(parsed.data))
    }
  }
}

function handleSocketMessage(event: MessageEvent): void {
  try {
    dispatch(JSON.parse(String(event.data)) as JobEventMessage)
  } catch {
    // Ignore malformed messages
  }
}

function hasSubscribers(): boolean {
  return updateHandlers.size > 0 || snapshotHandlers.size > 0
}

function connect(): void {
  if (
    socket !== null &&
    (socket.readyState === WebSocket.OPEN ||
      socket.readyState === WebSocket.CONNECTING)
  ) {
    return
  }
  const ws = new WebSocket(buildSocketUrl())
  socket = ws
  ws.onopen = () => {
    reconnectDelayMs = INITIAL_RECONNECT_DELAY_MS
  }
  ws.onmessage = handleSocketMessage
  ws.onclose = () => {
    if (socket !== ws) {
      return
    }
    socket = null
    if (hasSubscribers()) {
      reconnectTimer = window.setTimeout(connect, reconnectDelayMs)
      reconnectDelayMs = Math.min(
        reconnectDelayMs * 2,
        MAX_RECONNECT_DELAY_MS
      )
    }
  }
}

function disconnect(): void {
  window.clearTimeout(reconnectTimer)
  reconnectTimer = undefined
  if (socket !== null) {
    // Suppress the close handler so we don't schedule a reconnect
    socket.onclose = null
    socket.close()
    socket = null
  }
}

function maybeDisconnect(): void {
  if (!hasSubscribers()) {
    disconnect()
  }
}

/**
 * Subscribe to pushed job updates (all jobs).
 * Returns an unsubscribe function.
 */
export function onJobUpdate(handler: JobUpdateHandler): () => void {
  updateHandlers.add(handler)
  connect()
  return () => {
    updateHandlers.delete(handler)
    maybeDisconnect()
  }
}

/**
 * Subscribe to snapshot messages (full job list, sent on connect).
 * Returns an unsubscribe function.
 */
export function onJobSnapshot(handler: JobSnapshotHandler): () => void {
  snapshotHandlers.add(handler)
  connect()
  return () => {
    snapshotHandlers.delete(handler)
    maybeDisconnect()
  }
}
