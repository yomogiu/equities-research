# Reviewed HTML financial cells

Ordinary HTML financial statements without numeric inline-XBRL tags require an
explicit adapter selection. `earnings_report_flow.prepare(...,
reviewed_financial=selection)` accepts private `profile_path`, `review_path`, and
`authorization` fields. Paths are relative to the configured private root. It
does not discover a profile, automatically fall back from failed inline-XBRL, or
change issuer, completeness, fiscal-period, freshness, or transcript gates.

The authorization is externally reserved by the coordinator. It contains
`version: reviewed-html-financial-v1`, `enabled: true`, exact `source`,
`profile_sha256`, `review_sha256`, and distinct `author_id` / `reviewer_id`.
The source object contains the packet document's `document_id`, `raw_sha256`,
`text_sha256`, and packet `issuer_id`. Hashes bind exact file bytes.

A profile contains `version`, `source`, `author_id`, and `observations`. Each
observation has exactly:

- A unique `key`, explicitly reviewed `concept`, integer `scale` (-9 through 12),
  and `accounting_basis`. There is no author-supplied numeric value.
- `context`: `entity` equal to the qualified packet issuer ID,
  `entity_scheme: qualified_packet_issuer_id`, ISO `start_date` / `end_date` or
  `instant` (unused fields null), and `dimensions`. Dimensions have `dimension`,
  `member`, and `type` (`explicitmember` or `typedmember`). These are reviewed
  source descriptors, not a claim that the HTML contains XBRL tags.
- `unit`: lists `numerator` and `denominator`, using explicit namespace-qualified
  measures such as `iso4217:CAD` and `xbrli:shares`. Currency amounts in millions
  have scale 6; per-share amounts retain scale 0. No unit is guessed.
- `table`, `row`, `label`, and `value_cells`: original raw-HTML spans, each with
  `start`, `end`, and `raw_span_sha256`. Offsets are Unicode codepoints in the
  original UTF-8 document, end exclusive. Table/row/label/value selections must
  match complete original HTML elements. Value cells must be contiguous in one
  row, excluding its label, and contain exactly one numeric cell. This supports
  currency/parentheses split across adjacent presentation cells without treating
  two numeric columns as one number. No grid-position or table-order heuristic
  assigns reporting periods: the profile selects exact cells.
- `evidence`: nonempty lists of exact raw spans for `period`, `unit`, `entity`,
  and `basis`. Review must inspect the complete headings, row, table context and
  unit exceptions. Exact spans establish source location; they do not establish
  the semantic correctness of the proposed metadata without that review.

The review contains `version`, `source`, `profile_sha256`, matching `author_id`,
the reserved `reviewer_id`, `verdict: pass_profile_only`, and exactly one
`decisions` entry per observation. Each entry contains `key`, `verdict: pass`,
and `observation_sha256`, computed with financial_evidence's canonical JSON.
The coordinator must actually delegate or obtain independent review; a label in
a JSON file is not independent review by itself. Changing any selected field
requires newly reviewed bytes and a new authorization.

Code copies numeric text, preserves signs and decimal precision, and applies the
reviewed scale with Decimal arithmetic. Comma grouping and decimal points use the
explicit supported numeric format. Blanks, dashes, percentage suffixes, footnoted
numbers, nested tables and ambiguous numeric layouts fail closed. This initial
adapter does not infer zero or nil from a dash, derive missing quarters, or
calculate margins, growth or currency conversions. Select only unambiguous
numeric cells; keep other required metrics as explicit evidence gaps.

Select distinct concepts or explicit dimensions for different accounting bases,
segments and constant-currency comparisons. The same concept/entity/unit/dimensions
cannot silently change accounting basis across observations. Keep quarter and
YTD durations separate, and preserve original row labels. The reviewed basis is
visible in rendered rows; profile approval does not imply complete statement
coverage or financial/report acceptance.

Preparation freezes the selection authorization and original profile/review files.
Compact evidence replays the extraction against those frozen inputs before
accepting `reviewed_html_table` observations. `financial_evidence.validate_artifact`
requires those independently bound replay inputs for the new method; resealing
an edited value is insufficient. Financial scopes use original raw-source
offsets, hashes, row labels, and complete row context. Frozen inline-XBRL runs
keep their original path without modification.

Private profiles and issuer sources must never enter this public repository.
The test fixtures are fictitious and do not authorize live extraction or jobs.
