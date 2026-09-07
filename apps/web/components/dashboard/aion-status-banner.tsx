import { BrainCircuit } from "lucide-react";

export function AionStatusBanner({ connectedAgents }: { connectedAgents: number }) {
  return (
    <div className="relative overflow-hidden rounded-[24px] bg-[#e9eff8] p-4 pt-8 sm:p-5 sm:pt-9">
      <div className="absolute left-6 right-6 top-0 h-8 rounded-b-[20px] bg-[#dce6f4]" />
      <div className="relative flex items-center gap-4 rounded-full bg-navy px-4 py-3.5 text-white shadow-[0_8px_24px_rgba(25,36,56,0.16)] sm:px-5">
        <span className="grid size-10 shrink-0 place-items-center rounded-full bg-primary"><BrainCircuit className="size-[18px]" /></span>
        <div className="min-w-0">
          <p className="text-sm font-semibold">AION Online</p>
          <p className="text-[11px] text-white/60">{connectedAgents} agent{connectedAgents !== 1 ? "s" : ""} connected</p>
        </div>
        <span className="ml-auto flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-3 py-1.5 text-[10px] text-white/75"><span className="size-1.5 rounded-full bg-[#51d597]" />Live</span>
      </div>
    </div>
  );
}
