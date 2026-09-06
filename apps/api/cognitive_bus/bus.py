"""Universal Cognitive Bus: AION's in-memory task-scoped communication layer.

This is the infrastructure-level implementation for Phase B. It provides
real publish/subscribe delivery, task-isolated message history, and replay
— not merely an append-only log. It intentionally does not reach for
Redis/Kafka/NATS: `CognitiveBusInterface` is the contract a persistent or
distributed implementation would satisfy later without any caller change.

Delivery semantics (documented, not just implied)
---------------------------------------------------
- `publish()` delivers synchronously, in the order subscribers were
  registered for each matching topic. It is not async and does not retry.
- If a subscriber handler raises, the exception propagates out of
  `publish()` immediately; later subscribers for that message are NOT
  called, and the message IS still recorded in history (recording happens
  before dispatch). Callers that need dispatch to be fault-tolerant must
  handle errors inside their own handlers.
- `publish()` to a target with no active subscribers is not an error. The
  message is still recorded and retrievable via `get_task_messages`,
  `get_message`, and `replay`.
- Ordering is publish-call order, per task, per bus instance. There is no
  cross-process ordering guarantee — this is in-memory infrastructure.
- `consume()` is pull-based history lookup (get everything ever published to
  a topic); `subscribe()` is push-based live delivery from the moment of
  subscription onward. Subscribing does not retroactively deliver history —
  call `consume()` or `get_task_messages()` for that.

Topics
------
Three topic families, derived automatically from each message — publishers
never choose a topic explicitly, which keeps routing logic out of agent code:

  - "task:<task_id>"      — every message belonging to a task
  - "agent:<agent_id>"    — messages targeted at one specific agent
  - "broadcast:<task_id>" — messages with target_agent=None within a task

This is deliberately small. Capability/domain-based topics are not
introduced here; `subscribe_domain()` below shows how AgentRegistry can
resolve a domain to concrete "agent:<id>" topics at subscribe time instead,
keeping the bus itself free of any agent-specific or domain-specific logic.
"""

from __future__ import annotations

import itertools
from collections import defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

from cognitive_bus.schema import CognitiveMessage

if TYPE_CHECKING:
    from agents.registry import AgentRegistryInterface
    from models.cognitive_dna import Domain

MessageHandler = Callable[[CognitiveMessage], None]


@dataclass
class _Subscription:
    subscription_id: str
    handler: MessageHandler


class CognitiveBusInterface:
    """Abstract contract. A future persistent/distributed bus implements
    this so WorkflowRunner and future callers never depend on the in-memory
    details below."""

    def publish(self, message: CognitiveMessage) -> CognitiveMessage:
        raise NotImplementedError

    def subscribe(self, topic: str, handler: MessageHandler) -> str:
        raise NotImplementedError

    def unsubscribe(self, subscription_id: str) -> bool:
        raise NotImplementedError

    def consume(self, topic: str) -> list[CognitiveMessage]:
        raise NotImplementedError

    def get_task_messages(self, task_id: str) -> list[CognitiveMessage]:
        raise NotImplementedError

    def get_message(self, message_id: str) -> CognitiveMessage | None:
        raise NotImplementedError

    def replay(self, task_id: str) -> list[CognitiveMessage]:
        raise NotImplementedError

    def clear_task(self, task_id: str) -> None:
        raise NotImplementedError


class CognitiveBus(CognitiveBusInterface):
    """In-memory implementation. Process-lifetime storage, no persistence."""

    def __init__(self) -> None:
        self._messages: list[CognitiveMessage] = []
        self._by_task: dict[str, list[CognitiveMessage]] = defaultdict(list)
        self._by_id: dict[str, CognitiveMessage] = {}
        self._subscribers: dict[str, list[_Subscription]] = defaultdict(list)
        self._subscription_ids = itertools.count(1)

    @staticmethod
    def _topics_for(message: CognitiveMessage) -> list[str]:
        topics = [f"task:{message.task_id}"]
        if message.target_agent is None:
            topics.append(f"broadcast:{message.task_id}")
        else:
            topics.append(f"agent:{message.target_agent}")
        return topics

    def publish(self, message: CognitiveMessage) -> CognitiveMessage:
        self._messages.append(message)
        self._by_task[message.task_id].append(message)
        self._by_id[message.message_id] = message

        for topic in self._topics_for(message):
            for subscription in list(self._subscribers.get(topic, [])):
                subscription.handler(message)
        return message

    def subscribe(self, topic: str, handler: MessageHandler) -> str:
        subscription_id = f"sub-{next(self._subscription_ids)}"
        self._subscribers[topic].append(_Subscription(subscription_id, handler))
        return subscription_id

    def subscribe_domain(
        self, domain: "Domain", handler: MessageHandler, *, agent_registry: "AgentRegistryInterface"
    ) -> list[str]:
        """Subscribe to every currently-registered agent in a Cognitive DNA
        domain, resolved through the AgentRegistry rather than a hardcoded
        agent id list. This is the seam Dynamic Brain Formation (Phase C)
        will build on for capability-based message routing — the bus itself
        never needs to know which concrete agents exist.
        """
        return [
            self.subscribe(f"agent:{identity.id}", handler)
            for identity in agent_registry.find_by_capability(domain=domain, available_only=False)
        ]

    def unsubscribe(self, subscription_id: str) -> bool:
        for subscriptions in self._subscribers.values():
            for subscription in subscriptions:
                if subscription.subscription_id == subscription_id:
                    subscriptions.remove(subscription)
                    return True
        return False

    def consume(self, topic: str) -> list[CognitiveMessage]:
        """Pull-based: every message ever published that matches this
        topic, in publish order. Does not depend on any active subscription."""
        return [message for message in self._messages if topic in self._topics_for(message)]

    def get_task_messages(self, task_id: str) -> list[CognitiveMessage]:
        return list(self._by_task.get(task_id, []))

    def get_message(self, message_id: str) -> CognitiveMessage | None:
        return self._by_id.get(message_id)

    def replay(self, task_id: str) -> list[CognitiveMessage]:
        """Ordered history of a task, for post-hoc tracing/observability.
        Currently identical to get_task_messages — kept as a distinct,
        explicitly-named method because its purpose (answering "what
        happened while processing this task?") is different from routine
        lookup, and a future implementation may add replay-specific
        behavior (e.g. re-dispatching to a new subscriber) without changing
        get_task_messages' contract.
        """
        return self.get_task_messages(task_id)

    def clear_task(self, task_id: str) -> None:
        messages = self._by_task.pop(task_id, [])
        removed_ids = {message.message_id for message in messages}
        if not removed_ids:
            return
        self._messages = [message for message in self._messages if message.message_id not in removed_ids]
        for message_id in removed_ids:
            self._by_id.pop(message_id, None)
