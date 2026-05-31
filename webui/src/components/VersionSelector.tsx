import { useState, useMemo, useCallback } from "react"
import {
  ALL_VERSIONS,
  GROUPED_VERSIONS,
  VERSION_GROUPS,
  type ProxyType,
} from "@/lib/versions"
import { cn } from "@/lib/utils"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import { AlertTriangle } from "lucide-react"

interface VersionSelectorProps {
  selected: Set<string>
  onChange: (selected: Set<string>) => void
  proxy?: ProxyType
}

export function VersionSelector({
  selected,
  onChange,
  proxy = "none",
}: VersionSelectorProps) {
  const [search, setSearch] = useState("")
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(
    new Set(VERSION_GROUPS)
  )

  const toggleGroup = useCallback((group: string) => {
    setExpandedGroups((prev) => {
      const next = new Set(prev)
      if (next.has(group)) next.delete(group)
      else next.add(group)
      return next
    })
  }, [])

  const selectAllGroup = useCallback(
    (group: string) => {
      const versions = GROUPED_VERSIONS[group]
      const allSelected = versions.every((v) => selected.has(v.label))
      const next = new Set(selected)
      if (allSelected) {
        versions.forEach((v) => next.delete(v.label))
      } else {
        versions.forEach((v) => next.add(v.label))
      }
      onChange(next)
    },
    [selected, onChange]
  )

  const toggleVersion = useCallback(
    (label: string) => {
      const next = new Set(selected)
      if (next.has(label)) next.delete(label)
      else next.add(label)
      onChange(next)
    },
    [selected, onChange]
  )

  const selectAll = useCallback(() => {
    if (selected.size === ALL_VERSIONS.length) {
      onChange(new Set())
    } else {
      onChange(new Set(ALL_VERSIONS.map((v) => v.label)))
    }
  }, [selected, onChange])

  const clearAll = useCallback(() => onChange(new Set()), [onChange])

  const filteredGroups = useMemo(() => {
    if (!search.trim()) return VERSION_GROUPS
    const q = search.toLowerCase()
    return VERSION_GROUPS.filter((group) =>
      GROUPED_VERSIONS[group].some((v) => v.label.toLowerCase().includes(q))
    )
  }, [search])

  const totalSelected = selected.size
  const totalCount = ALL_VERSIONS.length

  return (
    <div className="flex flex-col gap-3 overflow-y-hidden">
      {/* Toolbar */}
      <div className="flex flex-wrap items-center gap-2">
        <input
          type="text"
          placeholder="Filter versions..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="flex h-7 w-full max-w-[200px] rounded-none border border-border bg-transparent px-2.5 py-1 text-xs transition-colors outline-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-1 focus-visible:ring-ring/50"
        />
        <span className="text-xs whitespace-nowrap text-muted-foreground">
          {totalSelected}/{totalCount}
        </span>
        <div className="ml-auto flex gap-1">
          <button
            type="button"
            onClick={selectAll}
            className="h-6 rounded-none border border-border bg-transparent px-2 text-[10px] text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          >
            All
          </button>
          <button
            type="button"
            onClick={clearAll}
            className="h-6 rounded-none border border-border bg-transparent px-2 text-[10px] text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          >
            Clear
          </button>
        </div>
      </div>

      {/* Version Groups */}
      <div className="flex scrollbar-thin flex-col gap-1 overflow-y-auto">
        {filteredGroups.map((group) => {
          const versions = GROUPED_VERSIONS[group]
          const groupSelected = versions.filter((v) => selected.has(v.label))
          const isExpanded = expandedGroups.has(group)
          const allInGroupSelected =
            versions.length > 0 && versions.every((v) => selected.has(v.label))

          return (
            <div key={group} className="border border-border">
              {/* Group header */}
              <button
                type="button"
                onClick={() => toggleGroup(group)}
                className={cn(
                  "flex w-full items-center gap-2 px-2.5 py-1.5 text-xs font-medium transition-colors hover:bg-muted/50",
                  isExpanded ? "bg-muted/30" : ""
                )}
              >
                <svg
                  className={cn(
                    "size-3 transition-transform",
                    isExpanded ? "rotate-90" : ""
                  )}
                  viewBox="0 0 16 16"
                  fill="currentColor"
                >
                  <path
                    d="M6 3l5 5-5 5"
                    stroke="currentColor"
                    strokeWidth="1.5"
                    fill="none"
                  />
                </svg>
                <span>{group}</span>
                <span className="ml-auto text-[10px] text-muted-foreground">
                  {groupSelected.length}/{versions.length}
                </span>
              </button>

              {/* Version chips */}
              {isExpanded && (
                <div className="flex flex-wrap gap-1 px-2 py-2">
                  {versions.map((v) => {
                    const isSelected = selected.has(v.label)
                    const hasWarning =
                      v.warning &&
                      v.warning.onlyWithProxy !== null &&
                      v.warning.onlyWithProxy === proxy
                    const hasGeneralWarning =
                      v.warning && v.warning.onlyWithProxy === null
                    const shouldShowWarning = hasWarning || hasGeneralWarning

                    const chipContent = (
                      <button
                        type="button"
                        key={v.label}
                        onClick={() => toggleVersion(v.label)}
                        className={cn(
                          "flex items-center gap-0.5 rounded-none border px-1.5 py-0.5 font-mono text-[10px] transition-all",
                          isSelected
                            ? "border-primary bg-primary text-primary-foreground"
                            : "border-border bg-transparent text-muted-foreground hover:border-border hover:bg-muted/50"
                        )}
                      >
                        {v.label}
                        {shouldShowWarning && (
                          <AlertTriangle
                            className={cn(
                              "size-2.5 shrink-0",
                              hasGeneralWarning
                                ? "text-amber-500"
                                : "text-yellow-500",
                              isSelected && "text-primary-foreground/70"
                            )}
                          />
                        )}
                      </button>
                    )

                    if (v.warning && shouldShowWarning) {
                      return (
                        <Tooltip key={v.label}>
                          <TooltipTrigger asChild>{chipContent}</TooltipTrigger>
                          <TooltipContent
                            side="bottom"
                            className="max-w-[280px]"
                          >
                            <AlertTriangle
                              className={cn(
                                "size-2.5 shrink-0",
                                hasGeneralWarning
                                  ? "text-amber-500"
                                  : "text-yellow-500"
                              )}
                            />
                            Known compatibility issue with multiplayer.
                          </TooltipContent>
                        </Tooltip>
                      )
                    }

                    return chipContent
                  })}
                </div>
              )}

              {/* Select all for group */}
              {isExpanded && (
                <div className="px-2 pb-1">
                  <button
                    type="button"
                    onClick={() => selectAllGroup(group)}
                    className="text-[10px] text-muted-foreground underline-offset-2 transition-colors hover:underline"
                  >
                    {allInGroupSelected ? "Deselect all" : "Select all"}
                  </button>
                </div>
              )}
            </div>
          )
        })}

        {filteredGroups.length === 0 && (
          <div className="py-8 text-center text-xs text-muted-foreground">
            No versions match &ldquo;{search}&rdquo;
          </div>
        )}
      </div>
    </div>
  )
}
