# api/tests/conftest.py
"""
Pytest configuration for the QuantEdge bridge smoke tests.

Adds the openbb_platform root to sys.path so `from api.<router> import ...`
works without needing the package installed editable. Avoids touching
the upstream `tests/` directory (which lives outside this commit's view
and depends on the full openbb-core install graph).
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent  # → openbb_platform/
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
