# Deterministic financial comparison tables

`deterministic-financial-analysis-v1` computes tables from the complete qualified
financial inventory in an authenticated compact evidence bundle. It does not
select facts from an earnings-call paraphrase or restrict coverage to the legacy
financial author's starting rows. It runs without a model.

## Produce a financial-only preview

```sh
python3 -m research.earnings_financial_analysis_report \
  --manifest /private/example/evidence/manifest.json \
  --quarter-start 2026-07-01 --quarter-end 2026-09-30 \
  --config /private/example/financial-analysis-config.json \
  --output /private/example/financial-preview
```

Paths above are fictional. Real inputs and outputs stay in the private runtime.
The command writes JSON, Markdown and HTML. Existing outputs cannot be overwritten
with different content. This preview is a calculation artifact; report acceptance
is a separate workflow.

Configuration explicitly binds the version, actual fiscal-quarter start/end,
as-of date, per-fact capital-expenditure sign conventions and any caller-declared
accounting bases. The CLI dates must agree with the configuration. It does not
derive fiscal dates from a ticker or `FY...` label.

## Table behavior

Each row retains entity, accounting basis, currency/unit and segment dimensions.
The table shows the current value, prior-quarter value, prior-year value and
absolute/relative changes. Quarterly, six-month, nine-month, annual and instant
observations stay separate. Other filed dates remain available as separately
dated reference observations; a year-end balance is never relabeled QoQ.

| Measure | Calculation or treatment |
| --- | --- |
| Amount change | Current minus comparable prior amount |
| Relative change | Amount change divided by a positive prior amount |
| Zero/negative prior amount | Absolute change retained; percentage is N/M |
| Gross profit | Reported gross profit, or revenue less cost of revenue when compatible |
| Operating/net margin | Matching-period operating/net income divided by revenue |
| Cash-flow margins | Matching-period operating/free cash flow divided by revenue |
| Free cash flow | Operating cash flow less explicitly normalized PPE payments |
| Capex intensity | Positive PPE payment amount divided by matching-period revenue |
| Liquid assets | Cash and equivalents plus separately disclosed short-term investments |
| Total/net debt | Compatible current plus noncurrent debt; net debt subtracts cash and equivalents |
| Margin change | Current percentage minus prior percentage, expressed in percentage points |

Calculated free cash flow is the stated OCF-minus-PPE measure. It does not silently
include acquisitions, securities purchases, leases, capitalized interest or other
investing flows. Liquid assets and net debt retain their separate definitions.

All arithmetic uses Decimal. Exact values, source fact IDs, source labels,
operands and formulas remain in JSON even where the table rounds a percentage.
Reported and calculated values are distinguishable. Calculation does not turn a
derived ratio or FCF measure into a company-reported GAAP measure.

## Comparability and source coverage

- Quarter comparisons require actual adjacent filed periods. Instant QoQ uses
  the day immediately before the explicit quarter start. Year comparisons use
  both filed boundaries with a bounded 52/53-week elapsed-date matcher.
- Additive monetary flows may be derived from matching cumulative periods with
  the same fiscal start. EPS and weighted-average shares are never obtained by
  subtracting YTD observations.
- Currency, entity, accounting basis and dimensions must match. Segment and
  consolidated measures remain distinct. Shareholder-attributable income does
  not acquire a consolidated net-income identity.
- Independently reviewed HTML mappings can establish the same concept across
  differing row labels. Original labels remain in provenance. No fuzzy label
  matching or invented taxonomy alias is used.
- Equal duplicate observations retain their source IDs. Conflicting duplicates,
  reported/derived disagreements and ambiguous operands produce explicit gaps.
- Signed cash-flow PPE outflows require an explicit `signed_cash_flow` convention
  for each fact. A positive-payment convention cannot silently accept negative
  values or reclassify refunds by taking an absolute value.
- A caller-declared basis is labeled as a declaration, with its assumption kept
  in the artifact. It cannot replace a conflicting source-established basis or
  serve as independent source qualification.
- A missing or incompatible comparator is unavailable, never zero. Unsupported
  source metrics remain available as reported rows without acquiring formulas.

The calculation layer cannot recover a numeric cell omitted during extraction.
For releases with ordinary HTML tables, broaden an exact-cell profile and obtain
an independent mapping review before using the new observations. For instance,
QoQ revenue requires the prior quarter itself; a prior-year amount cannot fill
that slot. Blank/dash source cells require their own source interpretation and
are not automatically zero.

## Optional report integration

New deterministic six-section file pipelines may freeze this feature and its
configuration explicitly. The pipeline stores `financial-analysis.json`, binds
its digest in the protocol and recomputes it from frozen inputs when loading.
The financial tables render from that verified artifact, independent of model
row selection and formatting prose. Narrative authors receive a read-only table
handoff and can focus on explanation rather than repeating the tables.

For a new file pipeline, the same configuration can be frozen explicitly:

```sh
python3 -m research.earnings_file_pipeline initialize \
  --case /private/example/case.json --output /private/example/new-pipeline \
  --writing /private/example/writing-standard.md \
  --financial-analysis deterministic-financial-analysis-v1 \
  --financial-analysis-config /private/example/financial-analysis-config.json
```

This initializes the new pipeline without executing a model role.

The option is absent by default. Existing frozen protocols and accepted reports
retain their previous behavior. This change does not enable recurring jobs,
change review criteria or rebuild the publication layer.

## Verification

The focused test modules cover arithmetic, period/basis/dimension conflicts,
capex signs, missing comparisons, provenance, immutable recomputation, rendering
and compatibility of protocols without the option. Run full unittest discovery
and CLI help before committing code. Public fixtures must remain fictional;
private source-backed previews supplement rather than replace these tests.
