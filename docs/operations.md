# Handoffs and acceptance

Use private storage with a stable namespace, for example:

```text
watchlist.json
calendar/<as-of>/calendar.json + calendar.md
queue/<issuer-period>.json
packets/<issuer-period>/<packet-id>.json
runs/<run-id>/<role>/result.json
reports/<issuer-period>/<packet-id>/<revision>/report.json + report.md
receipts/<run-id>.json
```

These are logical paths in a private service, not files to add to this repository.
Each cloud task must restore the relevant inputs and write back its results through
that service. Restoring a local copy alone does not establish durable persistence.
The CLI accepts private paths and refuses to render a report inside this checkout.

Record run ID, task/session identity when exposed, stage, source cutoff, artifact
locations/hashes, review status, superseded report, and next retry time. Use the
storage service's conditional writes or a single-writer queue to prevent two tasks
from publishing competing accepted versions. The workspace implements local file locks, fenced leases and fast-forward Git claim
publication before dispatch. Use one coordinator; this is not a general distributed
queue or exactly-once execution engine. See [workspace.md](workspace.md).

Acceptance needs all three: an agent's substantive rubric review, exact-source/schema
validation, and verified private persistence. A stopped task, a successful CLI exit,
or a polished report is not sufficient. Codex has no use of Anthropic's outcome API
here; the Codex coordinator follows the rubric and explicit repair procedure.

Every material quote keeps its document ID, verbatim text, speaker, and locator.
Every metric keeps its original passage, period, currency, unit/scale, and basis.
Interpretations distinguish company claims, facts, and inference, with counterevidence
and uncertainty. Review criteria assess evidence quality, not optimism or agreement.

Maintain a finite run capacity and bounded revisions. Codex subscription limits are
shared with other use. On interruption, preserve receipts and resume incomplete work;
do not recreate already accepted packets or assume an unlimited unattended budget.

Live research starts only after a reviewed watchlist, public-source network access,
private storage, and an actual cloud task invocation have been verified. The fake
example is for tests only and must never be queried as a real company.


## Batched report repair

The initial independent audit lists every material defect in one correction batch,
including repeated claims across financial context, retrieval summaries and prose.
Corrections are hash-bound field patches; financial observations and selected
quotations remain fixed. Claim groups enumerate every matching occurrence and require
an explicit repair or a reason to retain it. This check does not infer semantic
similarity; the author and reviewer must choose the complete aliases and affected fields.

Subsequent reviews receive the complete rendered report, exact field changes, pending
findings and original passages cited by the complete report, with source hashes and
character offsets. Supplying all direct report citations up front avoids a second
lookup for unchanged claims. Review prompts are bounded at 350,000 characters.
Repeated source spans share one source block. The original full-source audit stays
in the immutable history. A reviewer can request exact source IDs once; that evidence
expansion consumes measured tokens but no correction round. Insufficient evidence,
failed provenance, an uncertain launch or an exhausted budget cannot become acceptance.

The reviewer approves the exact staged candidate. Python applies the approved patch
and renders the result; no author rewrites follow acceptance. Optional
`format.layout` (`compact-financial-v1`) folds compatible ratio rows into monetary
rows and moves secondary tables into expandable detail while retaining every original
value and citation. Independent signal review and private persistence remain required.
Historical pinned runs replay with their original code. Explicit v2 remediation
editions may descend from a conclusively stopped correction or remediation run; they
preserve the entire prior history and cannot retry an unchanged candidate or fork a
second descendant from the same source.
