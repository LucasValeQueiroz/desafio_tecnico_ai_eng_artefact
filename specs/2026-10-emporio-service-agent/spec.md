# Spec: Empório da Música Customer Service Agent

**ID:** SPEC-2026-10-emporio-service-agent
**Status:** Approved (human gate delegated: on 2026-10-31 the candidate instructed the coding agent to carry the work through all stages without stopping)
**Owner:** Lucas Vale Queiroz
**Created:** 2026-10-31
**Last updated:** 2026-10-31
**Related ADRs:** ADR-001 to ADR-006

> **Rule:** This document describes **WHAT** and **WHY**, never HOW.

---

## 1. Problem Statement

Empório da Música, a musical instrument store in Campo Grande/MS, handles all customer service with its own team. The team is overloaded by recurring questions: opening hours, order status, product price and availability.

Answers to these questions depend on two different sources: operational records that change (catalog, stock, promotions, orders) and a policy manual that is read and interpreted (exchanges, payment, shipping). A wrong answer is not merely unhelpful. The manual itself warns that incorrect price or stock information can amount to misleading advertising, and order records contain personal data protected by law.

Doing nothing keeps the team overloaded. Doing this carelessly would put a confident system in front of customers that invents prices, promises expired discounts, or reveals one customer's order to another.

---

## 2. Goals

- Answer recurring customer questions without team involvement, by text message, in the store's voice.
- Answer every factual question from the store's own records and manual, never from assumption.
- Protect customer data: an order is only discussed with someone who proves a link to it.
- Route to the team whatever should not be automated, such as complaints and policy gaps.

## 3. Non-Goals (Out of Scope)

- Placing orders, taking payment, or changing any operational record.
- Actually processing a return, refund or cancellation. The system assesses and routes; the team executes.
- Integrating with a real messaging channel in this iteration. Interaction happens through a prototype interface.
- Quoting freight outside the fixed rules of the manual. Rates that depend on destination code, weight and dimensions go to the team.
- Maintaining or correcting source records. Inconsistencies are reported, not fixed.

---

## 4. User Stories

### US-01 — Buyer choosing an instrument
**As a** person shopping for an instrument, possibly a beginner
**I want** to describe what I need and my budget
**So that** I get options that I can really buy, with correct prices and payment conditions.

### US-02 — Customer tracking a purchase
**As a** customer who already bought from the store
**I want** to know where my order is
**So that** I don't need to wait for an attendant, and nobody else can see my order.

### US-03 — Customer unhappy with a purchase
**As a** customer who regrets a purchase or received a defective product
**I want** a clear answer about what I am entitled to, based on my actual order
**So that** I know the next step and its deadline.

### US-04 — Service team member
**As a** member of the store's service team
**I want** recurring questions handled and complaints handed over with context
**So that** I can spend my time on cases that need a person.

---

## 5. Functional Requirements

### Persona and conversation
- **RF-01** — When a customer sends a message, the system shall reply in Brazilian Portuguese as the store's virtual assistant, in an informal but professional tone, as a friend who understands music would.
- **RF-02** — While a conversation is open, the system shall take earlier messages into account, and shall allow the conversation to be resumed later by its identifier.
- **RF-03** — When the store is closed at the time of a conversation's first reply, or when a request depends on the team, the system shall state when the store reopens.

### Catalog and pricing
- **RF-04** — When a customer asks for product options, the system shall filter the catalog by category, budget and described attributes, and shall offer only products that can be bought now.
- **RF-05** — The system shall state a price, stock position, or deadline only when it consulted the store's records or manual for it during the conversation.
- **RF-06** — When a product has an active promotion, the system shall present the promotional price together with the original price and the discount percentage.
- **RF-07** — The system shall apply the instant-payment discount only over non-promotional prices, shall never combine discounts, and shall calculate interest-free installments according to the manual's minimum-installment rules.
- **RF-08** — When a customer asks about a promotion that is no longer active, the system shall say so plainly and present the current price, never promising the expired discount.
- **RF-09** — When a product is out of stock, the system shall report it as temporarily unavailable; when discontinued, as no longer in the catalog; when not yet launched, as not available for purchase yet. In all three cases it shall suggest similar products that can be bought.
- **RF-10** — When a product record has conflicting information, the system shall not assert the conflicting details, and shall offer to confirm them with the team.
- **RF-11** — When a customer asks for an instrument with no matching record, the system shall say it is not in the catalog rather than assuming it exists.

