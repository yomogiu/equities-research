# Financial display and bounded repair experiment

The opt-in `research.earnings_passage_pipeline` now freezes version
`luna-sol-presentation-v3`. Keep earlier frozen checkouts and runs unchanged.
This is experimental code; it does not enable production analysis or scheduling.

The financial worker selects source fact IDs and supplies source-backed context.
`research/earnings_financial_display.py` owns displayed metric identity, units,
scaling and comparison columns. Currency totals and share counts display in
millions; per-share observations and pure ratios retain their original scale.
Decimal conversion is exact. Mixed metrics are split into rows. Entities,
dimensions, units and quarterly versus year-to-date contexts stay separate.
Duplicate matching facts retain all evidence IDs; conflicting values fail.

Dates are filed observation contexts. Subsequent-event timing, payment-horizon
interpretation and comparability adjustments still require source-backed
financial context and substantive review. The renderer does not invent fiscal
years, new ratios, or historical comparisons that the worker did not select.

For malformed passage IDs, code supplies up to three similar IDs and one adjacent
passage on either side in the same original scope. Windows preserve exact source
text and offsets, are capped at 12,000 characters per slot and 24,000 total, and
are suggestions only. A worker may edit only failed slots and select only supplied,
substantive, unused IDs. No matching window or an explicit worker refusal produces
a source-selection handoff instead of a full-corpus retry. Broader evidence repairs
require a separate, explicitly scoped run.

Reviewers route display defects to `formatter`, selection/context defects to
`financial`, evidence interpretation to `retrieval`, and report prose to
`analysis`. A formatter finding stops the model correction loop and saves
`repair-handoff.json`, bound to the protocol, exact artifacts and review. Substantive
findings remain unresolved. The handoff is a code-repair queue, not an automatic
code-agent launcher. Repair in a new code/run version, rerender, and independently
review before acceptance. Existing two-round limits remain in effect.

Run all tests with `python3 -m unittest discover -s tests -v`, then
`python3 -m research.cli --help`. Tests use fictional evidence and mocked model
calls. Rendering a previous run is a deterministic preview, not a new generation
benchmark, quality pass, or measurement of provider token savings.
