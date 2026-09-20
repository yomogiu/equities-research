# Evidence workspace and durable handoffs

This original standard-library implementation adopts Prime Agent's patterns of
programmatic evidence access, focused agent contexts, and durable artifacts. It does
not fork/install Prime Agent or invoke models. Import/index operations are preparation
only. Research remains gated by private `config.json.enabled`; no schedule is enabled.

## Private layout

- `library/catalog.json` and `snapshots/<id>.json`: unified metadata and immutable versions.
- `library/issuers/<id>.json`: per-issuer inventories, including empty issuers.
- `library/review-queue.json`: source, period, completeness and language qualification.
- `library/search.sqlite3`: ignored, rebuildable full-text index.
- `library/qualifications/<id>.json`: explicit evidence-backed review decisions.
- `library/packets/<id>.json`: immutable evidence references, not copied full text.
- `handoffs/policies/<hash>.json`: rubric and full methodology bundle.
- `handoffs/plans/<id>.json`: task dependencies, revisions and fenced leases.
- `handoffs/events/<id>.json`: immutable state-transition snapshots.
- `handoffs/artifacts/<id>.json`: immutable agent results.

Raw bytes/text stay in their existing paths, including gzip objects. Reads verify
SHA-256 after decompression. Catalog IDs combine issuer ID and text hash; alternate
URLs, collector IDs and metadata are retained. Actual report URLs take precedence
over discovery pages. SEC aliases normalize to one identity; ambiguous tickers fail.

Source access does not verify fiscal period, full transcript, listing identity or
research authority. Legacy-only pages stay unqualified. Dates/fiscal fields remain
candidates; unflagged documents are not silently declared English.

## Import, search and bounded reading

Run from the public checkout with private paths (these paths are placeholders):

```sh
python3 -m research.workspace --root /private/data import --audit reports/audit/results.json --languages reports/audit/language-review.json
python3 -m research.workspace --root /private/data index
python3 -m research.workspace --root /private/data list --issuer FAKE
python3 -m research.workspace --root /private/data search 'revenue AND guidance' --issuer 'sec:0000000123'
python3 -m research.workspace --root /private/data search '營業收入' --literal
python3 -m research.workspace --root /private/data read DOCUMENT_ID --start 0 --end 6000
```

SQLite FTS5 supports word search. Literal Unicode substring search handles languages
without space-separated words. Results include document IDs and character offsets;
overlapping sections preserve surrounding context. Read source spans before citing;
snippets are discovery aids. Reads are capped at20,000 characters. Search refuses a
stale catalog fingerprint. Rebuild the ignored database locally; no embeddings needed.

## Qualification and packets

Qualification JSON requires `document_id`, `text_sha256`, `kind`, `period`,
`completeness`, `publisher_type`, `language`, `english_coverage`, `source_accepted`,
`reviewer_session`, `rationale`, and `source_spans`. Each span has `start`, `end`, and
exact original `text`. Source acceptance must be true; English coverage is full,
partial or none. Explicit periods use FY2026-Q2, FY2026-H1 or FY2025 notation.

```sh
python3 -m research.workspace --root /private/data qualify --input staging/qualification.json
python3 -m research.workspace --root /private/data packet --input staging/packet-selection.json
```

Packet selection specifies `issuer_id`, `period`, `qualification_ids`, and optional
`missing`: document-kind keys with status and reason. Missing kinds default to pending.
Earlier-year annual background is allowed; current-year annual reports cannot leak
into earlier quarters. Scope remains a limited event update. Publication cutoffs for
point-in-time research still need explicit review. Inventories are not period packets.

Packet hashes cover qualifications, sources, periods, language and availability.
Changes create successors. Unknown issuer identities block plans. `materialize
PACKET_ID --output new/private-packet.json` produces the existing research.cli packet
format. Catalog IDs and compatible source-URL-plus-text evidence IDs are both retained.

## Agent execution and review

`plan PACKET_ID` prepares tasks without invoking agents. Translation and independent
translation review precede analysis when needed. Extractor and commentator receive
the same originals in distinct sessions, without each other's first drafts. A fresh
reviewer receives both outputs and original sources. At most two targeted repair
rounds are allowed, including translation repair. Exhaustion becomes needs_attention.

The rubric and methodology are snapshotted. The bundle includes the skill, its
Markdown references, role prompts and operations rules. Agent discoveries must become
reviewed code/policy revisions; agents cannot rewrite the framework to force a pass.

```sh
python3 -m research.workspace --root /private/data plan PACKET_ID
python3 -m research.workspace --root /private/data status PLAN_ID
python3 -m research.workspace --root /private/data claim PLAN_ID TASK_ID --worker ACTUAL_SESSION_ID
python3 -m research.workspace --root /private/data complete PLAN_ID TASK_ID --token LEASE_TOKEN --input staging/role-result.json
python3 -m research.workspace --root /private/data interrupt PLAN_ID TASK_ID --token LEASE_TOKEN --reason 'Specific interruption'
python3 -m research.workspace --root /private/data verify PLAN_ID
```

Claims require enabled research, persisted/validated dependencies, independent
sessions and bounded leases. **Claim commits and pushes only its plan and event
before returning dispatch information.** A clean Git index and authorized writeback
are required. A competing clone's non-fast-forward push fails before dispatch. Never
force-push a failed claim; reconcile under one coordinator. File locks are local, not
distributed. Use one coordinator and the same Actions concurrency group for writers.

Claim output separates active inputs, accepted translations and historical repair
context. Workers return JSON instead of editing task state. Leases allow at most three
attempts and four hours each. Expired final attempts become blocked. Cancel expired
workers before reassigning. Fencing rejects stale results but does not guarantee
exactly-once model execution or external side effects.

`complete` saves validated local output. Commit/push artifacts, events and plan updates
before dispatching dependents. `verify` revalidates evidence, qualifications, policies,
role artifacts and exact bytes at remote main. Acceptance requires final review and
verified persistence. Preserve its receipt. Separate session IDs support, but cannot
prove, independent context; the coordinator is responsible for actual isolation.

## Translation

Prefer equivalent issuer English or embedded English. Qualification must inspect
coverage; a language screen alone cannot waive translation. Output requires document
ID, source SHA, source/target languages, translator version, and segments with offsets,
exact original text, English text and label `translation`. `untranslated_ranges`
account for all remaining characters. Selected translation is not full translation.

The translation reviewer checks meaning, numbers/units/periods, attribution and
coverage. Extraction quotes remain verbatim original language. Label English renderings
and link to translation artifact/segment; semantic review checks fidelity. Never
replace originals or present machine translation as verbatim English management quotes.

Software supports judgment; it does not establish translation accuracy, correct fiscal
assignment or sound investment reasoning. Model invocation, unattended Codex scheduling
and a resident agent daemon are not implemented here.