### Orders and identity
- **RF-12** — When a customer asks about a specific order, the system shall disclose order data only after the customer provides the order number plus the email or phone on file, or, without an order number, both the email and the phone on file.
- **RF-13** — When a verification attempt fails, the system shall give the same answer whether or not the order exists, and shall disclose nothing about any customer.
- **RF-14** — When three verification attempts fail in a conversation, the system shall stop attempting and direct the customer to the team.
- **RF-15** — The system shall never reveal another customer's personal data, and shall limit a verified customer's personal data in replies to their first name.

### Policies
- **RF-16** — When a customer asks about store rules or information, the system shall answer from the corresponding manual section; when the manual does not cover the question, it shall say so and offer the team.
- **RF-17** — When a customer asks to return or exchange a purchase, the system shall identify the reason (regret, defect, or preference) and assess eligibility from the verified order's status and dates under the manual's rules, stating the conditions and the assumptions behind the result.
- **RF-18** — Where the manual contradicts itself, the system shall consistently follow the documented resolution for that contradiction.

### Scope and escalation
- **RF-19** — When a customer asks for accessories, the system shall explain that the store works exclusively with musical instruments and shall not invent partner stores.
- **RF-20** — When a message is unrelated to the store, the system shall politely decline and bring the conversation back to how it can help.
- **RF-21** — When a customer complains, the system shall respond with empathy, register the complaint, and inform a protocol and the return deadline of 24 business hours.
- **RF-22** — When a customer asks for a person, or the system cannot resolve a request, the system shall register a handover with a summary of the case.
- **RF-23** — When a message tries to change the system's rules, obtain unauthorized discounts, or reveal internal instructions or other customers' data, the system shall refuse and continue to assist within its rules.

### Safety net
- **RF-24** — Before sending a reply, the system shall check that every monetary amount and percentage in it can be traced to the store's records, the manual, or the customer's own message; a reply that fails shall not reach the customer as written.
- **RF-25** — When the underlying language service is unavailable or a request cannot be completed, the system shall send a message with the store's contact details and shall not improvise an answer.

---

## 6. Non-Functional Requirements

- **RNF-01 (Performance)** — Consulting records and the manual takes under 50 ms per consultation on a developer laptop. Reply time is otherwise dominated by the language service and is measured, not promised.
- **RNF-02 (Portability)** — The language service can be replaced by configuration alone, including a free option, so that evaluators can run the project at no cost.
- **RNF-03 (Security and privacy)** — Identity rules are enforced outside the language model's judgment. Secrets never enter the repository. Conversation audit records never contain verification factors passed to the data layer.
- **RNF-04 (Observability)** — Each turn is recorded with the consultations made, latency, token usage, and safety-net outcomes.
- **RNF-05 (Reliability)** — A failed consultation or service call never crashes the conversation and never loses earlier history.
- **RNF-06 (Testability)** — All business rules can be tested without credentials or network. The current date and time can be fixed so results are reproducible.
- **RNF-07 (Simplicity)** — An evaluator can go from a fresh clone to a running conversation in under five minutes. Components are added only when they earn their place.
- **RNF-08 (Cost protection)** — When the system is publicly reachable, excess messages are refused before they consume the language service, and the provider's spending is capped outside the application.

---

## 7. Acceptance Criteria

### AC-01 (covers RF-01)
**Given** a new conversation
**When** a customer says hello
**Then** the reply is in Brazilian Portuguese, identifies a virtual assistant of the store, and asks how it can help.

### AC-02 (covers RF-02, RNF-05)
**Given** an open conversation in which a customer asked about a product
**When** the customer asks a follow-up that refers to "esse", or resumes the conversation by its identifier in a new process
**Then** the reply takes the earlier messages into account.

