# Finite earnings-report runner

`research.earnings_simple_runner` is a separate execution path. It does not import
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
