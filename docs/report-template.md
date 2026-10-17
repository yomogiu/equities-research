# Source-led earnings report template

New `research.earnings_file_pipeline.initialize` runs freeze
`report_template: source-led-six-sections-v1` by default. The marker is part of
the authored analysis, report digest and review units. Historical runs and
authenticated prepared continuations keep their recorded format. No migration,
new model stage, schedule change or budget increase is performed.

## Report structure

1. **Quarter in Focus:** the existing substantive opening.
2. **Growth & Demand:** compiled revenue rows and source-backed demand commentary.
3. **Earnings & Efficiency:** compiled profit/EPS rows and their drivers.
4. **Cash & Financial Capacity:** cash flow, investment and balance-sheet rows.
5. **Outlook & Guidance:** company guidance and its stated conditions.
6. **Earnings-Call Q&A:** consequential questions,
   management responses, qualifications and unresolved details.

The opening remains a substantive textual summary. Section findings retain material
explanations of drivers, mechanisms, management commentary, qualifications and
unresolved details; they may span multiple paragraphs. Tables support this narrative
rather than replacing it with captions. Source material determines depth, without
word or paragraph quotas. The existing reviewer checks material narrative omissions.

Scope and original source references follow as supporting material. There is no
next-tests/watchlist section. Valuation is optional commentary only if the supplied
evidence provides dated price and forecast estimates with compatible currency,
listing/share basis and forecast period. It is never a requirement to fetch more
context. Sector-specific operating metrics can be discussed from supplied sources;
this version does not invent structured observations from narrative disclosures.

## Roles and deterministic work

The existing financial preparation compiles selected original qualified facts.
The new default extends the starting metric list, up to the existing 12-row limit,
to include available gross profit, CapEx, inventory, liabilities and diluted shares.
Quarterly operating cash flow is preferred over YTD when both are available.
Absent facts remain absent; PDF proposals still need independent qualification.
Extraction, qualification and completeness are not established by rendering.

Python assembles the financial tables and routes known statutory revenue/profit
concepts to their sections. Other selected measures remain in cash/financial
capacity as filed detail, preserving their explicit labels. Each unit and exact
period group remains separate. Decimal arithmetic calculates QoQ and YoY changes
from compatible observations in the same row, with citations to both inputs.
No YTD-to-quarter comparison, zero/loss-base growth percentage, ratio-to-margin
conversion or fiscal-year guess is permitted. An unavailable comparison is `—`;
a nonpositive base is `n/m`. Sources are not modified.

The author supplies the existing opening and findings plus a `section` enum
(`demand`, `earnings`, `cash`, `outlook`, `qa`) on each finding. It returns
`next_tests: []`. Q&A selection reuses complete-call retrieval; the model explains
actual exchanges rather than generating an additional research questionnaire.
The independent reviewer assesses the exact compiled report through the existing
review/correction lifecycle. Corrections cannot remove the template marker.

Existing optional reviewed business signals appear next to their findings as
scoped direction/basis/period labels, without a separate repeated summary strip.
Financial change colouring is deterministic: green/red for a conservative set of
revenue/profit/EPS/operating-cash-flow labels, neutral for context-dependent or
unknown measures. Arrows and signed numbers accompany colour. Neutral does not
mean favourable or adverse. Tables scroll on narrow screens.

Legacy folds and supplemental source-row overlays are rejected by the new table
compiler rather than silently dropped. New runs use original numeric rows and
source-bound row/table labels. Existing historical renderers still support their
frozen formats. Use `initialize(..., report_template=None)` for an explicitly
legacy-format new run. Do not change a frozen protocol to switch format.

## Adoption and rollback

The code checkpoint before this change is `593db0b` (active code baseline
`d3132ff`). The new code defaults apply when a coordinator adopts this commit
for a **new** run. Existing private workflow pins and accepted reports are not
rewritten by installing this code. Reverting the template commit or restoring the
previous workflow pin restores the former default for new runs.

The [fictional preview](../examples/report-template.fake.md) demonstrates structure
and colour rendering, not an independently reviewed investment report. Model-free
tests exercise a complete simulated lifecycle, including independent-role receipts,
corrections, report replay and source links. No real model-cost saving is claimed
until a bounded run measures it; table assembly itself makes zero model calls.

## Original earnings-call exchanges

Q&A findings with exact exchange or member-turn citations receive expandable
“Read the original exchange” blocks in HTML. Python resolves the reviewed index,
includes linked parent questions/follow-ups, verifies the frozen transcript hash
and copies each original turn by its Unicode offsets with speaker attribution.
It does not infer exchanges from topic keywords or generate replacement quotations.
Only exchange-ID directives enter report Markdown; the original text is assembled
locally into HTML. This adds no model stage or repeated transcript payload to
review context. Render through `earnings_markdown.write` with the source bundle;
standalone rendering of a directive without source payload fails explicitly.
