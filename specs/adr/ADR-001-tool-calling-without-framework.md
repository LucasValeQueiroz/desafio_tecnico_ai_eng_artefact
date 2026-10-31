# ADR-001: Function calling with a hand-written loop, no agent framework

**Status:** Accepted
**Date:** 2026-10-31
**Deciders:** Lucas Vale Queiroz
**Related:** SPEC-2026-10-emporio-service-agent

## Context

The agent must decide when to consult data and when to consult policies. The recruiter's email asks for the simplest possible solution, and the assessment looks at reasoning. The questions are a closed family with a small tool set, and every turn must pass through a safety net before reaching the customer.

## Decision

We will use native function calling with a loop of about 60 lines in `agent.py`, without an agent framework.

## Alternatives Considered

### LangGraph / LangChain
- **Pros:** familiar vocabulary, ready-made checkpointers, ecosystem.
- **Cons:** a large dependency tree for a linear loop; a graph with one cycle adds indirection without adding capability.
- **Why rejected:** it would hide the very decisions the evaluators want to see. Worth revisiting if the flow gains real branching or multiple agents.

### Text-to-SQL agent
- **Pros:** flexible, answers ad hoc questions.
- **Cons:** generated queries over the customer table make the LLM a data-access decision maker, and results need validation anyway.
- **Why rejected:** conflicts with ADR-004.

### Anthropic SDK tool runner
- **Pros:** less code on the Claude path.
- **Cons:** beta, Claude-only, and the safety-net retry would need to be fitted around it.
- **Why rejected:** the loop must be shared across provider adapters (ADR-003).

### Pure RAG with everything in one index
- **Why rejected:** similarity search can't answer "violões up to R$ 1.000" reliably, and stock and order facts must be exact.

## Consequences

### Positive
- The whole control flow fits on one screen and is unit-testable with a scripted LLM.
- Few dependencies, fast install.

### Negative
- We own retries around tool rounds and message formats for each provider.

### Neutral / follow-ups
- Streaming isn't implemented; replies are short.

## Compliance / Governance

- Applies to: this repository.
- Review date: if a second agent or a branching workflow appears.
