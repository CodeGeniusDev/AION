"""AION Tool System: safe, discoverable, verifiable tool execution.

Import this package to trigger registration of the built-in deterministic
tools (see tools/builtin.py), mirroring how importing `agents` registers
the four core agents.
"""

from tools import builtin  # noqa: F401 — import triggers tool registration

__all__: list[str] = []
