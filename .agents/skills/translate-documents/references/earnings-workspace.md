# Equities research handoff adapter

Use only for an existing equities-research private workspace. Find pinned code via
its `workflow.json` / `.workflow` setup. Read its `docs/workspace.md`,
`roles/translator.md`, `roles/translation-reviewer.md` and actual translation validator.
Do not assume one machine's paths.

An independently authorized translation need not change research configuration.
Actual `claim`/`complete` operations follow workspace gates and persistence rules.
Do not change `enabled`, guess qualifications, or start the backlog simply to use
this skill. Explicit later user instructions can authorize separate one-off translation;
keep it distinct from an accepted handoff until integrated correctly.

Prefer qualified official English coverage; report new counterparts for source/period
qualification rather than silently replacing assigned evidence.

1. Read the packet and source. Use the packet's `document_id` (evidence ID, potentially
   different from the catalog ID) and `text_sha256`. Prepare identical extracted
   text with `--document-id EVIDENCE_ID`.
2. Translate selected material for the assigned scope and retain omitted ranges.
   Validate exact source/coverage with the helper first.
3. Export the completed English artifact:

   ```sh
   python3 scripts/translation_artifact.py export-workspace --source source.txt --input translation.json --output role-result.json
   ```

   This maps `translated_text` to `english_text`, retaining provenance, `start`,
   `end`, `original_text`, `label: translation`, and `untranslated_ranges`.
   Current workspace supports English target only. Export does not dispatch or accept.
4. Validate against the actual packet using the workspace validator. The coordinator
   completes the active task/lease, persists privately and dispatches an independent
   reviewer. Use its role contract: `verdict`, `findings`, four `criteria`,
   `report_markdown`, and the workspace's verdict/target vocabulary.
5. Downstream authors use renderings only after accepted independent translation review.
   Keep original-language quotes and links to translation artifact/segment.

Sources, translations, results and receipts belong in private data storage, never
public workflow code. Local valid JSON does not prove remote persistence or acceptance.
