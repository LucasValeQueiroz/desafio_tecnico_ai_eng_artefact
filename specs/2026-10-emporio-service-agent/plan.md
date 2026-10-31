# Plan: Empório da Música Customer Service Agent

**Spec:** SPEC-2026-10-emporio-service-agent
**Status:** Approved (see delegation note in `spec.md`)
**Last updated:** 2026-10-31

> **Rule:** This document describes **HOW** we will implement the spec. No new business rules.

---

## 1. Technical Summary

A small Python package with a hand-written tool-calling loop. The LLM decides *what to consult and how to phrase it*; deterministic Python decides *what is true*. Records are exposed through typed read-only tools, the manual through section routing, and identity, pricing and return rules live in code. A final safety net checks that every amount and percentage in a reply is traceable before it reaches the customer.

---

## 2. Architecture Decisions

- **AD-01** — Function calling with a hand-written loop, no agent framework. See ADR-001.
- **AD-02** — Manual retrieval by section routing, no embeddings. See ADR-002.
- **AD-03** — Provider adapter with Gemini as default through its OpenAI-compatible endpoint, and Claude as an alternative. See ADR-003 and ADR-005.
- **AD-04** — Identity, pricing and eligibility enforced in code, not in the prompt. See ADR-004.
- **AD-05** — Typed tools, no text-to-SQL. Rationale: a 6-table dataset and a closed list of questions don't justify it, and generated SQL over a customer table is a data-leak surface that AD-04 exists to remove.
- **AD-06** — SQLite (standard library) for conversations and tickets. Rationale: conversations must survive restarts (RF-02), no server needed.
- **AD-07** — Clock context travels in each user turn rather than in the system prompt. Rationale: the system prompt stays byte-identical, so the prompt cache keeps hitting, and history stays append-only, which models that replay thinking blocks require.
- **AD-08** — Public demo on Vercel, with temporary SQLite, application rate limits and a provider spending cap. See ADR-006.
- **New ADR required:** yes, ADR-001 to ADR-006 in `specs/adr/`.

---

## 3. Affected Components

### Agent (`emporio_agent/`)
| Module | Responsibility | Spec |
|---|---|---|
| `config.py` | Settings from environment, optional fixed clock | RNF-02, RNF-06 |
| `store_data.py` | Load and normalize CSVs, availability, record-conflict detection | RF-04, RF-09, RF-10 |
| `pricing.py` | Promotion, instant-payment, installments, BRL formatting | RF-06, RF-07 |
| `clock.py` | Store timezone, opening status, holidays, next opening | RF-03 |
| `policies.py` + `knowledge/policies.md` | Manual sections and table of contents | RF-16, RF-18 |
| `tools.py` | Tool schemas and execution, verification, return rules | RF-04–RF-17, RF-21, RF-22 |
| `guard.py` | Traceability check of amounts and percentages | RF-24 |
| `llm.py` | Provider adapters | RNF-02, RF-25 |
| `prompts/system_prompt.md` | Persona, routing and behavior | RF-01, RF-19, RF-20, RF-23 |
| `agent.py` | Loop, guard retry, fallbacks, persistence | RF-02, RF-24, RF-25 |
| `storage.py` | Sessions, turns, tickets | RF-02, RF-21, RNF-04 |
| `cli.py`, `api.py`, `static/` | Interfaces | RF-01 |

### Scripts, evaluation, docs
- `scripts/build_policy_kb.py` — manual PDF to section Markdown, with resolution notes.
- `scripts/profile_data.py` — data-quality report in `docs/data_quality.md`.
- `scripts/generate_examples.py` — real conversations into `examples/`.
- `evals/` — scripted scenarios against a live model.
- `tests/` — offline tests with a scripted fake LLM.

### Infrastructure
Local Python process, plus an optional public demo on Vercel: `app.py` as the entry point, `vercel.json`, `.vercelignore`, and settings in the platform's environment. See ADR-006.

---

## 4. Data Model

### Source (read-only, loaded in memory at startup)
`data/*.csv` is loaded by column name, since `order_items.csv` has an unusual column order. Prices become `Decimal`, `specs` JSON is parsed, blank optional fields become `None`.

### Derived fields
- `availability`: `discontinued` and `coming_soon` come from `status` and win over stock, so product 136 (discontinued, stock 13) and product 130 (coming soon, stock 2) are not sellable. Otherwise, stock above zero is `in_stock` and stock zero is `out_of_stock`.
- `record_conflict`: description mentions a brand or model line of a different brand than the name.

### Local state (SQLite, `DB_PATH`, git-ignored)
- `sessions(id, provider, model, created_at, updated_at, messages_json, evidence_json, failed_verifications)`
- `turns(id, session_id, created_at, user_text, reply, tool_trace_json, latency_ms, input_tokens, output_tokens, guard_flags_json)`
- `tickets(protocol, session_id, kind, summary, customer_name, contact, created_at, status)`

