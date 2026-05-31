import { useEffect, useState } from "react"
import { Label } from "@/components/ui/label"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog"
import { Button } from "@/components/ui/button"
import {
  Loader2,
  Trash2,
  Upload,
  CheckCircle2,
  XCircle,
  Check,
} from "lucide-react"
import {
  uploadPlugin,
  listPlugins,
  deletePlugin,
} from "@/lib/api"

interface VelocityConfigDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  forwardingMethod: string
  onForwardingMethodChange: (method: string) => void
  selectedPlugins?: string[]
  onSelectedPluginsChange?: (pluginNames: string[]) => void
}

const FORWARDING_METHODS = [
  {
    value: "none",
    label: "None",
    description:
      "No forwarding will be done. All players will appear to be connecting from the proxy and will have offline-mode UUIDs.",
  },
  {
    value: "legacy",
    label: "Legacy (BungeeCord)",
    description:
      "Forward player IPs and UUIDs in a BungeeCord-compatible format. Use this if you run servers using Minecraft 1.12 or lower.",
  },
  {
    value: "bungeeguard",
    label: "BungeeGuard",
    description:
      "Forward player IPs and UUIDs in a format supported by the BungeeGuard plugin. Use this if you run servers using Minecraft 1.12 or lower, and are unable to implement network level firewalling (on a shared host).",
  },
  {
    value: "modern",
    label: "Modern",
    description:
      "Forward player IPs and UUIDs as part of the login process using Velocity's native forwarding. Only applicable for Minecraft 1.13 or higher.",
  },
] as const

type PluginStatus = "uploading" | "ready" | "error"

