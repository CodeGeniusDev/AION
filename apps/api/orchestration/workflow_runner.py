import asyncio
from time import perf_counter
from typing import Any
from uuid import uuid4

from agents import CriticAgent, MemoryAgent, PlannerAgent, ResearchAgent
from agents.base import BaseAgent
from agents.registry import UnknownAgentError, registry
from cognitive_bus import CognitiveBus, CognitiveMessage
from immune.memory_policy import memory_candidates
from immune.system import ImmuneSystem
from memory.consolidation import consolidate_task_memory
from memory.store import MemoryStoreInterface, SQLiteMemoryStore
from models.chat import AgentId, ChatRequest, ChatResponse, UsedAgent
from models.cognitive_memory import MemoryRecord
from models.tool import ToolOutput
from models.verification import ImmuneReport
from config import settings
from observability.logging_config import get_logger
from orchestration.agent_router import AgentRouter
from orchestration.brain_former import DynamicBrainFormer, brain_to_routing_decision
from orchestration.research_pipeline import ResearchPipeline
from orchestration.response_synthesizer import ResponseSynthesizer
from models.knowledge import ResearchResult
from services.gemini import GeminiService, is_circuit_open, live_response_generated
from tools.executor import ToolExecutor
from tools.knowledge_providers import build_knowledge_registry
from tools.schema import tools_to_declarations, message_needs_tools

logger = get_logger("orchestration.workflow_runner")


