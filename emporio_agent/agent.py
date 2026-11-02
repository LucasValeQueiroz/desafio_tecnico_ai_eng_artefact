"""The conversation loop: the model chooses what to consult, the tools decide what is true."""
from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

from .clock import StoreClock
from .config import Settings
from .guard import Evidence, count_checked_values, find_untraceable
from .llm import LLMClient, LLMUnavailable, ToolResult, build_llm
from .policies import PolicyBook
from .storage import SessionState, Storage
from .store_data import StoreData
from .tools import StoreTools, tool_schemas

logger = logging.getLogger(__name__)

SYSTEM_PROMPT_FILE = Path(__file__).parent / "prompts" / "system_prompt.md"
MAX_TOOL_ROUNDS = 8
MAX_GUARD_RETRIES = 1
MAX_MESSAGE_CHARS = 4000

# Never stored in the audit trail: verification factors and contact details.
REDACTED_ARGUMENTS = {"email", "phone", "contact", "customer_name"}
RESERVED_TAGS = re.compile(r"</?\s*(contexto_do_sistema|mensagem_do_cliente|verificacao_interna)[^>]*>", re.IGNORECASE)

SAFE_REPLY = (
    "Desculpa, tive um problema aqui e prefiro não te passar uma informação errada. "
    "Você pode falar com a nossa equipe pelo telefone ou WhatsApp (67) 3341-4444, "
    "ou pelo e-mail contato@emporiodamusica.com.br."
)


@dataclass
class AgentReply:
    text: str
    tools_used: list[dict] = field(default_factory=list)
    degraded: bool = False
    guard_flags: list[str] = field(default_factory=list)
    latency_ms: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    checked_values: int = 0


def _wrap_customer_message(text: str, context_line: str) -> str:
    return (
        f"<contexto_do_sistema>{context_line}</contexto_do_sistema>\n"
        f"<mensagem_do_cliente>{RESERVED_TAGS.sub('', text)}</mensagem_do_cliente>"
    )


def _guard_correction(problems: list[str]) -> str:
    return (
        "<verificacao_interna>Sua resposta não foi enviada. Estes valores não vieram das consultas desta conversa: "
        f"{', '.join(problems)}. Consulte a ferramenta adequada, ou use somente valores retornados por ela, "
        "e responda novamente ao cliente sem mencionar esta verificação.</verificacao_interna>"
    )


def _redact(arguments: dict) -> dict:
    return {k: ("[redacted]" if k in REDACTED_ARGUMENTS else v) for k, v in arguments.items()}


class ServiceAgent:
    def __init__(self, data: StoreData, policies: PolicyBook, clock: StoreClock, storage: Storage, llm: LLMClient) -> None:
        self._data = data
        self._policies = policies
        self._clock = clock
        self._storage = storage
        self._llm = llm
        self._system_prompt = SYSTEM_PROMPT_FILE.read_text(encoding="utf-8")
        self._tools = tool_schemas(policies, list(data.categories.values()))

    @classmethod
    def from_settings(cls, settings: Settings) -> "ServiceAgent":
        return cls(
            data=StoreData(settings.data_dir),
            policies=PolicyBook(),
            clock=StoreClock(settings.fixed_now),
            storage=Storage(settings.db_path),
            llm=build_llm(settings),
        )

    def store_status(self) -> dict:
        return {"store_clock": self._clock.context_line(), "fixed_clock": self._clock.is_fixed}

    def reply(self, session_id: str, customer_text: str) -> AgentReply:
        started = time.perf_counter()
        customer_text = customer_text.strip()[:MAX_MESSAGE_CHARS]
        session = self._storage.load_session(session_id, self._llm.provider, self._llm.model)
        evidence = Evidence.from_json(session.evidence)
        evidence.add_customer_text(customer_text)
        trace: list[dict] = []
        guard_flags: list[str] = []
        usage = {"input": 0, "output": 0}

        # The turn is built on a copy. History only changes once the turn has an outcome (RNF-05).
        messages = [
            *session.messages,
            self._llm.user_message(_wrap_customer_message(customer_text, self._clock.context_line())),
        ]
        try:
            text = self._run_turn(session, messages, evidence, trace, guard_flags, usage)
        except LLMUnavailable as error:
            logger.error("Turn degraded for session %s: %s", session_id, error)
            guard_flags.append(f"llm_unavailable:{error}")
            text = None

        degraded = text is None
        if degraded:
            # Unsent drafts leave the history, so the next turn doesn't build on them.
            text = SAFE_REPLY
            messages = [
                *session.messages,
                self._llm.user_message(_wrap_customer_message(customer_text, self._clock.context_line())),
                self._llm.assistant_text_message(text),
            ]

        session.messages = messages
        session.evidence = evidence.to_json()
        self._storage.save_session(session)
        latency_ms = int((time.perf_counter() - started) * 1000)
        self._storage.record_turn(
            session_id, customer_text, text, trace, latency_ms, usage["input"], usage["output"], guard_flags
        )
        return AgentReply(
            text=text,
            tools_used=trace,
            degraded=degraded,
            guard_flags=guard_flags,
            latency_ms=latency_ms,
            input_tokens=usage["input"],
            output_tokens=usage["output"],
            checked_values=0 if degraded else count_checked_values(text),
        )

    def _run_turn(
        self,
        session: SessionState,
        messages: list[dict],
        evidence: Evidence,
        trace: list[dict],
        guard_flags: list[str],
        usage: dict,
    ) -> str | None:
        """Run the tool loop. Returns the reply, or None when no safe reply was produced."""
        tools = StoreTools(self._data, self._policies, self._clock, self._storage, session)
        guard_retries = 0
        for _ in range(MAX_TOOL_ROUNDS):
            turn = self._llm.complete(self._system_prompt, messages, self._tools)
            usage["input"] += turn.input_tokens
            usage["output"] += turn.output_tokens
            if turn.refused:
                guard_flags.append("refused")
                return None
            messages.append(turn.assistant_message)

            if turn.tool_calls:
                results = [self._execute(tools, call, evidence, trace) for call in turn.tool_calls]
                messages.extend(self._llm.tool_result_messages(results))
                continue

            problems = find_untraceable(turn.text, evidence)
            if not turn.text.strip():
                guard_flags.append("empty_reply")
                return None
            if not problems:
                return turn.text.strip()

            guard_flags.append("untraceable:" + ",".join(problems))
            logger.warning("Reply blocked by the safety net: %s", problems)
            if guard_retries >= MAX_GUARD_RETRIES:
                return None
            guard_retries += 1
            messages.append(self._llm.user_message(_guard_correction(problems)))

        guard_flags.append("max_tool_rounds")
        return None

    def _execute(self, tools: StoreTools, call, evidence: Evidence, trace: list[dict]) -> ToolResult:
        try:
            output = tools.execute(call.name, call.arguments)
            is_error = False
        except (TypeError, ValueError, KeyError) as error:
            logger.warning("Tool %s rejected its arguments: %s", call.name, error)
            output = {"status": "erro", "detalhe": f"Consulta inválida: {error}"}
            is_error = True
        except Exception:
            # A failed consultation must never take the conversation down (RNF-05).
            logger.exception("Tool %s failed", call.name)
            output = {"status": "erro", "detalhe": "Consulta indisponível. Não invente a informação; ofereça a equipe."}
            is_error = True
        content = json.dumps(output, ensure_ascii=False, sort_keys=True)
        evidence.add_trusted_text(content)
        trace.append({"tool": call.name, "arguments": _redact(call.arguments), "status": output.get("status", "ok")})
        return ToolResult(call=call, content=content, is_error=is_error)
