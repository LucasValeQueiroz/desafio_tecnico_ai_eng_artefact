# ADR-004: Identity, pricing and eligibility rules live in code

**Status:** Accepted
**Date:** 2026-10-31
**Deciders:** Lucas Vale Queiroz
**Related:** SPEC-2026-10-emporio-service-agent

## Context

The manual says wrong prices can amount to misleading advertising. Order records are personal data under the LGPD. A prompt is an instruction, not a boundary: it can be argued with, and the model can make arithmetic or date mistakes. A customer can also type anything, including instructions.

## Decision

We will enforce what must be true in Python. The LLM never receives unverified order data, because the tool refuses before reading it. Price quotes, installment limits and return windows are calculated by tools and returned ready to use. A final check blocks any reply with an amount or percentage that can't be traced to a tool result, the manual, or the customer's message.

## Alternatives Considered

### Prompt-only rules
- **Pros:** less code.
- **Cons:** a single successful prompt injection exposes customer data, and calculated values can be wrong.
- **Why rejected:** an unacceptable failure mode, even in a prototype meant to show judgment.

### A second LLM as output reviewer
- **Pros:** can catch semantic errors, not only numbers.
- **Cons:** doubles cost and latency, and is another probabilistic layer.
- **Why rejected:** the regex check covers the highest-liability failure deterministically. Listed as a future improvement.

## Consequences

### Positive
- Leak and price guarantees hold whatever the model does, and they're testable offline.

### Negative
- Rules are duplicated in spirit between code and manual, so a change in the manual needs a code change. Tests pin the values.
- The safety net only sees numbers, so a wrong non-numeric claim passes. The prompt and evaluation cover those.

### Neutral / follow-ups
- A real deployment needs identity from the messaging channel and rate limits across conversations.

## Compliance / Governance

- Applies to: this repository.
- Review date: before any use with real customer data.
