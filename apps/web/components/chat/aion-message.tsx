"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import {
  Bot,
  Check,
  ChevronDown,
  Copy,
  Database,
  RefreshCw,
  ShieldCheck,
  ThumbsDown,
  ThumbsUp,
  Volume2,
} from "lucide-react";
import { getVoiceStatus, saveToMemory, submitFeedback, voiceSay } from "@/services/api";
import type { ChatResponse } from "@/types";
import { Button } from "@/components/ui/button";
import { cn } from "@/utils/cn";

const shortNames: Record<string, string> = {
  planner: "Planner",
  researcher: "Researcher",
  critic: "Critic",
  memory: "Memory",
};

/** Server TTS availability is a deployment property — probe once, share
 * the answer across every message bubble. Uninstalled renders no button. */
let ttsProbe: Promise<boolean> | null = null;
function ttsAvailableOnce(): Promise<boolean> {
  if (!ttsProbe) {
    ttsProbe = getVoiceStatus()
      .then((status) => status.tts.available)
      .catch(() => false);
  }
  return ttsProbe;
}

/** Parse a markdown-style link `[title](url)` into a React anchor, or return plain text. */
function renderSource(source: string, index: number) {
  const match = source.match(/^\[([^\]]+)\]\(([^)]+)\)$/);
  if (match) {
    return (
      <a
        key={index}
        href={match[2]}
        target="_blank"
        rel="noopener noreferrer"
        className="text-primary underline">
        {match[1]}
      </a>
    );
  }
  return <span key={index}>{source}</span>;
}

