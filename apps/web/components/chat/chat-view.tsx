"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import {
  MessageCircleMore,
  Plus,
  Send,
  Sparkles,
  Trash2,
  UserRound,
} from "lucide-react";
import {
  deleteConversation,
  getConversationMessages,
  getConversations,
  sendChatMessage,
} from "@/services/api";
import type {
  AgentId,
  ChatMessage,
  ChatMode,
  ConversationSummary,
} from "@/types";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { PageHeader } from "@/components/layout/page-header";
import { AionMessage } from "./aion-message";
import { ChatErrorState } from "./chat-error-state";
import { ModeSelector } from "./mode-selector";
import { ProcessingState } from "./processing-state";
import { cn } from "@/utils/cn";

export function ChatView() {
  const [activeChat, setActiveChat] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [mode, setMode] = useState<ChatMode>("auto");
  const [selectedAgents, setSelectedAgents] = useState<AgentId[]>([]);
  const [sending, setSending] = useState(false);
  const [failedPrompt, setFailedPrompt] = useState<string | null>(null);
  const [errorDetail, setErrorDetail] = useState<string | null>(null);
  const [conversationId, setConversationId] = useState<string | undefined>(
    undefined,
  );
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [sseTaskId, setSseTaskId] = useState<string | null>(null);

  const manualInvalid = mode === "manual" && selectedAgents.length === 0;

  // Load conversations for the sidebar
  const refreshConversations = useCallback(() => {
    getConversations()
      .then(setConversations)
      .catch(() => setConversations([]));
  }, []);

  useEffect(() => {
    refreshConversations();
  }, [refreshConversations]);

  // Load a conversation's messages
  async function loadConversation(convoId: string) {
    try {
      const stored = await getConversationMessages(convoId);
      const loaded: ChatMessage[] = stored.map((msg, idx) =>
        msg.role === "user"
          ? {
              id: `loaded-user-${idx}`,
              role: "user" as const,
              content: msg.content,
            }
          : {
              id: `loaded-aion-${idx}`,
              role: "assistant" as const,
              response: {
                task_id: msg.task_id ?? "",
                conversation_id: convoId,
                author: "AION" as const,
                answer: msg.content,
                mode: "auto" as const,
                status: "completed" as const,
                used_agents: [],
                confidence: 0,
                processing_time_ms: 0,
                selection_summary: "",
                sources: [],
                error: null,
                development_mode: false,
                revision_count: 0,
              },
            },
      );
      setActiveChat(convoId);
      setConversationId(convoId);
      setMessages(loaded);
      setFailedPrompt(null);
    } catch {
      // conversation not found
    }
  }

  async function handleDeleteConversation(convoId: string) {
    try {
      await deleteConversation(convoId);
      if (conversationId === convoId) startFresh();
      refreshConversations();
    } catch {
      // ignore
    }
  }

  async function sendPrompt(
    value: string,
    replaceId?: string,
    modeOverride?: ChatMode,
  ) {
    const effectiveMode = modeOverride ?? mode;
    if (
      !value.trim() ||
      sending ||
      (effectiveMode === "manual" && selectedAgents.length === 0)
    )
      return;
    setActiveChat((current) => current ?? "new-chat");
    setFailedPrompt(null);
    setErrorDetail(null);
    setMessages((current) => {
      const retained = replaceId
        ? current.filter((message) => message.id !== replaceId)
        : current;
      return replaceId
        ? retained
        : [
            ...retained,
            { id: `user-${Date.now()}`, role: "user", content: value },
          ];
    });
    setInput("");
    setSending(true);
    setSseTaskId(null);
    try {
      const response = await sendChatMessage({
        message: value,
        mode: effectiveMode,
        selected_agents: effectiveMode === "manual" ? selectedAgents : [],
        conversation_id: conversationId,
        memory_enabled: true,
        verification_enabled: true,
      });
      if (response.status === "failed") {
        setErrorDetail(response.error ?? response.answer);
        throw new Error("workflow_failed");
      }
      setConversationId(response.conversation_id);
      setSseTaskId(response.task_id);
      setMessages((current) => [
        ...current,
        { id: `aion-${Date.now()}`, role: "assistant", response },
      ]);
      // Refresh sidebar
      refreshConversations();
    } catch (err) {
      if (!errorDetail) {
        // Network or unexpected error
        setErrorDetail(
          err instanceof Error && err.message !== "workflow_failed"
            ? `Network error: ${err.message}`
            : "Could not reach the AION backend. Please check that the server is running."
        );
      }
      setFailedPrompt(value);
    } finally {
      setSending(false);
    }
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void sendPrompt(input.trim());
  }
  function startFresh() {
    setActiveChat(null);
    setMessages([]);
    setFailedPrompt(null);
    setErrorDetail(null);
    setConversationId(undefined);
    setSseTaskId(null);
  }
  function previousUserMessage(index: number) {
    for (let cursor = index - 1; cursor >= 0; cursor -= 1) {
      const message = messages[cursor];
      if (message.role === "user") return message.content;
    }
    return "";
  }
  function retryQuick() {
    if (!failedPrompt) return;
    setMode("quick");
    setSelectedAgents([]);
    void sendPrompt(failedPrompt, undefined, "quick");
  }

  const headerStatus = sending
    ? mode === "research"
      ? "3 agents working"
      : mode === "manual"
        ? `${selectedAgents.length} agents working`
        : "AION is coordinating the task"
    : mode === "auto"
      ? "Auto collaboration enabled"
      : `${mode === "quick" ? "Direct response" : mode === "research" ? "Research workflow" : "Manual workflow"} enabled`;

  return (
    <>
      <PageHeader
        eyebrow="Agent collaboration"
        title="AI Chat"
        description="Talk to AION. It coordinates specialist agents and returns one verified response."
        action={
          <Button onClick={startFresh}>
            <Plus className="mr-2 size-4" />
            New conversation
          </Button>
        }
      />
      <div className="grid min-h-[680px] min-w-0 lg:grid-cols-[270px_minmax(0,1fr)]">
        <aside className="border-b bg-[#f8fafc] p-4 lg:border-b-0 lg:border-r">
          <p className="px-2 text-[10px] font-semibold uppercase tracking-[0.16em] text-muted-text">
            Recent conversations
          </p>
          {conversations.length === 0 ? (
            <p className="mt-3 px-2 text-[10px] leading-5 text-muted-text">
              No conversations yet.
            </p>
          ) : (
            <ul className="mt-3 space-y-1">
              {conversations.map((convo) => (
                <li key={convo.conversation_id}>
                  <button
                    type="button"
                    onClick={() => loadConversation(convo.conversation_id)}
                    className={cn(
                      "flex w-full items-center gap-2 rounded-lg px-2 py-2 text-left text-[11px] transition-colors",
                      conversationId === convo.conversation_id
                        ? "bg-primary/10 font-medium text-primary"
                        : "text-muted-text hover:bg-white",
                    )}>
                    <MessageCircleMore className="size-3.5 shrink-0" />
                    <span className="flex-1 truncate">{convo.title}</span>
                    <span className="shrink-0 text-[9px] text-muted-text">
                      {convo.message_count}
                    </span>
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        void handleDeleteConversation(convo.conversation_id);
                      }}
                      className="shrink-0 rounded p-0.5 text-muted-text hover:text-[#b14a4a]"
                      aria-label={`Delete ${convo.title}`}>
                      <Trash2 className="size-3" />
                    </button>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </aside>
        <section className="flex min-h-[600px] min-w-0 flex-col">
          <div className="relative flex items-start gap-3 border-b px-4 py-3.5 sm:px-6">
            <span className="grid size-9 shrink-0 place-items-center rounded-full bg-navy text-white">
              <Sparkles className="size-4" />
            </span>
            <div className="pt-0.5">
              <p className="text-xs font-semibold">AION Workspace</p>
              <p className="text-[10px] text-muted-text">{headerStatus}</p>
            </div>
            <ModeSelector
              mode={mode}
              selectedAgents={selectedAgents}
              disabled={sending}
              onModeChange={(nextMode) => {
                setMode(nextMode);
                if (nextMode !== "manual") setSelectedAgents([]);
              }}
              onAgentsChange={setSelectedAgents}
            />
          </div>
          <div className="scrollbar-subtle flex-1 overflow-y-auto p-4 sm:p-6">
            {!activeChat ? (
              <EmptyState
                icon={MessageCircleMore}
                title="Start a new conversation"
                description="Choose how AION should collaborate, then describe the outcome you want."
              />
            ) : messages.length === 0 && !sending ? (
              <EmptyState
                title="No messages yet"
                description="Send a message to begin coordinating with AION."
              />
            ) : (
              <div className="mx-auto max-w-3xl space-y-5">
                {messages.map((message, index) =>
                  message.role === "user" ? (
                    <div key={message.id} className="flex justify-end gap-3">
                      <div className="max-w-[82%] rounded-[22px] rounded-tr-md bg-navy px-4 py-3 text-sm leading-6 text-white">
                        <p>{message.content}</p>
                      </div>
                      <span className="grid size-9 shrink-0 place-items-center rounded-full bg-[#e9edf2] text-navy">
                        <UserRound className="size-4" />
                      </span>
                    </div>
                  ) : (
                    <AionMessage
                      key={message.id}
                      response={message.response}
                      onRegenerate={() =>
                        void sendPrompt(previousUserMessage(index), message.id)
                      }
                    />
                  ),
                )}
                {sending && (
                  <ProcessingState
                    mode={mode}
                    selectedAgents={selectedAgents}
                    taskId={sseTaskId}
                    onTaskId={setSseTaskId}
                  />
                )}
                {failedPrompt && !sending && (
                  <ChatErrorState
                    onRetry={() => void sendPrompt(failedPrompt)}
                    onQuick={retryQuick}
                    errorDetail={errorDetail}
                  />
                )}
              </div>
            )}
          </div>
          <form onSubmit={submit} className="border-t p-4 sm:p-5">
            <div className="mx-auto flex max-w-3xl items-end gap-2 rounded-[26px] border bg-white p-2 pl-4 shadow-[0_6px_22px_rgba(25,36,56,0.06)] focus-within:outline-none focus-within:ring-0">
              <label className="min-w-0 flex-1">
                <span className="sr-only">Message AION</span>

                <textarea
                  value={input}
                  onChange={(event) => setInput(event.target.value)}
                  onKeyDown={(event) => {
                    if (
                      event.key === "Enter" &&
                      !event.shiftKey &&
                      input.trim() &&
                      !sending &&
                      !manualInvalid
                    ) {
                      event.preventDefault();
                      (
                        event.currentTarget.closest("form") as HTMLFormElement
                      )?.requestSubmit();
                    }
                  }}
                  rows={1}
                  placeholder="Ask AION to plan, research or review..."
                  className="
          max-h-28
          min-h-10
          w-full
          resize-none
          border-0
          bg-transparent
          py-2
          text-sm
          outline-none
          ring-0
          focus:border-0
          focus:outline-none
          focus:ring-0
          focus-visible:border-0
          focus-visible:outline-none
          focus-visible:ring-0
          placeholder:text-[#9a9fa7]
        "
                />
              </label>

              <Button
                size="icon"
                type="submit"
                disabled={!input.trim() || sending || manualInvalid}
                aria-label="Send message">
                <Send className="size-4" />
              </Button>
            </div>

            {manualInvalid && (
              <p className="mx-auto mt-2 max-w-3xl text-center text-[10px] text-[#b14a4a]">
                Select at least one agent in Manual Agents mode.
              </p>
            )}
          </form>
        </section>
      </div>
    </>
  );
}
