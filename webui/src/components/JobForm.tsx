import { useState, useCallback } from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { VersionSelector } from "@/components/VersionSelector"
import { VelocityConfigDialog } from "@/components/VelocityConfigDialog"
import {
  createJob,
  type JobCreateInput,
  type JobInfo,
  ProxyOptions,
} from "@/lib/api"
import { ALL_VERSION_LABELS } from "@/lib/versions"
import { Loader2, Play, Server, Settings2 } from "lucide-react"

interface JobFormProps {
  onJobCreated: (job: JobInfo) => void
}

export function JobForm({ onJobCreated }: JobFormProps) {
  const [repoUrl, setRepoUrl] = useState(
    "https://github.com/Quozul/PicoLimbo.git"
  )
  const [ref, setRef] = useState("master")
  const [proxy, setProxy] = useState("none")
  const [forwardingMethod, setForwardingMethod] = useState("modern")
  const [forwardingSecret, setForwardingSecret] = useState("sup3r-s3cr3t")
  const [showConfigDialog, setShowConfigDialog] = useState(false)
  const [selectedVersions, setSelectedVersions] = useState<Set<string>>(
    new Set()
  )
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleSubmit = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault()
      setLoading(true)
      setError(null)

      try {
        const versions =
          selectedVersions.size === ALL_VERSION_LABELS.length
            ? null
            : selectedVersions.size > 0
              ? Array.from(selectedVersions)
              : null

        const input: JobCreateInput = {
          repo_url: repoUrl || "https://github.com/Quozul/PicoLimbo.git",
          ref: ref || "master",
          versions,
          proxy,
          forwarding_method: forwardingMethod,
          forwarding_secret: forwardingSecret,
        }

        const job = await createJob(input)
        onJobCreated(job)
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to create job")
      } finally {
        setLoading(false)
      }
    },
    [repoUrl, ref, proxy, forwardingMethod, forwardingSecret, selectedVersions, onJobCreated]
  )

  return (
    <form
      onSubmit={handleSubmit}
      className="flex h-full flex-col gap-4 overflow-hidden"
    >
      {/* Repo URL */}
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="repo-url" className="text-xs">
          Repository URL
        </Label>
        <Input
          id="repo-url"
          type="url"
          placeholder="https://github.com/Quozul/PicoLimbo.git"
          value={repoUrl}
          onChange={(e) => setRepoUrl(e.target.value)}
        />
      </div>

      {/* Ref */}
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="ref" className="text-xs">
          Branch / Commit
        </Label>
        <Input
          id="ref"
          placeholder="master"
          value={ref}
          onChange={(e) => setRef(e.target.value)}
        />
      </div>

      {/* Proxy */}
      <div className="flex flex-col gap-1.5">
        <Label className="text-xs">
          <span className="inline-flex items-center gap-1">
            <Server className="size-3" />
            Proxy
          </span>
        </Label>
        <Select value={proxy} onValueChange={setProxy}>
          <SelectTrigger className="w-full">
            <SelectValue placeholder="None" />
          </SelectTrigger>
          <SelectContent>
            {ProxyOptions.map((option) => (
              <SelectItem key={option.value} value={option.value}>
                {option.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {/* Velocity Config Button (only visible when Velocity is selected) */}
      {proxy === "velocity" && (
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="w-full gap-2 text-xs"
          onClick={() => setShowConfigDialog(true)}
        >
          <Settings2 className="size-3" />
          Configure Velocity Forwarding
        </Button>
      )}

      {/* Velocity Config Dialog */}
      <VelocityConfigDialog
        open={showConfigDialog}
        onOpenChange={setShowConfigDialog}
        forwardingMethod={forwardingMethod}
        onForwardingMethodChange={setForwardingMethod}
        forwardingSecret={forwardingSecret}
        onForwardingSecretChange={setForwardingSecret}
      />

      {/* Version Selector */}
      <div className="flex grow flex-col gap-1.5 overflow-y-hidden">
        <Label className="text-xs">
          Versions{" "}
          <span className="font-normal text-muted-foreground">
            ({selectedVersions.size} selected)
          </span>
        </Label>
        <VersionSelector
          selected={selectedVersions}
          onChange={setSelectedVersions}
          proxy={proxy as "none" | "velocity" | "bungeecord"}
        />
      </div>

      {/* Error */}
      {error && (
        <div className="rounded-none border border-destructive/50 bg-destructive/10 px-3 py-2 text-xs text-destructive">
          {error}
        </div>
      )}

      {/* Submit */}
      <Button type="submit" disabled={loading} className="mt-1 gap-2">
        {loading ? (
          <>
            <Loader2 className="size-3.5 animate-spin" />
            Creating Job...
          </>
        ) : (
          <>
            <Play className="size-3.5" />
            Start Job
          </>
        )}
      </Button>
    </form>
  )
}
