# Selected bounded report pipeline

`research.earnings_passage_pipeline` is the selected entry point for new,
user-authorized report runs. Version `luna6-sol-presentation-v4` uses financial
preparation on `gpt-5.6-luna` / `xhigh`, retrieval on `gpt-6-luna` / `max`, and
analysis plus a fresh independent reviewer on `gpt-6.1-sol` / `medium`.

The two preparation sessions run concurrently. Analysis then receives their
artifacts and the complete transcript. A fresh reviewer receives original
sources and the exact candidate report. At most two correction rounds are
permitted. Quotes are selected by passage ID; code copies text, offsets and
hashes. Financial values are rendered from the selected source observations.

## Execute a bounded run

Install Python 3.11+, Node and Prime Agent with the existing Codex subscription
sign-in. Source packets and outputs belong in private storage outside this public
checkout. Keep the code checkout pinned and unchanged for each frozen run.
The writing standard must be supplied explicitly. Case manifests must pass
`earnings_experiment.validate_case`; retain issuer, fiscal-period and source
qualification uncertainty. This runner consumes an existing frozen packet;
it does not collect missing documents or authorize investment activity.

Set `REPORT_CASE`, `REPORT_OUTPUT` and `REPORT_WRITING` to the authorized private
case manifest, a new private run directory and the report writing standard.

```sh
python3 -m research.earnings_mixed_runner --probe --model gpt-6-luna
python3 -m research.earnings_passage_pipeline freeze "$REPORT_CASE" "$REPORT_OUTPUT" "$REPORT_WRITING"
python3 -m research.earnings_passage_pipeline run "$REPORT_OUTPUT"
python3 -m research.earnings_passage_pipeline verify "$REPORT_OUTPUT"
```

The probe checks registration/sign-in without a model call. The runner verifies
exact requested model and effort, distinct role sessions, original evidence,
quote offsets, dependencies, review bindings and completed output receipts.
Never remove a launch receipt to force a retry. A launched but incomplete job
requires inspection and explicit recovery; it is not safe to launch again.

## Acceptance and repair

Only `result.json` with `status: accepted`, confirmed by `verify`, establishes
passing review of the exact artifacts. Report-file existence does not establish
acceptance. `blocked` results retain draft reports and unresolved findings.

- Invalid passage IDs receive a bounded candidate window; code permits edits
  only to failed selections. No suitable window or an explicit worker refusal
  produces a source-selection handoff.
- Wrong fact selection, missing material context and evidence interpretation
  return to the responsible author within the correction budget.
- Renderer findings stop model retries and persist `repair-handoff.json`, bound
  to the protocol, artifacts and review. This queues code work; it does not
  launch a code-fixing agent or waive substantive findings.

Current limitations include financial label/GAAP presentation defects and
interrupted/corrected transcript-turn interpretation. Report synthesis can omit
material facts already present in the preparer output. Independent review remains
required; efficiency measurements do not establish report quality. Fixes need a
new version and a fresh review, while original benchmark runs remain immutable.

This merge selects the bounded report implementation. Connecting it to the
private scheduled coordinator, changing its workflow pin, and enabling recurring
investment analysis are separate deployment steps. No recurring gate or private
configuration is changed by this entry point.

[Financial display and repair details](financial-rendering-experiment.md)
