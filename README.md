# Equities Research

Codex cloud workflow preparation for scheduled earnings research, using Codex
subscription authentication. This public repository holds code and instructions.
**Watchlists, documents, research reports, and credentials stay in separate private storage.**

New reports use the **simple runner** (`research.earnings_simple_runner`):

**Sources → financial tables → analysis → independent review → publication**

Collection, extraction and financial calculations run in code. One author writes
from the frozen evidence; one independent reviewer checks the draft. A material
finding permits one correction and one final check. Every company ends published
or failed, with a fixed cumulative token ceiling and exact private persistence.
Failures do not trigger handoffs, extra allowances or silent paid retries.

## Start here

- [Simple runner and source qualification](docs/simple-runner.md) — default for new reports
- [Financial extraction and calculations](docs/deterministic-financial-analysis.md)
- [Cloud environment setup](docs/cloud-setup.md)
- [Evidence rubric](roles/rubric.md)
- [Investment methodology](.agents/skills/analyze-stock/SKILL.md)

The private runtime owns scheduling, source profiles and frozen code pins. A schedule
requires explicit user authorization; installing this repository does not enable one.
Older sequential, handoff and recovery controllers remain only for historical pinned
runs. Their task prompts and [operations notes](docs/operations.md) are not instructions
for new reports.

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
