# Supplemental regression findings

A private audit can supply omitted issues to a fresh deterministic correction
handoff with `earnings_corrections init SEED OUTPUT --regression-findings FILE`.
This adds pending findings to the authenticated seed snapshot. It preserves all
original findings, report artifacts, remaining rounds, and inherited token use.
It cannot be combined with `--reuse-proposal` or `--new-experiment`.
The supplemental protocol version requires its audit binding on every load.
Inherited rounds and tokens are checked against the authenticated seed; the
token ceiling cannot exceed the seed's ceiling (600,000 for seeds without one).

The private JSON has exactly these fields (the IDs below are fictitious):

```json
{
  "version": 1,
  "case_sha256": "exact frozen case file SHA-256",
  "evidence_sha256": "exact frozen evidence manifest file SHA-256",
  "audit": {"path": "/private/runtime/audit.json", "sha256": "actual audit file SHA-256"},
  "findings": [{
    "target": "analysis",
    "passage": "Fictitious omitted comparison",
    "reason": "Why this comparison could materially affect the report",
    "required_change": "Verify the bounded comparison against original evidence",
    "citations": ["D001"],
    "passage_ids": ["Pfictional"]
  }]
}
```

Supply 1–12 distinct findings; target is `financial`, `retrieval`, `analysis`, or
`formatter`. Each text field is nonempty and at most 4,000 characters. Citation
and passage lists are nonempty, unique, contain at most 64 IDs, and must refer to
the exact frozen bundle. Keep supplemental and audit files in private storage.
Both files are hash-bound; later loads replay the additive merge against the
authenticated seed to detect changed or missing findings. Validation happens
before output creation. Existing protocols without supplemental input still work.

The audit remains fallible reviewer input. Its hash establishes provenance, not
independent acceptance or factual correctness. Every pending finding still needs
source-backed resolution by the independent correction reviewer; no audit alone
approves an edit or a report. Formatter findings do not expand editable targets.
