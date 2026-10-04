# Equities Research

Codex cloud workflow preparation for scheduled earnings research, using Codex
subscription authentication. This public repository holds code and instructions.
**Watchlists, documents, research reports, and credentials stay in separate private storage.**

The workflow is agent-led:

1. Deterministic collectors fetch configured sources; a calendar agent reconciles date gaps.
2. Scripts retrieve releases, transcripts, quarterly/annual filings, and background; agents resolve remaining source gaps.
3. Independent agents extract exact quotes/data and interpret the investment evidence.
4. A reviewer challenges both against original sources and a rubric.
5. Authors repair material findings, with at most two cross-review revision rounds.
6. Reviewed or explicitly incomplete reports are versioned in private storage.

The calendar prompt targets 07:00 Eastern Time on January, April, July and October 1; collection targets two-hour
opportunities during earnings windows, with daily follow-ups for delayed filings.
**These are prepared task prompts, not active schedules.** Creating this repository
does not create a scheduler, persistent research storage, or a running agent service.

## Start here

- [Unified catalog, packets and durable handoffs](docs/workspace.md)
- [Deterministic collection and private cloud execution](docs/deterministic-collection.md)
- [Cloud environment setup](docs/cloud-setup.md)
- [Calendar task](tasks/calendar.md)
- [Collection, analysis, and cross-review task](tasks/earnings.md)
- [Handoff and acceptance rules](docs/operations.md)
- [Evidence rubric](roles/rubric.md)
- [Investment methodology](.agents/skills/analyze-stock/SKILL.md)

## Selected report pipeline

Use `research.earnings_passage_pipeline` for new authorized, bounded report runs.
It runs Prime Agent sessions through the existing Codex subscription:

| Role | Model | Effort |
| --- | --- | --- |
| Financial context | GPT-5.6 Luna | Extra High |
| Retrieval and Q&A coverage | GPT-6 Luna | Max |
| Analysis | GPT-6.1 Sol | Medium |
| Independent review | GPT-6.1 Sol | Medium |

[Run, verify and repair the selected pipeline](docs/report-pipeline.md).
Code copies exact selected passages and renders source-derived financial values.
Use `freeze --repair-loop` to automatically dispatch targeted repairs or source-backed
rebuttals and return them to the reviewer for adjudication. Unresolved findings
keep reports in draft status; accepted reports require a final passing review.
This entry point does not activate the collection scheduler or unattended analysis.
New runs include [independently reviewed business signals](docs/report-signals.md)
after report acceptance by default. Use `freeze --no-signals` to opt out; existing
frozen runs keep their original setting.

## Check the code

Python 3.11+ and its standard library are sufficient. No API key, paid data provider,
Anthropic SDK, Google Cloud account, or model invocation is needed for these checks:

```sh
bash scripts/setup.sh
python3 -m research.cli watchlist --input examples/watchlist.fake.json
```

`research.cli` validates role outputs and normalizes document IDs. Its `report`
command renders a Markdown evidence report from a validated packet, extraction,
commentary, and review. Output paths must be outside the public checkout and must
not overwrite an existing report. Type `python3 -m research.cli --help` for commands.

The validators supplement agent judgment. They cannot establish that a retrieved
document is authoritative, a conclusion is persuasive, or a review was independent;
the coordinator and reviewer must substantiate those properties.

## Deployment status

The repository provides deterministic SEC/IR collectors, conditional caching, a private
analysis queue, role/task prompts, the analytical framework, contract checks, and
offline tests. Private GitHub Actions can run the downloader without any model calls.
Research-bearing workflows and inputs belong in the private data repository.
Unattended Codex analysis and its scheduling remain separate deployment work.

For immutable prepared data and exact reviewer-approved patches, use the opt-in
[deterministic correction stage](docs/deterministic-corrections.md). It copies existing
context into the report, preserves numeric records, and avoids a final agent rewrite.
