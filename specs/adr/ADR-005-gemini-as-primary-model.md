# ADR-005: Gemini as the primary model

**Status:** Accepted
**Date:** 2026-10-31
**Deciders:** Lucas Vale Queiroz
**Related:** SPEC-2026-10-emporio-service-agent, supersedes ADR-003

## Context

ADR-003 made Claude the default, with an OpenAI-compatible adapter as the free alternative. The candidate then chose a paid Gemini key for this project. An evaluator should need as little configuration as possible, and Google also offers a free tier, so the same default serves both cases.

## Decision

We will use `gemini-3.8-flash` by default through the OpenAI-compatible endpoint, so that `LLM_API_KEY` is the only required setting. The adapter interface from ADR-003 stays, along with the Claude path.

## Alternatives Considered

### Keep Claude as default
- **Pros:** the adapter uses the provider's native SDK and has prompt caching configured.
- **Cons:** no free tier for evaluators, and the candidate's available key is for Gemini.
- **Why rejected:** results and example conversations must come from the model that is actually used.

### Native Google SDK
- **Pros:** full access to provider-specific features.
- **Cons:** a third adapter, for features the agent doesn't need.
- **Why rejected:** the compatible endpoint supports function calling and thought signatures. Revisit if evaluation shows a limitation there.

### A Pro or flagship model
- **Pros:** potentially better judgment on difficult cases.
- **Cons:** higher cost and latency for short service replies.
- **Why rejected:** start with the cheaper option and let the evaluation suite show whether it is enough. The model is one environment variable.

## Consequences

### Positive
- One setting to run, and a free option with the same configuration.
- Low cost per conversation: USD 0.75 / 3.75 per million input / output tokens until 2026-12-31, then USD 1.50 / 7.50.

### Negative
- The Claude path has unit tests with a fake client but hasn't been run against the live API. The README says so.
- History stored with one provider can't continue on another, as before.

### Neutral / follow-ups
- Evaluation results are valid only for the model recorded in the report.

## Compliance / Governance

- Applies to: this repository.
- Review date: when `gemini-3.8-flash` is retired or its price changes.
