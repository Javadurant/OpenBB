"""Local-dev reliability contract tests ('Failed to fetch' regression,
2026-07-10): Discover endpoints must return structured JSON errors or a
stale-cache fallback — never crash bare. Recovery scripts must exist, be
executable, pass bash -n, and support --dry-run."""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

_SENTRIQ = pathlib.Path(__file__).resolve().parents[4] / "sentriq"


def test_setup_endpoint_structured_error_when_scan_fails(monkeypatch):
    from api import phase2_router as pr
    monkeypatch.setattr(pr, "_setup_of_the_day_impl",
                        lambda refresh=False: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr(pr, "_SETUP_CACHE", {"key": None, "at": 0.0, "data": None})
    resp = pr.setup_of_the_day(refresh=True)
    assert resp.status_code == 503
    body = json.loads(resp.body)
    assert body["ok"] is False
    err = body["error"]
    for k in ("code", "message", "details", "retryable", "source", "timestamp", "request_id"):
        assert k in err, f"error contract missing {k}"
    assert err["code"] == "SETUP_SCAN_FAILED" and err["retryable"] is True


def test_setup_endpoint_serves_stale_cache_before_error(monkeypatch):
    from api import phase2_router as pr
    monkeypatch.setattr(pr, "_setup_of_the_day_impl",
                        lambda refresh=False: (_ for _ in ()).throw(RuntimeError("boom")))
    good = {"status": "ok", "boxes": {"Swedish": {}}, "total_scored": 5}
    monkeypatch.setattr(pr, "_SETUP_CACHE", {"key": "setup_v3.2", "at": 1.0, "data": good})
    resp = pr.setup_of_the_day(refresh=True)
    assert isinstance(resp, dict)              # stale data, not an error response
    assert resp["stale"] is True and "stale_reason" in resp and "request_id" in resp
    assert resp["total_scored"] == 5           # the last good scan survives


def test_scripts_exist_executable_and_dry_run():
    import os
    scripts = _SENTRIQ / "scripts"
    for name in ("sentriq_doctor.sh", "sentriq_recover.sh", "sentriq_snapshot_good.sh"):
        p = scripts / name
        assert p.exists(), f"{name} missing"
        assert os.access(p, os.X_OK), f"{name} not executable"
        assert subprocess.run(["bash", "-n", str(p)]).returncode == 0, f"{name} syntax"
    dry = subprocess.run(["bash", str(scripts / "sentriq_recover.sh"), "--dry-run"],
                         capture_output=True, text=True, timeout=60)
    assert dry.returncode == 0
    assert "[dry-run]" in dry.stdout
    assert "kill" not in dry.stdout.split("[dry-run]")[0]   # nothing killed before dry-run notice


def test_package_scripts_wired():
    pkg = json.loads((_SENTRIQ / "package.json").read_text())
    for k in ("sentriq:doctor", "sentriq:recover", "sentriq:snapshot-good", "dev:safe"):
        assert k in pkg["scripts"], f"package script {k} missing"


def test_docs_include_vscode_command():
    doc = (_SENTRIQ / "docs" / "local_recovery.md").read_text()
    assert "pnpm sentriq:recover" in doc and "pnpm sentriq:doctor" in doc
    assert "never" in doc.lower()              # documents what it will NOT do
