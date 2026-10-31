# ADR-003: Claude by default, free alternative through a provider adapter

**Status:** Accepted
**Date:** 2026-10-31
**Deciders:** Lucas Vale Queiroz
**Related:** SPEC-2026-10-emporio-service-agent

## Context

The challenge lets the candidate choose any model, free or paid. Two needs pull in different directions: reliable tool use and Portuguese quality in the demonstration, and an evaluator being able to run the project without paying.

## Decision

We will define a small adapter interface in `llm.py` with two implementations: the official Anthropic SDK with `claude-opus-5-5` by default, and the official OpenAI SDK pointing at any compatible `base_url`, which covers Gemini's and Groq's free tiers and local Ollama. The conversation history is stored in the provider's native format and a session stays tied to its provider, so thinking blocks can be replayed unchanged on the Claude path.

## Alternatives Considered

### Routing library across providers
- **Pros:** one call shape for many providers.
- **Cons:** another large dependency, and a past supply-chain incident in this class of library makes pinning and review mandatory for little gain with only two adapters.
- **Why rejected:** two adapters are about 120 lines.

### Local model only
- **Pros:** no key, no cost.
- **Cons:** requires a multi-GB download; small models are weak at tool use and Portuguese without a GPU.
- **Why rejected:** kept as an option through the compatible adapter.

### Free tier only
- **Pros:** no cost for anybody.
- **Cons:** rate limits and model churn make the demonstration fragile.
- **Why rejected:** kept as the documented free path.

## Consequences

### Positive
- Provider swap by environment variables. Business code imports no provider SDK.

### Negative
- Each adapter must normalize messages. Live behavior can vary across models; evaluation results are valid only for the model recorded in the report.

### Neutral / follow-ups
- Claude's server-side refusal fallback is enabled by default.

## Compliance / Governance

- Applies to: this repository.
- Review date: when a recorded model is retired.
