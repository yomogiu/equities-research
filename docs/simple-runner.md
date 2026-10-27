# Finite earnings-report runner

`research.earnings_simple_runner` is the default execution path for new reports. It does not import
any sequential controller, single-author controller, recovery graph or handoff.
`earnings_report_content` holds shared report schemas, period resolution and rendering;
historical callers re-export these helpers. Extraction, original-table inventory,
financial selection validation, Decimal calculations and signed-in transport are reused.

Each company runs Sources → author → independent review → publication. A compiler
error or material review finding allows exactly one correction and one independent
check. The result is published or failed. There are no migrations, extra allowances,
successor jobs or operator resumes. A failed company does not prevent the next one.
An interrupted paid attempt is terminal and explicitly has incomplete usage; it is
never silently retried or reported as free. A new invocation returns existing terminal
results without another model call.

Author and reviewer: GPT-6.1 Sol, medium. Correction: GPT-6 Luna, max. Sessions are
independent, tool-free, one output each, with a fixed cumulative 1.2-million-token cap.
Every measured attempt is charged before output validation. Raw receipts and prior
candidates remain immutable. Unknown usage stays unknown.

The author receives the complete extracted financial inventory and captured tables,
full current-quarter filing/release/presentation/call, and annual financial statements,
notes and appendices. Annual business/risk/MD&A prose is explicitly excluded when
standard repeated Item 8 headings identify the financial-statement section. Ambiguous
layouts retain the full original body. All original files and numeric extraction remain
archived. An author selects existing IDs; code computes tables and multiples. Missing
inputs remain visible gaps; source collection is upstream and no post-draft search occurs.

Review assesses the same eight criteria and five questions. Material factual errors,
misleading basis/periods, false Q&A attribution and consequential omissions block.
Style, repetition, optional detail and layout preferences are advisory. Missing inputs
are not failures when accurately disclosed. One correction may change source selection
when needed to fix a material finding; reviewer section labels do not restrict necessary basis clarifications.
The final check receives the complete candidate, full call, complete cited original
scopes for actual changed claims and blocking findings, and prior review. Unchanged claims retain their original independent review; the final check sees the complete candidate and exact change map. Numerical selections are revalidated against frozen extraction.
A schema failure without an initial review receives full-packet independent checking.

Exact captured table IDs in citation lists resolve deterministically to their source
documents. Fact IDs, selected table IDs, financial values and prose are unchanged.
Raw model outputs and their authenticated receipts remain immutable; separate resolved
outputs and citation-mapping records bind both versions by hash. Review acceptance
binds the resolved review, whose raw output and deterministic mapping remain auditable.
Unknown citations and author schema/selection errors use the existing single correction
allowance. Persistent errors block publication. Transport, receipt, source-integrity and
budget failures remain terminal; this change adds no paid retry or allowance.

The private `run_simple_reports.py` adapter freezes an ordered manifest before testing,
checks clean code and adapter hashes, and selects consecutive untouched qualified packets
from the authorized batch. It persists stage state and verifies exact remote report bytes.
The batch is not a schedule. Automation remains paused during validation. Historical
jobs and costs are unchanged. Genuine autonomy evidence requires consecutive live runs
on a frozen version, without operator edits or extensions; fake tests alone do not prove it.

Fresh-source tests may provide an explicit verified-issuer source profile instead of
an archived packet. `earnings_fresh_sources` uses the existing bounded HTTPS client,
text/PDF extraction and native transcript index. It discovers the latest completed
ordinary quarter from an approved public issuer index, fetches the call and its exact
attached report, prefers an available official PDF, and permits an explicitly approved
provider mirror. It verifies issuer/quarter, financial-statement coverage and indexed
Q&A before passing an immutable source case directly to the finite runner. Retrieval
failures and every source hash remain in the case; source failures terminate before
paid authorship. It creates no global library acceptance or legacy qualification handoff.

The initial adapter supports English calendar-year quarterly PDF reports and the
configured public transcript-provider layout. Unsupported calendars, stale/ambiguous
periods, missing statements or unindexed calls fail explicitly. It observes issuer/period
transcript exclusions. Discovery is scoped to the configured indexes, not a guarantee
that every public disclosure was found. Source matching is deterministic; independent
report review still checks source interpretation. No source-model allowance is added.

`earnings_pdf_tables` retains original page text, units, header rows, sparse numeric
columns and source spans. PDF rows can be selected as reported tables. They do not
become inferred XBRL facts; normalized QoQ/YoY calculations remain unavailable without
qualified normalized inputs. Original tagged extraction and Decimal calculations are
unchanged. PDF text is bound to the original bytes and independently reproducible with
Poppler; positional limitations remain visible.

When the normalized observation inventory is completely empty but source tables are
selected, code records the missing normalization for required accounting metrics.
It preserves existing source-specific gaps and never fills price or annual-EPS valuation
inputs. Raw author outputs remain unchanged; the resolved output and a normalization
receipt record the added parser-gap labels. This does not label the metric undisclosed,
invent a fact, or waive source-table review. Partially tagged packets retain explicit
per-metric selection and gap checks. Compiler errors enumerate missing roles.

