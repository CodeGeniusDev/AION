"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { ArrowUpRight, BrainCircuit, Database, HardDrive, Search, Trash2, X } from "lucide-react";
import {
  deleteMemoryRecord,
  getMemory,
  listMemoryRecords,
  searchMemoryRecords,
} from "@/services/api";
import type { MemoryCategory, MemoryRecordOut } from "@/types";
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

  // Records panel
  const [records, setRecords] = useState<MemoryRecordOut[]>([]);
  const [recordsTotal, setRecordsTotal] = useState(0);
  const [recordsLoading, setRecordsLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [showRecords, setShowRecords] = useState(false);

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

  const loadRecords = useCallback(
    async (query?: string) => {
      setRecordsLoading(true);
      try {
        const result = query
          ? await searchMemoryRecords(query, { limit: 50 })
          : await listMemoryRecords({ limit: 50 });
        setRecords(result.items);
        setRecordsTotal(result.total);
      } catch {
        setRecords([]);
        setRecordsTotal(0);
      } finally {
        setRecordsLoading(false);
      }
    },
    [],
  );

  function openRecords() {
    setShowRecords(true);
    void loadRecords();
  }

  function handleSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void loadRecords(searchQuery.trim() || undefined);
  }

  async function handleDelete(memoryId: string) {
    try {
      await deleteMemoryRecord(memoryId);
      setRecords((current) => current.filter((r) => r.memory_id !== memoryId));
      setRecordsTotal((current) => current - 1);
    } catch {
      // ignore
    }
  }

  return (
    <>
      <PageHeader
        eyebrow="Shared context"
        title="Memory"
        description="See how AION keeps the right context available across tasks and agents."
      />
      <div className="p-4 sm:p-6 lg:p-7">
        {loading ? (
          <div
            aria-label="Loading memory"
            className="mt-5 grid gap-5 lg:grid-cols-3">
            {[0, 1, 2].map((item) => (
              <LoadingSkeleton key={item} className="h-[280px]" />
            ))}
          </div>
        ) : error ? (
          <div className="mt-5">
            <EmptyState
              title="Unable to load data"
              description="AION could not reach the backend API. Check that the server is running, then retry."
              action={
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setLoadAttempt((attempt) => attempt + 1)}>
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
                  <article
                    key={category.id}
                    className="rounded-[24px] border bg-white p-5 sm:p-6">
                    <span
                      className={`grid size-12 place-items-center rounded-[18px] ${tones[index % tones.length]}`}>
                      <Icon className="size-5" />
                    </span>
                    <h2 className="mt-5 text-lg font-semibold">
                      {category.title}
                    </h2>
                    <p className="mt-2 min-h-12 text-sm leading-6 text-muted-text">
                      {category.description}
                    </p>
                    <p className="mt-5 text-2xl font-semibold tracking-[-0.03em]">
                      {category.count}
                    </p>
                    <div className="mt-4">
                      <ProgressIndicator
                        value={category.usage}
                        label="Capacity used"
                      />
                    </div>
                    <button
                      type="button"
                      onClick={openRecords}
                      className="mt-5 flex items-center gap-2 text-xs font-semibold text-primary">
                      Explore memory <ArrowUpRight className="size-4" />
                    </button>
                  </article>
                );
              })}
            </div>
            <SectionCard
              className="mt-5"
              title="Memory policy"
              description="How AION decides what context should be retained.">
              <div className="grid gap-3 sm:grid-cols-3">
                {policies.map((item, index) => (
                  <div
                    key={item}
                    className="rounded-[18px] bg-[#f7f9fc] p-4">
                    <span className="text-[10px] font-semibold text-primary">
                      0{index + 1}
                    </span>
                    <p className="mt-2 text-xs font-medium">{item}</p>
                  </div>
                ))}
              </div>
            </SectionCard>

            {/* Records browser panel */}
            {showRecords && (
              <div className="mt-5 rounded-[24px] border bg-white p-5 sm:p-6">
                <div className="flex items-center justify-between">
                  <div>
                    <h2 className="text-lg font-semibold">Memory Records</h2>
                    <p className="mt-1 text-xs text-muted-text">
                      {recordsTotal} record{recordsTotal !== 1 ? "s" : ""} found
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => setShowRecords(false)}
                    className="rounded-full p-1.5 text-muted-text hover:bg-[#f2f4f7]"
                    aria-label="Close records">
                    <X className="size-4" />
                  </button>
                </div>
                <form
                  onSubmit={handleSearch}
                  className="mt-4 flex gap-2">
                  <label className="relative flex-1">
                    <Search className="absolute left-4 top-1/2 size-4 -translate-y-1/2 text-muted-text" />
                    <span className="sr-only">Search memory</span>
                    <input
                      value={searchQuery}
                      onChange={(e) => setSearchQuery(e.target.value)}
                      className="h-11 w-full rounded-full border bg-white pl-11 pr-4 text-sm"
                      placeholder="Search saved context..."
                    />
                  </label>
                  <Button type="submit" variant="outline" size="sm">
                    Search
                  </Button>
                </form>
                <div className="mt-4 max-h-[500px] overflow-y-auto">
                  {recordsLoading ? (
                    <p className="py-8 text-center text-xs text-muted-text">
                      Loading...
                    </p>
                  ) : records.length === 0 ? (
                    <p className="py-8 text-center text-xs text-muted-text">
                      No records found.
                    </p>
                  ) : (
                    <div className="divide-y">
                      {records.map((record) => (
                        <div
                          key={record.memory_id}
                          className="flex items-start gap-3 py-3">
                          <div className="min-w-0 flex-1">
                            <div className="flex items-center gap-2">
                              <span className="rounded-full bg-[#f2f4f7] px-2 py-0.5 text-[9px] font-medium text-primary">
                                {record.type}
                              </span>
                              <span className="text-[9px] text-muted-text">
                                {record.verification_state}
                              </span>
                              <span className="ml-auto text-[9px] text-muted-text">
                                {new Date(record.created_at).toLocaleDateString()}
                              </span>
                            </div>
                            <p className="mt-1 text-xs leading-5">
                              {record.content.length > 150
                                ? `${record.content.slice(0, 150)}...`
                                : record.content}
                            </p>
                            <p className="mt-1 text-[9px] text-muted-text">
                              {record.source_agent} · {record.task_id}
                              {record.tags.length > 0 &&
                                ` · ${record.tags.join(", ")}`}
                            </p>
                          </div>
                          <button
                            type="button"
                            onClick={() =>
                              void handleDelete(record.memory_id)
                            }
                            className="shrink-0 rounded p-1 text-muted-text hover:text-[#b14a4a]"
                            aria-label={`Delete record ${record.memory_id}`}>
                            <Trash2 className="size-3.5" />
                          </button>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </>
  );
}
