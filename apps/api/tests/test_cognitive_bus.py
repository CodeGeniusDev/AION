"""Tests for the Universal Cognitive Bus (cognitive_bus/bus.py). Covers
publish, subscribe, unsubscribe, targeted delivery, broadcast delivery,
task isolation, ordering, replay/history, duplicate subscriptions, and
unknown-target behavior. WorkflowRunner integration and chat regression
tests live in test_api.py alongside the existing chat tests.
"""

import pytest

from cognitive_bus import CognitiveBus, CognitiveMessage
from models.cognitive_dna import Domain


def _message(**overrides) -> CognitiveMessage:
    defaults = dict(task_id="task-1", source_agent="aion", target_agent="planner", intent="execute", content="do the thing")
    defaults.update(overrides)
    return CognitiveMessage(**defaults)


# ---------------------------------------------------------------------------
# Publish / retrieval
# ---------------------------------------------------------------------------


def test_publish_returns_the_message() -> None:
    bus = CognitiveBus()
    message = _message()
    result = bus.publish(message)
    assert result is message


def test_publish_is_retrievable_by_message_id() -> None:
    bus = CognitiveBus()
    message = bus.publish(_message())
    assert bus.get_message(message.message_id) is message


def test_get_message_returns_none_for_unknown_id() -> None:
    bus = CognitiveBus()
    assert bus.get_message("does-not-exist") is None


def test_each_published_message_has_a_unique_id() -> None:
    bus = CognitiveBus()
    first = bus.publish(_message())
    second = bus.publish(_message())
    assert first.message_id != second.message_id


# ---------------------------------------------------------------------------
# Task isolation
# ---------------------------------------------------------------------------


def test_task_isolation_keeps_different_tasks_separate() -> None:
    bus = CognitiveBus()
    bus.publish(_message(task_id="task-a", source_agent="planner", target_agent="researcher"))
    bus.publish(_message(task_id="task-a", source_agent="researcher", target_agent="critic"))
    bus.publish(_message(task_id="task-b", source_agent="planner", target_agent="memory"))

    task_a_messages = bus.get_task_messages("task-a")
    task_b_messages = bus.get_task_messages("task-b")

    assert len(task_a_messages) == 2
    assert len(task_b_messages) == 1
    assert all(message.task_id == "task-a" for message in task_a_messages)
    assert all(message.task_id == "task-b" for message in task_b_messages)


def test_get_task_messages_for_unknown_task_returns_empty_list() -> None:
    bus = CognitiveBus()
    assert bus.get_task_messages("never-published") == []


# ---------------------------------------------------------------------------
# Ordering
# ---------------------------------------------------------------------------


def test_task_messages_preserve_publish_order() -> None:
    bus = CognitiveBus()
    bus.publish(_message(task_id="task-1", content="first"))
    bus.publish(_message(task_id="task-1", content="second"))
    bus.publish(_message(task_id="task-1", content="third"))

    contents = [message.content for message in bus.get_task_messages("task-1")]
    assert contents == ["first", "second", "third"]


# ---------------------------------------------------------------------------
# Subscribe / targeted delivery
# ---------------------------------------------------------------------------


def test_subscribe_receives_targeted_messages() -> None:
    bus = CognitiveBus()
    received: list[CognitiveMessage] = []
    bus.subscribe("agent:researcher", received.append)

    bus.publish(_message(target_agent="researcher"))

    assert len(received) == 1
    assert received[0].target_agent == "researcher"


def test_subscribe_does_not_receive_messages_for_other_targets() -> None:
    bus = CognitiveBus()
    received: list[CognitiveMessage] = []
    bus.subscribe("agent:researcher", received.append)

    bus.publish(_message(target_agent="critic"))

    assert received == []


def test_publish_to_target_with_no_subscribers_does_not_raise() -> None:
    bus = CognitiveBus()
    message = bus.publish(_message(target_agent="nobody-is-listening"))
    assert message.status == "pending"
    assert bus.get_task_messages(message.task_id) == [message]


# ---------------------------------------------------------------------------
# Broadcast delivery
# ---------------------------------------------------------------------------


def test_broadcast_message_delivered_to_broadcast_subscriber() -> None:
    bus = CognitiveBus()
    received: list[CognitiveMessage] = []
    bus.subscribe("broadcast:task-1", received.append)

    bus.publish(_message(task_id="task-1", target_agent=None, intent="status_update"))

    assert len(received) == 1


def test_broadcast_message_not_delivered_to_specific_agent_subscriber() -> None:
    bus = CognitiveBus()
    received: list[CognitiveMessage] = []
    bus.subscribe("agent:planner", received.append)

    bus.publish(_message(target_agent=None))

    assert received == []


def test_targeted_message_not_delivered_to_broadcast_subscriber() -> None:
    bus = CognitiveBus()
    received: list[CognitiveMessage] = []
    bus.subscribe("broadcast:task-1", received.append)

    bus.publish(_message(task_id="task-1", target_agent="planner"))

    assert received == []


