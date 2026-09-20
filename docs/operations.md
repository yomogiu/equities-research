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