A new explicitly scoped development retest may reduce its ceiling by exact prior failed
usage. It cannot increase the fixed ceiling, mutate the failed job, reuse paid outputs,
or reset costs. The private manifest binds prior terminal receipts and the remaining
allowance; the retest still starts with fresh sources and its own one-correction limit.

Empty explicit price and annual-EPS inventories also receive deterministic gap labels;
this never supplies a valuation input or overrides an existing qualified value. PDF
unit/year/date header rows are retained even when authors select only metric rows.
Source-backed narrative FCF arithmetic remains required when reported inputs permit it,
with cash-capex/software/development conventions stated separately from normalization.

Report recognition uses opening identity headings or affirmative legal identity
statements in the accounting notes, with exact original text spans and hashes.
Image-only covers and contents pages need not contain the issuer name. The first
dated report heading in the opening extracted pages binds the period; later body
comparisons cannot substitute for it. Wrapped titles, year-first titles, ordinal
quarters, half-year, nine-month and full-year labels are recognized for calendar-year
events. Explicit heading dates must agree. This is bounded English heading recognition,
not arbitrary-document or OCR support.

A cumulative document can support the corresponding quarter's event, but qualification
records its actual start/end, basis and whether it is a standalone quarter. That basis
is carried into author/review scope notes. Every selected table retains its own period
headers; six-month or nine-month flows must never be relabeled as quarterly flows.
No normalized financial facts or quarter-only values are inferred by recognition.

Event discovery accepts Q1–Q4 calls, H1/H2 calls and the provider's explicit `-tu`
trading-update variant. It cross-checks the issuer-specific URL with the index label
and the downloaded call heading. H1/H2 labels and event durations remain explicit;
an H2 call does not establish second-half-only accounting figures. Future periods,
media/post-call/AGM variants, conflicting labels and ambiguous latest events do not
silently displace an eligible event. Retrieval exclusions apply to native half-year
labels and their equivalent quarter ends.

The selected event supplies its own attached quarterly/annual report. A trading
update may instead supply an earnings release, bound to the exact attachment ID
and document type. This route retains the `release` source kind and a frozen
`limited_trading_update` qualification; it is not a filed-statement waiver for
ordinary earnings calls. The release must have explicit issuer/period evidence
and substantive financial disclosure. Missing financial-statement coverage is
carried into the author/review context, with unavailable figures left as gaps.
There is no post-draft search, old-period substitution or additional model stage.

Repeated valid selections of the same source table are combined before compilation:
the union of selected original rows is rendered once in source order, under the
first requested section. Unknown tables, rows or sections still fail validation.
Raw model output is immutable; a separate selection receipt records the original
selections and exact union. This prevents a duplicate presentation choice from
consuming a factual correction or causing another valid table to be dropped.
PDF headers such as `(in € millions)` retain their original units and comparative
years even when the author selects only metric rows.

Scheduled execution requires explicit user resumption and a private scheduling adapter.
That adapter freezes a main-branch code pin and source profile, holds a global execution
lock, and processes one remaining company per invocation through this same runner.
It must check the active schedule, preserve terminal outcomes and budgets, and never
replay historical jobs. Source-profile ownership setup occurs before freezing; report
collection and qualification still occur inside Sources. The batch summary records
the manifest's scheduling mode; omitted mode remains PAUSED for existing validation.

Issuer recognition also accepts the named subject of a standard independent audit
or review report, and labeled registration identities under audit/corporate-information
headings. Bounded names, legal forms, paragraph/page context and original evidence
spans distinguish these from incidental company mentions. This uses no issuer-specific
name or identifier allowlist and does not relax reporting-period checks.

Issuer identity also accepts opening report headers with printed page counters and
line-anchored statutory publication statements naming the issuer. These rules retain
exact original evidence spans and bounded legal names. They do not accept arbitrary
body mentions, ticker substrings or change the reporting-period requirements.

Source qualification now combines the verified issuer index, matched call/event and
exact attached report with document identity and period evidence. Recognized evidence
uses the deterministic path. Unrecognized layouts are ambiguous rather than automatic
identity mismatches. Exactly one tool-free Sol medium source-verification call may
resolve ambiguity using bounded original excerpts and exact quotes. Its 220,000-token
ceiling (including the transport's registered output reservation) is part of the existing
1.2-million-token company budget, not an additional allowance. Realized usage, source
hashes, raw response and decision are persisted before authoring. Contradictory dates,
broken provenance, missing financial coverage, unverifiable quotations, rejection and
uncertainty still terminate. No source searching, financial inference or paid retry is
introduced. Independent report review remains required.

A frozen validation profile may set `source_verification: "always"` to exercise the
model path even for recognized documents. Normal profiles omit it and invoke the
model only for ambiguity. The same citation, contradiction and budget checks apply.