### AC-03 (covers RF-03)
**Given** the store is closed on a Saturday afternoon and Monday is a holiday
**When** a conversation's first reply is produced
**Then** the reply states that the store reopens on Tuesday at 09:00.

### AC-04 (covers RF-04, RF-05)
**Given** the question "Quais opções de violões disponíveis custando até R$1000?"
**When** the system answers
**Then** it lists only products that can be bought at or under R$ 1.000,00, with their correct prices, and excludes the out-of-stock and discontinued models.

### AC-05 (covers RF-05, RF-07)
**Given** the question "Quanto custa o Takamine GD20?"
**When** the system answers
**Then** it states R$ 2.199,00 and, if it mentions instant payment, R$ 2.089,05.

### AC-06 (covers RF-06, RF-07)
**Given** a product with an active promotion, such as the Ohana CK-20
**When** the customer asks its price
**Then** the reply presents R$ 549,00 as the original price, 20% off, and R$ 439,20 as the promotional price, with no further instant-payment discount.

### AC-07 (covers RF-08)
**Given** a promotion that exists in the records but is inactive, such as the 30% on the Tagima Woodstock
**When** the customer asks for that discount
**Then** the reply says it is no longer valid and states the current price of R$ 899,00.

### AC-08 (covers RF-09)
**Given** an out-of-stock, a discontinued, or a not-yet-launched product
**When** the customer asks to buy it
**Then** the reply uses the matching wording, never confirms availability, and suggests products that can be bought.

### AC-09 (covers RF-10)
**Given** a product whose description names a different brand than its name
**When** the customer asks for details
**Then** the reply does not assert the conflicting details and offers to confirm them with the team.

### AC-10 (covers RF-11)
**Given** a request for an instrument from a category with no products, such as a saxophone
**When** the system answers
**Then** it says it has no such record instead of inventing a product.

### AC-11 (covers RF-12, RF-13, RF-15)
**Given** a request for an order's status
**When** the customer gives only the order number, or gives data that does not match
**Then** no order data is disclosed, and the answer for an existing order and for a non-existing one is the same.

### AC-12 (covers RF-12, RF-15)
**Given** the order number and the email on file
**When** the customer asks for status
**Then** the reply gives status, dates and tracking code, and refers to the customer by first name only.

### AC-13 (covers RF-14)
**Given** three failed verification attempts in one conversation
**When** a fourth attempt is made, even with correct data
**Then** no order data is disclosed and the customer is directed to the team.

### AC-14 (covers RF-16)
**Given** a question on opening hours, address, payment or shipping
**When** the system answers
**Then** the answer matches the manual section consulted.

### AC-15 (covers RF-16)
**Given** a question the manual does not cover
**When** the system answers
**Then** it says it does not have that information and offers the team, without inventing a rule.

### AC-16 (covers RF-17)
**Given** a verified order delivered within the last 7 days and a customer who regrets the purchase
**When** the customer asks to return it
**Then** the reply confirms eligibility, the product conditions, the refund deadline of 10 business days, and that the store pays return freight.

### AC-17 (covers RF-17)
**Given** a verified order delivered more than 7 days ago, or not yet delivered, or cancelled
**When** the customer asks to return it out of regret
**Then** the reply explains why it is not eligible now and states the next applicable path.

### AC-18 (covers RF-17)
**Given** a verified order with a defective product
**When** the purchase is older than 30 days
**Then** the reply points to the manufacturer warranty, the store's offer to intermediate, and the legal warranty when still applicable.

### AC-19 (covers RF-18)
**Given** a question about the store's phone, email, or minimum installment
**When** the system answers
**Then** it follows the documented resolution of the manual's contradictions.

### AC-20 (covers RF-19)
**Given** a request for strings, picks, cables, cases, pedals or amplifiers
**When** the system answers
**Then** it explains that the store only sells instruments and names no partner store.

### AC-21 (covers RF-20, RF-23)
**Given** an off-topic question, a request for a made-up discount, or a request to ignore instructions
**When** the system answers
**Then** it declines politely, reveals no internal instructions, grants nothing, and offers to help with the store.

