"use client";

import {
  useEffect,
  useRef,
  useState,
  type ReactNode,
  type RefObject,
} from "react";
import { cn } from "@/utils/cn";

/**
 * Closes an overlay on outside pointer-down or Escape. Shared by the dropdown
 * and the global-search panel so the dismiss behavior stays consistent.
 */
export function useDismiss<T extends HTMLElement>(
  active: boolean,
  onClose: () => void,
): RefObject<T | null> {
  const ref = useRef<T>(null);

  useEffect(() => {
    if (!active) return;
    function onPointerDown(event: PointerEvent) {
      if (ref.current && !ref.current.contains(event.target as Node)) onClose();
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [active, onClose]);

  return ref;
}

interface DropdownProps {
  /** Renders the trigger; receives open state and a toggle callback. */
  trigger: (state: { open: boolean; toggle: () => void }) => ReactNode;
  /** Renders the panel; receives a close callback for menu actions. */
  children: (state: { close: () => void }) => ReactNode;
  align?: "start" | "end";
  /** Accessible name for the opened panel region. */
  label: string;
  className?: string;
  panelClassName?: string;
}

/**
 * Lightweight, dependency-free dropdown/popover. Handles open state,
 * outside-click + Escape dismissal, and ARIA — used by the notifications
 * center and the profile menu without pulling in a Radix popover.
 */
export function Dropdown({
  trigger,
  children,
  align = "end",
  label,
  className,
  panelClassName,
}: DropdownProps) {
  const [open, setOpen] = useState(false);
  const ref = useDismiss<HTMLDivElement>(open, () => setOpen(false));

  return (
    <div ref={ref} className={cn("relative", className)}>
      {trigger({ open, toggle: () => setOpen((value) => !value) })}
      {open && (
        <div
          role="dialog"
          aria-label={label}
          className={cn(
            "absolute top-full z-50 mt-2 min-w-[16rem] overflow-hidden rounded-2xl border bg-surface text-foreground shadow-[0_18px_50px_rgba(15,25,45,0.18)]",
            align === "end" ? "right-0" : "left-0",
            panelClassName,
          )}>
          {children({ close: () => setOpen(false) })}
        </div>
      )}
    </div>
  );
}
