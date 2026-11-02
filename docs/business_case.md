# Business case for Empório da Música

The prototype answers a technical question: can an agent serve customers without inventing facts? The store's question is different: is it worth using, and how would we know? This page separates what was measured from what still has to be measured.

## What the store gets

| Today | With the agent |
|---|---|
| The team answers every recurring question | Hours, prices, stock and order status are answered at any time |
| Replies wait for someone to be free, and the manual targets 5 minutes in opening hours | A reply takes seconds, at any hour |
| A price or stock mistake can amount to misleading advertising, as the manual warns | Prices come from records, and a reply with an untraceable value is blocked |
| Complaints arrive mixed with everything else | Complaints and handovers arrive with a protocol and a summary |

The agent also found problems the store didn't ask about. The manual has two phone numbers and two installment rules, and the records have products whose description names another brand. These are [listed in full](data_quality.md), and fixing them helps human attendants too.

## Measured

From the [evaluation report](../evals/reports/gemini-3.8-flash.json), with `gemini-3.8-flash` at the price valid until 2026-12-31:

| Measure | Value |
|---|---|
| Cost per scenario | About USD 0.0065 (USD 0.30 for 47 scenarios) |
| Cost per scenario from 2027-01-01, when the listed price doubles | About USD 0.013 |
| Median reply time per turn | 8.2 s |
| Scenarios passed | 47 of 47, on scripted scenarios and not on real customers |

These scenarios are short. A long real conversation costs more, since each turn resends its history.

## Not measured yet

The store's own numbers are unknown, so this estimate is a formula to fill in, not a promise.

```
Monthly saving = recurring conversations per month
               x share resolved without the team
               x minutes saved per conversation
               x attendant cost per minute
               - monthly cost of the agent
```

An **illustration only, with invented inputs that the store should replace**: 1,000 conversations a month, 60% resolved, 3 minutes each and R$ 0.40 per minute gives R$ 720 a month in attendant time. At the measured cost, the model would cost about USD 13 a month from 2027 on those 1,000 conversations, excluding hosting and maintenance. The model isn't the expensive part, which makes the resolution rate the number to watch.

## How I'd run a pilot

| Stage | What happens | Goes ahead when |
|---|---|---|
| 1. Shadow, 2 weeks | The agent drafts, and an attendant reviews and sends each reply | At least 95% of drafts are sent with no factual correction |
| 2. Recurring questions only | The agent answers hours, catalog and policies, and orders stay with the team | Customers correct a fact in under 1% of conversations |
| 3. Orders and returns | Identity comes from the messaging channel, and returns go to the team with a summary | No data incident, and fewer than 5% of returns are wrongly assessed |

The thresholds are my starting proposal, to be agreed with the store. Stage 1 costs the least and also produces real conversations for the evaluation suite.

## What to measure from day one

- **Resolution:** share of conversations closed without a person, counting only those where the customer doesn't return on the same subject within 48 hours.
- **Accuracy:** factual corrections per 100 conversations, from a weekly sample read by a person. Scores alone missed invented product details in this project, which only reading the replies caught.
- **Time saved:** attendant hours on recurring questions, before and after.
- **Experience:** reply time, and satisfaction compared with human service.
- **Safety:** replies blocked by the safety net, and any disclosure of personal data, with a target of zero.

## Main risks for the store

| Risk | Mitigation |
|---|---|
| A wrong non-numeric claim about a product | Replies are limited to the records, a weekly sample is read, and shadow mode comes first |
| Stale stock in a real deployment | Connect to the stock system before stage 2 |
| Customers want a person | Handover is available at any point, and the rate is tracked |
| Personal data in conversations | Retention policy, and identity from the channel, before stage 3 |
