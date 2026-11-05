"""Security tests: desktop tools must not leak into Gemini function declarations.

Desktop/file/browser/social tools are isolated in a private registry
(desktop_registry) and must never be exposed to Gemini via
tools_to_declarations(). Only safe builtin tools (calculator, text_analysis,
current_datetime) should be in the global registry.
"""

from tools.registry import registry  # noqa: E402
from tools.local_tools import desktop_registry  # noqa: E402
from tools.local_tools import FileReadTool  # noqa: E402


def test_global_registry_contains_only_safe_builtin_tools() -> None:
    """The global registry must only contain calculator, text_analysis, current_datetime."""
    tool_ids = [id.id for id in registry.list_identities()]
    assert tool_ids == ["calculator", "text_analysis", "current_datetime"]


def test_desktop_registry_is_separate_from_global() -> None:
    """Desktop tools must be in a separate registry, not the global one."""
    desktop_ids = set(desktop_registry.list_tool_ids())
    global_ids = set(id.id for id in registry.list_identities())

    # No overlap
    assert desktop_ids.isdisjoint(global_ids)

    # Desktop registry has the expected tools
    # (file_read, file_write, file_copy are the only local tools registered
    #  in the desktop_registry; broader desktop browser/desktop tools live
    #  in desktop/aion_desktop/browser.py, files.py, etc.)
    expected_desktop = {"file_read", "file_write", "file_copy"}
    assert desktop_ids == expected_desktop


def test_gemini_declarations_exclude_desktop_tools() -> None:
    """Gemini function declarations must never include desktop_*, browser_*, file_*, social_* tools."""
    from tools.schema import tools_to_declarations

    # Convert global registry to declarations (what Gemini sees)
    declarations = tools_to_declarations(registry.list_identities())
    tool_ids = [decl.get("name", "") for decl in declarations]

    # No desktop tools
    assert not any(tid.startswith("desktop_") for tid in tool_ids), \
        f"Desktop tools leaked to Gemini: {[t for t in tool_ids if t.startswith('desktop_')]}"

    # No browser tools
    assert not any(tid.startswith("browser_") for tid in tool_ids), \
        f"Browser tools leaked to Gemini: {[t for t in tool_ids if t.startswith('browser_')]}"

    # No file tools
    assert not any(tid.startswith("file_") for tid in tool_ids), \
        f"File tools leaked to Gemini: {[t for t in tool_ids if t.startswith('file_')]}"

    # No social tools
    assert not any(tid.startswith("social_") for tid in tool_ids), \
        f"Social tools leaked to Gemini: {[t for t in tool_ids if t.startswith('social_')]}"

    # Only safe builtin tools present
    assert set(tool_ids) == {"calculator", "text_analysis", "current_datetime"}


def test_approval_status_exists_and_transitions_correctly() -> None:
    """Desktop actions require approval (pending_approval status)."""
    from services.task_service import create_task, update_task_status

    # Create a task requiring approval
    task = create_task("Test desktop action", status="pending_approval")
    assert task.status == "pending_approval"

    # Approve the task (should auto-transition to running)
    approved = update_task_status(task.id, "approved")
    assert approved is not None
    assert approved.status == "running"  # Auto-transition on approval

    # Test other status transitions work normally
    updated = update_task_status(task.id, "completed")
    assert updated is not None
    assert updated.status == "completed"


def test_file_tools_prevent_symlink_traversal() -> None:
    """File tools must resolve symlinks before allowlist check to prevent traversal."""
    import asyncio
    import tempfile
    from pathlib import Path
    from tools.local_tools import FileReadTool, FileWriteTool, FileCopyTool, DEFAULT_ALLOWED_DIRS

    async def _run_test():
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            allowed_dir = tmpdir / "allowed"
            allowed_dir.mkdir()

            # Create a real file in allowed directory
            real_file = allowed_dir / "secret.txt"
            real_file.write_text("secret content")

            # Create a symlink in allowed directory pointing outside
            outside_dir = tmpdir / "outside"
            outside_dir.mkdir()
            outside_file = outside_dir / "outside.txt"
            outside_file.write_text("outside content")

            symlink = allowed_dir / "escape_link"
            symlink.symlink_to(outside_file)

            # Test read: should reject symlink pointing outside
            tool = FileReadTool()
            result = await tool.execute(
                "task-test",
                {"path": str(symlink), "allowed_dirs": [allowed_dir]},
            )
            assert not result.success
            assert "resolves outside the allowed directories" in result.error.lower()

            # Test write: should reject symlink pointing outside
            write_tool = FileWriteTool()
            result = await write_tool.execute(
                "task-test",
                {"path": str(symlink), "content": "test", "allowed_dirs": [allowed_dir]},
            )
            assert not result.success
            assert "resolves outside the allowed directories" in result.error.lower()

            # Test direct path traversal via ../
            result = await tool.execute(
                "task-test",
                {"path": str(allowed_dir / "../outside" / "outside.txt"), "allowed_dirs": [allowed_dir]},
            )
            assert not result.success
            assert "resolves outside the allowed directories" in result.error.lower()

            # Test absolute path outside allowlist
            result = await tool.execute(
                "task-test",
                {"path": str(outside_file), "allowed_dirs": [allowed_dir]},
            )
            assert not result.success
            assert "resolves outside the allowed directories" in result.error.lower()

            # Test symlink inside allowlist pointing to file inside allowlist (should succeed)
            internal_file = allowed_dir / "internal.txt"
            internal_file.write_text("internal content")
            internal_symlink = allowed_dir / "internal_link"
            internal_symlink.symlink_to(internal_file)
            result = await tool.execute(
                "task-test",
                {"path": str(internal_symlink), "allowed_dirs": [allowed_dir]},
            )
            assert result.success

            # Test circular symlink (symlink pointing to own directory)
            circular_symlink = allowed_dir / "circular"
            circular_symlink.symlink_to(allowed_dir)
            result = await tool.execute(
                "task-test",
                {"path": str(circular_symlink / "secret.txt"), "allowed_dirs": [allowed_dir]},
            )
            # Should not crash; handled gracefully during resolution

    asyncio.run(_run_test())
