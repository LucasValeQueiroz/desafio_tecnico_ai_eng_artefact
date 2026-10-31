# ADR-002: Manual retrieval by section routing, no embeddings

**Status:** Accepted
**Date:** 2026-10-31
**Deciders:** Lucas Vale Queiroz
**Related:** SPEC-2026-10-emporio-service-agent

## Context

The policy manual has 8 pages and 28 clearly numbered sections. Customers' words often differ from the manual's ("me arrependi" against "direito de arrependimento", "quando abre" against "horário de funcionamento"). The answer must follow the whole rule, so a chunk cut mid-section can cause a wrong answer. The manual also contradicts itself in places, which needs a human-reviewed resolution.

## Decision

We will expose the manual's table of contents in the description of a `get_policy` tool, and the LLM will ask for sections by id. The tool returns those sections in full, with any resolution notes. The manual is converted once by a script into a reviewable Markdown file.

## Alternatives Considered

### Vector search with embeddings
- **Pros:** the conventional answer; scales to many documents.
- **Cons:** adds an embedding model, an index and chunking parameters to solve a problem this corpus doesn't have. Top-k can return a neighbor section with similar words and miss the governing one.
- **Why rejected:** with 28 sections, the LLM reading a table of contents is cheaper, deterministic to inspect, and has no vocabulary-mismatch problem. Switch if the corpus grows to many documents.

### Keyword search (BM25)
- **Pros:** no external model.
- **Cons:** needs Portuguese stemming and synonyms to cover customers' vocabulary.
- **Why rejected:** same outcome with more moving parts.

### Entire manual in the system prompt
- **Pros:** simplest possible, high recall.
- **Cons:** every turn pays for the whole manual, including greetings and catalog questions; no trace of which rule was used.
- **Why rejected:** the challenge asks the agent to know *when* to consult policies, and the trace is useful for evaluation. It would be a close second.

## Consequences

### Positive
- No retrieval infrastructure; each answer records the sections consulted.
- Section integrity: a rule is never split.

### Negative
- Depends on the model choosing the right section. Evaluation scenarios assert the section used.
- Doesn't scale to a large corpus.

### Neutral / follow-ups
- If the store updates the manual, regenerate and review the Markdown file.

## Compliance / Governance

- Applies to: this repository.
- Review date: when a second policy document appears.
