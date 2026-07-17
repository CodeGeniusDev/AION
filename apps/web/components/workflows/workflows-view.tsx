import { ArrowUpRight, Network, Plus, Route } from "lucide-react";
import { workflows } from "@/data/demo-data";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/ui/status-badge";
import { PageHeader } from "@/components/layout/page-header";

export function WorkflowsView() {
  return <><PageHeader eyebrow="Agent orchestration" title="Workflows" description="Reusable paths that coordinate specialists from first request to reviewed result." action={<Button><Plus className="mr-2 size-4" />New Workflow</Button>} /><div className="grid gap-5 p-4 sm:p-6 lg:grid-cols-3 lg:p-7">{workflows.map((workflow, index) => <article key={workflow.name} className="flex flex-col rounded-[24px] border bg-white p-5 sm:p-6"><div className="flex items-start justify-between"><span className={`grid size-12 place-items-center rounded-[18px] ${index === 0 ? "bg-soft-blue" : index === 1 ? "bg-soft-peach" : "bg-soft-green"}`}>{index === 0 ? <Network className="size-5" /> : <Route className="size-5" />}</span><StatusBadge status={workflow.state} /></div><h2 className="mt-5 text-lg font-semibold tracking-[-0.02em]">{workflow.name}</h2><p className="mt-2 text-sm leading-6 text-muted-text">{workflow.description}</p><div className="mt-5 flex flex-wrap gap-1.5">{workflow.agents.map((agent, agentIndex) => <span key={agent} className="rounded-full border bg-[#fafbfd] px-2.5 py-1 text-[10px] font-medium">{agentIndex + 1}. {agent}</span>)}</div><div className="mt-auto flex items-center border-t pt-5 text-xs text-muted-text"><span>{workflow.runs} total runs</span><button type="button" className="ml-auto grid size-9 place-items-center rounded-full bg-navy text-white" aria-label={`Open ${workflow.name}`}><ArrowUpRight className="size-4" /></button></div></article>)}</div></>;
}

