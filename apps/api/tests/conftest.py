import os
import sys
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1]
os.environ["AION_DISABLE_MODEL_CALLS"] = "1"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))
