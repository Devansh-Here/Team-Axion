"""T-024: no-egress checks. Code scan + blocked-socket run.
Sirf loopback (127.0.0.1 / localhost / ::1) allowed.
Fail aaye to dusre ki file khud edit mat karo, owner ko batao.
"""
import re
import socket
import sqlite3
from pathlib import Path
from urllib.parse import urlparse

import pytest

APP_DIR = Path(__file__).resolve().parent.parent / "app"
REPO_ROOT = APP_DIR.parent.parent

FORBIDDEN_MODULES = (
    "openai", "anthropic", "cohere", "groq", "mistralai", "replicate", "together",
    "google.generativeai", "google.genai", "vertexai", "huggingface_hub",
    "sentry_sdk", "posthog", "mixpanel", "amplitude", "datadog", "newrelic",
    "opentelemetry", "langsmith", "wandb",
)
FORBIDDEN_PACKAGES = {m.split(".")[0].replace("_", "-") for m in FORBIDDEN_MODULES} | {
    "google-generativeai", "google-genai", "sentry-sdk", "huggingface-hub",
}
NETWORK_MODULES = (
    "httpx", "requests", "urllib.request", "aiohttp", "http.client",
    "websockets", "smtplib", "ftplib", "telnetlib",
)
# Sirf model_client.py ko network library ki ijazat (loopback Ollama)
NETWORK_ALLOWED_FILES = {"model_client.py"}
LOOPBACK = {"127.0.0.1", "localhost", "::1"}

_IMPORT_RE = re.compile(r"^\s*(?:import|from)\s+([A-Za-z0-9_\.]+)", re.M)
_URL_RE = re.compile(r"https?://[^\s\"'\)>\]]+")


def _py_files():
    return [p for p in APP_DIR.rglob("*.py") if "__pycache__" not in p.parts]


def _is(mod, names):
    return any(mod == n or mod.startswith(n + ".") for n in names)


def test_no_hosted_sdk_imports():
    bad = []
    for f in _py_files():
        for mod in _IMPORT_RE.findall(f.read_text(encoding="utf-8", errors="ignore")):
            if _is(mod, FORBIDDEN_MODULES):
                bad.append(f"{f.name}: {mod}")
    assert not bad, f"hosted/telemetry imports mile: {bad}"


def test_only_model_client_uses_network_libs():
    bad = []
    for f in _py_files():
        if f.name in NETWORK_ALLOWED_FILES:
            continue
        for mod in _IMPORT_RE.findall(f.read_text(encoding="utf-8", errors="ignore")):
            if _is(mod, NETWORK_MODULES):
                bad.append(f"{f.name}: {mod}")
    assert not bad, f"network library allowed files ke bahar: {bad}"


def test_no_external_urls_in_code():
    bad = []
    for f in _py_files():
        for url in _URL_RE.findall(f.read_text(encoding="utf-8", errors="ignore")):
            host = urlparse(url).hostname or ""
            if host not in LOOPBACK:
                bad.append(f"{f.name}: {url}")
    assert not bad, f"external URL mile: {bad}"


def test_model_url_default_is_loopback():
    from app import config
    assert urlparse(config.MODEL_BASE_URL).hostname in LOOPBACK


def test_requirements_have_no_hosted_sdk():
    candidates = [REPO_ROOT / "requirements.txt", APP_DIR.parent / "requirements.txt"]
    files = [p for p in candidates if p.is_file()]
    assert files, "requirements.txt nahi mili"
    bad = []
    for p in files:
        for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            name = re.split(r"[=<>!~\[ ;]", line, 1)[0].lower().replace("_", "-")
            if name in FORBIDDEN_PACKAGES:
                bad.append(name)
    assert not bad, f"requirements mein hosted/telemetry package: {bad}"


# ---------------- blocked-socket run ----------------
class EgressBlocked(OSError):
    pass


@pytest.fixture
def no_net(monkeypatch):
    attempts = []

    def _host(address):
        return address[0] if isinstance(address, tuple) else None

    def guarded(orig):
        def wrapper(self, address, *a, **k):
            host = _host(address)
            if host is not None and host not in LOOPBACK:
                attempts.append(str(host))
                raise EgressBlocked("egress blocked")
            return orig(self, address, *a, **k)
        return wrapper

    monkeypatch.setattr(socket.socket, "connect", guarded(socket.socket.connect))
    monkeypatch.setattr(socket.socket, "connect_ex", guarded(socket.socket.connect_ex))

    orig_gai = socket.getaddrinfo

    def gai(host, *a, **k):
        if host not in LOOPBACK and host not in (None, ""):
            attempts.append(str(host))
            raise EgressBlocked("dns blocked")
        return orig_gai(host, *a, **k)

    monkeypatch.setattr(socket, "getaddrinfo", gai)
    return attempts


def test_blocker_really_blocks(no_net):
    with pytest.raises(EgressBlocked):
        socket.create_connection(("93.184.216.34", 80), timeout=1)
    with pytest.raises(EgressBlocked):
        socket.getaddrinfo("example.com", 80)
    assert no_net


def test_guard_policy_executor_work_offline(no_net, tmp_path):
    from app.executor import execute_read_only
    from app.policy import authorize
    from app.sql_guard import Allow, validate_candidate

    db = tmp_path / "t.sqlite"
    c = sqlite3.connect(db)
    c.execute("CREATE TABLE sales (order_id INTEGER, net_amt REAL)")
    c.execute("INSERT INTO sales VALUES (1, 10.0)")
    c.commit()
    c.close()

    assert authorize("analyst", "demo", "total net sales").action == "ALLOW"
    sql = "SELECT SUM(net_amt) FROM sales"
    assert isinstance(validate_candidate(sql, {"sales"}, {"sales.net_amt"}), Allow)
    out = execute_read_only(str(db), sql, [], timeout_s=2, max_rows=10, max_bytes=10000)
    assert out.status == "OK" and out.rows[0][0] == 10.0
    assert no_net == []


def test_api_and_analyze_work_offline(no_net, tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from app import config, main

    monkeypatch.setattr(config, "METADATA_DB", str(tmp_path / "m.sqlite"))
    with TestClient(main.app, raise_server_exceptions=False) as client:
        assert client.get("/api/v1/health").status_code == 200
        client.post("/api/v1/analyze",
                    json={"dataset_id": "demo", "question": "total net sales by category"})
    assert no_net == [], f"bahar connect karne ki koshish: {no_net}"