import { ArrowUpRight, BrainCircuit, Database, HardDrive, Search } from "lucide-react";
import { PageHeader } from "@/components/layout/page-header";
import { ProgressIndicator } from "@/components/ui/progress-indicator";
import { SectionCard } from "@/components/ui/section-card";

const memories = [
  { title: "Short-Term Memory", description: "Active task context and recent conversation state.", count: "18 items", usage: 64, icon: BrainCircuit, tone: "bg-soft-peach" },
  { title: "Long-Term Memory", description: "Durable facts, decisions, and learned preferences.", count: "24 records", usage: 42, icon: HardDrive, tone: "bg-soft-blue" },
  { title: "Vector Memory", description: "Semantic context prepared for future similarity search.", count: "1,284 vectors", usage: 76, icon: Database, tone: "bg-soft-green" },
];

export function MemoryView() {
  return <><PageHeader eyebrow="Shared context" title="Memory" description="See how AION keeps the right context available across tasks and agents." /><div className="p-4 sm:p-6 lg:p-7"><label className="relative block max-w-lg"><Search className="absolute left-4 top-1/2 size-4 -translate-y-1/2 text-muted-text" /><span className="sr-only">Search memory</span><input className="h-11 w-full rounded-full border bg-white pl-11 pr-4 text-sm" placeholder="Search saved context" /></label><div className="mt-5 grid gap-5 lg:grid-cols-3">{memories.map((memory) => { const Icon = memory.icon; return <article key={memory.title} className="rounded-[24px] border bg-white p-5 sm:p-6"><span className={`grid size-12 place-items-center rounded-[18px] ${memory.tone}`}><Icon className="size-5" /></span><h2 className="mt-5 text-lg font-semibold">{memory.title}</h2><p className="mt-2 min-h-12 text-sm leading-6 text-muted-text">{memory.description}</p><p className="mt-5 text-2xl font-semibold tracking-[-0.03em]">{memory.count}</p><div className="mt-4"><ProgressIndicator value={memory.usage} label="Capacity used" /></div><button type="button" className="mt-5 flex items-center gap-2 text-xs font-semibold text-primary">Explore memory <ArrowUpRight className="size-4" /></button></article>; })}</div><SectionCard className="mt-5" title="Memory policy" description="How AION decides what context should be retained."><div className="grid gap-3 sm:grid-cols-3">{["Task context expires after 7 days", "Reviewed decisions persist", "Sensitive inputs stay local"].map((item, index) => <div key={item} className="rounded-[18px] bg-[#f7f9fc] p-4"><span className="text-[10px] font-semibold text-primary">0{index + 1}</span><p className="mt-2 text-xs font-medium">{item}</p></div>)}</div></SectionCard></div></>;
}

