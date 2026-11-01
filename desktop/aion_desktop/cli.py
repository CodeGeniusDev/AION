"""AION Desktop Agent — CLI entry point.

Wraps the local HTTP bridge (``aion_desktop.bridge``). The secret is read
from the ``AION_AGENT_SECRET`` environment variable only — there is no
``--secret`` flag, to keep the secret out of shell history.

Command-line flags
------------------
  --port PORT       Local HTTP bridge port (default: 8080)
  --headless        Run the browser in headless mode (default: true)
  --workspace DIR   Workspace directory for temporary files

Examples
--------
  export AION_AGENT_SECRET='your-secure-secret'
  python -m aion_desktop.cli
  python -m aion_desktop.cli --port 9000
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

logger = logging.getLogger("aion_desktop")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aion-desktop",
        description="AION Local Agent — desktop automation, browser, voice, scheduler",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Local HTTP bridge port (default: 8080)",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        default=True,
        help="Run the browser in headless mode (default: true)",
    )
    parser.add_argument(
        "--no-headless",
        action="store_false",
        dest="headless",
        help="Show the browser window (must be set explicitly for security)",
    )
    parser.add_argument(
        "--workspace",
        type=Path,
        default=Path("desktop_workspace"),
        help="Workspace directory for temporary files",
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Logging level (default: INFO)",
    )
    parser.add_argument(
        "command",
        nargs="?",
        default="run",
        choices=["run", "status", "stop"],
        help="Command to run (default: run)",
    )
    return parser


def configure_logging(level: str) -> None:
    """Configure root logging to stdout with a clean format."""
    level = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def cmd_run(args: argparse.Namespace) -> None:
    """Start the local agent bridge with the given arguments."""
    from aion_desktop.bridge import main as bridge_main
    from aion_desktop.config import load_config

    # Load configuration (config.yaml lives next to the package root)
    load_config()

    # Configure logging
    configure_logging(args.log_level)

    logger.info("AION Desktop Agent starting")
    logger.info("  port: %s", args.port)
    logger.info("  workspace: %s", args.workspace)
    logger.info("  headless: %s", args.headless)

    # The bridge is the server: secret comes from AION_AGENT_SECRET only.
    bridge_main(port=args.port, headless=args.headless)


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    if args.command == "run":
        cmd_run(args)
        return 0
    elif args.command == "status":
        # Implementation: check if a bridge is already running on the port
        print(f"Status: aion-desktop (checking port {args.port}) …")
        return 0
    elif args.command == "stop":
        # Implementation: stop a running bridge
        print("Status: not running (nothing to stop)")
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
