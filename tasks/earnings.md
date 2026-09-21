# Earnings collection and analysis — every two hours

Read AGENTS.md, docs/operations.md, the relevant role prompts, and the rubric.
Load the private queue and resumable stage receipts. Select due, unfinished events
within the approved run capacity. No queue or persistence connection means blocked,
not an empty earnings calendar. Retrieve the current accepted packet before collecting.

1. **Collect.** Use roles/collector.md. Read docs/workspace.md and the unified private library/catalog.json,
   library/review-queue.json, issuer inventory and source gaps first. Use workspace
   search/read for bounded source spans. Older collection indexes are importer inputs.
   Reuse deterministic downloads; search only to resolve a specific gap. Confirm
   period and completeness before promoting manifests to an accepted packet.
   Assemble the release, full transcript,
   applicable quarterly/annual filing, annual background, and material presentation.
   Record each availability state separately. Preserve full lawful source text and
   precise locators. Missing transcripts are explicit gaps, not fabricated summaries.
   Save explicit source/period/language qualifications and build a versioned workspace
   packet. Route selected translation and independent translation review when needed.
   Keep originals and precise source spans. Research requires config.json.enabled.
   Run workspace freshness for the packet before dispatch. Preserve retrieved_at,
   checked_at and source hashes; follow docs/workspace.md's packet freshness rule.
   Revalidate stale/unknown evidence and create a successor packet rather than
   editing timestamps. Fresh source access does not establish the latest fiscal period.
   Validate and fingerprint the packet with the CLI. If its content and relevant
   metadata have not changed, record the check and skip repeat analysis.
2. **Analyze independently.** Give an extractor and a commentator the same original
   packet, fiscal-period identity, framework, and prior accepted public evidence.
   Use roles/extractor.md and roles/commentator.md. Each writes a separate private
   artifact. Do not give either the other's draft before the independent first pass.
3. **Cross-review.** Give a fresh reviewer the original packet and both artifacts;
   apply roles/reviewer.md and roles/rubric.md. Check sourcing, material omissions,
   numerical context, causal claims, counterevidence, and management Q&A. Agreement
   is not proof. Exact-match checks supplement this judgment; they do not replace it.
4. **Repair.** Send material findings and drafts to the relevant author. Re-review
   against the same original packet after repair, up to two revision rounds. Missing
   public documents do not require routine user questions. Unresolved material
   findings produce needs_attention, never pass. Record unavailable independent
   review explicitly when separate contexts cannot be created.
5. **Deliver.** Validate all artifacts and render Markdown with `research.cli report`.
   Save a new private report version linked to its packet, reviews, and predecessor.
   Preserve provisional reports when late transcripts or filings trigger successors.
   Save stage receipts and verify the durable write before claiming completion.

Frequent collection: day before earnings through day seven. Afterward, check delayed
documents daily through day 60, extending only for a specific documented need. New
source evidence can reopen analysis. Identical blocked packets cannot silently become
accepted. Notify only for meaningful new research, a material change, or an actionable
failure. No external email, Slack, or portfolio actions.

Use workspace plans and fenced claims for role assignment. Claims must be persisted
before dispatch. Use active_inputs rather than superseded drafts. Commit and push
completed artifacts before dependent work, then run workspace verify before acceptance.
