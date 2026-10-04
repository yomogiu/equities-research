# Connected reviewed report flow

`research.earnings_report_flow` connects qualified private packets to the selected
passage pipeline, deterministic correction continuation and reviewed signal edition.
The private queue supplies explicit packet authorization and owns persistence.

`prepare(root, packet_id, output, writing, authorization)` verifies qualification,
current issuer eligibility, latest packet, original hashes and freshness. It binds
original archived sources and derives iXBRL observations and provisional transcript
boundaries. Ambiguous full-period filings/transcripts, no structured observations,
missing Q&A, translation requirements or unsupported compressed representations
remain preparation blockers. The reviewer receives all boundary uncertainty.

`advance(output, execute=True)` performs at most one new model call. It replays
completed receipts before advancing, retains uncertain-launch protection and
requires both deterministic corrections and reviewed signals in the frozen protocol.
Financial and retrieval preparation are serial in finite coordinator turns; regular
standalone runs retain concurrent preparation. Independent roles and model settings
are unchanged. At most two correction rounds remain available.

Acceptance here is local. The private coordinator must persist all receipts and
source bindings, verify exact bytes on remote main in a later invocation, and then
publish the completion proof used by its dashboard. A blocked signal review must
not count as a completed signal report. Existing frozen experiments remain unchanged.
The library does not enable schedules, authorize packets or upload credentials.
