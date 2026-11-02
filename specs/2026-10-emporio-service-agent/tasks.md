# Tasks: Empório da Música Customer Service Agent

**Spec:** SPEC-2026-10-emporio-service-agent
**Plan:** linked `plan.md`
**Status:** In Progress

> **Responsibility boundary.** `T-XX` tasks may be executed by an AI agent. `H-XX` steps are human-only: an agent must never execute, simulate or tick one.

---

## Legend

- `[ ]` pending — `[x]` done — `[~]` in progress — `[!]` blocked
- **T-XX** — implementation task; may be executed by an AI agent
- **H-XX** — human-only step
- **RF-XX / RNF-XX** — requirement reference; **AC-XX** — acceptance criterion
- **DEP** — depends on prior task

---

## Phase 1 — Foundation

- [x] **T-01** Write spec, plan, tasks and ADRs
  - covers: all
  - done when: all four are committed and every RF appears in the matrix below

- [x] **T-02** Project skeleton and settings from environment
  - covers: RNF-02, RNF-07
  - done when: `pip install -r requirements.txt` works, the package runs from the repository root, and `.env` is git-ignored

- [x] **T-03** Load and normalize store records, with availability and record-conflict detection
  - covers: RF-04, RF-09, RF-10
  - done when: tests assert products 130 and 136 are not sellable, and conflict detection flags exactly 135, 136, 137, 139, 140, 142 and 144

- [x] **T-04** Data-quality report
  - covers: RF-10, RF-18
  - DEP: T-03
  - done when: `scripts/profile_data.py` writes `docs/data_quality.md` listing the mismatched totals of orders 3 and 20

- [x] **T-05** Manual knowledge base with resolution notes
  - covers: RF-16, RF-18
  - done when: `scripts/build_policy_kb.py` regenerates `knowledge/policies.md` and tests assert all 28 numbered sections exist

---

## Phase 2 — Backend

- [x] **T-06** Price quote rules
  - covers: RF-06, RF-07
  - done when: tests assert Takamine GD20 PIX R$ 2.089,05, Ohana CK-20 R$ 439,20 without PIX, and installment limits at each boundary

- [x] **T-07** Store clock with holidays and next opening
  - covers: RF-03, RNF-06
  - done when: a test asserts Saturday 2026-10-31 14:00 reopens Tuesday 2026-11-03 09:00

- [x] **T-08** Catalog tools
  - covers: RF-04, RF-05, RF-08, RF-09, RF-10, RF-11
  - DEP: T-03, T-06
  - done when: tests assert exactly 12 acoustic guitars at or under R$ 1.000,00 and that "gd20" finds product 95

- [x] **T-09** Policy tool
  - covers: RF-16
  - DEP: T-05
  - done when: a test asserts asking for section 4 returns 4.1 to 4.4, and the table of contents is deterministic

- [x] **T-10** Order verification
  - covers: RF-12, RF-13, RF-14, RF-15, RNF-03
  - DEP: T-03
  - done when: tests assert identical failure payloads for existing and non-existing orders, lockout after three failures, and no email or phone in any tool output

- [x] **T-11** Return assessment
  - covers: RF-17
  - DEP: T-10
  - done when: tests cover each reason across delivered in and out of window, shipped, pending and cancelled

- [x] **T-12** Conversation storage and tickets
  - covers: RF-02, RF-21, RF-22, RNF-04
  - done when: tests assert sessions survive a new connection, tickets return a protocol, and audit trails contain no verification factors

- [x] **T-13** Traceability safety net
  - covers: RF-24
  - done when: tests assert Brazilian amount formats normalize correctly and an unknown amount or percentage is flagged

- [x] **T-14** Provider adapters
  - covers: RNF-02, RF-25
  - done when: tests with fake SDK clients assert request shape and normalized output for both adapters

- [x] **T-15** Persona and system prompt
  - covers: RF-01, RF-19, RF-20, RF-23
  - done when: the prompt is a versioned file and live evaluation groups for persona, scope and manipulation pass

- [x] **T-16** Agent loop
  - covers: RF-02, RF-24, RF-25, RNF-05
  - DEP: T-08, T-09, T-10, T-11, T-12, T-13, T-14, T-15
  - done when: tests with a scripted LLM cover tool rounds, guard retry, guard fallback, service failure with intact history, and round limit

- [x] **T-17** CLI
  - covers: RF-01, RF-02, RNF-07
  - DEP: T-16
  - done when: a piped conversation with a scripted LLM exits cleanly and `--session` resumes

- [x] **T-18** HTTP API and one-page chat
  - covers: RF-01, RF-02
  - DEP: T-16
  - done when: `TestClient` tests assert the envelope on success and validation failure

---

## Phase 3 — Testing & Observability

- [x] **T-19** Live evaluation suite
  - covers: all AC groups, Section 12 metrics
  - DEP: T-16
  - done when: `python -m evals.run` prints pass rates per group and writes a JSON report

- [x] **T-20** README with decisions, assumptions, limitations and assistant workflow
  - covers: RNF-07, A1–A8
  - done when: it contains every item required by the challenge's deliverables section

- [x] **T-21** Run live evaluation and record results
  - covers: Section 12 metrics
  - DEP: T-19
  - done when: the report is committed and the README states the real numbers

- [x] **T-22** Generate 5 real example conversations
  - covers: challenge deliverable 3
  - DEP: T-16
  - done when: `examples/` has 5 conversations produced by `scripts/generate_examples.py`, with at least one non-trivial case

