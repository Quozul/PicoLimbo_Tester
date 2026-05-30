import * as React from "react"

import { cn } from "@/lib/utils"

function Input({ className, type, ...props }: React.ComponentProps<"input">) {
  return (
    <input
      type={type}
      data-slot="input"
      className={cn(
        "flex h-8 w-full min-w-0 rounded-none border border-border bg-transparent px-3 py-1 text-xs shadow-none transition-[color,box-shadow] outline-none file:inline-flex file:h-7 file:border-0 file:bg-transparent file:text-xs file:font-medium placeholder:text-muted-foreground disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50 data-invalid:border-destructive data-invalid:ring-destructive/20 dark:data-invalid:ring-destructive/40 aria-invalid:ring-destructive/20 dark:aria-invalid:ring-destructive/40",
        "focus-visible:border-ring focus-visible:ring-1 focus-visible:ring-ring/50",
        "border-input placeholder:text-muted-foreground",
        "aria-invalid:border-destructive aria-invalid:ring-1 aria-invalid:ring-destructive/20",
        className
      )}
      {...props}
    />
  )
}

export { Input }
