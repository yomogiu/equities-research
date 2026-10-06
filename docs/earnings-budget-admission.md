# Correction and repair-review budget admission

Before launching a deterministic correction author, correction reviewer, or
targeted-remediation reviewer, reserve one input token per UTF-8 prompt byte,
4,096 tokens for runtime framing, and 32,768 tokens for output/reasoning. Every
evidence-expansion review gets a fresh admission check after subtracting measured
usage from its predecessor. Insufficient room stops before launch; it does not
increase the budget, omit evidence, or retry a partially launched job.

This is a conservative **estimated reservation**, not an exact tokenizer, provider
output cap, or guarantee about hidden runtime work. Typical prose input will cost
less; the byte-based fallback can therefore stop work that a calibrated tokenizer
would admit. This implementation does not infer calibration from untrusted model
content. Authenticated runtime receipt counters remain the only measured usage;
reserved amounts never replace or add to those counters. Actual output can still
exceed its allowance, so completed receipts require a separate compliance check.

A completed review is validated even if measured usage exceeds the budget. Its
authenticated verdict, candidate/plan bindings, and validation result remain
inspectable as substantive-review metadata. Official acceptance remains blocked,
and an over-budget approval does not apply the proposed patch. A malformed saved
review remains invalid rather than being hidden behind a budget status.

This admission policy currently covers the calls above. It does **not** yet cover
base-pipeline preparation/review calls, the older reviewer-repair driver, or the
separate signals author/reviewer. Their existing accounting and limits remain;
this change is not a claim of pipeline-wide provider-side cost enforcement.
