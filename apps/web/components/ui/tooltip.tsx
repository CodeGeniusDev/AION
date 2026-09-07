"use client";

import { useState, useRef, type ReactNode } from "react";
import { cn } from "@/utils/cn";

interface TooltipProps {
  content: string;
  children: ReactNode;
  className?: string;
  position?: "top" | "bottom";
}

/**
 * Lightweight CSS tooltip — no external deps.
 * Wraps a single child element and shows a tooltip on hover/focus.
 */
export function Tooltip({ content, children, className, position = "top" }: TooltipProps) {
  const [visible, setVisible] = useState(false);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  function show() {
    if (timeoutRef.current) clearTimeout(timeoutRef.current);
    setVisible(true);
  }

  function hide() {
    timeoutRef.current = setTimeout(() => setVisible(false), 100);
  }

  return (
    <span
      className={cn("relative inline-flex", className)}
      onMouseEnter={show}
      onMouseLeave={hide}
      onFocus={show}
      onBlur={hide}
    >
      {children}
      {visible && (
        <span
          role="tooltip"
          className={cn(
            "pointer-events-none absolute left-1/2 z-50 -translate-x-1/2 whitespace-nowrap rounded-lg bg-navy px-3 py-1.5 text-[11px] font-medium text-white shadow-lg",
            position === "top" ? "bottom-full mb-2" : "top-full mt-2",
          )}
        >
          {content}
          <span
            className={cn(
              "absolute left-1/2 -translate-x-1/2 border-4 border-transparent",
              position === "top"
                ? "top-full border-t-navy"
                : "bottom-full border-b-navy",
            )}
          />
        </span>
      )}
    </span>
  );
}
