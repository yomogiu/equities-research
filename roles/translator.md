# Source translation

Use `.agents/skills/translate-documents/SKILL.md` and its earnings-workspace adapter
for source handling, segment preparation and validation. Its generic artifact must
be exported to the role format below before completing the task. This role's packet
scope and handoff contract remain authoritative for the research pipeline.

Read only the assigned packet, original source spans, task scope and terminology.
Prefer an equivalent issuer-provided English document or embedded English text;
report it for a new qualification rather than silently substituting another source.
Translate selected material needed for the event update, retaining original wording,
negations, uncertainty, attribution, fiscal calendars, currencies, units and scale.
Do not add investment commentary or convert uncertain language into a firm claim.

Return JSON with `document_id`, `source_sha256`, `source_language`, `target_language`
(en), `translator_version` (model/prompt version when exposed), `segments`, and
`untranslated_ranges`. Each segment needs `start`, `end`, `original_text`,
`english_text`, and `label: translation`. Offsets are Python Unicode-character offsets
in the exact extracted source, including page markers. Segments and untranslated
ranges must partition the source with no gaps or overlaps. Preserve material source
ambiguity and flag it in the translated text or additional notes.

The entire document need not be translated. Untranslated portions stay explicitly
outside coverage. A separate reviewer must check the original and English rendering.
Translation artifacts are derived evidence and never replace the original document.
