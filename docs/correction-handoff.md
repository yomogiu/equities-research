# Source-bound correction handoff

Correction authors and validators now share an addressable occurrence inventory.
The inventory includes known financial display rows before an override exists,
individual prose fields, and explicitly allowed citation-list metadata. Numeric
observations and selected quotations remain outside this namespace.

New proposals use claim groups with `required_occurrence_ids` and unchanged
`{occurrence_id, reason}` entries. Code resolves each ID to its exact path and
snapshot value. Legacy `required_paths` groups remain supported only for the same
addressable fields. Whole objects/lists, invented IDs, stale IDs, empty aliases,
and duplicate or unexplained dispositions fail before independent review. Errors
identify the offending reference and, for aggregate paths, available individual
occurrence IDs. Validation never invents a disposition or makes an approval.

The analysis scope field is a bounded text target. Any change still requires exact
before hashes, original-source citations, and independent whole-report review.
The proposer and reviewer receive the same verified exchange-to-turn membership,
including question/answer roles, follow-ups and provisional boundary annotations.
Original words, source hashes and passage offsets remain unchanged.

This is a code-contract repair, not evidence of improved report quality. Existing
frozen runs retain their original code and outcomes. A saved proposal can be reused
only through a separately bound continuation that verifies its original receipt,
retains spent tokens and rounds, and obtains fresh independent acceptance. An
invalid aggregate disposition is not automatically expanded or approved. No
production flag, schedule, model, source or correction budget changes here.
