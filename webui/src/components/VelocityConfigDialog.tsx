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
import { Input } from "@/components/ui/input"
import { AlertTriangle } from "lucide-react"

interface VelocityConfigDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  forwardingMethod: string
  onForwardingMethodChange: (method: string) => void
  forwardingSecret: string
  onForwardingSecretChange: (secret: string) => void
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

export function VelocityConfigDialog({
  open,
  onOpenChange,
  forwardingMethod,
  onForwardingMethodChange,
  forwardingSecret,
  onForwardingSecretChange,
}: VelocityConfigDialogProps) {
  const needsSecret = forwardingMethod === "bungeeguard" || forwardingMethod === "modern"
  const selectedMethod = FORWARDING_METHODS.find(
    (m) => m.value === forwardingMethod
  )

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
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

          {/* Forwarding Secret */}
          {needsSecret && (
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="forwarding-secret">
                Forwarding secret{" "}
                <span className="text-muted-foreground">(required)</span>
              </Label>
              <Input
                id="forwarding-secret"
                type="text"
                value={forwardingSecret}
                onChange={(e) => onForwardingSecretChange(e.target.value)}
                placeholder="Enter forwarding secret"
              />
              <p className="text-xs text-muted-foreground">
                A forwarding secret is required for this forwarding method.
              </p>
            </div>
          )}
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
    </Dialog>
  )
}
