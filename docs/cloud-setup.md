# Codex cloud setup

Use Codex's existing ChatGPT sign-in and subscription. An Anthropic API key or a
separate OpenAI API key is not required to run a normal Codex cloud task.
[Authentication](https://learn.chatgpt.com/docs/auth).

## Repository environment

In [Codex environments](https://chatgpt.com/codex/settings/environments):

1. Ensure the Codex GitHub connection includes `yomogiu/equities-research`.
2. Create an environment for this repository and select `main` when starting tasks.
3. Keep the universal image with Python 3.11 or newer.
4. Set the setup script to `bash scripts/setup.sh`. It runs offline fixture tests
   and checks the CLI without reading a watchlist or invoking a model.
5. Before live research, configure approved issuer/regulator/source domains for
   agent internet access, preferably GET/HEAD/OPTIONS. Research cannot fetch current
   sources while internet access is off. Domain redirects/CDNs may need explicit entries.
6. Connect a private storage destination and supply the reviewed watchlist through
   private task context or that service. Never commit these inputs to this public repo.

Codex checks out the repository in its cloud container and uses AGENTS.md. Setup
secrets are removed before the agent phase; a setup-only secret does not establish
an authenticated runtime storage connector. Container caching is not durable shared
research storage. [Environment documentation](https://learn.chatgpt.com/docs/environments/cloud-environment),
[network settings](https://learn.chatgpt.com/docs/cloud/internet-access).

## First cloud task: code-only smoke check

For a separate private GitHub data repository, create a **second Codex environment**
whose checked-out repository is that private workspace. Its setup can fetch a pinned
commit of this public code into an ignored `.workflow/` directory and run
`.workflow/scripts/setup.sh`. Read/write research artifacts outside that public code
directory, inside the private checkout. This avoids needing to copy a private watchlist
into the public code repository. Verify authenticated private write-back separately;
a task's local file changes do not by themselves establish cross-task persistence.

Use this prompt before any real issuer research:

> Read AGENTS.md. Run bash scripts/setup.sh. Validate examples/watchlist.fake.json.
> Confirm the checks pass without credentials, network research, or real portfolio
> inputs. Describe the configured environment and report any unavailable capabilities.
> Do not create or enable schedules, research real issuers, or publish reports.

Cloud checkouts can use a local branch named `work`. Validate the checked-out commit
against the selected repository revision; do not require a local branch named `main`
or switch branches merely to run the tests.

Then test one approved real event privately. Verify actual source retrieval, separate
analysis contexts, exact-source validation, rubric-driven revision, and a private
write/read-back. A code-only smoke check does not validate those research capabilities.

## Scheduling

`tasks/calendar.md` and `tasks/earnings.md` are durable prompts. Reuse them when the
selected hosted scheduling surface is available, and give both stages access to the
same private queue/store. A GitHub repository alone does not schedule Codex tasks.
Do not add a GitHub Actions job that assumes a subscription is an API key or publishes
research as public Actions artifacts. Do not copy Codex account credentials here.

The automation tool exposed in the desktop preparation task creates local schedules;
those require the app and computer running. Web scheduled tasks use cloud-accessible
context and tools and have workspace-dependent availability. Do not claim that a
web research schedule automatically launches this Codex repository environment.
[Scheduled-task documentation](https://learn.chatgpt.com/docs/automations).

Before activation, verify a supported hosted invocation path plus private persistence
and source access. Preserve the user's cloud preference; do not silently substitute
desktop schedules. No schedule is enabled by any file in this repository.
