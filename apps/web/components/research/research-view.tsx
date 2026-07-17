import { ArrowUpRight, FileText, FlaskConical, Lightbulb, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/layout/page-header";
import { EmptyState } from "@/components/ui/empty-state";

const notes = [
  { title: "Agent handoff patterns", type: "Architecture note", date: "Updated today", tone: "bg-soft-blue" },
  { title: "Memory retrieval benchmarks", type: "Experiment", date: "Updated Tuesday", tone: "bg-soft-green" },
  { title: "Confidence scoring model", type: "Working draft", date: "Updated last week", tone: "bg-soft-peach" },
];

export function ResearchView() {
  return <><PageHeader eyebrow="Lab notebook" title="Research" description="Keep architecture notes, experiments, and promising ideas close to the system." action={<Button><Plus className="mr-2 size-4" />New Note</Button>} /><div className="grid gap-5 p-4 sm:p-6 lg:grid-cols-[minmax(0,1.45fr)_minmax(280px,.55fr)] lg:p-7"><section className="rounded-[24px] border bg-white p-5 sm:p-6"><div className="flex items-center justify-between"><div><h2 className="text-lg font-semibold">Recent notes</h2><p className="mt-1 text-xs text-muted-text">Ideas and experiments shaping AION</p></div><FlaskConical className="size-5 text-primary" /></div><div className="mt-5 divide-y">{notes.map((note) => <article key={note.title} className="flex items-center gap-4 py-4"><span className={`grid size-11 shrink-0 place-items-center rounded-[17px] ${note.tone}`}><FileText className="size-4" /></span><div className="min-w-0"><h3 className="truncate text-sm font-semibold">{note.title}</h3><p className="mt-1 text-[10px] text-muted-text">{note.type} · {note.date}</p></div><button type="button" className="ml-auto grid size-9 shrink-0 place-items-center rounded-full border" aria-label={`Open ${note.title}`}><ArrowUpRight className="size-4" /></button></article>)}</div></section><EmptyState icon={Lightbulb} title="Experiment queue" description="Promising research questions can be staged here before an agent workflow begins." action={<Button variant="outline" size="sm">Add an idea</Button>} /></div></>;
}

