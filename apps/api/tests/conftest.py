import copy
import os
import sys
from pathlib import Path

import pytest

API_ROOT = Path(__file__).resolve().parents[1]
os.environ["AION_DISABLE_MODEL_CALLS"] = "1"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))


@pytest.fixture(autouse=True)
def _isolate_agent_registry():
    """Snapshot the global Cognitive DNA registry before each test and
    restore it after, so tests that register/mutate/clear the registry
    (directly or via record_run) can never leak state into other tests.
    Identities are mutable (PerformanceHistory), so the snapshot is a deep
    copy rather than a shallow reference copy.
    """
    from agents.registry import registry

    snapshot_identities = copy.deepcopy(registry._identities)
    snapshot_instances = dict(registry._instances)  # agent instances are stateless; shallow copy is sufficient
    yield
    registry._identities = snapshot_identities
    registry._instances = snapshot_instances