# ---------------------------------------------------------------------------
# Task-level subscription (every message in a task, regardless of target)
# ---------------------------------------------------------------------------


def test_task_topic_subscriber_receives_both_targeted_and_broadcast_messages() -> None:
    bus = CognitiveBus()
    received: list[CognitiveMessage] = []
    bus.subscribe("task:task-1", received.append)

    bus.publish(_message(task_id="task-1", target_agent="planner"))
    bus.publish(_message(task_id="task-1", target_agent=None))

    assert len(received) == 2


# ---------------------------------------------------------------------------
# Unsubscribe / duplicate subscriptions
# ---------------------------------------------------------------------------


def test_unsubscribe_stops_further_delivery() -> None:
    bus = CognitiveBus()
    received: list[CognitiveMessage] = []
    subscription_id = bus.subscribe("agent:planner", received.append)

    bus.publish(_message(target_agent="planner"))
    removed = bus.unsubscribe(subscription_id)
    bus.publish(_message(target_agent="planner"))

    assert removed is True
    assert len(received) == 1


def test_unsubscribe_unknown_id_returns_false() -> None:
    bus = CognitiveBus()
    assert bus.unsubscribe("sub-does-not-exist") is False


def test_duplicate_subscriptions_to_same_topic_both_fire() -> None:
    bus = CognitiveBus()
    first_received: list[CognitiveMessage] = []
    second_received: list[CognitiveMessage] = []
    bus.subscribe("agent:planner", first_received.append)
    bus.subscribe("agent:planner", second_received.append)

    bus.publish(_message(target_agent="planner"))

    assert len(first_received) == 1
    assert len(second_received) == 1


# ---------------------------------------------------------------------------
# consume() — pull-based history by topic
# ---------------------------------------------------------------------------


def test_consume_returns_all_historical_matches_without_requiring_subscription() -> None:
    bus = CognitiveBus()
    bus.publish(_message(target_agent="planner", content="one"))
    bus.publish(_message(target_agent="planner", content="two"))
    bus.publish(_message(target_agent="critic", content="three"))

    results = bus.consume("agent:planner")
    assert [message.content for message in results] == ["one", "two"]


def test_consume_unknown_topic_returns_empty_list() -> None:
    bus = CognitiveBus()
    bus.publish(_message())
    assert bus.consume("agent:nobody") == []


# ---------------------------------------------------------------------------
# Replay / clear
# ---------------------------------------------------------------------------


def test_replay_matches_get_task_messages() -> None:
    bus = CognitiveBus()
    bus.publish(_message(task_id="task-1"))
    bus.publish(_message(task_id="task-1"))
    assert bus.replay("task-1") == bus.get_task_messages("task-1")


def test_clear_task_removes_history_but_leaves_other_tasks_intact() -> None:
    bus = CognitiveBus()
    bus.publish(_message(task_id="task-a"))
    bus.publish(_message(task_id="task-b"))

    bus.clear_task("task-a")

    assert bus.get_task_messages("task-a") == []
    assert len(bus.get_task_messages("task-b")) == 1


def test_clear_task_on_unknown_task_does_not_raise() -> None:
    bus = CognitiveBus()
    bus.clear_task("never-existed")  # should not raise


# ---------------------------------------------------------------------------
# Handler exceptions — documented semantics
# ---------------------------------------------------------------------------


def test_handler_exception_propagates_and_message_is_still_recorded() -> None:
    bus = CognitiveBus()

    def _broken_handler(_message: CognitiveMessage) -> None:
        raise RuntimeError("subscriber failure")

    bus.subscribe("agent:planner", _broken_handler)

    with pytest.raises(RuntimeError):
        bus.publish(_message(target_agent="planner"))

    # Recording happens before dispatch, so the message is retrievable
    # even though the subscriber raised.
    assert len(bus.get_task_messages("task-1")) == 1


# ---------------------------------------------------------------------------
# subscribe_domain — AgentRegistry-driven, no hardcoded agent ids
# ---------------------------------------------------------------------------


def test_subscribe_domain_resolves_agents_via_registry_not_hardcoded_ids() -> None:
    import agents  # noqa: F401 — ensures the four core agents are registered
    from agents.registry import registry as global_registry

    bus = CognitiveBus()
    received: list[CognitiveMessage] = []
    bus.subscribe_domain(Domain.PLANNING, received.append, agent_registry=global_registry)

    bus.publish(_message(target_agent="planner"))

    assert len(received) == 1


def test_subscribe_domain_with_no_matching_agents_subscribes_to_nothing() -> None:
    from agents.registry import AgentRegistry

    bus = CognitiveBus()
    received: list[CognitiveMessage] = []
    empty_registry = AgentRegistry()

    subscription_ids = bus.subscribe_domain(Domain.PLANNING, received.append, agent_registry=empty_registry)

    assert subscription_ids == []
    bus.publish(_message(target_agent="planner"))
    assert received == []
