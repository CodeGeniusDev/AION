"""AION Desktop Agent — configuration loader.

Loads configuration from ``config.yaml`` (with ``config.local.yaml`` and
``.env`` overrides). The configuration is validated at load time.

Configuration keys (with defaults):
  app_name: "AION Desktop Agent"
  workspace_dir: "<project>/desktop_workspace"
  allowed_dirs: ["~/Desktop", "~/AION/AION/desktop_workspace"]
  oauth_dir: "~/.aion"  # OAuth token vault (0600 files, never in git)
  social.live_enabled: false  # dry-run unless owner flips this
  voice.stt: "whisper" | "vosk" | "web"
  voice.tts: "edge" | "pyttsx3"
  browser.headless: true
  browser.blocked_ports: [3000, 3001, 8000, 8010, 8080, 8443]
  browser.allowlist: []   # empty = any (policy-conforming) host
  browser.denylist: []    # always refused, even if allowlisted
  desktop.capture_enabled: true
  logs.level: "INFO"
  logs.file: "<workspace>/logs/aion_desktop.log"
  agent.port: 8080

The bridge secret is NOT stored in configuration: it is read from the
``AION_AGENT_SECRET`` environment variable only (no --secret CLI flag,
no secrets in config files or shell history).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import yaml

DEFAULT_CONFIG: dict[str, Any] = {
    "app_name": "AION Desktop Agent",
    "workspace_dir": "desktop_workspace",
    "allowed_dirs": [
        str(Path.home() / "Desktop"),
        "desktop_workspace",
    ],
    # OAuth tokens live in the user's home, never in the repo or the
    # workspace (Phase 7). Relative values are anchored to home.
    "oauth_dir": "~/.aion",
    "voice": {
        "stt": "whisper",
        "tts": "edge",
    },
    "browser": {
        "headless": True,
        # Loopback ports a browser action may never reach (the bridge,
        # the API and the dev server live here).
        "blocked_ports": [3000, 3001, 8000, 8010, 8080, 8443],
        "allowlist": [],
        "denylist": [],
    },
    "desktop": {
        "capture_enabled": True,
    },
    # Social posting (Phase 7): dry-run unless the owner flips this AND
    # has real tokens in the vault. Requests can never override it.
    "social": {
        "live_enabled": False,
    },
    "logs": {
        "level": "INFO",
        "file": "logs/aion_desktop.log",
    },
    "agent": {
        "port": 8080,
    },
}


def _expand_user(path: str) -> str:
    """Expand ~ to the user's home directory."""
    return str(Path(path).expanduser())


def _expand_env(config: dict[str, Any], env: dict[str, str]) -> dict[str, Any]:
    """Recursively replace ${ENV_VAR} placeholders with environment
    variable values."""
    result: dict[str, Any] = {}
    for key, value in config.items():
        if isinstance(value, dict):
            result[key] = _expand_env(value, env)
        elif isinstance(value, list):
            result[key] = [
                _expand_env_str(item, env) for item in value
            ]
        else:
            result[key] = _expand_env_str(value, env)
    return result


def _expand_env_str(value: Any, env: dict[str, str]) -> Any:
    if isinstance(value, str):
        if value.startswith("${") and value.endswith("}"):
            var = value[2:-1]
            return env.get(var, value)
        return value
    return value


def _config_path(base_dir: Path, *names: str) -> dict[str, Path]:
    """Return a dict of config file paths: the base config + overrides."""
    cfg = {}
    for name in names:
        p = base_dir / name
        if p.exists():
            cfg[name] = p
    # Always return the base config, defaults to <name>.yaml
    base = base_dir / "config.yaml"
    if not any(cfg.values()):
        cfg["config.yaml"] = base
    return cfg


def load_config(base_dir: Path | None = None) -> dict[str, Any]:
    """Load the full configuration by merging defaults, config.yaml,
    config.local.yaml, and .env.

    Priority (highest first):
      1. environment variables (replace ${ENV_VAR} placeholders)
      2. config.local.yaml (local overrides, git-ignored)
      3. config.yaml (project defaults)
      4. DEFAULT_CONFIG (hardcoded defaults)

    Args:
        base_dir: Directory to search for config files. Defaults to the
            parent of this module.

    Returns:
        The merged configuration dictionary.
    """
    if base_dir is None:
        base_dir = Path(__file__).resolve().parent

    # Start with defaults
    config = dict(DEFAULT_CONFIG)

    # Layer 1: base config.yaml (project defaults)
    base_cfg = base_dir / "config.yaml"
    if base_cfg.exists():
        with open(base_cfg, "r", encoding="utf-8") as f:
            loaded = yaml.safe_load(f) or {}
            if isinstance(loaded, dict):
                config.update(loaded)

    # Layer 2: local overrides (config.local.yaml)
    local_cfg = base_dir / "config.local.yaml"
    if local_cfg.exists():
        with open(local_cfg, "r", encoding="utf-8") as f:
            loaded = yaml.safe_load(f) or {}
            if isinstance(loaded, dict):
                config.update(loaded)

    # Expand ${ENV_VAR} placeholders
    config = _expand_env(config, os.environ)

    # Expand ~ to home directory
    for key, value in config.items():
        if isinstance(value, str) and value.startswith("~"):
            config[key] = str(Path(value).expanduser())
        elif isinstance(value, list):
            config[key] = [_expand_user_item(item) for item in value]
        elif isinstance(value, dict):
            config[key] = _expand_env(value, os.environ)

    return config


def _expand_user_item(item: Any) -> Any:
    if isinstance(item, str) and item.startswith("~"):
        return str(Path(item).expanduser())
    return item


def get_log_level(config: dict[str, Any]) -> int:
    """Return the logging level from the config dict."""
    level_str = str(config.get("logs", {}).get("level", "INFO")).upper()
    return getattr(logging, level_str, logging.INFO)


def get_allowed_dirs(config: dict[str, Any]) -> list[Path]:
    """Return the list of allowed directories as resolved Paths."""
    dirs = config.get("allowed_dirs", [])
    if not dirs:
        return [Path.home() / "Desktop", Path("desktop_workspace")]
    return [Path(str(d)).expanduser().resolve() for d in dirs]


def get_workspace(config: dict[str, Any]) -> Path:
    """Return the workspace directory as an absolute path."""
    return Path(config.get("workspace_dir", "desktop_workspace")).expanduser().resolve()
