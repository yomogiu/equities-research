# Saved-proposal review recovery

A new private continuation can reuse a completed, authenticated correction author
proposal when its independent review has not run. Preserve the original code,
protocol, proposal and receipts. Initialize a separate directory with
`--reuse-proposal`; inherited correction rounds and measured tokens remain counted.

For a proposal whose only source-location defect is an exactly empty
`passage_ids` list alongside valid explicit citations, additionally opt in with
`--resolve-cited-passages`. Code derives **all** canonical passages belonging to
those cited scopes. It binds the original output, snapshot, catalog, exact
resolution and effective plan hashes. It never guesses an unknown ID, selects a
preferred sentence, adds a citation, rewrites the original proposal or approves
the edit. Ordinary atomic validation and a fresh independent reviewer remain
required. This option cannot reset an experiment or add new audit findings.

Large review contexts use a lossless shared-string map and columnar metadata.
The complete rendered report remains verbatim. Every original field and source
character must round-trip exactly before the existing context and prompt limits
are checked. A reviewer still receives the source references, offsets, hashes,
canonical Q&A annotations, pending findings and patch provenance. Insufficient
context or a failed review remains a blocked result.

These routes do not authorize production import or enable recurring analysis.
Reviewed signals and later private persistence verification remain separate gates.
