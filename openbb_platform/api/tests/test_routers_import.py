# api/tests/test_routers_import.py
"""
Module-load smoke tests for every router in api/.

The whole point of this file: catch the exact regression class from
2026-05-10, where ruff --fix removed a `from .postmortem_router import
router as postmortem_router` line that *looked* unused but was needed
by `app.include_router(postmortem_router)` further down in main.py.

If an import is broken (deleted side-effect, missing module, syntax
error), this test fails at collection time — before any user hits the
endpoint. Cheap, deterministic, no network.
"""
import importlib
import pytest


@pytest.mark.parametrize("module_name", [
    "api.main",
    "api.symbol_router",
    "api.phase2_router",
    "api.omnisearch_router",
    "api.bonds_router",
    "api.postmortem_router",
    "api.providers.openfigi",
    "api.providers.nasdaq_nordic",
    "api.providers.funds_library",
    "api.providers.esg",
])
def test_module_imports_without_error(module_name: str) -> None:
    """Importing the module must not raise — catches deleted/renamed imports."""
    importlib.import_module(module_name)


def test_main_app_mounts_every_router() -> None:
    """api.main must register every known router on the FastAPI app.

    If ruff deletes a router-import line, this fails because the route
    prefix is missing from the mounted set."""
    from api.main import app
    paths = [r.path for r in app.routes if hasattr(r, "path")]
    expected_groups = ["/api/symbol", "/api/discover", "/api/omni",
                       "/api/bonds", "/api/postmortem"]
    missing = [g for g in expected_groups if not any(p.startswith(g) for p in paths)]
    assert not missing, f"main.py is missing route groups: {missing}"
