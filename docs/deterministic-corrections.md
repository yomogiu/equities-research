# Deterministic report corrections

The correction stage preserves prepared financial and retrieval records. A proposal
agent selects exact report edits; an independent reviewer assesses the staged report
and each edit against original sources. Python applies the approved bundle unchanged.
There is no final author rewrite that can lose an accepted correction.

## Allowed operations

- `copy_context`: replace one exact report span with an existing financial context
  note. Python copies the text and merges its citations. The reviewer must confirm
  the context is correct; successful schema validation alone is not approval.
- `replace_text`: apply the exact reviewer-approved paragraph or heading.
- `set_display`: change a source-supported table label, dimension label, or accounting
  basis note. Numeric cells, periods, units and fact IDs remain fixed.
- `retain_quotes`: remove redundant quotations while preserving the order and exact
  source selections of those retained. Python still copies quotation text/offsets.

Every operation binds a stable target ID, expected old-value hash, snapshot hash,
original passage IDs and source citations. Context copies also bind the source note's
hash. Unsupported fields, unknown IDs, conflicting targets and stale snapshots fail
closed. A failed bundle changes nothing. Display length errors name the field, limit
and actual length.

## Execution and acceptance

Each round has one fresh proposal session and one fresh independent review session,
both using `gpt-6.1-sol` at `medium`. The reviewer sees complete original source text,
prepared artifacts, before/after rendered report bodies and actual citation anchors.
It assesses every operation, adjudicates every pending finding, and scores the entire
report rubric. Source-backed withdrawal of a mistaken finding is allowed.

Patch approval and report acceptance are separate. Approved changes persist even
when other findings keep the report blocked. Rejected bundles never replace the
committed state; staged candidates remain explicitly drafts. A passing report requires
an approved exact candidate, all criteria passing and every finding resolved. The
only rendering change after acceptance is the status banner; no prose is regenerated.

At most two correction rounds are available across an ordinary run. The default
600,000-token limit is checked between calls; an in-flight call can exceed it. Invalid
patches or malformed reviews stop with precise diagnostics rather than triggering a
whole-artifact rewrite. Upstream factual defects cannot be repaired through this
presentation interface: they require a separately validated preparation update.

## Use

All output directories must be private and outside the public code checkout.

```sh
python3 -m research.earnings_passage_pipeline freeze "$CASE" "$RUN" "$WRITING" --deterministic-corrections
python3 -m research.earnings_passage_pipeline run "$RUN"
python3 -m research.earnings_passage_pipeline verify "$RUN"
```

The opt-in flag stops ordinary author revisions after the first substantive review
and creates a sibling `-corrections` continuation for a complete blocked report.
Incomplete source preparation does not enter this stage. The older `--repair-loop`
strategy remains available for existing experiments; the flags are mutually exclusive.
No production workflow pin or schedule is changed by this feature.

To test corrections on an existing frozen report or repair run:

```sh
python3 -m research.earnings_corrections init "$SEED" "$NEW_PRIVATE_OUTPUT"
python3 -m research.earnings_corrections run "$NEW_PRIVATE_OUTPUT"
python3 -m research.earnings_corrections verify "$NEW_PRIVATE_OUTPUT"
```

`advance` executes at most one model call. Resume reuses verified completed receipts;
an interrupted launch without a verified output returns `launch_uncertain` and never
starts a duplicate. Source/code hashes and every request, proposal, decision, candidate
and final report are checked during replay. Earlier experiments are never edited.
A separately authorized experiment can use `init --new-experiment` to allocate a new
bounded budget; this is recorded explicitly and is never enabled by normal pipeline
continuation.

Unit tests establish structural guarantees, not model judgment. Live experiment
receipts and real-company reports belong only in private storage.
