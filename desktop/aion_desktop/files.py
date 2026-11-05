"""File tools for the AION Desktop Operating System MVP.

These tools perform file operations on the local Mac, restricted to the
directories listed in the local agent's config.yaml (the allowed_dirs
allowlist). This is the security boundary for all file access: anything
outside the allowlist is rejected before any I/O happens.

Operations:
  - file_read:  read a text file (restricted path)
  - file_write: write a text file (restricted path, creates dirs as needed)
  - file_copy:  copy a file to an allowed destination

Security
--------
All file tools enforce a path allowlist. Before performing any operation:

1. The raw path is resolved to its absolute form.
2. The resolved path must be inside one of the allowed directories.
3. Each component of the path is checked: if any component is a symlink,
   its real path must still be inside the allowed directories.
4. The final file must be a real file (not a symlink pointing outside).

Paths that fail any of these checks are rejected without performing any
IO, so the user's filesystem is never touched by a rejected operation.
"""

import os
from pathlib import Path
from typing import Any

from models.tool import ToolOutput
from tools.base import BaseTool

# ---------------------------------------------------------------------------
# Default allowed directories
# ---------------------------------------------------------------------------
DEFAULT_ALLOWED_DIRS: tuple[Path, ...] = (
    Path.home() / "Desktop",
    Path.home() / "AION" / "AION" / "desktop_workspace",
)


def _is_path_allowed(file_path: str | Path, allowed_dirs: tuple[Path, ...]) -> bool:
    """Return True if the resolved file path is inside one of the allowed
    directories or is one of the allowed directories itself."""
    try:
        resolved = Path(file_path).expanduser().resolve()
    except (OSError, RuntimeError):
        return False
    return any(resolved == d or resolved.is_relative_to(d) for d in allowed_dirs)


def _check_symlinks_within_allowed(path: Path, allowed_dirs: tuple[Path, ...]) -> bool:
    """Check that no component of *path* is a symlink pointing outside
    allowed_dirs. Returns True if all symlinks are within the allowlist."""
    try:
        parts = path.parts
        for i in range(1, len(parts) + 1):
            partial = Path(*parts[:i])
            if partial.is_symlink():
                real = os.path.realpath(partial)
                if not any(real == a or real.is_relative_to(a) for a in allowed_dirs):
                    return False
    except (OSError, RuntimeError):
        return False
    return True


