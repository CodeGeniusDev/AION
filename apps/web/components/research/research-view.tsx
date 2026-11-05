"use client";

import { useEffect, useMemo, useState } from "react";
import {
  ArrowUpRight,
  FileText,
  FlaskConical,
  Lightbulb,
  Lock,
} from "lucide-react";
import { getResearch } from "@/services/api";
import type { ResearchNote } from "@/types";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/layout/page-header";
import { usePageSearch } from "@/components/layout/page-search-provider";
import { EmptyState } from "@/components/ui/empty-state";
import { LoadingSkeleton } from "@/components/ui/loading-skeleton";
import { Tooltip } from "@/components/ui/tooltip";

const tones = ["bg-soft-blue", "bg-soft-green", "bg-soft-peach"];

export function ResearchView() {
  const { active, matches } = usePageSearch();
  const [notes, setNotes] = useState<ResearchNote[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [loadAttempt, setLoadAttempt] = useState(0);

  useEffect(() => {
    let mounted = true;
    setLoading(true);
    getResearch()
      .then((response) => {
        if (mounted) {
          setNotes(response.items);
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

  const visibleNotes = useMemo(
    () => notes.filter((note) => matches(note.title, note.type)),
    [notes, matches],
  );

  return (
    <>
      <PageHeader
        eyebrow="Lab notebook"
        title="Research"
        description="Keep architecture notes, experiments, and promising ideas close to the system."
        action={
          <Tooltip content="Lab notebook creation coming soon">
            <Button disabled>
              <Lock className="mr-2 size-3.5" />
              New Note
            </Button>
          </Tooltip>
        }
      />
      <div className="p-4 sm:p-6 lg:p-7">
        <div className="grid gap-5 lg:grid-cols-[minmax(0,1.45fr)_minmax(280px,.55fr)]">
          <section className="rounded-[24px] border bg-surface p-5 sm:p-6">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-lg font-semibold">Recent notes</h2>
                <p className="mt-1 text-xs text-muted-text">
                  Ideas and experiments shaping AION
                </p>
              </div>
              <FlaskConical className="size-5 text-primary" />
            </div>
            {loading ? (
              <div
                aria-label="Loading research notes"
                className="mt-5 space-y-3">
                {[0, 1, 2].map((item) => (
                  <LoadingSkeleton key={item} className="h-16" />
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
            ) : visibleNotes.length ? (
              <div className="mt-5 divide-y">
                {visibleNotes.map((note, index) => (
                  <article
                    key={note.id}
                    className="flex items-center gap-4 py-4">
                    <span
                      className={`grid size-11 shrink-0 place-items-center rounded-[17px] ${tones[index % tones.length]}`}>
                      <FileText className="size-4" />
                    </span>
                    <div className="min-w-0">
                      <h3 className="truncate text-sm font-semibold">
                        {note.title}
                      </h3>
                      <p className="mt-1 text-[10px] text-muted-text">
                        {note.type} · {note.date}
                      </p>
                    </div>
                    <Tooltip content="Note viewer coming soon">
                      <button
                        type="button"
                        disabled
                        className="ml-auto grid size-9 shrink-0 place-items-center rounded-full border border-border bg-surface-2 text-muted-text cursor-not-allowed"
                        aria-label={`Open ${note.title} (coming soon)`}>
                        <ArrowUpRight className="size-4" />
                      </button>
                    </Tooltip>
                  </article>
                ))}
              </div>
            ) : (
              <div className="mt-5">
                <EmptyState
                  title={
                    active && notes.length
                      ? "No notes match the search"
                      : "No research notes yet"
                  }
                  description={
                    active && notes.length
                      ? "Nothing on this page matches the current filter. Clear the search to see all notes again."
                      : "Verified research findings from AION will appear here once available."
                  }
                />
              </div>
            )}
          </section>
          <EmptyState
            icon={Lightbulb}
            title="Experiment queue"
            description="Promising research questions can be staged here before an agent workflow begins."
            action={
              <Tooltip content="Experiment queue coming soon">
                <Button variant="outline" size="sm" disabled>
                  <Lock className="mr-2 size-3.5" />
                  Add an idea
                </Button>
              </Tooltip>
            }
          />
        </div>
      </div>
    </>
  );
}
