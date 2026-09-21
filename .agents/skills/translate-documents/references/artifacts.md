# Translation artifacts and deterministic helper

Use Python 3.11+ and the helper relative to this skill:

```sh
python3 scripts/translation_artifact.py prepare --source source.txt --source-language ja --target-language en --output draft.json
python3 scripts/translation_artifact.py validate --source source.txt --input translation.json
python3 scripts/translation_artifact.py render --source source.txt --input translation.json --output translation.md
```

Replace paths with actual private source/output paths. Commands never call a model,
fetch a URL, or overwrite an output. Source must be frozen UTF-8 text, optionally
`.gz`. Hash decompressed UTF-8 bytes; preserve CRLF and Unicode normalization exactly.
Extract binary PDF/DOCX first and link the extraction to the original file/hash.

`prepare` covers the entire extracted text in chunks of at most 6,000 Unicode
characters, preferring paragraph/line boundaries. Adjust boundaries when tables need
their headers/rows kept together, preserving exact offsets. For selected passages,
pass `--ranges selection.json`: `[{"start": 0, "end": 120}]`. Remaining intervals
become `untranslated_ranges`. Use `--document-id` for an existing downstream evidence ID.

Draft structure:

```json
{
  "schema_version": 1,
  "document_id": "source-hash-or-existing-evidence-id",
  "source_sha256": "sha256-of-exact-extracted-UTF8",
  "source_language": "ja",
  "target_language": "en",
  "scope": "full",
  "translator_version": "",
  "glossary": [],
  "notes": [],
  "segments": [
    {"start": 0, "end": 120, "original_text": "exact source span", "translated_text": "", "label": "translation"}
  ],
  "untranslated_ranges": []
}
```

Fill `translated_text` and `translator_version` (skill version plus exposed model or
session identification; do not invent unavailable model versions). Add glossary,
ambiguity notes, source URL/original-file hash/extraction details, and page locators
as appropriate. Offsets include any page markers. Keep segments in increasing order.
Empty translations are invalid; placeholders do not resolve missing material.

Translated and untranslated intervals must partition the source exactly. Validation
checks source hash, exact spans, nonempty output, ordered/nonoverlapping coverage and
declared scope. It emits canonical artifact SHA-256 and coverage counts. It cannot
detect mistranslation, OCR omissions, incorrect numerical meaning, or misleading review
claims. Markdown rendering labels translated spans and records source hash/coverage;
it does not manufacture an accepted review badge or reproduce original page layout.
Keep the bilingual JSON as the auditable companion.

## Review artifact

Write separate JSON with `source_sha256`, `translation_sha256` from validation,
`reviewer_session`, `independent` (boolean), `verdict` (`pass`, `revise`, `blocked`),
and `criteria`: `meaning`, `numbers_units_periods`, `attribution`, `coverage`.
Each criterion has `status` (`pass`, `fail`, `unavailable`) and concrete `evidence`.
`findings` identifies offsets, the issue, materiality and requested repair. Pass
requires all criteria to pass. Bind review to the final artifact hash. A partial
translation can pass only for its selected scope, never imply full-document review.
