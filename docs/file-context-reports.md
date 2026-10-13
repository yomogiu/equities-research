# File-based earnings reports

New report policy: `file-backed-markdown-review-v1`. This is a new immutable run
version; never rewrite existing protocols, prompt files or accepted reports.

## Review and edit the steering

The editable assignments are `prompts/earnings/common.md`, `financial.md`,
`retrieval.md`, `analysis.md`, `signal_author.md`, `review.md` and `correction.md`.
The shared writing standard is the explicitly pinned private Markdown file.
Every template and code file is hashed into the run protocol. Future changes
require a new public code pin and newly authorized packet reservation.

All roles receive `prompt.md`, containing Markdown instructions, the writing
standard, inventory counts and a short IPython bootstrap. Sources, complete HTML,
financial records and prior artifacts are not embedded in instruction prompts.
The 24KB instruction ceiling detects accidental source/HTML payload expansion.
Roles return `response.md` with one JSON metadata block. This preserves exact
financial, quotation, signal and acceptance bindings while making the handoffs
readable. The deterministic report body is `report.md`; HTML is generated from
that Markdown only after a full independent review passes.

## Evidence access in Prime's IPython kernel

Each job has its own `contexts/<role>/index.json`, `sources.json`,
`passages.json`, `financial.json`, `transcript-index.json`, complete
`transcript.md`, `artifacts.json`, `metadata.json`, and (when applicable) `report.md`.
The evidence includes the complete original call, including unassigned spans;
source scope and passage IDs and original offsets remain unchanged.

The assignment supplies:

```python
from research.earnings_file_context import Evidence
ctx = Evidence(index_path, retrieval_log_path)
print(ctx.inventory())
print(ctx.search('cash flow'))
print(ctx.scope('D001'))
print(ctx.passage(passage_id, neighbors=1))
print(ctx.file('report.md'))
print(ctx.artifact('units'))
```

Keep loaded objects in kernel memory and print relevant pages. Each page is at
most 6,000 source characters. Follow `next_start` to complete a scope. Search
previews do not count as complete inspection. Every returned API page is logged
with a reproducible result digest. Original hashes, bundle hashes and retrieval
records are checked again before reuse or acceptance.

IPython is a general Python execution tool, not an OS sandbox. The evidence API
is read-only for sources, and the role contract confines work to the assigned
bundle. Existing signed-in authentication stays in Prime's normal AuthStorage;
no credentials are copied into requests or evidence. No extra model, network,
shell, skill, extension or subagent tool is enabled for report roles.

## Gates and budgets

Financial selection, evidence coverage, passage quotation binding, formatting,
source-derived numeric scales, signal directions and dependency identities reuse
the existing deterministic validators. Reviewers must retrieve the complete
Markdown candidate, complete original call, each indexed Q&A exchange and original
evidence behind the artifacts. Partial reads and search previews fail coverage.
Coverage records attest reproducible API retrieval, not whether a model understood
what it read; substantive independent review remains mandatory.

The independent joint reviewer assesses every unit and all eight report criteria
and six signal criteria, including mandatory writing requirements. A failing
criterion requires specific affected units. One correction author repairs a full
batch; a fresh reviewer evaluates the new entire candidate. At most two author
rounds are allowed. No completed receipt transfers to edited bytes. Formatting
and expanded signal-card duplication are avoided by reviewing the same Markdown
that the final renderer consumes; full signal fields remain in JSON metadata.

Each role uses one fresh Prime session and only the installed IPython tool. The
coordinator launches at most one new role per advance. Every assistant/tool turn,
exact model/effort, OAuth receipt, prompt, result, source retrieval and artifact
hash is validated. Tokens are summed across all model turns, including tool-loop
turns and cached tokens, with a bounded lifecycle total (maximum 1.2 million) and
maximum 48 tool calls per job. Before each provider request, the helper reserves
the serialized request byte bound plus the registered model output maximum.
It does not add unsupported API budget fields. An incomplete launch is preserved
and cannot be retried in place. Exceeded or unknown usage never grants acceptance.

## Operations

The private coordinator selects this policy for newly reserved packets. Packet
qualification, source freshness, reviewed transcript/financial mappings, separate
private persistence and later exact remote-byte verification remain required.
Existing queued and completed requests retain their original code pin. Updating
the report default does not enable analysis, resume schedules, authorize new
packets or migrate any old research.

Direct development commands (private or fictional runtime only):

```sh
python3 -m research.earnings_file_pipeline initialize --case CASE.json --output RUN --writing WRITING.md
python3 -m research.earnings_file_pipeline advance RUN
# Only an explicitly authorized runtime may launch a model:
python3 -m research.earnings_file_pipeline advance RUN --execute
python3 -m research.earnings_file_pipeline verify RUN
python3 -m research.earnings_markdown RUN/report.md RUN/copy.html --status accepted
```

Validation uses fictional provider transcripts and a local installed Prime/IPython
kernel smoke test. No live model call is part of the code test suite. A subsequent
explicitly budgeted live pilot is needed to evaluate actual retrieval choices,
provider compatibility and token savings; synthetic checks do not establish those.

## Closed preparation recovery

Financial roles use paged `financial_metrics()` and `financial_facts(query)` to
select original observation IDs. The complete extraction stays available in the
kernel; printing megabytes of repeated support is unnecessary. Selected original
scopes still require full retrieval and audit.

A coordinator may create one new source-bound recovery descendant for a proven
local `role_budget` stop at the first financial role, or a pre-model sidecar hold
with a new independent coverage receipt. Unknown provider failures cannot take
this route. Every completed provider turn and matched tool result is replayed;
original attempts remain immutable. The new protocol binds the recovery manifest,
starts accounting at the inherited measured spend, and retains the original
1.2-million-token company cap and two correction rounds. A failed role gets a
new recorded attempt; its old request is never launched again.
