import { cn } from "@/utils/cn";

export function LoadingSkeleton({ className }: { className?: string }) {
  return <div className={cn("animate-pulse rounded-2xl bg-[#e9edf2]", className)} aria-hidden="true" />;
}

