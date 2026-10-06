# Complete deterministic correction batches

Corrections stage an atomic candidate from an immutable report snapshot. An
independent reviewer assesses that candidate and each logical operation before
application. Financial observations and selected source quotations stay unchanged.

The addressable registry supports exact citation-list replacement, source-backed
table and row labels, and complete Q&A coverage entries. `replace_citations` can
remove erroneous support. When editing the same prose, use `citation_mode:
preserve` so the prose edit does not add those citations back. `replace_exchange`
groups the entry's prose and, where present, source-membership fields under one
operation; the review context expands its individual changes and retains their
parent operation ID. Exchange identity stays fixed.

The former 24-operation ceiling is replaced by the finite target registry,
conflicting-write checks, a 262,144-byte plan limit and a 128,000-character total
replacement limit. These limits permit complete multi-entry repairs while keeping
the candidate bounded. They do not increase correction rounds or token budgets.

New passage-pipeline freezes include a source-bound Q&A membership sidecar.
Retrieval selects original passage IDs for questions and answers; code checks
their membership against exact indexed turns and explicit continuation links.
Unresolved substantive attribution blocks analysis. These checks establish source
membership, not the truth or quality of a paraphrase. The independent reviewer
still evaluates meaning, omissions and management's response.

Correction calls and targeted repair reviews use the conservative admission
policy in [earnings-budget-admission.md](earnings-budget-admission.md). Authenticated
completed reviews retain their validated substantive verdict even when measured
usage exceeds the budget; official acceptance remains blocked.

Existing frozen runs retain their code and protocol bindings. Apply new code only
through a new freeze or an explicitly bound continuation preserving prior usage
and rounds. Passing code tests does not accept an existing report or resume a
drained production cohort.
