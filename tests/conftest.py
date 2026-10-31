from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import pytest

from emporio_agent.agent import ServiceAgent
from emporio_agent.clock import StoreClock
from emporio_agent.llm import LLMTurn, LLMUnavailable, ToolCall, ToolResult
from emporio_agent.policies import PolicyBook
from emporio_agent.storage import SessionState, Storage
from emporio_agent.store_data import StoreData
from emporio_agent.tools import StoreTools

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
TUESDAY_MORNING = datetime(2026, 2, 10, 10, 30)


@pytest.fixture(scope="session")
def data() -> StoreData:
    return StoreData(DATA_DIR)


@pytest.fixture(scope="session")
def policies() -> PolicyBook:
    return PolicyBook()


@pytest.fixture
def storage(tmp_path) -> Storage:
    return Storage(tmp_path / "test.db")


@pytest.fixture
def make_tools(data, policies, storage):
    def build(now: datetime = TUESDAY_MORNING, session_id: str = "s1") -> StoreTools:
        session = SessionState(session_id, "fake", "fake-model")
        return StoreTools(data, policies, StoreClock(now), storage, session)

    return build


@pytest.fixture
def tools(make_tools) -> StoreTools:
    return make_tools()


@dataclass
class ScriptedLLM:
    """Plays back a list of turns, and records every request it receives."""

    script: list = field(default_factory=list)
    provider: str = "fake"
    model: str = "fake-model"
    requests: list = field(default_factory=list)

    def complete(self, system, messages, tools) -> LLMTurn:
        self.requests.append([dict(m) for m in messages])
        step = self.script.pop(0)
        if isinstance(step, Exception):
            raise step
        if isinstance(step, str):
            return LLMTurn(text=step, assistant_message={"role": "assistant", "content": step})
        return step

    def user_message(self, text: str) -> dict:
        return {"role": "user", "content": text}

    def assistant_text_message(self, text: str) -> dict:
        return {"role": "assistant", "content": text}

    def tool_result_messages(self, results: list[ToolResult]) -> list[dict]:
        return [{"role": "tool", "id": r.call.id, "content": r.content} for r in results]


def tool_turn(name: str, **arguments) -> LLMTurn:
    call = ToolCall(id=f"call-{name}", name=name, arguments=arguments)
    return LLMTurn(text="", tool_calls=[call], assistant_message={"role": "assistant", "calls": [name]})


@pytest.fixture
def make_agent(data, policies, storage):
    def build(script: list, now: datetime = TUESDAY_MORNING) -> tuple[ServiceAgent, ScriptedLLM]:
        llm = ScriptedLLM(script=script)
        return ServiceAgent(data, policies, StoreClock(now), storage, llm), llm

    return build


__all__ = ["LLMUnavailable", "tool_turn"]
