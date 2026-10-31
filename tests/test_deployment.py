"""Settings defaults, the serverless storage location, and protection of the public endpoint."""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from emporio_agent.api import RateLimiter, create_app
from emporio_agent.config import (
    ANTHROPIC,
    DEFAULT_ANTHROPIC_MODEL,
    DEFAULT_GEMINI_MODEL,
    GEMINI_BASE_URL,
    OPENAI_COMPATIBLE,
    ConfigError,
    Settings,
    load_settings,
)
from emporio_agent.llm import OpenAICompatibleLLM, build_llm

ENV_NAMES = [
    "LLM_PROVIDER", "LLM_MODEL", "LLM_BASE_URL", "LLM_API_KEY", "GEMINI_API_KEY", "ANTHROPIC_API_KEY",
    "DB_PATH", "VERCEL", "AGENT_NOW", "RATE_LIMIT_PER_MINUTE", "RATE_LIMIT_PER_DAY",
]


@pytest.fixture
def clean_env(monkeypatch):
    # The developer's own .env must not influence these tests.
    monkeypatch.setattr("emporio_agent.config.load_dotenv", lambda *_: None)
    for name in ENV_NAMES:
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def test_gemini_is_the_default_and_needs_only_a_key(clean_env):
    clean_env.setenv("LLM_API_KEY", "k")
    settings = load_settings()
    assert settings.provider == OPENAI_COMPATIBLE
    assert settings.model == DEFAULT_GEMINI_MODEL and settings.base_url == GEMINI_BASE_URL
    assert isinstance(build_llm(settings), OpenAICompatibleLLM)


def test_gemini_key_name_is_also_accepted(clean_env):
    clean_env.setenv("GEMINI_API_KEY", "k")
    assert load_settings().api_key == "k"


def test_missing_key_is_explained(clean_env):
    with pytest.raises(ConfigError, match="LLM_API_KEY"):
        build_llm(load_settings())


def test_local_endpoint_needs_no_key(clean_env):
    clean_env.setenv("LLM_BASE_URL", "http://localhost:11434/v1")
    clean_env.setenv("LLM_MODEL", "qwen3:8b")
    assert isinstance(build_llm(load_settings()), OpenAICompatibleLLM)


def test_claude_remains_available(clean_env):
    clean_env.setenv("LLM_PROVIDER", ANTHROPIC)
    clean_env.setenv("ANTHROPIC_API_KEY", "k")
    settings = load_settings()
    assert settings.model == DEFAULT_ANTHROPIC_MODEL and settings.api_key == "k"


def test_database_goes_to_temp_directory_on_vercel(clean_env):
    clean_env.setenv("VERCEL", "1")
    path = load_settings().db_path
    assert path.name == "emporio.db" and Path(__file__).resolve().parents[1] not in path.parents


def test_openai_adapter_bounds_output_tokens():
    from types import SimpleNamespace

    from emporio_agent.llm import MAX_OUTPUT_TOKENS

    recorded = {}

    def create(**kwargs):
        recorded.update(kwargs)
        message = SimpleNamespace(content="ok", tool_calls=None, model_dump=lambda **_: {"role": "assistant"})
        return SimpleNamespace(choices=[SimpleNamespace(message=message, finish_reason="stop")], usage=None)

    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    settings = Settings(OPENAI_COMPATIBLE, "m", "k", "http://x", "low", Path("."), Path("x.db"), None)
    OpenAICompatibleLLM(settings, client=client).complete("s", [], [])
    assert recorded["max_tokens"] == MAX_OUTPUT_TOKENS


class _Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_rate_limit_per_client_recovers_after_a_minute():
    clock = _Clock()
    limiter = RateLimiter(per_minute=2, per_day=100, clock=clock)
    assert limiter.allow("a") and limiter.allow("a")
    assert not limiter.allow("a")
    assert limiter.allow("b")
    clock.now += 60
    assert limiter.allow("a")


