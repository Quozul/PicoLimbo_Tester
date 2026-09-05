import { useEffect, useState } from "react"
import { Label } from "@/components/ui/label"
import { Input } from "@/components/ui/input"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
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
  uploadSchematic,
  listSchematics,
  deleteSchematic,
} from "@/lib/api"

interface SchematicConfigDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  selectedSchematic: string | null
  onSelectedSchematicChange: (name: string | null) => void
  viewDistance: number
  onViewDistanceChange: (distance: number) => void
}

const VIEW_DISTANCE_MIN = 1
const VIEW_DISTANCE_MAX = 32

type SchematicStatus = "uploading" | "ready" | "error"

export function SchematicConfigDialog({
  open,
  onOpenChange,
  selectedSchematic,
  onSelectedSchematicChange,
  viewDistance,
  onViewDistanceChange,
}: SchematicConfigDialogProps) {
  const [schematicList, setSchematicList] = useState<
    Array<{ name: string; status: SchematicStatus }>
  >([])
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [uploadingName, setUploadingName] = useState<string | null>(null)
  const [deletingName, setDeletingName] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  // Load schematic list when dialog opens
  useEffect(() => {
    if (!open) return
    let cancelled = false
    listSchematics()
      .then((schematics) => {
        if (cancelled) return
        setSchematicList(
          schematics.map((s) => ({ ...s, status: "ready" as SchematicStatus }))
        )
      })
      .catch(() => {
        // Silently ignore errors loading schematics
      })
    return () => {
      cancelled = true
    }
  }, [open])

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
    setSchematicList((prev) => [
      ...prev,
      { name: fileName, status: "uploading" },
    ])
    setUploadingName(fileName)

    try {
      const result = await uploadSchematic(selectedFile)
      setSchematicList((prev) =>
        prev.filter((p) => p.name !== fileName)
      )
      setSchematicList((prev) => [
        ...prev,
        { name: result.name, status: "ready" },
      ])
      setSelectedFile(null)
      // Auto-select the newly uploaded schematic
      onSelectedSchematicChange(result.name)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed")
      setSchematicList((prev) =>
        prev.map((p) =>
          p.name === fileName ? { ...p, status: "error" } : p
        )
      )
    } finally {
      setUploadingName(null)
    }
  }

  const handleDeleteSchematic = async (name: string) => {
    setDeletingName(name)
    try {
      await deleteSchematic(name)
      setSchematicList((prev) => prev.filter((p) => p.name !== name))
      if (selectedSchematic === name) {
        onSelectedSchematicChange(null)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed")
    } finally {
      setDeletingName(null)
    }
  }

  const handleToggleSchematic = (name: string) => {
    // Clicking the selected schematic deselects it (disables loading)
    onSelectedSchematicChange(selectedSchematic === name ? null : name)
  }

  const handleViewDistanceChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = Number(e.target.value)
    if (Number.isNaN(value)) return
    onViewDistanceChange(
      Math.min(VIEW_DISTANCE_MAX, Math.max(VIEW_DISTANCE_MIN, value))
    )
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[420px]">
        <DialogHeader>
          <DialogTitle>World Schematic</DialogTitle>
          <DialogDescription>
            Load a custom structure (.schem) at the spawn location and set
            how many chunks are sent to clients.
          </DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-4 py-2">
          {/* Schematic Upload Section */}
          <div className="flex flex-col gap-2">
            <Label>Schematic file</Label>

            {/* File upload */}
            <div className="flex items-center gap-2">
              <label
                htmlFor="schematic-file"
                className="inline-flex h-8 items-center justify-center rounded-none border border-border bg-transparent px-3 text-xs transition-colors hover:bg-muted cursor-pointer"
              >
                <Upload className="size-3 mr-1" />
                Choose .schem file
              </label>
              <input
                id="schematic-file"
                type="file"
                accept=".schem"
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

            {/* Schematic list */}
            {schematicList.length > 0 && (
              <div className="flex flex-col gap-1 max-h-32 overflow-y-auto">
                {schematicList.map((schematic) => (
                  <div
                    key={schematic.name}
                    className={`flex items-center justify-between rounded-none border px-3 py-1.5 text-xs transition-colors ${
                      selectedSchematic === schematic.name
                        ? "border-primary bg-primary/10"
                        : "border-border bg-background hover:bg-muted"
                    }`}
                  >
                    <button
                      type="button"
                      className="flex flex-1 items-center gap-2 truncate text-left"
                      onClick={() => handleToggleSchematic(schematic.name)}
                    >
                      {schematic.status === "uploading" && (
                        <Loader2 className="size-3 shrink-0 animate-spin text-muted-foreground" />
                      )}
                      {schematic.status === "ready" && (
                        <CheckCircle2 className="size-3 shrink-0 text-green-600" />
                      )}
                      {schematic.status === "error" && (
                        <XCircle className="size-3 shrink-0 text-destructive" />
                      )}
                      {selectedSchematic === schematic.name && (
                        <Check className="size-3 shrink-0 text-primary" />
                      )}
                      <span className="truncate">
                        {schematic.name}
                      </span>
                      {schematic.status === "uploading" && (
                        <span className="text-muted-foreground shrink-0">
                          uploading
                        </span>
                      )}
                      {schematic.status === "error" && (
                        <span className="text-destructive shrink-0">
                          error
                        </span>
                      )}
                    </button>
                    {schematic.status !== "uploading" && (
                      <Button
                        type="button"
                        variant="ghost"
                        size="icon-xs"
                        className="size-6 shrink-0"
                        onClick={() => setDeletingName(schematic.name)}
                        disabled={deletingName === schematic.name}
                      >
                        {deletingName === schematic.name ? (
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

            {/* Selection hint */}
            {schematicList.length > 0 ? (
              <p className="text-xs text-muted-foreground">
                {selectedSchematic
                  ? `Loading ${selectedSchematic} at spawn.`
                  : "No schematic selected — schematic loading is disabled."}
              </p>
            ) : (
              <p className="text-xs text-muted-foreground">
                No schematics uploaded yet. Schematic loading is disabled.
              </p>
            )}
          </div>

          {/* View Distance */}
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="view-distance">View distance (chunks)</Label>
            <Input
              id="view-distance"
              type="number"
              min={VIEW_DISTANCE_MIN}
              max={VIEW_DISTANCE_MAX}
              value={viewDistance}
              onChange={handleViewDistanceChange}
            />
            <p className="text-xs text-muted-foreground">
              Should match or exceed the schematic's size in chunks.
            </p>
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
      <AlertDialog open={deletingName !== null} onOpenChange={(openState) => !openState && setDeletingName(null)}>
        <AlertDialogContent size="sm">
          <AlertDialogHeader>
            <AlertDialogTitle>Delete Schematic</AlertDialogTitle>
            <AlertDialogDescription>
              Are you sure you want to delete{" "}
              <strong>{deletingName}</strong>? This action cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              variant="destructive"
              onClick={() => deletingName && handleDeleteSchematic(deletingName)}
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
