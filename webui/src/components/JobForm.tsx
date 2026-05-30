import { useState, useCallback } from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { VersionSelector } from "@/components/VersionSelector"
import { createJob, type JobCreateInput, type JobInfo } from "@/lib/api"
import { ALL_VERSION_LABELS } from "@/lib/versions"
import { Loader2, Play } from "lucide-react"

interface JobFormProps {
  onJobCreated: (job: JobInfo) => void
}

export function JobForm({ onJobCreated }: JobFormProps) {
  const [repoUrl, setRepoUrl] = useState("https://github.com/Quozul/PicoLimbo.git")
  const [ref, setRef] = useState("master")
  const [selectedVersions, setSelectedVersions] = useState<Set<string>>(new Set())
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
          repo_url: repoUrl || undefined,
          ref: ref || undefined,
          versions,
        }

        const job = await createJob(input)
        onJobCreated(job)
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to create job")
      } finally {
        setLoading(false)
      }
    },
    [repoUrl, ref, selectedVersions, onJobCreated]
  )

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4">
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
          onChange={e => setRepoUrl(e.target.value)}
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
          onChange={e => setRef(e.target.value)}
        />
      </div>

      {/* Version Selector */}
      <div className="flex flex-col gap-1.5">
        <Label className="text-xs">
          Versions{" "}
          <span className="text-muted-foreground font-normal">
            ({selectedVersions.size} selected)
          </span>
        </Label>
        <VersionSelector
          selected={selectedVersions}
          onChange={setSelectedVersions}
        />
      </div>

      {/* Error */}
      {error && (
        <div className="rounded-none border border-destructive/50 bg-destructive/10 px-3 py-2 text-xs text-destructive">
          {error}
        </div>
      )}

      {/* Submit */}
      <Button
        type="submit"
        disabled={loading}
        className="mt-1 gap-2"
      >
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
