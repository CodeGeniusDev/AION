"use client";

import { useEffect, useState } from "react";
import { AlertCircle, ArrowUpRight, BrainCircuit, Database, HardDrive, Search } from "lucide-react";
import { getMemory } from "@/services/api";
import type { MemoryCategory } from "@/types";
import { PageHeader } from "@/components/layout/page-header";
import { LoadingSkeleton } from "@/components/ui/loading-skeleton";
import { ProgressIndicator } from "@/components/ui/progress-indicator";
import { SectionCard } from "@/components/ui/section-card";

const memoryFallback = {
  categories: [
    { id: "short-term", title: "Short-Term Memory", description: "Active task context and recent conversation state.", type: "short_term" as const, count: "18 items", usage: 64 },
    { id: "long-term", title: "Long-Term Memory", description: "Durable facts, decisions, and learned preferences.", type: "long_term" as const, count: "24 records", usage: 42 },
    { id: "vector", title: "Vector Memory", description: "Semantic context prepared for future similarity search.", type: "vector" as const, count: "1,284 vectors", usage: 76 },
  ],
  policies: ["Task context expires after 7 days", "Reviewed decisions persist", "Sensitive inputs stay local"],
};

const icons = [BrainCircuit, HardDrive, Database];
const tones = ["bg-soft-peach", "bg-soft-blue", "bg-soft-green"];

export function MemoryView() {
  const [categories, setCategories] = useState<MemoryCategory[]>(memoryFallback.categories);
  const [policies, setPolicies] = useState<string[]>(memoryFallback.policies);
  const [loading, setLoading] = useState(true);
  const [usingFallback, setUsingFallback] = useState(false);

  useEffect(() => {
    let mounted = true;
    getMemory()
      .then((response) => {
        if (mounted) {
          setCategories(response.categories);
          setPolicies(response.policies);
          setUsingFallback(false);
        }
      })
      .catch(() => {
        if (mounted) {
          setCategories(memoryFallback.categories);
          setPolicies(memoryFallback.policies);
          setUsingFallback(true);
        }
      })
      .finally(() => {
        if (mounted) setLoading(false);
      });
    return () => {
      mounted = false;
    };
  }, []);

  return (
    <>
      <PageHeader eyebrow="Shared context" title="Memory" description="See how AION keeps the right context available across tasks and agents." />
      <div className="p-4 sm:p-6 lg:p-7">
        {usingFallback && (
          <div role="status" className="mb-5 flex items-center gap-2 rounded-full border border-[#ead7af] bg-[#fff9eb] px-4 py-2 text-xs text-[#7d621e]">
            <AlertCircle className="size-4" />
            Live API unavailable — showing a safe demo snapshot.
          </div>
        )}
        <label className="relative block max-w-lg">
          <Search className="absolute left-4 top-1/2 size-4 -translate-y-1/2 text-muted-text" />
          <span className="sr-only">Search memory</span>
          <input className="h-11 w-full rounded-full border bg-white pl-11 pr-4 text-sm" placeholder="Search saved context" />
        </label>
        {loading ? (
          <div aria-label="Loading memory" className="mt-5 grid gap-5 lg:grid-cols-3">
            {[0, 1, 2].map((item) => <LoadingSkeleton key={item} className="h-[280px]" />)}
          </div>
        ) : (
          <div className="mt-5 grid gap-5 lg:grid-cols-3">
            {categories.map((category, index) => {
              const Icon = icons[index % icons.length];
              return (
                <article key={category.id} className="rounded-[24px] border bg-white p-5 sm:p-6">
                  <span className={`grid size-12 place-items-center rounded-[18px] ${tones[index % tones.length]}`}>
                    <Icon className="size-5" />
                  </span>
                  <h2 className="mt-5 text-lg font-semibold">{category.title}</h2>
                  <p className="mt-2 min-h-12 text-sm leading-6 text-muted-text">{category.description}</p>
                  <p className="mt-5 text-2xl font-semibold tracking-[-0.03em]">{category.count}</p>
                  <div className="mt-4">
                    <ProgressIndicator value={category.usage} label="Capacity used" />
                  </div>
                  <button type="button" className="mt-5 flex items-center gap-2 text-xs font-semibold text-primary">
                    Explore memory <ArrowUpRight className="size-4" />
                  </button>
                </article>
              );
            })}
          </div>
        )}
        <SectionCard className="mt-5" title="Memory policy" description="How AION decides what context should be retained.">
          <div className="grid gap-3 sm:grid-cols-3">
            {policies.map((item, index) => (
              <div key={item} className="rounded-[18px] bg-[#f7f9fc] p-4">
                <span className="text-[10px] font-semibold text-primary">0{index + 1}</span>
                <p className="mt-2 text-xs font-medium">{item}</p>
              </div>
            ))}
          </div>
        </SectionCard>
      </div>
    </>
  );
}
