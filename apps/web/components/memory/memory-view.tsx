"use client";

import { useEffect, useState } from "react";
import { ArrowUpRight, BrainCircuit, Database, HardDrive, Search } from "lucide-react";
import { getMemory } from "@/services/api";
import type { MemoryCategory } from "@/types";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { PageHeader } from "@/components/layout/page-header";
import { LoadingSkeleton } from "@/components/ui/loading-skeleton";
import { ProgressIndicator } from "@/components/ui/progress-indicator";
import { SectionCard } from "@/components/ui/section-card";

const icons = [BrainCircuit, HardDrive, Database];
const tones = ["bg-soft-peach", "bg-soft-blue", "bg-soft-green"];

export function MemoryView() {
  const [categories, setCategories] = useState<MemoryCategory[]>([]);
  const [policies, setPolicies] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [loadAttempt, setLoadAttempt] = useState(0);

  useEffect(() => {
    let mounted = true;
    setLoading(true);
    getMemory()
      .then((response) => {
        if (mounted) {
          setCategories(response.categories);
          setPolicies(response.policies);
          setError(false);
        }
      })
      .catch(() => {
        if (mounted) setError(true);
      })
      .finally(() => {
        if (mounted) setLoading(false);
      });
    return () => {
      mounted = false;
    };
  }, [loadAttempt]);

  return (
    <>
      <PageHeader eyebrow="Shared context" title="Memory" description="See how AION keeps the right context available across tasks and agents." />
      <div className="p-4 sm:p-6 lg:p-7">
        <label className="relative block max-w-lg">
          <Search className="absolute left-4 top-1/2 size-4 -translate-y-1/2 text-muted-text" />
          <span className="sr-only">Search memory</span>
          <input className="h-11 w-full rounded-full border bg-white pl-11 pr-4 text-sm" placeholder="Search saved context" />
        </label>
        {loading ? (
          <div aria-label="Loading memory" className="mt-5 grid gap-5 lg:grid-cols-3">
            {[0, 1, 2].map((item) => <LoadingSkeleton key={item} className="h-[280px]" />)}
          </div>
        ) : error ? (
          <div className="mt-5">
            <EmptyState
              title="Unable to load data"
              description="AION could not reach the backend API. Check that the server is running, then retry."
              action={
                <Button variant="outline" size="sm" onClick={() => setLoadAttempt((attempt) => attempt + 1)}>
                  Retry
                </Button>
              }
            />
          </div>
        ) : (
          <>
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
          </>
        )}
      </div>
    </>
  );
}