export function VelocityConfigDialog({
  open,
  onOpenChange,
  forwardingMethod,
  onForwardingMethodChange,
  selectedPlugins = [],
  onSelectedPluginsChange,
}: VelocityConfigDialogProps) {
  const selectedMethod = FORWARDING_METHODS.find(
    (m) => m.value === forwardingMethod
  )

  // Plugin state
  const [pluginList, setPluginList] = useState<
    Array<{ name: string; status: PluginStatus }>
  >([])
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [uploadingName, setUploadingName] = useState<string | null>(null)
  const [deletingName, setDeletingName] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  // Load plugin list when dialog opens
  useEffect(() => {
    if (open) {
      loadPlugins()
    }
  }, [open])

  const loadPlugins = async () => {
    try {
      const plugins = await listPlugins()
      setPluginList(plugins.map((p) => ({ ...p, status: "ready" as PluginStatus })))
    } catch {
      // Silently ignore errors loading plugins
    }
  }

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files
    if (files && files.length > 0) {
      setSelectedFile(files[0])
      setError(null)
    }
  }

  const handleUpload = async () => {
    if (!selectedFile) return

    const fileName = selectedFile.name
    // Add to list with "uploading" status
    setPluginList((prev) => [...prev, { name: fileName, status: "uploading" }])
    setUploadingName(fileName)

    try {
      const result = await uploadPlugin(selectedFile)
      // Remove the uploading entry and add the real one
      setPluginList((prev) =>
        prev.filter((p) => p.name !== fileName)
      )
      setPluginList((prev) => [
        ...prev,
        { name: result.name, status: "ready" },
      ])
      setSelectedFile(null)
      // Auto-select the newly uploaded plugin
      const updated = [...selectedPlugins, result.name]
      onSelectedPluginsChange?.(updated)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed")
      // Mark as error instead of removing
      setPluginList((prev) =>
        prev.map((p) =>
          p.name === fileName ? { ...p, status: "error" } : p
        )
      )
    } finally {
      setUploadingName(null)
    }
  }

  const handleDeletePlugin = async (name: string) => {
    setDeletingName(name)
    try {
      await deletePlugin(name)
      setPluginList((prev) => prev.filter((p) => p.name !== name))
      // Remove from selection if selected
      const updated = selectedPlugins.filter((p) => p !== name)
      onSelectedPluginsChange?.(updated)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed")
    } finally {
      setDeletingName(null)
    }
  }

  const handleTogglePlugin = (name: string) => {
    const isSelected = selectedPlugins.includes(name)
    const updated = isSelected
      ? selectedPlugins.filter((p) => p !== name)
      : [...selectedPlugins, name]
    onSelectedPluginsChange?.(updated)
  }

  const isSelected = (name: string) => selectedPlugins.includes(name)

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[420px]">
        <DialogHeader>
          <DialogTitle>Velocity Forwarding Configuration</DialogTitle>
          <DialogDescription>
            Configure how Velocity forwards player information to PicoLimbo.
          </DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-4 py-2">
          {/* Forwarding Method */}
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="forwarding-method">Forwarding method</Label>
            <Select
              value={forwardingMethod}
              onValueChange={onForwardingMethodChange}
            >
              <SelectTrigger className="w-full">
                <SelectValue placeholder="Select forwarding method" />
              </SelectTrigger>
              <SelectContent>
                {FORWARDING_METHODS.map((method) => (
                  <SelectItem key={method.value} value={method.value}>
                    {method.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {selectedMethod && (
              <p className="text-xs text-muted-foreground">
                {selectedMethod.description}
              </p>
            )}
          </div>



          {/* Plugin Upload Section */}
          <div className="flex flex-col gap-2">
            <Label>Velocity Plugins ({selectedPlugins.length} selected)</Label>

            {/* File upload */}
            <div className="flex items-center gap-2">
              <label
                htmlFor="plugin-file"
                className="inline-flex h-8 items-center justify-center rounded-none border border-border bg-transparent px-3 text-xs transition-colors hover:bg-muted cursor-pointer"
              >
                <Upload className="size-3 mr-1" />
                Choose .jar file
              </label>
              <input
                id="plugin-file"
                type="file"
                accept=".jar"
                className="hidden"
                onChange={handleFileSelect}
              />
              {selectedFile && (
                <span className="text-xs text-muted-foreground truncate">
                  {selectedFile.name}
                </span>
              )}
              {selectedFile && (
                <Button
                  type="button"
                  variant="secondary"
                  size="xs"
                  onClick={handleUpload}
                  disabled={!selectedFile}
                  className="gap-1"
                >
                  {uploadingName === selectedFile.name ? (
                    <Loader2 className="size-3 animate-spin" />
                  ) : (
                    <Upload className="size-3" />
                  )}
                  Upload
                </Button>
              )}
            </div>

            {/* Error message */}
            {error && (
              <div className="flex items-center gap-1.5 rounded-none border border-destructive/50 bg-destructive/10 px-3 py-1.5 text-xs text-destructive">
                <XCircle className="size-3 shrink-0" />
                {error}
              </div>
            )}

            {/* Plugin list */}
            {pluginList.length > 0 && (
              <div className="flex flex-col gap-1 max-h-32 overflow-y-auto">
                {pluginList.map((plugin) => (
                  <div
                    key={plugin.name}
                    className={`flex items-center justify-between rounded-none border px-3 py-1.5 text-xs transition-colors ${
                      isSelected(plugin.name)
                        ? "border-primary bg-primary/10"
                        : "border-border bg-background hover:bg-muted"
                    }`}
                  >
                    <button
                      type="button"
                      className="flex flex-1 items-center gap-2 truncate text-left"
                      onClick={() => handleTogglePlugin(plugin.name)}
                    >
                      {plugin.status === "uploading" && (
                        <Loader2 className="size-3 shrink-0 animate-spin text-muted-foreground" />
                      )}
                      {plugin.status === "ready" && (
                        <CheckCircle2 className="size-3 shrink-0 text-green-600" />
                      )}
                      {plugin.status === "error" && (
                        <XCircle className="size-3 shrink-0 text-destructive" />
                      )}
                      {isSelected(plugin.name) && (
                        <Check className="size-3 shrink-0 text-primary" />
                      )}
                      <span className="truncate">
                        {plugin.name}
                      </span>
                      {plugin.status === "uploading" && (
                        <span className="text-muted-foreground shrink-0">
                          uploading
                        </span>
                      )}
                      {plugin.status === "error" && (
                        <span className="text-destructive shrink-0">
                          error
                        </span>
                      )}
                    </button>
                    {plugin.status !== "uploading" && (
                      <Button
                        type="button"
                        variant="ghost"
                        size="icon-xs"
                        className="size-6 shrink-0"
                        onClick={() => setDeletingName(plugin.name)}
                        disabled={deletingName === plugin.name}
                      >
                        {deletingName === plugin.name ? (
                          <Loader2 className="size-3 animate-spin" />
                        ) : (
                          <Trash2 className="size-3 text-destructive" />
                        )}
                      </Button>
                    )}
                  </div>
                ))}
              </div>
            )}

            {/* Multi-select hint */}
            {pluginList.length > 0 && (
              <p className="text-xs text-muted-foreground">
                Click plugins to select them for this job. {selectedPlugins.length} selected.
              </p>
            )}
          </div>
        </div>

        <DialogFooter>
          <button
            type="button"
            onClick={() => onOpenChange(false)}
            className="inline-flex h-8 items-center justify-center rounded-none border border-border bg-transparent px-4 text-xs transition-colors hover:bg-muted"
          >
            Close
          </button>
        </DialogFooter>
      </DialogContent>

      {/* Delete Confirmation Dialog */}
      <AlertDialog open={deletingName !== null} onOpenChange={(open) => !open && setDeletingName(null)}>
        <AlertDialogContent size="sm">
          <AlertDialogHeader>
            <AlertDialogTitle>Delete Plugin</AlertDialogTitle>
            <AlertDialogDescription>
              Are you sure you want to delete{" "}
              <strong>{deletingName}</strong>? This action cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              variant="destructive"
              onClick={() => deletingName && handleDeletePlugin(deletingName)}
              disabled={deletingName === null}
            >
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Dialog>
  )
}
