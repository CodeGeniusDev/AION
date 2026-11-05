"""AION Desktop Agent package.

The desktop tools reuse the ``BaseTool``/``ToolOutput`` contracts from the
API app (``apps/api/tools/base.py`` and ``apps/api/models/tool.py``). When
the agent is run standalone (``cd desktop && python -m aion_desktop.bridge``)
that module lives outside the default import path, so add it here once,
relative to the repository root, before any submodule imports occur.
"""

from pathlib import Path
import sys

_API_DIR = Path(__file__).resolve().parents[2] / "apps" / "api"
if _API_DIR.is_dir() and str(_API_DIR) not in sys.path:
    sys.path.insert(0, str(_API_DIR))
