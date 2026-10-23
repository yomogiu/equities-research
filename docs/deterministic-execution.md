# Deterministic preparation and compact review

New file-pipeline requests with `--financial-analysis` automatically freeze
`deterministic-preparation-compact-review-v1`. New deterministic six-section
requests can also select it with `--execution-profile`. Existing protocols and
prepared continuations retain their frozen behavior; this is not a migration or
permission to rerun a completed report.

The profile reduces model work in three places:

1. **Source navigation in code.** When exact Q&A membership can be replayed from
   the source index, prepare passage addresses and up to four ranked filing
   excerpts without a retrieval model call. These are navigation aids, not
   semantic summaries, relevance judgments, or proof of source inspection.
   Ambiguous attribution or incomplete boundaries fall back to the existing
   retrieval role. Changed source bindings fail closed. The author and reviewer
   still inspect the complete original call and required support. The author may
   choose any inspected original passage rather than the navigation examples.
2. **Lossless compact packets.** Print the full candidate report once and replace
   duplicate long unit strings with exact character-range references. The view
   round-trips to the original handoff and has a digest; original artifacts stay
   available through the evidence API. Group handoff, call, and support pages
   into responses of at most 60,000 characters, retaining the original typed
   retrieval events, source hashes, financial inventory and delivery checks.
   The reviewer must also inspect a filing challenge packet, which selects
   additional eligible excerpts outside required support when available and
   explicitly identifies an exhausted-inventory fallback.
3. **Exact proposed edits in code.** Apply typed reviewer proposals against the
   authenticated original units when every directly revised unit has applicable
   edits. Conflicting, unsupported, or invalid candidates fall back to author
   correction. Never infer changes from finding prose. Extraction artifact
   changes still need the author path. Successful automatic edits consume a
   correction round, record a zero-provider-call derivation, and require fresh
   full independent review. There are still at most two correction rounds.

Before launching a role, `budget-preflights/<job>.json` records its planned
evidence packets, repeated context estimate, intermediate-output allowance and
full final-output reserve. The estimate includes cached input on every model
turn. It uses disclosed planning assumptions (three UTF-8 bytes per token,
4,096 tokens per intermediate output and envelope) and is **not** a tokenizer,
billing estimate, or guaranteed ceiling. A role whose forecast exceeds the
remaining lifecycle budget stops before a provider call. The runtime still
enforces actual cumulative usage and reserves the registered full output limit
before every model turn; the forecast cannot weaken that guard or raise a cap.

`retrieval-compiled.json`, `deterministic-corrections/`, `budget-preflights/`, and
the existing coverage/decision receipts permit offline replay. No synthetic
model session or acceptance receipt is generated for code-only work. Performance
changes can be measured without a live model run by comparing exact packet byte
counts, planned tool turns, and eligible deterministic stages against a frozen
private candidate. Actual token savings require a separately authorized live run.
