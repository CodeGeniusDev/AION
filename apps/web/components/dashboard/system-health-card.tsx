import { CheckCircle2, Database, RadioTower } from "lucide-react";

export function SystemHealthCard({ value }: { value: number }) {
  const statuses = [
    { label: "API Status", value: "Online", icon: RadioTower },
    { label: "Memory", value: "Connected", icon: Database },
    { label: "Agents", value: "4 Active", icon: CheckCircle2 },
  ];
  return (
    <article className="rounded-[24px] border bg-white p-5 sm:p-6">
      <div className="flex items-start justify-between">
        <div><h2 className="text-lg font-semibold tracking-[-0.02em]">System Health</h2><p className="mt-1 text-xs text-muted-text">All systems operational</p></div>
        <span className="rounded-full bg-[#eaf6f0] px-2.5 py-1 text-[10px] font-semibold text-[#247a55]">Healthy</span>
      </div>
      <div className="relative mx-auto mt-8 h-[100px] w-[210px] overflow-hidden">
        <div className="health-gauge absolute inset-x-0 top-0 h-[210px] rounded-full" />
        <div className="absolute left-[18px] top-[18px] size-[174px] rounded-full bg-white" />
        <div className="absolute inset-x-0 bottom-0 text-center"><span className="text-[43px] font-semibold leading-none tracking-[-0.05em]">{value}%</span><p className="mt-1 text-[10px] uppercase tracking-[0.16em] text-muted-text">System score</p></div>
      </div>
      <div className="mt-6 divide-y rounded-[18px] border px-4">
        {statuses.map((status) => {
          const Icon = status.icon;
          return <div key={status.label} className="flex items-center gap-3 py-3 text-xs"><Icon className="size-4 text-primary" /><span className="text-muted-text">{status.label}</span><span className="ml-auto font-medium">{status.value}</span></div>;
        })}
      </div>
    </article>
  );
}

