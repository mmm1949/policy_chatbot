# Policy Answer Retrieval Benchmark: Questions, Expected Answers and Results

This document combines the 25-question evaluation set (with expected answers) and the observed results of the post-fix run against the local API. It compares answers before and after the retrieval fixes.

## Contents

1. [Summary](#1-summary)
2. [Run details](#2-run-details)
3. [How to run a comparable evaluation](#3-how-to-run-a-comparable-evaluation)
4. [Results: answerable questions (IDs 1-20)](#4-results-answerable-questions-ids-1-20)
5. [Results: unanswerable questions (IDs 21-25)](#5-results-unanswerable-questions-ids-21-25)
6. [Metrics](#6-metrics)
7. [Interpretation and limitations](#7-interpretation-and-limitations)
8. [Follow-up items](#8-follow-up-items)

---

## 1. Summary

| Measure | Before fixes | After fixes |
|---|---:|---:|
| Historical no-answer count reported by the project owner | 15/53 (28.3%) | Not measured |
| No-answer rate on this 25-question set | Not measured | 1/20 answerable questions (5.0%) |
| Correct abstentions on unanswerable questions | Not measured | 5/5 |
| Answerable responses meeting expected evidence | Not measured | 17/20 (85.0%) |
| Partial answerable responses | Not measured | 2/20 (IDs 4 and 14) |
| Unsupported-answer rate on unanswerable questions | Not measured | 0/5 (0.0%) |

**Key points**

- The reported 15/53 result comes from saved conversation memory and is not a controlled run of this question set. It must not be copied into the per-question results or used as the baseline for this set.
- Per-question baseline outputs were not available when the fixes were applied and cannot be reconstructed reliably.
- The post-fix run is an observed run, not a controlled before/after comparison.

---

## 2. Run details

| Field | Before fixes | After fixes |
|---|---|---|
| Run date | Not recorded | 2026-11-13 |
| Endpoint | Not recorded | Local API at `http://localhost:8000/chat` |
| API health | Not recorded | Healthy |
| Questions | Not measured | 25 total: 20 answerable, 5 unanswerable |
| Conversation state | Not recorded | Fresh conversation ID for every question |
| Code version / commit | Not recorded | Not exposed by the running API |
| Model and prompt version | Not recorded | Effective settings not exposed by the running API |
| `RELEVANCE_THRESHOLD` | Not recorded | Effective value not exposed by the running API |

**Retries:** Two requests (IDs 8 and 17) initially received HTTP 503 because of a Groq rate limit. Both were retried with fresh conversation IDs and returned HTTP 200. The results below record the successful retry responses.

**Authentication:** When `API_AUTH_TOKEN` is configured, `/chat` requires `Authorization: Bearer <API_AUTH_TOKEN>`. Tokenless local development is allowed and logged. Unit tests with fake models do not produce benchmark answers.

**Notes on the answers:** The observed answers are summaries of the API's actual responses, for readability. Source lists and raw reranker scores are as returned. A reranker score is not a calibrated confidence value.

---

## 3. How to run a comparable evaluation

1. Use the same policy PDFs, model, prompt version and retrieval settings for both code versions. Record the version/commit and `RELEVANCE_THRESHOLD`.
2. Run this exact question list once on the pre-fix version and once on the fixed version. Use a fresh conversation ID per question so saved memory cannot change later answers.
3. Record the full answer and returned source list in the before/after columns. Mark whether a no-answer fallback was returned.
4. Score answers against the expected evidence. An answer is not correct merely because it avoided the fallback; unsupported factual answers to the unanswerable questions count as false answers.

Expected answers are based on the policy PDFs in `server/data/documents/`. They are evaluation references, not answers measured from the chatbot.

---

## 4. Results: answerable questions (IDs 1-20)

### Merchant onboarding and terms

| ID | Question | Expected answer / evidence | Observed answer | Sources | Score | Assessment |
|---:|---|---|---|---|---:|---|
| 1 | What documents must a merchant provide during onboarding? | PAN, GST, bank details, address proof and business registration documents. [merchant_onboarding_terms_and_conditions.pdf, p. 1] | Valid, verifiable documents: PAN, GST registration, bank details, address proof and business registration. | merchant_onboarding_terms_and_conditions.pdf, p. 1 | 0.999 | Meets expected answer |
| 2 | What compliance checks does Toucan perform during onboarding? | KYC and AML checks required by applicable regulations. [merchant_onboarding_terms_and_conditions.pdf, p. 1] | KYC and AML verification, plus background/document validation and business background checks. | merchant_onboarding_terms_and_conditions.pdf, p. 1; fraud_monitoring_and_prevention_policy.pdf, p. 2 | 0.929 | Meets expected answer; includes additional cited checks |
| 3 | Can Toucan reject or suspend an onboarding application with incomplete or suspicious documents? | Yes. It reserves the right to reject or suspend onboarding for incomplete, incorrect or suspicious documentation. [merchant_onboarding_terms_and_conditions.pdf, p. 1] | Yes. Toucan may reject or suspend onboarding for incomplete, incorrect or suspicious documents. | merchant_onboarding_terms_and_conditions.pdf, p. 1 | 1.000 | Meets expected answer |
| 4 | What is the refund policy merchants must communicate to customers? | Merchants must clearly disclose refund, return and cancellation policies. For an eligible cancelled transaction, refund details are processed to the original source account. [merchant_onboarding_terms_and_conditions.pdf, p. 1; customer_dispute_resolution_mechanism.pdf, p. 2] | Merchants must clearly disclose refund, return and cancellation policies; the answer says the documents do not provide specific policy wording. | merchant_onboarding_terms_and_conditions.pdf, p. 1 | 0.519 | **Partial:** omits the eligible-cancellation refund-to-original-source detail |
| 5 | What payout-cycle examples are given in the merchant terms? | T+1 and T+2 are examples; the actual cycle is the one agreed with the merchant. [merchant_onboarding_terms_and_conditions.pdf, p. 1] | T+1 and T+2 are payout-cycle examples. | merchant_onboarding_terms_and_conditions.pdf, p. 1 | 0.190 | Meets expected answer |
| 6 | How are standard MDR or transaction fees handled? | Standard MDR or applicable transaction fees are deducted before settlement; no specific rate is stated. [merchant_onboarding_terms_and_conditions.pdf, p. 1] | Standard MDR and applicable transaction fees are deducted before settlement; no specific rate provided. | merchant_onboarding_terms_and_conditions.pdf, p. 1 | 0.748 | Meets expected answer |
| 7 | What is the merchant responsible for if a chargeback is successful? | Reimburse the full transaction amount and any applicable penalties. [merchant_onboarding_terms_and_conditions.pdf, p. 1] | The merchant reimburses the full transaction amount and any applicable penalties. | merchant_onboarding_terms_and_conditions.pdf, p. 1 | 0.971 | Meets expected answer |

### Dispute resolution

| ID | Question | Expected answer / evidence | Observed answer | Sources | Score | Assessment |
|---:|---|---|---|---|---:|---|
| 8 | What are the stages in the transaction and dispute lifecycle? | Initiation, authorization, capture, clearing, settlement, reconciliation, dispute raised, investigation, resolution and closure. [customer_dispute_resolution_mechanism.pdf, p. 5] | Initiation, authorization, capture, clearing, settlement, reconciliation, dispute raised, investigation, resolution, closure. | customer_dispute_resolution_mechanism.pdf, p. 5 | 0.990 | Meets expected answer |
| 9 | How soon should a customer dispute be acknowledged? | Within 24 hours. [customer_dispute_resolution_mechanism.pdf, p. 5] | Acknowledge within 24 hours; also cites the one-business-day escalation entry. | fraud_monitoring_and_prevention_policy.pdf, p. 4; customer_dispute_resolution_mechanism.pdf, pp. 5-6 | 0.295 | Meets expected answer |
| 10 | How quickly must a merchant respond to dispute queries? | Within 48 hours, with requested documentation. [customer_dispute_resolution_mechanism.pdf, p. 6] | The merchant must reply within 48 hours. | customer_dispute_resolution_mechanism.pdf, p. 6 | 0.736 | Meets expected answer |
| 11 | When is documentation from dispute stakeholders due? | Within 4 business days. [customer_dispute_resolution_mechanism.pdf, p. 5] | Requested documentation is due within 4 business days. | customer_dispute_resolution_mechanism.pdf, p. 5 | 0.125 | Meets expected answer |
| 12 | By when should final customer communication be sent for a dispute? | Within 10 working days. [customer_dispute_resolution_mechanism.pdf, p. 6] | Final communication is due within 10 working days. | customer_dispute_resolution_mechanism.pdf, p. 6 | 0.731 | Meets expected answer |
| 13 | How soon should a customer report a dispute? | Within T+3 days, with evidence. [customer_dispute_resolution_mechanism.pdf, p. 6] | Raise within T+3 days and provide supporting evidence. | customer_dispute_resolution_mechanism.pdf, p. 6 | 0.840 | Meets expected answer |
| 14 | What should happen when a customer is charged twice for one product? | The merchant initiates a refund for the duplicate transaction and informs the issuer bank and customer. [customer_dispute_resolution_mechanism.pdf, p. 1] | Provide invoice copies for both orders, refund one, then the system reconciles by webhook and notifies the customer. | customer_dispute_resolution_mechanism.pdf, p. 1 | 0.801 | **Partial:** does not mention informing the issuer bank |
| 15 | What should a merchant do after a card transaction is declined with reason code 59? | The issuer suspects fraud. Monitor transactions processed after the decline. [customer_dispute_resolution_mechanism.pdf, p. 4] | Reason code 59 means suspected fraud; monitor subsequent transactions. | customer_dispute_resolution_mechanism.pdf, p. 4 | 0.885 | Meets expected answer |

### Termination and offboarding

| ID | Question | Expected answer / evidence | Observed answer | Sources | Score | Assessment |
|---:|---|---|---|---|---:|---|
| 16 | How much notice does a merchant need to give to terminate the agreement? | Either party may terminate with 30 days' written notice. [merchant_onboarding_terms_and_conditions.pdf, p. 2] | Either party must give 30 days' written notice. | merchant_onboarding_terms_and_conditions.pdf, p. 2 | 0.925 | Meets expected answer |
| 17 | When can Toucan immediately suspend or terminate a merchant? | Fraud, breach of law or violation of the agreement terms. [merchant_onboarding_terms_and_conditions.pdf, p. 2] | Immediate suspension or termination may apply for fraud, breach of law or violation of agreement terms. | merchant_onboarding_terms_and_conditions.pdf, p. 2 | 0.966 | Meets expected answer |
| 18 | What must an offboarding notice communicate to a merchant? | The reason, effective termination date, outstanding settlements or dues, and instructions for data retrieval or record closure. [merchant_offboarding_policy.pdf, p. 2] | The reason, effective date, outstanding settlements/dues, and data-retrieval or record-closure instructions. | merchant_offboarding_policy.pdf, p. 2 | 0.942 | Meets expected answer |
| 19 | What financial and dispute steps happen before offboarding? | Reconcile outstanding payments, address ongoing disputes and potential chargebacks, and retain necessary funds for pending disputes or regulatory obligations. [merchant_offboarding_policy.pdf, p. 2] | Returned the fixed no-answer response: "I could not find a verified answer in the policy knowledge base. Please ask a question related to the available merchant policy documents." | None | 0.000 | **No-answer fallback;** expected answer was available |
| 20 | What obligations can continue after a merchant is offboarded? | Reconciliation of post-offboarding settlements, chargebacks or disputes. [merchant_offboarding_policy.pdf, p. 2] | Reconciliation of settlements, chargebacks and disputes, plus providing documents regulators may request for audit. | merchant_offboarding_policy.pdf, p. 2 | 0.949 | Meets expected answer; includes an additional cited obligation |

---

## 5. Results: unanswerable questions (IDs 21-25)

The assistant should abstain or state that the information is not specified, rather than invent an answer.

| ID | Question | Expected behaviour / evidence | Observed answer | Sources | Score | Assessment |
|---:|---|---|---|---|---:|---|
| 21 | What exact MDR percentage will be charged to my business? | Terms say applicable MDR/transaction fees are deducted but give no specific merchant rate. Should say the rate is not specified. | Fees are deducted before settlement, but the exact MDR percentage is not specified. | merchant_onboarding_terms_and_conditions.pdf, p. 1 | 0.041 | Correct abstention |
| 22 | What exact payout cycle has been assigned to my account? | T+1 and T+2 are only examples; no individual cycle is identified. Should not guess. | T+1 and T+2 are examples; the assigned cycle for this account is not specified. | merchant_onboarding_terms_and_conditions.pdf, p. 1 | 0.058 | Correct abstention |
| 23 | Which exact business categories are prohibited? | Documents refer to illegal or restricted activities and an acceptable-use policy but do not enumerate categories. Should say the list is not available. | Categories are not enumerated; documents refer to illegal/restricted activities and the acceptable-use policy. | merchant_offboarding_policy.pdf, p. 1; merchant_onboarding_terms_and_conditions.pdf, p. 1 | 0.324 | Correct abstention |
| 24 | How many years is merchant data retained after offboarding? | Offboarding policy refers to the period mandated by RBI guidelines but gives no duration. Should not invent a number. | Retained for the period mandated by RBI guidelines; no number of years given. | merchant_offboarding_policy.pdf, p. 2 | 0.961 | Correct abstention |
| 25 | What is the exact number of days for filing a card-network chargeback? | Dispute policy refers to network timelines but states no specific number of days. Should say the deadline is not specified. | Refers to network timelines; no exact number of days stated. | customer_dispute_resolution_mechanism.pdf, p. 6 | 0.864 | Correct abstention |

---

## 6. Metrics

**Definitions**

```text
answerable no-answer rate =
  answerable questions returning the fixed no-answer response / 20

unsupported-answer rate =
  unanswerable questions receiving an unsupported factual answer / 5
```

An overall fallback percentage over all 25 questions is not a sufficient quality metric: the five unanswerable cases should generally be refused, while the 20 answerable cases should receive grounded answers.

**Post-fix results**

| Metric | Result |
|---|---:|
| Answerable questions returning the fixed no-answer fallback | 1/20 (ID 19) |
| Answerable no-answer rate | **5.0%** |
| Answerable responses meeting expected evidence | 17/20 (85.0%) |
| Partial answerable responses | 2/20 (IDs 4 and 14) |
| Unanswerable questions correctly abstained | 5/5 |
| Unsupported-answer rate on unanswerable questions | **0/5 (0.0%)** |
| Final successful API responses | 25/25 (100% after retrying two transient rate limits) |

The no-answer rate measures only fallback responses; it does not count partial answers as fallbacks. IDs 4 and 14 are partial against the expected evidence, so the no-answer metric alone overstates complete answer quality.

---

## 7. Interpretation and limitations

- The 5.0% result is an observed run against the currently running local API, whose endpoint behaviour matched the updated development authentication flow. The API does not expose a build identifier, so the exact source revision serving every response could not be verified. It is not a controlled before/after comparison.
- The project owner's historical 15/53 fallback count (28.3%) came from different saved conversations and must not be used as the baseline for this 25-question set.
- The baseline answers, running code commit and effective model/prompt/threshold settings were not available from the API. A valid paired comparison needs those captured and the same questions run against the pre-fix and fixed versions.
- Raw reranker scores are not calibrated confidence values. Some correct answers had low scores (for example ID 11 at 0.125, ID 5 at 0.190), and some abstentions had high scores (ID 24 at 0.961).

---

## 8. Follow-up items

1. Review retrieval/answer completeness for **refund terms** (ID 4) and **duplicate transactions** (ID 14).
2. Investigate why **ID 19** (pre-offboarding financial and dispute steps) returned the no-answer fallback despite relevant content on `merchant_offboarding_policy.pdf`, p. 2.
3. Record the code commit, model, prompt version and `RELEVANCE_THRESHOLD` for each run.
4. Run the same 25 questions on the pre-fix version to obtain a valid paired baseline.