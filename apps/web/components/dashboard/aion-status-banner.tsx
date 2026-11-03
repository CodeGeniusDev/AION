import { BrainCircuit } from "lucide-react";
import { cn } from "@/utils/cn";

interface AionStatusBannerProps {
  connectedAgents: number;
  connectionStatus?: "connected" | "reconnecting" | "disconnected";
}

export function AionStatusBanner({ connectedAgents, connectionStatus = "connected" }: AionStatusBannerProps) {
  return (
    <div className="relative overflow-hidden rounded-[24px] bg-info-soft p-4 pt-8 sm:p-5 sm:pt-9">
      <div className="absolute left-6 right-6 top-0 h-8 rounded-b-[20px] bg-soft-blue" />
      <div className="relative flex items-center gap-4 rounded-full bg-navy px-4 py-3.5 text-white shadow-[0_8px_24px_rgba(25,36,56,0.16)] sm:px-5">
        <span className="grid size-10 shrink-0 place-items-center rounded-full bg-primary"><BrainCircuit className="size-[18px]" /></span>
        <div className="min-w-0">
          <p className="text-sm font-semibold">AION Online</p>
          <p className="text-[11px] text-white/60">{connectedAgents} agent{connectedAgents !== 1 ? "s" : ""} connected</p>
        </div>
        <span className={cn(
          "ml-auto flex items-center gap-2 rounded-full border border-white/10 bg-surface/5 px-3 py-1.5 text-[10px] text-white/75",
          connectionStatus === "connected" ? "bg-emerald-500/20" : connectionStatus === "reconnecting" ? "bg-amber-500/20" : "bg-red-500/20",
        )}>
          <span className={cn("size-1.5 rounded-full", connectionStatus === "connected" ? "bg-success-solid" : connectionStatus === "reconnecting" ? "bg-warning-solid" : "bg-danger-solid")} />
          {connectionStatus === "connected" ? "Live" : connectionStatus === "reconnecting" ? "Reconnecting" : "Disconnected"}
        </span>
      </div>
    </div>
  );
}
