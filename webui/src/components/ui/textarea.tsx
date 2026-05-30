import * as React from "react"

import { cn } from "@/lib/utils"

function Textarea({ className, ...props }: React.ComponentProps<"textarea">) {
  return (
    <textarea
      data-slot="textarea"
      className={cn(
        "flex min-h-[60px] w-full resize-none rounded-none border border-border bg-transparent px-3 py-2 text-xs placeholder:text-muted-foreground focus-visible:border-ring focus-visible:outline-1 focus-visible:outline-ring disabled:cursor-not-allowed disabled:opacity-50",
        className
      )}
      {...props}
    />
  )
}

export { Textarea }
