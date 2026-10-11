# Editorial acceptance in the combined review

New requests can explicitly select `batched-editorial-review-v3` by freezing
with `--batch-review --mechanical-preflight --editorial-review`. This binds the
existing private writing standard and its hash; no extra editorial model role
or review call is added. Earlier versions retain their original contracts.

The reviewer checks factual correctness and the bound guide together. Guide
violations block acceptance. Personal preferences outside the guide do not.
Word counts guide compression rather than forcing deletion of material evidence.
For every pending unit, the reviewer returns `review_kind` (`none`, `editorial`,
`factual`, or `mixed`) and `editorial_repairs`. Each repair identifies a field
path within the unit, exact unique text, a concrete replacement (empty for a
cut), and a specific guide violation. A pass cannot contain unresolved repairs.
Factual and mixed findings still require exact source passage IDs. Editorial-only
cuts use validated text locations and do not invent source evidence.

The existing correction author receives all findings in one batch. Numbers,
quotes, attribution, conditions, accounting bases and citations must survive.
Deterministic schema checks validate repair addresses; the independent reviewer
assesses meaning. Repairs cannot address source or signal classification bindings.
This is not a regex rewrite engine.

Unchanged accepted units retain their receipts and are not reopened for editorial
preferences. Changed units and their dependencies require review; old acceptance
never certifies edited bytes. The original two correction rounds and recorded
usage remain intact. Existing accepted reports require an explicitly bound new
edition for editorial work; do not rewrite their artifacts or replay old receipts
under this policy.
