"use client";

import { useEffect, useRef, useState } from "react";
import { Bot, Check, Circle } from "lucide-react";
import type { AgentId, ChatMode } from "@/types";
import { API_URL } from "@/services/api";

const names: Record<AgentId, string> = {
  planner: "Planner Agent",
  researcher: "Research Agent",
  critic: "Critic Agent",
  memory: "Memory Agent",
};

interface BusEvent {
  type: "agent_event" | "connected" | "done";
  source_agent?: string;
  target_agent?: string | null;
  intent?: string;
  content?: string;
  status?: string;
  task_id?: string;
}

interface AgentStep {
  agent: string;
  label: string;
  status: "waiting" | "working" | "completed";
}

export function ProcessingState({
  mode,
  selectedAgents,
  taskId,
  onTaskId,
}: {
  mode: ChatMode;
  selectedAgents: AgentId[];
  taskId: string | null;
  onTaskId?: (id: string) => void;
}) {
  const [steps, setSteps] = useState<AgentStep[]>([]);
  const [log, setLog] = useState<string[]>([]);
  const [connected, setConnected] = useState(false);
  const [done, setDone] = useState(false);
  const esRef = useRef<EventSource | null>(null);

  // Determine expected agents
  const expectedAgents: AgentId[] =
    mode === "research"
      ? ["planner", "researcher", "critic"]
      : mode === "manual"
        ? selectedAgents
        : [];

  // Initialize steps from expected agents
  useEffect(() => {
    setSteps(
      expectedAgents.map((agent) => ({
        agent,
        label: names[agent] ?? agent,
        status: "waiting",
      })),
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode, selectedAgents.length]);

  // Connect to SSE when taskId is available
  useEffect(() => {
    if (!taskId || done) return;

    const es = new EventSource(`${API_URL}/api/events/${taskId}`);
    esRef.current = es;

    es.onmessage = (event) => {
      const data: BusEvent = JSON.parse(event.data);

      if (data.type === "connected") {
        setConnected(true);
        if (data.task_id) onTaskId?.(data.task_id);
        return;
      }

      if (data.type === "done") {
        setDone(true);
        es.close();
        return;
      }

      if (data.type === "agent_event") {
        // Update step statuses based on agent events
        const sourceAgent = data.source_agent;
        const targetAgent = data.target_agent;
        const intent = data.intent ?? "";
        const status = data.status ?? "";

        setSteps((current) =>
          current.map((step) => {
            if (targetAgent === step.agent && status === "processing") {
              return { ...step, status: "working" };
            }
            if (sourceAgent === step.agent && status === "completed") {
              return { ...step, status: "completed" };
            }
            return step;
          }),
        );

        // Add to log
        if (data.content && intent !== "task_started" && intent !== "task_completed") {
          setLog((current) => {
            const next = [...current, `${sourceAgent}: ${data.content}`];
            return next.length > 8 ? next.slice(-8) : next;
          });
        }
      }
    };

    es.onerror = () => {
      // Connection failed — fall back to basic animation
      setConnected(false);
    };

    return () => {
      es.close();
      esRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [taskId]);

  // Fallback: if no SSE after 2s, show basic staged animation
  useEffect(() => {
    if (connected || done) return;
    const timer = window.setTimeout(() => {
      if (!connected) {
        setSteps((current) =>
          current.map((step, i) =>
            step.status === "waiting" && i === 0
              ? { ...step, status: "working" }
              : step,
          ),
        );
      }
    }, 2000);
    return () => window.clearTimeout(timer);
  }, [connected, done]);

  return (
    <div className="flex gap-3">
      <span className="grid size-9 shrink-0 place-items-center rounded-full bg-primary text-white">
        <Bot className="size-4" />
      </span>
      <div className="min-w-[260px] rounded-[20px] rounded-tl-md bg-[#f0f4fa] p-4">
        <p className="text-xs font-semibold">AION is working...</p>
        <p className="mt-1 text-[9px] uppercase tracking-[0.12em] text-muted-text">
          {connected ? "Live agent progress" : "Connecting..."}
        </p>
        <div className="mt-3 space-y-2 text-[11px]">
          {/* Selecting agents step — always completed */}
          <div className="flex items-center gap-2">
            <Check className="size-3.5 text-[#2b9b68]" />
            <span>Selecting agents</span>
          </div>

          {/* Agent steps */}
          {steps.length > 0
            ? steps.map((step) => (
                <div key={step.agent} className="flex items-center gap-2">
                  {step.status === "completed" ? (
                    <Check className="size-3.5 text-[#2b9b68]" />
                  ) : (
                    <Circle
                      className={`size-3.5 ${step.status === "working" ? "fill-primary text-primary animate-pulse" : "text-[#adb4be]"}`}
                    />
                  )}
                  <span
                    className={
                      step.status === "working"
                        ? "font-medium"
                        : step.status === "completed"
                          ? "text-muted-text line-through"
                          : "text-muted-text"
                    }>
                    {step.label}{" "}
                    {step.status === "working"
                      ? "is working"
                      : step.status === "completed"
                        ? "completed"
                        : "is waiting"}
                  </span>
                </div>
              ))
            : !connected && (
                <div className="flex items-center gap-2">
                  <Circle className="size-3.5 fill-primary text-primary animate-pulse" />
                  <span>Coordinating the selected workflow</span>
                </div>
              )}
        </div>

        {/* Live event log */}
        {log.length > 0 && (
          <div className="mt-3 border-t border-[#dce2ea] pt-2">
            {log.slice(-3).map((entry, i) => (
              <p key={i} className="text-[9px] leading-4 text-muted-text truncate">
                {entry}
              </p>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
