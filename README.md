# Equities Research

Codex cloud workflow preparation for scheduled earnings research, using Codex
subscription authentication. This public repository holds code and instructions.
**Watchlists, documents, research reports, and credentials stay in separate private storage.**

The workflow is agent-led:

1. A calendar agent discovers and reconciles issuer earnings dates.
2. A collector retrieves releases, transcripts, quarterly/annual filings, and background.
3. Independent agents extract exact quotes/data and interpret the investment evidence.
4. A reviewer challenges both against original sources and a rubric.
5. Authors repair material findings, with at most two cross-review revision rounds.
6. Reviewed or explicitly incomplete reports are versioned in private storage.

The calendar prompt targets 07:00 Eastern Time daily; collection targets two-hour
opportunities during earnings windows, with daily follow-ups for delayed filings.
**These are prepared task prompts, not active schedules.** Creating this repository
does not create a scheduler, persistent research storage, or a running agent service.

## Start here

- [Cloud environment setup](docs/cloud-setup.md)
- [Calendar task](tasks/calendar.md)
- [Collection, analysis, and cross-review task](tasks/earnings.md)
- [Handoff and acceptance rules](docs/operations.md)
- [Evidence rubric](roles/rubric.md)
- [Investment methodology](.agents/skills/analyze-stock/SKILL.md)

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

The initial repository provides role/task prompts, the neutral analytical framework,
source-contract checks, a private-output renderer, and offline tests. It has no model
API backend and no research-bearing GitHub Actions workflow. Cloud environment
connection, private storage, independent-agent availability, live source retrieval,
and hosted scheduling must be verified before unattended production runs.