### AC-22 (covers RF-21, RF-22)
**Given** a complaint or a request for a person
**When** the system handles it
**Then** a record exists with a protocol that the reply informs, and for complaints the reply informs the 24-business-hour deadline.

### AC-23 (covers RF-24)
**Given** a draft reply with an amount or percentage that cannot be traced
**When** the safety net evaluates it
**Then** the draft is regenerated once, and if it still fails the customer receives a safe message instead.

### AC-24 (covers RF-25, RNF-05)
**Given** the language service fails during a turn
**When** the failure happens
**Then** the customer receives the store's contact details and the conversation history stays usable.

---

## 8. Domain Model Impact

- **Product, Category, Promotion, Customer, Order, Order Item** — read-only views of the store's records.
- **Policy Section** — a numbered part of the manual, with resolution notes where the manual contradicts itself.
- **Availability** — the buying situation of a product: available, temporarily unavailable, no longer in catalog, or not launched.
- **Price Quote** — list price, active promotion, final price, instant-payment price and installment limit.
- **Return Assessment** — eligibility by reason, deadline, conditions and assumptions.
- **Conversation** — history and evidence of consulted facts for one customer exchange.
- **Service Ticket** — a complaint or handover waiting for the team.

---

## 9. External Interactions

- **Inbound:** customers sending text messages through a prototype interface.
- **Outbound:** a language service chosen by configuration. Tickets are recorded locally for the team; nobody is actively notified in this prototype.

---

## 10. Assumptions

- **A1 — Receipt date:** records have no actual delivery date, so the estimated delivery date stands in for receipt on delivered orders, and the reply says so.
- **A2 — Purchase channel:** records don't say whether a purchase was online, and the right of regret applies to online purchases. Every recorded order is treated as online, and the team confirms.
- **A3 — Preference window:** the manual gives 7 days for preference exchanges without a start date. Counting starts from receipt, as in the right of regret.
- **A4 — Installments:** the manual's general table (R$ 100,00 minimum) conflicts with its detailed rules. The detailed rules win because they are more specific: up to 3x with R$ 50,00 minimum, 4x–6x with R$ 80,00, 7x–12x with R$ 100,00.
- **A5 — Contact details:** the manual has two phone numbers and two spellings of the email. Canonical values are (67) 3341-4444, which appears in the two company-data sections and is labelled phone and messaging, and contato@emporiodamusica.com.br, the cover spelling, without an accent in the domain.
- **A6 — Catalog size:** the manual claims over 300 instruments and categories such as wind and orchestral strings; records have 65 products and none in those categories. The records are the truth for what can be sold.
- **A7 — Current date:** the dataset ends in March 2026 while the assessment happens in October 2026. The system uses the real clock unless a fixed date is configured, and a past-due shipped order is reported as such.
- **A8 — Language:** customers write in Brazilian Portuguese. Project documents are in English, as the recruiter's email requires.
- **A9 — Public demo:** a demo for evaluators may lose a conversation's memory or a registered ticket when its temporary environment is replaced. The full behavior is in the local version.

## 11. Open Questions

No blocking question remains. The challenge explicitly asks for reasonable, documented assumptions; each one is in Section 10 and is repeated in the README so that the store could overrule it.

---

## 12. Success Metrics

- **Evaluation suite:** at least 90% of scripted scenarios pass against a live model, with zero tolerance in the two critical groups below.
- **Data leakage:** 0 scenarios disclose order data without valid verification.
- **Fabricated facts:** 0 scenarios deliver an untraceable price or percentage to the customer.
- **Setup:** fresh clone to first conversation in under 5 minutes by following the README.
- **After a real pilot (not measurable in this prototype):** share of recurring questions resolved without the team, with a first target of 60%; complaint handover rate; customer corrections of wrong answers.

---

## 13. Change Log

| Date | Author | Change |
|------|--------|--------|
| 2026-10-31 | Lucas Vale Queiroz | Initial draft from the challenge brief, the manual and data profiling |
| 2026-10-31 | Lucas Vale Queiroz | Added RNF-08 and A9 for a public demo |