### Migrations
`CREATE TABLE IF NOT EXISTS` at startup. Rollback by deleting the local file.

---

## 5. Contracts

### Tools exposed to the LLM
| Tool | Purpose |
|---|---|
| `search_products` | Filter sellable products by category, budget, free text |
| `get_product` | Details, price quote, availability, expired promotions, alternatives |
| `list_active_promotions` | Sellable products on an active promotion |
| `get_policy` | Manual sections by id; table of contents embedded in the description |
| `get_my_orders` | Order data after verification |
| `check_return_eligibility` | Assessment for regret, defect or preference after verification |
| `register_ticket` | Complaint or handover with protocol |

Failed verification always returns the same payload, whatever the cause.

### HTTP API
Envelope `{ data, meta, error }`, kept from the SDD kit.

`POST /api/v1/chat`
```json
{ "session_id": "optional-string", "message": "Qual o endereço da loja?" }
```
Response 200:
```json
{
  "data": { "session_id": "abc", "reply": "..." },
  "meta": { "request_id": "uuid", "tools": ["get_policy"], "latency_ms": 1800 },
  "error": null
}
```
Errors: `422` validation (`error.code = "INVALID_REQUEST"`). A language-service failure is a `200` with the safe reply and `meta.degraded = true`, since the customer is still answered.

`GET /api/v1/health` and `GET /` (one-page chat).

---

## 6. Integration Points

- **Inbound:** CLI and HTTP.
- **Outbound:** language service through `llm.py` only. Business code never imports a provider SDK.
- **Claude adapter:** official `anthropic` SDK, `claude-opus-5-5` default, explicit `output_config.effort`, system prompt with `cache_control`, content blocks replayed unchanged, `stop_reason: "refusal"` handled, server-side `fallbacks: "default"` enabled.
- **OpenAI-compatible adapter:** official `openai` SDK with `base_url`, covering Gemini's and Groq's free tiers and local Ollama.
- **Logging:** standard `logging`, no `print` outside the CLI and scripts.

---

## 7. Non-Functional Implementation

| NFR | Mechanism |
|-----|-----------|
| RNF-01 Performance | In-memory data; a test asserts a consultation stays under 50 ms |
| RNF-02 Portability | `LLM_PROVIDER`, `LLM_MODEL`, `LLM_API_KEY`, `LLM_BASE_URL` |
| RNF-03 Security | Verification in `tools.py`; tools return first name only; verification arguments redacted from the audit trail; `.env` git-ignored |
| RNF-04 Observability | `turns` table and `--debug` in the CLI |
| RNF-05 Reliability | Tool errors become error results; a failed turn is not persisted, so history stays valid |
| RNF-06 Testability | `AGENT_NOW` fixes the clock; scripted LLM in tests |
| RNF-07 Simplicity | `pip install -r requirements.txt`, one env var, one command |

---

## 8. Testing Strategy

- **Unit:** pricing, availability, clock and holidays, verification, return rules, guard, policy sections, record conflicts.
- **Agent loop:** scripted LLM covering tool rounds, guard retry and fallback, service failure, session resume.
- **API:** FastAPI `TestClient` with a scripted LLM.
- **Live evaluation:** `evals/` with deterministic assertions on tools called and reply content, including the leakage and fabrication groups.
- **Load:** not applicable.

---

## 9. Delivery Plan — HUMAN RESPONSIBILITY

> **Not executable by an AI agent.** An agent may push commits to the repositories as the candidate instructed. Reviewing the result, submitting the form and replying to the recruiter are performed by the candidate, after the local validation gate in `tasks.md` is signed off.

- **Gate:** candidate reviews the code and runs the project.
- **Submission:** repository link per the challenge, PDF per the recruiter's email.
- **Freeze:** no commit after the delivery date and time, as the challenge requires.
- **Rollback:** before submission, revert with a new commit. Never force-push, since the challenge evaluates commit history.

---

## 10. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|-----------|
| LLM skips a tool and invents a fact | M | H | Prompt rule, plus the RF-24 safety net, plus evaluation |
| Prompt injection extracts another customer's order | M | H | Verification in code; the LLM never has access to unverified data |
| Verification brute force | L | M | Per-conversation lockout; cross-conversation limits listed as a known limitation |
| Guard rejects a legitimate calculated amount | M | L | One retry with instructions, then safe message; tools supply calculated values |
| Free-tier provider rate limits during evaluation | M | L | SDK retries; friendly fallback; provider swap |
| Evaluator has no key | M | M | Free provider instructions; offline tests run without a key |
| Provider model is retired | L | M | Model name is configuration |

---

## 11. Dependencies

- **Blocks:** nothing.
- **Blocked by:** an LLM credential for live evaluation and real example conversations. Everything else runs offline.
- **External:** availability of the chosen language service.

---

## 12. Change Log

| Date | Author | Change |
|------|--------|--------|
| 2026-10-31 | Lucas Vale Queiroz | Initial plan |