export function AionMessage({
  response,
  onRegenerate,
}: {
  response: ChatResponse;
  onRegenerate: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [copied, setCopied] = useState(false);
  const [reaction, setReaction] = useState<"up" | "down" | null>(null);
  const [saved, setSaved] = useState(false);
  const [canSpeak, setCanSpeak] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const pending = response.pending_approval ?? null;
  // The backend prefixes the answer with a plain-text notice so every
  // consumer sees it. When we render the structured card we drop that
  // first notice paragraph to avoid showing the same thing twice.
  const displayAnswer =
    pending && response.answer.startsWith("⚠ Approval required:")
      ? response.answer.slice(response.answer.indexOf("\n\n") + 2)
      : response.answer;
  const agentLine = response.used_agents
    .map((agent) => shortNames[agent.id])
    .join(" • ");

  async function copyAnswer() {
    await navigator.clipboard.writeText(response.answer);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1400);
  }

  useEffect(() => {
    void ttsAvailableOnce().then(setCanSpeak);
  }, []);

  async function speakAnswer() {
    if (speaking) return;
    setSpeaking(true);
    try {
      const result = await voiceSay(displayAnswer.slice(0, 1000));
      if (result.available && result.audio_base64 && result.mime) {
        new Audio(`data:${result.mime};base64,${result.audio_base64}`).play();
      }
      // Not available: silent degradation — the probe raced an uninstall.
    } catch {
      /* non-blocking */
    } finally {
      setSpeaking(false);
    }
  }

  async function handleReaction(sentiment: "up" | "down") {
    setReaction(sentiment);
    try {
      await submitFeedback(response.task_id, sentiment);
    } catch {
      /* non-blocking */
    }
  }

  async function handleSaveToMemory() {
    if (saved) return;
    try {
      await saveToMemory(response.answer, response.task_id);
      setSaved(true);
    } catch {
      /* non-blocking */
    }
  }

  return (
    <div className="flex gap-3">
      <span className="grid size-9 shrink-0 place-items-center rounded-full bg-primary text-white">
        <Bot className="size-4" />
      </span>
      <div className="max-w-[88%] rounded-[22px] rounded-tl-md bg-[#f0f4fa] px-4 py-3 text-sm leading-6 text-aion-text">
        <div className="flex flex-wrap items-center gap-x-2">
          <p className="text-[11px] font-semibold text-primary">AION</p>
          {response.development_mode && (
            <span className="rounded-full bg-[#fff4d8] px-2 py-0.5 text-[9px] font-medium text-[#84651b]">
              Development mode
            </span>
          )}
        </div>
        {agentLine && (
          <p className="mb-2 text-[10px] text-muted-text">{agentLine}</p>
        )}
        {pending && (
          <div className="mb-3 rounded-[14px] border border-[#e2d4ad] bg-[#fff8e6] p-3">
            <div className="flex items-start gap-2">
              <ShieldCheck className="mt-0.5 size-4 shrink-0 text-[#8b6a16]" />
              <div className="min-w-0 flex-1">
                <p className="text-[11px] font-semibold text-[#8b6a16]">
                  Approval pending — nothing has run
                </p>
                <p className="mt-0.5 text-[10px] leading-5 text-[#8b6a16]/90">
                  “{pending.tool}” is waiting for your decision. It expires at{" "}
                  {new Date(pending.expires_at).toLocaleTimeString()}.
                </p>
                <Link href={pending.queue_path} className="mt-2 inline-block">
                  <Button size="sm" variant="outline" className="h-8 gap-1.5 text-[10px]">
                    Review in queue
                    <ChevronDown className="size-3.5 -rotate-90" />
                  </Button>
                </Link>
              </div>
            </div>
          </div>
        )}
        <p className="whitespace-pre-wrap">{displayAnswer}</p>
        {response.sources.length > 0 && (
          <div className="mt-3 rounded-[12px] border border-[#dce2ea] bg-white/70 p-3">
            <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-muted-text">
              Sources
            </p>
            <ul className="mt-2 space-y-1">
              {response.sources.map((source, i) => (
                <li key={i} className="text-[10px] leading-5 text-muted-text">
                  {renderSource(source, i)}
                </li>
              ))}
            </ul>
          </div>
        )}
        <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-[#dce2ea] pt-3 text-[10px] font-medium text-muted-text">
          <span>{Math.round(response.confidence * 100)}% confidence</span>
          <span>•</span>
          <span>{response.used_agents.length} agents used</span>
          <span>•</span>
          <span>{(response.processing_time_ms / 1000).toFixed(1)}s</span>
          {response.sources.length > 0 && (
            <>
              <span>•</span>
              <span>{response.sources.length} sources</span>
            </>
          )}
        </div>
        <div className="mt-3 flex flex-wrap gap-1">
          <button
            type="button"
            onClick={copyAnswer}
            className="flex h-8 items-center gap-1.5 rounded-full px-2.5 text-[10px] text-muted-text hover:bg-white">
            <Copy className="size-3.5" />
            {copied ? "Copied" : "Copy"}
          </button>
          <button
            type="button"
            onClick={onRegenerate}
            className="flex h-8 items-center gap-1.5 rounded-full px-2.5 text-[10px] text-muted-text hover:bg-white">
            <RefreshCw className="size-3.5" />
            Regenerate
          </button>
          {canSpeak && (
            <button
              type="button"
              onClick={() => void speakAnswer()}
              disabled={speaking}
              aria-label="Read the answer aloud in the browser"
              className="flex h-8 items-center gap-1.5 rounded-full px-2.5 text-[10px] text-muted-text hover:bg-white">
              <Volume2 className="size-3.5" />
              {speaking ? "Speaking…" : "Speak"}
            </button>
          )}
          <button
            type="button"
            onClick={handleSaveToMemory}
            disabled={saved}
            className={cn(
              "flex h-8 items-center gap-1.5 rounded-full px-2.5 text-[10px] hover:bg-white",
              saved ? "text-primary" : "text-muted-text",
            )}>
            <Database className="size-3.5" />
            {saved ? "Saved" : "Save to Memory"}
          </button>
          <button
            type="button"
            onClick={() => handleReaction("up")}
            aria-pressed={reaction === "up"}
            className={cn(
              "grid size-8 place-items-center rounded-full text-muted-text hover:bg-white",
              reaction === "up" && "bg-white text-primary",
            )}
            aria-label="Like response">
            <ThumbsUp className="size-3.5" />
          </button>
          <button
            type="button"
            onClick={() => handleReaction("down")}
            aria-pressed={reaction === "down"}
            className={cn(
              "grid size-8 place-items-center rounded-full text-muted-text hover:bg-white",
              reaction === "down" && "bg-white text-[#b14a4a]",
            )}
            aria-label="Dislike response">
            <ThumbsDown className="size-3.5" />
          </button>
        </div>
        {response.used_agents.length > 0 && (
          <div className="mt-2 border-t border-[#dce2ea] pt-2">
            <button
              type="button"
              onClick={() => setExpanded((value) => !value)}
              aria-expanded={expanded}
              className="flex w-full items-center gap-2 py-1 text-left text-[11px] font-semibold">
              <ChevronDown
                className={cn(
                  "size-4 transition-transform",
                  expanded && "rotate-180",
                )}
              />
              View Agent Process
            </button>
            {expanded && (
              <div className="mt-2 space-y-3 rounded-[16px] bg-white/70 p-3">
                {response.used_agents.map((agent) => (
                  <div key={agent.id} className="flex gap-2">
                    <Check
                      className={cn(
                        "mt-1 size-3.5 shrink-0",
                        agent.status === "completed"
                          ? "text-[#2b9b68]"
                          : "text-[#b14a4a]",
                      )}
                    />
                    <div>
                      <p className="text-[11px] font-semibold">{agent.name}</p>
                      <p className="text-[10px] leading-5 text-muted-text">
                        {agent.summary}
                      </p>
                    </div>
                  </div>
                ))}
                <p className="text-[9px] leading-4 text-muted-text">
                  {response.selection_summary}
                </p>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
