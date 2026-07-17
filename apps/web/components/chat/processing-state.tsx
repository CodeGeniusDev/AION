"use client";

import { useEffect, useState } from "react";
import { Bot, Check, Circle } from "lucide-react";
import type { AgentId, ChatMode } from "@/types";

const names: Record<AgentId, string> = { planner: "Planner Agent", researcher: "Research Agent", critic: "Critic Agent", memory: "Memory Agent" };

export function ProcessingState({ mode, selectedAgents }: { mode: ChatMode; selectedAgents: AgentId[] }) {
  const [stage, setStage] = useState(0);
  useEffect(() => {
    const timer = window.setInterval(() => setStage((value) => Math.min(value + 1, 2)), 900);
    return () => window.clearInterval(timer);
  }, []);
  const agents = mode === "research" ? (["planner", "researcher", "critic"] as AgentId[]) : mode === "manual" ? selectedAgents : [];
  return <div className="flex gap-3"><span className="grid size-9 shrink-0 place-items-center rounded-full bg-primary text-white"><Bot className="size-4" /></span><div className="min-w-[240px] rounded-[20px] rounded-tl-md bg-[#f0f4fa] p-4"><p className="text-xs font-semibold">AION is working...</p><p className="mt-1 text-[9px] uppercase tracking-[0.12em] text-muted-text">Staged progress preview</p><div className="mt-3 space-y-2 text-[11px]"><div className="flex items-center gap-2"><Check className="size-3.5 text-[#2b9b68]" />Selecting agents</div>{agents.length ? agents.slice(0, 3).map((agent, index) => <div key={agent} className="flex items-center gap-2">{stage > index ? <Check className="size-3.5 text-[#2b9b68]" /> : <Circle className={`size-3.5 ${stage === index ? "fill-primary text-primary" : "text-[#adb4be]"}`} />}<span className={stage === index ? "font-medium" : "text-muted-text"}>{names[agent]} {stage === index ? "is working" : stage > index ? "completed" : "is waiting"}</span></div>) : <div className="flex items-center gap-2"><Circle className="size-3.5 fill-primary text-primary" /><span>Coordinating the selected workflow</span></div>}</div></div></div>;
}

