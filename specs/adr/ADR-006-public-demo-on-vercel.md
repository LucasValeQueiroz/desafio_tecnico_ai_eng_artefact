# ADR-006: Public demo on Vercel with temporary state

**Status:** Accepted
**Date:** 2026-10-31
**Deciders:** Lucas Vale Queiroz
**Related:** SPEC-2026-10-emporio-service-agent, ADR-005

## Context

The candidate wants a public demo, with the API key held in the platform's environment settings. The repository remains the challenge's deliverable and the CLI its main interface. A public URL brings two new problems: serverless functions have a temporary filesystem, so SQLite doesn't survive across instances, and anyone with the link can spend the candidate's paid key.

## Decision

We will deploy the existing FastAPI app on Vercel through a root `app.py`. On that platform SQLite lives in the temporary directory, and we accept that history, tickets and the verification lockout can reset when an instance changes. We will limit messages per client and per day in the application, and rely on a spending cap at the LLM provider as the hard ceiling.

## Alternatives Considered

### Managed Postgres or Redis
- **Pros:** real persistence; rate limits and lockout that hold across instances.
- **Cons:** another account, a new dependency and a second storage implementation, for a demo that one evaluator uses for a few minutes.
- **Why rejected:** the brief asks for the simplest solution. This is the first change to make for real traffic.

### Conversation state signed and held by the client
- **Pros:** survives instance changes with no database.
- **Cons:** an old token can be replayed to reset the lockout, and tickets would still need storage.
- **Why rejected:** more machinery that doesn't solve the whole problem.

### Access code on the demo
- **Pros:** the strongest protection against abuse without a database.
- **Cons:** friction for evaluators, and one more thing to send.
- **Why rejected:** a link shared only by email or PDF plus the spending cap is enough for a few days. Easy to add if abuse appears.

### No public demo
- **Pros:** no cost exposure and nothing new to explain.
- **Cons:** an evaluator must install the project to see it working.
- **Why rejected:** it's the candidate's decision, and it suits a full-stack role.

## Consequences

### Positive
- An evaluator can try the agent from a link with no setup.
- No storage code changes: only the default path differs.

### Negative
- A conversation can lose its memory on an instance change, and promised protocols may not persist on the demo.
- The lockout and rate limits apply per instance, which is weaker than on the CLI or a real deployment.

### Neutral / follow-ups
- Example conversations and evaluation run locally, since they need a fixed clock that a public endpoint must not expose.

## Compliance / Governance

- Applies to: the public demo only. Fictional data only.
- Review date: before any use beyond the assessment. Take the demo down after the selection process.
