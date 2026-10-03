# Reviewed business signals

The signal strip surfaces up to four material developments. Matching badges appear
beside the relevant findings. Cards link to those findings and expose period,
comparison, rationale and source evidence in an expandable detail. Small coloured
accents accompany explicit text labels; meaning never depends on colour alone.
The layout uses four columns on wide screens, two on tablets and one on phones.

Direction and evidence basis are separate:

| Direction | Business meaning |
| --- | --- |
| Improving · green | Supported improvement or completed milestone |
| Deteriorating · red | Supported deterioration or quantified constraint |
| Conditional · amber | Opportunity depends on specified events |
| Unresolved · grey | Material question remains unanswered |

Evidence labels are **Reported result**, **Management guidance** and **Analyst
inference**. Reported results can include management-reported completed milestones;
that label does not assert an independent audit. A guidance-versus-actual comparison
uses Management guidance. An unanswered question is not automatically a red business
signal. Do not force all four directions into every report or infer a company rating.

The analyst proposes structured signals tied to the exact report digest, finding IDs,
periods, comparisons and original passage IDs. A separate fresh reviewer assesses
source support, scope/direction, evidence basis, period/comparison, selection and
writing. Every signal must pass before the annotated edition is published. A blocked
annotation stage leaves the original accepted report available. The source report,
financial records, retrieval artifacts and prose are never rewritten.

Use `--signals` with the passage pipeline's `freeze` command to enable the stage after
report acceptance, including acceptance through deterministic corrections. `run` and
`verify` expose annotation status separately from the original report's status.
The flag does not enable production schedules or change workflow pins.

For an existing accepted report, use a new directory in private storage:

```sh
python3 -m research.earnings_signals init "$ACCEPTED_REPORT_RUN" "$SIGNAL_EDITION"
python3 -m research.earnings_signals run "$SIGNAL_EDITION"
python3 -m research.earnings_signals verify "$SIGNAL_EDITION"
```

There are two model calls at most: a bounded annotation proposal and independent
review, both Sol 6.1 Medium. Review sees the complete original source text. The stage
uses a 400,000-token between-call gate and a 750,000-character prompt preflight limit.
In-flight calls can exceed the token gate. It does not launch repeated correction
loops; blocked or invalid annotations require a separately scoped revision. Completed
jobs are replayed and verified. An uncertain launch is never duplicated.
