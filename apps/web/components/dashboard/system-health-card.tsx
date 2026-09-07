import { CheckCircle2, Database, RadioTower } from "lucide-react";
import type { HealthData } from "@/types";

const statusColors: Record<string, string> = {
  ok: "bg-[#eaf6f0] text-[#247a55]",
  degraded: "bg-[#fff4d8] text-[#84651b]",
  error: "bg-[#fde8e8] text-[#b14a4a]",
};

const statusLabels: Record<string, string> = {
  healthy: "Healthy",
  degraded: "Degraded",
  unhealthy: "Unhealthy",
};

export function SystemHealthCard({
  value,
  health,
}: {
  value: number;
  health?: HealthData | null;
}) {
  const statuses = [
    {
      label: "Gemini API",
      value: health?.gemini.detail ?? "Checking...",
      status: health?.gemini.status ?? "ok",
      icon: RadioTower,
    },
    {
      label: "Memory",
      value: health?.memory.detail ?? "Checking...",
      status: health?.memory.status ?? "ok",
      icon: Database,
    },
    {
      label: "Agents",
      value: health?.agents.detail ?? "Checking...",
      status: health?.agents.status ?? "ok",
      icon: CheckCircle2,
    },
  ];

  const overall = health?.status ?? "healthy";

  return (
    <article className="rounded-[24px] border bg-white p-5 sm:p-6">
      <div className="flex items-start justify-between">
        <div>
          <h2 className="text-lg font-semibold tracking-[-0.02em]">
            System Health
          </h2>
          <p className="mt-1 text-xs text-muted-text">
            {health?.version ? `v${health.version}` : "All systems operational"}
          </p>
        </div>
        <span
          className={`rounded-full px-2.5 py-1 text-[10px] font-semibold ${statusColors[overall === "healthy" ? "ok" : overall === "degraded" ? "degraded" : "error"] ?? statusColors.ok}`}>
          {statusLabels[overall] ?? "Healthy"}
        </span>
      </div>
      <div className="relative mx-auto mt-8 h-[100px] w-[210px] overflow-hidden">
        <div className="health-gauge absolute inset-x-0 top-0 h-[210px] rounded-full" />
        <div className="absolute left-[18px] top-[18px] size-[174px] rounded-full bg-white" />
        <div className="absolute inset-x-0 bottom-0 text-center">
          <span className="text-[43px] font-semibold leading-none tracking-[-0.05em]">
            {value}%
          </span>
          <p className="mt-1 text-[10px] uppercase tracking-[0.16em] text-muted-text">
            System score
          </p>
        </div>
      </div>
      <div className="mt-6 divide-y rounded-[18px] border px-4">
        {statuses.map((status) => {
          const Icon = status.icon;
          return (
            <div
              key={status.label}
              className="flex items-center gap-3 py-3 text-xs">
              <Icon className="size-4 text-primary" />
              <span className="text-muted-text">{status.label}</span>
              <span className="ml-auto font-medium">{status.value}</span>
            </div>
          );
        })}
      </div>
    </article>
  );
}
