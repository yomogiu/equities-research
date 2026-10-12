# Checked evidence handoffs

New factual/editorial split requests bind
`checked-facts-cited-filing-full-call-v2`. Existing frozen requests retain their
original context policy, sources, author/reviewer outputs and correction budgets.

Before a new author or reviewer call, the controller resolves every registered
D/F/P/turn/exchange reference in the relevant artifacts, gap prose and outstanding
findings. Complete original spans are materialized and hash checked; exchange
references retain all original turns. Unknown IDs stop before the model with the
exact IDs. Registry absence is not proof that a document is unavailable publicly.
No source fetch is dispatched by this contract.

Author prompts append only complete original spans not already supplied. Reviewer
packets carry the checked source closure, while original passages and observations
remain in the existing lossless source view. Previews cannot satisfy full spans.
The registry certifies source availability, never factual support or accounting
basis. Potential stale absence claims are explicitly flagged for factual review.

If a completed reviewer asserts that an existing but previously deferred source
was unavailable, one fresh scoped source-handoff reviewer checks only those units
against the complete requested original passages. It cannot rewrite artifacts or
reopen accepted units. Its request binds the original review findings, complete
batch, protocol and evidence packet. Completed authenticated calls replay; uncertain
calls hold without retries. Already supplied sources do not trigger another check.

A pass preserves unchanged unit hashes and other acceptance receipts. Residual
substantive findings return to the normal bounded author flow. A persistent source
absence assertion stops with a diagnostic rather than repeating the check. Source
transport and its separately recorded review do not spend an author round; actual
factual edits still spend one of the original two rounds. This mechanism never
provides a third author round or promotes a draft directly to production.

After factual acceptance the final editorial gate, private import and later fresh
remote-byte verification remain mandatory. The host controller advances pending
source checks through the ordinary locked pipeline, with at most one new model
call per advance. It reports source-check usage separately in repair handoffs.