- [x] **T-23** Gemini as the default model, needing only a key
  - covers: RNF-02, RNF-07
  - done when: tests assert the defaults and a clear error for a missing key

- [x] **T-24** Serverless entry point and temporary storage location
  - covers: RNF-05, A9
  - done when: tests assert the database path on Vercel and that runtime files aren't excluded from the bundle

- [x] **T-25** Rate limits on the HTTP API
  - covers: RNF-08
  - done when: tests assert a 429 envelope without a model call, and recovery after the window

- [x] **T-26** Smoke test of the public URL
  - covers: AC-04, AC-14, RNF-08
  - DEP: H-07
  - done when: the URL's chat page answers a catalog and a policy question

---

- [x] **T-27** Show consultations and checked values on the demo page, with scenario shortcuts
  - covers: RNF-09
  - done when: a browser check against a live model shows the data and policy labels, and a test asserts no verification data in the response

- [~] **T-28** Run the offline tests in continuous integration
  - covers: RNF-06, RNF-07
  - done when: the workflow is committed and its first run on GitHub passes

- [x] **T-29** Business case for the store
  - covers: Section 12 metrics
  - done when: `docs/business_case.md` separates measured values from assumptions

---

## Local Validation Gate — HUMAN ONLY

> **No AI agent may execute, simulate or tick anything in this section.**

- [ ] **H-01** Run the project from a fresh clone following the README
  - done when: a conversation works on the candidate's machine

- [ ] **H-02** Read the code and the example conversations
  - covers: all ACs that are only observable
  - done when: the candidate can explain each decision in the technical interviews

- [ ] **H-03** Sign off the gate
  - done when: the candidate decides the repository is ready to submit

---

## Delivery — HUMAN ONLY

> **Not an agent phase.** Blocked until H-03 is signed off.

- [ ] **H-04** Submit the PDF named per the recruiter's email through the Google Form
  - done when: the form confirms submission

- [ ] **H-05** Reply to the recruiter's email with the public repository link
  - done when: the email is sent

- [ ] **H-06** Freeze the repository
  - done when: no commit exists after the delivery date and time; spec marked `Implemented`

- [ ] **H-07** Create the Vercel project and set limits outside the application
  - covers: RNF-08
  - done when: the repository is imported, `LLM_API_KEY` is set in the project, a firewall rate limit covers the chat route, and the provider has a budget alert and a quota

- [ ] **H-08** Take the demo down after the selection process
  - covers: RNF-08
  - done when: the Vercel project is removed and the key is rotated

---

## Traceability Matrix

| Requirement | Tasks | Acceptance Criteria |
|-------------|-------|---------------------|
| RF-01 | T-15, T-17, T-18 | AC-01 |
| RF-02 | T-12, T-16, T-17, T-18 | AC-02 |
| RF-03 | T-07 | AC-03 |
| RF-04 | T-03, T-08 | AC-04 |
| RF-05 | T-08, T-13 | AC-04, AC-05 |
| RF-06 | T-06 | AC-06 |
| RF-07 | T-06 | AC-05, AC-06 |
| RF-08 | T-08 | AC-07 |
| RF-09 | T-03, T-08 | AC-08 |
| RF-10 | T-03, T-04, T-08 | AC-09 |
| RF-11 | T-08 | AC-10 |
| RF-26 | T-08, T-15, T-21 | AC-25 |
| RF-12 | T-10 | AC-11, AC-12 |
| RF-13 | T-10 | AC-11 |
| RF-14 | T-10 | AC-13 |
| RF-15 | T-10 | AC-11, AC-12 |
| RF-16 | T-05, T-09 | AC-14, AC-15 |
| RF-17 | T-11 | AC-16, AC-17, AC-18 |
| RF-18 | T-04, T-05 | AC-19 |
| RF-19 | T-15 | AC-20 |
| RF-20 | T-15 | AC-21 |
| RF-21 | T-12 | AC-22 |
| RF-22 | T-12 | AC-22 |
| RF-23 | T-15 | AC-21 |
| RF-24 | T-13, T-16 | AC-23 |
| RF-25 | T-14, T-16 | AC-24 |
| RNF-01 | T-08 | — |
| RNF-02 | T-02, T-14 | — |
| RNF-03 | T-10, T-12 | AC-11 |
| RNF-04 | T-12 | — |
| RNF-05 | T-16 | AC-02, AC-24 |
| RNF-06 | T-07, T-16 | — |
| RNF-07 | T-02, T-17, T-20, T-23, H-01 | — |
| RNF-08 | T-25, T-26, H-07, H-08 | — |
| RNF-09 | T-27 | — |

**Reading the matrix:** `T-` entries may be executed by an agent. `H-` entries are human-only. Live behavior is demonstrated by T-21 and T-22, and finally closed by a person in H-01 and H-02, never by an agent reporting success.

---

## Notes / Decisions during execution

- 2026-10-31 — Checks on the deployed URL found three things tests had missed: the app crashed opaquely without a key, framework errors escaped the response envelope, and simultaneous requests bypass the per-instance rate limit. The first two were fixed; the third needs a limit outside the application (H-07).
- 2026-10-31 — The first live run scored 43/44, and the stricter suite 44/44, yet reading the replies showed invented product details that no assertion caught. Tools now return description and specs in every result, the prompt forbids embellishment, and new scenarios cover it. Lesson: read the transcripts, not only the score.
- 2026-10-31 — The recruiter's email says responses must be in English and submitted as a PDF through a form; the challenge PDF says to reply to the email with the repository link. Both are in the Delivery section so neither is missed.
