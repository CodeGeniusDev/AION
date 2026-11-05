"""File tools for the AION Desktop Operating System MVP.

These tools perform file operations on the local Mac, restricted to the
directories listed in the local agent's config.yaml (the allowed_dirs
allowlist). The implementation normalizes macOS ``/private`` prefixes so
allowlist comparisons work on all platforms, and resolves symlinks before
checking the allowlist to prevent path-traversal and symlink-escape
attacks.

Tool IDs (registered in local_tools.py):
    file_read, file_write, file_copy
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

from tools.base import BaseTool, ToolOutput
from tools.registry import ToolRegistry, ToolIdentity, BaseTool as BaseToolType, registry as global_registry
from models.cognitive_dna import CapabilityTag, Domain, AvailabilityStatus
from models.tool import ToolIdentity as ToolIdentityType


# Desktop tools share a private registry that is never exposed to Gemini
# or the global registry. This is created and populated when the module
# is imported (mirroring tools/builtin.py).
desktop_registry = ToolRegistry()


# Default directories allowed for file operations.
# Can be overridden by the agent's config.yaml (allowed_dirs key).
DEFAULT_ALLOWED_DIRS = [
    Path.home() / "Desktop",
    Path.home() / "Documents",
    Path.home() / "Downloads",
    Path.home() / "Applications",
]


def _register_tool(tool_class: type[BaseToolType]) -> None:
    """Register a single tool in the desktop_registry."""
    identity = ToolIdentityType(
        id=tool_class.id,
        name=tool_class.name,
        description=f"Desktop tool: {tool_class.name}",
        capabilities=[CapabilityTag(name=tool_class.id, domain=Domain.DESKTOP, declared_proficiency=0.9)],
        domains=[Domain.DESKTOP],
        timeout_seconds=2.0,
        requires_verification=True,
        version="1.0.0",
        provenance="aion-core",
        availability=AvailabilityStatus.ONLINE,
    )
    desktop_registry.register(identity, tool_class())


class FileReadTool(BaseTool):
    """Read a text file, restricted to allowed directories."""

    id = "file_read"
    name = "File Read"

    async def execute(self, task_id: str, parameters: dict[str, Any]) -> ToolOutput:
        path = str(parameters.get("path", "")).strip()
        if not path:
            return ToolOutput(
                tool_id=self.id, task_id=task_id,
                success=False, error="No 'path' parameter provided.",
            )
        allowed = parameters.get("allowed_dirs", DEFAULT_ALLOWED_DIRS)

        # Resolve the path BEFORE checking the allowlist to prevent
        # symlink and path traversal attacks. The resolved path must be
        # inside the allowlist, and the final file must be a real file
        # (not a symlink pointing outside the allowlist).
        try:
            resolved = Path(path).expanduser().resolve(strict=False)
        except (OSError, RuntimeError) as exc:
            return ToolOutput(
                tool_id=self.id, task_id=task_id, success=False,
                error=f"Invalid path '{path}': {exc}",
            )

        # Normalize both sides: macOS resolves to /private/var/... but
        # allowlists use /var/..., so strip the /private prefix from both
        # resolved and allowed paths so comparisons work on all platforms.
        normalized = str(resolved).replace("/private", "", 1)
        normalized_allowed = [str(a).replace("/private", "", 1) for a in allowed]

        if not any(normalized == a or Path(normalized).is_relative_to(a) for a in normalized_allowed):
            return ToolOutput(
                tool_id=self.id, task_id=task_id, success=False,
                error=f"Path '{path}' resolves outside the allowed directories. "
                      f"Allowed: {allowed}",
            )

        # Check each component of the path is not a symlink pointing outside
        # the allowlist. This prevents a symlink inside the allowlist from
        # pointing to a file outside the allowlist.
        try:
            parts = resolved.parts
            for i in range(1, len(parts) + 1):
                partial = Path(*parts[:i])
                if partial.is_symlink():
                    # If this is a symlink, its real path must still be inside
                    # the allowed directories
                    real = os.path.realpath(partial)
                    real_normalized = str(real).replace("/private", "", 1)
                    if not any(real_normalized == a or Path(real_normalized).is_relative_to(a) for a in normalized_allowed):
                        return ToolOutput(
                            tool_id=self.id, task_id=task_id, success=False,
                            error=f"Symlink '{partial}' points outside the "
                                  f"allowed directories. Allowed: {allowed}",
                        )
        except (OSError, RuntimeError):
            # If we can't check symlinks, rely on the resolved path check
            # already performed above
            pass

        try:
            content = resolved.read_text(encoding="utf-8")
            return ToolOutput(
                tool_id=self.id, task_id=task_id, success=True,
                content=f"Read {len(content)} chars from {resolved}.",
                data={"path": str(resolved), "content": content, "size": len(content)},
            )
        except PermissionError as exc:
            return ToolOutput(
                tool_id=self.id, task_id=task_id, success=False,
                error=f"Permission denied reading '{resolved}': {exc}",
            )
        except UnicodeDecodeError as exc:
            return ToolOutput(
                tool_id=self.id, task_id=task_id, success=False,
                error=f"File is not valid UTF-8 text: {exc}",
            )
        except Exception as exc:
            return ToolOutput(
                tool_id=self.id, task_id=task_id, success=False,
                error=f"Could not read file '{resolved}': {exc}",
            )


class FileWriteTool(BaseTool):
    """Write a text file, restricted to allowed directories."""

    id = "file_write"
    name = "File Write"

    async def execute(self, task_id: str, parameters: dict[str, Any]) -> ToolOutput:
        path = str(parameters.get("path", "")).strip()
        content = str(parameters.get("content", ""))
        allowed = parameters.get("allowed_dirs", DEFAULT_ALLOWED_DIRS)
        if not path:
            return ToolOutput(
                tool_id=self.id, task_id=task_id,
                success=False, error="No 'path' parameter provided.",
            )
        # Resolve the path BEFORE checking the allowlist to prevent
        # symlink and path traversal attacks.
        try:
            resolved = Path(path).expanduser().resolve(strict=False)
        except (OSError, RuntimeError) as exc:
            return ToolOutput(
                tool_id=self.id, task_id=task_id, success=False,
                error=f"Invalid path '{path}': {exc}",
            )

        # Normalize: macOS resolves to /private/var/... but allowlists use
        # /var/..., so strip the /private prefix from both sides.
        normalized = str(resolved).replace("/private", "", 1)
        normalized_allowed = [str(a).replace("/private", "", 1) for a in allowed]

        if not any(normalized == a or Path(normalized).is_relative_to(a) for a in normalized_allowed):
            return ToolOutput(
                tool_id=self.id, task_id=task_id, success=False,
                error=f"Path '{path}' resolves outside the allowed directories. "
                      f"Allowed: {allowed}",
            )

        # Check each component is not a symlink pointing outside
        try:
            parts = resolved.parts
            for i in range(1, len(parts) + 1):
                partial = Path(*parts[:i])
                if partial.is_symlink():
                    real = os.path.realpath(partial)
                    real_normalized = str(real).replace("/private", "", 1)
                    if not any(real_normalized == a or Path(real_normalized).is_relative_to(a) for a in normalized_allowed):
                        return ToolOutput(
                            tool_id=self.id, task_id=task_id, success=False,
                            error=f"Symlink '{partial}' points outside the "
                                  f"allowed directories. Allowed: {allowed}",
                        )
        except (OSError, RuntimeError):
            pass

        try:
            p = resolved
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
            return ToolOutput(
                tool_id=self.id, task_id=task_id, success=True,
                content=f"Wrote {len(content)} chars to {p}.",
                data={"path": str(p), "size": len(content)},
            )
        except Exception as exc:
            return ToolOutput(
                tool_id=self.id, task_id=task_id, success=False,
                error=f"Could not write file: {exc}",
            )


class FileCopyTool(BaseTool):
    """Copy a file, restricted to allowed directories."""

    id = "file_copy"
    name = "File Copy"

    async def execute(self, task_id: str, parameters: dict[str, Any]) -> ToolOutput:
        src = str(parameters.get("source", "")).strip()
        dest = str(parameters.get("destination", "")).strip()
        allowed = parameters.get("allowed_dirs", DEFAULT_ALLOWED_DIRS)
        if not src or not dest:
            return ToolOutput(
                tool_id=self.id, task_id=task_id,
                success=False, error="No 'source' or 'destination' parameter provided.",
            )

        # Resolve both paths BEFORE allowlist checks
        try:
            src_resolved = Path(src).expanduser().resolve(strict=False)
            dest_resolved = Path(dest).expanduser().resolve(strict=False)
        except (OSError, RuntimeError) as exc:
            return ToolOutput(
                tool_id=self.id, task_id=task_id, success=False,
                error=f"Invalid paths: {exc}",
            )

        # Normalize both sides: strip /private prefix (macOS)
        src_normalized = str(src_resolved).replace("/private", "", 1)
        dest_normalized = str(dest_resolved).replace("/private", "", 1)
        src_normalized_allowed = [str(a).replace("/private", "", 1) for a in allowed]
        dest_normalized_allowed = [str(a).replace("/private", "", 1) for a in allowed]

        # Source must be inside allowlist
        if not any(src_normalized == a or Path(src_normalized).is_relative_to(a) for a in src_normalized_allowed):
            return ToolOutput(
                tool_id=self.id, task_id=task_id, success=False,
                error=f"Source path '{src}' resolves outside the allowed directories. "
                      f"Allowed: {allowed}",
            )

        # Destination must be inside allowlist
        if not any(dest_normalized == a or Path(dest_normalized).is_relative_to(a) for a in dest_normalized_allowed):
            return ToolOutput(
                tool_id=self.id, task_id=task_id, success=False,
                error=f"Destination path '{dest}' resolves outside the allowed directories. "
                      f"Allowed: {allowed}",
            )

        # Check each component is not a symlink pointing outside
        try:
            for label, path_resolved in [("source", src_resolved), ("destination", dest_resolved)]:
                parts = path_resolved.parts
                for i in range(1, len(parts) + 1):
                    partial = Path(*parts[:i])
                    if partial.is_symlink():
                        real = os.path.realpath(partial)
                        real_normalized = str(real).replace("/private", "", 1)
                        allowed_for = src_normalized_allowed if label == "source" else dest_normalized_allowed
                        if not any(real_normalized == a or Path(real_normalized).is_relative_to(a) for a in allowed_for):
                            return ToolOutput(
                                tool_id=self.id, task_id=task_id, success=False,
                                error=f"Symlink '{partial}' ({label}) points outside "
                                      f"the allowed directories. Allowed: {allowed}",
                            )
        except (OSError, RuntimeError):
            pass

        try:
            # Ensure destination parent exists
            dest_resolved.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_resolved, dest_resolved)
            return ToolOutput(
                tool_id=self.id, task_id=task_id, success=True,
                content=f"Copied '{src_resolved}' -> '{dest_resolved}' ({src_resolved.stat().st_size} bytes).",
                data={"source": str(src_resolved), "destination": str(dest_resolved), "size": src_resolved.stat().st_size},
            )
        except Exception as exc:
            return ToolOutput(
                tool_id=self.id, task_id=task_id, success=False,
                error=f"Could not copy file: {exc}",
            )


# Register all file tools into the private desktop_registry when the
# module is imported (mirroring how tools/builtin.py registers itself).
_register_tool(FileReadTool)
_register_tool(FileWriteTool)
_register_tool(FileCopyTool)