def test_rate_limit_per_day_applies_across_clients():
    clock = _Clock()
    limiter = RateLimiter(per_minute=100, per_day=2, clock=clock)
    assert limiter.allow("a") and limiter.allow("b")
    assert not limiter.allow("c")
    clock.now += 86400
    assert limiter.allow("c")


def test_rejected_messages_do_not_consume_the_limit():
    clock = _Clock()
    limiter = RateLimiter(per_minute=1, per_day=2, clock=clock)
    assert limiter.allow("a")
    for _ in range(5):
        assert not limiter.allow("a")
    assert limiter.allow("b")


def test_api_returns_429_envelope_without_calling_the_model(make_agent):
    agent, llm = make_agent(["Oi"])
    client = TestClient(create_app(agent, RateLimiter(per_minute=1)))
    assert client.post("/api/v1/chat", json={"message": "Oi"}).status_code == 200
    response = client.post("/api/v1/chat", json={"message": "De novo"})
    body = response.json()
    assert response.status_code == 429 and body["data"] is None
    assert body["error"]["code"] == "RATE_LIMITED"
    assert len(llm.requests) == 1


def test_api_limits_by_forwarded_address(make_agent):
    agent, _ = make_agent(["Um", "Dois"])
    client = TestClient(create_app(agent, RateLimiter(per_minute=1)))
    first = client.post("/api/v1/chat", json={"message": "Oi"}, headers={"x-forwarded-for": "1.1.1.1, 9.9.9.9"})
    second = client.post("/api/v1/chat", json={"message": "Oi"}, headers={"x-forwarded-for": "2.2.2.2, 9.9.9.9"})
    assert first.status_code == 200 and second.status_code == 200


def test_api_exposes_no_interactive_docs(make_agent):
    agent, _ = make_agent([])
    client = TestClient(create_app(agent))
    assert client.get("/docs").status_code == 404 and client.get("/openapi.json").status_code == 404


def test_every_error_uses_the_envelope(make_agent):
    agent, llm = make_agent([])
    client = TestClient(create_app(agent), raise_server_exceptions=False)
    not_utf8 = client.post(
        "/api/v1/chat", content='{"message": "endereço"}'.encode("latin-1"), headers={"Content-Type": "application/json"}
    )
    not_found = client.get("/nothing-here")
    wrong_method = client.get("/api/v1/chat")
    for response, status in ((not_utf8, 400), (not_found, 404), (wrong_method, 405)):
        body = response.json()
        assert response.status_code == status
        assert body["data"] is None and body["meta"]["request_id"] and body["error"]["code"] == "HTTP_ERROR"
    assert llm.requests == []


def test_missing_key_is_reported_instead_of_crashing_at_import(clean_env):
    client = TestClient(create_app())
    for path in ("/", "/api/v1/health"):
        response = client.get(path)
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "NOT_CONFIGURED"
        assert "LLM_API_KEY" in response.json()["error"]["message"]
    assert client.post("/api/v1/chat", json={"message": "Oi"}).status_code == 503


def test_missing_bundled_file_is_reported_instead_of_crashing_at_import(clean_env, tmp_path):
    clean_env.setenv("LLM_API_KEY", "k")
    clean_env.setenv("DATA_DIR", str(tmp_path))
    clean_env.setenv("DB_PATH", str(tmp_path / "x.db"))
    response = TestClient(create_app()).get("/api/v1/health")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "STARTUP_FAILED"
    assert "categories.csv" in response.json()["error"]["message"]
    assert str(tmp_path) not in response.text


def test_vercel_bundle_keeps_runtime_files():
    root = Path(__file__).resolve().parents[1]
    ignored = (root / ".vercelignore").read_text(encoding="utf-8").split()
    assert not any(entry.rstrip("/") in ("data", "emporio_agent") for entry in ignored)
    assert "*.csv" not in ignored and "*.md" not in ignored
    assert "create_app()" in (root / "app.py").read_text(encoding="utf-8")