class FileReadTool(BaseTool):
    """Read a text file, restricted to the allowed directory allowlist."""

    id = "file_read"
    name = "File Read"

    async def execute(self, task_id: str, parameters: dict[str, Any]) -> ToolOutput:
        raw_path = str(parameters.get("path", "")).strip()
        if not raw_path:
            return ToolOutput(
                tool_id=self.id, task_id=task_id,
                success=False, error="No 'path' parameter provided.",
            )

        allowed_dirs = parameters.get("allowed_dirs", DEFAULT_ALLOWED_DIRS)
        if not _is_path_allowed(raw_path, allowed_dirs):
            return ToolOutput(
                tool_id=self.id, task_id=task_id, success=False,
                error=(
                    f"Path '{raw_path}' is outside the allowed directories "
                    f"(allowed: {[str(d) for d in allowed_dirs]})."
                ),
            )

        # Resolve the path BEFORE checking the allowlist to prevent
        # symlink and path traversal attacks.
        try:
            resolved = Path(raw_path).expanduser().resolve(strict=False)
        except (OSError, RuntimeError) as exc:
            return ToolOutput(
                tool_id=self.id, task_id=task_id, success=False,
                error=f"Invalid path '{raw_path}': {exc}",
            )

        if not any(resolved == a or resolved.is_relative_to(a) for a in allowed_dirs):
            return ToolOutput(
                tool_id=self.id, task_id=task_id, success=False,
                error=(
                    f"Path '{raw_path}' resolves outside the allowed "
                    f"directories. Allowed: {allowed_dirs}"
                ),
            )

        # Check that no symlink component points outside the allowlist
        if not _check_symlinks_within_allowed(resolved, allowed_dirs):
            return ToolOutput(
                tool_id=self.id, task_id=task_id, success=False,
                error=(
                    f"Path '{raw_path}' contains a symlink pointing outside "
                    f"the allowed directories. Allowed: {allowed_dirs}"
                ),
            )

        try:
            if not resolved.is_file():
                return ToolOutput(
                    tool_id=self.id, task_id=task_id, success=False,
                    error=f"Path '{resolved}' is not a file.",
                )
            content = resolved.read_text(encoding="utf-8")
            return ToolOutput(
                tool_id=self.id, task_id=task_id, success=True,
                content=f"Read {len(content)} chars from {resolved.relative_to(Path.home())}.",
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
    """Write a text file, restricted to the allowed directory allowlist."""

    id = "file_write"
    name = "File Write"

    async def execute(self, task_id: str, parameters: dict[str, Any]) -> ToolOutput:
        raw_path = str(parameters.get("path", "")).strip()
        content = str(parameters.get("content", ""))
        if not raw_path:
            return ToolOutput(
                tool_id=self.id, task_id=task_id,
                success=False, error="No 'path' parameter provided.",
            )

        allowed_dirs = parameters.get("allowed_dirs", DEFAULT_ALLOWED_DIRS)
        if not _is_path_allowed(raw_path, allowed_dirs):
            return ToolOutput(
                tool_id=self.id, task_id=task_id, success=False,
                error=(
                    f"Path '{raw_path}' is outside the allowed directories "
                    f"(allowed: {[str(d) for d in allowed_dirs]})."
                ),
            )

        # Resolve before allowlist check (symlink protection)
        try:
            resolved = Path(raw_path).expanduser().resolve(strict=False)
        except (OSError, RuntimeError) as exc:
            return ToolOutput(
                tool_id=self.id, task_id=task_id, success=False,
                error=f"Invalid path '{raw_path}': {exc}",
            )

        if not any(resolved == a or resolved.is_relative_to(a) for a in allowed_dirs):
            return ToolOutput(
                tool_id=self.id, task_id=task_id, success=False,
                error=(
                    f"Path '{raw_path}' resolves outside the allowed "
                    f"directories. Allowed: {allowed_dirs}"
                ),
            )

        if not _check_symlinks_within_allowed(resolved, allowed_dirs):
            return ToolOutput(
                tool_id=self.id, task_id=task_id, success=False,
                error=(
                    f"Path '{raw_path}' contains a symlink pointing outside "
                    f"the allowed directories. Allowed: {allowed_dirs}"
                ),
            )

        try:
            # Refuse to write to a path that points outside the allowlist
            # after parent traversal (e.g. "../../../etc/passwd").
            if not _is_path_allowed(str(resolved), allowed_dirs):
                return ToolOutput(
                    tool_id=self.id, task_id=task_id, success=False,
                    error=(
                        f"Path '{resolved}' resolves outside the allowed "
                        f"directories. Allowed: {allowed_dirs}"
                    ),
                )
            resolved.parent.mkdir(parents=True, exist_ok=True)
            resolved.write_text(content, encoding="utf-8")
            return ToolOutput(
                tool_id=self.id, task_id=task_id, success=True,
                content=(
                    f"Wrote {len(content)} chars to {resolved.relative_to(Path.home())}."
                ),
                data={"path": str(resolved), "size": len(content)},
            )
        except PermissionError as exc:
            return ToolOutput(
                tool_id=self.id, task_id=task_id, success=False,
                error=f"Permission denied writing '{resolved}': {exc}",
            )
        except Exception as exc:
            return ToolOutput(
                tool_id=self.id, task_id=task_id, success=False,
                error=f"Could not write file '{resolved}': {exc}",
            )


class FileCopyTool(BaseTool):
    """Copy a file from a source to a destination, both within the allowed
    directory allowlist."""

    id = "file_copy"
    name = "File Copy"

    async def execute(self, task_id: str, parameters: dict[str, Any]) -> ToolOutput:
        raw_src = str(parameters.get("src", "")).strip()
        raw_dest = str(parameters.get("dest", "")).strip()
        if not raw_src:
            return ToolOutput(
                tool_id=self.id, task_id=task_id,
                success=False, error="No 'src' parameter provided.",
            )
        if not raw_dest:
            return ToolOutput(
                tool_id=self.id, task_id=task_id,
                success=False, error="No 'dest' parameter provided.",
            )

        allowed_dirs = parameters.get("allowed_dirs", DEFAULT_ALLOWED_DIRS)
        if not _is_path_allowed(raw_src, allowed_dirs):
            return ToolOutput(
                tool_id=self.id, task_id=task_id, success=False,
                error=(
                    f"Source path '{raw_src}' is outside the allowed "
                    f"directories. Allowed: {allowed_dirs}"
                ),
            )
        if not _is_path_allowed(raw_dest, allowed_dirs):
            return ToolOutput(
                tool_id=self.id, task_id=task_id, success=False,
                error=(
                    f"Destination path '{raw_dest}' is outside the allowed "
                    f"directories. Allowed: {allowed_dirs}"
                ),
            )

        # Resolve both paths before allowlist check
        try:
            src = Path(raw_src).expanduser().resolve(strict=False)
            dest = Path(raw_dest).expanduser().resolve(strict=False)
        except (OSError, RuntimeError) as exc:
            return ToolOutput(
                tool_id=self.id, task_id=task_id, success=False,
                error=f"Invalid path: {exc}",
            )

        if not any(src == a or src.is_relative_to(a) for a in allowed_dirs):
            return ToolOutput(
                tool_id=self.id, task_id=task_id, success=False,
                error=f"Source resolves outside allowed directories: {allowed_dirs}",
            )
        if not any(dest == a or dest.is_relative_to(a) for a in allowed_dirs):
            return ToolOutput(
                tool_id=self.id, task_id=task_id, success=False,
                error=f"Destination resolves outside allowed directories: {allowed_dirs}",
            )

        if not _check_symlinks_within_allowed(src, allowed_dirs):
            return ToolOutput(
                tool_id=self.id, task_id=task_id, success=False,
                error=f"Source contains a symlink pointing outside the allowed directories.",
            )

        try:
            if not src.is_file():
                return ToolOutput(
                    tool_id=self.id, task_id=task_id, success=False,
                    error=f"Source '{src}' is not a file.",
                )
            dest.parent.mkdir(parents=True, exist_ok=True)
            import shutil
            shutil.copy2(src, dest)
            return ToolOutput(
                tool_id=self.id, task_id=task_id, success=True,
                content=f"Copied '{src.relative_to(Path.home())}' to "
                        f"'{dest.relative_to(Path.home())}'.",
                data={"src": str(src), "dest": str(dest)},
            )
        except PermissionError as exc:
            return ToolOutput(
                tool_id=self.id, task_id=task_id, success=False,
                error=f"Permission denied: {exc}",
            )
        except Exception as exc:
            return ToolOutput(
                tool_id=self.id, task_id=task_id, success=False,
                error=f"Could not copy file: {exc}",
            )