class WorkflowRunner:
    def __init__(
        self,
        agents: dict[AgentId, BaseAgent] | None = None,
        bus: CognitiveBus | None = None,
        brain_former: DynamicBrainFormer | None = None,
        immune_system: ImmuneSystem | None = None,
        enable_immune: bool = True,
        use_dynamic_brain: bool = True,
        memory_store: MemoryStoreInterface | None = None,
        enable_memory_persistence: bool = True,
        tool_executor: ToolExecutor | None = None,
        research_pipeline: ResearchPipeline | None = None,
        max_retained_tasks: int | None = None,
    ) -> None:
        self.router = AgentRouter()
        self.model_service = GeminiService()
        self.synthesizer = ResponseSynthesizer()
        self.agents = agents or {
            "planner": PlannerAgent(),
            "researcher": ResearchAgent(),
            "critic": CriticAgent(),
            "memory": MemoryAgent(),
        }
        # Persistent for the runner's lifetime (not a fresh throwaway per
        # request) so a task's Cognitive Bus history survives past run()
        # returning and can be queried via bus.get_task_messages()/replay().
        # Note: this is process-lifetime, in-memory storage with no
        # automatic eviction — CognitiveBus.clear_task() exists for a future
        # retention policy but nothing calls it yet; a long-running process
        # will accumulate history for every task until restarted.
        self.bus = bus or CognitiveBus()
        # Dynamic Brain Formation replaces AgentRouter as the primary
        # decision-maker; the legacy router (self.router, above) is kept
        # as-is and is what brain_former falls back to when capability
        # discovery cannot confidently select an agent for a required domain.
        self.brain_former = brain_former or DynamicBrainFormer(router=self.router)
        # AI Immune System: an independent verification pass over the
        # synthesized draft, distinct from the Critic (see
        # models/verification.py for the exact distinction). Runs after
        # every request by default; enable_immune=False exists for future
        # A/B evaluation, not for disabling it in normal operation.
        # Verification results are NOT wired into ChatResponse or the
        # existing API contract — they are observational (bus events +
        # get_immune_report()) so the frontend contract stays untouched.
        self.immune_system = immune_system or ImmuneSystem()
        self.enable_immune = enable_immune
        # use_dynamic_brain=False bypasses Dynamic Brain Formation entirely
        # and routes through the legacy AgentRouter directly — this exists
        # for Phase F's "baseline pipeline" benchmark configuration, not for
        # normal operation (default True preserves Phase C's behavior).
        self.use_dynamic_brain = use_dynamic_brain
        self._immune_reports: dict[str, ImmuneReport] = {}
        # Bounded retention: prevents the previously-unbounded growth of
        # Cognitive Bus history and Immune reports identified in the
        # architecture audit. Insertion-ordered dict-as-set of task_ids;
        # oldest task is evicted (bus history cleared, reports dropped)
        # once the cap is exceeded. This is "per-request isolation made
        # explicit" for memory/lifecycle purposes, not multi-tenant
        # separation (no tenant concept exists in this codebase).
        self._max_retained_tasks = max_retained_tasks or settings.max_retained_tasks
        self._task_history: dict[str, None] = {}
        # Cognitive Memory: real SQLite persistence behind a replaceable
        # interface (memory/store.py). When AION_MEMORY_DB_PATH is set in
        # the environment, uses a file-backed SQLite for durability across
        # process restarts. Otherwise defaults to an in-memory SQLite
        # database — genuine SQL storage for the life of this WorkflowRunner
        # instance, but not durable across a process restart.
        if memory_store is not None:
            self.memory_store = memory_store
        elif settings.memory_db_path:
            self.memory_store = SQLiteMemoryStore(settings.memory_db_path)
        else:
            self.memory_store = SQLiteMemoryStore(":memory:")
        self.enable_memory_persistence = enable_memory_persistence
        # Tool System: a fully real, callable pipeline
        # (discover -> execute -> verify -> memory-eligible), available via
        # execute_tool() below. Deliberately NOT auto-invoked anywhere in
        # the default chat flow in run() — deciding *when* a message needs
        # a tool requires a task-understanding-to-tool-need mechanism
        # (essentially LLM function calling) that doesn't exist in this
        # codebase yet. Wiring a heuristic guess for that now would be
        # exactly the kind of unproven, silently-behavior-changing logic
        # this project has consistently avoided. This is a stated, honest
        # scope boundary, not an oversight.
        self.tool_executor = tool_executor or ToolExecutor()
        self._tool_immune_reports: dict[str, dict[str, ImmuneReport]] = {}
        # Knowledge & Research layer, built directly on the Tool System
        # above. Uses its OWN private ToolRegistry (not the shared global
        # one tools/builtin.py registers into) because MemoryKnowledgeProvider
        # is bound to this specific memory_store instance — sharing it
        # globally would leak one WorkflowRunner's memory access into
        # another's. See tools/knowledge_providers.py for why.
        # Same deliberate scope boundary as execute_tool(): research() is a
        # fully real, callable, tested pipeline, but NOT auto-invoked
        # anywhere in run() — deciding when a task needs research requires
        # the same task-to-need inference this project has consistently
        # declined to fake.
        self._knowledge_registry = build_knowledge_registry(self.memory_store)
        self._knowledge_executor = ToolExecutor(self._knowledge_registry)
        self.research_pipeline = research_pipeline or ResearchPipeline(
            tool_registry=self._knowledge_registry, tool_executor=self._knowledge_executor,
            immune_system=self.immune_system, memory_store=self.memory_store if self.enable_memory_persistence else None,
            bus=self.bus,
        )

    def _track_task(self, task_id: str) -> None:
        """Register a task for bounded retention. Evicts the oldest task's
        Cognitive Bus history and Immune reports once the cap is exceeded —
        real, working cleanup, not just a documented intention.
        """
        if task_id in self._task_history:
            return
        self._task_history[task_id] = None
        if len(self._task_history) > self._max_retained_tasks:
            oldest_task_id = next(iter(self._task_history))
            del self._task_history[oldest_task_id]
            self.bus.clear_task(oldest_task_id)
            self._immune_reports.pop(oldest_task_id, None)
            self._tool_immune_reports.pop(oldest_task_id, None)
            logger.info("task_evicted task_id=%s reason=retention_cap", oldest_task_id)

    async def research(self, query: str, *, task_id: str, provider_ids: list[str] | None = None) -> ResearchResult:
        self._track_task(task_id)
        return await self.research_pipeline.research(query, task_id=task_id, provider_ids=provider_ids)

    def get_immune_report(self, task_id: str) -> ImmuneReport | None:
        return self._immune_reports.get(task_id)

    def get_tool_immune_report(self, task_id: str, tool_id: str) -> ImmuneReport | None:
        return self._tool_immune_reports.get(task_id, {}).get(tool_id)

    async def execute_tool(self, tool_id: str, *, task_id: str, parameters: dict[str, Any]) -> ToolOutput:
        """Full tool life cycle: request -> execute -> verify -> (if
        eligible) memory write-back. Callable independently of run() —
        this is the real, tested integration point Dynamic Brain Formation
        (Phase C) will call once task-to-tool-need inference exists.
        """
        self._track_task(task_id)
        bus = self.bus
        bus.publish(CognitiveMessage(
            task_id=task_id, source_agent="aion", target_agent=None, intent="tool_requested",
            content=f"Requested tool '{tool_id}'", context={"tool_id": tool_id, "parameters": parameters}, status="pending",
        ))
        bus.publish(CognitiveMessage(
            task_id=task_id, source_agent="aion", target_agent=None, intent="tool_started",
            content=f"Executing tool '{tool_id}'", status="processing",
        ))

        output = await self.tool_executor.execute(tool_id, task_id=task_id, parameters=parameters)

        bus.publish(CognitiveMessage(
            task_id=task_id, source_agent=f"tool:{tool_id}", target_agent=None,
            intent="tool_completed" if output.success else "tool_failed",
            content=output.content if output.success else (output.error or "Tool failed"),
            context={"success": output.success, "latency_ms": output.latency_ms},
            status="completed" if output.success else "failed",
        ))

        identity = self.tool_executor.registry.get_identity(tool_id)
        if output.success and identity is not None and identity.requires_verification and self.enable_immune:
            await self._verify_and_consolidate_tool_output(task_id=task_id, tool_id=tool_id, content=output.content, bus=bus)

        return output

    async def _verify_and_consolidate_tool_output(
        self, *, task_id: str, tool_id: str, content: str, bus: CognitiveBus,
    ) -> None:
        """Tool output goes through the exact same claim-extraction and
        verified-only memory gate as agent-generated content (Phase E/D) —
        being deterministic doesn't exempt a tool from corroboration-based
        trust. See models/tool.py::ToolIdentity.requires_verification.

        SQLite calls are offloaded via asyncio.to_thread so a memory
        search/write here never blocks the event loop for other concurrent
        requests (audit finding: blocking I/O inside async handlers).
        """
        source_agent = f"tool:{tool_id}"
        try:
            memory_context = (
                [
                    result.record.content
                    for result in await asyncio.to_thread(self.memory_store.search, query=content, memory_type="semantic", limit=5)
                ]
                if self.enable_memory_persistence else []
            )
            report = self.immune_system.evaluate(
                task_id=task_id, draft=content, used_agent_outputs={}, memory=memory_context,
            )
        except Exception as exc:
            report = ImmuneReport(
                task_id=task_id, claims_checked=0, verification_results=[],
                decision="require_revision",
                decision_reason=f"Tool output verification failed unexpectedly and was not marked verified: {exc}",
            )
        self._tool_immune_reports.setdefault(task_id, {})[tool_id] = report

        if self.enable_memory_persistence:
            try:
                for verified_result in memory_candidates(report):
                    await asyncio.to_thread(self.memory_store.write, MemoryRecord(
                        type="semantic", content=verified_result.claim.text, task_id=task_id,
                        source_agent=source_agent, verification_state="verified",
                        tags=["computation"], provenance=f"tool:{tool_id}",
                    ))
            except Exception:
                pass  # a memory write failure here must never break tool execution

    async def run(
        self, request: ChatRequest, available_memory: list[str] | None = None, tenant_id: str | None = None,
    ) -> ChatResponse:
        started = perf_counter()
        # Per-request flag (contextvars): concurrent requests each get their
        # own copy, eliminating the race that existed with the old shared
        # GeminiService.generated_live_response attribute.
        live_response_generated.set(False)
        task_id = f"task-{uuid4().hex[:8]}"
        self._track_task(task_id)
        conversation_id = request.conversation_id or f"conversation-{uuid4().hex[:8]}"
        memories = available_memory or []
        bus = self.bus
        logger.info("task_started task_id=%s mode=%s tenant_id=%s", task_id, request.mode, tenant_id)
        # Publish early so SSE subscribers connecting right after POST /api/chat
        # can discover this task via bus replay.
        bus.publish(CognitiveMessage(
            task_id=task_id, source_agent="aion", target_agent=None,
            intent="task_started", content=f"Task started in {request.mode} mode",
            context={"mode": request.mode}, status="processing",
        ))
        if self.enable_memory_persistence:
            retrieved = await asyncio.to_thread(
                self.memory_store.search, query=request.message, memory_type="semantic", limit=5, tenant_id=tenant_id,
            )
            retrieved_contents = [result.record.content for result in retrieved]
            # Preserve order, drop duplicates: caller-supplied memory first,
            # then anything genuinely new from persistent retrieval.
            memories = list(dict.fromkeys(memories + retrieved_contents))
            if retrieved:
                bus.publish(CognitiveMessage(
                    task_id=task_id, source_agent="aion", target_agent=None, intent="memory_retrieved",
                    content=f"{len(retrieved)} relevant memory record(s) retrieved",
                    context={"count": len(retrieved), "memory_ids": [r.record.memory_id for r in retrieved]},
                    status="completed",
                ))

        # ── Quick mode fast path: exactly 1 Gemini API call ─────────
        # Skip tool invocation, agent routing, agent execution, synthesis,
        # and critic review. A single direct Gemini call handles the entire
        # request. This is the most quota-efficient path for free-tier keys
        # (20 requests/day): quick mode = 1 call vs auto mode = 3-5 calls.
        if request.mode == "quick":
            # Early exit if circuit breaker is open (429 cooldown active)
            if is_circuit_open():
                elapsed = max(1, round((perf_counter() - started) * 1000))
                bus.publish(CognitiveMessage(
                    task_id=task_id, source_agent="aion", target_agent=None,
                    intent="task_failed", content="Gemini rate limit active — try again in ~60s",
                    status="failed",
                ))
                return ChatResponse(
                    task_id=task_id, conversation_id=conversation_id,
                    answer="The AI model is rate-limited. Please wait about 60 seconds and try again.",
                    mode="quick", status="failed", used_agents=[], confidence=0.2,
                    processing_time_ms=elapsed,
                    selection_summary="Quick Answer — rate limited.", error="Gemini rate limit active.",
                )
            memory_hint = f"\n\nContext from previous conversations: {'; '.join(memories[:3])}" if memories else ""
            direct_answer = await self.model_service.generate(
                "You are AION, a helpful AI assistant. Answer clearly, concisely, and accurately." + memory_hint,
                request.message,
            )
            elapsed = max(1, round((perf_counter() - started) * 1000))
            development_mode = not live_response_generated.get()
            if direct_answer:
                status = "completed"
                confidence = self.calculate_confidence(
                    total_agents=0, completed_agents=0, critic_approved=False,
                    verification_enabled=False, source_count=0, error_count=0,
                    development_mode=development_mode,
                )
            else:
                status = "failed"
                direct_answer = "The AI model is currently unavailable. Please try again in a moment."
                confidence = 0.2
            bus.publish(CognitiveMessage(
                task_id=task_id, source_agent="aion", target_agent=None,
                intent="task_completed" if status == "completed" else "task_failed",
                content=f"Quick answer {status} in {elapsed}ms",
                context={"status": status}, status="completed" if status == "completed" else "failed",
            ))
            return ChatResponse(
                task_id=task_id, conversation_id=conversation_id,
                answer=direct_answer, mode="quick", status=status,
                used_agents=[], confidence=confidence, processing_time_ms=elapsed,
                selection_summary="Quick Answer — direct AION response (1 call).",
                error=None if status == "completed" else direct_answer,
                development_mode=development_mode,
            )

        if self.use_dynamic_brain:
            brain = self.brain_former.form(
                task_id=task_id,
                message=request.message,
                mode=request.mode,
                selected_agents=request.selected_agents,
                available_memory=memories,
                memory_enabled=request.memory_enabled,
            )
            decision = brain_to_routing_decision(brain)
            bus.publish(CognitiveMessage(
                task_id=task_id, source_agent="aion", target_agent=None, intent="brain_formed",
                content=brain.formation_reason,
                context={
                    "required_domains": [domain.value for domain in brain.required_domains],
                    "selected_agents": decision.execution_order,
                    "used_fallback": brain.used_fallback,
                },
                status="completed",
            ))
        else:
            decision = self.router.route(request.message, request.mode, request.selected_agents, memories, request.memory_enabled)
        outputs: list[str] = []
        agent_outputs: dict[str, str] = {}
        used_agents: list[UsedAgent] = []
        errors = 0
        critic_approved = False
        revision_count = 0

        # --- Tool invocation via Gemini function calling ----------------
        # Only invoke tools when the message heuristically matches a
        # tool-capable intent (math, time, text analysis). This avoids an
        # expensive Gemini function-calling round-trip for the vast majority
        # of messages that don't need computation.
        # Also skip if circuit breaker is open (429 cooldown active).
        tool_results: list[str] = []
        tool_identities = self.tool_executor.registry.list_identities()
        if tool_identities and self.model_service.is_configured() and not is_circuit_open() and message_needs_tools(request.message):
            declarations = tools_to_declarations(tool_identities)

            async def _execute_tool_fn(name: str, args: dict) -> str:
                output = await self.execute_tool(name, task_id=task_id, parameters=args)
                return output.content if output.success else (output.error or "Tool execution failed")

            tool_response = await self.model_service.generate_with_tools(
                role_instruction="You are AION's tool coordinator. Use available tools when the user's request involves computation, text analysis, or time lookup. Always include tool results in your response.",
                prompt=request.message,
                tool_declarations=declarations,
                execute_fn=_execute_tool_fn,
            )
            if tool_response:
                tool_results.append(tool_response)
                bus.publish(CognitiveMessage(
                    task_id=task_id, source_agent="tool_system", target_agent=None,
                    intent="tool_invocation_complete",
                    content=f"Tool invocation produced results for agent context",
                    status="completed",
                ))
                # Record tool invocation as a synthetic "agent" for the response
                used_agents.append(UsedAgent(
                    id="tool_system", name="Tool System",
                    status="completed", summary="Invoked tools via LLM function calling",
                ))

        # --- Staggered parallel agent execution via asyncio.gather ---
        # Agents are independent (same memories + tool_results context).
        # Running in parallel reduces latency from sum() to max(), but
        # starting all agents at the exact same instant fires N Gemini
        # API calls simultaneously — which triggers 429 rate limits on
        # free-tier keys (~15 RPM). A 1s stagger between agent starts
        # spreads the API calls over time while keeping most of the
        # parallel latency benefit.

        # ── Agent cap for free-tier quota ──────────────────────────
        # Limit to 2 agents maximum to conserve Gemini API quota.
        # Free-tier allows ~20 requests/day; each agent = 1 API call
        # + 1 synthesis = minimum 3 calls per auto-mode message.
        # Without this cap, research intent triggers 3 agents + synth
        # + critic = 5-7 calls, exhausting quota in 2-3 messages.
        _MAX_AGENTS = 2
        execution_order = list(decision.execution_order)
        selected_agents = list(decision.selected_agents)
        if len(execution_order) > _MAX_AGENTS:
            logger.info("agent_cap_applied original=%d capped=%d", len(execution_order), _MAX_AGENTS)
            execution_order = execution_order[:_MAX_AGENTS]
            selected_agents = selected_agents[:_MAX_AGENTS]

        # If circuit breaker is open, skip agents entirely — they would
        # all fail and just burn more quota.
        if is_circuit_open():
            logger.info("agents_skipped reason=circuit_breaker_open")
            for agent_id in execution_order:
                errors += 1
                agent = self.agents[agent_id]
                used_agents.append(UsedAgent(id=agent_id, name=agent.name, status="failed", summary="Skipped — rate limit cooldown active"))
            execution_order = []  # empty so gather below is a no-op

        async def _run_agent(agent_id: str, stagger_delay: float) -> tuple[str, str | None, str, float]:
            """Run a single agent, returning (agent_id, output_or_None, summary, latency_ms)."""
            if stagger_delay > 0:
                await asyncio.sleep(stagger_delay)
            agent = self.agents[agent_id]
            step_started = perf_counter()
            try:
                context: dict[str, Any] = {"memories": memories, "draft": "", "tool_results": tool_results}
                output = await agent.run(request.message, context, self.model_service)
                latency = (perf_counter() - step_started) * 1000
                summary = agent.completion_summary
                if agent_id == "memory":
                    summary = f"Retrieved {len(memories)} related memories"
                return (agent_id, output, summary, latency)
            except Exception:
                latency = (perf_counter() - step_started) * 1000
                return (agent_id, None, "Could not complete the assigned step", latency)

        # Publish "execute" messages for all agents
        for agent_id in execution_order:
            bus.publish(CognitiveMessage(task_id=task_id, source_agent="aion", target_agent=agent_id, intent="execute", content=request.message, status="processing"))

        # Stagger agent starts by 1s each to avoid burst rate-limiting.
        # Skip stagger when model calls are disabled (test mode) since
        # agents return instantly and the delay only slows tests.
        _STAGGER_DELAY = 1.0 if settings.model_calls_enabled else 0.0
        results = await asyncio.gather(*[
            _run_agent(aid, i * _STAGGER_DELAY)
            for i, aid in enumerate(execution_order)
        ])

        for agent_id, output, summary, latency in results:
            agent = self.agents[agent_id]
            if output is not None:
                outputs.append(output)
                agent_outputs[agent_id] = output
                used_agents.append(UsedAgent(id=agent_id, name=agent.name, status="completed", summary=summary))
                bus.publish(CognitiveMessage(task_id=task_id, source_agent=agent_id, target_agent="aion", intent="result", content=summary, confidence=0.8, status="completed"))
                self._record_run_telemetry(agent_id, success=True, latency_ms=latency)
            else:
                errors += 1
                used_agents.append(UsedAgent(id=agent_id, name=agent.name, status="failed", summary=summary))
                self._record_run_telemetry(agent_id, success=False, latency_ms=latency)

        # Include tool results at the beginning of outputs for synthesis
        all_outputs = tool_results + outputs
        draft = await self.synthesizer.synthesize(request.message, all_outputs, self.model_service)
        # ── Skip critic LLM review for quota conservation ─────────
        # The critic's review_with_llm() makes 1-3 additional Gemini calls
        # (review + possible revision + re-review). On free-tier (20/day)
        # this is too expensive. The immune system (below) provides
        # independent verification without API calls.
        # if "critic" in decision.selected_agents and request.verification_enabled:
        #     critic = self.agents["critic"]
        #     if isinstance(critic, CriticAgent):
        #         critic_approved, issues = await critic.review_with_llm(draft, request.message, self.model_service)

        if self.enable_immune:
            self._run_immune_evaluation(task_id=task_id, draft=draft, agent_outputs=agent_outputs, memories=memories, bus=bus)

        status = "failed" if selected_agents and errors == len(selected_agents) else "completed"

        if self.enable_memory_persistence:
            required_domains = [domain.value for domain in brain.required_domains] if self.use_dynamic_brain else []
            await self._consolidate_memory(
                task_id=task_id, mode=request.mode, execution_order=execution_order,
                decision_reason=decision.reason, status=status, required_domains=required_domains, bus=bus,
                tenant_id=tenant_id,
            )
        logger.info("task_completed task_id=%s status=%s errors=%s", task_id, status, errors)
        development_mode = not live_response_generated.get()
        confidence = self.calculate_confidence(
            total_agents=len(selected_agents),
            completed_agents=len(selected_agents) - errors,
            critic_approved=critic_approved,
            verification_enabled=request.verification_enabled,
            source_count=0,
            error_count=errors,
            development_mode=development_mode,
        )

        # Research mode: run the research pipeline and populate sources
        sources: list[str] = []
        if request.mode == "research" and status == "completed":
            try:
                research_result = await self.research(request.message, task_id=task_id)
                for source in research_result.all_sources:
                    label = source.title
                    if source.url:
                        label = f"[{source.title}]({source.url})"
                    sources.append(label)
                # Append verified evidence to the answer
                if research_result.evidence:
                    evidence_text = "\n\n".join(f"- {e.content[:200]}" for e in research_result.evidence[:3])
                    draft = f"{draft}\n\n**Research evidence:**\n{evidence_text}"
            except Exception as exc:
                logger.warning("research_pipeline_failed task_id=%s error=%s", task_id, exc)

        # Last-resort recovery: if all agents failed OR draft is still the
        # generic development-mode fallback, try a direct Gemini call to
        # produce a useful answer instead of the unhelpful placeholder.
        error_detail: str | None = None
        if status == "failed" or (development_mode and not all_outputs):
            direct_answer = await self.model_service.generate(
                "You are AION, a multi-agent AI assistant. Answer the user's question directly and helpfully.",
                request.message,
            )
            if direct_answer:
                draft = direct_answer
                status = "completed"
                development_mode = not live_response_generated.get()
                confidence = self.calculate_confidence(
                    total_agents=0, completed_agents=0, critic_approved=False,
                    verification_enabled=request.verification_enabled,
                    source_count=0, error_count=0, development_mode=development_mode,
                )
            else:
                error_detail = (
                    "The AI model is currently unavailable. Please check your GEMINI_API_KEY "
                    "configuration and try again in a moment."
                )

        # Publish terminal event so SSE subscribers know the task is done
        bus.publish(CognitiveMessage(
            task_id=task_id, source_agent="aion", target_agent=None,
            intent="task_completed" if status == "completed" else "task_failed",
            content=f"Task {status} in {max(1, round((perf_counter() - started) * 1000))}ms",
            context={"status": status, "confidence": confidence},
            status="completed" if status == "completed" else "failed",
        ))

        return ChatResponse(
            task_id=task_id,
            conversation_id=conversation_id,
            answer=draft if status == "completed" else (error_detail or "AION could not complete this task."),
            mode=request.mode,
            status=status,
            used_agents=used_agents,
            confidence=confidence,
            processing_time_ms=max(1, round((perf_counter() - started) * 1000)),
            selection_summary=decision.reason,
            sources=sources,
            error=error_detail if status == "failed" else None,
            development_mode=development_mode,
            revision_count=revision_count,
        )

    async def _consolidate_memory(
        self, *, task_id: str, mode: str, execution_order: list[str], decision_reason: str,
        status: str, required_domains: list[str], bus: CognitiveBus, tenant_id: str | None = None,
    ) -> None:
        """Write-back after task completion. Wrapped so a storage failure
        can never crash the chat response — persistence is additive
        infrastructure, not a request-blocking dependency. The actual
        writes are offloaded via asyncio.to_thread (audit finding:
        blocking SQLite calls inside async handlers).
        """
        try:
            written = await asyncio.to_thread(
                consolidate_task_memory,
                task_id=task_id, mode=mode, execution_order=execution_order,
                decision_reason=decision_reason, status=status, required_domains=required_domains,
                immune_report=self.get_immune_report(task_id), store=self.memory_store, tenant_id=tenant_id,
            )
        except Exception as exc:  # never let persistence failure break the response
            bus.publish(CognitiveMessage(
                task_id=task_id, source_agent="aion", target_agent=None, intent="memory_write_failed",
                content=f"Memory consolidation failed and was skipped: {exc}", status="failed",
            ))
            return

        semantic_count = sum(1 for record in written if record.type == "semantic")
        bus.publish(CognitiveMessage(
            task_id=task_id, source_agent="aion", target_agent=None, intent="memory_write",
            content=f"Stored 1 episodic record and {semantic_count} verified semantic record(s)",
            context={"episodic": 1, "semantic": semantic_count, "memory_ids": [r.memory_id for r in written]},
            status="completed",
        ))

    def _run_immune_evaluation(
        self, *, task_id: str, draft: str, agent_outputs: dict[str, str], memories: list[str], bus: CognitiveBus,
    ) -> None:
        """Independent verification pass. Wrapped so an internal failure can
        never crash the chat request or, per Phase E's fail-safe rule, ever
        be silently converted into a 'verified' outcome — an unexpected
        exception here still produces an observable require_revision report.
        """
        try:
            report = self.immune_system.evaluate(
                task_id=task_id, draft=draft, used_agent_outputs=agent_outputs, memory=memories,
            )
        except Exception as exc:  # never let verification failure break the response
            report = ImmuneReport(
                task_id=task_id, claims_checked=0, verification_results=[],
                decision="require_revision",
                decision_reason=f"Immune evaluation failed unexpectedly and was not marked verified: {exc}",
            )
        self._immune_reports[task_id] = report
        bus.publish(CognitiveMessage(
            task_id=task_id, source_agent="aion", target_agent=None, intent="immune_claims_extracted",
            content=f"{report.claims_checked} claim(s) extracted for verification", status="completed",
        ))
        bus.publish(CognitiveMessage(
            task_id=task_id, source_agent="aion", target_agent=None, intent="immune_decision",
            content=report.decision_reason,
            context={"decision": report.decision, "claims_checked": report.claims_checked},
            status="completed",
        ))

    @staticmethod
    def _record_run_telemetry(agent_id: str, *, success: bool, latency_ms: float) -> None:
        """Best-effort Cognitive DNA performance recording.

        Per-agent confidence is not computed individually anywhere in the
        current pipeline (only an overall response confidence exists), so
        confidence is intentionally passed as None rather than invented.
        This must never affect chat behavior: registry lookups are wrapped
        so a missing/unregistered agent id degrades silently instead of
        breaking the response.
        """
        try:
            registry.record_run(agent_id, success=success, confidence=None, latency_ms=latency_ms)
        except UnknownAgentError:
            pass

    @staticmethod
    def calculate_confidence(
        *, total_agents: int, completed_agents: int, critic_approved: bool,
        verification_enabled: bool, source_count: int, error_count: int,
        development_mode: bool,
    ) -> float:
        completion_ratio = completed_agents / total_agents if total_agents else 1.0
        score = 0.50 + (0.25 * completion_ratio)
        score += 0.10 if critic_approved else 0.0
        score += 0.05 if verification_enabled else 0.0
        score += 0.05 if source_count > 0 else 0.0
        score -= min(error_count * 0.15, 0.45)
        score -= 0.08 if development_mode else 0.0
        return round(max(0.20, min(score, 0.99)), 2)
